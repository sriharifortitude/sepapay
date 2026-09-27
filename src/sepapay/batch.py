"""Reading a payment run: who pays (a TOML file) and whom (a CSV).

Every problem is collected with its row number rather than stopping at the
first, so one run tells the person preparing the file everything to fix.
Nothing is written unless there are no errors at all.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import tomllib
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from sepapay import iban as ibanlib
from sepapay import reference as rf
from sepapay import target2
from sepapay.money import AmountError, parse_amount
from sepapay.text import TextError, identifier, to_sepa

NOT_PROVIDED = "NOTPROVIDED"  # the EPC's own placeholder for a missing EndToEndId

REQUIRED_COLUMNS = ("name", "iban", "amount")
OPTIONAL_COLUMNS = ("bic", "reference", "end_to_end_id")


@dataclass(frozen=True)
class Debtor:
    name: str
    iban: str
    bic: str | None
    execution_date: dt.date
    batch_booking: bool


@dataclass(frozen=True)
class Payment:
    row: int
    creditor_name: str
    iban: str
    bic: str | None
    amount: Decimal
    end_to_end_id: str
    remittance: str | None
    """Free text, when the reference isn't an RF creditor reference."""
    creditor_reference: str | None
    """A validated ISO 11649 RF reference, sent structured."""


@dataclass
class Problems:
    errors: list[str]
    warnings: list[str]

    def __bool__(self) -> bool:
        return bool(self.errors)


def load_debtor(toml_text: str, today: dt.date) -> tuple[Debtor | None, list[str]]:
    errors: list[str] = []
    try:
        data = tomllib.loads(toml_text)
    except tomllib.TOMLDecodeError as exc:
        return None, [f"debtor file: not valid TOML: {exc}"]

    unknown = set(data) - {"name", "iban", "bic", "execution_date", "batch_booking"}
    if unknown:
        errors.append(f"debtor file: unknown key(s) {', '.join(sorted(unknown))}")

    name = _field(errors, "debtor name", lambda: to_sepa(_str(data, "name"), "debtor name", 70))
    iban = _checked_iban(errors, "debtor iban", _str(data, "iban", errors=errors))
    bic = _checked_bic(errors, "debtor bic", data.get("bic"))

    execution_date = data.get("execution_date")
    if not isinstance(execution_date, dt.date) or isinstance(execution_date, dt.datetime):
        errors.append("debtor file: execution_date must be a TOML date, e.g. execution_date = 2026-10-01")
        execution_date = None
    else:
        if execution_date < today:
            errors.append(f"execution_date {execution_date} is in the past")
        closed = target2.closed_because(execution_date)
        if closed:
            errors.append(
                f"execution_date {execution_date}: TARGET2 is closed ({closed}); "
                f"the next business day is {target2.next_business_day(execution_date)}"
            )

    batch_booking = data.get("batch_booking", True)
    if not isinstance(batch_booking, bool):
        errors.append("debtor file: batch_booking must be true or false")
        batch_booking = True

    if errors or name is None or iban is None or execution_date is None:
        return None, errors
    return Debtor(name, iban, bic, execution_date, batch_booking), errors


