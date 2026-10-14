"""Import MIT Maigret GET rules from a local snapshot without contacting profile sites."""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]


class Site(BaseModel):
    """Read detection metadata only; ignore example identities and request credentials."""

    model_config = ConfigDict(extra="ignore")
    url: str = ""
    urlProbe: str = ""
    checkType: str = ""
    absenceStrs: list[str] = Field(default_factory=list)
    presenseStrs: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    regexCheck: str = ""
    disabled: bool = False
    engine: str = ""
    source: str = ""
    requestMethod: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    requestBody: str | dict[str, object] | None = None
    requestPayload: str | dict[str, object] | None = None
    activation: dict[str, object] = Field(default_factory=dict)
    type: str = "username"
    protocol: str = ""
    urlMain: str = ""
    urlSubpath: str = ""
    errorUrl: str = ""


class Engine(BaseModel):
    """Only the site's request defaults are inherited, never example identities."""

    site: Site


def resolve_site(raw: dict[str, object], engines: dict[str, Engine]) -> Site | None:
    """Resolve declared engine defaults with explicit per-site overrides."""
    site = Site.model_validate(raw)
    if site.engine:
        engine = engines.get(site.engine)
        if engine is None:
            return None
        site = Site.model_validate(engine.site.model_dump(exclude_unset=True) | raw)
    for field in ("url", "urlProbe"):
        value = getattr(site, field)
        value = value.replace("{urlMain}", site.urlMain.rstrip("/"))
        value = value.replace("{urlSubpath}", site.urlSubpath)
        setattr(site, field, value)
    return site


def safe_template(url: str) -> bool:
    """Accept exactly one username placeholder on a public HTTPS host, not a subdomain."""
    parsed = urlsplit(url)
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and "." in parsed.hostname
        and "{" not in parsed.netloc
        and not parsed.username
        and parsed.port in {None, 443}
        and url.count("{username}") == 1
        and "{" not in url.replace("{username}", "")
        and not parsed.hostname.endswith((".onion", ".local", ".test"))
    )


def import_sites(snapshot: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Deduplicate original profile endpoints and exclude rules needing custom requests."""
    from idlink.core.categories import category_for_tags

    data = json.loads(snapshot.read_bytes())
    sites = data["sites"]
    engines = {name: Engine.model_validate(raw) for name, raw in data.get("engines", {}).items()}
    existing = json.loads((ROOT / "idlink/data/platforms.json").read_bytes())
    labels = {s["label"].casefold() for s in existing}
    urls = {s["template"].rstrip("/").casefold() for s in existing}
    sources: list[dict[str, object]] = []
    rules: list[dict[str, object]] = []
    for label, raw in sites.items():
        site = resolve_site(raw, engines)
        if site is None:
            continue
        tags = sorted(set(site.tags))
        if (
            site.disabled
            or site.source
            or site.headers
            or site.requestBody
            or site.requestPayload
            or site.activation
            or site.type != "username"
            or site.protocol not in {"", "https"}
            or site.requestMethod != "GET"
            or not safe_template(site.url)
            or not safe_template(site.urlProbe or site.url)
            or site.checkType not in {"message", "status_code", "response_url"}
        ):
            continue
        url = site.url.replace("{username}", "{}")
        key = url.rstrip("/").casefold()
        if label.casefold() in labels or key in urls:
            continue
        if site.checkType == "message" and not (site.presenseStrs or site.absenceStrs):
            continue
        if site.regexCheck:
            try:
                re.compile(site.regexCheck)
            except re.error:
                continue
        name = "maigret-" + hashlib.sha256(key.encode()).hexdigest()[:16]
        sources.append(
            {
                "name": name,
                "label": label,
                "category": category_for_tags(tags),
                "tags": tags,
                "automatic": False,
                "template": url,
                "reason": "Публичная страница; правило Maigret, эвристический кандидат.",
            }
        )
        rules.append(
            {
                "label": label,
                "url": url,
                "probe": (site.urlProbe or site.url).replace("{username}", "{}"),
                "kind": site.checkType,
                "errors": site.absenceStrs,
                "presence": site.presenseStrs,
                "pattern": site.regexCheck,
                "error_url": site.errorUrl,
                "evidence": (
                    "mediawiki-user"
                    if site.engine.startswith("MediaWikiJson")
                    else {
                        "DiscourseJson": "discourse-user",
                        "Mastodon": "mastodon-user",
                        "Lemmy": "lemmy-user",
                    }.get(site.engine, "")
                ),
            }
        )
        labels.add(label.casefold())
        urls.add(key)
    return sources, rules


def main() -> None:
    """Write a sanitized bundled snapshot and attribution manifest."""
    import sys

    snapshot = Path(sys.argv[1])
    sources, rules = import_sites(snapshot)
    for name, records in (("extra_platforms.json", sources), ("extra_probe_rules.json", rules)):
        (ROOT / "idlink/data" / name).write_text(
            json.dumps(records, ensure_ascii=False, indent=2) + "\n"
        )
    (ROOT / "idlink/data/maigret-provenance.json").write_text(
        json.dumps(
            {
                "source": "https://github.com/soxoj/maigret",
                "file": "maigret/resources/data.json",
                "license": "MIT",
                "retrieved_at": datetime.now(UTC).date().isoformat(),
                "source_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                "entries": len(sources),
                "use": "GET rules with resolved engine defaults; no example identities or headers",
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Imported {len(sources)} distinct profile endpoints")


if __name__ == "__main__":
    main()
