"""Derived token overlap, explicit identifiers and conservative language evidence."""

import hashlib
import re

from idlink.core.models import Profile, Signal

STOPWORDS = frozenset(
    """
a an and are as at be by for from has have he her him i in is it its me my of on or our
she that the their them they this to us was we were will with you your developer engineer
а без бы был была были быть в вам вас весь во вот вы где да для до его ее её если есть
же за и из или им их к как ко кто ли мне мой мы на не но о об он она они от по при про
с со так то у уже что это я разработчик инженер
""".split()
)
COMMON_DOMAINS = frozenset(
    {
        "github.com",
        "habr.com",
        "gravatar.com",
        "gmail.com",
        "mail.ru",
        "outlook.com",
        "yandex.ru",
        "google.com",
        "linkedin.com",
    }
)


def tokenize(text: str) -> frozenset[str]:
    """Discard source text; emails become hashed identifier tokens."""
    text = text.casefold()
    tokens: set[str] = set()
    emails = re.findall(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", text)
    for email in emails:
        tokens.add("id:email:" + hashlib.sha256(email.encode()).hexdigest())
        text = text.replace(email, " ")
    for handle in re.findall(r"(?<!\w)@([\w.-]{3,})", text):
        tokens.add("id:handle:" + handle)
    for domain in re.findall(
        r"(?<![\w@])(?:https?://)?([a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,})(?=[/\s:]|$)", text
    ):
        if domain not in COMMON_DOMAINS:
            tokens.add("id:domain:" + domain)
    words = re.findall(r"[^\W\d_]{3,}", text, re.UNICODE)
    tokens.update(word for word in words if word not in STOPWORDS)
    cyrillic = len(re.findall(r"[а-яё]", text))
    latin = len(re.findall(r"[a-z]", text))
    total = cyrillic + latin
    if total >= 20:
        if cyrillic / total >= 0.9:
            tokens.add("lang:ru")
        elif latin / total >= 0.9:
            tokens.add("lang:en")
    return frozenset(tokens)


def compare(a: Profile, b: Profile) -> list[Signal]:
    """Check overlap of non-stopwords and shared uncommon explicit identifiers."""
    left = {x for x in a.bio_tokens if not x.startswith(("id:", "lang:")) and x not in STOPWORDS}
    right = {x for x in b.bio_tokens if not x.startswith(("id:", "lang:")) and x not in STOPWORDS}
    union = left | right
    overlap = len(left & right) / len(union) if union else 0.0
    shared_id = any(x.startswith("id:") for x in a.bio_tokens & b.bio_tokens)
    signals = [
        Signal(
            name="bio",
            log_lr=1.0 if overlap >= 0.3 else 0.0,
            explanation=f"Jaccard по содержательным токенам: {overlap:.3f}.",
            counter="Шаблонное био и профессиональные термины могут совпадать случайно.",
        ),
        Signal(
            name="bio_identifier",
            log_lr=3.0 if shared_id else 0.0,
            explanation="Общий явный идентификатор найден."
            if shared_id
            else "Общего явного идентификатора нет.",
            counter="Домены и handles могут быть общими; идентификатор можно скопировать.",
        ),
    ]
    languages_a = {x for x in a.bio_tokens if x.startswith("lang:")}
    languages_b = {x for x in b.bio_tokens if x.startswith("lang:")}
    different = bool(languages_a and languages_b and languages_a.isdisjoint(languages_b))
    signals.append(
        Signal(
            name="contradiction",
            log_lr=-1.5 if different else 0.0,
            explanation="Био написаны преимущественно на разных языках."
            if different
            else "Явного языкового противоречия не обнаружено.",
            counter="Человек может писать на нескольких языках; детектор видит алфавит.",
        )
    )
    return signals
