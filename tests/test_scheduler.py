"""The bounded continuous pool refills without waiting for a slow previous batch."""

import asyncio
from collections import deque

import pytest

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


async def test_source_deadline_cancels_wait_and_frees_slot() -> None:
    from idlink.plugins.base import PluginError

    cancelled = asyncio.Event()

    class Fixture(PlatformPlugin):
        name = "fixture"

        async def fetch(self, username: str) -> Profile | None:
            if username == "slow":
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
            return None

    results = [
        item
        async for item in _fetch_queue(
            {"fixture": Fixture()},
            deque([("fixture", "slow", 0), ("fixture", "fast", 0)]),
            set(),
            2,
            concurrency=1,
            check_timeout=0.01,
        )
    ]
    assert cancelled.is_set()
    error = results[0][3]
    assert isinstance(error, PluginError) and error.kind == "timeout"
    assert results[1][1] == "fast" and results[1][3] is None


async def test_long_crawl_delay_is_skipped_without_early_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    from idlink.core.catalog import PROBE_SOURCES
    from idlink.core.collection import collect
    from idlink.core.http import PublicHTTP
    from idlink.core.ratelimit import DomainRateLimiter
    from idlink.plugins.sherlock import ProbeRule

    calls: list[str] = []
    waiting = asyncio.Event()
    monkeypatch.setitem(
        PROBE_SOURCES,
        "fixture",
        ProbeRule(
            label="fixture",
            url="https://fixture.example/{}",
            probe="https://fixture.example/{}",
            kind="status_code",
        ),
    )

    async def sleep(delay: float) -> None:
        assert delay >= 120
        waiting.set()
        await asyncio.Event().wait()

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, text="User-agent: *\nCrawl-delay: 120\n")

    async with PublicHTTP(
        "https://example.org/idlink",
        timeout=0.01,
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(clock=lambda: 0, sleep=sleep),
    ) as http:
        result = await asyncio.wait_for(collect(http, [("fixture", "alice")], depth=0), 1)
    assert waiting.is_set()
    assert calls == ["/robots.txt"]
    assert result.has_errors and not result.report.nodes
    assert result.report.checks[0].error_kind == "timeout"
