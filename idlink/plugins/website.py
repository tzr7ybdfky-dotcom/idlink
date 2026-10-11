"""Public homepage adapter: explicit self-links only, no site-wide crawling."""

from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from idlink.core.http import PublicHTTP
from idlink.core.inputs import seed_kind
from idlink.core.models import Profile
from idlink.plugins.base import PlatformPlugin, PluginError
from idlink.signals.bio import tokenize


class WebsitePlugin(PlatformPlugin):
    """Read a user-supplied public origin, collecting rel=me links and description."""

    name = "website"

    def __init__(self, http: PublicHTTP) -> None:
        self.http = http

    async def fetch(self, username: str) -> Profile | None:
        """This website observation does not establish who owns the domain."""
        if seed_kind(username) != "website":
            raise ValueError("website requires a public domain")
        url = username.rstrip("/") if username.startswith("https://") else "https://" + username
        response = await self.http.get(url + "/")
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise PluginError(f"Website returned HTTP {response.status_code}")
        if "html" not in response.headers.get("content-type", "").lower():
            raise PluginError("website did not return HTML")
        soup = BeautifulSoup(response.content, "html.parser")
        links: set[str] = set()
        for anchor in soup.select('a[rel~="me"]'):
            href = anchor.get("href")
            if isinstance(href, str):
                target = urljoin(url + "/", href)
                parsed = urlsplit(target)
                if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username:
                    links.add(target)
        description = soup.select_one('meta[name="description"]')
        content = description.get("content") if description else ""
        return Profile(
            platform=self.name,
            username=urlsplit(url).hostname or username,
            url=url,
            bio_tokens=tokenize(content if isinstance(content, str) else ""),
            outbound_links=frozenset(links),
            fetched_at=datetime.now(UTC),
        )
