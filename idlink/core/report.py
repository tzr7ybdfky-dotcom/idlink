"""Single-file report rendering and offline explanation loading."""

import json
import re
from importlib.resources import files
from pathlib import Path

from idlink.core.catalog import SOURCES
from idlink.core.graph import Report


def render_html(report: Report) -> str:
    """Inline all assets and escape JSON so profile data cannot create HTML."""
    assets = files("idlink.assets")
    template = assets.joinpath("report.html").read_text(encoding="utf-8")
    payload = report.model_dump_json().replace("<", "\\u003c").replace("&", "\\u0026")
    platform_labels = json.dumps({s.name: s.label for s in SOURCES}, ensure_ascii=False)
    platform_labels = platform_labels.replace("<", "\\u003c").replace("&", "\\u0026")
    library = assets.joinpath("d3-7.9.0.min.js").read_text(encoding="utf-8")
    license_text = assets.joinpath("D3-LICENSE").read_text(encoding="utf-8")
    return (
        template.replace("__D3__", library)
        .replace("__D3_LICENSE__", license_text)
        .replace("__DATA__", payload)
        .replace("__PLATFORM_LABELS__", platform_labels)
    )


def write_report(report: Report, path: Path) -> None:
    """Write only the requested self-contained artifact."""
    path.write_text(render_html(report), encoding="utf-8")


def read_report(path: Path) -> Report:
    """Parse typed JSON from a generated artifact without running its JavaScript."""
    content = path.read_text(encoding="utf-8")
    match = re.search(
        r'<script id="idlink-data" type="application/json">(.*?)</script>', content, re.DOTALL
    )
    if not match:
        raise ValueError("not an idlink report")
    return Report.model_validate(json.loads(match.group(1)))
