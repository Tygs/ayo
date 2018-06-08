"""
    ayo: High level API for asyncio that integrates well with non ayo code

    Ayo let you focus on using asyncio instead of dealing with it.
    It has shortcuts for common operations, and offer sane tools to do
    the complicated things. The default behavior is to do most boiler plate
    for you, but you can opt out of anything you want, and take back control,
    or delegate control to another code that doesn't use ayo.

    Among the features:

    - Minimal boiler plate setup
    - A port of Trio's nurseries, including cancellation
    - Syntaxic sugar for common operations
    - Easy time out
    - Easy concurrency limit
    - Well behaved scheduled tasks
    - A proposed structure for your asyncio code
    - Mechanism to react to code changing the loop or loop policy

    Each feature is optional but on by default and always
    at reach near you need them.

    ayo does **not** provide a different async system. It embraces asyncio,
     so you can use ayo with other asyncio using code.

    ayo is **not** a framework. It only makes asyncio easier and safer to use.
     It does nothing else.

    - Documentation:
    - Supported Python : CPython 3.6+
    - Install : `pip install ayo` or download from Pypi
    - Licence : MIT
    - Source code : `git clone http://github.com/tygs/ayo`
"""


import asyncio

from asyncio import sleep

from typing import Coroutine, Callable

from ayo.scope import ScopedTaskFactory, Scope

__version__ = "0.1.0"

__all__ = ["context", "sleep", "scope"]


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
            async with Scope() as scp:
                await self.main(scp)

        loop.run_until_complete(main_wrapper())


def context(loop=None) -> AsynchronousExecutionContext:
    """ Set our custom task factory and create a context object """
    # TODO: check that the task factory hasn't been changed first,
    # and with a thread lock
    loop = loop or asyncio.get_event_loop()
    loop.set_task_factory(ScopedTaskFactory())
    return AsynchronousExecutionContext()


scope = Scope  # pylint: disable=C0103
