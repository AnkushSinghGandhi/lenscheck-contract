"""Read Django's own runtime state.

Static analysis cannot see routers, loops, or mixins. Django can - it already
resolved all of it at startup. So we ask it instead of parsing files.
"""

from __future__ import annotations

from typing import Any

from .models import Contract, Model, Route
from .registry import handler_name

AUTH_DECORATOR_FILES = ("django/contrib/auth/decorators.py",)


def probe(contract: Contract | None = None) -> Contract:
    contract = contract if contract is not None else Contract()
    _probe_models(contract)
    _probe_routes(contract)
    contract.recompute_coverage()
    return contract


# ---------------- models ----------------


def _probe_models(contract: Contract) -> None:
    from django.apps import apps

    for model in apps.get_models():
        meta = model._meta
        entry = Model(name=meta.label, table=meta.db_table)
        for f in meta.get_fields():
            if not getattr(f, "concrete", False) and not f.is_relation:
                continue
            info: dict[str, Any] = {"type": type(f).__name__}
            for attr in ("null", "unique", "blank", "primary_key"):
                val = getattr(f, attr, None)
                if val:
                    info[attr] = True
            max_length = getattr(f, "max_length", None)
            if max_length:
                info["max_length"] = max_length
            related = getattr(f, "related_model", None)
            if related is not None:
                info["relates_to"] = related._meta.label
            entry.fields[f.name] = info
        contract.models[entry.name] = entry


# ---------------- routes ----------------


def _probe_routes(contract: Contract) -> None:
    from django.urls import get_resolver

    _walk(get_resolver(), "", contract)


def _walk(resolver: Any, prefix: str, contract: Contract) -> None:
    from django.urls.resolvers import URLPattern, URLResolver

    try:
        patterns = resolver.url_patterns
    except Exception as exc:  # noqa: BLE001 - a broken include must not hide the rest
        contract.coverage.unresolved.append(f"{prefix or '/'} ({exc.__class__.__name__})")
        return

    for entry in patterns:
        piece = str(entry.pattern)
        if isinstance(entry, URLResolver):
            _walk(entry, prefix + piece, contract)
        elif isinstance(entry, URLPattern):
            _add_route(prefix + piece, entry.callback, contract)


def _add_route(path: str, callback: Any, contract: Contract) -> None:
    if callback is None:
        contract.coverage.unresolved.append(path)
        return

    handler = handler_name(callback)
    auth = _auth_of(callback)

    for method in _methods_of(callback):
        contract.add_route(
            Route(
                method=method,
                path="/" + path.lstrip("/"),
                handler=handler,
                auth=auth,
                source="runtime",
            )
        )


def _methods_of(callback: Any) -> list[str]:
    view_class = getattr(callback, "view_class", None) or getattr(callback, "cls", None)
    actions = getattr(callback, "actions", None)  # DRF viewset
    if isinstance(actions, dict) and actions:
        return sorted(m.upper() for m in actions)
    if view_class is not None:
        allowed = getattr(view_class, "http_method_names", [])
        found = [m.upper() for m in allowed if _defined_by_user(view_class, m)]
        if found:
            return sorted(found)
    return ["ANY"]


def _defined_by_user(view_class: Any, method: str) -> bool:
    """Django's base View supplies `options` for free. That is not a real route."""
    for klass in getattr(view_class, "__mro__", ()):
        if method in vars(klass):
            return not getattr(klass, "__module__", "").startswith("django.views")
    return False


def _auth_of(callback: Any) -> str:
    """Best-effort. Returns 'unknown' rather than guessing wrong."""
    view_class = getattr(callback, "view_class", None) or getattr(callback, "cls", None)

    perms = getattr(view_class, "permission_classes", None)
    if perms:
        names = sorted(p.__name__ for p in perms)
        return "public" if names == ["AllowAny"] else "+".join(names)
    if perms is not None:            # explicitly `permission_classes = []` → no checks → open
        return "public"

    if view_class is not None:
        mro = {c.__name__ for c in getattr(view_class, "__mro__", ())}
        marks = sorted(n for n in mro if n.endswith("RequiredMixin"))
        if marks:
            return "+".join(marks)

    fn: Any = callback
    seen = 0
    while fn is not None and seen < 10:
        code = getattr(fn, "__code__", None)
        filename = getattr(code, "co_filename", "")
        if any(m in filename.replace("\\", "/") for m in AUTH_DECORATOR_FILES):
            return "login_required"
        fn = getattr(fn, "__wrapped__", None)
        seen += 1

    return "unknown"
