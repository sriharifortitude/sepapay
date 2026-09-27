# sepapay

[![CI](https://github.com/sriharifortitude/sepapay/actions/workflows/ci.yml/badge.svg)](https://github.com/sriharifortitude/sepapay/actions/workflows/ci.yml)

Turns a payment run (who pays, and a CSV of whom) into a SEPA Credit
Transfer file: ISO 20022 `pain.001.001.09`, the XML a European company
uploads to its bank to pay suppliers in bulk. A second command
independently re-checks a finished file before anyone releases it. Python
3.12, MIT.

In this portfolio it's the middle of one finance chain:
[ubl-billing](https://github.com/sriharifortitude/ubl-billing) issues
invoices, sepapay pays suppliers, and
[camtmatch](https://github.com/sriharifortitude/camtmatch) reconciles the
bank statement. An ISO 11649 `RF` reference given here travels structured
all the way through, and it's the first thing camtmatch matches on.

## Why a tool for a file format

The format is the easy part. The mistakes are what cost money: a supplier
IBAN with two digits swapped, `"1,000.50"` from a spreadsheet read as
1.0005 or 100050, a name in a character set a bank along the way mangles,
an execution date on Good Friday, the same run uploaded twice. The bank
finds most of these after the upload, one rejection at a time, or doesn't
find them at all.

<!-- mistakes:start -->
```
error: row 2, iban: check digits don't match: a character is mistyped or two are swapped
error: row 3, amount: '480,25' is not an amount: use digits with an optional '.' and at most two decimals, no thousands separators
error: row 4, name: 'サ' 'フ' 'ル' 'ン' '会' '式' '株' '社' can't be represented in the SEPA character set

3 error(s); nothing written.
```
<!-- mistakes:end -->

That's `sepapay build` on [`examples/payments-with-mistakes.csv`](examples/payments-with-mistakes.csv):
every problem, with its row, in one pass, and no file written. The same
run fixed ([`examples/payments.csv`](examples/payments.csv)):

<!-- build:start -->
```
wrote run.xml: 3 payment(s), EUR 1820.15, executing 2026-10-01
next: sepapay verify run.xml   (ideally run by whoever approves the payment run)
```
<!-- build:end -->

Then the person who approves the payment run checks the file itself:

<!-- verify:start -->
```
file      run.xml
sha256    087bf649e3f9b2d7ff0f69fc523dc9f4cb7984306b7281f6ce32a6e33a4e9d60
message   SEPAPAY-20261001-6347C36E506D
debtor    Muller + Sohne GmbH  DE89370400440532013000
executes  2026-10-01

         1250.00  Acme Ltd        GB82WEST12345698765432  RF18539007547034
          480.25  Buro Nord B.V.  NL91ABNA0417164300      Rechnung 2026-042
           89.90  Cafe Sud        BE68539007547034        Order 7731
  --------------
         1820.15  EUR, 3 payment(s)

OK: schema, counts, control sums, IBAN and reference checksums, dates all check out.
```
<!-- verify:end -->

These three blocks are the tool's real output, and CI re-runs the commands
and diffs them against this README (`scripts/check-readme.sh`).

## What `build` checks

- **IBAN checksums** (ISO 13616, mod 97): catches every single mistyped
  character and almost every swap of two adjacent ones. Also the country's
  IBAN length, and that the country is in the SEPA scheme.
- **Amounts as exact decimals** with a `.` and at most two places, from
  0.01 to the scheme maximum of 999,999,999.99. `1,000.50` and `1.000,50`
  are refused, not guessed at. Control sums are computed in `Decimal`:
  three payments of 0.10 total 0.30, which binary floating point doesn't.
- **The SEPA character set.** Accents are removed (é → e, ü → u, Ł → L),
  letters that don't decompose are spelled out (ß → ss, Æ → AE), and `&`
  becomes `+`. That last one is this tool's choice, not an EPC rule.
  Anything that still can't be represented is an error naming the
  character, never a silent `?`. Lengths are checked after conversion,
  because `ß` becomes two characters.
- **Execution date** on a TARGET2 business day: weekends, New Year,
  Good Friday, Easter Monday, 1 May and 25/26 December are refused with
  the next business day named. National holidays don't close TARGET2, so
  they're allowed.
- **RF creditor references** (ISO 11649) are checksum-checked and sent as
  structured remittance information. Anything else goes as free text.
- **Unique EndToEndIds**, plus a warning (not an error) when two rows pay
  the same amount to the same IBAN with the same reference, or when a row
  pays the debtor's own account.
- **An unknown CSV column is an error.** `ammount` would otherwise be
  silently ignored and `amount` reported missing.

Then the file is validated against the **official ISO 20022 XSD**, bundled
unmodified with its source URL and SHA-256 (`src/sepapay/schemas/SOURCE.md`;
a test checks the hash). A file the schema rejects is never written: that
would be a bug in sepapay, and it raises instead.

## What `verify` checks, and why it's separate

A payment run is usually prepared by one person and released by another.
The approver should check the file that will be uploaded, not the
spreadsheet and not the tool that produced it.
[ADR 3](docs/adr/0003-verify-shares-nothing-with-build.md) covers this.
`verify` re-parses the XML from scratch and recomputes:

- every count (`NbOfTxs`) and control sum (`CtrlSum`), per batch and in
  total. A hand-edited amount that leaves the sums alone is caught.
- every debtor and creditor IBAN checksum, and every RF reference
  checksum;
- duplicate EndToEndIds, including a duplicated transaction block;
- the SEPA rules the generic ISO schema doesn't enforce. pain.001 serves
  every kind of credit transfer, so the schema lets a file omit the
  charge bearer. A SEPA file needs `SLEV`, and a test proves a schema
  check alone would pass the file without it.

It refuses a file with a `DOCTYPE` without parsing it (XXE and entity
expansion have no place in a payment file), reads version 09 only, and
prints a SHA-256 of the exact bytes, so the approval can name the file
that was approved.

## The message ID prevents double payment

`MsgId` is derived from the run's content: debtor, date, and each
payment's IBAN, amount, EndToEndId and reference. Rebuilding the same run
gives the same MsgId, and banks reject a file whose MsgId they've already
processed, so an accidental second upload bounces instead of paying every
supplier twice. A genuinely different run always gets a new one.
[ADR 2](docs/adr/0002-message-id-from-content.md).

## Usage

```bash
pip install git+https://github.com/sriharifortitude/sepapay@v0.1.0

sepapay build --debtor debtor.toml --payments payments.csv --output run.xml
sepapay verify run.xml
```

`debtor.toml` holds `name`, `iban`, `execution_date` (a TOML date), and
optionally `bic` and `batch_booking` (default `true`). `payments.csv`
needs `name,iban,amount`, and optionally `bic`, `reference` and
`end_to_end_id`. Exit codes: `0` ok, `1` problems found (nothing written
by `build`), `2` a file couldn't be read.

## What it doesn't do

- **No bank connectivity.** It writes a file; uploading it (EBICS,
  online banking, an API) is outside its scope.
- **pain.001.001.09 only.** Some banks still want the older `.03`; this
  doesn't produce it.
- **Format checks, not account checks.** A valid IBAN checksum means the
  number is well formed, not that the account exists or belongs to that
  name. The EU's Verification of Payee, which does check the name, is a
  service the bank runs, not something a file can do.
- **The SEPA country list** is the long-standing 36-member scheme area
  (`iban.py`). Countries the EPC has admitted since are refused rather
  than assumed.
- **Not tested against a bank.** The files validate against the official
  ISO schema and the rules above. No bank's own ingestion has seen one,
  and individual banks add their own restrictions.

## Licence

[MIT](LICENSE).
