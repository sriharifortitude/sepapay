# ADR 2: the message ID is derived from the run's content

## Status
Accepted

## Context
Every pain.001 carries a `MsgId`, and banks use it for duplicate
detection: a second file with a `MsgId` they've already processed is
rejected. Most generators fill it with a timestamp or a random UUID, so
every export gets a new one.

That defeats the bank's check exactly when it matters. Someone exports
the run, the upload seems to fail, they export and upload again. Both
files have fresh IDs, the bank accepts both, and every supplier on the
run is paid twice.

## Decision
`MsgId` is `SEPAPAY-<execution date>-<12 hex characters>`, the hex being
the start of a SHA-256 over the debtor IBAN, the execution date, and each
payment's IBAN, amount, EndToEndId and reference, in file order. The
payment information ID is the same with `-1` appended.

The creation timestamp (`CreDtTm`) is not part of the hash, so rebuilding
the same run gives a different file (a new timestamp) with the same
`MsgId`.

## Consequences
- Uploading the same run twice, whether rebuilt or not, is rejected by any
  bank that checks `MsgId` uniqueness, which is the scheme's own
  safeguard. sepapay doesn't have to remember anything to make it work.
- Changing anything that affects what gets paid (an amount, an IBAN, a
  payment added or removed, the date) produces a new ID, so a corrected
  run is never mistaken for a duplicate.
- **A deliberate repeat of an identical run is refused too.** If a
  business really does pay the same suppliers the same amounts on the
  same date twice, the second run needs different EndToEndIds, which it
  should have anyway.
- 48 bits of hash per execution date: accidental collisions between
  genuinely different runs on the same date aren't a practical concern.
  The ID only has to be unique per debtor at their bank, not globally.
- `sepapay verify` doesn't check this derivation. A file from any other
  tool, with any `MsgId`, is verified the same way.
