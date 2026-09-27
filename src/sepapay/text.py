"""The SEPA character set and field rules.

The EPC's SEPA rulebooks guarantee only a basic Latin set end to end:

    a-z A-Z 0-9 / - ? : ( ) . , ' + and space

A bank may accept more, but anything outside that set can be rejected,
replaced or garbled by any bank along the chain, so a supplier called
"Müller" can arrive as "M?ller" or bounce the whole file. The conversion
here is deterministic and documented, and anything it can't convert is an
error that names the character, never a silent replacement.
"""

from __future__ import annotations

import re
import unicodedata

_ALLOWED = re.compile(r"^[A-Za-z0-9/\-?:().,'+ ]*$")

# Letters that don't decompose under NFKD into a base letter plus accents.
# Every other accented Latin letter (é, ä, ñ, č, ő, ...) loses its
# diacritics through decomposition. "&" -> "+" is this library's choice,
# not an EPC rule: it keeps "Müller & Söhne" readable instead of refusing it.
_EXPLICIT = {
    "ß": "ss", "ẞ": "SS", "Æ": "AE", "æ": "ae", "Ø": "O", "ø": "o", "Œ": "OE", "œ": "oe",
    "Ł": "L", "ł": "l", "Đ": "D", "đ": "d", "Þ": "TH", "þ": "th", "Ð": "D", "ð": "d",
    "&": "+",
    "\u2019": "'", "\u2018": "'",  # typographic single quotes
    "\u2013": "-", "\u2014": "-",  # en and em dash
    "\u00a0": " ",  # no-break space
}  # fmt: skip


class TextError(ValueError):
    pass


def to_sepa(value: str, field: str, max_length: int) -> str:
    """Convert to the SEPA basic Latin set, or raise TextError naming what couldn't be."""
    converted = "".join(_EXPLICIT.get(ch, ch) for ch in value)
    converted = "".join(ch for ch in unicodedata.normalize("NFKD", converted) if not unicodedata.combining(ch))
    converted = " ".join(converted.split())  # collapse runs of whitespace, strip ends
    if not _ALLOWED.match(converted):
        bad = sorted({ch for ch in converted if not _ALLOWED.match(ch)})
        raise TextError(f"{field}: {' '.join(repr(c) for c in bad)} can't be represented in the SEPA character set")
    if not converted:
        raise TextError(f"{field}: empty")
    if len(converted) > max_length:
        raise TextError(f"{field}: {len(converted)} characters after conversion, the maximum is {max_length}")
    return converted


def identifier(value: str, field: str) -> str:
    """An EPC identifier (MsgId, PmtInfId, EndToEndId): max 35, SEPA set, no leading/trailing '/', no '//'."""
    result = to_sepa(value, field, 35)
    if result.startswith("/") or result.endswith("/") or "//" in result:
        raise TextError(f"{field}: identifiers can't start or end with '/' or contain '//'")
    return result
