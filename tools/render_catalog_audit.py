"""Publish coverage facts without handles, profile bodies, personal text or images."""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from pydantic import TypeAdapter

from idlink.core.catalog import SOURCES
from idlink.core.graph import SourceCheck


def render(source: Path, destination: Path) -> None:
    """Missing or blocked reference accounts never count as validated detectors."""
    raw = json.loads(source.read_bytes())
    adapter = TypeAdapter(list[SourceCheck])
    positive = {c.platform: c for c in adapter.validate_python(raw["reference_checks"])}
    negative = {c.platform: c for c in adapter.validate_python(raw["negative_checks"])}
    counts: Counter[str] = Counter()
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / "catalog-audit.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(
            [
                "platform",
                "source_id",
                "url_template",
                "positive_control",
                "negative_control",
                "coverage",
                "positive_error",
                "negative_error",
            ]
        )
        for site in SOURCES:
            pos, neg = positive.get(site.name), negative.get(site.name)
            state = (
                "disabled"
                if not site.automatic
                else "unexpected_positive"
                if neg and neg.status == "found"
                else "controls_passed"
                if pos and pos.status == "found" and neg and neg.status == "missing"
                else "inconclusive"
            )
            counts[state] += 1
            writer.writerow(
                [
                    site.label,
                    site.name,
                    site.template,
                    pos.status if pos else "not_tested",
                    neg.status if neg else "not_tested",
                    state,
                    pos.error_kind if pos else "",
                    neg.error_kind if neg else "",
                ]
            )
    summary = f"""# Catalogue audit

UTC: {raw["fetched_at"]}. Catalogue: {len(SOURCES)} sources.

| Coverage | Sources |
|---|---:|
"""
    summary += "".join(f"| {state} | {count} |\n" for state, count in sorted(counts.items()))
    summary += """
See [the per-source CSV](catalog-audit.csv). `controls_passed` means a public reference
account was found and a random format-valid handle was absent in this run.
It is evidence for that detector at that time, not a guarantee for every account.
`inconclusive` includes inaccessible endpoints, missing/stale public references and
ambiguous pages. Blocked requests and timeouts never establish absence.
`unexpected_positive` requires investigation; it is not automatically a real account.
Disabled sources are not queried. Domain and email inputs need separate controls.

References come from official Sherlock/Maigret metadata and reviewed Discourse forums.
Requests respect robots.txt, access refusals and a shared two-second hostname limiter.
Only URL templates and statuses are published; no profile text or avatars are stored.

Reproduce from a development checkout:

```sh
python -m tools.audit_catalog --live --username YOUR_USERNAME --out build/audit.json
python -m tools.render_catalog_audit build/audit.json --out docs
```

This is an opt-in live audit. Automated tests use fixtures and prohibit real networking.
"""
    (destination / "catalog-audit.md").write_text(summary, encoding="utf-8")


def main() -> None:
    """Render a local audit artifact, without issuing any network requests."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, default=Path("docs"))
    args = parser.parse_args()
    render(args.source, args.out)


if __name__ == "__main__":
    main()
