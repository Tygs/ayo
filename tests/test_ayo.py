# pylint: disable=W0621,C0111,W0613,W0612,C0103

"""
Most basic tests for ayo
"""


import time

from types import SimpleNamespace

import pytest

import ayo

from ayo.scope import Scope


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

    def has_almost_elapsed(self, seconds, precision=2):
        """ Return True if `seconds` have approxitly passed since the last record """
        return round(self.elapsed - seconds, precision) == 0


@pytest.fixture
def ns() -> SimpleNamespace:  # pylint: disable=C0103
    """ Provide a fresh new namespace """
    return SimpleNamespace()


@pytest.fixture
def timer() -> Timer:
    return Timer()


def test_version():
    """ The version is accessible programmatically """
    assert ayo.__version__ == "0.1.0"


def test_context_run_with_main(ns):
    """ run_with_main execute the coroutine """
    ayoc = ayo.context()

    ns.has_run = False

    @ayoc.run_with_main()
    async def main(run):
        assert isinstance(run, Scope)
        ns.has_run = True

    assert ns.has_run


def test_ayo_sleep(timer):
    """ ayo.sleep does block for the number of seconds expected """
    ayoc = ayo.context()

    @ayoc.run_with_main()
    async def main(run):
        await ayo.sleep(3)

    assert timer.has_almost_elapsed(3)


def test_forgetting_async_with_on_scope_raises_exception():
    """ We raise an exeption if sync with is used on scopes """
    with pytest.raises(TypeError):
        with ayo.scope():
            pass

    with pytest.raises(TypeError):
        ayo.scope().__exit__(None, None, None)
