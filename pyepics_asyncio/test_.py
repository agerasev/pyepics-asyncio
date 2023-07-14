from __future__ import annotations
from typing import List

import random
import asyncio
from pyepics_asyncio import Pv
import pytest

ATTEMPTS = 256
SEED = 0xDEADBEFF
DELAY = 0.01


@pytest.mark.asyncio
async def test_scalar() -> None:
    in_ = await Pv.connect("ca:test:ai")
    out = await Pv.connect("ca:test:ao")

    rng = random.Random(SEED)
    for i in range(0, ATTEMPTS):
        value = rng.gauss(0.0, 1.0)
        await out.put(value)
        assert await in_.get() == value


@pytest.mark.asyncio
async def test_scalar_monitor() -> None:
    in_ = await Pv.connect("ca:test:ai")
    out = await Pv.connect("ca:test:ao")

    rng = random.Random(SEED)
    values = [rng.gauss(0.0, 1.0) for i in range(0, ATTEMPTS)]
    bar = asyncio.Barrier(2)

    async def assert_monitor(pv: Pv) -> None:
        i = 0
        with pv.monitor() as mon:
            assert await mon.__anext__() == 0.0
            await bar.wait()
            async for value in mon:
                assert value == values[i]
                i += 1
                if i >= len(values):
                    break
                await bar.wait()

    await out.put(0.0)
    task = asyncio.get_running_loop().create_task(assert_monitor(in_))

    for value in values:
        await bar.wait()
        await out.put(value)

    await task


@pytest.mark.asyncio
async def test_array() -> None:
    in_ = await Pv.connect("ca:test:aai")
    out = await Pv.connect("ca:test:aao")
    max_len = out.nelm

    rng = random.Random(SEED)
    for i in range(0, ATTEMPTS):
        value = [rng.randint(-(2**31), 2**31 - 1) for i in range(0, rng.randint(2, max_len))]
        await out.put(value)
        assert list(await in_.get()) == value


@pytest.mark.asyncio
async def test_array_monitor() -> None:
    in_ = await Pv.connect("ca:test:aai")
    out = await Pv.connect("ca:test:aao")
    max_len = out.nelm

    rng = random.Random(SEED)
    values = [[rng.randint(-(2**31), 2**31 - 1) for j in range(0, rng.randint(2, max_len))] for i in range(0, ATTEMPTS)]
    bar = asyncio.Barrier(2)

    async def assert_monitor(pv: Pv) -> None:
        i = 0
        with pv.monitor() as mon:
            assert list(await mon.__anext__()) == [0, 0]
            await bar.wait()
            async for value in mon:
                assert list(value) == values[i]
                i += 1
                if i >= len(values):
                    break
                await bar.wait()

    await out.put([0, 0])
    task = asyncio.get_running_loop().create_task(assert_monitor(in_))

    for value in values:
        await bar.wait()
        await out.put(value)

    await task


@pytest.mark.asyncio
async def test_multiple_monitors() -> None:
    loop = asyncio.get_running_loop()

    in_ = await Pv.connect("ca:test:ai")
    out = await Pv.connect("ca:test:ao")

    rng = random.Random(SEED)
    values = [[rng.gauss(0.0, 1.0) for i in range(0, ATTEMPTS)] for k in range(0, 4)]
    bar = asyncio.Barrier(3)

    async def assert_monitor(pv: Pv, values: List[float]) -> None:
        i = 0
        with pv.monitor() as mon:
            x = await mon.__anext__()
            await bar.wait()
            async for value in mon:
                assert value == values[i]
                i += 1
                if i >= len(values):
                    break
                await bar.wait()

    async def skip_barrier(count: int) -> None:
        for i in range(0, count):
            await bar.wait()

    await out.put(0.0)
    await asyncio.sleep(DELAY)

    task0 = loop.create_task(assert_monitor(in_, values[0] + values[1]))
    skip = loop.create_task(skip_barrier(ATTEMPTS))
    for value in values[0]:
        await bar.wait()
        await out.put(value)
    await skip
    await asyncio.sleep(DELAY)

    task1 = loop.create_task(assert_monitor(in_, values[1] + values[2]))
    for value in values[1]:
        await bar.wait()
        await out.put(value)
    await task0
    await asyncio.sleep(DELAY)

    skip = loop.create_task(skip_barrier(ATTEMPTS))
    for value in values[2]:
        await bar.wait()
        await out.put(value)
    await task1
    await skip
    await asyncio.sleep(DELAY)

    task2 = loop.create_task(assert_monitor(in_, values[3]))
    skip = loop.create_task(skip_barrier(ATTEMPTS))
    for value in values[3]:
        await bar.wait()
        await out.put(value)
    await task2
    await skip
    await asyncio.sleep(DELAY)
