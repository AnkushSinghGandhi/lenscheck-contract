"""pryti-contract — your backend keeps a list of what it does.

    from pryti_contract import contract

    @contract.route("POST /orders", auth="user")
    @contract.effects("net:api.stripe.com", "email")
    def create_order(request): ...

Then::

    pryti-contract export -o contract.json
    pryti-contract diff base.json head.json
"""

from __future__ import annotations

from .diff import Change, diff, render_markdown, render_text, worst
from .guard import UndeclaredEffect, guard
from .models import Contract, Coverage, Job, Model, Route
from .registry import handler_name, scope
from .registry import registry as contract

__version__ = "0.1.0"

__all__ = [
    "contract",
    "guard",
    "scope",
    "handler_name",
    "build",
    "diff",
    "render_text",
    "render_markdown",
    "worst",
    "Change",
    "Contract",
    "Coverage",
    "Route",
    "Model",
    "Job",
    "UndeclaredEffect",
    "__version__",
]


def build(include_django: bool = True) -> Contract:
    """The whole contract: what Django knows at runtime, plus what you declared.

    Order matters. Probing loads the URLConf, which imports your views, which is
    what makes the decorators run. Reading the registry first would find it empty.
    """
    result = Contract()
    if include_django:
        try:
            from django.apps import apps  # noqa: F401

            from .django_probe import probe

            probe(result)
        except Exception:  # noqa: BLE001 - Django is optional; declarations still work
            pass

    _merge_declarations(result, contract.build())
    result.recompute_coverage()
    return result


def _merge_declarations(runtime: Contract, declared: Contract) -> None:
    """A declaration is a claim about a handler. The router says where it lives."""
    by_handler: dict[str, list[str]] = {}
    for key, route in runtime.routes.items():
        by_handler.setdefault(route.handler, []).append(key)

    for d in declared.routes.values():
        keys = by_handler.get(d.handler, [])
        exact = [k for k in keys if runtime.routes[k].path == d.path]
        targets = exact or keys

        if not targets:
            # Declared but not mounted (yet). Keep it; a missing route is worth seeing.
            runtime.routes[d.key] = d
            continue

        paths = sorted({runtime.routes[k].path for k in targets})
        for k in targets:
            runtime.routes.pop(k, None)
        for path in paths:
            merged = Route(
                method=d.method,
                path=path,
                handler=d.handler,
                auth=d.auth,
                effects=sorted(d.effects),
                source="declared",
            )
            runtime.routes[merged.key] = merged

    for job in declared.jobs.values():
        runtime.jobs[job.name] = job
