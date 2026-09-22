"""The Flask probe: routes, methods, auth best-effort, and declaration merge."""

import functools

import pytest

flask = pytest.importorskip("flask")

from lenscheck_contract import build, contract  # noqa: E402


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


def _fake_login_required(fn):
    """Stand-in for flask_login.login_required — but with a co_filename the probe recognises."""
    @functools.wraps(fn)
    def wrapper(*a, **k):
        return fn(*a, **k)
    # rewrite the wrapper's source path to look like it came from flask_login
    wrapper.__code__ = wrapper.__code__.replace(
        co_filename="/site-packages/flask_login/utils.py"
    )
    return wrapper


def _make_app():
    app = flask.Flask(__name__)

    @app.route("/health")
    def health():
        return ""

    @app.route("/orders", methods=["POST", "GET"])
    def orders():
        return ""

    @app.route("/admin")
    @_fake_login_required
    def admin():
        return ""

    return app


def test_probe_records_routes_and_methods():
    c = build(include_django=False, flask_app=_make_app())
    assert "GET /health" in c.routes
    # multiple methods on one rule become separate routes; HEAD/OPTIONS are dropped
    assert "POST /orders" in c.routes
    assert "GET /orders" in c.routes
    assert not any("HEAD" in k or "OPTIONS" in k for k in c.routes)


def test_static_route_is_skipped():
    c = build(include_django=False, flask_app=_make_app())
    assert not any(r.path.startswith("/static") for r in c.routes.values())


def test_auth_detected_from_decorator():
    c = build(include_django=False, flask_app=_make_app())
    assert c.routes["GET /admin"].auth == "login_required"
    assert c.routes["GET /health"].auth == "unknown"


def test_auth_detected_on_class_based_view():
    from flask.views import MethodView

    app = flask.Flask(__name__)

    class Dashboard(MethodView):
        decorators = [_fake_login_required]            # class-level auth, the common Flask pattern

        def get(self):
            return ""

    app.add_url_rule("/dashboard", view_func=Dashboard.as_view("dashboard"))
    c = build(include_django=False, flask_app=app)
    assert c.routes["GET /dashboard"].auth == "login_required"


def test_jwt_extended_style_decorator_is_named():
    def jwt_required(fn):
        import functools

        @functools.wraps(fn)
        def wrapper(*a, **k):
            return fn(*a, **k)
        wrapper.__code__ = wrapper.__code__.replace(
            co_filename="/site-packages/flask_jwt_extended/view_decorators.py"
        )
        return wrapper

    app = flask.Flask(__name__)

    @app.get("/secure")
    @jwt_required
    def secure():
        return ""

    c = build(include_django=False, flask_app=app)
    assert c.routes["GET /secure"].auth == "jwt_required"


def test_declarations_merge_over_probe():
    app = flask.Flask(__name__)

    @app.route("/orders", methods=["POST"])
    @contract.route("POST /orders", auth="user")
    @contract.effects("net:api.stripe.com")
    def create():
        return ""

    c = build(include_django=False, flask_app=app)
    r = c.routes["POST /orders"]
    assert r.auth == "user"                     # declared auth wins over probed "unknown"
    assert r.effects == ["net:api.stripe.com"]
    assert r.source == "declared"
