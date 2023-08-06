#!/usr/bin/env python3


import asyncio
from pyepics_asyncio import Pv

N = 1024


async def main() -> None:
    async def get() -> None:
        a = await (await Pv.connect("ca:test:ai")).get()
        b = await (await Pv.connect("ca:test:ao")).get()

    async with asyncio.timeout(10):
        await asyncio.gather(*[get() for i in range(N)])

    print("Ok")


asyncio.run(main())
