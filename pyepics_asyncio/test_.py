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
    bar = asyncio.Barrier(2)

    async def monitor(pv: PvMonitor) -> None:
        i = 0
        async for value in pv:
            assert value == values[i]
            i += 1
            if i >= len(values):
                break
            await bar.wait()

    output = await Pv.connect("ca:test:ao")
    await output.put(values[0])

    input = await PvMonitor.connect("ca:test:ai")
    task = asyncio.get_running_loop().create_task(monitor(input))

    for value in values[1:]:
        await bar.wait()
        await output.put(value)

    await task


@pytest.mark.asyncio
async def test_array() -> None:
    rng = random.Random(SEED)

    output = await Pv.connect("ca:test:aao")
    input = await Pv.connect("ca:test:aai")

    max_len = output.nelm
    for i in range(0, ATTEMPTS):
        value = [rng.randint(-(2**31), 2**31 - 1) for i in range(0, rng.randint(2, max_len))]
        await output.put(value)
        assert list(await input.get()) == value


@pytest.mark.asyncio
async def test_array_monitor() -> None:
    output = await Pv.connect("ca:test:aao")
    max_len = output.nelm

    rng = random.Random(SEED)
    values = [[rng.randint(-(2**31), 2**31 - 1) for j in range(0, rng.randint(2, max_len))] for i in range(0, ATTEMPTS)]
    bar = asyncio.Barrier(2)

    async def monitor(pv: PvMonitor) -> None:
        i = 0
        async for value in pv:
            assert list(value) == values[i]
            i += 1
            if i >= len(values):
                break
            await bar.wait()

    await output.put(values[0])

    input = await PvMonitor.connect("ca:test:aai")
    task = asyncio.get_running_loop().create_task(monitor(input))

    for value in values[1:]:
        await bar.wait()
        await output.put(value)

    await task
