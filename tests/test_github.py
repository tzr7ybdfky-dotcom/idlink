"""GitHub fixture tests cannot contact the network."""

from pathlib import Path

import httpx
import pytest

from idlink.core.http import PublicHTTP
from idlink.core.ratelimit import DomainRateLimiter
from idlink.plugins.base import PluginError
from idlink.plugins.github import GitHubPlugin


@pytest.mark.parametrize("status", [200, 404, 403, 429, 500, 302])
async def test_fetch(status: int) -> None:
    calls: list[str] = []
    fixture = (Path(__file__).parent / "fixtures/github_user.json").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        assert request.headers["User-Agent"] == "idlink/0.1.0 (+https://example.org/idlink)"
        assert "Authorization" not in request.headers
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(status, content=fixture)

    async def no_sleep(delay: float) -> None:
        pass

    limiter = DomainRateLimiter(sleep=no_sleep)
    async with PublicHTTP(
        "https://example.org/idlink", transport=httpx.MockTransport(handler), limiter=limiter
    ) as http:
        plugin = GitHubPlugin(http)
        if status == 200:
            profile = await plugin.fetch("demo")
            assert profile is not None
            assert "python" in profile.bio_tokens
            assert "https://example.org" in profile.outbound_links
            assert profile.avatar_phash is None
        elif status == 404:
            assert await plugin.fetch("demo") is None
        else:
            with pytest.raises(PluginError):
                await plugin.fetch("demo")
        assert calls == ["/robots.txt", "/users/demo"]
