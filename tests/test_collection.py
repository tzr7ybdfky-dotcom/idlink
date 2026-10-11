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
