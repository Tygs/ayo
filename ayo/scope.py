"""
    Machinery used to implement the Trio's nursery concept, here name
    "Scope"
"""


import threading

import asyncio

from itertools import chain
from enum import Enum

from typing import Awaitable, cast

from ayo.utils import TaskList


class ExecutionScope:
    """ Attempt at recreating trio.nursery for asyncio """

    class STATE(Enum):
        """ Scope life cycle """

        INIT = 0
        ENTERED = 1
        EXITED = 2
        CANCELLED = 3
        TIMEDOUT = 4

    def __init__(self, loop=None, timeout=None, return_exceptions=False):
        # Parameters we will pass to gather()
        self._loop = loop
        self.return_exceptions = return_exceptions

        # All the awaitables we will await in gather()
        self.tasks_to_await = {}
        self.awaited_tasks = set()

        # We use that to promote the parent scope as the current scope
        # in resolve()
        self._parent_scope = None

        # Make sure we use the scope in the proper order of states
        self.state = self.STATE.INIT

        # To prevent the used of self.cancel() outside of the scope
        self._used_as_context_manager = False

        # Store the timeout time and reference to the handler
        self._timeout_handler = None
        self.timeout = timeout

    async def __aenter__(self):
        self._used_as_context_manager = True
        return await self.enter()

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type:
            self._cancel_scope()
        else:
            # A cancellation may happen in the __aexit__
            try:
                await self.exit()
            except asyncio.CancelledError:
                self._cancel_scope()
                return True

        return exc_type == asyncio.CancelledError

    def __enter__(self):
        raise TypeError('You must use "async with" on scopes, not just "with"')

    def __exit__(self, exc_type, exc, tb):
        raise TypeError('You muse use "__aexit__" on scope instead of "__exit__"')

    def __lshift__(self, coro):
        """ Shortcut for self.assap """
        return self.asap(coro)

    @property
    def loop(self):
        """ Return the internal loop or the current one """
        return self._loop or asyncio.get_event_loop()

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

    def all(self, *awaitables) -> TaskList:
        """ Schedule all tasks to be run in the current scope"""
        return TaskList(self.asap(awaitable) for awaitable in awaitables)

    async def enter(self):
        """ Set itself as the current scope """
        assert self.state == self.STATE.INIT, "You can't enter a scope twice"
        # TODO: in debug mode only:
        loop = self.loop
        factory = loop.get_task_factory()
        factory.set_current_scope(self)
        self.state = self.STATE.ENTERED

        # Cancel all tasks in case of a timeout
        if self.timeout:
            self._timeout_handler = self.asap(self.trigger_timeout(self.timeout))

        return self

    async def exit(self):
        """ Await all awaitables created in the scope or cancel them all  """
        assert self.state == self.STATE.ENTERED, "You can't exit a scope you are not in"

        if not self.tasks_to_await:
            self.cancel_timeout()
            return

        # Await all submitted tasks. The tasks may themself submit more
        # task, so we do it in a loop to exhaust all potential nested tasks
        while self.tasks_to_await:
            # TODO: collecting results
            self.awaited_tasks.update(self.tasks_to_await.values())
            tasks = asyncio.gather(
                *self.tasks_to_await.values(),
                loop=self._loop,
                return_exceptions=self.return_exceptions,
            )
            # We empty the dict of tasks to await after gather() has a
            # reference on them otherwise it will have nothing to work on.
            # But we empty it before we await the gaher(), since gather()
            # may put new tasks in it.
            self.tasks_to_await.clear()
            await tasks

        self.cancel_timeout()
        # TODO: in debug mode only
        self._restore_parent_scope()

        self.state = self.STATE.EXITED

    async def trigger_timeout(self, seconds):
        """ sleep for n seconds and cancel the scope """
        await asyncio.sleep(seconds)
        self.cancel()

    def cancel_timeout(self):
        """ Disable the timeout """
        if self._timeout_handler:
            self._timeout_handler.cancel()

    def _cancel_scope(self):
        assert (
            self.state == self.STATE.ENTERED
        ), "You can't cancel a scope you are not in"

        self.cancel_timeout()

        # TODO: in debug mode only
        self._restore_parent_scope()
        for awaitable in chain(self.tasks_to_await.values(), self.awaited_tasks):
            awaitable.cancel()
        self.state = self.STATE.CANCELLED

    def _restore_parent_scope(self):
        """ Restaure the parent scope as the current scope.

            It may be None, in which case we are out of all scopes.
        """
        factory = self.loop.get_task_factory()
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
        raise asyncio.CancelledError

    @property
    def cancelled(self):
        """ Has the scope being cancelled """
        return self.state.value >= self.STATE.CANCELLED.value


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
