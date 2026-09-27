import dataclasses
import hashlib
from decimal import Decimal
from importlib import resources

from lxml import etree

from sepapay.batch import Debtor, Payment
from sepapay.builder import build, message_id
from sepapay.schema import NAMESPACE, pain001_schema, safe_parser
from sepapay.verify import verify
from tests.conftest import NOW

NS = {"p": NAMESPACE}


def test_bundled_schema_is_the_unmodified_iso_file() -> None:
    xsd = resources.files("sepapay.schemas").joinpath("pain.001.001.09.xsd").read_bytes()
    assert hashlib.sha256(xsd).hexdigest() == "de038b373e47b0077b1832ddd81f4b2f1eb25d35721f62da1e38b7f5a09fda24"


def test_output_passes_the_official_schema(debtor: Debtor, payments: list[Payment]) -> None:
    root = etree.fromstring(build(debtor, payments, NOW), safe_parser())
    assert pain001_schema().validate(root)


def test_control_sums_are_exact_decimal(debtor: Debtor, payments: list[Payment]) -> None:
    # 1250.00 + 0.10 + 0.10 + 0.10: in binary floating point 0.1 * 3 is not 0.3.
    root = etree.fromstring(build(debtor, payments, NOW), safe_parser())
    assert root.findtext("p:CstmrCdtTrfInitn/p:GrpHdr/p:CtrlSum", namespaces=NS) == "1250.30"
    assert root.findtext("p:CstmrCdtTrfInitn/p:PmtInf/p:CtrlSum", namespaces=NS) == "1250.30"
    assert root.findtext("p:CstmrCdtTrfInitn/p:GrpHdr/p:NbOfTxs", namespaces=NS) == "4"


def test_rf_reference_goes_structured_and_free_text_unstructured(debtor: Debtor, payments: list[Payment]) -> None:
    root = etree.fromstring(build(debtor, payments, NOW), safe_parser())
    txs = root.findall("p:CstmrCdtTrfInitn/p:PmtInf/p:CdtTrfTxInf", NS)
    assert txs[0].findtext("p:RmtInf/p:Strd/p:CdtrRefInf/p:Ref", namespaces=NS) == "RF18539007547034"
    assert txs[0].findtext("p:RmtInf/p:Strd/p:CdtrRefInf/p:Tp/p:CdOrPrtry/p:Cd", namespaces=NS) == "SCOR"
    assert txs[1].findtext("p:RmtInf/p:Ustrd", namespaces=NS) == "Rechnung 42"
    assert txs[1].findtext("p:CdtrAgt/p:FinInstnId/p:BICFI", namespaces=NS) == "ABNANL2A"
    assert txs[0].find("p:CdtrAgt", NS) is None  # IBAN-only: no agent at all


def test_message_id_is_stable_for_the_same_run_and_changes_with_it(debtor: Debtor, payments: list[Payment]) -> None:
    first = message_id(debtor, payments)
    assert first == message_id(debtor, list(payments))
    assert first.startswith("SEPAPAY-20261001-") and len(first) <= 35
    changed = [dataclasses.replace(payments[0], amount=Decimal("1250.01")), *payments[1:]]
    assert message_id(debtor, changed) != first


def test_verify_accepts_what_build_produced(debtor: Debtor, payments: list[Payment]) -> None:
    data = build(debtor, payments, NOW)
    report = verify(data)
    assert report.problems == []
    assert report.total == Decimal("1250.30")
    assert len(report.lines) == 4
    assert report.sha256 == hashlib.sha256(data).hexdigest()


def _edit(data: bytes, old: str, new: str, count: int = 1) -> bytes:
    text = data.decode()
    assert old in text
    return text.replace(old, new, count).encode()


def test_verify_catches_an_amount_edited_after_building(debtor: Debtor, payments: list[Payment]) -> None:
    # The classic: someone changes one amount in the XML by hand and leaves the sums.
    tampered = _edit(build(debtor, payments, NOW), ">1250.00<", ">1350.00<")
    problems = verify(tampered).problems
    assert any("CtrlSum says 1250.30, the transactions add up to 1350.30" in p for p in problems)


def test_verify_catches_a_creditor_iban_edited_after_building(debtor: Debtor, payments: list[Payment]) -> None:
    tampered = _edit(build(debtor, payments, NOW), "GB82WEST12345698765432", "GB82WEST12345698765433")
    problems = verify(tampered).problems
    assert any("creditor IBAN GB82WEST12345698765433: check digits" in p for p in problems)


def test_verify_catches_a_duplicated_transaction(debtor: Debtor, payments: list[Payment]) -> None:
    data = build(debtor, payments, NOW).decode()
    start = data.index("<CdtTrfTxInf>")
    end = data.index("</CdtTrfTxInf>") + len("</CdtTrfTxInf>")
    doubled = (data[:end] + data[start:end] + data[end:]).encode()
    problems = verify(doubled).problems
    assert any("NbOfTxs says 4, the file contains 5" in p for p in problems)
    assert any("EndToEndId INV-1001 appears 2 times" in p for p in problems)


def test_verify_refuses_a_doctype_unread() -> None:
    evil = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>'
    assert verify(evil).problems == ["the file declares a DOCTYPE; a pain.001 has none, and it is refused unread"]


def test_verify_refuses_another_message_version() -> None:
    other = b'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"/>'
    assert "version 09 only" in verify(other).problems[0]


def test_verify_reports_schema_violations(debtor: Debtor, payments: list[Payment]) -> None:
    broken = _edit(build(debtor, payments, NOW), "<PmtMtd>TRF</PmtMtd>", "")  # required by the schema
    problems = verify(broken).problems
    assert problems and all(p.startswith("schema:") for p in problems)


def test_verify_enforces_sepa_rules_the_generic_schema_does_not(debtor: Debtor, payments: list[Payment]) -> None:
    # pain.001 serves every credit transfer, not just SEPA ones, so the ISO
    # schema allows a file with no charge bearer. The SEPA rulebook requires
    # SLEV, and a schema check alone would pass this file.
    without_charge_bearer = _edit(build(debtor, payments, NOW), "<ChrgBr>SLEV</ChrgBr>", "")
    root = etree.fromstring(without_charge_bearer, safe_parser())
    assert pain001_schema().validate(root)
    assert any(
        "charge bearer is missing, a SEPA credit transfer needs SLEV" in p
        for p in verify(without_charge_bearer).problems
    )
