"""Bio overlap, explicit identifiers, language caveats and UTC activity."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from idlink.core.models import Profile
from idlink.signals import activity, bio


def profile(tokens: frozenset[str] = frozenset(), hist: tuple[int, ...] | None = None) -> Profile:
    return Profile(
        platform="demo",
        username="user",
        url="https://example.org/u",
        bio_tokens=tokens,
        activity_hist=hist,
        fetched_at=datetime.now(UTC),
    )


def test_bio_overlap_and_identifiers() -> None:
    a = profile(bio.tokenize("astronomy robotics user@example.org @rarehandle"))
    b = profile(bio.tokenize("astronomy robotics user@example.org @rarehandle"))
    signals = bio.compare(a, b)
    assert signals[0].log_lr == 1
    assert signals[1].log_lr == 3
    assert "user@example.org" not in a.bio_tokens
    assert "user@example.org" not in str(signals)
    assert bio.compare(profile(bio.tokenize("the and a")), profile())[0].log_lr == 0


def test_domains_and_languages() -> None:
    assert "id:domain:example.org" in bio.tokenize("https://example.org/about")
    assert "id:domain:github.com" not in bio.tokenize("https://github.com/demo")
    ru = profile(bio.tokenize("Разрабатываю телескопы и изучаю далёкие галактики"))
    en = profile(bio.tokenize("Researching astronomy and exploring distant galaxies"))
    assert bio.compare(ru, en)[2].log_lr == -1.5
    assert bio.compare(ru, profile())[2].log_lr == 0


def test_activity_minimum_and_similarity() -> None:
    a = profile(hist=(30,) + (0,) * 23)
    assert activity.compare(a, a).log_lr == 0.5
    assert activity.compare(a, profile(hist=(29,) + (0,) * 23)).log_lr == 0
    assert activity.compare(a, profile(hist=(0, 30) + (0,) * 22)).log_lr == 0
    assert activity.compare(a, profile()).log_lr == 0


def test_histogram_converts_to_utc() -> None:
    event = datetime(2026, 1, 1, 3, tzinfo=timezone(timedelta(hours=3)))
    assert activity.histogram([event] * 30) == (30,) + (0,) * 23
    with pytest.raises(ValueError):
        activity.histogram([datetime(2026, 1, 1)])
