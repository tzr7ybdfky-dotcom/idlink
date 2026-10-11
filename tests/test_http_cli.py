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


def test_cli_requires_purpose_and_repository() -> None:
    runner = CliRunner()
    assert runner.invoke(app, ["search", "demo"]).exit_code == 2
    assert runner.invoke(app, ["audit", "demo"], env={"IDLINK_REPOSITORY_URL": ""}).exit_code == 2
    args = ["search", "demo", "--repository-url", "https://example.org/idlink", "--purpose", " "]
    assert runner.invoke(app, args).exit_code == 2
