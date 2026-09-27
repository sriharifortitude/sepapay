"""Independent verification of a pain.001.001.09 file, for the person who approves it.

A payment run is usually prepared by one person and released by another
(four-eyes). The approver should check the file that will actually be
uploaded, not the spreadsheet it came from and not the tool that built it.
This module re-reads the XML from scratch, shares no state with the builder,
and recomputes everything a hand edit or a buggy generator could get wrong:
the counts and control sums, every IBAN and RF checksum, duplicate
EndToEndIds, the execution date. It reports what the bank would be asked
to do, with a SHA-256 of the exact bytes so the approval can name the file.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from lxml import etree

from sepapay import iban as ibanlib
from sepapay import reference as rf
from sepapay import target2
from sepapay.schema import NAMESPACE, safe_parser, schema_errors

_NS = {"p": NAMESPACE}


@dataclass(frozen=True)
class Line:
    creditor: str
    iban: str
    amount: Decimal
    end_to_end_id: str
    reference: str


@dataclass
class Report:
    sha256: str
    message_id: str = ""
    debtor: str = ""
    debtor_iban: str = ""
    execution_dates: list[str] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def total(self) -> Decimal:
        return sum((line.amount for line in self.lines), Decimal(0))

    @property
    def ok(self) -> bool:
        return not self.problems


def verify(data: bytes) -> Report:
    report = Report(sha256=hashlib.sha256(data).hexdigest())

    if b"<!DOCTYPE" in data[:4096].upper():
        report.problems.append("the file declares a DOCTYPE; a pain.001 has none, and it is refused unread")
        return report
    try:
        root = etree.fromstring(data, safe_parser())
    except etree.XMLSyntaxError as exc:
        report.problems.append(f"not well-formed XML: {exc}")
        return report
    if etree.QName(root).namespace != NAMESPACE:
        report.problems.append(
            f"not a pain.001.001.09 document (namespace {etree.QName(root).namespace!r}); sepapay reads version 09 only"
        )
        return report

    report.problems.extend(f"schema: {e}" for e in schema_errors(root))
    if report.problems:
        return report  # the checks below assume the structure the schema guarantees

    header = _one(root, "p:CstmrCdtTrfInitn/p:GrpHdr")
    report.message_id = _text(header, "p:MsgId")

    all_amounts: list[Decimal] = []
    for info in root.iterfind("p:CstmrCdtTrfInitn/p:PmtInf", _NS):
        _check_payment_info(info, report, all_amounts)

    _check_sums(report, "group header", header, all_amounts)

    counts = Counter(line.end_to_end_id for line in report.lines if line.end_to_end_id != "NOTPROVIDED")
    for end_to_end_id, n in sorted(counts.items()):
        if n > 1:
            report.problems.append(f"EndToEndId {end_to_end_id} appears {n} times")
    return report


def _check_payment_info(info: etree._Element, report: Report, all_amounts: list[Decimal]) -> None:
    pmt_id = _text(info, "p:PmtInfId")
    where = f"payment information {pmt_id}"

    for path, expected, what in (
        ("p:PmtMtd", "TRF", "payment method"),
        ("p:PmtTpInf/p:SvcLvl/p:Cd", "SEPA", "service level"),
        ("p:ChrgBr", "SLEV", "charge bearer"),
    ):
        actual = _text(info, path)
        if actual != expected:
            report.problems.append(f"{where}: {what} is {actual or 'missing'}, a SEPA credit transfer needs {expected}")

    report.debtor = _text(info, "p:Dbtr/p:Nm")
    report.debtor_iban = _text(info, "p:DbtrAcct/p:Id/p:IBAN")
    if not report.debtor_iban:
        report.problems.append(f"{where}: the debtor account is not an IBAN")
    elif problem := ibanlib.iban_problem(report.debtor_iban):
        report.problems.append(f"{where}: debtor IBAN {report.debtor_iban}: {problem}")

    date_text = _text(info, "p:ReqdExctnDt/p:Dt")
    report.execution_dates.append(date_text or "(not a plain date)")
    if date_text:
        closed = target2.closed_because(dt.date.fromisoformat(date_text))
        if closed:
            report.problems.append(f"{where}: execution date {date_text} is a TARGET2 closing day ({closed})")

    amounts: list[Decimal] = []
    for tx in info.iterfind("p:CdtTrfTxInf", _NS):
        line = _check_transaction(tx, where, report)
        amounts.append(line.amount)
        report.lines.append(line)
    all_amounts.extend(amounts)
    _check_sums(report, where, info, amounts)


def _check_transaction(tx: etree._Element, where: str, report: Report) -> Line:
    end_to_end_id = _text(tx, "p:PmtId/p:EndToEndId")
    at = f"{where}, EndToEndId {end_to_end_id}"

    amount_el = _one(tx, "p:Amt/p:InstdAmt")
    amount = Decimal(amount_el.text or "0")
    if amount_el.get("Ccy") != "EUR":
        report.problems.append(f"{at}: currency {amount_el.get('Ccy')}, a SEPA credit transfer is in EUR")
    if amount.as_tuple().exponent < -2:  # type: ignore[operator]
        report.problems.append(f"{at}: amount {amount} has more than two decimals")

    creditor_iban = _text(tx, "p:CdtrAcct/p:Id/p:IBAN")
    if not creditor_iban:
        report.problems.append(f"{at}: the creditor account is not an IBAN")
    elif problem := ibanlib.iban_problem(creditor_iban):
        report.problems.append(f"{at}: creditor IBAN {creditor_iban}: {problem}")

    reference = _text(tx, "p:RmtInf/p:Strd/p:CdtrRefInf/p:Ref")
    is_rf = _text(tx, "p:RmtInf/p:Strd/p:CdtrRefInf/p:Tp/p:CdOrPrtry/p:Cd") == "SCOR"
    if reference and is_rf and (problem := rf.rf_problem(reference)):
        report.problems.append(f"{at}: creditor reference {reference}: {problem}")
    reference = reference or _text(tx, "p:RmtInf/p:Ustrd")

    return Line(_text(tx, "p:Cdtr/p:Nm"), creditor_iban, amount, end_to_end_id, reference)


def _check_sums(report: Report, where: str, element: etree._Element, amounts: list[Decimal]) -> None:
    declared_count = _text(element, "p:NbOfTxs")
    if declared_count != str(len(amounts)):
        report.problems.append(f"{where}: NbOfTxs says {declared_count}, the file contains {len(amounts)}")
    declared_sum = _text(element, "p:CtrlSum")
    if not declared_sum:
        return  # optional in the schema; only a CtrlSum that disagrees is a problem
    try:
        declared = Decimal(declared_sum)
    except InvalidOperation:
        report.problems.append(f"{where}: CtrlSum {declared_sum!r} is not a number")
        return
    actual = sum(amounts, Decimal(0))
    if declared != actual:
        report.problems.append(f"{where}: CtrlSum says {declared}, the transactions add up to {actual}")


def _one(element: etree._Element, path: str) -> etree._Element:
    found = element.find(path, _NS)
    if found is None:
        raise ValueError(f"{path} missing, though the schema requires it")
    return found


def _text(element: etree._Element, path: str) -> str:
    found = element.find(path, _NS)
    return (found.text or "").strip() if found is not None else ""
