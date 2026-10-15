"""Public audit tables retain coverage, without leaking audit inputs or profile contents."""

import csv
import json
from pathlib import Path

import pytest

from idlink.core.catalog import Source
from tools.render_catalog_audit import render


def test_render_coverage_without_claiming_inaccessible_detectors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.render_catalog_audit as module

    sites = [
        Source(name=name, label=name, category="Форумы") for name in ("pass", "blocked", "bad")
    ]
    sites.append(Source(name="disabled", label="disabled", category="Форумы", automatic=False))
    monkeypatch.setattr(module, "SOURCES", sites)
    artifact = tmp_path / "audit.json"
    artifact.write_text(
        json.dumps(
            {
                "fetched_at": "2026-10-12T00:00:00Z",
                "seed": "private_audit_input",
                "reference_checks": [
                    {"platform": "pass", "status": "found", "detail": "ignored_profile_text"},
                    {
                        "platform": "blocked",
                        "status": "error",
                        "detail": "access refused",
                        "error_kind": "blocked",
                    },
                ],
                "negative_checks": [
                    {"platform": "pass", "status": "missing", "detail": ""},
                    {"platform": "bad", "status": "found", "detail": ""},
                ],
            }
        )
    )
    destination = tmp_path / "docs"
    render(artifact, destination)
    text = (destination / "catalog-audit.csv").read_text()
    rows = {r["source_id"]: r for r in csv.DictReader(text.splitlines())}
    assert rows["pass"]["coverage"] == "controls_passed"
    assert rows["blocked"]["coverage"] == "inconclusive"
    assert rows["bad"]["coverage"] == "unexpected_positive"
    assert rows["disabled"]["coverage"] == "disabled"
    assert "private_audit_input" not in text
    assert "ignored_profile_text" not in text


def test_published_inventory_matches_current_catalogue() -> None:
    from idlink.core.catalog import SOURCES

    root = Path(__file__).resolve().parents[1]
    with (root / "docs/catalog-audit.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == len(SOURCES)
    by_name = {row["source_id"]: row for row in rows}
    assert len(by_name) == len(rows)
    for site in SOURCES:
        row = by_name[site.name]
        assert row["url_template"] == site.template
        assert row["automatic"] == str(site.automatic).lower()
    summary = (root / "docs/catalog-audit.md").read_text()
    assert f"**{len(SOURCES)} записей**" in summary


def test_inventory_keeps_historical_audit_separate(tmp_path: Path) -> None:
    from tools.render_catalog_audit import render_inventory

    previous = tmp_path / "old.csv"
    previous.write_text(
        "source_id,url_template,coverage\ngithub,https://www.github.com/{},controls_passed\n"
    )
    destination = tmp_path / "docs"
    render_inventory(destination, previous)
    with (destination / "catalog-audit.csv").open() as stream:
        rows = {row["source_id"]: row for row in csv.DictReader(stream)}
    assert rows["github"]["coverage"] == "not_tested"
    assert rows["github"]["historical_coverage"] == "controls_passed"
