# WARNING

While most of the examples work and are unit tested, the API is still moving a lot and we have zero doc. Don't spend too much time on here.


# ayo: High level API for asyncio that integrates well with non ayo code

Ayo let you focus on using asyncio instead of dealing with it. It has shortcuts for common operations, and offer sane tools to do the complicated things. The default behavior is to do most of the boiler plate for you, but you can opt out of anything you want, and take back control, or delegate control to another code that doesn't use ayo.

Among the features:

- Minimal boiler plate setup
- A port of Trio's nurseries, including cancellation. We called them `execution scopes` here.
- Syntaxic sugar for common operations
- Easy time out
- Easy concurrency limit
- Well behaved scheduled tasks

Incomming:

- Helpers to create cancallable callbacks when you run them in executors.
- Mechanisms to react to changing the loop, the loop policy or the task factory. Or a locking mechanism in the future. Not sure yet.
- Protocols that allow async/await.

Each feature is optional but on by default and always at reach when you need them.

ayo does **not** provide a different async system. It embraces asyncio, so you can use ayo inside or above other codes that use asyncio. It's completly compatible with asyncio and requires zero rewrite or lock in. You can mix ayo and pure asyncio code transparently.

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
import asyncio

@ayo.run_as_main()
async def main(run):
    await asyncio.sleep(3)
    print('Hello !')
```

`run` here, is the root execution scope of your program. It's what set the boundaries in which your tasks can execute safely: tasks you run inside the scope are guaranteed to be done outside of the scope. You can create and nest as many scopes as you need.

To learn about how this works, follow the tutorial.

To learn about how you can still use regular asyncio code, opt out of the autorun, use an already running even loop or get the ayo event loop back, read the dedicated part of the documentation.

## Execution scope (aka Trio's nursery)

Execution scopes are a tool to give you garanties about you concurrent tasks:

```python

import random
import asyncio

import ayo

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

@ayo.run_as_main()
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

Some code will block the event loop for a long time, preventing your tasks to execute. This can happen if the code is doing very long heavy calculations, or wait for I/O without using asyncio.

Such code may be doing file processing, database querying, using the urllib, smtp or requests modules, etc.

In that case, you can put the blocking code in a function, and pass it to `aside()`:

```python
ayo.aside(callback, foo, bar=1)
```

This will call `callback(foo, bar=1)` in the default asyncio executor, which, if you haved changed done anything, will be a `ThreadPoolExcecutor` with `(os.cpu_count() or 1) * 5` workers. It's similar to `asyncio.get_event_loop().run_in_executor(None, lambda: callback(foo, bar=1))`, but binds the task to the current scope like `asap()`.

What this mean, is that the blocking code with not lock your event loop anymore.

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

**Be careful!**

Tasks scheduled with `aside()` are NOT included in the limit of `max_concurrency`. Indeed, only tasks running in the event loop are limited by `max_concurrency`. Tasks scheduled by `aside()` and `aside_in()` are running in an executor.

Executors are "objects executing things", so they potentially could do anything, but in practice, they are mainly doing either:

- a thread pool
- a process pool

So your tasks will run in a separate thread or process. If they run in a thread, they won't block I/O, but will share the CPU ressources. If they run in another process, they may run on another CPU but will consume more memory and take longer to be sent back and forth.

Concurrency in that case, is limited by the number of workers.

If you just use `aside()`, it will use the default executor, and if you didn't setup anything, the default executor for the default asyncio loop is a thread pool with `(os.cpu_count() or 1) * 5` workers.


## Scheduled tasks

```python

import ayo

import datetime as dt

@ayo.run_as_main()
async def main(run):
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

import ayo

import datetime as dt

@ayo.run_as_main()
async def main(run):
    run.after(2, callback, foo, bar=1).dont_hold_exit()
    run.at(dt.datetime(2018, 12, 1), callback, foo, bar=1).dont_hold_exit()
    run.every(0.2, callback, foo, bar=1).dont_hold_exit()
```

## Saving RAM

If you use `max_concurrency` with a low value but attach a lot of coroutines to your scope, you will have many coroutines objects eating up RAM but not actually being scheduled.

For this particular case, if you want to save up memory, you can use `Scope.from_callable()`:


```python
import asyncio

import ayo

async def zzz(seconds):
    await asyncio.sleep(seconds)
    print(f'Slept for {seconds} seconds')

@ayo.run_as_main()
async def main(run_in_top):

    async with ayo.scope(max_concurrency=10) as run:
        # A lot of things in the waiting queue, but only 10 can execute at the
        # same time, so most of them do nothing and eat up memory.
        for _ in range(10000):
            # Pass a callable here (e.g: function), not an awaitable (e.g: coroutine)
            # So do:
            run.from_callable(zzz, 0.01)
            # But NOT:
            # run.from_callable(zzz(0.01))
```

The callable must always return an awaitable. Any `async def` function reference will hence naturally be accepted.

`run.from_callable()` will store the reference of the callable and its parameters, and only call it to get the awaitable at the very last moment. If you use a lot of similar combinaisons of
callables and parameters, this will store only references to them instead of a new coroutine object
everytime. This can add up to a lot of memory.

This feature is mostly for this specific case, and you should not bother with it unless you
are in this exact situation.

Another use case would be if you want to dynamically create the awaitable at the last minute from a
factory.

## Playing well with others

### Just do as usual for simple cases

Most asyncio code hook on the currently running loop, and so can be used as is. Example with aiohttp client:

```python

import ayo

import aiohttp

URLS = [
    "https://www.python.org/",
    "https://pypi.python.org/",
    "https://docs.python.org/"
]

# Regular aiohttp code that send HTTP GET a URL and print the size the response
async def fetch(url):
    async with aiohttp.request('GET', 'http://python.org/') as resp:
        print(url, "content size:", len(await response.text()))

@ayo.run_as_main()
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

async def main():
    with ayo.scope as run():
        await run.sleep(3)
        print('Hello !')

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
```

`ayo` doesn't need a main function to run, it's just a convenient wrapper. It also ensure all your code run in a scope, while you do not have this guaranty if you do everything manuelly.

To learn more about the tradeoff, read the dedicated part of the documentation.

### React to life cycle hooks

ayo provide several hooks on which you can plug your code to react to things like the `main()` function starting or stopping, the current event loop stopping, or closing, etc. Example, running a countown just before leaving:

```python

import asyncio

import ayo

@ayoc.on.stopping()
async def the_final_count_down(run):
    for x in (3, 2, 1):
        asyncio.sleep(1)
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

# TODO

- Figure out a good story to facilitate multi-threading and enforce good practices
- Figure out a good story to facilitate signal handling
- Help on the integration with trio, twisted, tornado, qt, wx and tkinter event loops
- Create helpers for popular libs. Example: aiohttp session could be also a scope, a helper for aiohttp.request...
- Fast fail mode for when `run_until_complete()` is in used.

