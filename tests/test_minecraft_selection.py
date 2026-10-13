"""Category filters change coverage, never the Minecraft account detector."""

from collections.abc import Callable

import httpx
import pytest
from typer.testing import CliRunner

from idlink.cli import app
from idlink.core.categories import selected_platforms
from idlink.core.collection import Collection, collect, plan_seeds
from idlink.core.graph import Report, SourceCheck
from idlink.core.http import PublicHTTP
from idlink.core.models import Profile
from idlink.core.ratelimit import DomainRateLimiter


async def test_minecraft_is_found_with_and_without_gaming_filter() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.mojang.com" and request.url.path != "/robots.txt":
            calls.append(str(request.url))
            return httpx.Response(200, json={"id": "0" * 32, "name": "demouser"})
        return httpx.Response(404)

    async def sleep(delay: float) -> None:
        pass

    plans = [
        plan_seeds("demouser", "all", []),
        plan_seeds("demouser", selected_platforms("all", {"gaming": True}), []),
    ]
    assert ("manual-minecraft", "demouser") in plans[0][:32]
    assert ("manual-minecraft", "demouser") in plans[1]
    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(sleep=sleep),
    ) as http:
        for roots in plans:
            result = await collect(http, roots, depth=0)
            checks = [c for c in result.report.checks if c.platform == "manual-minecraft"]
            assert len(checks) == 1 and checks[0].status == "found"
            assert any(node.platform == "manual-minecraft" for node in result.report.nodes)
    assert calls == ["https://api.mojang.com/users/profiles/minecraft/demouser"] * 2


def test_failed_minecraft_lookup_is_visible_without_reporting_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import idlink.cli as cli

    async def execute(
        roots: list[tuple[str, str]],
        repository_url: str,
        depth: int,
        activity: bool,
        on_profile: Callable[[Profile], None] | None = None,
        allowed_platforms: frozenset[str] | None = None,
        timeout: float = 6.0,
        on_check: Callable[[SourceCheck, int, int], None] | None = None,
    ) -> Collection:
        check = SourceCheck(
            platform="manual-minecraft",
            status="error",
            error_kind="timeout",
            detail="таймаут 6 с; существование профиля неизвестно",
        )
        assert on_check
        on_check(check, 1, len(roots))
        return Collection(Report(nodes=[], edges={}, checks=[check]), True)

    monkeypatch.setattr(cli, "execute", execute)
    result = CliRunner().invoke(app, ["search", "demouser", "--games"])
    assert result.exit_code == 3
    assert result.stdout == ""
    assert "Minecraft: не удалось проверить" in result.stderr
    assert "существование профиля неизвестно" in result.stderr
    assert "Найдено: 0" in result.stderr
