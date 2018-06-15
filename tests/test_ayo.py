# pylint: disable=W0621,C0111,W0613,W0612,C0103,C0102

"""
Most basic tests for ayo
"""


import time
import asyncio
import itertools

import datetime as dt

from typing import Callable

import pytest

import ayo

from ayo.scope import ExecutionScope
from ayo.utils import ensure_future, LazyTask


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


class ExecutionCounter:
    def __init__(self, start=1):
        self.count = itertools.count(start)
        self.value = 0
        self.marks = set()

    def __call__(self, mark=None):
        """ Increment the counter.

            Pass a mark if you should make this call only once per unique
            value
        """
        if mark is not None:
            if mark in self.marks:
                raise ValueError(f"The mark '{mark}' has already been used")
            self.marks.add(mark)
        self.value = next(self.count)
        return self.value

    def __eq__(self, other):
        return self.value == other


@pytest.fixture
def count() -> Callable[[], int]:  # pylint: disable=C0103
    return ExecutionCounter()


@pytest.fixture
def timer() -> Timer:
    return Timer()


def test_version():
    """ The version is accessible programmatically """
    assert ayo.__version__ == "0.1.0"


def test_context_run_with_main(count):
    """ run_with_main execute the coroutine """

    @ayo.run_as_main()
    async def main(run):
        assert isinstance(run, ExecutionScope)
        count()

    assert count(), "The main() coroutine is called"


def test_ayo_sleep(timer):
    """ ayo.sleep does block for the number of seconds expected """

    @ayo.run_as_main()
    async def main(run):
        await asyncio.sleep(0.1)

    assert timer.has_almost_elapsed(0.1), "Sleep does make the code wait"


def test_forgetting_async_with_on_scope_raises_exception():
    """ We raise an exeption if sync with is used on scopes """
    with pytest.raises(TypeError):
        with ayo.scope():
            pass

    with pytest.raises(TypeError):
        ayo.scope().__exit__(None, None, None)


def test_asap(count):
    """ asap execute the coroutine in the scope """

    async def foo(mark):
        count(mark)

    @ayo.run_as_main()
    async def main(run):
        run.asap(foo(1))
        run.asap(foo(2))

    assert count == 2, "All coroutines have been called exactly once"


def test_asap_shortcut(count):
    """ lsfhit is a shorthand for asap """

    async def foo(mark):
        count(mark)

    @ayo.run_as_main()
    async def main(run):
        run << foo(1)
        run << foo(2)

    assert count == 2, "All coroutines have been called exactly once"


def test_all_shorthand(count):
    """ scope.all is a shorthand for creating a scope and runninig things in it """

    async def foo(mark):
        count(mark)

    @ayo.run_as_main()
    async def main(run):
        run.all(foo(1), foo(2), foo(3))

    assert count == 3, "All coroutines have been called exactly once"


def test_all_then_gather(count):
    """ gather() can be used to get results before the end of the scope """

    async def foo(mark):
        await asyncio.sleep(0.1)
        return count(mark)

    @ayo.run_as_main()
    async def main(run):
        tasks = run.all(foo(1), foo(2), foo(3))
        assert count.value < 3, "All coroutines should have not run yet"
        results = await tasks.gather()
        assert sorted(results) == [1, 2, 3]

# TODO: test what happen if we cancel a task before inserting it in asyncio
def test_cancel_scope(count):
    """ cancel() exit a scope and cancel all tasks in it """

    async def foo(run):
        await asyncio.sleep(1)
        count()
        return True

    @ayo.run_as_main()
    async def main(run):
        run << foo(run)

        # TODO: check what happens if I cancel from the parent scope
        # TODO: test stuff with the parent scope
        async with ayo.scope() as runalso:
            runalso.all(foo(runalso), foo(runalso), foo(runalso))
            assert not runalso.cancelled
            runalso.cancel()
            assert False, "We should never reach this point"

        assert not run.cancelled
        assert runalso.cancelled
        assert not count.value, "No coroutine has finished"

    assert count.value == 1, "One coroutine only has finished"


def test_timeout(count):
    """setting a timeout limit the time it can execute in """

    async def foo(s):
        await asyncio.sleep(s)
        count()
        return True

    # TODO: put timeout on run_with_main()
    @ayo.run_as_main()
    async def main1(run):
        async with ayo.scope(timeout=0.1) as runalso:
            runalso.all(foo(0.05), foo(0.2), foo(0.3))

    assert count.value == 1, "2 coroutines has been cancelled"

    @ayo.run_as_main()
    async def main2(run):
        async with ayo.scope(timeout=1) as runalso:
            runalso.all(foo(0.05), foo(0.2), foo(0.3))

    assert count.value == 4, "all coroutines has ran"

    @ayo.run_as_main(timeout=0.1)
    async def main3(run):
        async with ayo.scope() as runalso:
            runalso.all(foo(0.05), foo(0.2), foo(0.3))

    assert count.value == 5, "2 coroutines has been cancelled"

    # TODO: make the timeout a separate task, outside of the self._running_tasks
    @ayo.run_as_main(timeout=0.1)
    async def main4(run):
        async with ayo.scope() as runalso:
            runalso.all(foo(0.5), foo(2), foo(3))

    assert count.value == 5, "all coroutines has been cancelled"


# TODO: test timeout with a long sleep in the scope


def test_all_scope_results(count):
    """ A scope remembers the results of all awaited tasks """

    async def foo(mark):
        return count(mark)

    @ayo.run_as_main()
    async def main(s):

        async with ayo.scope() as run:
            run.all(foo(1), foo(2), foo(3))

        assert sorted(run.results) == [1, 2, 3]

def test_delayed_task_execution(count):
    """ Using a lazy task allow later schedule execution """

    async def foo(mark):
        return count(mark)

    task = None

    @ayo.run_as_main()
    async def main2(s):
        task = LazyTask(foo(1))
        await asyncio.sleep(0.1)
        assert count.value == 0
        task.schedule_for_execution()
        await task
        assert count.value == 1
        count()

    assert count.value == 2

def test_max_concurrency(count):
    """setting a timeout limit the time it can execute in """

    async def foo():
        start = dt.datetime.now()
        await asyncio.sleep(0.1)
        return start

    def diff_in_seconds(x, y):
        return abs(round(x.timestamp() - y.timestamp(), 1))

    @ayo.run_as_main()
    async def main1(run):
        async with ayo.scope(max_concurrency=2) as runalso:
            runalso.all(foo(), foo(), foo(), foo(), foo(), foo())

        a, b, c, d, e, f = runalso.results
        assert diff_in_seconds(a, b) == 0.0
        assert diff_in_seconds(c, d) == 0.0
        assert diff_in_seconds(e, f) == 0.0

        assert diff_in_seconds(c, b) == 0.1
        assert diff_in_seconds(d, e) == 0.1

    @ayo.run_as_main(max_concurrency=2)
    async def main2(run):
        results = run.all(foo(), foo(), foo(), foo(), foo(), foo()).gather()
        a, b, c, d, e, f = await results

        assert diff_in_seconds(a, b) == 0.0
        assert diff_in_seconds(c, d) == 0.0
        assert diff_in_seconds(e, f) == 0.0

        assert diff_in_seconds(c, b) == 0.1
        assert diff_in_seconds(d, e) == 0.1

# TODO: test concurrency with aside

# TODO: TEST cancelling the top task to see if the bottom tasks are
# cancelled

# TODO: test assertions preventing missuse of scopes

# TODO: make shield work ?
# TODO: check passing a custom loop
