"""Import anonymous GET metadata from a local CC BY-SA WhatsMyName snapshot."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from tools.import_catalog import ROOT, safe_template

CATEGORIES = {
    "social": "Социальные сети",
    "gaming": "Игры",
    "tech": "Разработка",
    "coding": "Разработка",
    "music": "Музыка",
    "video": "Видео и стримы",
    "images": "Фотография",
    "art": "Искусство и дизайн",
    "blog": "Блоги",
    "news": "Новости",
    "business": "Работа и бизнес",
    "finance": "Работа и бизнес",
    "shopping": "Магазины",
    "education": "Образование",
    "forum": "Форумы",
}


class Site(BaseModel):
    """Ignore known usernames and all other data not used for detection."""

    model_config = ConfigDict(extra="ignore")
    name: str
    uri_check: str
    uri_pretty: str = ""
    e_code: int
    e_string: str
    m_string: str
    m_code: int
    cat: str
    valid: bool = True


def import_sites(snapshot: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Keep only supported rules and deduplicate against the other bundled catalogues."""
    existing = []
    for filename in ("platforms.json", "extra_platforms.json"):
        existing.extend(json.loads((ROOT / "idlink/data" / filename).read_bytes()))
    labels = {s["label"].casefold() for s in existing}
    urls = {s["template"].rstrip("/").casefold() for s in existing}
    sources: list[dict[str, object]] = []
    rules: list[dict[str, object]] = []
    for raw in json.loads(snapshot.read_bytes())["sites"]:
        if any(raw.get(key) for key in ("headers", "post_body", "strip_bad_char")):
            continue
        site = Site.model_validate(raw)
        url = (site.uri_pretty or site.uri_check).replace("{account}", "{username}")
        probe = site.uri_check.replace("{account}", "{username}")
        if not site.valid or site.e_code != 200 or not site.e_string:
            continue
        if not safe_template(url) or not safe_template(probe):
            continue
        url, probe = url.replace("{username}", "{}"), probe.replace("{username}", "{}")
        key = url.rstrip("/").casefold()
        if key in urls or site.name.casefold() in labels:
            continue
        sources.append(
            {
                "name": "wmn-" + hashlib.sha256(key.encode()).hexdigest()[:16],
                "label": site.name,
                "category": CATEGORIES.get(site.cat, "Другие сообщества"),
                "tags": [site.cat],
                "automatic": False,
                "template": url,
                "reason": "Публичная страница; правило WhatsMyName, эвристический кандидат.",
            }
        )
        rules.append(
            {
                "label": site.name,
                "url": url,
                "probe": probe,
                "kind": "message",
                "presence": [site.e_string],
                "errors": [site.m_string] if site.m_string else [],
            }
        )
        urls.add(key)
        labels.add(site.name.casefold())
    return sources, rules


def main() -> None:
    """Write separately attributed, sanitized CC BY-SA data files."""
    import sys

    snapshot = Path(sys.argv[1])
    sources, rules = import_sites(snapshot)
    for name, data in (("wmn_platforms.json", sources), ("wmn_probe_rules.json", rules)):
        (ROOT / "idlink/data" / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        )
    manifest = {
        "source": "https://github.com/WebBreacher/WhatsMyName",
        "file": "wmn-data.json",
        "license": "CC-BY-SA-4.0",
        "copyright": "Micah Hoffman and WhatsMyName contributors",
        "retrieved_at": datetime.now(UTC).date().isoformat(),
        "source_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        "entries": len(sources),
        "adaptations": "GET metadata, normalized templates, deduplication; no example accounts",
        "derived_files": ["wmn_platforms.json", "wmn_probe_rules.json"],
    }
    (ROOT / "idlink/data/wmn-provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Imported {len(sources)} distinct WhatsMyName endpoints")


if __name__ == "__main__":
    main()
