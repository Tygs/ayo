# WARNING

This project is empty. Don't try it


# ayo: High level API for asyncio that integrates well with non ayo code

Ayo let you focus on using asyncio instead of dealing with it. It has shortcuts for common operations, and offer sane tools to do the complicated things. The default behavior is to do most boiler plate for you, but you can opt out of anything you want, and take back control, or delegate control to another code that doesn't use ayo.

Among the features:

- Minimal boiler plate setup
- A port of Trio's nurseries, including cancellation
- Syntaxic sugar for common operations
- Easy time out
- Easy concurrency limit
- Well behaved scheduled tasks
- A proposed structure for your asyncio code
- Mechanism to react to code changing the loop or loop policy

Each feature is optional but on by default and always at reach near you need them.

ayo does **not** provide a different async system. It embraces asyncio, so you can use ayo with other asyncio using code.

ayo is **not** a framework. It only makes asyncio easier and safer to use. It does nothing else.

- Documentation: tutorial, index, api, download
- Supported Python : CPython 3.6+
- Install : `pip install ayo` or download from Pypi
- Licence : MIT
- Source code : `git clone http://github.com/tygs/ayo`

# Examples

## Hello world

```python
import ayo

ayoc = ayo.context()

@ayoc.run_with_main()
async def main(run):
    await run.sleep(3)
    print('Hello !')
```

`run` here, is the root scope of your program. It's what set the boundaries in which your tasks can execute safely. You can create and nest as many scopes as you need.

To learn about how this works, follow the tutorial.

To learn about how you can still use regular asyncio code, opt out of the autorun, use an already running even loop or get the ayo event loop back, read the dedicated part of the documentation.

## Execution scope (aka Trio's nursery)

Execution scopes are a tool to give you garanties about you concurrent tasks:

```python

import random
import asyncio

async def zzz():
    time = random.randint(0, 15)
    await asyncio.sleep(time)
    print(f'Slept for {time} seconds')

async with ayo.scope(max_concurrency=10, timeout=12) as run:
    for _ in range(20):
        run << zzz() # schedule the coroutine for execution
```

Here, no more than 10 tasks will be run in parallel in this scope, which is delimited by the `async with` block. If an exception is raised in any task of this scope, all the tasks in the same scope are cancelled, then the exception bubbles out of the `with` block like in regular Python code. If no exception is raised, after 12 seconds, if some tasks are still running, they are cancelled and the `with` block exits.

Any code *after* the `with` block is guaranteed to happend *only* after all the tasks are completed or cancelled. This is one of the benefits of execution scopes. To learn more about the execution scopes, go to the dedicated part of documentation.

ayo also comes with a lot of short hands. Here you can see `run << stuff()` which is just syntaxic sugar for `run.asap(stuff())`. And `run.asap(stuff())` is nothing more than a safer version of `asyncio.ensure_future(stuff())` restricted to the current scope.

The running a bunch of task is a common case, and so we provide a shorter way to express it:

```python
async with ayo.scope() as run:
    run.all(zzz(), zzz(), zzz())
```

And you can cancel all tasks running in this scope with by calling `run.cancel()`.

Learn more in the dedicated part of the documentation.

## A more advanced example

```python
import ayo

ayoc = ayo.context()

@ayoc.run_with_main()
async def main(run_in_top):

    print('Top of the program')
    run_in_top << anything()

    async with ayo.scope() as run:
        for stuff in stuff_to_do:
            print('Deeper into the program')
            run << stuff()

        async with ayo.scope(timeout=0.03) as subrun:
            print('Deep inside the program')
            subrun << foo()
            subrun << bar()

        if subrun.timeout:
            run.cancel()
        else:
            for res in subrun.results:
                print(res)
```

This example have 3 nested scopes: `run_in_top`, `run` and `subrun`.

`foo()` and `bar()` execute concurrently, but have a 0.03 seconds time limit to finish. After that, they get cancelled automatially. Later, in the `else`: we print the results of all the tasks, but only if there was no timeout.

All `stuff()` execute concurrently with each others, they start before `foo()` and `bar()`, execute concurrently with them too, and keep executing after them. However, in the `if` clause, we check if `subrun` has timed out, and if yes, we cancel all the tasks in `run`.

`anything()` starts before the tasks in `run`, execute concurrently to them, and continue to execute after them.

