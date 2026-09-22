"""Read a FastAPI app's own runtime state.

FastAPI resolves every route and its dependency tree at import time, so — like Django — we
ask the framework instead of parsing files. Pass the app instance (FastAPI has no global
registry the way Django does):

    from lenscheck_contract import build
    contract = build(fastapi_app=app)

Models come from SQLAlchemy via `sqla_probe` (the common ORM for FastAPI backends).
"""

from __future__ import annotations

from typing import Any

from .models import Contract, Route
from .pydantic_probe import probe_models as probe_pydantic_models
from .registry import handler_name
from .sqla_probe import probe_models
from .tortoise_probe import probe_models as probe_tortoise_models

# A dependency callable whose name looks like this is treated as an auth check.
_AUTH_HINTS = ("auth", "current_user", "current-user", "get_user", "login",
               "token", "permission", "scope", "require")
# Methods FastAPI/Starlette add for free — not routes a user declared.
_AUTO_METHODS = {"HEAD", "OPTIONS"}


def probe(app: Any, contract: Contract | None = None) -> Contract:
    contract = contract if contract is not None else Contract()
    probe_models(contract)                                   # SQLAlchemy tables (the DB layer)
    probe_tortoise_models(contract)                          # Tortoise ORM models (async DB layer)
    probe_pydantic_models(getattr(app, "routes", []), contract)  # Pydantic request/response schemas
    _probe_routes(app, contract)
    contract.recompute_coverage()
    return contract


def _probe_routes(app: Any, contract: Contract) -> None:
    try:
        from fastapi.routing import APIRoute
    except Exception:  # noqa: BLE001 - FastAPI is optional
        return

    for route in getattr(app, "routes", []):
        if not isinstance(route, APIRoute):
            continue  # Mounts, static files, websockets — no HTTP method contract
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            contract.coverage.unresolved.append(str(getattr(route, "path", "?")))
            continue
        handler = handler_name(endpoint)
        auth = _auth_of(route)
        for method in _methods_of(route):
            contract.add_route(
                Route(method=method, path=route.path, handler=handler, auth=auth, source="runtime")
            )


def _methods_of(route: Any) -> list[str]:
    methods = {m.upper() for m in (getattr(route, "methods", None) or [])} - _AUTO_METHODS
    return sorted(methods) or ["ANY"]


def _auth_of(route: Any) -> str:
    """Best-effort from the dependency tree. Security schemes win; then auth-ish deps; else honest."""
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return "unknown"

    schemes, calls, total = _collect(dependant)
    if schemes:
        return "+".join(sorted(set(schemes)))
    hits = [c for c in calls if any(h in c.lower() for h in _AUTH_HINTS)]
    if hits:
        return "+".join(sorted(set(hits)))
    if total == 0:
        return "public"          # no dependencies guard it at all
    return "unknown"             # has dependencies, but none we can read as auth


def _collect(dependant: Any) -> tuple[list[str], list[str], int]:
    """Walk the dependency tree. Returns (security-scheme names, dep callable names, dep count)."""
    try:
        from fastapi.security.base import SecurityBase
    except Exception:  # noqa: BLE001
        SecurityBase = ()  # type: ignore[assignment]

    schemes: list[str] = []
    calls: list[str] = []
    total = 0
    for dep in getattr(dependant, "dependencies", []) or []:
        total += 1
        call = getattr(dep, "call", None)
        if SecurityBase and isinstance(call, SecurityBase):
            schemes.append(getattr(call, "scheme_name", None) or type(call).__name__)
        elif call is not None:
            calls.append(getattr(call, "__name__", type(call).__name__))
        sub_s, sub_c, sub_t = _collect(dep)
        schemes += sub_s
        calls += sub_c
        total += sub_t
    return schemes, calls, total
