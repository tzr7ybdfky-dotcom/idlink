"""Bounded discovery and partial-failure reporting use local HTTP fixtures."""

import httpx
import pytest

from idlink.core.collection import collect, linked_seed, plan_seeds
from idlink.core.http import PublicHTTP
from idlink.core.ratelimit import DomainRateLimiter


def test_seed_plan_and_link_recognition() -> None:
    assert plan_seeds("demo", "auto", []) == [("github", "demo")]
    assert plan_seeds("example.org", "auto", ["github:demo"]) == [
        ("website", "example.org"),
        ("github", "demo"),
    ]
    assert linked_seed("https://github.com/demo/repo") is None
    assert linked_seed("https://github.com/demo") == ("github", "demo")
    assert linked_seed("https://127.0.0.1") is None
    for seed, platforms in [("x", "bad"), ("u@example.org", "github"), ("u_name", "github")]:
        with pytest.raises(ValueError):
            plan_seeds(seed, platforms, [])


async def test_collect_follows_only_one_layer() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.host == "example.org":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text='<a rel="me" href="https://github.com/demo">me</a>',
            )
        return httpx.Response(
            200,
            json={
                "login": "demo",
                "html_url": "https://github.com/demo",
                "type": "User",
                "blog": "https://example.net",
            },
        )

    async def sleep(delay: float) -> None:
        pass

    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(sleep=sleep),
    ) as http:
        result = await collect(http, [("website", "example.org")], depth=1)
    assert not result.has_errors
    assert len(result.report.nodes) == 2
    assert len(result.report.edges) == 1
    assert not any("example.net" in call for call in calls)


async def test_habr_partial_failure_is_reported() -> None:
    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(lambda request: httpx.Response(500)),
    ) as http:
        result = await collect(http, [("habr", "demo")], depth=0)
    assert result.has_errors
    assert result.report.nodes == []
    assert "Habr" in result.report.warnings[0]


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://keybase.io/demo", ("keybase", "demo")),
        ("https://news.ycombinator.com/user?id=Demo", ("hackernews", "Demo")),
        ("https://bsky.app/profile/demo.bsky.social", ("bluesky", "demo")),
        ("https://bsky.app/profile/example.org", None),
        ("https://news.ycombinator.com/user?id=demo&id=other", None),
        ("https://keybase.io/docs", None),
        ("https://t.me/demo", None),
    ],
)
def test_recognize_public_api_links(url: str, expected: tuple[str, str] | None) -> None:
    assert linked_seed(url) == expected


async def test_link_discovery_continues_after_missing_profile() -> None:
    """An absent linked account must not prevent a later valid account being fetched."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.host == "example.org":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text='<a rel="me" href="https://keybase.io/missing">me</a>'
                '<a rel="me" href="https://bsky.app/profile/demo.bsky.social">me</a>',
            )
        if request.url.host == "keybase.io":
            return httpx.Response(200, json={"status": {"code": 0}, "them": [None]})
        return httpx.Response(200, json={"handle": "demo.bsky.social", "did": "did:plc:demo"})

    async def sleep(delay: float) -> None:
        pass

    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(sleep=sleep),
    ) as http:
        result = await collect(http, [("website", "example.org")], depth=1)
    assert {n.platform for n in result.report.nodes} == {"website", "bluesky"}
    assert any(c.platform == "keybase" and c.status == "missing" for c in result.report.checks)
    assert not result.has_errors


async def test_domains_probe_concurrently_and_stream_fast_results() -> None:
    """A slow platform must not prevent an independent profile reaching the callback."""
    import asyncio
    from datetime import UTC, datetime
    from unittest.mock import patch

    from idlink.core.models import Profile
    from idlink.plugins.bluesky import BlueskyPlugin
    from idlink.plugins.github import GitHubPlugin

    entered = asyncio.Event()
    fast_reported = asyncio.Event()
    order: list[str] = []

    async def slow(self: GitHubPlugin, username: str) -> Profile:
        entered.set()
        await asyncio.wait_for(fast_reported.wait(), timeout=1)
        return Profile(
            platform="github",
            username=username,
            url="https://github.com/alice",
            fetched_at=datetime.now(UTC),
        )

    async def fast(self: BlueskyPlugin, username: str) -> Profile:
        await entered.wait()
        return Profile(
            platform="bluesky",
            username=username,
            url="https://bsky.app/profile/alice.bsky.social",
            fetched_at=datetime.now(UTC),
        )

    def report(profile: Profile) -> None:
        order.append(profile.platform)
        if profile.platform == "bluesky":
            fast_reported.set()

    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(lambda request: httpx.Response(404)),
    ) as http:
        with patch.object(GitHubPlugin, "fetch", slow), patch.object(BlueskyPlugin, "fetch", fast):
            result = await collect(
                http, [("github", "alice"), ("bluesky", "alice")], depth=0, on_profile=report
            )
    assert order == ["bluesky", "github"]
    assert len(result.report.nodes) == 2
