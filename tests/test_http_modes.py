"""Robots is selectable; request spacing, public URLs and server refusals always apply."""

from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from idlink.cli import app
from idlink.core.http import PublicHTTP
from idlink.core.ratelimit import DomainRateLimiter
from idlink.plugins.base import PluginError


async def test_direct_mode_skips_robots_and_keeps_spacing() -> None:
    now = [0.0]
    starts: list[float] = []

    async def sleep(delay: float) -> None:
        now[0] += delay

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path != "/robots.txt"
        assert request.headers["user-agent"].startswith("idlink/")
        assert not request.headers.get("authorization")
        starts.append(now[0])
        return httpx.Response(200)

    async with PublicHTTP(
        "https://example.org/idlink",
        respect_robots=False,
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(clock=lambda: now[0], sleep=sleep),
    ) as http:
        await http.get("https://example.org/alice")
        await http.get("https://example.org/bob")
    assert starts == [0, 2]


async def test_direct_mode_stops_after_server_refusal() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(429)

    async with PublicHTTP(
        "https://example.org/idlink",
        respect_robots=False,
        transport=httpx.MockTransport(handler),
    ) as http:
        assert (await http.get("https://example.org/alice")).status_code == 429
        with pytest.raises(PluginError) as exc:
            await http.get("https://example.org/bob")
    assert exc.value.kind == "blocked"
    assert calls == ["/alice"]


@pytest.mark.parametrize("respect", [False, True])
def test_search_robots_option_reaches_transport(
    respect: bool, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import idlink.cli as cli

    monkeypatch.chdir(tmp_path)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        return httpx.Response(
            200,
            json={
                "login": "alice",
                "type": "User",
                "html_url": "https://github.com/alice",
            },
        )

    def client(repository: str, *, timeout: float, respect_robots: bool) -> PublicHTTP:
        assert respect_robots is respect
        return PublicHTTP(
            repository,
            timeout=timeout,
            respect_robots=respect_robots,
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(cli, "PublicHTTP", client)
    args = ["search", "alice", "--platforms", "github", "--depth", "0"]
    if respect:
        args.append("--respect-robots")
    result = CliRunner().invoke(app, args)
    if respect:
        assert result.exit_code == 3 and calls == ["/robots.txt"]
        assert "GitHub:" not in result.stdout
    else:
        assert result.exit_code == 0 and calls == ["/users/alice"]
        assert "GitHub: https://github.com/alice" in result.stdout
