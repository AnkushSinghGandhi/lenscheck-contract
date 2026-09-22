"""Read a Flask app's own runtime state.

Flask resolves every route into its `url_map` at import time, so we ask the framework
instead of parsing files. Pass the app instance (Flask has no global registry):

    from lenscheck_contract import build
    contract = build(flask_app=app)

Models come from SQLAlchemy via `sqla_probe` (Flask-SQLAlchemy models are ordinary SQLAlchemy
mapped classes, so they're picked up too).
"""

from __future__ import annotations

from typing import Any

from .models import Contract, Route
from .registry import handler_name
from .sqla_probe import probe_models

# Auth decorators live in these packages; we read the wrapper's source file, which
# functools.wraps does NOT rewrite (unlike __module__), so it still points at the decorator.
_AUTH_FILES = {
    "flask_login": "login_required",
    "flask_security": "auth_required",
    "flask_jwt_extended": "jwt_required",
    "flask_httpauth": "login_required",
}
_AUTO_METHODS = {"HEAD", "OPTIONS"}


def probe(app: Any, contract: Contract | None = None) -> Contract:
    contract = contract if contract is not None else Contract()
    probe_models(contract)
    _probe_routes(app, contract)
    contract.recompute_coverage()
    return contract


def _probe_routes(app: Any, contract: Contract) -> None:
    url_map = getattr(app, "url_map", None)
    view_functions = getattr(app, "view_functions", {})
    if url_map is None:
        return

    for rule in url_map.iter_rules():
        if rule.endpoint == "static":
            continue  # Flask's built-in static route, not the app's contract
        view = view_functions.get(rule.endpoint)
        if view is None:
            contract.coverage.unresolved.append(str(rule))
            continue
        handler = handler_name(view)
        auth = _auth_of(view)
        for method in _methods_of(rule):
            contract.add_route(
                Route(method=method, path=str(rule), handler=handler, auth=auth, source="runtime")
            )


def _methods_of(rule: Any) -> list[str]:
    methods = {m.upper() for m in (rule.methods or [])} - _AUTO_METHODS
    return sorted(methods) or ["ANY"]


def _auth_of(view: Any) -> str:
    """Best-effort: follow the wrapper chain and name a known auth decorator. Else 'unknown'."""
    fn: Any = view
    seen = 0
    while fn is not None and seen < 12:
        code = getattr(fn, "__code__", None)
        filename = getattr(code, "co_filename", "").replace("\\", "/")
        for pkg, label in _AUTH_FILES.items():
            if f"/{pkg}/" in filename:
                return label
        fn = getattr(fn, "__wrapped__", None)
        seen += 1
    return "unknown"
