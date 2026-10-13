"""Every imported rule must reject blocked pages, 404s and reflected catch-all HTML."""

import re

import httpx
import pytest

from idlink.core.catalog import PROBE_SOURCES
from idlink.core.http import PublicHTTP
from idlink.core.ratelimit import DomainRateLimiter
from idlink.plugins.base import PluginError
from idlink.plugins.sherlock import ProbeRule, SherlockPlugin

CANDIDATES = (
    "alice",
    "Alice",
    "testuser",
    "test_user",
    "test1234",
    "test-user",
    "testuser12345678",
    "123456789",
    "123456789abcdef0",
    "alice@example.org",
    "0000-0002-1825-0097",
    "a",
)


@pytest.mark.parametrize("name,rule", list(PROBE_SOURCES.items()), ids=list(PROBE_SOURCES))
@pytest.mark.parametrize("status", [200, 404, 403])
async def test_catalog_never_reports_missing_blocked_or_catch_all_pages(
    name: str,
    rule: ProbeRule,
    status: int,
) -> None:
    seed = next(
        (
            candidate
            for candidate in CANDIDATES
            if not rule.pattern or re.fullmatch(rule.pattern, candidate)
        ),
        None,
    )
    if seed is None:
        pytest.skip("No valid synthetic handle for this platform's specialised format")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        # These headings intentionally echo the requested route for any handle.
        body = f'<title>{seed}</title><link rel="canonical" href="{request.url}">'
        return httpx.Response(status, text=body)

    async def sleep(delay: float) -> None:
        pass

    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(sleep=sleep),
    ) as http:
        try:
            profile = await SherlockPlugin(http, name, rule).fetch(seed)
        except PluginError:
            return
        assert profile is None
