"""FastAPI / Starlette ASGI middleware — the guard's "watch everything" layer for FastAPI.

Without this, the guard only knows which handler is running for endpoints you decorated. This sets
the current handler for *every* request, so an undeclared endpoint is watched too.

    from lenscheck_contract import install_fastapi, guard

    install_fastapi(app)
    guard.install(mode="error")   # off | record | warn | error

We match the route ourselves and set the handler in the ASGI call, *before* delegating to the app —
a plain ASGI middleware (not Starlette's BaseHTTPMiddleware), so the contextvar propagates into the
endpoint (sync endpoints run in a threadpool that copies the context; async endpoints share it).
"""

from __future__ import annotations

from typing import Any, Callable

from .registry import current_handler, handler_name


def install_fastapi(app: Any) -> Any:
    """Add the contract ASGI middleware to a FastAPI/Starlette app. Returns the app."""
    app.add_middleware(_ContractASGIMiddleware, get_routes=lambda: app.routes)
    return app


class _ContractASGIMiddleware:
    def __init__(self, app: Any, get_routes: Callable[[], Any]) -> None:
        self.app = app                # the next ASGI layer
        self.get_routes = get_routes  # deferred: the route table is complete by request time

    async def __call__(self, scope: Any, receive: Any, send: Any) -> Any:
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        token = current_handler.set(_handler_for(self.get_routes(), scope))
        try:
            return await self.app(scope, receive, send)
        finally:
            current_handler.reset(token)


def _handler_for(routes: Any, scope: Any) -> str | None:
    try:
        from starlette.routing import Match
    except Exception:  # noqa: BLE001 - Starlette absent
        return None
    for route in routes:
        matches = getattr(route, "matches", None)
        if matches is None:
            continue
        match, _child = matches(scope)
        if match == Match.FULL:
            endpoint = getattr(route, "endpoint", None)
            return handler_name(endpoint) if endpoint is not None else None
    return None
