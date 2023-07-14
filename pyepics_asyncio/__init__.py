from __future__ import annotations
from typing import Any, List, AsyncIterable, AsyncIterator, Awaitable

import asyncio
from asyncio import AbstractEventLoop, Future, Event
from threading import Lock

import epics  # type: ignore


class Pv(AsyncIterable[Any]):
    "Process variable"

    def __init__(self, raw: epics.PV) -> None:
        self.raw = raw

    @property
    def name(self) -> str:
        assert isinstance(self.raw.pvname, str)
        return self.raw.pvname

    @property
    def nelm(self) -> int:
        assert isinstance(self.raw.nelm, int)
        return self.raw.nelm

    @staticmethod
    def connect(name: str) -> Awaitable[Pv]:
        return _Connect(name)

    def put(self, value: Any) -> Awaitable[None]:
        return _Put(self, value)

    def get(self) -> Awaitable[Any]:
        return _Get(self)

    def monitor(self) -> AsyncIterator[Any]:
        return _Monitor(self.raw)

    def __aiter__(self) -> AsyncIterator[Any]:
        return self.monitor()


class _Connect(Future[Pv]):
    def _cancel(self) -> None:
        self.raw.disconnect()

    def _complete(self) -> None:
        self.set_result(Pv(self.raw))

    def _connection_callback(self, pvname: str, conn: bool = False, **kw: Any) -> None:
        assert pvname == self.name
        if conn:
            self.raw.connection_callbacks.clear()
            assert self.remove_done_callback(_Connect._cancel) == 1
            loop = self.get_loop()
            if not loop.is_closed():
                loop.call_soon_threadsafe(self._complete)

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name
        self.add_done_callback(_Connect._cancel)
        self.raw = epics.PV.__new__(epics.PV)
        self.raw.__init__(
            self.name,
            form="native",
            auto_monitor=False,
            connection_callback=self._connection_callback,
        )


class _Put(Future[None]):
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


class _Get(Future[Any]):
    def _complete(self, value: Any) -> None:
        if not self.done():
            self.set_result(value)

    def _clear(self) -> None:
        self.raw.clear_auto_monitor()
        self.raw.clear_callbacks()

    def _callback(self, value: Any, **kw: Any) -> None:
        self._clear()
        loop = self.get_loop()
        if not loop.is_closed():
            loop.call_soon_threadsafe(lambda: self._complete(value))

    def __init__(self, pv: Pv) -> None:
        super().__init__()
        self.raw = pv.raw
        self.raw.add_callback(self._callback)
        self.add_done_callback(_Get._clear)
        self.raw.auto_monitor = epics.dbr.DBE_VALUE


class _Monitor(Pv, AsyncIterator[Any]):
    "Process variable with monitor"

    def _callback(self, value: Any, **kw: Any) -> None:
        with self._lock:
            if self._values[0] is None:
                self._values[0] = value
            else:
                self._values[1] = value
            loop = self._loop

        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._event.set)

    def __init__(self, raw: epics.PV) -> None:
        self._loop: AbstractEventLoop | None = None
        self._event = Event()
        self._lock = Lock()
        self._values: List[Any] = [None, None]
        super().__init__(raw)
        self.raw.add_callback(self._callback)
        self.raw.auto_monitor = epics.dbr.DBE_VALUE

    async def get(self) -> Any:
        return self.raw.get(use_monitor=True)

    async def __anext__(self) -> Any:
        while True:
            with self._lock:
                self._loop = asyncio.get_running_loop()
                (value, *self._values) = (*self._values, None)
                self._event.clear()
            if value is not None:
                return value
            await self._event.wait()

    def __aiter__(self) -> _Monitor:
        return self
