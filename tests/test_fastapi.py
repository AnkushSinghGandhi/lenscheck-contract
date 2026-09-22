"""The FastAPI probe: routes, methods, auth from the dependency tree, and declaration merge."""

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi import Depends, FastAPI, Security  # noqa: E402
from fastapi.security import HTTPBearer  # noqa: E402

from lenscheck_contract import build, contract  # noqa: E402

_bearer = HTTPBearer(auto_error=False)


def _current_user(cred=Security(_bearer)):
    return cred


@pytest.fixture(autouse=True)
def clean():
    # Snapshot/restore rather than reset: the global registry holds import-time declarations
    # from other test modules (e.g. the Django demo) that later tests rely on.
    from lenscheck_contract.registry import registry

    saved = (dict(registry.routes), dict(registry.jobs),
             {k: list(v) for k, v in registry._declared.items()})
    registry.reset()          # start each test with a clean registry (no cross-module bleed)
    yield
    registry.routes.clear(); registry.routes.update(saved[0])
    registry.jobs.clear(); registry.jobs.update(saved[1])
    registry._declared.clear(); registry._declared.update(saved[2])


def _make_app():
    app = FastAPI()

    @app.get("/health")
    def health():
        return {}

    @app.post("/orders")
    def create(user=Depends(_current_user)):
        return {}

    return app


def test_probe_records_routes_and_methods():
    c = build(include_django=False, fastapi_app=_make_app())
    assert "GET /health" in c.routes
    assert "POST /orders" in c.routes
    assert not any("HEAD" in k or "OPTIONS" in k for k in c.routes)


def test_public_route_has_no_guards():
    c = build(include_django=False, fastapi_app=_make_app())
    assert c.routes["GET /health"].auth == "public"


def test_security_scheme_is_named():
    c = build(include_django=False, fastapi_app=_make_app())
    # the security scheme name wins over the dependency function name
    assert c.routes["POST /orders"].auth == "HTTPBearer"


def test_auth_from_dependency_name_without_scheme():
    app = FastAPI()

    def require_admin():
        return True

    @app.get("/reports")
    def reports(_=Depends(require_admin)):
        return {}

    c = build(include_django=False, fastapi_app=app)
    assert c.routes["GET /reports"].auth == "require_admin"


def test_declarations_merge_over_probe():
    app = FastAPI()

    @app.post("/orders")
    @contract.route("POST /orders", auth="user")
    @contract.effects("net:api.stripe.com")
    def create():
        return {}

    c = build(include_django=False, fastapi_app=app)
    r = c.routes["POST /orders"]
    assert r.auth == "user"                     # declared auth wins over probed scheme
    assert r.effects == ["net:api.stripe.com"]
    assert r.source == "declared"
