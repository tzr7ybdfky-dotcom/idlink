"""Public Bluesky profiles require an exact handle; blocked access is never absence."""

import httpx
import pytest

from idlink.core.http import PublicHTTP
from idlink.core.ratelimit import DomainRateLimiter
from idlink.plugins.base import PluginError
from idlink.plugins.bluesky import BlueskyPlugin


@pytest.mark.parametrize(
    "status,payload,result",
    [
        (
            200,
            {
                "did": "did:plc:demo",
                "handle": "demo.bsky.social",
                "description": "https://github.com/demo",
            },
            "found",
        ),
        (400, {"error": "ProfileNotFound"}, "missing"),
        (400, {"error": "InvalidRequest"}, "error"),
        (200, {"did": "did:plc:other", "handle": "other.bsky.social"}, "error"),
        (200, {"message": "challenge"}, "error"),
        (429, {"error": "RateLimitExceeded"}, "error"),
    ],
)
async def test_exact_handle(status: int, payload: object, result: str) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(status, json=payload)

    async def sleep(delay: float) -> None:
        pass

    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(sleep=sleep),
    ) as http:
        plugin = BlueskyPlugin(http)
        if result == "error":
            with pytest.raises(PluginError):
                await plugin.fetch("demo")
        else:
            profile = await plugin.fetch("demo")
            assert (profile is not None) == (result == "found")
            if profile:
                assert profile.url == "https://bsky.app/profile/demo.bsky.social"
                assert profile.outbound_links == frozenset({"https://github.com/demo"})
    assert len(calls) == 2
    assert calls[-1].url.params["actor"] == "demo.bsky.social"
    assert "authorization" not in calls[-1].headers
