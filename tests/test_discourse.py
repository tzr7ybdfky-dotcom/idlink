"""Anonymous forum evidence distinguishes real accounts, absence and access failures."""

import httpx
import pytest

from idlink.core.http import PublicHTTP
from idlink.core.ratelimit import DomainRateLimiter
from idlink.plugins.base import PluginError
from idlink.plugins.discourse import FORUMS, DiscoursePlugin, ForumSource


@pytest.mark.parametrize("forum", FORUMS, ids=[f.name for f in FORUMS])
@pytest.mark.parametrize(
    "status,payload,result",
    [
        (200, {"user": {"id": 12, "username": "Alice"}}, "found"),
        (200, {"user": {"id": -1, "username": "alice"}}, "found"),
        (404, {"error_type": "not_found", "errors": ["Not found"]}, "missing"),
        (404, {"error_type": "invalid_access", "errors": ["Login required"]}, "unverified"),
        (404, {}, "unverified"),
        (200, {"user": {"id": 12, "username": "other"}}, "unverified"),
        (200, {"user": {"id": True, "username": "alice"}}, "unverified"),
        (200, {"user": {"id": 0, "username": "alice"}}, "unverified"),
        (200, {"user": {"username": "alice"}}, "unverified"),
        (200, {"errors": ["Not found"]}, "unverified"),
        (200, "<title>alice</title>", "unverified"),
        (403, {}, "blocked"),
        (429, {}, "blocked"),
        (500, {}, "http"),
    ],
)
async def test_forum_account_evidence(
    forum: ForumSource, status: int, payload: object, result: str
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        assert request.url.path == "/u/alice.json"
        return httpx.Response(status, json=payload)

    async def sleep(delay: float) -> None:
        pass

    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(sleep=sleep),
    ) as http:
        plugin = DiscoursePlugin(http, forum.name, forum.host)
        if result not in {"found", "missing"}:
            with pytest.raises(PluginError) as exc:
                await plugin.fetch("alice")
            assert exc.value.kind == result
        else:
            profile = await plugin.fetch("alice")
            assert (profile is not None) == (result == "found")
            if profile:
                assert profile.url.lower() == f"https://{forum.host}/u/alice"
                assert not profile.bio_tokens
    assert all(not r.headers.get("authorization") for r in calls)
