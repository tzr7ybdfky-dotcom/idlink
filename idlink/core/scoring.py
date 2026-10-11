"""Heuristic Bayesian-style linkage; these percentages are not calibrated."""

import math
from typing import Literal

from idlink.core.models import Edge, Profile, Signal
from idlink.signals import activity, avatar, bio, links, username

PRIOR = 0.01
LOGIT0 = math.log(PRIOR / (1 - PRIOR))


def posterior(signals: list[Signal]) -> float:
    """Separate explicit-link evidence, cap other evidence and apply a stable sigmoid."""
    link_signals = [s for s in signals if s.name == "links"]
    if len(link_signals) > 1:
        raise ValueError("at most one links signal is allowed")
    link_weight = link_signals[0].log_lr if link_signals else 0.0
    if link_weight not in {0.0, 3.0, 6.0}:
        raise ValueError("links weight must be 0, 3 or 6")
    other = math.fsum(s.log_lr for s in signals if s.name != "links")
    logit = LOGIT0 + link_weight + min(5.0, other)
    probability = (
        1 / (1 + math.exp(-logit)) if logit >= 0 else math.exp(logit) / (1 + math.exp(logit))
    )
    return min(probability, 0.85) if link_weight <= 0 else probability


def verdict(probability: float) -> Literal["связь маловероятна", "возможна", "вероятно связаны"]:
    """Render the specified conservative boundary labels."""
    if probability < 0.30:
        return "связь маловероятна"
    return "возможна" if probability <= 0.60 else "вероятно связаны"


def score(a: Profile, b: Profile, extra: list[Signal] | None = None) -> Edge:
    """Score one pair using derived observations and optional explicit contradictions."""
    signals = [links.compare(a, b), avatar.compare(a, b), username.compare(a, b)]
    signals.extend(bio.compare(a, b))
    signals.append(activity.compare(a, b))
    signals.extend(extra or [])
    probability = posterior(signals)
    return Edge(
        a=a.url, b=b.url, probability=probability, signals=signals, verdict=verdict(probability)
    )
