"""Graph determinism, artifact round-trip and script injection protection."""

from datetime import UTC, datetime
from pathlib import Path

from idlink.core.graph import edge_id, make_report
from idlink.core.models import Profile
from idlink.core.report import read_report, render_html, write_report


def test_report_roundtrip_and_minimization(tmp_path: Path) -> None:
    a = Profile(
        platform="github",
        username="a",
        url="https://github.com/a",
        bio_tokens=frozenset({"secret-token"}),
        fetched_at=datetime.now(UTC),
    )
    b = a.model_copy(update={"platform": "demo", "username": "b", "url": "https://example.org/b"})
    report = make_report([a, b])
    assert len(report.edges) == 1
    assert edge_id(a.url, b.url) == edge_id(b.url, a.url)
    path = tmp_path / "report.html"
    write_report(report, path)
    assert read_report(path) == report
    html = path.read_text()
    assert "secret-token" not in html
    assert "<script src=" not in html
    assert "connect-src" not in html or "connect-src 'none'" in html
    assert "12 * d.probability" in html


def test_profile_label_cannot_escape_json_script() -> None:
    a = Profile(
        platform="test",
        username="</script><img src=x onerror=alert(1)>",
        url="https://example.org/a",
        fetched_at=datetime.now(UTC),
    )
    html = render_html(make_report([a]))
    assert "<img src=x" not in html
    assert "\\u003c/script>" in html


def test_large_graph_keeps_nodes_without_accumulating_weak_edges() -> None:
    profiles = [
        Profile(
            platform="fixture",
            username="demo",
            url=f"https://example.org/{i}",
            fetched_at=datetime.now(UTC),
        )
        for i in range(30)
    ]
    report = make_report(profiles, sparse=True)
    assert len(report.nodes) == 30
    assert not report.edges
    assert "30%" in report.warnings[0]
