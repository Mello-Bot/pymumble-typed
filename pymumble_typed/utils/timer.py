from __future__ import annotations

from asyncio import sleep, create_task, BaseEventLoop
from typing import Callable, Optional


class AsyncTimer:
    def __init__(self, interval: float, function: Callable, loop: Optional[BaseEventLoop], *args, **kwargs):
        self._interval = interval
        self._function = function
        self._loop = loop
        self._args = args
        self._kwargs = kwargs
        self._task = None
        self._finished = False
        self._timer_expired = False

    @property
    def finished(self):
        return self._finished

    def start(self):
        return self._loop.create_task(self._start(), name=self.__class__.__name__)

    async def _start(self):
        print("Sleeping", self._interval)
        await sleep(self._interval)
        self._timer_expired = True
        if self._args and self._kwargs:
            await self._function(*self._args, **self._kwargs)
        elif self._kwargs:
            await self._function(**self._kwargs)
        elif self._args:
            await self._function(*self._args)
        else:
            await self._function()
        self._finished = True

    def cancel(self):
        if self._task and not self._timer_expired:
            self._task.cancel()
