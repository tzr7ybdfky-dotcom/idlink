"""Bounded public profile discovery from explicit seeds and outbound self-links."""

import asyncio
import re
from collections import deque
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from idlink.core.cache import ProfileCache
from idlink.core.catalog import PROBE_SOURCES, USERNAME_PLATFORMS, WIKI_HOSTS
from idlink.core.graph import Report, SourceCheck, make_report
from idlink.core.http import PublicHTTP
from idlink.core.inputs import seed_kind
from idlink.core.models import Profile
from idlink.plugins.base import PlatformPlugin, PluginError
from idlink.plugins.bluesky import BlueskyPlugin
from idlink.plugins.github import GitHubPlugin
from idlink.plugins.gravatar import GravatarPlugin
from idlink.plugins.habr import HabrPlugin
from idlink.plugins.public_apis import PublicAPIPlugin
from idlink.plugins.sherlock import SherlockPlugin
from idlink.plugins.website import WebsitePlugin

PLATFORMS = USERNAME_PLATFORMS | {"gravatar", "habr", "website"}


@dataclass(frozen=True)
class Collection:
    """A report may be useful even when some requested sources failed."""

    report: Report
    has_errors: bool


def linked_seed(url: str) -> tuple[str, str] | None:
    """Recognize exact supported profile URLs, never search or repository URLs."""
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if parsed.scheme != "https" or parsed.username or parsed.fragment:
        return None
    path = parsed.path.strip("/")
    if host == "news.ycombinator.com" and path == "user":
        query = parse_qs(parsed.query)
        if set(query) == {"id"} and len(query["id"]) == 1:
            name = query["id"][0]
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
                return "hackernews", name
        return None
    if parsed.query:
        return None
    if host == "t.me" and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,30}[A-Za-z0-9]", path):
        return "telegram", path
    if host == "keybase.io" and re.fullmatch(r"[A-Za-z0-9_]{2,16}", path):
        if path.lower() not in {"login", "signup", "docs", "about", "download"}:
            return "keybase", path
    if host == "bsky.app" and path.startswith("profile/"):
        handle = path.removeprefix("profile/")
        if handle.lower().endswith(".bsky.social"):
            name = handle[:-12]
            if re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", name):
                return "bluesky", name
        return None
    for name, rule in PROBE_SOURCES.items():
        locator = urlsplit(rule.url)
        if (locator.hostname or "").lower().removeprefix("www.") != host:
            continue
        pattern = re.escape(locator.path.strip("/")).replace(
            r"\{\}", r"([A-Za-z0-9][A-Za-z0-9_.-]{0,79})"
        )
        if match := re.fullmatch(pattern, path):
            if rule.pattern and not re.fullmatch(rule.pattern, match[1]):
                continue
            return name, match[1]
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
        (set(USERNAME_PLATFORMS) if kind == "username" else {kind})
        if platforms == "all"
        else set(platforms.split(","))
        if platforms != "auto"
        else {"github" if kind == "username" else kind}
    )
    if not selected <= PLATFORMS:
        raise ValueError("unknown platform; choose all or a supported source from the catalogue")
    expected = USERNAME_PLATFORMS | {"habr"} if kind == "username" else {kind}
    if not selected <= expected:
        raise ValueError("selected platforms do not accept this input kind")
    roots = [(platform, seed) for platform in sorted(selected)]
    if (
        platforms != "all"
        and "github" in selected
        and (
            "--" in seed or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", seed)
        )
    ):
        raise ValueError("invalid GitHub username")
    for raw in extra:
        name, sep, value = raw.partition(":")
        if not sep or name not in PLATFORMS or not value:
            raise ValueError("--profile expects platform:identifier")
        plan_seeds(value, name, [])
        roots.append((name, value))
    if len(extra) > 8:
        raise ValueError("at most eight explicit profiles are supported")
    return list(dict.fromkeys(roots))


