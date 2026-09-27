"""The command line, end to end, on the files in examples/."""

import io
from pathlib import Path

import pytest

from sepapay.cli import main

EXAMPLES = Path(__file__).parent.parent / "examples"
NOW = "2026-09-27T10:00:00+00:00"


def build(tmp_path: Path, payments: str) -> tuple[int, Path]:
    out = tmp_path / "run.xml"
    code = main(["build", "--debtor", str(EXAMPLES / "debtor.toml"), "--payments", str(EXAMPLES / payments),
                 "--output", str(out), "--now", NOW])  # fmt: skip
    return code, out


def test_build_then_verify(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = build(tmp_path, "payments.csv")
    assert code == 0
    assert "3 payment(s), EUR 1820.15, executing 2026-10-01" in capsys.readouterr().out

    assert main(["verify", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "1820.15  EUR, 3 payment(s)" in printed
    assert "OK:" in printed


def test_a_run_with_mistakes_reports_all_of_them_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = build(tmp_path, "payments-with-mistakes.csv")
    assert code == 1
    assert not out.exists()
    printed = capsys.readouterr().out
    assert "row 2, iban: check digits don't match" in printed
    assert "row 3, amount:" in printed
    assert "row 4, name:" in printed and "can't be represented in the SEPA character set" in printed
    assert "3 error(s); nothing written." in printed


def test_verify_refuses_a_hand_edited_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, out = build(tmp_path, "payments.csv")
    out.write_bytes(out.read_bytes().replace(b">480.25<", b">4802.50<"))
    capsys.readouterr()
    assert main(["verify", str(out)]) == 1
    printed = capsys.readouterr().out
    assert "CtrlSum says 1820.15, the transactions add up to 6142.40" in printed
    assert "do not release this file" in printed


def test_missing_file_is_a_usage_error(tmp_path: Path) -> None:
    assert main(["verify", str(tmp_path / "nope.xml")]) == 2


def test_errors_quoting_non_latin_input_do_not_crash_a_cp1252_console(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The default Windows console encoding. Before the fix, printing the
    # error for a Japanese supplier name raised UnicodeEncodeError here.
    raw = io.BytesIO()
    console = io.TextIOWrapper(raw, encoding="cp1252")
    monkeypatch.setattr("sys.stdout", console)
    code, _ = build(tmp_path, "payments-with-mistakes.csv")
    console.flush()
    assert code == 1
    printed = raw.getvalue().decode("cp1252")
    assert "row 4, name:" in printed
    assert r"\u682a" in printed  # the character is escaped rather than crashing the console
    assert "3 error(s); nothing written." in printed
