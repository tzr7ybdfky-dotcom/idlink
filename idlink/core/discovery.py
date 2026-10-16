"""Bounded similar-handle discovery through official anonymous search APIs."""

import asyncio
import re
from urllib.parse import quote, urlencode

from pydantic import BaseModel, Field, ValidationError
from rapidfuzz.distance import Levenshtein

from idlink.core.http import PublicHTTP
from idlink.plugins.base import PluginError


class SimilarMatch(BaseModel):
    """Name similarity describes spelling only and never person-link probability."""

    platform: str
    username: str
    url: str
    name_similarity: float = Field(ge=0, le=1)


class GitHubAccount(BaseModel):
    """Discard all fields except the public account identifier and login."""

    id: int = Field(gt=0)
    login: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")
    type: str = "User"


class GitHubResults(BaseModel):
    """An incomplete API response remains a bounded sample, never an exhaustive search."""

    items: list[GitHubAccount]
    incomplete_results: bool = False


class BskyAccount(BaseModel):
    """Public stable DID and handle; discard biographies and photos."""

    did: str = Field(pattern=r"^did:(?:plc|web):[A-Za-z0-9.:_%~-]+$")
    handle: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$")


class BskyResults(BaseModel):
    """Only the first bounded page is used; cursors are never traversed."""

    actors: list[BskyAccount]


def normal_name(value: str) -> str:
    """Ignore casing and separators; compare the nickname part of default Bluesky handles."""
    return re.sub(r"[._-]", "", value.casefold().removesuffix(".bsky.social"))


def match_name(seed: str, candidate: str, edits: int) -> float | None:
    """Allow bounded edit distance; omit exact spellings already handled by normal lookup."""
    name = candidate.removesuffix(".bsky.social")
    if seed.casefold() == name.casefold():
        return None
    a, b = normal_name(seed), normal_name(candidate)
    distance = Levenshtein.distance(a, b)
    if not b or distance > edits:
        return None
    return 1 - distance / max(len(a), len(b))


async def discover_similar(
    http: PublicHTTP,
    seed: str,
    platforms: frozenset[str],
    *,
    limit: int = 5,
    edits: int = 2,
) -> tuple[list[SimilarMatch], list[str]]:
    """Two public API calls at most; every request uses the shared robots/rate-limit policy."""
    if not 1 <= limit <= 20 or not 0 <= edits <= 4:
        raise ValueError("similar limit must be 1..20 and edit distance 0..4")
    name = normal_name(seed)
    if len(name) < 4 or not re.fullmatch(r"[a-z0-9]+", name):
        return [], []
    query = name[: max(3, min(5, len(name) // 2))]

    async def search(platform: str) -> tuple[list[SimilarMatch], list[str]]:
        matches: list[SimilarMatch] = []
        warnings: list[str] = []
        try:
            async with asyncio.timeout(4 * http.timeout):
                if platform == "github":
                    url = "https://api.github.com/search/users?" + urlencode(
                        {"q": query + " in:login type:user", "per_page": 50}
                    )
                else:
                    url = (
                        "https://public.api.bsky.app/xrpc/app.bsky.actor.searchActors?"
                        + urlencode({"q": query, "limit": 50})
                    )
                response = await http.get(url)
                if response.status_code != 200:
                    raise PluginError(f"HTTP {response.status_code}")
                if platform == "github":
                    result = GitHubResults.model_validate_json(response.content)
                    candidates = [
                        (a.login, "https://github.com/" + a.login)
                        for a in result.items
                        if a.type == "User"
                    ]
                    if result.incomplete_results:
                        warnings.append("GitHub similar-name search returned incomplete results.")
                else:
                    actors = BskyResults.model_validate_json(response.content).actors
                    candidates = [
                        (a.handle, "https://bsky.app/profile/" + quote(a.did, safe=":"))
                        for a in actors
                    ]
                for username, locator in candidates:
                    similarity = match_name(seed, username, edits)
                    if similarity is not None:
                        matches.append(
                            SimilarMatch(
                                platform=platform,
                                username=username,
                                url=locator,
                                name_similarity=similarity,
                            )
                        )
        except (PluginError, ValidationError, TimeoutError) as exc:
            warnings.append(f"{platform}: similar-name search unavailable ({exc}).")
        unique = {item.url: item for item in matches}
        return sorted(unique.values(), key=lambda item: (-item.name_similarity, item.username))[
            :limit
        ], warnings

    results = await asyncio.gather(*(search(p) for p in sorted(platforms & {"github", "bluesky"})))
    return [item for matches, _ in results for item in matches], [
        w for _, warnings in results for w in warnings
    ]
