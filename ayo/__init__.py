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
from ayo.scope import ExecutionScope as scope
from ayo.context import context

# from ayo.utils import gather

__version__ = "0.1.0"

__all__ = ["context", "scope"]
