#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  3 bad things, 0 get through.  (FastAPI)
#
#  One AI-written PR — "add order analytics" — sneaks in three dangerous changes:
#     #1  POST /orders   auth: user  ->  public       (Depends(current_user) removed)
#     #2  Customer.email field deleted                 (silent data loss)
#     #3  a call to analytics.tracksy.io               (never declared — exfil)
#
#  lenscheck-contract catches all three: two structurally in CI, one at runtime.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
PY="${PYTHON:-python3}"
export PYTHONPATH="$HERE/../../src"

b=$'\033[1m'; dim=$'\033[2m'; cyan=$'\033[36m'; r=$'\033[0m'

echo
echo "${b}▌ PR #128  ·  \"add order analytics\"  ·  +4 −2${r}   ${dim}looks harmless${r}"
echo

# ── export both contracts — a fresh process each, exactly like CI base vs head ──
$PY -m lenscheck_contract.cli export --no-django --root before --app app:app -o /tmp/fa_base.json >/dev/null 2>&1
$PY -m lenscheck_contract.cli export --no-django --root after  --app app:app -o /tmp/fa_head.json >/dev/null 2>&1

echo "${cyan}── Layer 2 · ${b}lenscheck-contract diff${r}${cyan}  (structural — runs in CI) ──${r}"
echo
$PY -m lenscheck_contract.cli diff /tmp/fa_base.json /tmp/fa_head.json --markdown --fail-on risky
code=$?
echo
echo "   ${dim}exit $code → ${r}${b}CI blocked${r}  ${dim}(#1 auth + #2 field caught before merge)${r}"
echo

echo "${cyan}── Layer 3 · ${b}lenscheck-contract guard${r}${cyan}  (runtime — in the running app) ──${r}"
echo
$PY guard_demo.py
echo
echo "${b}▌ 3 bad things in. 0 shipped.${r}"
echo
