"""Case retries preserve letters, stop on success and do not repeat refusals."""

from collections import deque
from datetime import UTC, datetime

import pytest

from idlink.core.case import case_candidates
from idlink.core.collection import _fetch_queue
from idlink.core.models import Profile
from idlink.plugins.base import PlatformPlugin, PluginError


@pytest.mark.parametrize("name", ["telegram", "github", "bluesky", "discourse-example"])
def test_case_insensitive_platform_uses_one_lookup(name: str) -> None:
    assert case_candidates(name, "deMoUser") == ("demouser",)


def test_unknown_platform_uses_bounded_spellings_without_typos() -> None:
    assert case_candidates("hackernews", "deMoUser") == (
        "deMoUser",
        "demouser",
        "DEMOUSER",
        "Demouser",
    )
    assert case_candidates("hackernews", "123") == ("123",)


@pytest.mark.parametrize("blocked", [False, True])
async def test_case_retries_only_after_confirmed_absence(blocked: bool) -> None:
    calls: list[str] = []

    class Stub(PlatformPlugin):
        name = "hackernews"

        async def fetch(self, username: str) -> Profile | None:
            """Simulate a case-sensitive public account without network traffic."""
            calls.append(username)
            if blocked:
                raise PluginError("HTTP 429", kind="blocked")
            if username != "Demouser":
                return None
            return Profile(
                platform=self.name,
                username=username,
                url=f"https://news.ycombinator.com/user?id={username}",
                fetched_at=datetime.now(UTC),
            )

    results = [
        result
        async for result in _fetch_queue(
            {"hackernews": Stub()},
            deque([("hackernews", "deMoUser", 0)]),
            set(),
            1,
            check_case=True,
        )
    ]
    assert len(results) == 1
    assert calls == (["deMoUser"] if blocked else ["deMoUser", "demouser", "DEMOUSER", "Demouser"])
    assert isinstance(results[0][-1], PluginError if blocked else Profile)
