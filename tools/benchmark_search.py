"""Compare old 24-request waves with the continuous pool on identical offline latency fixtures."""

import asyncio
import json
import statistics
import time
from collections import deque

from idlink.core.collection import _fetch_queue
from idlink.core.models import Profile
from idlink.plugins.base import PlatformPlugin


class LatencyFixture(PlatformPlugin):
    """Simulate a missing public page with deterministic latency, without sockets."""

    name = "fixture"

    async def fetch(self, username: str) -> Profile | None:
        await asyncio.sleep(0.09 if int(username) % 24 == 0 else 0.03)
        return None


async def measure(continuous: bool) -> float:
    """Use identical sources and delays for both scheduling strategies."""
    plugins: dict[str, PlatformPlugin] = {str(i): LatencyFixture() for i in range(384)}
    items = [(key, key, 0) for key in plugins]
    start = time.perf_counter()
    if continuous:
        async for _ in _fetch_queue(plugins, deque(items), set(), len(items)):
            pass
    else:
        for offset in range(0, len(items), 24):
            await asyncio.gather(*(plugins[p].fetch(s) for p, s, _ in items[offset : offset + 24]))
    return time.perf_counter() - start


async def main() -> None:
    """Report median timings; this measures scheduling, not real Internet performance."""
    old = statistics.median([await measure(False) for _ in range(3)])
    new = statistics.median([await measure(True) for _ in range(3)])
    print(
        json.dumps(
            {
                "fixture": "384 sources, 30ms normal / 90ms slow, 3 runs, no network",
                "old_seconds": round(old, 4),
                "new_seconds": round(new, 4),
                "speedup": round(old / new, 2),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
