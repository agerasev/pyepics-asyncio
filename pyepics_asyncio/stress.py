"""
Reproducer for segfault when connecting to multiple PVs concurrently.

Triggers the race between CA thread callbacks (CAC-TCP-recv) and
_Connect._cancel -> epics.PV.disconnect() cleanup from the event loop thread.

Run with: uv run python reproducer.py
Requires the test IOC (ioc/iocBoot/iocTest/st.cmd) to be running.
"""

import asyncio
import gc
import signal
import sys
from pyepics_asyncio import Pv


def handler(signum, frame):
    print("\nInterrupted", file=sys.stderr)
    sys.exit(1)


signal.signal(signal.SIGINT, handler)


async def main():
    pv_name = "ca:test:ai"

    for iteration in range(100000):
        # Create many _Connect futures sharing the same ca._cache entry
        futures = [Pv.connect(pv_name) for _ in range(32)]

        # Cancel half to trigger _cancel -> disconnect() on the shared cache entry
        # while the CA thread is still processing events for the other half
        for i, fut in enumerate(futures):
            if i % 2 == 0:
                fut.cancel()

        # Gather all with timeout to prevent hanging
        results = await asyncio.wait_for(
            asyncio.gather(*futures, return_exceptions=True), timeout=2.0
        )

        successes = sum(1 for r in results if isinstance(r, Pv))
        cancelled = sum(1 for r in results if isinstance(r, asyncio.CancelledError))
        other = sum(
            1
            for r in results
            if isinstance(r, Exception) and not isinstance(r, asyncio.CancelledError)
        )

        if iteration % 100 == 0:
            print(
                f"Iter {iteration:>6}: ok={successes:>2} "
                f"cancelled={cancelled:>2} other={other:>2}"
            )

        gc.collect()


if __name__ == "__main__":
    print("Starting reproducer... (Ctrl+C to stop)")
    asyncio.run(main())
