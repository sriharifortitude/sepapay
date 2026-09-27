"""Building the pain.001.001.09 document.

The output is validated against the official ISO 20022 schema before it's
returned. A file this module produced and the schema rejects is a bug here,
and it raises instead of being written.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from decimal import Decimal

from lxml import etree

from sepapay.batch import Debtor, Payment
from sepapay.money import format_amount
from sepapay.schema import NAMESPACE, schema_errors

_NS = f"{{{NAMESPACE}}}"


class InvalidDocumentError(RuntimeError):
    pass


def message_id(debtor: Debtor, payments: list[Payment]) -> str:
    """Derived from the payment run's content, not random.

    Banks refuse a second file with a MsgId they've already processed.
    Rebuilding the same run (someone re-runs the tool, the file is exported
    twice) therefore produces the same MsgId, and an accidental double
    upload bounces at the bank instead of paying every supplier twice. A
    genuinely different run always gets a different one. docs/adr/0002.
    """
    digest = hashlib.sha256()
    digest.update(f"{debtor.iban}|{debtor.execution_date.isoformat()}".encode())
    for p in payments:
        reference = p.creditor_reference or p.remittance or ""
        digest.update(f"|{p.iban}|{format_amount(p.amount)}|{p.end_to_end_id}|{reference}".encode())
    return f"SEPAPAY-{debtor.execution_date:%Y%m%d}-{digest.hexdigest()[:12].upper()}"


def build(debtor: Debtor, payments: list[Payment], created_at: dt.datetime) -> bytes:
    if created_at.tzinfo is None:
        raise ValueError("created_at must be timezone-aware")
    if not payments:
        raise ValueError("a payment file needs at least one payment")

    msg_id = message_id(debtor, payments)
    count = str(len(payments))
    total = format_amount(sum((p.amount for p in payments), Decimal(0)))

    # None is lxml's key for the default namespace; lxml-stubs types nsmap keys as str only.
    doc = etree.Element(_NS + "Document", nsmap={None: NAMESPACE})  # type: ignore[dict-item]
    initiation = _sub(doc, "CstmrCdtTrfInitn")

    header = _sub(initiation, "GrpHdr")
    _sub(header, "MsgId", msg_id)
    _sub(header, "CreDtTm", created_at.astimezone(dt.UTC).replace(microsecond=0).isoformat())
    _sub(header, "NbOfTxs", count)
    _sub(header, "CtrlSum", total)
    _sub(_sub(header, "InitgPty"), "Nm", debtor.name)

    info = _sub(initiation, "PmtInf")
    _sub(info, "PmtInfId", f"{msg_id}-1")
    _sub(info, "PmtMtd", "TRF")
    _sub(info, "BtchBookg", "true" if debtor.batch_booking else "false")
    _sub(info, "NbOfTxs", count)
    _sub(info, "CtrlSum", total)
    _sub(_sub(_sub(info, "PmtTpInf"), "SvcLvl"), "Cd", "SEPA")
    _sub(_sub(info, "ReqdExctnDt"), "Dt", debtor.execution_date.isoformat())
    _sub(_sub(info, "Dbtr"), "Nm", debtor.name)
    _sub(_sub(_sub(info, "DbtrAcct"), "Id"), "IBAN", debtor.iban)
    _agent(info, "DbtrAgt", debtor.bic, required=True)
    _sub(info, "ChrgBr", "SLEV")  # SEPA: each side pays its own bank's charges

    for p in payments:
        tx = _sub(info, "CdtTrfTxInf")
        _sub(_sub(tx, "PmtId"), "EndToEndId", p.end_to_end_id)
        amount = _sub(_sub(tx, "Amt"), "InstdAmt", format_amount(p.amount))
        amount.set("Ccy", "EUR")
        _agent(tx, "CdtrAgt", p.bic, required=False)
        _sub(_sub(tx, "Cdtr"), "Nm", p.creditor_name)
        _sub(_sub(_sub(tx, "CdtrAcct"), "Id"), "IBAN", p.iban)
        if p.creditor_reference:
            structured = _sub(_sub(tx, "RmtInf"), "Strd")
            ref_info = _sub(structured, "CdtrRefInf")
            ref_type = _sub(ref_info, "Tp")
            _sub(_sub(ref_type, "CdOrPrtry"), "Cd", "SCOR")
            _sub(ref_type, "Issr", "ISO")
            _sub(ref_info, "Ref", p.creditor_reference)
        elif p.remittance:
            _sub(_sub(tx, "RmtInf"), "Ustrd", p.remittance)

    problems = schema_errors(doc)
    if problems:
        raise InvalidDocumentError("generated file fails the pain.001.001.09 schema:\n" + "\n".join(problems))
    serialized: bytes = etree.tostring(doc, xml_declaration=True, encoding="UTF-8", pretty_print=True)
    return serialized


def _sub(parent: etree._Element, tag: str, text: str | None = None) -> etree._Element:
    element = etree.SubElement(parent, _NS + tag)
    if text is not None:
        element.text = text
    return element


def _agent(parent: etree._Element, tag: str, bic: str | None, *, required: bool) -> None:
    if bic:
        _sub(_sub(_sub(parent, tag), "FinInstnId"), "BICFI", bic)
    elif required:
        # The debtor agent is mandatory in the schema; with IBAN-only the
        # EPC implementation guidelines use NOTPROVIDED here.
        _sub(_sub(_sub(_sub(parent, tag), "FinInstnId"), "Othr"), "Id", "NOTPROVIDED")
