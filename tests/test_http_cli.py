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
        out: Path,
        extra: list[str] | None,
        depth: int,
        activity: bool,
    ) -> None:
        calls.append((seed, repository_url, platforms))

    monkeypatch.setattr(cli, "run", fake_run)
    result = CliRunner().invoke(app, ["search", "demo"], env={"IDLINK_REPOSITORY_URL": ""})
    assert result.exit_code == 0
    assert calls == [("demo", "https://github.com/tzr7ybdfky-dotcom/idlink", "all")]
    assert "ложные совпадения" in result.output
