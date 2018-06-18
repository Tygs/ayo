"""
    Machinery used to implement the Trio's nursery concept, here name
    "Scope"
"""

import asyncio

from asyncio import ensure_future, Future, Task

from collections import deque
from itertools import chain
from enum import Enum

from typing import Awaitable, Union

from ayo.utils import FutureList, AsyncOnlyContextManager, LazyTask


class ExecutionScope(AsyncOnlyContextManager):
    """ Attempt at recreating trio.nursery for asyncio """

    # pylint: disable=too-many-instance-attributes

    class STATE(Enum):
        """ Scope life cycle """

        INIT = 0
        ENTERED = 1
        EXITED = 2
        CANCELLED = 3
        TIMEDOUT = 4

    def __init__(
        self, loop=None, timeout=None, max_concurrency=None, return_exceptions=False
    ):

        assert timeout is None or timeout >= 0, "timeout must be > 0"

        # Parameters we will pass to gather()
        self._loop = loop
        self.return_exceptions = return_exceptions

        # All the awaitables we process on scope r
        self._lazy_task_queue = deque()
        self._scheduled_tasks_queue = deque()
        self._awaited_tasks = deque()

        # Results of all awaited tasks
        self.results = []

        # How many tasks can run at the same time in the scope
        self.max_concurrency = max_concurrency
        # No need to make this check if no concurrency limit
        if max_concurrency is None:
            self._can_schedule_task = lambda: True
        else:
            self._can_schedule_task = (
                lambda: len(self._scheduled_tasks_queue) < self.max_concurrency
            )

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

    def __lshift__(self, coro):
        """ Shortcut for self.assap """
        return self.asap(coro)

    def asap(self, awaitable: Awaitable) -> Union[Task, LazyTask, Future]:
        """ Execute the awaitable in the current scope as soon as possible """

        loop = self._loop or asyncio.get_event_loop()

        if self.max_concurrency:

            if self._can_schedule_task():
                # Schedule the task for execution in the event loop
                task = ensure_future(awaitable, loop=loop)
                self._scheduled_tasks_queue.append(task)
            else:
                # This is the only future that is not a task. This way
                # it's not scheduling the awaitable on the event loop
                task = LazyTask(awaitable, loop=self._loop)

                # This future is in self._scheduled_tasks_queue. so that
                # it is awaited at the scope resolution.
                self._scheduled_tasks_queue.append(task)

                # We then put the future in the
                self._lazy_task_queue.append(task)

            # When the task is done, we want to be sure it schedule for
            # for execution in the loop the next task in the queue
            task.add_done_callback(self._schedule_next_task)
            return task

        task = ensure_future(awaitable, loop=loop)
        self._scheduled_tasks_queue.append(task)
        return task

    def _schedule_next_task(
        self, future: asyncio.Future = None  # pylint: disable=W0613
    ) -> None:
        """ Schedule the next Lazy tasks from the queue for execution """
        if self._lazy_task_queue:
            # TODO: document the fact max_concurrency is not recursive
            # TODO: affer an alternative scope design that allow recursive
            # max concurrency ?
            self._lazy_task_queue.popleft().schedule_for_execution()

    def all(self, *awaitables) -> FutureList:
        """ Schedule all tasks to be run in the current scope"""
        return FutureList(self.asap(awaitable) for awaitable in awaitables)

    async def enter(self):
        """ Set itself as the current scope """
        assert self.state == self.STATE.INIT, "You can't enter a scope twice"
        # TODO: in debug mode only:
        self.state = self.STATE.ENTERED

        # Cancel all tasks in case of a timeout
        if self.timeout:
            self._timeout_handler = self.asap(self.trigger_timeout(self.timeout))

        return self

    async def exit(self):
        """ Await all awaitables created in the scope or cancel them all  """
        assert self.state == self.STATE.ENTERED, "You can't exit a scope you are not in"

        if not self._scheduled_tasks_queue:
            self.cancel_timeout()
            return

        # Await all submitted tasks. The tasks may themself submit more
        # task, so we do it in a loop to exhaust all potential nested tasks
        while self._scheduled_tasks_queue:
            # TODO: collecting results
            tasks_to_run = tuple(self._scheduled_tasks_queue)
            self._scheduled_tasks_queue.clear()
            tasks = asyncio.gather(
                *tasks_to_run, loop=self._loop, return_exceptions=self.return_exceptions
            )
            self._awaited_tasks.extend(tasks_to_run)
            self.results.extend(await tasks)

        self.cancel_timeout()

        self.state = self.STATE.EXITED

    async def trigger_timeout(self, seconds):
        """ sleep for n seconds and cancel the scope """
        await asyncio.sleep(seconds)
        self.cancel()

    def cancel_timeout(self):
        """ Disable the timeout """
        if self._timeout_handler:
            self._timeout_handler.cancel()

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

    def _cancel_scope(self):
        assert (
            self.state == self.STATE.ENTERED
        ), "You can't cancel a scope you are not in"

        self.cancel_timeout()

        for awaitable in chain(self._scheduled_tasks_queue, self._awaited_tasks):
            awaitable.cancel()
        self.state = self.STATE.CANCELLED
