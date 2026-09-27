"""IBAN and BIC checks for SEPA.

An IBAN is valid when it has the right length for its country and its two
check digits make the whole number congruent to 1 modulo 97 (ISO 13616).
The check catches every single-character typo and nearly every swap of two
adjacent characters, which is exactly the class of mistake a person keying
a supplier's bank details makes.
"""

from __future__ import annotations

import re

# Countries and territories whose IBANs can be used in a SEPA Credit
# Transfer, with the IBAN length for each (ISO 13616 registry). This is the
# long-standing 36-member scheme area: the EU 27, the rest of the EEA
# (IS, LI, NO), and CH, GB, MC, SM, AD, VA. The EPC has admitted further
# countries since; they aren't listed here, so a payment to one is
# refused rather than guessed at. French overseas departments and
# territories use FR IBANs, so they are covered by FR.
SEPA_IBAN_LENGTHS: dict[str, int] = {
    "AD": 24, "AT": 20, "BE": 16, "BG": 22, "CH": 21, "CY": 28, "CZ": 24, "DE": 22, "DK": 18,
    "EE": 20, "ES": 24, "FI": 18, "FR": 27, "GB": 22, "GR": 27, "HR": 21, "HU": 28, "IE": 22,
    "IS": 26, "IT": 27, "LI": 21, "LT": 20, "LU": 20, "LV": 21, "MC": 27, "MT": 31, "NL": 18,
    "NO": 15, "PL": 28, "PT": 25, "RO": 24, "SE": 24, "SI": 19, "SK": 24, "SM": 27, "VA": 22,
}  # fmt: skip

_IBAN_SHAPE = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]+$")
_BIC_SHAPE = re.compile(r"^[A-Z]{4}([A-Z]{2})[A-Z0-9]{2}([A-Z0-9]{3})?$")


def normalize_iban(raw: str) -> str:
    """Upper-case and strip the spaces people write IBANs with."""
    return "".join(raw.split()).upper()


def mod97(digits_and_letters: str) -> int:
    """The ISO 7064 MOD 97-10 remainder, letters counted as A=10 ... Z=35.

    Shared by IBANs (ISO 13616) and RF creditor references (ISO 11649).
    """
    numeric = "".join(str(int(c, 36)) for c in digits_and_letters)
    return int(numeric) % 97


def iban_problem(iban: str) -> str | None:
    """Why this (normalized) IBAN can't be paid by SEPA Credit Transfer, or None if it can."""
    if not _IBAN_SHAPE.match(iban):
        return "not an IBAN: two letters, two check digits, then letters and digits"
    country = iban[:2]
    expected = SEPA_IBAN_LENGTHS.get(country)
    if expected is None:
        return f"{country} is not a SEPA country"
    if len(iban) != expected:
        return f"{country} IBANs are {expected} characters, this one is {len(iban)}"
    if mod97(iban[4:] + iban[:4]) != 1:
        return "check digits don't match: a character is mistyped or two are swapped"
    return None


def bic_problem(bic: str) -> str | None:
    """Why this BIC is malformed, or None. Format only: nothing checks a BIC is registered."""
    match = _BIC_SHAPE.match(bic)
    if not match:
        return "not a BIC: 4 letters (bank), 2 letters (country), 2 letters/digits (location), optional 3 (branch)"
    return None
