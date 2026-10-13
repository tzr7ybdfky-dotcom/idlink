"""Graph snapshots precede the slowest source, without sockets or persisted profiles."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import patch

import httpx

from idlink.core.http import PublicHTTP
from idlink.core.live import stream_collection
from idlink.core.models import Profile
from idlink.plugins.bluesky import BlueskyPlugin
from idlink.plugins.github import GitHubPlugin


async def test_first_graph_arrives_before_slow_source_finishes() -> None:
    entered, graph_visible = asyncio.Event(), asyncio.Event()
    events: list[dict[str, object]] = []

    async def slow(self: BlueskyPlugin, username: str) -> None:
        entered.set()
        await asyncio.wait_for(graph_visible.wait(), 1)

    async def fast(self: GitHubPlugin, username: str) -> Profile:
        await entered.wait()
        return Profile(
            platform="github",
            username=username,
            url="https://github.com/alice",
            fetched_at=datetime.now(UTC),
        )

    def emit(event: dict[str, object]) -> None:
        events.append(event)
        if event["type"] == "progress" and "report" in event:
            graph_visible.set()

    async with PublicHTTP(
        "https://example.org/idlink", transport=httpx.MockTransport(lambda r: httpx.Response(404))
    ) as http:
        with patch.object(GitHubPlugin, "fetch", fast), patch.object(BlueskyPlugin, "fetch", slow):
            report = await stream_collection(
                http, [("github", "alice"), ("bluesky", "alice")], emit, depth=0
            )
    assert graph_visible.is_set()
    assert events[0]["type"] == "start" and events[-1]["type"] == "done"
    assert len(report.nodes) == 1 and len(report.checks) == 2
    assert events[-1]["checked"] == 2
    assert "html" in events[-1]
