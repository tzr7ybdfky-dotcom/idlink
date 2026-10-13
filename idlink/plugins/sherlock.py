"""Anonymous Sherlock-compatible existence heuristics, not identity verification."""

import json
import re
import secrets
from datetime import UTC, datetime
from importlib.resources import files
from urllib.parse import parse_qs, quote, urlsplit

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, TypeAdapter

from idlink.core.http import PublicHTTP
from idlink.core.models import Profile
from idlink.plugins.base import PlatformPlugin, PluginError
from idlink.plugins.evidence import identifies_profile, json_identity, soft_404


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
    presence: list[str] = Field(default_factory=list)


RULES = {
    r.label.casefold(): r
    for r in TypeAdapter(list[ProbeRule]).validate_json(
        files("idlink.data").joinpath("probe_rules.json").read_bytes()
    )
}
RULES.update(
    {
        r.label.casefold(): r
        for r in TypeAdapter(list[ProbeRule]).validate_json(
            files("idlink.data").joinpath("extra_probe_rules.json").read_bytes()
        )
    }
)


# Check original public pages, never unofficial mirrors used by some upstream rules.
SOCIAL_RULES = {
    "telegram": ProbeRule(
        label="Telegram",
        url="https://t.me/{}",
        probe="https://t.me/{}",
        kind="message",
        errors=[],
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
        title = soup.select_one(".tgme_page_title")
        actions = soup.select("a.tgme_action_button[href], a.tgme_action_button_new[href]")

        def resolves_requested_handle(href: str) -> bool:
            target = urlsplit(href)
            names = parse_qs(target.query).get("domain", [])
            return (
                target.scheme == "tg"
                and target.netloc == "resolve"
                and len(names) == 1
                and names[0].casefold() == username.casefold()
            )

        return bool(
            title
            and title.get_text(strip=True)
            and any(resolves_requested_handle(str(action.get("href", ""))) for action in actions)
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
    try:
        if json_identity(json.loads(body), username):
            return True
    except ValueError:
        pass
    for script in soup.find_all("script", attrs={"type": "application/json"}):
        try:
            if json_identity(json.loads(script.get_text()), username):
                return True
        except ValueError:
            continue
    return False


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
            raise PluginError("unsafe probe URL", kind="policy")
        response = await self.http.get(probe)
        status = response.status_code
        if status in {401, 403, 429}:
            raise PluginError(f"access blocked: HTTP {status}", kind="blocked")
        if status in {404, 410}:
            return None
        if 300 <= status < 400:
            location = response.headers.get("location", "")
            if rule.kind == "response_url" and rule.error_url and location == rule.error_url:
                return None
            raise PluginError("redirect not followed; existence unknown", kind="redirect")
        if status != 200:
            raise PluginError(f"unexpected HTTP {status}; existence unknown", kind="http")
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
            raise PluginError("challenge or access restriction; existence unknown", kind="blocked")
        if not plain.strip():
            raise PluginError("empty response; existence unknown", kind="response")
        if soft_404(plain):
            return None
        if rule.kind == "message" and any(error in plain for error in rule.errors):
            return None
        if rule.presence and not any(marker in plain for marker in rule.presence):
            raise PluginError(
                "positive detection marker missing; existence unknown", kind="unverified"
            )
        if not page_evidence(rule, plain, username, url):
            raise PluginError(
                "public profile evidence missing; existence unknown", kind="unverified"
            )
        if rule.kind not in {"message", "status_code", "response_url"}:
            raise PluginError("unsupported detection rule", kind="response")
        if not rule.evidence or rule.evidence == "profile-meta":
            if not identifies_profile(plain, username, url):
                raise PluginError("HTTP 200 without account identity evidence", kind="unverified")
            try:
                api_identity = json_identity(json.loads(plain), username)
            except ValueError:
                api_identity = False
            if not api_identity:
                await self._negative_control(username)
            if probe != url and urlsplit(probe)._replace(query="") != urlsplit(url)._replace(
                query=""
            ):
                page = await self.http.get(url)
                if page.status_code in {404, 410} or soft_404(page.text):
                    return None
                if page.status_code != 200 or not identifies_profile(page.text, username, url):
                    raise PluginError(
                        "profile URL not confirmed by API evidence", kind="unverified"
                    )
        return Profile(
            platform=self.name,
            username=username,
            url=url,
            fetched_at=datetime.now(UTC),
        )

    async def _negative_control(self, username: str) -> None:
        """A second, rare handle must explicitly be absent; catch-all pages remain unverified."""
        candidates = [secrets.token_hex(length) for length in (16, 12, 8, 6, 4)]
        name = next(
            (
                candidate
                for candidate in candidates
                if candidate != username
                and (not self.rule.pattern or re.fullmatch(self.rule.pattern, candidate))
            ),
            None,
        )
        if name is None:
            raise PluginError("cannot form a safe negative control", kind="unverified")
        response = await self.http.get(self.rule.probe.replace("{}", quote(name, safe="")))
        if response.status_code in {404, 410} or (
            response.status_code == 200
            and (
                soft_404(response.text) or any(error in response.text for error in self.rule.errors)
            )
        ):
            return
        raise PluginError(
            "control page does not establish absence; catch-all possible", kind="unverified"
        )
