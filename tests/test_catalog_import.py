"""An imported manifest contains only supported anonymous GET metadata."""

import json
from pathlib import Path

from tools.import_catalog import import_sites


def test_import_excludes_credentials_disabled_mirrors_and_unsafe_hosts(tmp_path: Path) -> None:
    valid: dict[str, object] = {
        "url": "https://fixture.example/user/{username}",
        "checkType": "message",
        "presenseStrs": ["public-profile"],
        "absenceStrs": ["missing"],
        "tags": ["forum"],
        "usernameClaimed": "must-not-be-imported",
    }
    cases = {"Fixture": valid}
    updates: dict[str, dict[str, object]] = {
        "Disabled": {"disabled": True},
        "Authenticated": {"headers": {"Cookie": "secret"}},
        "Mirror": {"source": "Fixture"},
        "POST": {"requestMethod": "POST"},
        "HTTP": {"url": "http://fixture.example/{username}"},
        "Subdomain": {"url": "https://{username}.example.org"},
        "BrokenPattern": {"regexCheck": "["},
        "Engine": {"engine": "XenForo"},
    }
    for label, update in updates.items():
        cases[label] = valid | update
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps({"sites": cases}))
    sources, rules = import_sites(path)
    assert len(sources) == len(rules) == 1
    assert sources[0]["category"] == "Форумы"
    assert rules[0]["presence"] == ["public-profile"]
    assert "must-not-be-imported" not in json.dumps([sources, rules])
