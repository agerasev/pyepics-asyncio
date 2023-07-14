from __future__ import annotations

import math
import asyncio
from pyepics_asyncio import Pv, PvMonitor
import pytest


@pytest.mark.asyncio
async def test_scalar() -> None:
    output = await Pv.connect("ca:test:ao")
    input = await Pv.connect("ca:test:ai")

    await output.put(math.e)
    assert await input.get() == math.e

    await output.put(math.pi)
    assert await input.get() == math.pi


@pytest.mark.asyncio
async def test_scalar_monitor() -> None:
    async def monitor(pv: PvMonitor) -> None:
        mon = pv.__aiter__()
        assert await mon.__anext__() == 0.0
        assert await mon.__anext__() == math.e
        assert await mon.__anext__() == math.pi

    output = await Pv.connect("ca:test:ao")
    await output.put(0.0)

    input = await PvMonitor.connect("ca:test:ai")
    task = asyncio.get_running_loop().create_task(monitor(input))

    await output.put(math.e)
    await output.put(math.pi)

    await task
