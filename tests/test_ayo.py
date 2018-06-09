# pylint: disable=W0621,C0111,W0613,W0612,C0103,C0102

"""
Most basic tests for ayo
"""


import time
import itertools

from typing import Callable

import pytest

import ayo

from ayo.scope import ExecutionScope
from ayo.context import AsynchronousExecutionContext


class Timer:
    """ Helper to calculate elapsed time """

    def __init__(self):
        self.record()

    def record(self):
        """ Store the current time """
        self.last_time = time.time()

    @property
    def elapsed(self):
        """ Return the time that has elapsed since the last record """
        return time.time() - self.last_time

    def has_almost_elapsed(self, seconds, precision=1):
        """ Return True if `seconds` have approxitly passed since the last record """
        return round(self.elapsed - seconds, precision) == 0


class Counter:
    def __init__(self):
        self.count = itertools.count(1)
        self.value = 0

    def __call__(self):
        self.value = next(self.count)
        return self.value

    def __eq__(self, other):
        return self.value == other


@pytest.fixture
def count() -> Callable[[], int]:  # pylint: disable=C0103
    return Counter()


@pytest.fixture
def ayoc() -> AsynchronousExecutionContext:
    return ayo.context()


@pytest.fixture
def timer() -> Timer:
    return Timer()


def test_version():
    """ The version is accessible programmatically """
    assert ayo.__version__ == "0.1.0"


def test_context_run_with_main(count, ayoc):
    """ run_with_main execute the coroutine """

    @ayoc.run_with_main()
    async def main(run):
        assert isinstance(run, ExecutionScope)
        count()

    assert count()


def test_ayo_sleep(timer, ayoc):
    """ ayo.sleep does block for the number of seconds expected """

    @ayoc.run_with_main()
    async def main(run):
        await run.sleep(3)

    assert timer.has_almost_elapsed(3)


def test_forgetting_async_with_on_scope_raises_exception():
    """ We raise an exeption if sync with is used on scopes """
    with pytest.raises(TypeError):
        with ayo.scope():
            pass

    with pytest.raises(TypeError):
        ayo.scope().__exit__(None, None, None)


def test_asap(count, ayoc):
    """ asap execute the coroutine in the scope """

    async def foo():
        count()

    @ayoc.run_with_main()
    async def main(run):
        run.asap(foo())
        run.asap(foo())

    assert count == 2


def test_asap_shortcut(count, ayoc):
    """ lsfhit is a shorthand for asap """

    async def foo():
        count()

    @ayoc.run_with_main()
    async def main(run):
        run << foo()
        run << foo()

    assert count == 2


def test_all_shorthand(count, ayoc):
    """ scope.all is a shorthand for creating a scope and runninig things in it """

    async def foo():
        count()

    @ayoc.run_with_main()
    async def main(run):
        run.all(foo(), foo(), foo())

    assert count == 3


def test_all_then_gather(count, ayoc):
    """ scope.all is a shorthand for creating a scope and runninig things in it """

    async def foo(run):
        await run.sleep(0.1)
        count()
        return True

    @ayoc.run_with_main()
    async def main(run):
        tasks = run.all(foo(run), foo(run), foo(run))
        assert count.value < 3
        results = await tasks.gather()
        assert isinstance(results, list)
        assert len(results) == 3
        assert all(results)
        assert count.value == 3


# The lib provides other similar shortcuts:

# - `ayo.map()`:
# - `ayo.starmap()`
# - `ayo.funcmap()`
# - `ayo.starfuncmap()`
# - `ayo.cancel()`
