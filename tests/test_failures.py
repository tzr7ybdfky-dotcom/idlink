"""Check malformed API data and CLI exit-code contracts."""

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from typer.testing import CliRunner

from idlink.cli import app
from idlink.core.collection import Collection
from idlink.core.graph import Report
from idlink.core.http import PublicHTTP
from idlink.core.ratelimit import DomainRateLimiter
from idlink.plugins.base import PluginError
from idlink.plugins.github import GitHubPlugin


@pytest.mark.parametrize("body", [b"bad json", b"{}", b'{"login":null}'])
async def test_malformed_profile(body: bytes) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, content=body)

    async def no_sleep(delay: float) -> None:
        pass

    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(sleep=no_sleep),
    ) as http:
        with pytest.raises(PluginError):
            await GitHubPlugin(http).fetch("demo")


async def test_rate_refusal_stops_further_requests() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(404 if request.url.path == "/robots.txt" else 429)

    async def no_sleep(delay: float) -> None:
        pass

    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(sleep=no_sleep),
    ) as http:
        for _ in range(2):
            with pytest.raises(PluginError):
                await GitHubPlugin(http).fetch("demo")
    assert calls == ["/robots.txt", "/users/demo"]


def test_cli_network_failure_and_search_warning() -> None:
    args = [
        "search",
        "demo",
        "--repository-url",
        "https://example.org/idlink",
        "--purpose",
        "self audit",
    ]
    with patch("idlink.cli.execute", side_effect=PluginError("offline")):
        result = CliRunner().invoke(app, args)
    assert result.exit_code == 3
    assert "ложные совпадения" in result.output


def test_cli_audit_success(tmp_path: Path) -> None:
    data = Collection(Report(nodes=[], edges={}), False)
    with patch("idlink.cli.execute", return_value=data):
        result = CliRunner().invoke(
            app,
            [
                "audit",
                "demo",
                "--repository-url",
                "https://example.org/idlink",
                "--out",
                str(tmp_path / "report.html"),
            ],
        )
    assert result.exit_code == 0
    assert "Отчёт:" in result.output


def test_search_distinguishes_unverified_from_access_reasons() -> None:
    from idlink.core.graph import SourceCheck

    checks = [
        SourceCheck(platform="one", status="unverified", error_kind="unverified", detail="shell"),
        SourceCheck(platform="two", status="error", error_kind="robots", detail="disallowed"),
        SourceCheck(platform="three", status="error", error_kind="timeout", detail="deadline"),
        SourceCheck(platform="four", status="missing", detail="404"),
    ]
    with patch(
        "idlink.cli.execute",
        return_value=Collection(Report(nodes=[], edges={}, checks=checks), True),
    ):
        result = CliRunner().invoke(app, ["search", "alice"])
    assert result.exit_code == 3
    assert not result.stdout.strip()
    assert "Недоступно: 2. Неподтверждено: 1." in result.stderr
    assert "robots.txt: 1; таймауты: 1" in result.stderr
