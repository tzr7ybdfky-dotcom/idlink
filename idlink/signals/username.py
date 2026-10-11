"""Conservative name similarity with a replaceable common-name denylist."""

from importlib.resources import files

from rapidfuzz.distance import JaroWinkler

from idlink.core.models import Profile, Signal


def normalize(value: str) -> str:
    """Apply the specified lowercase and punctuation removal only."""
    return value.lower().translate(str.maketrans("", "", "._-"))


def common_names() -> frozenset[str]:
    """Read the bundled, provenance-documented conservative denylist."""
    content = files("idlink.data").joinpath("common_usernames.txt").read_text(encoding="utf-8")
    return frozenset(
        normalize(x.strip()) for x in content.splitlines() if x.strip() and not x.startswith("#")
    )


def compare(a: Profile, b: Profile, common: frozenset[str] | None = None) -> Signal:
    """A common name at either endpoint suppresses all name evidence."""
    left, right = normalize(a.username), normalize(b.username)
    common = common_names() if common is None else frozenset(normalize(x) for x in common)
    rarity = min(1.0, min(len(left), len(right)) / 12)
    if left in common or right in common or a.platform == "gravatar" or b.platform == "gravatar":
        rarity = 0.0
    exact = bool(left) and left == right
    similar = bool(left and right) and JaroWinkler.normalized_similarity(left, right) >= 0.92
    weight = (1.0 if exact else 0.5 if similar else 0.0) * rarity
    kind = "точное" if exact else "близкое" if similar else "нет"
    return Signal(
        name="username",
        log_lr=weight,
        explanation=f"Совпадение ника: {kind}; rarity={rarity:.3f}; вклад {weight:.3f}.",
        counter="Ник может быть занят разными людьми; rarity по длине — эвристика.",
    )
