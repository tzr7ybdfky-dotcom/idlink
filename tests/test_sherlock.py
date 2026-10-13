"""Existence heuristics never treat challenges or redirects as verified accounts."""

import httpx
import pytest

from idlink.core.catalog import PROBE_SOURCES, USERNAME_PLATFORMS
from idlink.core.collection import collect, plan_seeds
from idlink.core.http import PublicHTTP
from idlink.core.ratelimit import DomainRateLimiter
from idlink.plugins.base import PluginError
from idlink.plugins.sherlock import ProbeRule, SherlockPlugin


@pytest.mark.parametrize(
    "kind,status,body,headers,outcome",
    [
        ("message", 200, "public demo profile", {}, "found"),
        ("message", 200, "User not found", {}, "missing"),
        ("status_code", 200, "public demo profile", {}, "found"),
        ("status_code", 404, "missing", {}, "missing"),
        ("status_code", 200, "<title>Just a moment</title>", {}, "error"),
        ("message", 200, "hcaptcha", {}, "error"),
        ("status_code", 403, "blocked", {}, "error"),
        ("status_code", 429, "backoff", {}, "error"),
        ("response_url", 302, "", {"location": "https://profiles.example/not-found"}, "missing"),
        ("response_url", 302, "", {"location": "https://profiles.example/login"}, "error"),
        ("message", 200, "", {}, "error"),
    ],
)
async def test_rules(
    kind: str, status: int, body: str, headers: dict[str, str], outcome: str
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(status, text=body, headers=headers)

    async def sleep(delay: float) -> None:
        pass

    rule = ProbeRule(
        label="Fixture",
        url="https://profiles.example/{}",
        probe="https://profiles.example/{}",
        kind=kind,
        errors=["User not found"],
        error_url="https://profiles.example/not-found",
    )
    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(sleep=sleep),
    ) as http:
        plugin = SherlockPlugin(http, "fixture", rule)
        if outcome == "error":
            with pytest.raises(PluginError):
                await plugin.fetch("demo")
        else:
            profile = await plugin.fetch("demo")
            assert (profile is not None) == (outcome == "found")
            if profile:
                assert not profile.bio_tokens and not profile.outbound_links
                assert profile.avatar_phash is None
    assert len(calls) == 2
    assert "authorization" not in calls[-1].headers
    assert calls[-1].headers["user-agent"].startswith("idlink/")


def test_bulk_plan_has_over_300_probes_and_keeps_restricted_sources_disabled() -> None:
    assert len(PROBE_SOURCES) > 300
    assert len(plan_seeds("demo", "all", [])) == len(USERNAME_PLATFORMS)
    assert "telegram" not in USERNAME_PLATFORMS
    assert "instagram" not in USERNAME_PLATFORMS


async def test_all_roots_are_checked_beyond_old_16_limit() -> None:
    roots = [("github", f"demo{i}") for i in range(20)]

    async def sleep(delay: float) -> None:
        pass

    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(lambda request: httpx.Response(404)),
        limiter=DomainRateLimiter(sleep=sleep),
    ) as http:
        result = await collect(http, roots, depth=0)
    assert len(result.report.checks) == 20
    assert not result.report.nodes
