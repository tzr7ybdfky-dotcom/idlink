"""Named, combinable source categories shared by terminal and visual searches."""

from collections.abc import Iterable, Mapping

# Flag, Russian label, upstream tags. Several flags form a union, not an intersection.
CATEGORIES: dict[str, tuple[str, frozenset[str]]] = {
    "forums": ("Форумы", frozenset({"forum", "discussion"})),
    "social": ("Социальные сети", frozenset({"social", "messaging", "networking"})),
    "dev": ("Разработка", frozenset({"coding", "tech"})),
    "gaming": ("Игры", frozenset({"gaming", "games"})),
    "music": ("Музыка", frozenset({"music"})),
    "video": ("Видео и стримы", frozenset({"video", "streaming", "movies"})),
    "photo": ("Фотография", frozenset({"photo"})),
    "art": ("Искусство и дизайн", frozenset({"art", "design", "3d"})),
    "blogs": ("Блоги", frozenset({"blog", "writing", "books"})),
    "news": ("Новости", frozenset({"news"})),
    "science": ("Наука", frozenset({"science", "research"})),
    "education": ("Образование", frozenset({"education"})),
    "business": ("Работа и бизнес", frozenset({"business", "professional", "freelance"})),
    "shopping": ("Магазины", frozenset({"shopping"})),
    "sport": ("Спорт", frozenset({"sport"})),
    "travel": ("Путешествия", frozenset({"travel", "geosocial"})),
    "wikis": ("Вики", frozenset({"wiki"})),
}


def category_for_tags(tags: Iterable[str]) -> str:
    """Choose one display section while retaining every tag for source filtering."""
    values = set(tags)
    return next(
        (label for label, keys in CATEGORIES.values() if keys & values), "Другие сообщества"
    )


def selected_platforms(platforms: str, flags: Mapping[str, object]) -> str:
    """Apply category union, intersect an explicit source list and reject empty selections."""
    from idlink.core.catalog import SOURCES, USERNAME_PLATFORMS

    selected = [key for key in CATEGORIES if flags.get(key) is True]
    if not selected:
        return platforms
    names = {
        source.name
        for source in SOURCES
        if source.name in USERNAME_PLATFORMS
        and any(
            source.tags & CATEGORIES[key][1] or source.category == CATEGORIES[key][0]
            for key in selected
        )
    }
    if platforms not in {"all", "auto"}:
        requested = set(platforms.split(","))
        if not requested <= USERNAME_PLATFORMS:
            raise ValueError("Неизвестная или недоступная площадка в --platforms.")
        names &= requested
    if not names:
        raise ValueError("В выбранных категориях нет подходящих автоматических источников.")
    return ",".join(sorted(names))
