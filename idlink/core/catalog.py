"""Reviewed source catalogue; availability is never inferred from a guessed URL."""

from importlib.resources import files

from pydantic import BaseModel, TypeAdapter

from idlink.plugins.discourse import FORUMS
from idlink.plugins.sherlock import RULES


class Source(BaseModel):
    """A supported lookup or a clearly labelled unavailable source."""

    name: str
    label: str
    category: str
    input_kind: str = "username"
    automatic: bool = True
    reason: str = "Официальный публичный API; robots.txt проверяется при запросе."
    host: str = ""
    template: str = ""
    tags: frozenset[str] = frozenset()


SOURCES = [
    Source(name="github", label="GitHub", category="Разработка"),
    Source(name="bluesky", label="Bluesky", category="Социальные сети"),
    Source(name="hackernews", label="Hacker News", category="Сообщества"),
    Source(name="keybase", label="Keybase", category="Публичные идентификаторы"),
    Source(name="wikipedia", label="Wikipedia (EN)", category="Вики", host="en.wikipedia.org"),
    Source(name="wikidata", label="Wikidata", category="Вики", host="www.wikidata.org"),
    Source(
        name="commons", label="Wikimedia Commons", category="Вики", host="commons.wikimedia.org"
    ),
    Source(name="gravatar", label="Gravatar", category="Аватары", input_kind="gravatar"),
    Source(
        name="website",
        label="Собственный домен",
        category="Сайты",
        input_kind="website",
        reason="Только заданный домен и rel=me; сначала проверьте условия сайта.",
    ),
    Source(
        name="habr",
        label="Habr",
        category="Сообщества",
        automatic=False,
        reason="Сбор отключён по условиям площадки; требуется разрешение.",
    ),
    Source(
        name="gitlab",
        label="GitLab",
        category="Разработка",
        automatic=False,
        reason="Users API требует авторизацию; автоматический поиск отключён.",
    ),
    Source(
        name="devto",
        label="DEV Community",
        category="Сообщества",
        automatic=False,
        reason="Условия ограничивают копирование и публичное использование; нужно уточнение.",
    ),
    *[
        Source(
            name=name,
            label=label,
            category="Социальные сети",
            automatic=False,
            reason="Анонимный адаптер не подключён: требуется проверка API и условий доступа.",
        )
        for name, label in [
            ("instagram", "Instagram"),
            ("facebook", "Facebook"),
            ("x", "X / Twitter"),
            ("vk", "VK"),
            ("telegram", "Telegram"),
            ("tiktok", "TikTok"),
            ("linkedin", "LinkedIn"),
            ("reddit", "Reddit"),
        ]
    ],
]
SOURCES.extend(
    Source(
        name=forum.name,
        label=forum.label,
        category="Форумы",
        tags=frozenset({"forum"}),
        template=f"https://{forum.host}/u/{{}}",
        reason="Публичный Discourse API; проверены положительный и отрицательный контроль.",
    )
    for forum in FORUMS
)
manual_sources = TypeAdapter(list[Source]).validate_json(
    files("idlink.data").joinpath("platforms.json").read_bytes()
)
manual_sources.extend(
    TypeAdapter(list[Source]).validate_json(
        files("idlink.data").joinpath("extra_platforms.json").read_bytes()
    )
)
by_label = {s.label.casefold(): s for s in manual_sources}
for source in SOURCES:
    imported = by_label.get(source.label.casefold())
    if imported:
        source.template = imported.template
    if source.host:
        source.automatic = False
        source.reason = "robots.txt запрещает выбранный API. Автопроверка отключена."
        source.template = f"https://{source.host}/wiki/User:{{}}"
existing = {s.label.casefold() for s in SOURCES}
SOURCES.extend(s for s in manual_sources if s.label.casefold() not in existing)
RESTRICTED = {"habr", "dev community", "gitlab"}
PROBE_SOURCES = {}
for source in SOURCES:
    rule = RULES.get(source.label.casefold())
    if (
        not source.automatic
        and rule
        and source.label.casefold() not in RESTRICTED
        and not source.host
    ):
        source.automatic = True
        source.reason = "Правило публичной GET-проверки; результат — эвристический кандидат."
        PROBE_SOURCES[source.name] = rule
USERNAME_PLATFORMS = frozenset(
    s.name for s in SOURCES if s.automatic and s.input_kind == "username"
)
WIKI_HOSTS = {s.name: s.host for s in SOURCES if s.host}
