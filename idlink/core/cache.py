"""Minimal derived-data cache; never serialize an entire Profile."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from idlink.core.models import Profile


class CacheEntry(BaseModel):
    """Only fields explicitly permitted by the storage policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    url: str
    phash: int | None = Field(ge=0, lt=2**64)
    tokens: frozenset[str]
    activity_hist: tuple[int, ...] | None
    fetched_at: AwareDatetime


class ProfileCache:
    """Persist derived observations keyed by URL with an explicit lifetime."""

    def __init__(self, path: Path, ttl: timedelta = timedelta(hours=24)) -> None:
        self.path = path
        self.ttl = ttl

    def put(self, profile: Profile) -> None:
        """Store only the allowlisted projection, discarding default-avatar hashes."""
        from hashlib import sha256

        entry = CacheEntry(
            url=profile.url,
            phash=None if profile.avatar_is_default else profile.avatar_phash,
            tokens=profile.bio_tokens,
            activity_hist=profile.activity_hist,
            fetched_at=profile.fetched_at,
        )
        self.path.mkdir(parents=True, exist_ok=True)
        target = self.path / (sha256(profile.url.encode()).hexdigest() + ".json")
        temporary = target.with_suffix(".tmp")
        temporary.write_text(entry.model_dump_json(), encoding="utf-8")
        temporary.replace(target)

    def get(self, url: str, *, now: datetime | None = None) -> CacheEntry | None:
        """Return a fresh observation; corrupted or expired records are misses."""
        from hashlib import sha256

        target = self.path / (sha256(url.encode()).hexdigest() + ".json")
        try:
            entry = CacheEntry.model_validate_json(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        age = (now or datetime.now(UTC)) - entry.fetched_at
        return entry if entry.url == url and timedelta(0) <= age <= self.ttl else None
