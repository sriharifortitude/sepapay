import datetime as dt

import pytest

from sepapay.batch import Debtor, Payment, load_debtor, load_payments

TODAY = dt.date(2026, 9, 27)
NOW = dt.datetime(2026, 9, 27, 10, 0, tzinfo=dt.UTC)

DEBTOR_TOML = """\
name = "Müller & Söhne GmbH"
iban = "DE89 3704 0044 0532 0130 00"
bic = "COBADEFFXXX"
execution_date = 2026-10-01
"""

PAYMENTS_CSV = """\
name,iban,bic,amount,reference,end_to_end_id
Acme Ltd,GB82 WEST 1234 5698 7654 32,,1250.00,RF18 5390 0754 7034,INV-1001
Büro Nord,NL91 ABNA 0417 1643 00,ABNANL2A,0.10,Rechnung 42,INV-1002
Café Süd,BE68 5390 0754 7034,,0.10,,INV-1003
Café Süd,BE68 5390 0754 7034,,0.10,,INV-1004
"""


@pytest.fixture
def debtor() -> Debtor:
    result, errors = load_debtor(DEBTOR_TOML, TODAY)
    assert result is not None, errors
    return result


@pytest.fixture
def payments() -> list[Payment]:
    result, problems = load_payments(PAYMENTS_CSV)
    assert not problems.errors, problems.errors
    return result
