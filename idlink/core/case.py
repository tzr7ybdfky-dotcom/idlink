"""Bounded case variants; never mutate letters or enumerate an exponential space."""

CASE_INSENSITIVE = frozenset(
    {"github", "telegram", "instagram", "facebook", "x", "reddit", "tiktok", "bluesky", "keybase"}
)


def case_candidates(platform: str, username: str) -> tuple[str, ...]:
    """Use one normalized lookup when known, otherwise at most four spellings."""
    if platform in CASE_INSENSITIVE or platform.startswith("discourse-"):
        return (username.lower(),)
    return tuple(
        dict.fromkeys((username, username.lower(), username.upper(), username.capitalize()))
    )
