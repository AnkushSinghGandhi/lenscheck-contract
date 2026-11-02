"""An effect must be attributed to the handler that caused it, not to a neighbour running at the same
time, and not dropped into `<no handler>` (recorded but never enforced) when the handler fans work out.

Resolution of an `.invalid` host fails (OSError), but the guard decides before the lookup happens."""

import asyncio
import concurrent.futures as cf
import socket
import threading

import pytest

from lenscheck_contract import UndeclaredEffect, guard
from lenscheck_contract.registry import current_handler


@pytest.fixture(autouse=True)
def clean():
    guard.reset()
    current_handler.set(None)               # the sync tests set it on the main thread: don't leak it
    yield
    guard.uninstall()
    guard.reset()
    current_handler.set(None)


def _resolve(host):
    try:
        socket.getaddrinfo(host, 443)
    except OSError:
        pass


async def _aresolve(host):
    try:
        await asyncio.get_running_loop().getaddrinfo(host, 443)
    except OSError:
        pass


def _by_handler():
    return {h: sorted(e) for h, e in guard.observed.items() if not h.startswith("<")}


def test_concurrent_async_tasks_each_keep_their_own_handler():
    guard.install(mode="record")

    async def handler(name, host):
        current_handler.set(name)
        await asyncio.sleep(0.01)           # let the others interleave before resolving
        await _aresolve(host)

    async def main():
        await asyncio.gather(handler("A.view", "a.invalid"), handler("B.view", "b.invalid"),
                             handler("C.view", "c.invalid"))

    asyncio.run(main())
    assert _by_handler() == {"A.view": ["net:a.invalid"], "B.view": ["net:b.invalid"],
                             "C.view": ["net:c.invalid"]}


def test_concurrent_threads_each_keep_their_own_handler():
    guard.install(mode="record")
    barrier = threading.Barrier(3)

    def request(name, host):
        current_handler.set(name)
        barrier.wait()                       # all three are inside their handler at once
        _resolve(host)

    threads = [threading.Thread(target=request, args=(f"{n}.view", f"{n.lower()}.invalid")) for n in "ABC"]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert _by_handler() == {"A.view": ["net:a.invalid"], "B.view": ["net:b.invalid"],
                             "C.view": ["net:c.invalid"]}


def test_thread_pool_work_is_attributed_to_the_submitting_handler():
    guard.install(mode="record")

    def handler(name, host):
        current_handler.set(name)
        with cf.ThreadPoolExecutor(2) as ex:
            ex.submit(_resolve, host).result()

    handler("A.view", "a.invalid")
    handler("B.view", "b.invalid")
    assert _by_handler() == {"A.view": ["net:a.invalid"], "B.view": ["net:b.invalid"]}
    assert "<no handler>" not in guard.observed


def test_run_in_executor_is_attributed_to_the_awaiting_handler():
    guard.install(mode="record")

    async def main():
        current_handler.set("A.view")
        await asyncio.get_running_loop().run_in_executor(None, _resolve, "a.invalid")

    asyncio.run(main())
    assert _by_handler() == {"A.view": ["net:a.invalid"]}


def test_undeclared_effect_in_a_thread_pool_is_enforced():
    guard.install(mode="error")

    def handler():
        current_handler.set("A.view")
        with cf.ThreadPoolExecutor(1) as ex:
            ex.submit(_resolve, "api.stripe.com").result()

    with pytest.raises(UndeclaredEffect):
        handler()


def test_asyncio_to_thread_is_attributed_to_the_awaiting_handler():
    guard.install(mode="record")

    async def main():
        current_handler.set("A.view")
        await asyncio.to_thread(_resolve, "a.invalid")

    asyncio.run(main())
    assert _by_handler() == {"A.view": ["net:a.invalid"]}


def test_thread_pool_patch_is_removed_on_uninstall():
    original = cf.ThreadPoolExecutor.submit
    guard.install(mode="record")
    assert cf.ThreadPoolExecutor.submit is not original
    guard.uninstall()
    assert cf.ThreadPoolExecutor.submit is original


def test_executor_results_and_exceptions_still_flow_through_submit():
    guard.install(mode="record")
    with cf.ThreadPoolExecutor(1) as ex:
        assert ex.submit(lambda x, y=1: x + y, 2, y=3).result() == 5
        with pytest.raises(ZeroDivisionError):
            ex.submit(lambda: 1 / 0).result()
