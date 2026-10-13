"""Positive identity evidence and contextual soft-404 detection; HTTP 200 alone proves nothing."""

import json
import re
from html import unescape
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup, SoupStrainer

ABSENT = re.compile(
    r"(?:^404(?:\s|:|$)|page\s*(?:not found|doesn.t exist)|"
    r"(?:user|profile|account)\s+(?:not found|does not exist|doesn.t exist)|"
    r"страниц[аы]\s+(?:не найден[аы]|не существует)|пользователь\s+не найден|profile unavailable)",
    re.IGNORECASE,
)


def soft_404(body: str) -> bool:
    """Inspect visible page headings, never error strings embedded in JavaScript bundles."""
    headings = re.findall(r"<(?:title|h[12])\b[^>]*>(.*?)</(?:title|h[12])>", body, re.I | re.S)
    if not any(ABSENT.search(unescape(re.sub(r"<[^>]*>", " ", text)).strip()) for text in headings):
        return False
    # Raw templates inside scripts can contain <title>404</title>; only DOM headings count.
    soup = BeautifulSoup(body, "html.parser", parse_only=SoupStrainer(["title", "h1", "h2"]))
    return any(
        ABSENT.search(tag.get_text(" ", strip=True)) for tag in soup.find_all(["title", "h1", "h2"])
    )


def json_identity(value: object, username: str, *, allow_name: bool = False) -> bool:
    """Require an identity and stable account ID in the same object, ignoring route parameters."""
    pending = [value]
    name = username.casefold().lstrip("@")
    examined = 0
    while pending and examined < 2000:
        item = pending.pop()
        examined += 1
        if isinstance(item, dict):
            if item.get("error") or item.get("errors") or item.get("success") is False:
                continue
            identifiers = (
                item.get(key)
                for key in ("id", "uid", "userId", "user_id", "accountId", "did", "uuid", "rest_id")
            )
            has_id = any(
                isinstance(identifier, (str, int))
                and not isinstance(identifier, bool)
                and bool(identifier)
                for identifier in identifiers
            )
            matches = any(
                isinstance(item.get(key), str) and str(item[key]).casefold().lstrip("@") == name
                for key in (
                    "username",
                    "userName",
                    "login",
                    "handle",
                    "uniqueId",
                    "screen_name",
                    *(("name",) if allow_name else ()),
                )
            )
            if has_id and matches:
                return True
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item[:2000])
    return False


def identifies_profile(body: str, username: str, url: str) -> bool:
    """Bind public account metadata to the requested identity; URL echoes are insufficient."""
    try:
        if json_identity(json.loads(body), username, allow_name=minecraft_endpoint(url)):
            return True
    except ValueError:
        pass
    if body.lstrip().startswith("<?xml"):
        return False
    if username.casefold() not in unescape(unquote(body)).casefold():
        return False
    soup = BeautifulSoup(
        body,
        "html.parser",
        parse_only=SoupStrainer(["title", "h1", "h2", "meta", "link", "script"]),
    )
    for script in soup.find_all("script", attrs={"type": "application/json"}):
        try:
            if json_identity(json.loads(script.get_text()), username):
                return True
        except ValueError:
            continue
    meta = soup.select_one('meta[property="profile:username"]')
    if meta and str(meta.get("content", "")).casefold().lstrip("@") == username.casefold().lstrip(
        "@"
    ):
        return True
    identity = re.compile(r"(?<![\w.-])@?" + re.escape(username) + r"(?![\w.-])", re.I)
    labels = [tag.get_text(" ", strip=True) for tag in soup.find_all(["title", "h1", "h2"])]
    labels.extend(str(tag.get("content", "")) for tag in soup.select('meta[property="og:title"]'))
    labels.extend(str(tag.get("content", "")) for tag in soup.select('meta[name="twitter:title"]'))
    if any(identity.search(label) for label in labels):
        return True
    return False


def minecraft_endpoint(url: str) -> bool:
    """Only Mojang's documented account route uses name as its username field."""
    parsed = urlsplit(url)
    return parsed.hostname == "api.mojang.com" and parsed.path.startswith(
        "/users/profiles/minecraft/"
    )


def absence_marker(body: str, markers: list[str]) -> bool:
    """Require visible error phrases; JavaScript templates and metadata keys are ambiguous."""
    candidates = [marker for marker in markers if marker in body]
    if not candidates:
        return False
    try:
        value = json.loads(body)
        if isinstance(value, dict):
            errors = json.dumps([value.get("error"), value.get("errors")], ensure_ascii=False)
            if value.get("statusCode") in (404, 410, 10221) or re.search(
                r"not[_ -]found|no such user|unknown user|does not exist", errors, re.I
            ):
                return True
    except ValueError:
        pass
    if body.lstrip().startswith("<?xml"):
        return False
    soup = BeautifulSoup(body, "html.parser")
    visible = soup.get_text(" ", strip=True).casefold()
    for marker in candidates:
        phrase = BeautifulSoup(marker, "html.parser").get_text(" ", strip=True).casefold()
        if len(phrase) >= 8 and len(phrase.split()) >= 2 and phrase in visible:
            return True
    return False
