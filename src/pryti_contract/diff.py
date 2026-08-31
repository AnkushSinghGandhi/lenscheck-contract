"""Diff two contracts. This is the output a human actually reads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import Contract

WEAK_AUTH = {"unknown", "none", "any", "allowany", "public"}

RISKY = "risky"
REVIEW = "review"
INFO = "info"

_ORDER = {RISKY: 0, REVIEW: 1, INFO: 2}


@dataclass
class Change:
    severity: str
    kind: str
    subject: str
    detail: str

    def line(self) -> str:
        return f"{self.subject}  {self.detail}"


def _is_weak(auth: str) -> bool:
    return auth.strip().lower() in WEAK_AUTH


def diff(base: Contract, head: Contract) -> list[Change]:
    changes: list[Change] = []
    _diff_routes(base, head, changes)
    _diff_models(base, head, changes)
    _diff_jobs(base, head, changes)
    _diff_coverage(base, head, changes)
    changes.sort(key=lambda c: (_ORDER[c.severity], c.subject))
    return changes


def _diff_routes(base: Contract, head: Contract, out: list[Change]) -> None:
    for key in sorted(set(head.routes) - set(base.routes)):
        r = head.routes[key]
        sev = RISKY if _is_weak(r.auth) else INFO
        out.append(Change(sev, "route_added", key, f"new route, auth: {r.auth}"))

    for key in sorted(set(base.routes) - set(head.routes)):
        out.append(Change(REVIEW, "route_removed", key, "route removed"))

    for key in sorted(set(base.routes) & set(head.routes)):
        b, h = base.routes[key], head.routes[key]
        if b.auth != h.auth:
            weakened = not _is_weak(b.auth) and _is_weak(h.auth)
            out.append(
                Change(
                    RISKY if weakened else REVIEW,
                    "auth_weakened" if weakened else "auth_changed",
                    key,
                    f"auth: {b.auth} -> {h.auth}",
                )
            )
        added = sorted(set(h.effects) - set(b.effects))
        removed = sorted(set(b.effects) - set(h.effects))
        for e in added:
            out.append(Change(RISKY, "effect_added", key, f"new effect: {e}"))
        for e in removed:
            out.append(Change(INFO, "effect_removed", key, f"effect gone: {e}"))
        if b.handler != h.handler:
            out.append(
                Change(REVIEW, "handler_changed", key, f"handler: {b.handler} -> {h.handler}")
            )


def _diff_models(base: Contract, head: Contract, out: list[Change]) -> None:
    for name in sorted(set(head.models) - set(base.models)):
        out.append(Change(INFO, "model_added", name, "new model"))
    for name in sorted(set(base.models) - set(head.models)):
        out.append(Change(RISKY, "model_removed", name, "model removed"))

    for name in sorted(set(base.models) & set(head.models)):
        bf, hf = base.models[name].fields, head.models[name].fields
        for f in sorted(set(hf) - set(bf)):
            out.append(Change(INFO, "field_added", f"{name}.{f}", f"new field ({hf[f].get('type')})"))
        for f in sorted(set(bf) - set(hf)):
            out.append(Change(RISKY, "field_removed", f"{name}.{f}", "field removed (data loss)"))
        for f in sorted(set(bf) & set(hf)):
            for change in _field_changes(bf[f], hf[f]):
                sev, detail = change
                out.append(Change(sev, "field_changed", f"{name}.{f}", detail))


def _field_changes(b: dict[str, Any], h: dict[str, Any]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    if b.get("type") != h.get("type"):
        result.append((RISKY, f"type: {b.get('type')} -> {h.get('type')}"))
    for attr, risky_when in (("unique", False), ("null", True), ("primary_key", False)):
        before, after = bool(b.get(attr)), bool(h.get(attr))
        if before != after:
            sev = RISKY if after is risky_when else REVIEW
            result.append((sev, f"{attr}: {before} -> {after}"))
    if b.get("relates_to") != h.get("relates_to"):
        result.append((RISKY, f"relation: {b.get('relates_to')} -> {h.get('relates_to')}"))
    if b.get("max_length") != h.get("max_length"):
        shrunk = (h.get("max_length") or 0) < (b.get("max_length") or 0)
        result.append(
            (RISKY if shrunk else INFO, f"max_length: {b.get('max_length')} -> {h.get('max_length')}")
        )
    return result


def _diff_jobs(base: Contract, head: Contract, out: list[Change]) -> None:
    for name in sorted(set(head.jobs) - set(base.jobs)):
        out.append(Change(REVIEW, "job_added", name, "new background job"))
    for name in sorted(set(base.jobs) - set(head.jobs)):
        out.append(Change(REVIEW, "job_removed", name, "job removed"))
    for name in sorted(set(base.jobs) & set(head.jobs)):
        b, h = base.jobs[name], head.jobs[name]
        if b.schedule != h.schedule:
            out.append(Change(REVIEW, "job_rescheduled", name, f"{b.schedule} -> {h.schedule}"))
        for e in sorted(set(h.effects) - set(b.effects)):
            out.append(Change(RISKY, "effect_added", name, f"new effect: {e}"))


def _diff_coverage(base: Contract, head: Contract, out: list[Change]) -> None:
    b, h = base.coverage, head.coverage
    if h.routes_total and b.routes_total:
        before = b.routes_with_auth / b.routes_total
        after = h.routes_with_auth / h.routes_total
        if after < before - 0.01:
            out.append(
                Change(
                    REVIEW,
                    "coverage_dropped",
                    "coverage",
                    f"auth known on {after:.0%} of routes (was {before:.0%})",
                )
            )
    new_unresolved = len(h.unresolved) - len(b.unresolved)
    if new_unresolved > 0:
        out.append(
            Change(REVIEW, "unresolved", "coverage", f"{new_unresolved} more routes unresolved")
        )


# ---------------- rendering ----------------


def render_text(changes: list[Change]) -> str:
    if not changes:
        return "No contract changes."
    lines = []
    for sev in (RISKY, REVIEW, INFO):
        group = [c for c in changes if c.severity == sev]
        if not group:
            continue
        lines.append(f"{sev.upper()} ({len(group)})")
        lines.extend("  " + c.line() for c in group)
        lines.append("")
    return "\n".join(lines).rstrip()


def render_markdown(changes: list[Change]) -> str:
    if not changes:
        return "**Backend contract:** no changes."
    icons = {RISKY: "🔴", REVIEW: "🟡", INFO: "⚪"}
    out = ["### Backend contract changes", ""]
    for c in changes:
        out.append(f"- {icons[c.severity]} `{c.subject}` — {c.detail}")
    risky = sum(1 for c in changes if c.severity == RISKY)
    out.append("")
    out.append(f"_{risky} risky, {len(changes)} total._")
    return "\n".join(out)


def worst(changes: list[Change]) -> str:
    for sev in (RISKY, REVIEW, INFO):
        if any(c.severity == sev for c in changes):
            return sev
    return INFO
