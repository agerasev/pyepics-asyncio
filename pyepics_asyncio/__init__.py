from __future__ import annotations
from typing import Any, List, AsyncIterable, AsyncIterator, Awaitable, TypeVar

import asyncio
from asyncio import AbstractEventLoop, Future, Event
from threading import Lock

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

    def get(self) -> _GetFuture:
        return _GetFuture(self)


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


class _GetFuture(Future[Any]):
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

    def __init__(self, pv: PvBase) -> None:
        super().__init__()
        self.raw = pv.raw
        self.raw.add_callback(self._callback)
        self.add_done_callback(_GetFuture._clear)
        self.raw.auto_monitor = epics.dbr.DBE_VALUE


T = TypeVar("T", bound=PvBase)


class _ConnectBase(Future[T]):
    def _cancel(self) -> None:
        self.raw.disconnect()

    def _complete(self) -> None:
        raise NotImplementedError()

    def _connection_callback(self, pvname: str = "", conn: bool = False, **kw: Any) -> None:
        assert pvname == self.name
        if conn:
            self.raw.connection_callbacks.clear()
            assert self.remove_done_callback(_ConnectBase._cancel) == 1
            loop = self.get_loop()
            if not loop.is_closed():
                loop.call_soon_threadsafe(self._complete)

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name
        self.raw = epics.PV.__new__(epics.PV)
        self.add_done_callback(_ConnectBase._cancel)
        self.__init_raw__(self.raw)

    def __init_raw__(self, raw: epics.PV) -> None:
        raise NotImplementedError()


class _Connect(_ConnectBase[Pv]):
    def _complete(self) -> None:
        self.set_result(Pv(self.raw))

    def __init_raw__(self, raw: epics.PV) -> None:
        raw.__init__(
            self.name,
            form="native",
            auto_monitor=False,
            connection_callback=self._connection_callback,
        )


class _ConnectMonitor(_ConnectBase[PvMonitor]):
    def _complete(self) -> None:
        self.set_result(PvMonitor(self.raw, self.values))

    def __init__(self, name: str) -> None:
        self.values = _Monitor(loop=asyncio.get_running_loop())
        super().__init__(name)

    def __init_raw__(self, raw: epics.PV) -> None:
        raw.__init__(
            self.name,
            form="native",
            auto_monitor=epics.dbr.DBE_VALUE,
            connection_callback=self._connection_callback,
            callback=self.values._callback,
        )


class _Monitor(AsyncIterator[Any]):
    def __init__(self, loop: AbstractEventLoop) -> None:
        super().__init__()
        self._loop = loop
        self._event = Event()
        self._lock = Lock()
        self._values: List[Any] = [None, None]

    def _callback(self, value: Any = None, **kw: Any) -> None:
        with self._lock:
            if self._values[0] is None:
                self._values[0] = value
            else:
                self._values[1] = value

        if not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._event.set)

    async def __anext__(self) -> Any:
        while True:
            with self._lock:
                (value, *self._values) = (*self._values, None)
                self._event.clear()
            if value is not None:
                return value
            await self._event.wait()

    def __aiter__(self) -> _Monitor:
        return self
