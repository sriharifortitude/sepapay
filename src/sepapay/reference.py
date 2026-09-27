"""ISO 11649 structured creditor references ("RF" references).

A creditor reference lets the payee's bank statement carry exactly the
reference their accounts-receivable system issued, instead of whatever
free text the payer typed. camtmatch, elsewhere in this portfolio, matches
incoming payments to invoices by this reference first, so a pain.001
that carries it structured is the other end of the same wire.
"""

from __future__ import annotations

import re

from sepapay.iban import mod97

_RF_SHAPE = re.compile(r"^RF[0-9]{2}[A-Z0-9]{1,21}$")


def normalize_reference(raw: str) -> str:
    return "".join(raw.split()).upper()


def looks_like_rf(raw: str) -> bool:
    return normalize_reference(raw).startswith("RF")


def rf_problem(ref: str) -> str | None:
    """Why this (normalized) RF reference is invalid, or None. Max 25 characters, mod 97 = 1."""
    if not _RF_SHAPE.match(ref):
        return "not an RF creditor reference: RF, two check digits, then up to 21 letters and digits"
    if mod97(ref[4:] + ref[:4]) != 1:
        return "RF check digits don't match: the reference is mistyped"
    return None
