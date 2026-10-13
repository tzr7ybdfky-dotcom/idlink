"""Regression checks for contextual errors and safe canonical redirects."""

import httpx
import pytest

from idlink.core.http import PublicHTTP
from idlink.core.ratelimit import DomainRateLimiter
from idlink.plugins.base import PluginError
from idlink.plugins.evidence import absence_marker, identifies_profile, soft_404
from idlink.plugins.pages import canonical_redirect, public_page


@pytest.mark.parametrize(
    "body,markers,missing",
    [
        ('<script>const x="User not found";</script><h1>alice</h1>', ["User not found"], False),
        ('<meta property="og:site_name" content="Example"><h1>alice</h1>', ["og:site_name"], False),
        ("<h1>User not found</h1>", ["User not found"], True),
        ('{"statusCode":{"code":404},"note":"missing"}', ["missing"], False),
        ('{"statusCode":10221,"note":"missing"}', ["missing"], True),
        ('{"error":"rate limit exceeded"}', ['"error"'], False),
        ('{"error":"authentication required"}', ['"error"'], False),
        ('{"error":"user not found"}', ['"error"'], True),
    ],
)
def test_contextual_absence(body: str, markers: list[str], missing: bool) -> None:
    assert absence_marker(body, markers) is missing


def test_inline_error_template_does_not_hide_a_profile() -> None:
    body = '<script>const error="<title>404</title>";</script><h1>alice</h1>'
    assert not soft_404(body)
    assert identifies_profile(body, "alice", "https://example.org/alice")


def test_product_name_is_not_an_account_username() -> None:
    body = '{"id":"123456789abcdef0123456789abcdef0","name":"alice"}'
    assert not identifies_profile(body, "alice", "https://example.org/alice")
    assert identifies_profile(
        body, "alice", "https://api.mojang.com/users/profiles/minecraft/alice"
    )


@pytest.mark.parametrize(
    "target,allowed",
    [
        ("/alice/", True),
        ("https://www.example.org/alice", True),
        ("/login", False),
        ("https://other.example.org/alice", False),
        ("http://example.org/alice", False),
        ("https://user:password@example.org/alice", False),
        ("/alice?login=1", False),
        ("https://example.org:bad/alice", False),
    ],
)
def test_redirect_scope(target: str, allowed: bool) -> None:
    assert (canonical_redirect("https://example.org/alice", target) is not None) is allowed


async def test_canonical_hop_keeps_request_spacing() -> None:
    now = [0.0]
    starts: list[float] = []

    async def sleep(delay: float) -> None:
        now[0] += delay

    def handler(request: httpx.Request) -> httpx.Response:
        starts.append(now[0])
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/alice":
            return httpx.Response(301, headers={"Location": "/alice/"})
        return httpx.Response(200, text="<h1>alice</h1>")

    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(clock=lambda: now[0], sleep=sleep),
    ) as http:
        response = await public_page(http, "https://profiles.example/alice")
        assert response.status_code == 200
        assert str(response.request.url) == "https://profiles.example/alice/"
    assert starts == [0, 2, 4]


async def test_canonical_hop_does_not_bypass_target_robots() -> None:
    seen: list[str] = []

    async def sleep(delay: float) -> None:
        pass

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.host == "www.example.org":
            return httpx.Response(200, text="User-agent: *\nDisallow: /alice\n")
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(301, headers={"Location": "https://www.example.org/alice"})

    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(sleep=sleep),
    ) as http:
        with pytest.raises(PluginError) as exc:
            await public_page(http, "https://example.org/alice")
    assert exc.value.kind == "robots"
    assert seen[-1] == "https://www.example.org/robots.txt"
