import datetime as dt

from sepapay.batch import NOT_PROVIDED, Debtor, Payment, Problems, check_against_debtor, load_debtor, load_payments
from tests.conftest import DEBTOR_TOML, PAYMENTS_CSV, TODAY


def test_reads_a_valid_run(debtor: Debtor, payments: list[Payment]) -> None:
    assert debtor.name == "Muller + Sohne GmbH"
    assert debtor.iban == "DE89370400440532013000"
    assert [p.end_to_end_id for p in payments] == ["INV-1001", "INV-1002", "INV-1003", "INV-1004"]
    acme = payments[0]
    assert acme.creditor_reference == "RF18539007547034"
    assert acme.remittance is None
    assert payments[1].remittance == "Rechnung 42"


def test_warns_about_what_looks_like_the_same_payment_twice() -> None:
    _, problems = load_payments(PAYMENTS_CSV)
    assert problems.errors == []
    assert problems.warnings == ["rows 4, 5 pay 0.10 to BE68539007547034: the same payment more than once?"]


def test_collects_every_error_with_its_row_instead_of_stopping_at_the_first() -> None:
    csv = (
        "name,iban,amount,reference,end_to_end_id\n"
        "Good Ltd,DE89370400440532013000,10.00,,A-1\n"
        "Typo GmbH,DE89370400440532013001,10.00,,A-2\n"
        'Comma AG,DE89370400440532013000,"1,000.00",,A-3\n'
        "Bad Ref BV,DE89370400440532013000,5.00,RF18539007547035,A-4\n"
    )
    payments, problems = load_payments(csv)
    assert [p.row for p in payments] == [2]
    assert len(problems.errors) == 3
    assert problems.errors[0].startswith("row 3, iban: check digits")
    assert problems.errors[1].startswith("row 4, amount:")
    assert problems.errors[2].startswith("row 5, reference: RF check digits")


def test_duplicate_end_to_end_ids_are_an_error_but_notprovided_is_not() -> None:
    csv = (
        "name,iban,amount,end_to_end_id\n"
        "A,DE89370400440532013000,1.00,X-1\n"
        "B,GB82WEST12345698765432,2.00,X-1\n"
        "C,GB82WEST12345698765432,3.00,\n"
        "D,GB82WEST12345698765432,4.00,\n"
    )
    payments, problems = load_payments(csv)
    assert problems.errors == ["end_to_end_id X-1 is used on rows 2, 3; it must be unique"]
    assert [p.end_to_end_id for p in payments][2:] == [NOT_PROVIDED, NOT_PROVIDED]


def test_an_unknown_column_is_an_error_not_silently_ignored() -> None:
    _, problems = load_payments("name,iban,ammount\nA,DE89370400440532013000,1.00\n")
    assert any("unknown column(s) ammount" in e for e in problems.errors)
    assert any("missing column(s) amount" in e for e in problems.errors)


def test_execution_date_on_a_closing_day_names_the_next_business_day() -> None:
    toml = DEBTOR_TOML.replace("2026-10-01", "2026-12-25")
    debtor, errors = load_debtor(toml, TODAY)
    assert debtor is None
    assert errors == [
        "execution_date 2026-12-25: TARGET2 is closed (Christmas Day); the next business day is 2026-12-28"
    ]


def test_execution_date_in_the_past_is_refused() -> None:
    _, errors = load_debtor(DEBTOR_TOML, dt.date(2026, 10, 2))
    assert errors == ["execution_date 2026-10-01 is in the past"]


def test_warns_when_a_payment_goes_to_the_debtors_own_account(debtor: Debtor) -> None:
    payments, problems = load_payments("name,iban,amount\nSelf,DE89370400440532013000,5.00\n")
    check_against_debtor(debtor, payments, problems)
    assert problems.warnings == ["row 2 pays the debtor's own account DE89370400440532013000"]
    assert isinstance(problems, Problems)
