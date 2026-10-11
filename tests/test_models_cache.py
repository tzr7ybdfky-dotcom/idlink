"""Validate strict models and the cache storage boundary."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from idlink.core.cache import ProfileCache
from idlink.core.models import Profile, Signal


def test_cache_allowlist_and_expiry(tmp_path: Path) -> None:
    profile = Profile(
        platform="github",
        username="demo",
        url="https://github.com/demo",
        bio_tokens=frozenset({"python"}),
        fetched_at=datetime.now(UTC),
    )
    cache = ProfileCache(tmp_path)
    cache.put(profile)
    data = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert set(data) == {"url", "phash", "tokens", "activity_hist", "fetched_at"}
    assert cache.get(profile.url) is not None
    assert cache.get(profile.url, now=profile.fetched_at + timedelta(days=2)) is None
    assert cache.get("https://github.com/missing") is None


def test_models_reject_invalid_data() -> None:
    with pytest.raises(ValidationError):
        Signal(name="bio", log_lr=1, explanation=" ")
    with pytest.raises(ValidationError):
        Profile(
            platform="github",
            username="x",
            url="https://github.com/x",
            activity_hist=(1,),
            fetched_at=datetime.now(UTC),
        )
    with pytest.raises(ValidationError):
        Profile(
            platform="github",
            username="x",
            url="https://github.com/x",
            fetched_at=datetime(2026, 1, 1),
        )
