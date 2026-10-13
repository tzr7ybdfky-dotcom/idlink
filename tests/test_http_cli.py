"""Policy failures and input errors must not trigger profile requests."""

import httpx
import pytest
from typer.testing import CliRunner

from idlink.cli import app
from idlink.core.http import PublicHTTP
from idlink.plugins.base import PluginError


@pytest.mark.parametrize(
    "status,text",
    [
        (200, "User-agent: *\nDisallow: /users/\n"),
        (503, ""),
        (403, ""),
        (302, ""),
        (200, "<html>challenge</html>"),
    ],
)
async def test_robots_denial(status: int, text: str) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(status, text=text)

    async with PublicHTTP(
        "https://example.org/idlink", transport=httpx.MockTransport(handler)
    ) as http:
        with pytest.raises(PluginError):
            await http.get("https://api.github.com/users/demo")
    assert calls == ["/robots.txt"]


async def test_network_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    async with PublicHTTP(
        "https://example.org/idlink", transport=httpx.MockTransport(handler)
    ) as http:
        with pytest.raises(PluginError):
            await http.get("https://api.github.com/users/demo")


def test_cli_rejects_empty_purpose_and_audit_requires_repository() -> None:
    runner = CliRunner()
    assert runner.invoke(app, ["audit", "demo"], env={"IDLINK_REPOSITORY_URL": ""}).exit_code == 2
    args = ["search", "demo", "--repository-url", "https://example.org/idlink", "--purpose", " "]
    assert runner.invoke(app, args).exit_code == 2


def test_search_without_options_uses_all_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    """The short command keeps all-source lookup and the false-match warning."""
    from pathlib import Path

    import idlink.cli as cli

    calls: list[tuple[str, str, str]] = []

    def fake_run(
        seed: str,
        repository_url: str,
        platforms: str,
        out: Path | None,
        extra: list[str] | None,
        depth: int,
        activity: bool,
        restrict_sources: bool = False,
        timeout: float = 6.0,
        respect_robots: bool = True,
    ) -> None:
        calls.append((seed, repository_url, platforms))

    monkeypatch.setattr(cli, "run", fake_run)
    result = CliRunner().invoke(app, ["search", "demo"], env={"IDLINK_REPOSITORY_URL": ""})
    assert result.exit_code == 0
    assert calls == [("demo", "https://github.com/tzr7ybdfky-dotcom/idlink", "all")]
    assert "ложные совпадения" in result.output


async def test_crawl_delay_does_not_slow_unrelated_hostname() -> None:
    """A site's crawl-delay applies only to that domain, not the entire pool."""
    now = [0.0]
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)
        now[0] += delay

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return (
                httpx.Response(200, text="User-agent: *\nCrawl-delay: 20\nAllow: /")
                if request.url.host == "slow.example"
                else httpx.Response(404)
            )
        return httpx.Response(200, text="public")

    from idlink.core.ratelimit import DomainRateLimiter

    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(clock=lambda: now[0], sleep=sleep),
    ) as http:
        await http.get("https://slow.example/alice")
        await http.get("https://fast.example/alice")
    assert sleeps == [20.0, 2.0]


async def test_total_deadline_cancels_an_unresponsive_source() -> None:
    import asyncio

    cancelled = asyncio.Event()
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return httpx.Response(200)

    async with PublicHTTP(
        "https://example.org/idlink", transport=httpx.MockTransport(handler), timeout=0.02
    ) as http:
        with pytest.raises(PluginError, match="таймаут.*неизвестно"):
            await http.get("https://fixture.example/alice")
    assert calls == ["/robots.txt"] and cancelled.is_set()


async def test_slow_robots_does_not_add_an_unnecessary_two_seconds() -> None:
    from idlink.core.ratelimit import DomainRateLimiter

    now, starts = [0.0], []

    async def sleep(delay: float) -> None:
        now[0] += delay

    def handler(request: httpx.Request) -> httpx.Response:
        starts.append(now[0])
        if request.url.path == "/robots.txt":
            now[0] += 3.0
            return httpx.Response(404)
        return httpx.Response(200, text="public")

    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(clock=lambda: now[0], sleep=sleep),
    ) as http:
        await http.get("https://fixture.example/alice")
        await http.get("https://fixture.example/bob")
    assert starts == [0.0, 3.0, 5.0]
