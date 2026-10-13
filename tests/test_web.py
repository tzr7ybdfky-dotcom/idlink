"""Live UI intent and origin checks run without opening sockets."""

import httpx
import pytest

from idlink.core.catalog import USERNAME_PLATFORMS
from idlink.core.collection import plan_seeds
from idlink.core.http import PublicHTTP
from idlink.core.ratelimit import DomainRateLimiter
from idlink.web import SearchRequest, search_report, trusted_request


def test_all_sources_and_purpose_validation() -> None:
    assert {p for p, _ in plan_seeds("demo", "all", [])} == USERNAME_PLATFORMS
    assert plan_seeds("example.org", "all", []) == [("website", "example.org")]
    assert SearchRequest(seed="demo").mode == "audit"
    assert len(SearchRequest(seed="demo", mode="search").roots()) == len(USERNAME_PLATFORMS)
    assert SearchRequest(seed="user@example.org").roots()[0][0] == "gravatar"
    with pytest.raises(ValueError):
        SearchRequest(seed="demo", platforms="unsupported-source").roots()
    assert len(SearchRequest(seed="demo", mode="search", purpose="Research").roots()) == len(
        USERNAME_PLATFORMS
    )


@pytest.mark.parametrize(
    "host,origin,token,allowed",
    [
        ("127.0.0.1:8765", "http://127.0.0.1:8765", "secret", True),
        ("evil.example:8765", "http://127.0.0.1:8765", "secret", False),
        ("127.0.0.1:8765", "https://evil.example", "secret", False),
        ("127.0.0.1:8765", "http://127.0.0.1:8765", "wrong", False),
    ],
)
def test_loopback_request_guard(host: str, origin: str, token: str, allowed: bool) -> None:
    assert trusted_request(host, origin, token, "secret", 8765) is allowed


async def test_multi_source_search_partial_failure_and_links() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.host == "api.github.com":
            return httpx.Response(
                200,
                json={
                    "login": "demo",
                    "type": "User",
                    "html_url": "https://github.com/demo",
                    "blog": "https://keybase.io/demo",
                },
            )
        if request.url.host == "keybase.io":
            return httpx.Response(
                200,
                json={
                    "status": {"code": 0},
                    "them": [
                        {
                            "basics": {"username": "demo"},
                            "profile": {"bio": "https://github.com/demo"},
                        }
                    ],
                },
            )
        if request.url.host == "hacker-news.firebaseio.com":
            return httpx.Response(429)
        return httpx.Response(200, json={"query": {"users": [{"name": "Demo", "missing": True}]}})

    async def sleep(delay: float) -> None:
        pass

    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(sleep=sleep),
    ) as http:
        report = await search_report(
            http,
            SearchRequest(
                seed="demo",
                mode="search",
                purpose="Research",
                platforms="github,keybase,hackernews",
            ),
        )
    assert len(report.nodes) == 2
    assert {c.status for c in report.checks} == {"found", "error"}
    assert next(iter(report.edges.values())).signals[0].log_lr == 6
    assert any(c.platform == "hackernews" and c.status == "error" for c in report.checks)


def test_server_routes_enforce_origin_and_intent_without_sockets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json
    import re
    from email.message import Message
    from io import BytesIO
    from typing import Any

    import idlink.web as web

    upstream: list[str] = []

    def transport(request: httpx.Request) -> httpx.Response:
        upstream.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            200, json={"login": "demo", "html_url": "https://github.com/demo", "type": "User"}
        )

    async def sleep(delay: float) -> None:
        pass

    def client(repository: str, *, timeout: float = 6.0) -> PublicHTTP:
        return PublicHTTP(
            repository,
            transport=httpx.MockTransport(transport),
            limiter=DomainRateLimiter(sleep=sleep),
        )

    class FakeServer:
        def __init__(self, address: object, handler: Any) -> None:
            self.handler = handler

        def __enter__(self) -> "FakeServer":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def request(self, method: str, path: str, headers: dict[str, str], body: str = "") -> str:
            instance = self.handler.__new__(self.handler)
            instance.headers = Message()
            for key, value in headers.items():
                instance.headers[key] = value
            instance.path, instance.request_version = path, "HTTP/1.1"
            instance.requestline, instance.command = method + " " + path, method
            output = BytesIO()
            instance.rfile, instance.wfile = BytesIO(body.encode()), output
            getattr(instance, "do_" + method)()
            return output.getvalue().decode()

        def serve_forever(self) -> None:
            page = self.request("GET", "/", {"Host": "127.0.0.1:8765"})
            assert "200 OK" in page and "TikTok" in page and "Telegram" in page
            assert 'const initialSeed = "demo";' in page
            match = re.search(r'const token = "([^"]+)"', page)
            assert match is not None
            headers = {
                "Host": "127.0.0.1:8765",
                "Origin": "http://127.0.0.1:8765",
                "X-idlink-token": match[1],
                "Content-Type": "application/json",
            }
            body = json.dumps({"seed": "demo", "platforms": "unsupported-source"})
            headers["Content-Length"] = str(len(body))
            assert "400 Bad Request" in self.request("POST", "/api/search", headers, body)
            assert not upstream
            body = json.dumps(
                {"seed": "demo", "mode": "search", "platforms": "github", "purpose": "Research"}
            )
            headers["Content-Length"] = str(len(body))
            result = self.request("POST", "/api/search", headers, body)
            assert "200 OK" in result and "found" in result
            streamed = self.request("POST", "/api/search/stream", headers, body)
            assert "application/x-ndjson" in streamed and "200 OK" in streamed
            events = [json.loads(line) for line in streamed.split("\r\n\r\n", 1)[1].splitlines()]
            assert events[0]["type"] == "start" and events[-1]["type"] == "done"
            assert any(event["type"] == "progress" and "report" in event for event in events)
            count = len(upstream)
            headers["Origin"] = "https://evil.example"
            assert "403 Forbidden" in self.request("POST", "/api/search", headers, body)
            assert len(upstream) == count
            assert "404 Not Found" in self.request("GET", "/README.md", {"Host": "127.0.0.1:8765"})

    monkeypatch.setattr(web, "PublicHTTP", client)
    monkeypatch.setattr(web, "HTTPServer", FakeServer)
    web.serve("https://example.org/idlink", initial_seed="demo")
