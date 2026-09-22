"""The Flask request hook: the guard sees the running handler for every view."""

import socket

import pytest

flask = pytest.importorskip("flask")

from lenscheck_contract import contract, guard, install_flask  # noqa: E402


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
    app = flask.Flask(__name__)

    @app.route("/leaky")
    def leaky():                       # undeclared — the guard should catch this
        socket.getaddrinfo("api.stripe.com", 443)
        return "oops"

    @app.route("/declared")
    @contract.route("GET /declared", auth="public")
    @contract.effects("net:api.stripe.com")
    def declared():
        socket.getaddrinfo("api.stripe.com", 443)
        return "ok"

    return app


def test_undeclared_effect_on_an_undecorated_view_is_caught():
    app = _make_app()
    install_flask(app)
    guard.install(mode="warn")         # warn so the request completes and we can inspect violations
    client = app.test_client()
    client.get("/leaky")
    handlers = {h for h, _ in guard.violations}
    assert any(h.endswith("leaky") for h in handlers)   # handler was set → guard knew who acted


def test_declared_effect_does_not_violate():
    app = _make_app()
    install_flask(app)
    guard.install(mode="warn")
    app.test_client().get("/declared")
    assert not guard.violations


def test_handler_is_cleared_after_the_request():
    from lenscheck_contract.registry import current_handler

    app = _make_app()
    install_flask(app)
    guard.install(mode="warn")
    app.test_client().get("/declared")
    assert current_handler.get() is None
