"""Regression fixtures for soft 404s, catch-all routes and account-bound evidence."""

import httpx
import pytest

from idlink.core.collection import collect
from idlink.core.http import PublicHTTP
from idlink.core.ratelimit import DomainRateLimiter
from idlink.plugins.base import PluginError
from idlink.plugins.evidence import identifies_profile, json_identity, soft_404
from idlink.plugins.sherlock import ProbeRule, SherlockPlugin

URL = "https://profiles.example/alice"
PAGE = '<title>alice profile</title><link rel="canonical" href="' + URL + '">'


@pytest.mark.parametrize(
    "body",
    ["<title>404: not found</title>", "<h1>User not found</h1>", "<h2>Страница не найдена</h2>"],
)
def test_visible_missing_heading(body: str) -> None:
    assert soft_404(body)


def test_error_strings_in_scripts_are_not_missing_headings() -> None:
    assert not soft_404(PAGE + '<script>const message="User not found"</script>')


@pytest.mark.parametrize(
    "body",
    [
        "public profile",
        '<link rel="canonical" href="' + URL + '">',
        '{"route":{"username":"alice"}}',
        '{"error":"missing","id":42,"username":"alice"}',
    ],
)
def test_url_echo_and_route_parameters_are_not_accounts(body: str) -> None:
    assert not identifies_profile(body, "alice", URL)


def test_stable_account_record_is_positive() -> None:
    assert json_identity({"user": {"id": "42", "username": "alice"}}, "alice")
    assert not json_identity({"id": False, "username": "alice"}, "alice")
    assert identifies_profile(PAGE, "alice", URL)


@pytest.mark.parametrize(
    "control,expected", [(404, "found"), (200, "unverified"), (403, "unverified")]
)
async def test_positive_html_requires_negative_control(control: int, expected: str) -> None:
    calls: list[str] = []
    starts: list[float] = []
    now = 0.0

    async def sleep(delay: float) -> None:
        nonlocal now
        now += delay

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        starts.append(now)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/alice":
            return httpx.Response(200, text=PAGE)
        # A generic reflected profile shell must never establish existence.
        name = request.url.path.lstrip("/")
        return httpx.Response(control, text=PAGE.replace("alice", name))

    rule = ProbeRule(
        label="fixture",
        url="https://profiles.example/{}",
        probe="https://profiles.example/{}",
        kind="status_code",
    )
    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(clock=lambda: now, sleep=sleep),
    ) as http:
        plugin = SherlockPlugin(http, "fixture", rule)
        if expected == "found":
            assert await plugin.fetch("alice") is not None
        else:
            with pytest.raises(PluginError) as exc:
                await plugin.fetch("alice")
            assert exc.value.kind == "unverified"
    assert len(calls) == 3
    assert starts == [0, 2, 4]


async def test_unverified_is_not_a_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from idlink.core.catalog import PROBE_SOURCES

    monkeypatch.setitem(
        PROBE_SOURCES,
        "fixture",
        ProbeRule(
            label="fixture",
            url="https://profiles.example/{}",
            probe="https://profiles.example/{}",
            kind="status_code",
        ),
    )

    async def sleep(delay: float) -> None:
        pass

    async with PublicHTTP(
        "https://example.org/idlink",
        limiter=DomainRateLimiter(sleep=sleep),
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                404 if r.url.path == "/robots.txt" else 200, text="generic shell"
            )
        ),
    ) as http:
        result = await collect(http, [("fixture", "alice")], depth=0)
    assert not result.has_errors
    assert result.report.checks[0].status == "unverified"
    assert result.report.checks[0].error_kind == "unverified"
    assert not result.report.nodes


async def test_api_record_does_not_validate_missing_public_url() -> None:
    async def sleep(delay: float) -> None:
        pass

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/alice":
            return httpx.Response(200, json={"id": 42, "username": "alice"})
        return httpx.Response(404)

    rule = ProbeRule(
        label="fixture",
        url="https://profiles.example/{}",
        probe="https://profiles.example/api/{}",
        kind="status_code",
    )
    async with PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(sleep=sleep),
    ) as http:
        assert await SherlockPlugin(http, "fixture", rule).fetch("alice") is None
