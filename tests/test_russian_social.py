"""Russian public pages must pass identity and missing-page controls."""

import httpx
import pytest

from idlink.core.catalog import PROBE_SOURCES, SOURCES
from idlink.core.categories import selected_platforms
from idlink.core.http import PublicHTTP
from idlink.core.ratelimit import DomainRateLimiter
from idlink.plugins.base import PluginError
from idlink.plugins.sherlock import SherlockPlugin

CASES = [
    ("ok", "alice"),
    ("ok-id", "123456789"),
    ("rutube", "alice"),
    ("rutube-id", "12345678"),
    ("dzen", "alice"),
]


def test_russian_sources_are_selected_as_social() -> None:
    social = set(selected_platforms("all", {"social": True}).split(","))
    assert {name for name, _ in CASES} | {"vk"} <= social
    for label in ("pikabu", "Boosty", "LiveJournal", "My.Mail.ru@mail.ru"):
        assert next(s.name for s in SOURCES if s.label == label) in social
    video = set(selected_platforms("all", {"video": True}).split(","))
    assert {"rutube", "rutube-id"} <= video


@pytest.mark.parametrize("name,username", CASES)
@pytest.mark.parametrize("mode", ["profile", "missing", "login", "catch-all", "blocked"])
async def test_russian_public_page(name: str, username: str, mode: str) -> None:
    rule = PROBE_SOURCES[name]
    target = rule.url.replace("{}", username)
    controls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if mode == "blocked":
            return httpx.Response(403)
        if mode == "missing":
            return httpx.Response(200, text="<h1>Страница не найдена</h1>")
        if mode == "login":
            return httpx.Response(200, text="<h1>Вход на сайт</h1>")
        if str(request.url) != target:
            controls.append(request.url)
            if mode != "catch-all":
                return httpx.Response(404)
        return httpx.Response(
            200,
            text=(
                f'<meta property="og:url" content="{request.url}">'
                '<meta property="og:title" content="Алексей Иванов">'
            ),
        )

    async def sleep(delay: float) -> None:
        pass

    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(sleep=sleep),
    ) as http:
        plugin = SherlockPlugin(http, name, rule)
        if mode in {"login", "catch-all", "blocked"}:
            with pytest.raises(PluginError):
                await plugin.fetch(username)
        elif mode == "missing":
            assert await plugin.fetch(username) is None
        else:
            result = await plugin.fetch(username)
            assert result is not None and result.url == target
            assert len(controls) == 1
            if name.endswith("-id"):
                assert controls[0].path.strip("/").split("/")[-1].isdigit()
