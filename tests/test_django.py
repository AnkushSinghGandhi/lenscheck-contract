import os
import sys
from pathlib import Path

import pytest

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo"


@pytest.fixture(scope="module", autouse=True)
def django_setup():
    sys.path.insert(0, str(DEMO))
    os.environ["DJANGO_SETTINGS_MODULE"] = "settings"
    import django

    django.setup()
    yield


def test_probe_finds_models_and_their_constraints():
    from pryti_contract import build

    c = build()
    assert "shop.Customer" in c.models
    assert c.models["shop.Customer"].fields["email"]["unique"] is True
    assert c.models["shop.Order"].fields["customer"]["relates_to"] == "shop.Customer"


def test_probe_finds_routes_built_in_a_loop():
    from pryti_contract import build

    c = build()
    paths = {r.path for r in c.routes.values()}
    assert "/reports/daily" in paths
    assert "/reports/monthly" in paths


def test_declared_auth_survives_the_probe():
    from pryti_contract import build

    c = build()
    assert c.routes["POST /orders"].auth == "user"
    assert c.routes["POST /orders"].effects == ["net:api.stripe.com"]


def test_login_required_is_detected_without_a_declaration():
    from pryti_contract import build

    c = build()
    account = [r for r in c.routes.values() if r.path == "/account"]
    assert account and account[0].auth == "login_required"


def test_class_based_view_mixin_is_detected():
    from pryti_contract import build

    c = build()
    panel = [r for r in c.routes.values() if r.path == "/admin-panel"]
    assert panel
    assert all(r.auth == "LoginRequiredMixin" for r in panel)
    assert {r.method for r in panel} == {"GET", "POST"}


def test_undeclared_route_is_reported_as_unknown_auth():
    from pryti_contract import build

    c = build()
    leaky = [r for r in c.routes.values() if r.path == "/orders/leaky"]
    assert leaky and leaky[0].auth == "unknown"


def test_coverage_is_reported_honestly():
    from pryti_contract import build

    c = build()
    assert c.coverage.routes_total > 0
    assert c.coverage.routes_with_auth < c.coverage.routes_total


def test_empty_and_allowany_permission_classes_read_as_public():
    # an empty permission_classes = [] means no checks → open, not "unknown"; AllowAny → open too
    from pryti_contract.django_probe import _auth_of

    open_view = type("OpenView", (), {"permission_classes": []})
    allowany = type("AllowAny", (), {})
    wide_view = type("WideView", (), {"permission_classes": [allowany]})
    assert _auth_of(type("cb", (), {"view_class": open_view})()) == "public"
    assert _auth_of(type("cb", (), {"view_class": wide_view})()) == "public"


def test_model_records_its_sql_table():
    from pryti_contract import build

    c = build()
    assert c.models["shop.Customer"].table == "shop_customer"   # Django's default table name, captured


def test_cache_ops_are_recorded_as_effects():
    from django.core.cache import cache

    from pryti_contract import guard

    guard.reset()
    guard.install(mode="record")
    try:
        cache.set("k", 1)
        cache.get("k")
        cache.delete("k")
    finally:
        observed = {e for effects in guard.suggestions().values() for e in effects}
        guard.uninstall()
    assert "cache:write" in observed and "cache:read" in observed
