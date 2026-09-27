"""Amounts: exact decimals in euro, as the SCT rulebook allows them."""

from __future__ import annotations

import re
from decimal import Decimal

MIN_AMOUNT = Decimal("0.01")
MAX_AMOUNT = Decimal("999999999.99")  # the SCT rulebook's per-transaction maximum

# A plain decimal with "." and at most two places. "1,000.50" and "1.000,50"
# are refused outright: guessing which convention a CSV used is how 1,005
# becomes 1.005 or 1005.
_AMOUNT = re.compile(r"^[0-9]+(\.[0-9]{1,2})?$")


class AmountError(ValueError):
    pass


def parse_amount(raw: str) -> Decimal:
    text = raw.strip()
    if not _AMOUNT.match(text):
        raise AmountError(
            f"{raw!r} is not an amount: use digits with an optional '.' and at most two decimals, "
            "no thousands separators"
        )
    value = Decimal(text)
    if value < MIN_AMOUNT:
        raise AmountError(f"{raw!r}: the smallest SEPA credit transfer is 0.01")
    if value > MAX_AMOUNT:
        raise AmountError(f"{raw!r}: over the SCT maximum of 999999999.99 per transaction")
    return value.quantize(Decimal("0.01"))


def format_amount(value: Decimal) -> str:
    """Always two decimals: pain.001 amounts are decimal strings, and '10' vs '10.00' should never vary."""
    return f"{value.quantize(Decimal('0.01')):f}"
