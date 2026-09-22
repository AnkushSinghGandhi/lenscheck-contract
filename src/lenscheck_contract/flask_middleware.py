"""Flask request hook — the guard's "watch everything" layer for Flask.

Without this, the guard only knows which handler is running for views you decorated. This sets
the current handler for *every* request, so an undeclared view is watched too — which is the whole
point (the views you forgot to declare are the ones worth watching).

    from lenscheck_contract import install_flask, guard

    install_flask(app)
    guard.install(mode="error")   # off | record | warn | error
"""

from __future__ import annotations

from typing import Any

from .registry import current_handler, handler_name


def install_flask(app: Any) -> Any:
    """Register before/teardown request hooks that scope the current handler. Returns the app."""
    from flask import g, request

    @app.before_request
    def _lenscheck_set() -> None:
        view = app.view_functions.get(request.endpoint) if request.endpoint else None
        g._lenscheck_token = current_handler.set(handler_name(view) if view else None)

    @app.teardown_request
    def _lenscheck_reset(_exc: BaseException | None = None) -> None:
        token = g.pop("_lenscheck_token", None)
        if token is not None:
            current_handler.reset(token)

    return app
