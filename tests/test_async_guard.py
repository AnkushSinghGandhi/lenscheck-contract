"""The guard must catch effects from *async* code too — httpx.AsyncClient / aiohttp resolve on the
event loop, whose getaddrinfo runs in an executor thread where the handler contextvar is lost.
The guard hooks the loop's getaddrinfo so the check runs in the caller's async context."""

import asyncio

import pytest

from lenscheck_contract import UndeclaredEffect, guard
from lenscheck_contract.registry import current_handler


@pytest.fixture(autouse=True)
def clean():
    guard.reset()
    yield
    guard.uninstall()
    guard.reset()


def test_async_effect_is_attributed_to_the_handler():
    guard.install(mode="warn")

    async def main():
        current_handler.set("demo.async_handler")
        try:
            await asyncio.get_running_loop().getaddrinfo("example.invalid", 443)
        except OSError:
            pass  # resolution fails; the guard decision is what we're testing

    asyncio.run(main())
    assert ("demo.async_handler", "net:example.invalid") in guard.violations


def test_async_effect_is_blocked_in_error_mode():
    guard.install(mode="error")

    async def main():
        current_handler.set("demo.async_handler")
        await asyncio.get_running_loop().getaddrinfo("api.stripe.com", 443)

    with pytest.raises(UndeclaredEffect):
        asyncio.run(main())


def test_declared_async_effect_passes():
    from lenscheck_contract import contract

    @contract.effects("net:api.stripe.com")
    def handler():
        pass

    guard.install(mode="error")

    async def main():
        current_handler.set(handler.__lenscheck_handler__)
        try:
            await asyncio.get_running_loop().getaddrinfo("api.stripe.com", 443)
        except OSError:
            pass

    asyncio.run(main())          # must not raise
    assert not guard.violations
    contract.reset()


def test_uninstall_restores_the_loop_getaddrinfo():
    from asyncio.base_events import BaseEventLoop

    before = BaseEventLoop.getaddrinfo
    guard.install(mode="warn")
    assert BaseEventLoop.getaddrinfo is not before
    guard.uninstall()
    assert BaseEventLoop.getaddrinfo is before
