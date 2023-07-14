from __future__ import annotations

import math
from pyepics_asyncio import Pv
import pytest


@pytest.mark.asyncio
async def test_scalar() -> None:
    output = await Pv.connect("ca:test:ao")
    input = await Pv.connect("ca:test:ai")

    await output.put(math.e)
    assert await input.get() == math.e

    await output.put(math.pi)
    assert await input.get() == math.pi
