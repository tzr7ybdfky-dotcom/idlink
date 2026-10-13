"""Anonymous Sherlock-compatible existence heuristics, not identity verification."""

import re
from datetime import UTC, datetime
from importlib.resources import files
from urllib.parse import quote, urlsplit

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


RULES = {
    r.label.casefold(): r
    for r in TypeAdapter(list[ProbeRule]).validate_json(
        files("idlink.data").joinpath("probe_rules.json").read_bytes()
    )
}


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
        if rule.kind not in {"message", "status_code", "response_url"}:
            raise PluginError("unsupported detection rule")
        return Profile(
            platform=self.name,
            username=username,
            url=url,
            fetched_at=datetime.now(UTC),
        )
