"""Measure complete collection with HTTP, robots, rate limits, deadlines and graph building."""

import asyncio
import json
import statistics
import time
from unittest.mock import patch

import httpx

from idlink.core.catalog import PROBE_SOURCES
from idlink.core.collection import collect
from idlink.core.http import PublicHTTP
from idlink.core.ratelimit import DomainRateLimiter
from idlink.plugins.sherlock import ProbeRule

SCALE = 0.01  # One simulated network second takes 10 milliseconds of wall time.
RULES = {
    f"fixture-{i}": ProbeRule(
        label=f"Fixture {i}",
        url=f"https://site{i}.example/alice",
        probe=f"https://site{i}.example/alice",
        kind="status_code",
    )
    for i in range(384)
}


async def measure(timeout: float, concurrency: int) -> tuple[float, int, int]:
    """Both runs find the same responsive profiles; offline hosts remain unknown."""

    async def handler(request: httpx.Request) -> httpx.Response:
        index = int(request.url.host.removeprefix("site").removesuffix(".example"))
        if index % 2 == 0:
            await asyncio.sleep(100)  # The request deadline cancels this fixture.
        await asyncio.sleep(0.5 * SCALE)
        return (
            httpx.Response(404)
            if request.url.path == "/robots.txt"
            else httpx.Response(200, json={"id": str(index), "username": "alice"})
        )

    async def sleep(delay: float) -> None:
        await asyncio.sleep(delay * SCALE)

    limiter = DomainRateLimiter(clock=lambda: time.monotonic() / SCALE, sleep=sleep)
    start = time.perf_counter()
    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=limiter,
        timeout=timeout * SCALE,
    ) as http:
        with patch.dict(PROBE_SOURCES, RULES):
            result = await collect(
                http, [(name, "alice") for name in RULES], depth=0, concurrency=concurrency
            )
    return (
        time.perf_counter() - start,
        len(result.report.nodes),
        sum(c.status == "error" for c in result.report.checks),
    )


async def main() -> None:
    """Report medians for previous defaults and new defaults; never use the real network."""
    previous = [await measure(20, 128) for _ in range(3)]
    current = [await measure(6, 256) for _ in range(3)]
    assert {item[1:] for item in previous + current} == {(192, 192)}
    old, new = statistics.median(x[0] for x in previous), statistics.median(x[0] for x in current)
    print(
        json.dumps(
            {
                "fixture": "384 sites, 50% offline, 3 runs, complete pipeline, scaled time",
                "old_seconds": round(old, 4),
                "new_seconds": round(new, 4),
                "speedup": round(old / new, 2),
                "found_both": 192,
                "unknown_both": 192,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
