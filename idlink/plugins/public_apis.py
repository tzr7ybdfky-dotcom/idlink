"""Small anonymous adapters for documented public profile APIs."""

import re
from datetime import UTC, datetime
from urllib.parse import quote, urlencode

from bs4 import BeautifulSoup
from pydantic import BaseModel, ValidationError

from idlink.core.http import PublicHTTP
from idlink.core.models import Profile
from idlink.plugins.base import PlatformPlugin, PluginError
from idlink.signals.bio import tokenize


class HNUser(BaseModel):
    """Keep only the public username and temporary self-description."""

    id: str
    about: str = ""


class Basics(BaseModel):
    """Keybase public account locator."""

    username: str


class Biography(BaseModel):
    """Only biography text is transformed to tokens."""

    bio: str | None = None


class KeybaseUser(BaseModel):
    """Ignore keys, proofs, addresses and other unneeded data."""

    basics: Basics
    profile: Biography | None = None


class APIStatus(BaseModel):
    """Application status must succeed even when HTTP is 200."""

    code: int


class Lookup(BaseModel):
    """An absent Keybase user is a null entry."""

    status: APIStatus
    them: list[KeybaseUser | None]


class WikiUser(BaseModel):
    """MediaWiki marks unavailable accounts with missing or invalid."""

    name: str
    missing: object | None = None
    invalid: object | None = None


class WikiQuery(BaseModel):
    """Validate the users array rather than assuming a 200 is a profile."""

    users: list[WikiUser]


class WikiResponse(BaseModel):
    """Error envelopes do not satisfy the expected schema."""

    query: WikiQuery


class PublicAPIPlugin(PlatformPlugin):
    """Exact nickname lookup, no enumeration or authentication."""

    def __init__(self, http: PublicHTTP, name: str, host: str = "") -> None:
        self.http, self.name, self.host = http, name, host

    async def fetch(self, username: str) -> Profile | None:
        """Project public API responses without retaining the raw document."""
        if not username or len(username) > 80 or any(c in username for c in "\n\r|/"):
            raise ValueError("invalid platform username")
        if self.name == "hackernews":
            endpoint = f"https://hacker-news.firebaseio.com/v0/user/{quote(username, safe='')}.json"
        elif self.name == "keybase":
            if not re.fullmatch(r"[A-Za-z0-9_]{2,16}", username):
                raise ValueError("invalid Keybase username")
            endpoint = "https://keybase.io/_/api/1.0/user/lookup.json?" + urlencode(
                {"usernames": username, "fields": "basics,profile"}
            )
        else:
            endpoint = f"https://{self.host}/w/api.php?" + urlencode(
                {
                    "action": "query",
                    "list": "users",
                    "ususers": username,
                    "format": "json",
                    "formatversion": "2",
                }
            )
        response = await self.http.get(endpoint)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise PluginError(
                f"{self.name} returned HTTP {response.status_code}",
                kind="blocked" if response.status_code in {401, 403, 429} else "http",
            )
        try:
            bio = ""
            if self.name == "hackernews":
                if response.json() is None:
                    return None
                user = HNUser.model_validate_json(response.content)
                if user.id != username:
                    raise ValueError("unexpected username")
                name, bio = user.id, user.about
                url = "https://news.ycombinator.com/user?" + urlencode({"id": name})
            elif self.name == "keybase":
                lookup = Lookup.model_validate_json(response.content)
                if lookup.status.code != 0 or len(lookup.them) != 1:
                    raise ValueError("unsuccessful lookup")
                person = lookup.them[0]
                if person is None:
                    return None
                name = person.basics.username
                if name.casefold() != username.casefold():
                    raise ValueError("unexpected username")
                bio = (person.profile.bio or "") if person.profile else ""
                url = f"https://keybase.io/{name}"
            else:
                users = WikiResponse.model_validate_json(response.content).query.users
                if len(users) != 1:
                    raise ValueError("unexpected user count")
                account = users[0]
                if {"missing", "invalid"} & account.model_fields_set:
                    return None
                name = account.name
                if name.replace("_", " ").casefold() != username.replace("_", " ").casefold():
                    raise ValueError("unexpected username")
                url = f"https://{self.host}/wiki/User:{quote(name.replace(' ', '_'), safe='')}"
        except (ValidationError, ValueError) as exc:
            raise PluginError(f"invalid {self.name} response", kind="response") from exc
        soup = BeautifulSoup("<div>" + bio + "</div>", "html.parser")
        links = {
            str(a.get("href"))
            for a in soup.select("a[href]")
            if str(a.get("href")).startswith(("https://", "http://"))
        }
        plain = soup.get_text(" ")
        links.update(re.findall(r"https?://[^\s<>]+", plain))
        return Profile(
            platform=self.name,
            username=name,
            url=url,
            bio_tokens=tokenize(plain),
            outbound_links=frozenset(links),
            fetched_at=datetime.now(UTC),
        )
