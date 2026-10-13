"""Source categories filter real lookup plans, including combined and invalid selections."""

import pytest
from typer.testing import CliRunner

from idlink.cli import app
from idlink.core.catalog import SOURCES, USERNAME_PLATFORMS
from idlink.core.categories import CATEGORIES, selected_platforms


@pytest.mark.parametrize("flag", list(CATEGORIES))
def test_each_category_has_automatic_sources(flag: str) -> None:
    selected = set(selected_platforms("all", {flag: True}).split(","))
    assert selected and selected <= USERNAME_PLATFORMS
    assert all(
        source.tags & CATEGORIES[flag][1] or source.category == CATEGORIES[flag][0]
        for source in SOURCES
        if source.name in selected
    )


def test_union_and_explicit_source_intersection() -> None:
    forums = set(selected_platforms("all", {"forums": True}).split(","))
    social = set(selected_platforms("all", {"social": True}).split(","))
    combined = set(selected_platforms("all", {"forums": True, "social": True}).split(","))
    assert combined == forums | social
    assert selected_platforms("github", {"dev": True}) == "github"
    with pytest.raises(ValueError):
        selected_platforms("github", {"music": True})
    with pytest.raises(ValueError):
        selected_platforms("fake-platform", {"social": True})


def test_help_and_category_options_are_discoverable() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["help"])
    assert result.exit_code == 0
    assert "idlink search" in result.stdout and "idlink visual" in result.stdout
    for name in CATEGORIES:
        assert "--" + name in result.stdout
    for command in ("search", "visual"):
        assert runner.invoke(app, [command, "--help"]).exit_code == 0
        invalid = runner.invoke(app, [command, "alice", "--music", "--platforms", "github"])
        assert invalid.exit_code == 2


def test_search_passes_categories_to_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    import idlink.cli as cli

    captured: list[str] = []

    def run(
        seed: str,
        repository_url: str,
        platforms: str,
        out: Path | None,
        extra: list[str] | None,
        depth: int,
        activity: bool,
        restrict_sources: bool = False,
    ) -> None:
        assert restrict_sources
        captured.append(platforms)

    monkeypatch.setattr(cli, "run", run)
    assert CliRunner().invoke(app, ["search", "alice", "--forums", "--social"]).exit_code == 0
    assert captured == [selected_platforms("all", {"forums": True, "social": True})]


def test_visual_carries_source_filter_to_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    import idlink.web as web

    captured: list[str] = []

    def serve(
        repository_url: str,
        port: int = 8765,
        *,
        initial_seed: str = "",
        open_browser: bool = False,
        initial_platforms: str = "all",
    ) -> None:
        captured.append(initial_platforms)

    monkeypatch.setattr(web, "serve", serve)
    assert CliRunner().invoke(app, ["visual", "alice", "--gaming"]).exit_code == 0
    assert captured == [selected_platforms("all", {"gaming": True})]
