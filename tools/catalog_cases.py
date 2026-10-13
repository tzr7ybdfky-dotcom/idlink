"""Read public upstream control locators in memory; never persist profile content or examples."""

import re
import secrets
from dataclasses import dataclass
from urllib.parse import urlsplit

from pydantic import AliasChoices, BaseModel, Field, TypeAdapter

from idlink.core.catalog import PROBE_SOURCES, USERNAME_PLATFORMS
from idlink.core.http import PublicHTTP
from idlink.plugins.base import PluginError
from idlink.plugins.discourse import FORUMS

UPSTREAM = (
    "https://raw.githubusercontent.com/sherlock-project/sherlock/master/sherlock_project/resources/data.json",
    "https://raw.githubusercontent.com/soxoj/maigret/main/maigret/resources/data.json",
)


class Example(BaseModel):
    """Use public reference handles only for compatible anonymous GET endpoints."""

    url: str = ""
    claimed: str = Field(
        default="", validation_alias=AliasChoices("username_claimed", "usernameClaimed")
    )
    disabled: bool = False


@dataclass(frozen=True)
class References:
    """Coverage and retrieval errors remain explicit when upstream data is unavailable."""

    roots: list[tuple[str, str]]
    disabled: frozenset[str]
    warnings: tuple[str, ...]


def endpoint(template: str) -> str:
    """Match the entire public endpoint, not merely its hostname or label."""
    parsed = urlsplit(template.replace("{username}", "{}"))
    return parsed._replace(netloc=parsed.netloc.lower(), path=parsed.path.rstrip("/")).geturl()


def reference_roots(records: list[Example]) -> tuple[list[tuple[str, str]], frozenset[str]]:
    """A regex-invalid upstream example is excluded rather than rewritten or guessed."""
    examples = {endpoint(row.url): row for row in records if row.url}
    roots: list[tuple[str, str]] = []
    disabled: set[str] = set()
    for name, rule in PROBE_SOURCES.items():
        row = examples.get(endpoint(rule.url))
        if row is None:
            continue
        if row.disabled:
            disabled.add(name)
        if (
            row.claimed
            and not row.disabled
            and (not rule.pattern or re.fullmatch(rule.pattern, row.claimed))
        ):
            roots.append((name, row.claimed))
    return roots, frozenset(disabled)


def negative_roots() -> list[tuple[str, str]]:
    """Generate rare format-valid controls; an unexpected positive requires investigation."""
    digits = "".join(str(secrets.randbelow(10)) for _ in range(15))
    total = 0
    for digit in digits:
        total = (total + int(digit)) * 2
    checksum = (12 - total % 11) % 11
    identifier = digits + ("X" if checksum == 10 else str(checksum))
    orcid = "-".join(identifier[start : start + 4] for start in range(0, 16, 4))
    candidates = (
        "idlink" + secrets.token_hex(4),
        "idlink" + "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(8)),
        "idlink_" + secrets.token_hex(6),
        *(secrets.token_hex(n) for n in (16, 12, 8, 6, 4)),
        *(
            str(secrets.randbelow(9) + 1) + "".join(str(secrets.randbelow(10)) for _ in range(n))
            for n in (14, 8, 5)
        ),
        orcid,
    )
    roots = []
    for name in sorted(USERNAME_PLATFORMS):
        rule = PROBE_SOURCES.get(name)
        seed = next(
            (
                value
                for value in candidates
                if not rule or not rule.pattern or re.fullmatch(rule.pattern, value)
            ),
            None,
        )
        if seed:
            roots.append((name, seed))
    return roots


async def fetch_references(http: PublicHTTP) -> References:
    """Official metadata follows the same robots and host-rate policy as profile requests."""
    records: list[Example] = []
    warnings: list[str] = []
    for url in UPSTREAM:
        try:
            response = await http.get(url)
            if response.status_code != 200:
                raise ValueError(f"HTTP {response.status_code}")
            raw = response.json()
            sites = raw.get("sites", raw)
            for value in sites.values():
                if isinstance(value, dict):
                    try:
                        records.append(TypeAdapter(Example).validate_python(value))
                    except ValueError:
                        continue
        except (PluginError, ValueError) as exc:
            warnings.append(f"{url}: {exc}")
    roots, disabled = reference_roots(records)
    roots.extend((forum.name, forum.reference_url.rstrip("/").split("/")[-1]) for forum in FORUMS)
    return References(roots, disabled, tuple(warnings))
