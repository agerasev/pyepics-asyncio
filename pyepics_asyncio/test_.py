from __future__ import annotations

import random
import asyncio
from pyepics_asyncio import Pv, PvMonitor
import pytest

ATTEMPTS = 256
SEED = 0xDEADBEFF


@pytest.mark.asyncio
async def test_scalar() -> None:
    rng = random.Random(SEED)

    output = await Pv.connect("ca:test:ao")
    input = await Pv.connect("ca:test:ai")

    for i in range(0, ATTEMPTS):
        value = rng.gauss(0.0, 1.0)
        await output.put(value)
        assert await input.get() == value


@pytest.mark.asyncio
async def test_scalar_monitor() -> None:
    rng = random.Random(SEED)
    values = [rng.gauss(0.0, 1.0) for i in range(0, ATTEMPTS)]

    async def monitor(pv: PvMonitor) -> None:
        i = 0
        async for value in pv:
            assert value == values[i]
            i += 1
            if i >= len(values):
                break

    output = await Pv.connect("ca:test:ao")
    await output.put(values[0])

    input = await PvMonitor.connect("ca:test:ai")
    task = asyncio.get_running_loop().create_task(monitor(input))

    for value in values[1:]:
        await output.put(value)

    await task
