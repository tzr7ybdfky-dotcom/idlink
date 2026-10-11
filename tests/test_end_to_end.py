"""End-to-end audit, report, cache and explain with no real network."""

import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from typer.testing import CliRunner

from idlink.cli import app
from idlink.core.http import PublicHTTP
from idlink.core.ratelimit import DomainRateLimiter
from idlink.core.report import read_report


def test_audit_to_explain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    now = [0.0]

    async def sleep(delay: float) -> None:
        now[0] += delay

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if request.url.host == "example.org":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="""
              <meta name="description" content="Astronomy telescopes">
              <a rel="me" href="https://github.com/demo">me</a>""",
            )
        return httpx.Response(
            200,
            json={
                "login": "demo",
                "html_url": "https://github.com/demo",
                "type": "User",
                "bio": "Astronomy telescopes",
                "blog": "https://example.org",
            },
        )

    http = PublicHTTP(
        "https://example.org/idlink",
        transport=httpx.MockTransport(handler),
        limiter=DomainRateLimiter(clock=lambda: now[0], sleep=sleep),
    )
    # All filesystem effects remain inside the test's temporary directory.
    monkeypatch.chdir(tmp_path)
    with patch("idlink.cli.PublicHTTP", return_value=http):
        result = CliRunner().invoke(
            app, ["audit", "example.org", "--repository-url", "https://example.org/idlink"]
        )
        assert result.exit_code == 0, result.output
        report = read_report(Path("report.html"))
        assert len(report.nodes) == 2
        edge_id, edge = next(iter(report.edges.items()))
        assert edge.probability > 0.85
        assert edge.verdict == "вероятно связаны"
        explain = CliRunner().invoke(app, ["explain", edge_id])
        assert explain.exit_code == 0
        assert "Контрдовод:" in explain.output
        for cache_file in Path(".cache/idlink").glob("*.json"):
            data = json.loads(cache_file.read_text())
            assert set(data) == {"url", "phash", "tokens", "activity_hist", "fetched_at"}
            assert "bio" not in data
    assert len(calls) == 4
