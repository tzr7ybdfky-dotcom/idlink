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


def test_bulk_plan_includes_public_social_page_checks() -> None:
    assert len(PROBE_SOURCES) > 300
    assert len(plan_seeds("demo", "all", [])) == len(USERNAME_PLATFORMS)
    assert {
        "telegram",
        "instagram",
        "facebook",
        "tiktok",
        "reddit",
        "linkedin",
        "x",
    } <= USERNAME_PLATFORMS
    assert "habr" not in USERNAME_PLATFORMS


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


@pytest.mark.parametrize(
    "label,body,outcome",
    [
        (
            "telegram",
            '<div class="tgme_page_title"><span>Example</span></div>'
            '<a class="tgme_action_button" href="tg://resolve?domain=alice">Open</a>',
            "found",
        ),
        ("telegram", "<title>Telegram Messenger</title>", "missing"),
        (
            "telegram",
            "If you have <strong>Telegram</strong>, you can contact "
            '<a class="tgme_username_link" href="tg://resolve?domain=alice">Alice</a>',
            "missing",
        ),
        ("telegram", "<html>Sign in</html>", "unknown"),
        ("instagram", '{"username":"alice"}', "found"),
        ("instagram", '{"username":"someoneelse"}', "unknown"),
        ("instagram", "Sorry, this page isn't available.", "missing"),
        ("tiktok", '{"uniqueId":"alice"}', "found"),
        ("tiktok", '{"statusCode":10221}', "missing"),
        ("x / twitter", '{"screen_name":"alice"}', "found"),
        (
            "facebook",
            '<meta property="og:type" content="profile">'
            '<meta property="og:url" content="https://www.facebook.com/alice">',
            "found",
        ),
        ("facebook", "<title>Log in to Facebook</title>", "unknown"),
    ],
)
async def test_public_social_pages(label: str, body: str, outcome: str) -> None:
    from idlink.plugins.sherlock import SOCIAL_RULES

    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text=body)

    async def sleep(delay: float) -> None:
        pass

    rule = SOCIAL_RULES[label]
    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(sleep=sleep),
    ) as http:
        plugin = SherlockPlugin(http, label, rule)
        if outcome == "unknown":
            with pytest.raises(PluginError):
                await plugin.fetch("alice")
        else:
            profile = await plugin.fetch("alice")
            assert (profile is not None) == (outcome == "found")
    assert str(calls[-1].url) == rule.url.replace("{}", "alice")
    assert not calls[-1].headers.get("cookie")


async def test_telegram_robots_refusal_prevents_profile_request() -> None:
    from idlink.plugins.sherlock import SOCIAL_RULES

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, text="User-agent: *\nDisallow: /\n")

    async def sleep(delay: float) -> None:
        pass

    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(sleep=sleep),
    ) as http:
        with pytest.raises(PluginError):
            await SherlockPlugin(http, "telegram", SOCIAL_RULES["telegram"]).fetch("alice")
    assert calls == ["/robots.txt"]