def load_payments(csv_text: str) -> tuple[list[Payment], Problems]:
    problems = Problems(errors=[], warnings=[])
    reader = csv.DictReader(io.StringIO(csv_text))
    columns = [c.strip() for c in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    unknown = [c for c in columns if c not in REQUIRED_COLUMNS + OPTIONAL_COLUMNS]
    if missing:
        problems.errors.append(f"payments file: missing column(s) {', '.join(missing)}")
    if unknown:
        problems.errors.append(
            f"payments file: unknown column(s) {', '.join(unknown)} "
            f"(expected {', '.join(REQUIRED_COLUMNS + OPTIONAL_COLUMNS)})"
        )
    if problems.errors:
        return [], problems

    payments: list[Payment] = []
    for row_number, raw in enumerate(reader, start=2):  # row 1 is the header
        row = {k.strip(): (v or "").strip() for k, v in raw.items() if k is not None}
        if not any(row.values()):
            continue
        payment = _payment(row_number, row, problems.errors)
        if payment is not None:
            payments.append(payment)

    if not payments and not problems.errors:
        problems.errors.append("payments file: no payments")
    _check_duplicates(payments, problems)
    return payments, problems


def _payment(row_number: int, row: dict[str, str], errors: list[str]) -> Payment | None:
    before = len(errors)
    at = f"row {row_number}"

    name = _field(errors, f"{at}, name", lambda: to_sepa(row["name"], f"{at}, name", 70))
    iban = _checked_iban(errors, f"{at}, iban", row["iban"])
    bic = _checked_bic(errors, f"{at}, bic", row.get("bic") or None)
    amount = _field(errors, f"{at}, amount", lambda: parse_amount(row["amount"]))

    end_to_end = row.get("end_to_end_id") or NOT_PROVIDED
    end_to_end_id = _field(errors, f"{at}, end_to_end_id", lambda: identifier(end_to_end, f"{at}, end_to_end_id"))

    remittance: str | None = None
    creditor_reference: str | None = None
    reference = row.get("reference") or ""
    if reference and rf.looks_like_rf(reference):
        normalized = rf.normalize_reference(reference)
        problem = rf.rf_problem(normalized)
        if problem:
            errors.append(f"{at}, reference: {problem}")
        creditor_reference = normalized
    elif reference:
        remittance = _field(errors, f"{at}, reference", lambda: to_sepa(reference, f"{at}, reference", 140))

    if len(errors) > before or name is None or iban is None or amount is None or end_to_end_id is None:
        return None
    return Payment(row_number, name, iban, bic, amount, end_to_end_id, remittance, creditor_reference)


def check_against_debtor(debtor: Debtor, payments: list[Payment], problems: Problems) -> None:
    for p in payments:
        if p.iban == debtor.iban:
            problems.warnings.append(f"row {p.row} pays the debtor's own account {p.iban}")


def _check_duplicates(payments: list[Payment], problems: Problems) -> None:
    by_id: dict[str, list[int]] = defaultdict(list)
    by_content: dict[tuple[str, Decimal, str], list[int]] = defaultdict(list)
    for p in payments:
        if p.end_to_end_id != NOT_PROVIDED:
            by_id[p.end_to_end_id].append(p.row)
        by_content[(p.iban, p.amount, p.creditor_reference or p.remittance or "")].append(p.row)
    for end_to_end_id, rows in by_id.items():
        if len(rows) > 1:
            problems.errors.append(f"end_to_end_id {end_to_end_id} is used on rows {_rows(rows)}; it must be unique")
    for (iban, amount, ref), rows in by_content.items():
        if len(rows) > 1:
            what = f" with reference {ref!r}" if ref else ""
            problems.warnings.append(
                f"rows {_rows(rows)} pay {amount} to {iban}{what}: the same payment more than once?"
            )


def _rows(rows: list[int]) -> str:
    return ", ".join(str(r) for r in rows)


def _str(data: dict[str, object], key: str, errors: list[str] | None = None) -> str:
    value = data.get(key)
    if isinstance(value, str):
        return value
    if errors is not None:
        errors.append(f"debtor file: {key} is required")
    return ""


def _checked_iban(errors: list[str], where: str, raw: str) -> str | None:
    if not raw:
        return None
    normalized = ibanlib.normalize_iban(raw)
    problem = ibanlib.iban_problem(normalized)
    if problem:
        errors.append(f"{where}: {problem}")
        return None
    return normalized


def _checked_bic(errors: list[str], where: str, raw: object) -> str | None:
    if raw is None or raw == "":
        return None  # optional: IBAN-only has been the SEPA default since 2016
    if not isinstance(raw, str):
        errors.append(f"{where}: must be text")
        return None
    normalized = "".join(raw.split()).upper()
    problem = ibanlib.bic_problem(normalized)
    if problem:
        errors.append(f"{where}: {problem}")
        return None
    return normalized


def _field[T](errors: list[str], where: str, produce: Callable[[], T]) -> T | None:
    try:
        return produce()
    except (TextError, AmountError) as exc:
        message = str(exc)
        errors.append(message if message.startswith(where) else f"{where}: {message}")
        return None
    except KeyError:
        errors.append(f"{where}: required")
        return None
