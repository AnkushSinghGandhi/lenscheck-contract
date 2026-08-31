"""Django middleware.

Without this, the guard only watches views you decorated - which is backwards.
The views you forgot to declare are exactly the ones worth watching.

    MIDDLEWARE = [
        "pryti_contract.middleware.ContractMiddleware",
        ...
    ]
"""

from __future__ import annotations

from typing import Any, Callable

from .registry import current_handler, handler_name


class ContractMiddleware:
    def __init__(self, get_response: Callable[..., Any]) -> None:
        self.get_response = get_response

    def __call__(self, request: Any) -> Any:
        token = current_handler.set(None)
        try:
            return self.get_response(request)
        finally:
            current_handler.reset(token)

    def process_view(
        self, request: Any, view_func: Any, view_args: Any, view_kwargs: Any
    ) -> None:
        current_handler.set(handler_name(view_func))
        return None
