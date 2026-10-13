"""Short terminal and visual commands have distinct output and execution contracts."""

from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from idlink.cli import app
from idlink.core.collection import Collection
from idlink.core.graph import Report, SourceCheck
from idlink.core.models import Profile


def test_search_prints_final_english_list_without_duplicates_or_html(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import idlink.cli as cli

    monkeypatch.chdir(tmp_path)

    async def execute(
        roots: list[tuple[str, str]],
        repository_url: str,
        depth: int,
        activity: bool,
        on_profile: Callable[[Profile], None] | None = None,
        allowed_platforms: frozenset[str] | None = None,
        timeout: float = 6.0,
        respect_robots: bool = True,
        on_check: Callable[[SourceCheck, int, int], None] | None = None,
    ) -> Collection:
        from datetime import UTC, datetime

        from idlink.core.graph import Node

        profile = Profile(
            platform="tiktok",
            username="alice",
            url="https://www.tiktok.com/@alice",
            fetched_at=datetime.now(UTC),
        )
        assert on_profile is not None
        on_profile(profile)
        return Collection(
            Report(
                nodes=[
                    Node(id=profile.url, platform="tiktok", username="alice"),
                    Node(id="https://t.me/alice", platform="telegram", username="alice"),
                ],
                edges={},
            ),
            False,
        )

    monkeypatch.setattr(cli, "execute", execute)
    result = CliRunner().invoke(app, ["search", "alice"])
    assert result.exit_code == 0
    assert result.stdout.strip().splitlines() == [
        "Telegram: https://t.me/alice",
        "TikTok: https://www.tiktok.com/@alice",
    ]
    assert "TikTok: https://www.tiktok.com/@alice" in result.stderr
    assert not (tmp_path / "report.html").exists()


def test_visual_prefills_seed_and_opens_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    import idlink.web as web

    calls: list[tuple[str, bool]] = []

    def serve(
        repository_url: str,
        port: int = 8765,
        *,
        initial_seed: str = "",
        open_browser: bool = False,
        initial_platforms: str = "all",
        timeout: float = 6.0,
        respect_robots: bool = True,
    ) -> None:
        calls.append((initial_seed, open_browser))

    monkeypatch.setattr(web, "serve", serve)
    assert CliRunner().invoke(app, ["visual", "alice"]).exit_code == 0
    assert calls == [("alice", True)]
