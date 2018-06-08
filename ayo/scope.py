"""
    Machinery used to implement the Trio's nursery concept, here name
    "Scope"
"""


import threading

import asyncio

from typing import Union


class ScopedTaskFactory:  # pylint: disable=too-few-public-methods
    """ TaskFactory that ensure created tasks are attached to the scope """

    def __init__(self):
        self.thread_local = threading.local()

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

        scope = getattr(self.thread_local, "asyncio_task_scope", None)
        if scope:
            # Maybe add a warning here if coro not in the dict already ?
            scope.awaitables[coro] = task
        return task


class Scope:
    """ Attempt at recreating trio.nursery for asyncio """

    def __init__(self, loop=None, return_exceptions=False):
        # Parameters we will pass to gather()
        self.loop = loop
        self.return_exceptions = return_exceptions

        # All the awaitable we will awaited in gather()
        # This is also indirectly filled from ScopedEventLoop.created_task
        # in case the user by pass the scope infrastructure
        self.awaitables = {}

        # We use that to promote the parent scope as the current scope
        # in resolve()
        self._parent_scope = None

        # Make sure the scope can't be used twice
        self.resolved = False

        # We'll store result of gather here in resolve()
        self._gathering_future = None

    async def __aenter__(self):
        return await self.begin()

    async def __aexit__(self, exc_type, exc, tb):
        await self.resolve(cancel=bool(exc_type))
        return False  # No return to propagate the possible exception

    def __enter__(self):
        raise TypeError('You must use "async with" on scopes, not just "with"')

    def __exit__(self, exc_type, exc, tb):
        raise TypeError('You muse use "__aexit__" on scope instead of "__exit__"')

    def __lshift__(self, coro):
        """ Shortcut for self.assap """
        self.asap(coro)

    def asap(self, awaitable):
        """ Execute the awaitable in the current scope as soon as possible """
        loop = self.loop or asyncio.get_event_loop()
        task = self.awaitables[awaitable] = asyncio.ensure_future(awaitable, loop=loop)
        return task

    def sleep(self, seconds: Union[int, float]) -> asyncio.Task:
        """ Alias to asyncio.sleep, but executed in the scope """
        return self.asap(asyncio.sleep(seconds))

    async def begin(self):
        """ Set itself as the current scope """
        assert not self.resolved
        factory = asyncio.get_event_loop().get_task_factory()
        factory.thread_local.asyncio_task_scope = self
        return self

    async def resolve(self, cancel=False):
        """ Await all awaitables created in the scope or cancel them all  """
        self.resolved = True

        # Restaure the parent scope as the current scope. Which may
        # may be None, in which case we are out of all scopes.
        factory = asyncio.get_event_loop().get_task_factory()
        factory.thread_local.asyncio_task_scope = self._parent_scope

        if not self.awaitables:
            return

        # Group all tasks so we can await them together
        self._gathering_future = asyncio.gather(
            *self.awaitables.values(),
            loop=self.loop,
            return_exceptions=self.return_exceptions,
        )

        if cancel:
            self._gathering_future.cancel()

        return await self._gathering_future
