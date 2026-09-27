#!/usr/bin/env bash
# Re-runs the three commands shown in the README and diffs their output
# against the README's blocks, byte for byte (the build is deterministic
# given --now, so even the SHA-256 line is stable).
set -euo pipefail
cd "$(dirname "$0")/../examples"
readme=../README.md
trap 'rm -f run.xml' EXIT

block() {  # the fenced block between <!-- name:start --> and <!-- name:end -->
  awk -v s="<!-- $1:start -->" -v e="<!-- $1:end -->" '$0==s{f=1;next} $0==e{f=0} f' "$readme" | sed '1d;$d'
}

check() {  # name, expected exit code, command...
  local name=$1 want=$2; shift 2
  set +e; actual=$("$@"); code=$?; set -e
  actual=${actual//$'\r'/}  # Windows consoles end lines with CRLF; the README uses LF
  if [ "$code" -ne "$want" ]; then echo "$name: exit $code, expected $want" >&2; exit 1; fi
  diff <(block "$name") <(printf '%s\n' "$actual") || { echo "README block '$name' is out of date" >&2; exit 1; }
  echo "$name: matches"
}

now=2026-09-27T10:00:00+00:00
check mistakes 1 sepapay build --debtor debtor.toml --payments payments-with-mistakes.csv --output run.xml --now "$now"
check build 0 sepapay build --debtor debtor.toml --payments payments.csv --output run.xml --now "$now"
check verify 0 sepapay verify run.xml
