"""Only explicit inputs and self-links are accepted."""

import httpx
import pytest

from idlink.core.http import PublicHTTP
from idlink.core.inputs import seed_kind
from idlink.core.ratelimit import DomainRateLimiter
from idlink.plugins.website import WebsitePlugin


@pytest.mark.parametrize(
    "value,kind",
    [
        ("demo", "username"),
        ("example.org", "website"),
        ("user@example.org", "gravatar"),
        ("a" * 64, "gravatar"),
    ],
)
def test_classification(value: str, kind: str) -> None:
    assert seed_kind(value) == kind


@pytest.mark.parametrize(
    "value",
    ["", "user name", "localhost", "host.local", "https://127.0.0.1", "https://example.org/path"],
)
def test_invalid_input(value: str) -> None:
    if value == "localhost":
        assert seed_kind(value) == "username"
    else:
        with pytest.raises(ValueError):
            seed_kind(value)


async def test_only_rel_me_links() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="""
          <meta name="description" content="Astronomy researcher">
          <a rel="me" href="https://github.com/demo">Profile</a>
          <a href="https://github.com/someoneelse">Menu</a>""",
        )

    async def sleep(delay: float) -> None:
        pass

    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(sleep=sleep),
    ) as http:
        profile = await WebsitePlugin(http).fetch("example.org")
    assert profile is not None
    assert profile.outbound_links == frozenset({"https://github.com/demo"})
