"""Common names, exact link matching and reciprocal links."""

from datetime import UTC, datetime

from idlink.core.models import Profile
from idlink.signals import links, username


def profile(name: str, url: str, outbound: frozenset[str] = frozenset()) -> Profile:
    return Profile(
        platform="github",
        username=name,
        url=url,
        outbound_links=outbound,
        fetched_at=datetime.now(UTC),
    )


def test_common_nick_no_contribution() -> None:
    a = profile("alex", "https://github.com/alex")
    assert username.compare(a, a).log_lr == 0
    assert username.compare(a, a.model_copy(update={"username": "a_l-e.x"})).log_lr == 0


def test_normalization_and_similarity() -> None:
    a = profile("rare-long-name", "https://github.com/a")
    b = a.model_copy(update={"username": "Rare.Long_Name"})
    assert username.compare(a, b, frozenset()).log_lr == 1
    b = a.model_copy(update={"username": "rare-long-nam"})
    assert username.compare(a, b, frozenset()).log_lr == 0.5 * 11 / 12


def test_explicit_links_only() -> None:
    a = profile("a", "https://github.com/a", frozenset({"https://example.org/b/"}))
    b = profile("b", "https://example.org/b", frozenset({"https://github.com/a#bio"}))
    assert links.compare(a, b).log_lr == 6
    assert links.compare(a, b.model_copy(update={"outbound_links": frozenset()})).log_lr == 3
    b = b.model_copy(update={"url": "https://example.org/c", "outbound_links": frozenset()})
    assert links.compare(a, b).log_lr == 0
