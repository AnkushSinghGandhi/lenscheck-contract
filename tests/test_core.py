import json
import socket

import pytest

from pryti_contract import Contract, UndeclaredEffect, contract, diff, guard, render_text


@pytest.fixture(autouse=True)
def clean():
    contract.reset()
    guard.reset()
    yield
    guard.uninstall()
    contract.reset()
    guard.reset()


def test_route_and_effects_are_recorded():
    @contract.route("POST /orders", auth="user")
    @contract.effects("net:api.stripe.com", "email")
    def create_order():
        return "ok"

    c = contract.build()
    assert "POST /orders" in c.routes
    r = c.routes["POST /orders"]
    assert r.auth == "user"
    assert r.effects == ["email", "net:api.stripe.com"]
    assert create_order() == "ok"


def test_contract_json_is_stable():
    @contract.route("GET /health", auth="public")
    def health():
        pass

    a = json.dumps(contract.build().to_dict(), sort_keys=True)
    b = json.dumps(contract.build().to_dict(), sort_keys=True)
    assert a == b


def test_undeclared_effect_raises():
    @contract.route("POST /pay", auth="user")
    def pay():
        socket.getaddrinfo("api.stripe.com", 443)

    guard.install(mode="error")
    with pytest.raises(UndeclaredEffect) as exc:
        pay()
    assert "api.stripe.com" in str(exc.value)
    assert guard.violations


def test_declared_effect_is_allowed(monkeypatch):
    calls = []

    @contract.route("POST /pay2", auth="user")
    @contract.effects("net:api.stripe.com")
    def pay():
        socket.getaddrinfo("api.stripe.com", 443)
        calls.append(1)

    guard.install(mode="error")
    monkeypatch.setattr(
        guard._originals["getaddrinfo"].__self__ if False else socket,
        "gethostbyname",
        lambda h: "1.2.3.4",
        raising=False,
    )
    # real DNS may be unavailable; only the guard decision matters here
    try:
        pay()
    except socket.gaierror:
        pass
    assert not guard.violations


def test_wildcard_pattern_matches_subdomain():
    @contract.route("POST /pay3", auth="user")
    @contract.effects("net:*.stripe.com")
    def pay():
        socket.getaddrinfo("api.stripe.com", 443)

    guard.install(mode="error")
    try:
        pay()
    except socket.gaierror:
        pass
    assert not guard.violations


def test_localhost_is_never_an_effect():
    @contract.route("GET /db", auth="user")
    def db():
        socket.getaddrinfo("localhost", 5432)

    guard.install(mode="error")
    try:
        db()
    except socket.gaierror:
        pass
    assert not guard.violations


def test_record_mode_suggests_declarations():
    @contract.route("POST /pay4", auth="user")
    def pay():
        socket.getaddrinfo("api.stripe.com", 443)

    guard.install(mode="record")
    try:
        pay()
    except socket.gaierror:
        pass
    sugg = guard.suggestions()
    assert any("net:api.stripe.com" in v for v in sugg.values())


def test_effects_outside_a_handler_are_recorded_not_raised():
    guard.install(mode="error")
    try:
        socket.getaddrinfo("api.stripe.com", 443)
    except socket.gaierror:
        pass
    assert not guard.violations
    assert "<no handler>" in guard.observed


# ---------------- diff ----------------


def _c(routes=(), models=(), jobs=()):
    data = {"routes": list(routes), "models": list(models), "jobs": list(jobs)}
    return Contract.from_dict(data)


def test_auth_weakening_is_risky():
    base = _c([{"method": "POST", "path": "/admin", "handler": "h", "auth": "staff"}])
    head = _c([{"method": "POST", "path": "/admin", "handler": "h", "auth": "unknown"}])
    changes = diff(base, head)
    assert changes[0].severity == "risky"
    assert changes[0].kind == "auth_weakened"


def test_new_effect_is_risky():
    base = _c([{"method": "POST", "path": "/pay", "handler": "h", "auth": "user"}])
    head = _c(
        [
            {
                "method": "POST",
                "path": "/pay",
                "handler": "h",
                "auth": "user",
                "effects": ["net:api.stripe.com"],
            }
        ]
    )
    changes = diff(base, head)
    assert any(c.kind == "effect_added" and c.severity == "risky" for c in changes)


def test_dropped_field_is_risky():
    base = _c(models=[{"name": "app.User", "fields": {"email": {"type": "CharField"}}}])
    head = _c(models=[{"name": "app.User", "fields": {}}])
    changes = diff(base, head)
    assert any(c.kind == "field_removed" and c.severity == "risky" for c in changes)


def test_unique_relaxed_is_risky():
    base = _c(
        models=[{"name": "app.User", "fields": {"email": {"type": "CharField", "unique": True}}}]
    )
    head = _c(models=[{"name": "app.User", "fields": {"email": {"type": "CharField"}}}])
    changes = diff(base, head)
    assert any("unique" in c.detail and c.severity == "risky" for c in changes)


def test_identical_contracts_have_no_changes():
    base = _c([{"method": "GET", "path": "/x", "handler": "h", "auth": "user"}])
    head = _c([{"method": "GET", "path": "/x", "handler": "h", "auth": "user"}])
    assert diff(base, head) == []
    assert render_text([]) == "No contract changes."


def test_table_rename_is_risky():
    base = _c(models=[{"name": "app.Order", "table": "orders", "fields": {}}])
    head = _c(models=[{"name": "app.Order", "table": "orders_v2", "fields": {}}])
    changes = diff(base, head)
    assert any(c.kind == "table_renamed" and c.severity == "risky" for c in changes)


def test_new_cache_effect_is_lower_severity_than_network():
    route = lambda effects: {"method": "GET", "path": "/x", "handler": "h", "auth": "user", "effects": effects}
    base = _c([route([])])
    head = _c([route(["cache:write", "cache:read", "net:api.x.com"])])
    sev = {c.detail: c.severity for c in diff(base, head)}
    assert sev["new effect: cache:write"] == "review"      # invalidation → worth a look
    assert sev["new effect: cache:read"] == "info"         # read → informational
    assert sev["new effect: net:api.x.com"] == "risky"     # outbound network → risky
