"""The registry. Decorators write into it at import time; nothing is parsed."""

from __future__ import annotations

import contextvars
import functools
from typing import Any, Callable

from .models import Contract, Job, Route

# Which handler is running right now. The guard reads this.
current_handler: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "pryti_current_handler", default=None
)


def _qualname(fn: Callable[..., Any]) -> str:
    mod = getattr(fn, "__module__", "?")
    name = getattr(fn, "__qualname__", getattr(fn, "__name__", "?"))
    return f"{mod}.{name}"


def _split_spec(spec: str) -> tuple[str, str]:
    """'POST /orders' -> ('POST', '/orders'). Bare '/orders' -> ('GET', '/orders')."""
    parts = spec.strip().split(None, 1)
    if len(parts) == 2 and parts[0].isalpha() and parts[0].isupper():
        return parts[0], parts[1]
    return "GET", spec.strip()


class Registry:
    def __init__(self) -> None:
        self.routes: dict[str, Route] = {}
        self.jobs: dict[str, Job] = {}
        self._declared: dict[str, list[str]] = {}

    def reset(self) -> None:
        self.routes.clear()
        self.jobs.clear()
        self._declared.clear()

    # ---------- decorators ----------

    def route(self, spec: str, auth: str = "unknown") -> Callable[..., Any]:
        """@contract.route("POST /orders", auth="user")"""
        method, path = _split_spec(spec)

        def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
            handler = _handler_of(fn)
            r = Route(
                method=method,
                path=path,
                handler=handler,
                auth=auth,
                effects=sorted(self._declared.get(handler, [])),
                source="declared",
            )
            self.routes[r.key] = r
            return self._instrument(fn, handler)

        return decorate

    def effects(self, *patterns: str) -> Callable[..., Any]:
        """@contract.effects("net:api.stripe.com", "email")"""

        def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
            handler = _handler_of(fn)
            declared = self._declared.setdefault(handler, [])
            for p in patterns:
                if p not in declared:
                    declared.append(p)
            for r in self.routes.values():
                if r.handler == handler:
                    r.effects = sorted(set(r.effects) | set(patterns))
            for j in self.jobs.values():
                if j.handler == handler:
                    j.effects = sorted(set(j.effects) | set(patterns))
            return self._instrument(fn, handler)

        return decorate

    def job(self, name: str, schedule: str | None = None) -> Callable[..., Any]:
        """@contract.job("nightly-invoices", schedule="0 2 * * *")"""

        def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
            handler = _handler_of(fn)
            self.jobs[name] = Job(
                name=name,
                handler=handler,
                schedule=schedule,
                effects=sorted(self._declared.get(handler, [])),
                source="declared",
            )
            return self._instrument(fn, handler)

        return decorate

    # ---------- plumbing ----------

    def _instrument(self, fn: Callable[..., Any], handler: str) -> Callable[..., Any]:
        """Set the contextvar while the handler runs. Applied at most once."""
        if getattr(fn, "__pryti_handler__", None) is not None:
            return fn

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            token = current_handler.set(handler)
            try:
                return fn(*args, **kwargs)
            finally:
                current_handler.reset(token)

        wrapper.__pryti_handler__ = handler  # type: ignore[attr-defined]
        return wrapper

    def declared_effects(self, handler: str | None) -> list[str]:
        if handler is None:
            return []
        return list(self._declared.get(handler, []))

    def build(self) -> Contract:
        c = Contract()
        for r in self.routes.values():
            c.add_route(r)
        for j in self.jobs.values():
            c.jobs[j.name] = j
        c.recompute_coverage()
        return c


def handler_name(target: Any) -> str:
    """One naming rule, shared by the decorators, the probe and the middleware.

    If these three ever disagree, the guard silently stops working.
    """
    existing = getattr(target, "__pryti_handler__", None)
    if existing:
        return str(existing)
    view_class = getattr(target, "view_class", None) or getattr(target, "cls", None)
    return _qualname(view_class or target)


def scope(name: str) -> Any:
    """Run a block as if it were handler `name`. For jobs, scripts and tests."""
    import contextlib

    @contextlib.contextmanager
    def _scope():
        token = current_handler.set(name)
        try:
            yield
        finally:
            current_handler.reset(token)

    return _scope()


def _handler_of(fn: Callable[..., Any]) -> str:
    """Stacked decorators wrap each other; keep one identity for the same function."""
    existing = getattr(fn, "__pryti_handler__", None)
    if existing:
        return str(existing)
    return _qualname(fn)


registry = Registry()
