"""The FastAPI ASGI middleware: the guard sees the running handler for every endpoint."""

import socket

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")  # FastAPI's TestClient needs it

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from lenscheck_contract import contract, guard, install_fastapi  # noqa: E402


@pytest.fixture(autouse=True)
def clean():
    from lenscheck_contract.registry import registry

    saved = (dict(registry.routes), dict(registry.jobs),
             {k: list(v) for k, v in registry._declared.items()})
    registry.reset()
    guard.reset()
    yield
    guard.uninstall()
    guard.reset()
    registry.routes.clear(); registry.routes.update(saved[0])
    registry.jobs.clear(); registry.jobs.update(saved[1])
    registry._declared.clear(); registry._declared.update(saved[2])


def _make_app():
    app = FastAPI()

    @app.get("/leaky")
    def leaky():                       # undeclared
        socket.getaddrinfo("api.stripe.com", 443)
        return {}

    @app.get("/declared")
    @contract.route("GET /declared", auth="public")
    @contract.effects("net:api.stripe.com")
    def declared():
        socket.getaddrinfo("api.stripe.com", 443)
        return {}

    install_fastapi(app)
    return app


def test_undeclared_effect_on_an_undecorated_endpoint_is_caught():
    guard.install(mode="warn")
    with TestClient(_make_app()) as client:
        client.get("/leaky")
    handlers = {h for h, _ in guard.violations}
    assert any(h.endswith("leaky") for h in handlers)


def test_declared_effect_does_not_violate():
    guard.install(mode="warn")
    with TestClient(_make_app()) as client:
        client.get("/declared")
    assert not guard.violations


def test_error_mode_blocks_the_call():
    # In error mode the undeclared effect raises inside the endpoint → 500, and it's recorded.
    guard.install(mode="error")
    with TestClient(_make_app(), raise_server_exceptions=False) as client:
        resp = client.get("/leaky")
    assert resp.status_code == 500
    assert any(h.endswith("leaky") for h, _ in guard.violations)


def test_async_endpoint_effect_is_caught():
    # The real async path: an `async def` endpoint resolving a host on the event loop.
    import asyncio

    app = FastAPI()

    @app.get("/aleaky")
    async def aleaky():
        try:
            await asyncio.get_running_loop().getaddrinfo("api.stripe.com", 443)
        except OSError:
            pass
        return {}

    install_fastapi(app)
    guard.install(mode="warn")
    with TestClient(app) as client:
        client.get("/aleaky")
    assert any(h.endswith("aleaky") for h, _ in guard.violations)
