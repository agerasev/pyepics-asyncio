from __future__ import annotations
from typing import Any, AsyncGenerator, AsyncContextManager

from dataclasses import dataclass

import asyncio
from asyncio import AbstractEventLoop, Future, Queue

import epics  # type: ignore


class Pv:
    def __init__(self, raw: epics.PV) -> None:
        self.raw = raw

    @staticmethod
    def connect(name: str) -> _PvConnectFuture:
        return _PvConnectFuture(name)

    async def get(self) -> Any:
        return self.raw.get(use_monitor=True)

    def put(self, value: Any) -> _PvPutFuture:
        return _PvPutFuture(self, value)

    # By default values are yielded only on update.
    # If you need monitor to also provide current value on start set `current=True`.
    def monitor(self, current: bool = False) -> _PvMonitorContextManager:
        return _PvMonitorContextManager(self, current)

    @property
    def name(self) -> str:
        assert isinstance(self.raw.pvname, str)
        return self.raw.pvname

    @property
    def nelm(self) -> int:
        assert isinstance(self.raw.nelm, int)
        return self.raw.nelm


class _PvConnectFuture(Future[Pv]):
    def _cancel(self) -> None:
        self.pv.disconnect()

    def _complete(self) -> None:
        self.set_result(Pv(self.pv))

    def _connection_callback(self, pvname: str = "", conn: bool = False, **kw: Any) -> None:
        assert pvname == self._name
        if conn:
            assert self.remove_done_callback(_PvConnectFuture._cancel) == 1
            loop = self.get_loop()
            if not loop.is_closed():
                loop.call_soon_threadsafe(self._complete)

    def __init__(self, name: str) -> None:
        super().__init__()

        self._name = name

        self.add_done_callback(_PvConnectFuture._cancel)
        self.pv = epics.PV(
            name,
            form="native",
            auto_monitor=True,
            connection_callback=self._connection_callback,
        )


class _PvPutFuture(Future[None]):
    def _complete(self) -> None:
        if not self.done():
            self.set_result(None)

    def _callback(self, **kw: Any) -> None:
        loop = self.get_loop()
        if not loop.is_closed():
            loop.call_soon_threadsafe(self._complete)

    def __init__(self, pv: Pv, value: Any) -> None:
        super().__init__()
        pv.raw.put(value, wait=False, callback=self._callback)


@dataclass
class _PvMonitorGenerator(AsyncGenerator[Any, None]):
    pv: Pv
    loop: AbstractEventLoop

    def __post_init__(self) -> None:
        self._queue: Queue[Any | None] = Queue()
        self._done = False

    def _callback(self, value: Any = None, **kw: Any) -> None:
        if not self.loop.is_closed():
            self.loop.call_soon_threadsafe(lambda: self._queue.put_nowait(value))

    def _cancel(self) -> None:
        self._done = True
        self._queue.put_nowait(None)

    def __aiter__(self) -> AsyncGenerator[Any, None]:
        return self

    async def __anext__(self) -> Any:
        value = await self._queue.get()
        if not self._done:
            assert value is not None
            return value
        else:
            assert value is None
            raise StopAsyncIteration()

    async def aclose(self) -> None:
        self._cancel()

    async def asend(self, value: Any) -> Any:
        return await self.__anext__()

    async def athrow(self, *args: Any, **kw: Any) -> Any:
        return await self.__anext__()


@dataclass
class _PvMonitorContextManager(AsyncContextManager[_PvMonitorGenerator]):
    pv: Pv
    ret_cur: bool
    gen: _PvMonitorGenerator | None = None

    async def __aenter__(self) -> _PvMonitorGenerator:
        assert self.gen is None
        self.gen = _PvMonitorGenerator(self.pv, asyncio.get_running_loop())
        self.pv.raw.add_callback(self.gen._callback)
        if self.ret_cur:
            self.pv.raw.run_callbacks()
        return self.gen

    async def __aexit__(self, *args: Any) -> None:
        assert self.gen is not None
        self.pv.raw.remove_callback(self.gen._callback)
        self.gen = None
