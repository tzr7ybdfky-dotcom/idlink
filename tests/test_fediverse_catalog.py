"""Federated server enrollment requires real endpoint controls, not guessed URLs."""

import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from idlink.core.fediverse import FederatedServer
from idlink.core.http import PublicHTTP
from idlink.core.ratelimit import DomainRateLimiter
from tools.discover_fediverse import public_domain, verify
from tools.import_fediverse import import_servers


@pytest.mark.parametrize(
    "domain", ["localhost", "127.0.0.1", "host.internal", "a/b.org", "a.org:443"]
)
def test_discovery_rejects_non_public_dns_names(domain: str) -> None:
    assert not public_domain(domain)


@pytest.mark.parametrize("fault", ["", "catch_all", "wrong_user", "blocked", "wrong_domain"])
async def test_enrollment_requires_matching_positive_and_negative_controls(fault: str) -> None:
    calls = []
    account = {
        "id": "12",
        "username": "alice",
        "acct": "alice",
        "url": "https://fixture.example/@alice",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path == "/api/v2/instance":
            return httpx.Response(
                200,
                json={
                    "domain": "other.example" if fault == "wrong_domain" else "fixture.example",
                    "version": "4.5.0",
                    "configuration": {},
                    "contact": {"account": account},
                },
            )
        username = request.url.params["acct"]
        if fault == "blocked":
            return httpx.Response(403)
        if username != "alice":
            if fault == "catch_all":
                return httpx.Response(200, json=account)
            return httpx.Response(404, json={"error": "Record not found"})
        result = account | ({"username": "other"} if fault == "wrong_user" else {})
        return httpx.Response(200, json=result)

    async def sleep(delay: float) -> None:
        pass

    async with PublicHTTP(
        "https://example.org/idlink",
        respect_robots=False,
        limiter=DomainRateLimiter(sleep=sleep),
        transport=httpx.MockTransport(handler),
    ) as http:
        row = await verify(http, "fixture.example")
    if fault:
        assert row is None
    else:
        assert row is not None
        assert row["positive_control"] == "found"
        assert row["negative_control"] == "missing"
        assert "alice" not in json.dumps(row)
        assert "contact" not in row
        assert len(calls) == 3


def test_import_deduplicates_and_refuses_profile_fields(tmp_path: Path) -> None:
    row = {
        "domain": "fixture.example",
        "software": "mastodon-compatible",
        "version": "4.5.0",
        "checked_at": "2026-10-15T00:00:00+00:00",
        "positive_control": "found",
        "negative_control": "missing",
    }
    snapshot = tmp_path / "servers.jsonl"
    snapshot.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n")
    servers = import_servers(snapshot)
    assert len(servers) == 1
    assert servers[0].template == "https://fixture.example/@{}"
    with pytest.raises(ValidationError):
        FederatedServer.model_validate(row | {"username": "private-account"})
