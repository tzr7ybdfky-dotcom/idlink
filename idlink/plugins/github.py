"""GitHub public user API adapter without authentication."""

import re
from datetime import UTC, datetime
from urllib.parse import urlsplit

from pydantic import AwareDatetime, BaseModel, TypeAdapter, ValidationError

from idlink.core.http import PublicHTTP
from idlink.core.models import Profile
from idlink.plugins.base import PlatformPlugin, PluginError
from idlink.signals.activity import histogram
from idlink.signals.bio import tokenize


class GitHubUser(BaseModel):
    """Only the public fields needed for derived observations."""

    login: str
    html_url: str
    bio: str | None = None
    blog: str | None = None
    type: str


class PublicEvent(BaseModel):
    """Discard event payloads, repository names and all other upstream data."""

    id: str
    public: bool
    created_at: AwareDatetime


class GitHubPlugin(PlatformPlugin):
    """Fetch a named public user; organizations are not person profiles."""

    name = "github"

    def __init__(self, http: PublicHTTP, *, collect_activity: bool = False) -> None:
        self.http = http
        self.collect_activity = collect_activity

    async def activity(self, username: str) -> tuple[int, ...]:
        """Read at most one page of 100 public events, deduplicated by ID."""
        response = await self.http.get(
            f"https://api.github.com/users/{username}/events/public?per_page=100"
        )
        if response.status_code != 200:
            raise PluginError(
                f"GitHub events returned HTTP {response.status_code}",
                kind="blocked" if response.status_code in {401, 403, 429} else "http",
            )
        try:
            events = TypeAdapter(list[PublicEvent]).validate_json(response.content)
        except ValidationError as exc:
            raise PluginError("invalid GitHub event response", kind="response") from exc
        observed = {event.id: event.created_at for event in events if event.public}
        return histogram(observed.values())

    async def fetch(self, username: str) -> Profile | None:
        """Extract tokens and explicit links while discarding the API body."""
        if "--" in username or not re.fullmatch(
            r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", username
        ):
            raise ValueError("invalid GitHub username")
        response = await self.http.get(f"https://api.github.com/users/{username}")
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise PluginError(
                f"GitHub returned HTTP {response.status_code}",
                kind="blocked" if response.status_code in {401, 403, 429} else "http",
            )
        try:
            user = GitHubUser.model_validate_json(response.content)
            if user.login.casefold() != username.casefold():
                raise ValueError("unexpected username")
            if user.html_url.rstrip("/").casefold() != f"https://github.com/{username}".casefold():
                raise ValueError("unexpected profile URL")
        except (ValidationError, ValueError) as exc:
            raise PluginError("invalid GitHub response", kind="response") from exc
        if user.type != "User":
            return None
        bio = user.bio or ""
        links = set(re.findall(r"https?://[^\s<>]+", bio))
        if user.blog:
            blog = user.blog.strip()
            if "://" not in blog:
                blog = "https://" + blog
            parsed = urlsplit(blog)
            if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username:
                links.add(blog)
        return Profile(
            platform=self.name,
            username=user.login,
            url=user.html_url,
            bio_tokens=tokenize(bio),
            outbound_links=frozenset(links),
            activity_hist=await self.activity(username) if self.collect_activity else None,
            fetched_at=datetime.now(UTC),
        )
