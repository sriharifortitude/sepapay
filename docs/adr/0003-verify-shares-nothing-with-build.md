# ADR 3: `verify` shares nothing with `build`

## Status
Accepted

## Context
Releasing a payment run is normally a four-eyes step: one person prepares
it and another approves it. What the approver looks at matters. Checking
the spreadsheet proves nothing about the file, which could have been
built from an older version, edited by hand afterwards, or produced by a
tool with a bug. Checking the file with the same code that produced it
proves little more. A bug in how `build` computes a control sum would be
repeated by any check that reuses that computation.

## Decision
`verify` takes the bytes of a pain.001.001.09 file and nothing else. It
imports no builder code and reads no input files. It parses the XML
itself and recomputes everything from the transactions it finds:
`NbOfTxs` and `CtrlSum` per batch and overall, every IBAN and RF
checksum, duplicate EndToEndIds, and the SEPA-specific rules (service
level `SEPA`, charge bearer `SLEV`, currency `EUR`, execution date on a
TARGET2 business day).

It also:
- validates against the official ISO schema first, and stops if that
  fails, since the later checks assume the structure the schema
  guarantees;
- refuses a file containing a `DOCTYPE` without parsing it, since a
  payment file has no use for one and it's the entry point for XXE and
  entity-expansion attacks;
- prints a SHA-256 of the exact bytes, so an approval can refer to one
  specific file.

The low-level checks (IBAN mod 97, the TARGET2 calendar) are the same
functions `build` uses. They're small, checked against published
reference values, and not where a sum or a structure goes wrong.

## Consequences
- A hand edit that changes an amount without updating the sums is caught,
  as is a duplicated transaction and a mistyped IBAN. The tests plant
  each of these in a built file.
- It checks files from any generator, not just sepapay's, which is what
  makes it useful as an approval step in a company that already has a
  payment export.
- It says what the file instructs the bank to do. It can't know whether
  that's what the business meant to pay: the approver still compares the
  printed lines with the invoices.
