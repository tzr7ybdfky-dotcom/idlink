"""The bounded continuous pool refills without waiting for a slow previous batch."""

import asyncio
from collections import deque

from idlink.core.collection import _fetch_queue
from idlink.core.models import Profile
from idlink.plugins.base import PlatformPlugin


async def test_slot_is_refilled_and_no_task_leaks() -> None:
    third_started = asyncio.Event()
    active, peak = 0, 0

    class Fixture(PlatformPlugin):
        name = "fixture"

        async def fetch(self, username: str) -> Profile | None:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                if username == "slow":
                    await asyncio.wait_for(third_started.wait(), 1)
                elif username == "third":
                    third_started.set()
                await asyncio.sleep(0)
                return None
            finally:
                active -= 1

    plugins: dict[str, PlatformPlugin] = {"fixture": Fixture()}
    queue = deque(("fixture", name, 0) for name in ("slow", "fast", "third"))
    results = [result async for result in _fetch_queue(plugins, queue, set(), 3, concurrency=2)]
    assert len(results) == 3 and peak == 2 and active == 0


async def test_cancellation_cleans_up_pending_fetches() -> None:
    entered = asyncio.Event()
    exited = asyncio.Event()

    class Fixture(PlatformPlugin):
        name = "fixture"

        async def fetch(self, username: str) -> Profile | None:
            if username == "fast":
                await entered.wait()
                return None
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                exited.set()
            return None

    stream = _fetch_queue(
        {"fixture": Fixture()}, deque([("fixture", "fast", 0), ("fixture", "slow", 0)]), set(), 2
    )
    await anext(stream)
    await stream.aclose()
    assert exited.is_set()
