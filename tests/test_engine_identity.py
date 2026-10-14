"""API engine rules bind a stable ID to exactly the requested local account."""

import json

import httpx
import pytest

from idlink.core.http import PublicHTTP
from idlink.plugins.base import PluginError
from idlink.plugins.sherlock import ProbeRule, SherlockPlugin, engine_identity

CASES = [
    ("discourse-user", {"user": {"id": 12, "username": "alice"}}),
    ("mastodon-user", {"id": "12", "username": "alice", "acct": "alice"}),
    ("lemmy-user", {"person_view": {"person": {"id": 12, "name": "alice", "local": True}}}),
    ("mediawiki-user", {"query": {"users": [{"userid": 12, "name": "alice"}]}}),
]


@pytest.mark.parametrize("kind,payload", CASES)
async def test_engine_accepts_only_requested_account(kind: str, payload: dict[str, object]) -> None:
    body = json.dumps(payload)
    assert engine_identity(body, "alice", kind)
    with pytest.raises(PluginError):
        engine_identity(body, "other", kind)
    rule = ProbeRule(
        label="Fixture",
        url="https://fixture.example/u/{}",
        probe="https://fixture.example/api/{}",
        kind="status_code",
        evidence=kind,
    )
    async with PublicHTTP(
        "https://example.org/idlink",
        respect_robots=False,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
    ) as http:
        result = await SherlockPlugin(http, "fixture", rule).fetch("alice")
    assert result is not None and result.url == "https://fixture.example/u/alice"


@pytest.mark.parametrize("kind,_", CASES)
@pytest.mark.parametrize("body", ["{}", "<html>alice</html>", '{"user":{"username":"alice"}}'])
def test_engine_rejects_shells_and_missing_ids(kind: str, _: object, body: str) -> None:
    with pytest.raises(PluginError):
        engine_identity(body, "alice", kind)


def test_mediawiki_missing_and_mastodon_remote_account() -> None:
    assert not engine_identity(
        '{"query":{"users":[{"name":"alice","missing":""}]}}', "alice", "mediawiki-user"
    )
    with pytest.raises(PluginError):
        engine_identity(
            '{"id":"1","username":"alice","acct":"alice@remote.example"}', "alice", "mastodon-user"
        )
