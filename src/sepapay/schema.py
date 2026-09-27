"""The official ISO 20022 pain.001.001.09 schema, and a parser that can't be abused."""

from __future__ import annotations

from collections.abc import Iterable
from functools import cache
from importlib import resources
from typing import cast

from lxml import etree

NAMESPACE = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.09"


@cache
def pain001_schema() -> etree.XMLSchema:
    xsd = resources.files("sepapay.schemas").joinpath("pain.001.001.09.xsd").read_bytes()
    return etree.XMLSchema(etree.fromstring(xsd, safe_parser()))


def safe_parser() -> etree.XMLParser:
    """No DTDs, no entity expansion, no network: a pain.001 has no business with any of them,
    and each is an XXE or billion-laughs vector in a file that came from somewhere else."""
    return etree.XMLParser(
        resolve_entities=False, no_network=True, load_dtd=False, dtd_validation=False, huge_tree=False
    )


def schema_errors(document: etree._Element) -> list[str]:
    schema = pain001_schema()
    if schema.validate(document):
        return []
    # lxml-stubs types _ErrorLog as non-iterable; at runtime it iterates _LogEntry objects.
    entries = cast("Iterable[etree._LogEntry]", schema.error_log)
    return [f"line {e.line}: {e.message}" for e in entries]
