"""Public transport refuses local resources and handles decoded HTTP bodies."""

import gzip

import httpx
import pytest

from idlink.core.http import PublicHTTP
from idlink.core.ratelimit import DomainRateLimiter
from idlink.plugins.base import PluginError


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/x",
        "https://localhost/x",
        "https://10.0.0.1/x",
        "https://u:pass@example.org/x",
    ],
)
async def test_private_endpoints_never_reach_transport(url: str) -> None:
    def forbidden(request: httpx.Request) -> httpx.Response:
        raise AssertionError("transport should not run")

    async with PublicHTTP(
        "https://example.org/idlink", transport=httpx.MockTransport(forbidden)
    ) as http:
        with pytest.raises(PluginError):
            await http.get(url)


async def test_gzip_body_not_decoded_twice() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            200, headers={"content-encoding": "gzip"}, content=gzip.compress(b'{"public":true}')
        )

    async def sleep(delay: float) -> None:
        pass

    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(sleep=sleep),
    ) as http:
        response = await http.get("https://example.org/data")
    assert response.json() == {"public": True}
