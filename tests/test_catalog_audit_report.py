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
