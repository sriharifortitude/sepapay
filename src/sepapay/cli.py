"""Command-line entry point.

sepapay build --debtor debtor.toml --payments payments.csv --output run.xml
sepapay verify run.xml
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import sys
from decimal import Decimal
from pathlib import Path

from sepapay import batch
from sepapay.builder import build
from sepapay.money import format_amount
from sepapay.verify import verify

EXIT_OK, EXIT_PROBLEMS, EXIT_USAGE = 0, 1, 2


def main(argv: list[str] | None = None) -> int:
    # Error messages quote the input that caused them, and a supplier name
    # can hold any script. A Windows console defaults to cp1252, where
    # printing "株" raised UnicodeEncodeError mid-report. Escape what the
    # console can't show instead of crashing.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")

    parser = argparse.ArgumentParser(
        prog="sepapay", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)

    b = commands.add_parser("build", help="validate a payment run and write a pain.001.001.09 file")
    b.add_argument("--debtor", type=Path, required=True, help="TOML: name, iban, bic (optional), execution_date")
    b.add_argument(
        "--payments",
        type=Path,
        required=True,
        help="CSV: name, iban, amount, and optionally bic, reference, end_to_end_id",
    )
    b.add_argument("--output", type=Path, required=True)
    b.add_argument(
        "--now",
        type=dt.datetime.fromisoformat,
        help="creation timestamp (ISO 8601 with offset), for reproducible output",
    )

    v = commands.add_parser("verify", help="independently re-check a pain.001.001.09 file before releasing it")
    v.add_argument("file", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            return _build(args.debtor, args.payments, args.output, args.now)
        return _verify(args.file)
    except OSError as exc:
        print(f"sepapay: {exc}", file=sys.stderr)
        return EXIT_USAGE


def _build(debtor_path: Path, payments_path: Path, output: Path, now: dt.datetime | None) -> int:
    created_at = now or dt.datetime.now(dt.UTC)
    if created_at.tzinfo is None:
        print("sepapay: --now needs a UTC offset, e.g. 2026-09-27T10:00:00+00:00", file=sys.stderr)
        return EXIT_USAGE

    debtor, debtor_errors = batch.load_debtor(debtor_path.read_text(encoding="utf-8"), created_at.date())
    payments, problems = batch.load_payments(payments_path.read_text(encoding="utf-8-sig"))
    problems.errors[:0] = debtor_errors
    if debtor is not None:
        batch.check_against_debtor(debtor, payments, problems)

    for warning in problems.warnings:
        print(f"warning: {warning}")
    if problems.errors or debtor is None:
        for error in problems.errors:
            print(f"error: {error}")
        print(f"\n{len(problems.errors)} error(s); nothing written.")
        return EXIT_PROBLEMS

    output.write_bytes(build(debtor, payments, created_at))
    total = format_amount(sum((p.amount for p in payments), Decimal(0)))
    print(f"wrote {output}: {len(payments)} payment(s), EUR {total}, executing {debtor.execution_date}")
    print(f"next: sepapay verify {output}   (ideally run by whoever approves the payment run)")
    return EXIT_OK


def _verify(path: Path) -> int:
    report = verify(path.read_bytes())
    print(f"file      {path}")
    print(f"sha256    {report.sha256}")
    if report.message_id:
        print(f"message   {report.message_id}")
        print(f"debtor    {report.debtor}  {report.debtor_iban}")
        print(f"executes  {', '.join(report.execution_dates)}")
        print()
        width = max((len(line.creditor) for line in report.lines), default=0)
        iban_width = max((len(line.iban) for line in report.lines), default=0)
        for line in report.lines:
            print(
                f"  {format_amount(line.amount):>14}  {line.creditor:<{width}}  "
                f"{line.iban:<{iban_width}}  {line.reference}"
            )
        print(f"  {'-' * 14}")
        print(f"  {format_amount(report.total):>14}  EUR, {len(report.lines)} payment(s)")
    print()
    if report.ok:
        print("OK: schema, counts, control sums, IBAN and reference checksums, dates all check out.")
        return EXIT_OK
    for problem in report.problems:
        print(f"problem: {problem}")
    print(f"\n{len(report.problems)} problem(s): do not release this file.")
    return EXIT_PROBLEMS


if __name__ == "__main__":
    sys.exit(main())
