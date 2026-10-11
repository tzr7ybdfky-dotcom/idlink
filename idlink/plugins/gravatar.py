"""Anonymous Gravatar image lookup using a user-supplied email hash."""

import hashlib
import re
from datetime import UTC, datetime

from idlink.core.http import PublicHTTP
from idlink.core.models import Profile
from idlink.plugins.base import PlatformPlugin, PluginError
from idlink.signals.avatar import phash_bytes


def email_hash(value: str) -> str:
    """Accept MD5/SHA-256 or hash an explicit email; never guess addresses."""
    value = value.strip().lower()
    if re.fullmatch(r"[0-9a-f]{32}|[0-9a-f]{64}", value):
        return value
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise ValueError("Gravatar requires an email or its MD5/SHA-256 hash")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class GravatarPlugin(PlatformPlugin):
    """Fetch a real public avatar; d=404 suppresses generated defaults."""

    name = "gravatar"

    def __init__(self, http: PublicHTTP) -> None:
        self.http = http

    async def fetch(self, username: str) -> Profile | None:
        """Keep the hash and derived image fingerprint, never the email or image."""
        identifier = email_hash(username)
        url = f"https://gravatar.com/avatar/{identifier}?d=404&s=200&r=g"
        response = await self.http.get(url)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise PluginError(f"Gravatar returned HTTP {response.status_code}")
        try:
            phash = phash_bytes(response.content)
        except ValueError as exc:
            raise PluginError("invalid Gravatar image") from exc
        # An avatar observation is not proof that a public profile page exists.
        return Profile(
            platform=self.name,
            username=identifier,
            url=url,
            avatar_phash=phash,
            fetched_at=datetime.now(UTC),
        )
