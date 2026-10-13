"""Exact anonymous account checks against the documented Discourse user endpoint."""

import re
from datetime import UTC, datetime
from importlib.resources import files
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from idlink.core.http import PublicHTTP
from idlink.core.models import Profile
from idlink.plugins.base import PlatformPlugin, PluginError


class ForumSource(BaseModel):
    """An enrolled forum has passed anonymous positive and negative live controls."""

    name: str
    label: str
    host: str
    reference_url: str


FORUMS = TypeAdapter(list[ForumSource]).validate_json(
    files("idlink.data").joinpath("discourse_forums.json").read_bytes()
)
DISCOURSE_HOSTS = {forum.name: forum.host for forum in FORUMS}


class ForumUser(BaseModel):
    """Read only the public stable ID and account name, discarding other fields."""

    model_config = ConfigDict(strict=True)
    id: int
    username: str


class ForumResponse(BaseModel):
    """Login pages and error envelopes cannot satisfy this schema."""

    user: ForumUser


class ForumMissing(BaseModel):
    """Only a structured not-found envelope establishes absence."""

    error_type: str
    errors: list[str] = Field(min_length=1)


class DiscoursePlugin(PlatformPlugin):
    """No API key, enumeration, posts, avatars or authenticated endpoints."""

    def __init__(self, http: PublicHTTP, name: str, host: str) -> None:
        self.http, self.name, self.host = http, name, host

    async def fetch(self, username: str) -> Profile | None:
        """Bind the returned stable account to the requested nickname before reporting it."""
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,59}", username):
            raise ValueError("invalid forum username")
        route = f"https://{self.host}/u/{quote(username, safe='')}"
        response = await self.http.get(route + ".json")
        if response.status_code == 404:
            try:
                missing = ForumMissing.model_validate_json(response.content)
            except ValidationError as exc:
                raise PluginError(
                    "404 without a Discourse error envelope", kind="unverified"
                ) from exc
            if missing.error_type == "not_found":
                return None
            raise PluginError("ambiguous Discourse error", kind="unverified")
        if response.status_code != 200:
            raise PluginError(
                f"forum HTTP {response.status_code}; existence unknown",
                kind="blocked" if response.status_code in {401, 403, 429} else "http",
            )
        try:
            account = ForumResponse.model_validate_json(response.content).user
        except ValidationError as exc:
            raise PluginError("invalid forum account response", kind="unverified") from exc
        if not account.id or account.username.casefold() != username.casefold():
            raise PluginError("forum identity does not match requested nickname", kind="unverified")
        return Profile(
            platform=self.name,
            username=account.username,
            url=f"https://{self.host}/u/{quote(account.username, safe='')}",
            fetched_at=datetime.now(UTC),
        )
