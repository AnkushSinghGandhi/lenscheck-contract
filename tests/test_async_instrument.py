"""An async handler decorated with @contract.effects must stay scoped while it actually runs —
the direct-call path (jobs, scripts, tests), independent of any web middleware."""

import asyncio

import pytest

from lenscheck_contract import UndeclaredEffect, contract, guard
from lenscheck_contract.registry import current_handler


@pytest.fixture(autouse=True)
def clean():
    contract.reset()
    guard.reset()
    yield
    guard.uninstall()
    guard.reset()
    contract.reset()


def test_async_handler_keeps_its_scope_while_running():
    seen = {}

    @contract.effects("net:api.stripe.com")
    async def do_work():
        await asyncio.sleep(0)                       # yield control — the scope must survive this
        seen["handler"] = current_handler.get()

    asyncio.run(do_work())
    assert seen["handler"] == do_work.__lenscheck_handler__


def test_declared_async_effect_passes_and_undeclared_blocks():
    @contract.effects("net:api.stripe.com")
    async def charge():
        await asyncio.get_running_loop().getaddrinfo("api.stripe.com", 443)

    @contract.effects("net:api.stripe.com")
    async def leak():
        await asyncio.get_running_loop().getaddrinfo("evil.example.com", 443)

    guard.install(mode="error")

    async def ok():
        try:
            await charge()                           # declared → allowed (DNS may fail, that's fine)
        except OSError:
            pass
    asyncio.run(ok())
    assert not guard.violations

    with pytest.raises(UndeclaredEffect):
        asyncio.run(leak())                          # undeclared → blocked, in the async handler's scope


def test_sync_handler_still_works():
    seen = {}

    @contract.effects("net:x")
    def sync_work():
        seen["handler"] = current_handler.get()

    sync_work()
    assert seen["handler"] == sync_work.__lenscheck_handler__
