"""Mathematical acceptance tests, including the contradictory original criterion."""

import math

import pytest

from idlink.core.models import Signal
from idlink.core.scoring import posterior, verdict


def signal(name: str, weight: float) -> Signal:
    return Signal(name=name, log_lr=weight, explanation="Synthetic test evidence")


def test_prior_and_links_only() -> None:
    assert posterior([]) == pytest.approx(0.01)
    assert posterior([signal("links", 6)]) == pytest.approx(math.exp(6) / (99 + math.exp(6)))
    assert posterior([signal("links", 6), signal("avatar", 4)]) > 0.85


@pytest.mark.parametrize("weight", [0, 1, 5, 20, 1e100])
def test_without_links_never_exceeds_85_percent(weight: float) -> None:
    assert posterior([signal("avatar", weight)]) <= 0.85
    assert posterior([signal("links", 0), signal("avatar", weight)]) <= 0.85


def test_other_evidence_cap_and_contradictions() -> None:
    assert posterior([signal("avatar", 100)]) == posterior([signal("avatar", 5)])
    assert posterior([signal("avatar", 4), signal("contradiction", -1.5)]) < posterior(
        [signal("avatar", 4)]
    )
    assert math.isfinite(posterior([signal("contradiction", -10000)]))
    with pytest.raises(ValueError):
        posterior([signal("links", 6), signal("links", 6)])


def test_verdict_boundaries() -> None:
    assert verdict(0.2999) == "связь маловероятна"
    assert verdict(0.30) == verdict(0.60) == "возможна"
    assert verdict(0.6001) == "вероятно связаны"
