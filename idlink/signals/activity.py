"""UTC activity histograms with minimum-sample and automation caveats."""

import math
from collections.abc import Iterable
from datetime import UTC, datetime

from idlink.core.models import Profile, Signal


def histogram(events: Iterable[datetime]) -> tuple[int, ...]:
    """Bin only timezone-aware events into UTC hours."""
    bins = [0] * 24
    for event in events:
        if event.tzinfo is None or event.utcoffset() is None:
            raise ValueError("event timestamp must be timezone-aware")
        bins[event.astimezone(UTC).hour] += 1
    return tuple(bins)


def compare(a: Profile, b: Profile) -> Signal:
    """Contribute +0.5 only with >=30 events on both sides and cosine >=0.9."""
    left, right = a.activity_hist, b.activity_hist
    weight = 0.0
    explanation = "Недостаточно активности: нужно не менее 30 событий у каждого."
    if left is not None and right is not None and sum(left) >= 30 and sum(right) >= 30:
        dot = sum(x * y for x, y in zip(left, right, strict=True))
        norm = math.sqrt(sum(x * x for x in left) * sum(y * y for y in right))
        cosine = dot / norm
        weight = 0.5 if cosine >= 0.9 else 0.0
        explanation = f"Косинусное сходство 24 бинов UTC: {cosine:.3f}; вклад {weight:g}."
    return Signal(
        name="activity",
        log_lr=weight,
        explanation=explanation,
        counter="Часовой пояс, расписание и автоматизация дают похожую активность.",
    )
