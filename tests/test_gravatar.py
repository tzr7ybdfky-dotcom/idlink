"""Gravatar requests are served only by synthetic fixtures."""

import hashlib
from io import BytesIO

import httpx
import pytest
from PIL import Image

from idlink.core.http import PublicHTTP
from idlink.core.ratelimit import DomainRateLimiter
from idlink.plugins.base import PluginError
from idlink.plugins.gravatar import GravatarPlugin, email_hash


def test_email_hash_normalization() -> None:
    assert email_hash(" USER@example.org ") == hashlib.sha256(b"user@example.org").hexdigest()
    assert email_hash("a" * 32) == "a" * 32
    with pytest.raises(ValueError):
        email_hash("username")


@pytest.mark.parametrize("status", [200, 404, 429])
async def test_gravatar_fetch(status: int) -> None:
    stream = BytesIO()
    Image.new("RGB", (32, 32), "blue").save(stream, format="PNG")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        assert request.url.params["d"] == "404"
        assert "user@example.org" not in str(request.url)
        return httpx.Response(status, content=stream.getvalue())

    async def sleep(delay: float) -> None:
        pass

    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(sleep=sleep),
    ) as http:
        plugin = GravatarPlugin(http)
        if status == 429:
            with pytest.raises(PluginError):
                await plugin.fetch("user@example.org")
        else:
            profile = await plugin.fetch("user@example.org")
            assert (profile is None) == (status == 404)
            if profile is not None:
                assert profile.avatar_phash is not None
                assert not profile.avatar_is_default
