"""Offline explanations, partial reports and default audit routing."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from idlink.cli import app, main
from idlink.core.collection import Collection
from idlink.core.graph import make_report
from idlink.core.models import Profile
from idlink.core.report import write_report


def test_explain_uses_saved_report_without_network(tmp_path: Path) -> None:
    a = Profile(
        platform="a",
        username="rare-name",
        url="https://example.org/a",
        fetched_at=datetime.now(UTC),
    )
    b = a.model_copy(update={"url": "https://example.org/b"})
    data = make_report([a, b])
    output = tmp_path / "report.html"
    write_report(data, output)
    result = CliRunner().invoke(app, ["explain", next(iter(data.edges)), "--report", str(output)])
    assert result.exit_code == 0
    assert "Контрдовод:" in result.output
    assert "log_lr" in result.output
    assert CliRunner().invoke(app, ["explain", "missing", "--report", str(output)]).exit_code == 2


def test_partial_network_failure_writes_report_and_returns_three(tmp_path: Path) -> None:
    result_data = Collection(make_report([], ["habr: unavailable"]), True)
    out = tmp_path / "report.html"
    with patch("idlink.cli.execute", return_value=result_data):
        result = CliRunner().invoke(
            app,
            ["audit", "demo", "--repository-url", "https://example.org/idlink", "--out", str(out)],
        )
    assert result.exit_code == 3
    assert out.exists()
    assert "unavailable" in result.output


def test_bare_seed_routes_to_audit() -> None:
    with patch("sys.argv", ["idlink", "demo"]), patch("idlink.cli.app") as mocked:
        main()
    mocked.assert_called_once_with(args=["audit", "demo"])
