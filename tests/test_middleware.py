import os
import socket
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


@pytest.fixture(autouse=True)
def clean_guard():
    from pryti_contract import guard

    guard.reset()
    yield
    guard.uninstall()
    guard.reset()


def test_middleware_blocks_an_undeclared_view():
    from pryti_contract import UndeclaredEffect, build, guard
    from pryti_contract.middleware import ContractMiddleware

    build()
    guard.install(mode="error")

    from shop import views

    mw = ContractMiddleware(lambda req: views.leaky_order(req))

    class Req:
        pass

    def get_response(req):
        mw.process_view(req, views.leaky_order, (), {})
        return views.leaky_order(req)

    mw = ContractMiddleware(get_response)
    with pytest.raises(UndeclaredEffect):
        mw(Req())


def test_middleware_allows_a_declared_view():
    from pryti_contract import build, guard
    from pryti_contract.middleware import ContractMiddleware

    build()
    guard.install(mode="error")

    from shop import views

    def get_response(req):
        mw_inner.process_view(req, views.create_order, (), {})
        try:
            return views.create_order(req)
        except socket.gaierror:
            return "no dns, guard decision is what matters"

    mw_inner = ContractMiddleware(get_response)
    mw_inner(object())
    assert not guard.violations


def test_scope_restores_the_previous_handler():
    from pryti_contract import scope
    from pryti_contract.registry import current_handler

    assert current_handler.get() is None
    with scope("a.b"):
        assert current_handler.get() == "a.b"
        with scope("c.d"):
            assert current_handler.get() == "c.d"
        assert current_handler.get() == "a.b"
    assert current_handler.get() is None
