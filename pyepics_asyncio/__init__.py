from __future__ import annotations
from typing import Any, AsyncIterable, AsyncIterator, Awaitable, TypeVar

import asyncio
from asyncio import AbstractEventLoop, Future, Queue

import epics  # type: ignore


class PvBase:
    def __init__(self, raw: epics.PV) -> None:
        self.raw = raw

    def put(self, value: Any) -> _PutFuture:
        return _PutFuture(self, value)

    @property
    def name(self) -> str:
        assert isinstance(self.raw.pvname, str)
        return self.raw.pvname

    @property
    def nelm(self) -> int:
        assert isinstance(self.raw.nelm, int)
        return self.raw.nelm


class Pv(PvBase):
    "Process variable"

    @staticmethod
    def connect(name: str) -> Awaitable[Pv]:
        return _Connect(name)

    async def get(self) -> Any:
        def caget() -> Any:
            return self.raw.get(use_monitor=False)

        await asyncio.get_running_loop().run_in_executor(None, caget)


class PvMonitor(PvBase, AsyncIterable[Any]):
    "Process variable with monitor"

    def __init__(self, raw: epics.PV, monitor: _Monitor) -> None:
        super().__init__(raw)
        self._monitor = monitor

    @staticmethod
    def connect(name: str) -> Awaitable[PvMonitor]:
        return _ConnectMonitor(name)

    def get(self) -> Any:
        return self.raw.get(use_monitor=True)

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._monitor


class _PutFuture(Future[None]):
    def _complete(self) -> None:
        if not self.done():
            self.set_result(None)

    def _callback(self, **kw: Any) -> None:
        loop = self.get_loop()
        if not loop.is_closed():
            loop.call_soon_threadsafe(self._complete)

    def __init__(self, pv: PvBase, value: Any) -> None:
        super().__init__()
        pv.raw.put(value, wait=False, callback=self._callback)


T = TypeVar("T", bound=PvBase, covariant=True)


class _ConnectBase(Future[T]):
    def _cancel(self) -> None:
        self.raw.disconnect()

    def _complete(self) -> None:
        raise NotImplementedError()

    def _connection_callback(self, pvname: str = "", conn: bool = False, **kw: Any) -> None:
        assert pvname == self.name
        if conn:
            assert self.remove_done_callback(_ConnectBase._cancel) == 1
            loop = self.get_loop()
            if not loop.is_closed():
                loop.call_soon_threadsafe(self._complete)

    def __init__(self, name: str, raw: epics.PV) -> None:
        super().__init__()
        self.name = name
        self.raw = raw
        self.add_done_callback(_ConnectBase._cancel)


class _Connect(_ConnectBase[Pv]):
    def _complete(self) -> None:
        self.set_result(Pv(self.raw))

    def __init__(self, name: str) -> None:
        super().__init__(
            name,
            epics.PV(
                name,
                form="native",
                auto_monitor=False,
                connection_callback=self._connection_callback,
            ),
        )


class _ConnectMonitor(_ConnectBase[PvMonitor]):
    def _complete(self) -> None:
        self.set_result(PvMonitor(self.raw, self.values))

    def __init__(self, name: str) -> None:
        self.values = _Monitor(loop=asyncio.get_running_loop())
        super().__init__(
            name,
            epics.PV(
                name,
                form="native",
                auto_monitor=epics.dbr.DBE_VALUE,
                connection_callback=self._connection_callback,
                callback=self.values._callback,
            ),
        )


class _Monitor(AsyncIterator[Any]):
    def __init__(self, loop: AbstractEventLoop) -> None:
        super().__init__()
        self._loop = loop
        self._queue: Queue[Any] = Queue()

    def _callback(self, value: Any = None, **kw: Any) -> None:
        if not self._loop.is_closed():
            self._loop.call_soon_threadsafe(lambda: self._queue.put_nowait(value))

    async def __anext__(self) -> Any:
        return await self._queue.get()

    def __aiter__(self) -> _Monitor:
        return self
