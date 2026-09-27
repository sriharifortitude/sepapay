# ADR 1: refuse rather than guess

## Status
Accepted

## Context
Payment files are built from spreadsheets, and spreadsheets are
ambiguous. `1,000.50` is one thousand in English and one point zero zero
zero five in German. `Müller & Söhne` is a normal company name that a
bank's SEPA character set can't carry. A date typed as 2026-12-25 is a
valid date on which nothing settles. Every one of these has an "obvious"
fix a tool could apply silently, and each fix is right most of the time.

In payments, "most of the time" means the wrong amount leaves the account
some of the time. The errors a guess introduces are the expensive kind,
too: not a rejected file someone fixes on Monday, but a payment that
executes and has to be recovered from the recipient.

## Decision
When input is ambiguous, `build` reports it and writes nothing. It
collects every problem across the whole file in one pass, each with its
row, so refusing costs one round of edits, not one per mistake.

Refused rather than guessed:
- amounts with a thousands or comma decimal separator, or more than two
  decimals;
- characters with no representation in the SEPA basic Latin set, after a
  conversion that is fully specified and tested (accents removed, `ß` →
  `ss`, `&` → `+`);
- an execution date on a TARGET2 closing day. The next business day is
  named in the message, but not substituted;
- a CSV column the tool doesn't know, which is usually a misspelling of
  one it does;
- anything over a field's maximum length, measured *after* conversion,
  because `ß` → `ss` can push a name that fitted over the limit.

## Consequences
- Some runs that another tool would have accepted fail here first. That's
  the intent.
- The one lossy conversion the tool does perform (accents removed from
  names and references) is deterministic, documented and tested, and
  it's what banks do anyway. Doing it before the file is written means
  the approver sees the exact text the bank will receive.
- Warnings exist for things that are suspicious but legitimate: the same
  amount to the same IBAN with the same reference twice, or a payment to
  the debtor's own account. They're printed and don't block the file,
  because a genuine case of each exists.
