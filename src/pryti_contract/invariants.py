"""Bridge to pryti-semantic-reviewer.

The reviewer *discovers* invariants by guessing from git history, then a human
confirms them into a JSON it enforces on every PR (`--invariants`). This hands it
the truth instead: your app's real, declared egress destinations become the
approved allowlist, and the auth/PII rules the contract is built around are
confirmed. Feed the output straight into the reviewer:

    pryti-contract invariants --settings app.settings -o invariants.json
    # then, in the reviewer step:
    #   pryti-semantic-reviewer ... --invariants invariants.json

Output is the exact corpus shape the reviewer's enforce() reads: a list of
`{"id", "statement", "severity", "confirmed", ...}` entries.
"""

from __future__ import annotations

from typing import Any

from .models import Contract

_LOCAL = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "::"}


def _declared_destinations(contract: Contract) -> list[str]:
    """Every `net:` destination the app declares, across routes and jobs."""
    dests: set[str] = set()
    carriers: list[Any] = list(contract.routes.values()) + list(contract.jobs.values())
    for c in carriers:
        for eff in getattr(c, "effects", None) or []:
            if eff.startswith("net:"):
                host = eff[4:].strip()
                if host and host not in _LOCAL:
                    dests.add(host)
    return sorted(dests)


def to_invariant_corpus(contract: Contract) -> list[dict[str, Any]]:
    """Contract -> the confirmed-invariant corpus the reviewer enforces on a PR."""
    dests = _declared_destinations(contract)
    src = "pryti-contract runtime export"
    return [
        {
            "id": "external-egress-allowlist",
            "statement": f"External egress limited to {len(dests)} declared destination(s)",
            "kind": "allowlist",
            "severity": "critical",
            "scope": "global",
            "observed": {"destinations": dests},
            "baseline_exceptions": [],
            "confirmed": True,
            "owner": src,
        },
        {
            "id": "auth-before-write",
            "statement": "Authenticated access before any DB write",
            "kind": "rule",
            "severity": "critical",
            "scope": "global",
            "baseline_exceptions": [],
            "confirmed": True,
            "owner": src,
        },
        {
            "id": "pii-egress-authed",
            "statement": "PII read + egress only on authenticated endpoints",
            "kind": "rule",
            "severity": "critical",
            "scope": "global",
            "baseline_exceptions": [],
            "confirmed": True,
            "owner": src,
        },
    ]
