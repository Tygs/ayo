"""
    Declarative system for async tasks groups
"""

import asyncio

from typing import Callable, Coroutine

from ayo.scope import ScopedTaskFactory, ExecutionScope

__all__ = ["AsynchronousExecutionContext", "context"]


# TODO: find a better name
class AsynchronousExecutionContext:
    """ A tree of async instructions to run on the same loop and some metadata """

    def __init__(self):
        self.main = None

    def run_with_main(self) -> Callable:
        """ Run this function as the main entry point of the asyncio program """

        def decorator(main_func: Coroutine) -> Coroutine:
            """ Execute current context with the given coutine as the main function """
            self.main = main_func
            self.run()
            return main_func

        return decorator

    def run(self) -> None:
        """ Start the event loop to execute the main function """
        # TODO: check that the patch has been done ?
        loop = asyncio.get_event_loop()

        async def main_wrapper():
            """ Wrap the main function in a scope and pass the scope to it """
            async with ExecutionScope() as run:
                run.asap(self.main(run))

        loop.run_until_complete(main_wrapper())


def context(loop=None) -> AsynchronousExecutionContext:
    """ Set our custom task factory and create a context object """
    # TODO: check that the task factory hasn't been changed first,
    # and with a thread lock
    loop = loop or asyncio.get_event_loop()
    loop.set_task_factory(ScopedTaskFactory())
    return AsynchronousExecutionContext()
