"""Positive identity evidence and contextual soft-404 detection; HTTP 200 alone proves nothing."""

import json
import re
from html import unescape
from urllib.parse import unquote

from bs4 import BeautifulSoup, SoupStrainer

from idlink.signals.links import canonical_url

ABSENT = re.compile(
    r"(?:^404(?:\s|:|$)|page\s*(?:not found|doesn.t exist)|"
    r"(?:user|profile|account)\s+(?:not found|does not exist|doesn.t exist)|"
    r"страниц[аы]\s+(?:не найден[аы]|не существует)|пользователь\s+не найден|profile unavailable)",
    re.IGNORECASE,
)


def soft_404(body: str) -> bool:
    """Inspect visible page headings, never error strings embedded in JavaScript bundles."""
    headings = re.findall(r"<(?:title|h[12])\b[^>]*>(.*?)</(?:title|h[12])>", body, re.I | re.S)
    return any(ABSENT.search(unescape(re.sub(r"<[^>]*>", " ", text)).strip()) for text in headings)


def json_identity(value: object, username: str) -> bool:
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
                    "name",
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
    if username.casefold() not in unquote(body).casefold():
        return False
    try:
        if json_identity(json.loads(body), username):
            return True
    except ValueError:
        pass
    soup = BeautifulSoup(
        body, "html.parser", parse_only=SoupStrainer(["title", "h1", "meta", "link", "script"])
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
    labels = [tag.get_text(" ", strip=True) for tag in soup.find_all(["title", "h1"])]
    labels.extend(str(tag.get("content", "")) for tag in soup.select('meta[property="og:title"]'))
    if not any(identity.search(label) for label in labels):
        return False
    locators = [str(tag.get("content", "")) for tag in soup.select('meta[property="og:url"]')]
    locators.extend(str(tag.get("href", "")) for tag in soup.select('link[rel="canonical"]'))
    return bool(canonical_url(url)) and any(
        canonical_url(locator) == canonical_url(url) for locator in locators
    )
