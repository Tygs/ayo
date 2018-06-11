"""
    Machinery used to implement the Trio's nursery concept, here name
    "Scope"
"""


import threading

import asyncio

from enum import Enum

from typing import Union, Awaitable, cast

from ayo.utils import TaskList


class ExitExecutionScopee(Exception):
    """Break out of the with statement, cancelling all tasks"""


class ExecutionScope:
    """ Attempt at recreating trio.nursery for asyncio """

    class STATE(Enum):
        """ Scope life cycle """

        INIT = 0
        ENTERED = 1
        EXITED = 2
        CANCELLED = 3

    def __init__(self, name=None, loop=None, return_exceptions=False):
        # Parameters we will pass to gather()
        self.loop = loop
        self.return_exceptions = return_exceptions
        self.name = name

        # All the awaitables we will await in gather()
        self.tasks_to_await = {}
        self.awaited_tasks = set()

        # We use that to promote the parent scope as the current scope
        # in resolve()
        self._parent_scope = None

        # Make sure we use the scope in the proper order of states
        self.state = self.STATE.INIT

        # We'll store result of gather here in resolve()
        self._gathering_future = None

        # To prevent the used of self.cancel() outside of the scope
        self._used_as_context_manager = False

    async def __aenter__(self):
        self._used_as_context_manager = True
        return await self.enter()

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type:
            self._cancel_scope()
        else:
            await self.exit()

        return exc_type == ExitExecutionScopee

    def __enter__(self):
        raise TypeError('You must use "async with" on scopes, not just "with"')

    def __exit__(self, exc_type, exc, tb):
        raise TypeError('You muse use "__aexit__" on scope instead of "__exit__"')

    def __lshift__(self, coro):
        """ Shortcut for self.assap """
        self.asap(coro)

    def asap(self, awaitable: Awaitable) -> asyncio.Task:
        """ Execute the awaitable in the current scope as soon as possible """
        loop = self.loop or asyncio.get_event_loop()
        if awaitable in self.tasks_to_await:
            raise RuntimeError(
                f"The awaitable 'awaitable' is already scheduled in this scope"
            )
        task = cast(asyncio.Task, asyncio.ensure_future(awaitable, loop=loop))
        self.tasks_to_await[awaitable] = task
        return task

    def sleep(self, seconds: Union[int, float]) -> asyncio.Task:
        """ Alias to asyncio.sleep, but executed in the scope """
        return self.asap(asyncio.sleep(seconds))

    def all(self, *awaitables) -> TaskList:
        """ Schedule all tasks to be run in the current scope"""
        return TaskList(self.asap(awaitable) for awaitable in awaitables)

    async def enter(self):
        """ Set itself as the current scope """
        assert self.state == self.STATE.INIT, "You can't enter a scope twice"
        factory = asyncio.get_event_loop().get_task_factory()
        factory.set_current_scope(self)
        self.state = self.STATE.ENTERED
        return self

    async def exit(self):
        """ Await all awaitables created in the scope or cancel them all  """
        assert self.state == self.STATE.ENTERED, "You can't exit a scope you are not in"
        self.exited = self.STATE.EXITED

        self._restore_parent_scope()

        if not self.tasks_to_await:
            return

        # Await all submitted tasks. The tasks may themself submit more
        # task, so we do it in a loop to exhaust all potential nested tasks
        while self.tasks_to_await:
            # TODO: collecting results
            self.awaited_tasks.update(self.tasks_to_await.values())
            self._gathering_future = asyncio.gather(
                *self.tasks_to_await.values(),
                loop=self.loop,
                return_exceptions=self.return_exceptions,
            )
            # We empty the dict of tasks to await after gather() has a
            # reference on them otherwise it will have nothing to work on.
            # But we empty it before we await the gaher(), since gather()
            # may put new tasks in it.
            self.tasks_to_await.clear()
            await self._gathering_future

    def _cancel_scope(self):
        assert (
            self.state == self.STATE.ENTERED
        ), "You can't cancel a scope you are not in"
        self._restore_parent_scope()
        for awaitable in self.tasks_to_await.values():
            awaitable.cancel()
        self.state = self.STATE.CANCELLED

    def _restore_parent_scope(self):
        """ Restaure the parent scope as the current scope.

            It may be None, in which case we are out of all scopes.
        """
        factory = asyncio.get_event_loop().get_task_factory()
        factory.set_current_scope(self._parent_scope)

    def cancel(self):
        """ Exit the scope `with` block, cancelling all the tasks

            Only to be used inside the `with` block. If you call
            `enter()` and `exit()` manually, you should use
            `exit(cancel=True)`.
        """
        assert (
            self._used_as_context_manager
        ), "You can't call cancel() outside a `with` block"
        raise ExitExecutionScopee

    @property
    def cancelled(self):
        """ Has the scope being cancelled """
        return self.state == self.STATE.CANCELLED


class ScopedTaskFactory:  # pylint: disable=too-few-public-methods
    """ TaskFactory that ensure created tasks are attached to the scope """

    def __init__(self):
        self.thread_locals = threading.local()

    def get_current_scope(self) -> ExecutionScope:
        """ Get the current scope for the running thread """
        return getattr(self.thread_locals, "ayo_execution_scope", None)

    def set_current_scope(self, scope: ExecutionScope) -> ExecutionScope:
        """ Set the current scope for the running thread """
        self.thread_locals.ayo_execution_scope = scope
        return scope

    def __call__(self, loop, coro) -> asyncio.Task:
        """ Create a Task from the coroutine, then attach it to the current scope

            This allows the scope to still track tasks not created
            using it's infrastructure. E.G: if the user calls
            asyncio.ensure_future(coro) and never scope.run().

            This uses thread_local to get the current scope for the running
            thread.
        """
        # pylint: disable=W0212
        task = asyncio.Task(coro, loop=loop)
        if task._source_traceback:  # type: ignore
            del task._source_traceback[-1]  # type: ignore

        # scope = self.get_current_scope()
        # TODO: task tracking to warn if we ensure_future() without
        # a scope
        # TODO: capture_orphan_tasks option on scope
        # if scope:
        #     # Maybe add a warning here if coro not in the dict already ?
        #     scope.tasks_to_await[coro] = task
        return task


def get_current_scope(loop=None) -> ExecutionScope:
    """ Return the current scope for the running event loop """
    loop = loop or asyncio.get_event_loop()
    return loop.get_task_factory().get_current_scope()