async def _fetch_queue(
    plugins: dict[str, PlatformPlugin],
    queue: deque[tuple[str, str, int]],
    visited: set[tuple[str, str]],
    limit: int,
    concurrency: int = 128,
) -> AsyncGenerator[tuple[str, str, int, Profile | None | ValueError | PluginError], None]:
    """Refill a freed slot immediately; one slow host never stalls the next wave."""

    async def fetch(
        item: tuple[str, str, int],
    ) -> tuple[str, str, int, Profile | None | ValueError | PluginError]:
        platform, seed, level = item
        try:
            result: Profile | None | ValueError | PluginError = await plugins[platform].fetch(seed)
        except (ValueError, PluginError) as error:
            result = error
        return platform, seed, level, result

    pending: set[asyncio.Task[tuple[str, str, int, Profile | None | ValueError | PluginError]]] = (
        set()
    )
    try:
        while pending or (queue and len(visited) < limit):
            while queue and len(pending) < concurrency and len(visited) < limit:
                platform, seed, level = queue.popleft()
                key = platform, seed if platform == "hackernews" else seed.lower()
                if key in visited:
                    continue
                visited.add(key)
                pending.add(asyncio.create_task(fetch((platform, seed, level))))
            if not pending:
                break
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                yield task.result()
    finally:
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


async def collect(
    http: PublicHTTP,
    roots: list[tuple[str, str]],
    *,
    depth: int,
    cache: ProfileCache | None = None,
    activity: bool = False,
    on_profile: Callable[[Profile], None] | None = None,
    allowed_platforms: frozenset[str] | None = None,
) -> Collection:
    """Check every selected source and at most 16 additional self-links."""
    plugins: dict[str, PlatformPlugin] = {
        "github": GitHubPlugin(http, collect_activity=activity),
        "bluesky": BlueskyPlugin(http),
        "gravatar": GravatarPlugin(http),
        "website": WebsitePlugin(http),
        "habr": HabrPlugin(),
        **{
            name: PublicAPIPlugin(http, name, WIKI_HOSTS.get(name, ""))
            for name in USERNAME_PLATFORMS - {"github", "bluesky"} - PROBE_SOURCES.keys()
        },
    }
    plugins.update({name: SherlockPlugin(http, name, rule) for name, rule in PROBE_SOURCES.items()})
    profiles: dict[str, Profile] = {}
    warnings: list[str] = []
    checks: list[SourceCheck] = []
    visited: set[tuple[str, str]] = set()
    has_errors = False
    queue = deque((platform, seed, 0) for platform, seed in roots)
    limit = len(roots) + 16
    async for platform, _seed, level, profile in _fetch_queue(plugins, queue, visited, limit):
        if isinstance(profile, ValueError):
            checks.append(
                SourceCheck(
                    platform=platform,
                    status="invalid",
                    detail="Формат ника не поддерживается этой площадкой.",
                )
            )
            continue
        if isinstance(profile, PluginError):
            has_errors = True
            warnings.append(f"{platform}: {profile}")
            checks.append(SourceCheck(platform=platform, status="error", detail=str(profile)))
            continue
        if profile is None:
            warnings.append(f"{platform}: публичный профиль не найден.")
            checks.append(
                SourceCheck(
                    platform=platform,
                    status="missing",
                    detail="Страница отсутствует по правилу площадки или ответу API.",
                )
            )
            continue
        if profile.url not in profiles and on_profile:
            on_profile(profile)
        profiles[profile.url] = profile
        checks.append(
            SourceCheck(
                platform=platform,
                status="found",
                detail=(
                    "Кандидат по правилу страницы; возможна заглушка или ложное совпадение."
                    if platform in PROBE_SOURCES
                    else "Профиль найден; принадлежность человеку не установлена."
                ),
                url=profile.url,
            )
        )
        if cache:
            cache.put(profile)
        if level < depth:
            for url in sorted(profile.outbound_links)[:8]:
                candidate = linked_seed(url)
                if candidate and (allowed_platforms is None or candidate[0] in allowed_platforms):
                    queue.append((*candidate, level + 1))
    if queue:
        warnings.append("Достигнут лимит дополнительных переходов по ссылкам.")
    report = make_report(list(profiles.values()), warnings, sparse=len(profiles) > 24)
    report.checks = checks
    return Collection(report, has_errors)
