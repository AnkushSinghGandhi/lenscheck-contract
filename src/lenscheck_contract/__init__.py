"""lenscheck-contract — your backend keeps a list of what it does.

    from lenscheck_contract import contract

    @contract.route("POST /orders", auth="user")
    @contract.effects("net:api.stripe.com", "email")
    def create_order(request): ...

Then::

    lenscheck-contract export -o contract.json
    lenscheck-contract diff base.json head.json
"""

from __future__ import annotations

from .diff import Change, diff, render_markdown, render_text, worst
from .guard import UndeclaredEffect, guard
from .models import Contract, Coverage, Job, Model, Route
from .registry import handler_name, scope
from .registry import registry as contract

__version__ = "1.2.0"

__all__ = [
    "contract",
    "guard",
    "scope",
    "handler_name",
    "install_flask",
    "install_fastapi",
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


def build(
    include_django: bool = True,
    flask_app: object | None = None,
    fastapi_app: object | None = None,
    celery_app: object | None = None,
    include_celery: bool = True,
) -> Contract:
    """The whole contract: what the framework knows at runtime, plus what you declared.

    Django auto-discovers (it has a global app/URL registry), so it runs whenever it's
    configured. Flask and FastAPI have no such registry — pass the app instance:

        build(flask_app=app)      #  or
        build(fastapi_app=app)

    Celery background jobs are discovered from `celery_app` (or Celery's current_app) whenever
    Celery is installed and has tasks registered; pass `include_celery=False` to skip.

    Order matters. Probing loads the routes, which imports your views, which is what makes
    the decorators run. Reading the registry first would find it empty.
    """
    result = Contract()
    if include_django:
        try:
            from django.apps import apps  # noqa: F401

            from .django_probe import probe

            probe(result)
        except Exception:  # noqa: BLE001 - Django is optional; declarations still work
            pass

    if flask_app is not None:
        from .flask_probe import probe as flask_probe

        flask_probe(flask_app, result)

    if fastapi_app is not None:
        from .fastapi_probe import probe as fastapi_probe

        fastapi_probe(fastapi_app, result)

    if include_celery or celery_app is not None:
        from .celery_probe import probe_jobs

        probe_jobs(result, celery_app)   # best-effort; uses current_app when celery_app is None

    _merge_declarations(result, contract.build())
    result.recompute_coverage()
    return result


def install_flask(app: object) -> object:
    """Scope the current handler for every Flask request (the guard's watch-everything layer)."""
    from .flask_middleware import install_flask as _install

    return _install(app)


def install_fastapi(app: object) -> object:
    """Scope the current handler for every FastAPI request (the guard's watch-everything layer)."""
    from .fastapi_middleware import install_fastapi as _install

    return _install(app)


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
