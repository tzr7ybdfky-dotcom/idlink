"""Explicit profile-to-profile links, not shared domains or website menus."""

from urllib.parse import urlsplit, urlunsplit

from idlink.core.models import Profile, Signal


def canonical_url(value: str) -> str:
    """Ignore fragments and trailing slashes; retain paths and query identity."""
    parsed = urlsplit(value)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username:
        return ""
    host = parsed.hostname.lower().removeprefix("www.")
    try:
        port = parsed.port
    except ValueError:
        return ""
    if port not in {None, 80, 443}:
        host += f":{port}"
    path = parsed.path.rstrip("/")
    if host in {"github.com", "gravatar.com"}:
        path = path.lower()
    return urlunsplit(("https", host, path, parsed.query, ""))


def compare(a: Profile, b: Profile) -> Signal:
    """Assign +6 to reciprocal and +3 to one-way explicit profile URLs."""
    a_url, b_url = canonical_url(a.url), canonical_url(b.url)
    forward = bool(b_url) and b_url in {canonical_url(x) for x in a.outbound_links}
    reverse = bool(a_url) and a_url in {canonical_url(x) for x in b.outbound_links}
    weight = 6.0 if forward and reverse else 3.0 if forward or reverse else 0.0
    explanation = (
        "Профили явно ссылаются друг на друга; вклад +6."
        if forward and reverse
        else "Один профиль явно ссылается на второй; вклад +3."
        if forward or reverse
        else "Явных ссылок между профилями нет; вклад 0."
    )
    return Signal(
        name="links",
        log_lr=weight,
        explanation=explanation,
        counter="Ссылки могут означать сотрудничество, рекомендации или быть устаревшими.",
    )
