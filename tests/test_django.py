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