The whole program ends when `run` (or `anything()`, since it's the only task in `run`) finishes or get cancelled (e.g: if the user hit ctrl + c).

This example illustrate the concepts, but can't be executed. For fully functional and realistics examples, check out the example directory in the source code.

## Executing blocking code

```python
ayo.aside(callback, foo, bar=1)
```

This will call `callback(foo, bar=1)` in the default asyncio executor, which, if you haved changed done anything, will be a `ThreadPoolExcecutor`. It's similar to `asyncio.get_event_loop().run_in_executor(func, functools.partial(callback, foo, bar=1))`, but binds the task to the current scope.

You can also choose a different executor doing:

```python
ayo.aside_in(executor, callback, foo, bar=1)
```

or:

```python
ayo.aside_in('notifications', callback, foo, bar=1)
```

Provided you created an executor named 'notifications' with ayo before that.

Learn more about handling blocking code in the dedicated part of the documentation.

## Scheduled tasks

```python

import datetime as dt

async with ayo.scope() as run:
    run.after(2, callback, foo, bar=1)
    run.at(dt.datetime(2018, 12, 1), callback, foo, bar=1)
    run.every(0.2, callback, foo, bar=1)
```

`run.after(2, callback, foo, bar=1)` calls `callback(foo, bar=1)` after 2 seconds.

`run.at(dt.datetime(2018, 12, 1), callback, foo, bar=1)` calls `callback(foo, bar=1)` after december 1st, 2018.

`run.every(0.2, callback, foo, bar=1)` calls `callback(foo, bar=1)` every 200ms again and again.

There is no task queue and no task peristence. We only use `asyncio` mechanisms. This also means the timing is limited to the precision provided by `asyncio`.

Learn more about scheduled tasks in the dedicated part of the documentation.

**Be careful!**

The scope will exit only when all tasks have finished or have been cancelled. If you set a task far away in the future, the `with` will stay active until then. If you set a recurring task, the `with` will stay active forever, or until you stop the task manually with `unschedule()` or `cancel()`.

If it's a problem, use `dont_hold_exit()`:

```python

import datetime as dt

async with ayo.scope() as run:
    run.after(2, callback, foo, bar=1).dont_hold_exit()
    run.at(dt.datetime(2018, 12, 1), callback, foo, bar=1).dont_hold_exit()
    run.every(0.2, callback, foo, bar=1).dont_hold_exit()
```

## Playing well with others

### Just do as usual for simple cases

Most asyncio code hook on the currently running loop, and so can be used as is. Example with aiohttp client:

```python

import ayo

ayoc = ayo.context()

URLS = [
    "https://www.python.org/",
    "https://pypi.python.org/",
    "https://docs.python.org/"
]

# Regular aiohttp code that send HTTP GET a URL and print the size the response
async def fetch(url):
    async with aiohttp.request('GET', 'http://python.org/') as resp:
        print(url, "content size:", len(await response.text()))

@ayoc.run_with_main()
async def main(run):
    # Just run your coroutine in the scope and you are good to go
    for url in URLS:
        run << fetch(url)

    # or use run.map(fetch, URLS)
```

This code actually works. Try it.

### Giving up the control of the loop

ayo starts the loop for you, but this may not be what you want. This may not be what the rest of the code expects. You can tell ayo to give up the control of the loop life cycle:

```python

import asyncio

import ayo

ayoc = ayo.context()

@ayoc.with_main()
async def main(run):
    await run.sleep(3)
    print('Hello !')

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
```

The `ayoc` context is an awaitable that can be used where you usually pass a coroutine. You can even pass it to `ensure_future()`. Note that if you use `run_forever()`, then exceptions will not halt the program, which can make it harder to debug.

Remember that anything that is execute outside of the ayo context `main()` cannot benefit from any ayo tools : no helpers, no scope, no timeout, no cancellation, and no clear boundaries to limit task execution. You loose all guaranties ayo offers and go back to manually dealing with all asyncio edge cases.

To learn more about the tradeoff, read the dedicated part of the documentation.

**Be careful!**

ayo monkey patch `asyncio.set_event_policy()`. It also installs a custom event loop policy, a custom loop and a custom `task factory`. Here we do it  `ayo.context()`. You usually don't need to know about this, or care. But if you try to do something complicated, or use a library that does, read the dedicated part of the documentation.

### React to life cycle hooks

ayo provide several hooks on which you can plug your code to react to things like the `main()` function starting or stopping, the current event loop stopping, or closing, etc. Example, running a countown just before leaving:

```python

import ayo

ayoc = ayo.context()

@ayoc.on.stopping()
async def the_final_count_down(run):
    for x in (3, 2, 1):
        ayoc.sleep(1)
        print(x)
    print('Good bye !')

@ayoc.run_with_main():
...
```

Available hooks:

- ayo.on.starting: this ayo context main function is going to start.
- ayo.on.started: this ayo context main function has started.
- ayo.on.stopping: this ayo context main function is going to stop.
- ayo.on.stopped: this ayo context main function has stopped.
- ayo.on.loop.started: the current loop for this ayo context has started.
- ayo.on.loop.closed: the current loop for this ayo context has stopped.
- ayo.on.loop.set: the current loop for this ayo context has been set.
- ayo.on.loop.created: a loop has been created the in the current context.
- ayo.on.policy.set: the global loop policy has been set.

By default ayo hooks to some of those, in particular to raise some warnings or exception. E.G: something is erasing ayo's custom loop policy.

You can disable globally or selectively any hook.

To learn more about life cycle hooks, read the dedicated part of the documentation.

### Pluggable code

ayo suggest a certain structure to your code by enforcing the `main()` function as a single entry point, and requiring a waterfall workflow for your tasks by nesting scopes.

Just like you should construct a hierarchy of scopes (and actually, all scopes have helpers to access their children and parent), you may contruct a hierarchy of contexts. A context is just a bag of code with some information, that you attach later to an event loop, but it can exist without an event loop.

If you want to make a reusable bag of code, just use a context:

```python

import ayo

reusable_code = ayo.context()

@reusable_code.with_main()
async def main(run):
    await run.sleep(3)
    print('Hello !')

```

You can plug it later under any other context:

```python

import ayo

from reusable_module import reusable_code

ayoc = ayo.context()

ayoc.attach(reusable_code)

@ayoc.run_with_main()
async def main(run):
    # do whatever you want
```

This will start the `reusable_code` `main()` in function as soon as `aoyc` own `main()` has started and pass it the same scope.

Learn more about writting pluggable code in the dedicated part of the documentation.

# TODO

- Figure out a good story to facilitate multi-threading and enforce good practices
- Figure out a good story to facilitate signal handling
- Help on the integration with trio, twisted, tornado, qt, wx and tkinter event loops
- Create helpers for popular libs. Example: aiohttp session could be also a scope, a helper for aiohttp.request...
- Fast fail mode for when `run_until_complete()` is in used.

