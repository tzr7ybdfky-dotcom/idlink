"""Bounded public profile discovery from explicit seeds and outbound self-links."""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from idlink.core.cache import ProfileCache
from idlink.core.graph import Report, make_report
from idlink.core.http import PublicHTTP
from idlink.core.inputs import seed_kind
from idlink.core.models import Profile
from idlink.plugins.base import PlatformPlugin, PluginError
from idlink.plugins.github import GitHubPlugin
from idlink.plugins.gravatar import GravatarPlugin
from idlink.plugins.habr import HabrPlugin
from idlink.plugins.website import WebsitePlugin

PLATFORMS = frozenset({"github", "gravatar", "habr", "website"})


@dataclass(frozen=True)
class Collection:
    """A report may be useful even when some requested sources failed."""

    report: Report
    has_errors: bool


def linked_seed(url: str) -> tuple[str, str] | None:
    """Recognize exact supported profile URLs, never search or repository URLs."""
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if parsed.scheme != "https" or parsed.username or parsed.query:
        return None
    path = parsed.path.strip("/")
    if host == "github.com" and re.fullmatch(r"[A-Za-z0-9-]{1,39}", path):
        if path.lower() not in {"about", "login", "signup", "settings", "features", "pricing"}:
            return "github", path
    if host == "gravatar.com" and re.fullmatch(r"avatar/[0-9a-f]{32}|avatar/[0-9a-f]{64}", path):
        return "gravatar", path.split("/")[1]
    if host == "habr.com" and path.startswith(("ru/users/", "en/users/")):
        return "habr", path.split("/")[-1]
    if not path and host:
        try:
            if seed_kind(host) == "website":
                return "website", host
        except ValueError:
            pass
    return None


def plan_seeds(seed: str, platforms: str, extra: list[str]) -> list[tuple[str, str]]:
    """Validate the whole plan before issuing any request."""
    kind = seed_kind(seed)
    selected = (
        set(platforms.split(","))
        if platforms != "auto"
        else {"github" if kind == "username" else kind}
    )
    if not selected <= PLATFORMS:
        raise ValueError("unknown platform; choose github, gravatar, website or habr")
    expected = {"github", "habr"} if kind == "username" else {kind}
    if not selected <= expected:
        raise ValueError("selected platforms do not accept this input kind")
    roots = [(platform, seed) for platform in sorted(selected)]
    if "github" in selected and (
        "--" in seed or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", seed)
    ):
        raise ValueError("invalid GitHub username")
    for raw in extra:
        name, sep, value = raw.partition(":")
        if not sep or name not in PLATFORMS or not value:
            raise ValueError("--profile expects platform:identifier")
        plan_seeds(value, name, [])
        roots.append((name, value))
    if len(roots) > 8:
        raise ValueError("at most eight explicit profiles are supported")
    return list(dict.fromkeys(roots))


async def collect(
    http: PublicHTTP,
    roots: list[tuple[str, str]],
    *,
    depth: int,
    cache: ProfileCache | None = None,
    activity: bool = False,
) -> Collection:
    """Fetch at most 16 profiles and follow at most one layer of explicit links."""
    plugins: dict[str, PlatformPlugin] = {
        "github": GitHubPlugin(http, collect_activity=activity),
        "gravatar": GravatarPlugin(http),
        "website": WebsitePlugin(http),
        "habr": HabrPlugin(),
    }
    profiles: dict[str, Profile] = {}
    warnings: list[str] = []
    visited: set[tuple[str, str]] = set()
    has_errors = False
    queue = [(platform, seed, 0) for platform, seed in roots]
    while queue and len(visited) < 16:
        platform, seed, level = queue.pop(0)
        key = (platform, seed.lower())
        if key in visited:
            continue
        visited.add(key)
        try:
            profile = await plugins[platform].fetch(seed)
        except (PluginError, ValueError) as exc:
            has_errors = True
            # Avoid echoing email seeds or raw upstream response bodies.
            warnings.append(f"{platform}: {exc}")
            continue
        if profile is None:
            warnings.append(f"{platform}: публичный профиль не найден.")
            continue
        profiles[profile.url] = profile
        if cache:
            cache.put(profile)
        if level < depth:
            for url in sorted(profile.outbound_links)[:8]:
                candidate = linked_seed(url)
                if candidate:
                    queue.append((*candidate, level + 1))
    if queue:
        warnings.append("Достигнут лимит: не более 16 профилей за запуск.")
    return Collection(make_report(list(profiles.values()), warnings), has_errors)
