"""Separate browser-facing profile pages from internal detection endpoints."""

import re
from urllib.parse import quote, urlsplit

# Public profile routes; the API probe stays unchanged. Minecraft uses NameMC's
# public player page because Mojang exposes only a JSON lookup, not public profiles.
PROFILE_PAGES = {
    "minecraft": "https://namemc.com/profile/{}",
    "rarible": "https://rarible.com/{}",
    "zhihu": "https://www.zhihu.com/people/{}",
    "bandlab": "https://www.bandlab.com/{}",
    "fansly": "https://fansly.com/{}/posts",
    "fotka": "https://fotka.com/profil/{}",
    "voice123": "https://voice123.com/{}",
    "shaniiwrites": "https://forum.shanniiwrites.com/u/{}",
}


def is_api_url(url: str) -> bool:
    """Recognize service endpoints without rejecting domains containing the word API."""
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    first_label = host.split(".")[0]
    return bool(
        re.fullmatch(r"(?:m?api\d*|.*-api)", first_label)
        or re.search(r"/(?:api(?:\d|/|\.)|graphql(?:/|$)|[^/]*-api/)", parsed.path, re.I)
        or parsed.path.lower().endswith((".json", ".xml"))
    )


def public_profile_url(label: str, username: str, url: str) -> str | None:
    """Never present an API-only hit as a link to an account page."""
    if not is_api_url(url):
        return url
    template = PROFILE_PAGES.get(label.casefold())
    return template.replace("{}", quote(username, safe="")) if template else None
