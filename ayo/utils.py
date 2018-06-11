"""
    Collection of helpers
"""

import asyncio


__all__ = ["TaskList"]


class TaskList(list):
    """ Syntaxic sugar to be able ease mass process of tasks """

    def gather(self) -> asyncio.Task:
        """ Apply asyncio.gather on self"""
        return asyncio.gather(*self)

    # async def as_completed(self):
    #     for task in asyncio.as_completed(self.tasks):
    #         yield (await task)
