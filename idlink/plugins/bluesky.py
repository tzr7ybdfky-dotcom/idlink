"""Exact public Bluesky lookup; no login, post history or handle enumeration."""

import re
from datetime import UTC, datetime
from urllib.parse import urlencode

from pydantic import BaseModel, ValidationError

from idlink.core.http import PublicHTTP
from idlink.core.models import Profile
from idlink.plugins.base import PlatformPlugin, PluginError
from idlink.signals.bio import tokenize


class PublicActor(BaseModel):
    """Discard counts, images, moderation metadata and all unrelated fields."""

    did: str
    handle: str
    description: str = ""


class BlueskyPlugin(PlatformPlugin):
    """A bare nickname targets exactly its standard bsky.social handle."""

    name = "bluesky"

    def __init__(self, http: PublicHTTP) -> None:
        self.http = http

    async def fetch(self, username: str) -> Profile | None:
        """Convert only a verified exact handle and public biography to a profile."""
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", username):
            raise ValueError("invalid Bluesky nickname")
        handle = username.lower() + ".bsky.social"
        response = await self.http.get(
            "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile?"
            + urlencode({"actor": handle})
        )
        try:
            if response.status_code == 400:
                error = response.json()
                if error.get("error") == "ProfileNotFound":
                    return None
            if response.status_code != 200:
                raise PluginError(
                    f"bluesky returned HTTP {response.status_code}",
                    kind="blocked" if response.status_code in {401, 403, 429} else "http",
                )
            actor = PublicActor.model_validate_json(response.content)
            if actor.handle.casefold() != handle or not actor.did.startswith("did:"):
                raise ValueError("unexpected Bluesky handle")
        except (ValidationError, ValueError, AttributeError) as exc:
            raise PluginError("invalid bluesky response", kind="response") from exc
        return Profile(
            platform=self.name,
            username=username.lower(),
            url=f"https://bsky.app/profile/{handle}",
            bio_tokens=tokenize(actor.description),
            outbound_links=frozenset(re.findall(r"https?://[^\s<>]+", actor.description)),
            fetched_at=datetime.now(UTC),
        )
