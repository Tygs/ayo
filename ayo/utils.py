"""
    Collection of helpers
"""

import asyncio

from asyncio import gather, Task, Future, AbstractEventLoop, ensure_future


from typing import Callable, Coroutine, Union, Awaitable

import ayo

__all__ = ["FutureList", "run_as_main", "run", "pass_scope_and_run", "LazyTask"]


class FutureList(list):
    """ Syntaxic sugar to be able ease mass process of tasks """

    def gather(self) -> asyncio.Task:
        """ Apply asyncio.gather on self"""
        return gather(*self)

    # TODO: implement that
    # async def as_completed(self):
    #     for task in asyncio.as_completed(self.tasks):
    #         yield (await task)


class AsyncOnlyContextManager:
    """ Prevent the easy mistake of forgetting `async` before `with` """

    def __enter__(self):
        raise TypeError('You must use "async with", not just "with"')

    def __exit__(self, exc_type, exc, tb):
        raise TypeError('You muse use "__aexit__" instead of "__exit__"')


def run_as_main(
    timeout: Union[int, float] = None,
    max_concurrency: int = None,
    loop: AbstractEventLoop = None,
) -> Callable:
    """ Run this function as the main entry point of the asyncio program """

    def decorator(coroutine: Coroutine) -> Coroutine:  # pylint: disable=C0111
        pass_scope_and_run(
            coroutine, timeout=timeout, max_concurrency=max_concurrency, loop=loop
        )
        return coroutine

    return decorator


# TODO: test run
def run(
    awaitables: Awaitable,
    timeout: Union[int, float] = None,
    max_concurrency: int = None,
    loop: AbstractEventLoop = None,
    return_coroutine: bool = False,
) -> None:
    """ Start the event loop and execute the awaitables in a scope """

    @run_as_main()
    async def main_wrapper(scope):  # pylint: disable=C0111
        scope.asap(*awaitables)

    return pass_scope_and_run(
        main_wrapper,
        timeout=timeout,
        max_concurrency=max_concurrency,
        loop=loop,
        return_coroutine=return_coroutine,
    )


# TODO: test pass_scope_and_run
def pass_scope_and_run(
    *coroutines: Coroutine,
    timeout: Union[int, float] = None,
    max_concurrency: int = None,
    loop: AbstractEventLoop = None,
    return_coroutine: bool = False
) -> None:
    """Start the loop and execute the coros in a scope. Pass them the scope ref"""

    assert not (
        loop and return_coroutine
    ), "`loop` and `return_coroutine` are incompatible"

    async def main_wrapper():  # pylint: disable=C0111
        async with ayo.scope(timeout=timeout, max_concurrency=max_concurrency) as scope:
            scope.all(*(coro(scope) for coro in coroutines))

    if return_coroutine:
        return main_wrapper()

    loop = loop or asyncio.get_event_loop()
    loop.run_until_complete(main_wrapper())


class LazyTask(Future):
    """ A future linked to a unscheduled coroutine, that can be scheduled later """

    def __init__(self, awaitable, *, loop=None):
        super().__init__(loop=loop)
        self._awaitable = awaitable

    def schedule_for_execution(self):
        """ Create a task from the awaitable

            Link the task resolution to the future resolution
        """
        task = ensure_future(self._awaitable, loop=self._loop)
        task.add_done_callback(self._task_done_callback)
        return task

    def _task_done_callback(self, task: Task) -> None:
        """ After scheduling, when the related task is done, set the future result """
        try:
            self.set_result(task.result())
        except asyncio.CancelledError:
            self.cancel()
