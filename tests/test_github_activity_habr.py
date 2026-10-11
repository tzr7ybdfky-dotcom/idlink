"""Public event minimization and Habr refusal without network collection."""

import json

import httpx
import pytest

from idlink.core.http import PublicHTTP
from idlink.core.ratelimit import DomainRateLimiter
from idlink.plugins.base import PluginError
from idlink.plugins.github import GitHubPlugin
from idlink.plugins.habr import HabrPlugin


async def test_public_events_deduplicate_and_filter_private() -> None:
    events = [
        {"id": str(i), "created_at": "2026-01-01T05:00:00Z", "public": True} for i in range(30)
    ]
    events.extend(
        [events[0], {"id": "private", "created_at": "2026-01-01T06:00:00Z", "public": False}]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        assert request.url.path.endswith("/events/public")
        return httpx.Response(200, text=json.dumps(events))

    async def sleep(delay: float) -> None:
        pass

    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(sleep=sleep),
    ) as http:
        hist = await GitHubPlugin(http).activity("demo")
    assert sum(hist) == hist[5] == 30
    assert hist[6] == 0


async def test_habr_policy_is_not_a_missing_profile() -> None:
    with pytest.raises(PluginError, match="Habr отключён"):
        await HabrPlugin().fetch("demo")
