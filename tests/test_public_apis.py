"""New anonymous APIs distinguish missing profiles from invalid or blocked responses."""

import json

import httpx
import pytest

from idlink.core.http import PublicHTTP
from idlink.core.ratelimit import DomainRateLimiter
from idlink.plugins.base import PluginError
from idlink.plugins.public_apis import PublicAPIPlugin


@pytest.mark.parametrize(
    "name,payload,expected",
    [
        ("hackernews", {"id": "demo", "about": '<a href="https://github.com/demo">me</a>'}, True),
        ("hackernews", None, False),
        ("keybase", {"status": {"code": 0}, "them": [{"basics": {"username": "demo"}}]}, True),
        ("keybase", {"status": {"code": 0}, "them": [None]}, False),
        ("wikipedia", {"query": {"users": [{"name": "Demo", "userid": 1}]}}, True),
        ("wikipedia", {"query": {"users": [{"name": "Demo", "missing": True}]}}, False),
        ("wikipedia", {"query": {"users": [{"name": "Demo", "invalid": ""}]}}, False),
    ],
)
async def test_exact_public_lookup(name: str, payload: object, expected: bool) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return (
            httpx.Response(404)
            if request.url.path == "/robots.txt"
            else httpx.Response(200, content=json.dumps(payload))
        )

    async def sleep(delay: float) -> None:
        pass

    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(sleep=sleep),
    ) as http:
        profile = await PublicAPIPlugin(http, name, "en.wikipedia.org").fetch("demo")
    assert (profile is not None) == expected
    assert len(calls) == 2
    assert not calls[-1].headers.get("authorization")
    if profile and name == "hackernews":
        assert profile.outbound_links == frozenset({"https://github.com/demo"})


@pytest.mark.parametrize("payload", [{}, {"id": "someoneelse"}])
async def test_malformed_never_means_found(payload: object) -> None:
    async def sleep(delay: float) -> None:
        pass

    async with PublicHTTP(
        "https://example.org/idlink",
        limiter=DomainRateLimiter(sleep=sleep),
        transport=httpx.MockTransport(
            lambda r: httpx.Response(404 if r.url.path == "/robots.txt" else 200, json=payload)
        ),
    ) as http:
        with pytest.raises(PluginError):
            await PublicAPIPlugin(http, "hackernews").fetch("demo")
