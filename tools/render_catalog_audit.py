"""Publish coverage facts without handles, profile bodies, personal text or images."""

import argparse
import csv
import json
from collections import Counter
from datetime import UTC, datetime
from importlib.resources import files
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


def render_inventory(destination: Path, previous_csv: Path | None = None) -> None:
    """List every current source without treating old or absent checks as fresh validation."""
    from urllib.parse import urlsplit

    previous = {}
    if previous_csv:
        with previous_csv.open(encoding="utf-8", newline="") as stream:
            previous = {row["source_id"]: row for row in csv.DictReader(stream)}
    snapshot = files("idlink.data").joinpath("fediverse_servers.json")
    verified = {row["domain"]: row for row in json.loads(snapshot.read_bytes())}
    counts: Counter[str] = Counter()
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / "catalog-audit.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(
            [
                "platform",
                "source_id",
                "url_template",
                "automatic",
                "positive_control",
                "negative_control",
                "coverage",
                "checked_at",
                "historical_coverage",
            ]
        )
        for site in SOURCES:
            check = (
                verified.get(urlsplit(site.template).hostname or "", {})
                if (site.name.startswith("fediverse-"))
                else {}
            )
            positive = check.get("positive_control", "not_tested")
            negative = check.get("negative_control", "not_tested")
            state = (
                "disabled"
                if not site.automatic
                else "controls_passed"
                if positive == "found" and negative == "missing"
                else "endpoint_checked"
                if negative == "missing"
                else "not_tested"
            )
            old = previous.get(site.name, {})
            history = old.get("coverage", "") if old.get("url_template") == site.template else ""
            counts[state] += 1
            writer.writerow(
                [
                    site.label,
                    site.name,
                    site.template,
                    str(site.automatic).lower(),
                    positive,
                    negative,
                    state,
                    check.get("checked_at", ""),
                    history,
                ]
            )
    automatic = sum(s.automatic and s.input_kind == "username" for s in SOURCES)
    summary = f"""# Каталог и покрытие проверками

Обновлено: {datetime.now(UTC).isoformat()}.

**{len(SOURCES)} записей**, **{automatic} автоматических источников для поиска по нику**.
CSV содержит все записи текущего каталога плюс одну строку заголовка.

| Проверка | Записей |
|---|---:|
"""
    summary += "".join(f"| `{state}` | {count} |\n" for state, count in sorted(counts.items()))
    summary += """
[Полный каталог CSV](catalog-audit.csv) ·
[Архив сетевого аудита от 12 октября](audits/2026-10-12.md).

- `controls_passed`: положительный и случайный отрицательный контроль прошли в дату `checked_at`.
- `endpoint_checked`: проверены метаданные сервера и отсутствие случайного аккаунта;
  положительный контроль не проводился.
- `not_tested`: правило подключено, свежей сетевой проверки здесь нет.
- `disabled`: источник отключён или дублирует уже подключённую страницу.

`historical_coverage` — результат старого аудита для совпадающего URL, **не свежая проверка**.
Число источников не означает, что все сайты доступны или что любой ник на них существует.
Серверы Fediverse считаются отдельно: это независимые базы аккаунтов одной сети.
В таблице только шаблоны ссылок и статусы, без ников контрольных аккаунтов и данных профилей.

Обновить таблицу после изменения каталога (без сетевых запросов):

```bash
python -m tools.render_catalog_audit --inventory --out docs
```
"""
    (destination / "catalog-audit.md").write_text(summary, encoding="utf-8")


def main() -> None:
    """Render a local audit artifact, without issuing any network requests."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?")
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--previous-csv", type=Path, default=Path("docs/audits/2026-10-12.csv"))
    parser.add_argument("--out", type=Path, default=Path("docs"))
    args = parser.parse_args()
    if args.inventory:
        render_inventory(args.out, args.previous_csv)
    elif args.source:
        render(args.source, args.out)
    else:
        parser.error("provide an audit artifact or --inventory")


if __name__ == "__main__":
    main()
