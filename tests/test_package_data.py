"""Package data must be consistent and ship the offline assets and license."""

from importlib.resources import files
from pathlib import Path

from idlink.signals.username import common_names


def test_common_name_source_matches_packaged_copy() -> None:
    source = Path(__file__).parent.parent / "data/common_usernames.txt"
    bundled = files("idlink.data").joinpath("common_usernames.txt")
    assert source.read_text(encoding="utf-8") == bundled.read_text(encoding="utf-8")
    assert "alex" in common_names()


def test_offline_assets_and_license_are_available() -> None:
    assets = files("idlink.assets")
    assert "7.9.0" in assets.joinpath("d3-7.9.0.min.js").read_text()[:100]
    assert "Copyright" in assets.joinpath("D3-LICENSE").read_text()
    assert "__DATA__" in assets.joinpath("report.html").read_text()


def test_catalog_has_over_300_unique_sources_and_manual_social_links() -> None:
    from urllib.parse import urlsplit

    from idlink.core.catalog import SOURCES

    assert len({s.label.casefold() for s in SOURCES}) > 300
    assert len({urlsplit(s.template).hostname for s in SOURCES if s.template}) > 300
    assert len({s.name for s in SOURCES}) == len(SOURCES)
    for label in ("Telegram", "TikTok", "Instagram"):
        source = next(s for s in SOURCES if s.label == label)
        assert not source.automatic
        assert source.template.startswith("https://")
        assert source.template.count("{}") == 1
    assert "MIT" in files("idlink.data").joinpath("SHERLOCK-LICENSE").read_text()
