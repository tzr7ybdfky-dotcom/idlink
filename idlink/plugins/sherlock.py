"""Anonymous Sherlock-compatible existence heuristics, not identity verification."""

import re
from datetime import UTC, datetime
from importlib.resources import files
from urllib.parse import quote, urlsplit

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, TypeAdapter

from idlink.core.http import PublicHTTP
from idlink.core.models import Profile
from idlink.plugins.base import PlatformPlugin, PluginError


class ProbeRule(BaseModel):
    """Keep detection rules only; never import example usernames or extra headers."""

    label: str
    url: str
    probe: str
    kind: str
    errors: list[str] = Field(default_factory=list)
    error_url: str = ""
    pattern: str = ""
    evidence: str = ""


RULES = {
    r.label.casefold(): r
    for r in TypeAdapter(list[ProbeRule]).validate_json(
        files("idlink.data").joinpath("probe_rules.json").read_bytes()
    )
}


# Check original public pages, never unofficial mirrors used by some upstream rules.
SOCIAL_RULES = {
    "telegram": ProbeRule(
        label="Telegram",
        url="https://t.me/{}",
        probe="https://t.me/{}",
        kind="message",
        errors=RULES["telegram"].errors,
        pattern=r"[A-Za-z][A-Za-z0-9_]{3,30}[A-Za-z0-9]",
        evidence="telegram",
    ),
    "instagram": ProbeRule(
        label="Instagram",
        url="https://www.instagram.com/{}/",
        probe="https://www.instagram.com/{}/",
        kind="message",
        errors=["Sorry, this page isn't available."],
        evidence="username",
    ),
    "facebook": ProbeRule(
        label="Facebook",
        url="https://www.facebook.com/{}",
        probe="https://www.facebook.com/{}",
        kind="message",
        errors=["This content isn't available right now"],
        evidence="profile-meta",
    ),
    "tiktok": RULES["tiktok"].model_copy(update={"evidence": "uniqueId"}),
    "linkedin": RULES["linkedin"].model_copy(update={"evidence": "profile-meta"}),
    "reddit": RULES["reddit"],
    "x / twitter": ProbeRule(
        label="X / Twitter",
        url="https://x.com/{}",
        probe="https://x.com/{}",
        kind="message",
        errors=["This account doesn’t exist"],
        pattern=r"[A-Za-z0-9_]{1,15}",
        evidence="screen_name",
    ),
}
RULES.update(SOCIAL_RULES)
RULES["twitter"] = SOCIAL_RULES["x / twitter"]


def page_evidence(rule: ProbeRule, body: str, username: str, url: str) -> bool:
    """Require public page evidence for sites whose login shell returns HTTP 200."""
    if not rule.evidence:
        return True
    soup = BeautifulSoup(body, "html.parser")
    if rule.evidence == "telegram":
        title = soup.select_one(".tgme_page_title span")
        action = soup.select_one("a.tgme_action_button[href]")
        return bool(
            title
            and title.get_text(strip=True)
            and action
            and str(action.get("href")).lower() == "tg://resolve?domain=" + username.lower()
        )
    if rule.evidence == "profile-meta":
        locator = soup.select_one('meta[property="og:url"]')
        kind = soup.select_one('meta[property="og:type"]')
        return bool(
            locator
            and kind
            and str(kind.get("content")) == "profile"
            and str(locator.get("content")).rstrip("/") == url.rstrip("/")
        )
    key = re.escape(rule.evidence)
    name = re.escape(username)
    return bool(re.search(r'"' + key + r'"\s*:\s*"' + name + r'"', body, re.IGNORECASE))


class SherlockPlugin(PlatformPlugin):
    """A positive result is a URL candidate based on a site's negative-page rule."""

    def __init__(self, http: PublicHTTP, name: str, rule: ProbeRule) -> None:
        self.http, self.name, self.rule = http, name, rule

    async def fetch(self, username: str) -> Profile | None:
        """Respect the shared HTTP policy and distinguish challenges from missing pages."""
        rule = self.rule
        if rule.pattern and not re.fullmatch(rule.pattern, username):
            raise ValueError("nickname does not match platform format")
        encoded = quote(username, safe="")
        url, probe = rule.url.replace("{}", encoded), rule.probe.replace("{}", encoded)
        # A nickname cannot introduce a host label separator or credentials.
        if urlsplit(probe).scheme != "https" or urlsplit(probe).username:
            raise PluginError("unsafe probe URL")
        response = await self.http.get(probe)
        status = response.status_code
        if status in {401, 403, 429}:
            raise PluginError(f"access blocked: HTTP {status}")
        if status == 404:
            return None
        if 300 <= status < 400:
            location = response.headers.get("location", "")
            if rule.kind == "response_url" and rule.error_url and location == rule.error_url:
                return None
            raise PluginError("redirect not followed; existence unknown")
        if status != 200:
            raise PluginError(f"unexpected HTTP {status}; existence unknown")
        plain = response.text
        lower = plain.lower()
        if any(
            marker in lower
            for marker in (
                "cf-chl-",
                "g-recaptcha",
                "hcaptcha",
                "verify you are human",
                "checking your browser",
                "<title>just a moment",
                "access denied",
            )
        ):
            raise PluginError("challenge or access restriction; existence unknown")
        if not plain.strip():
            raise PluginError("empty response; existence unknown")
        if rule.kind == "message" and any(error in plain for error in rule.errors):
            return None
        if not page_evidence(rule, plain, username, url):
            raise PluginError("public profile evidence missing; existence unknown")
        if rule.kind not in {"message", "status_code", "response_url"}:
            raise PluginError("unsupported detection rule")
        return Profile(
            platform=self.name,
            username=username,
            url=url,
            fetched_at=datetime.now(UTC),
        )
