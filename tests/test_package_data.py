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
