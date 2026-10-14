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


def test_engine_defaults_resolve_and_site_overrides_win(tmp_path: Path) -> None:
    engine = {"site": {"url": "{urlMain}{urlSubpath}/u/{username}", "checkType": "status_code"}}
    data = {
        "engines": {"DiscourseJson": engine},
        "sites": {
            "Forum Fixture": {
                "engine": "DiscourseJson",
                "urlMain": "https://forum.example",
                "urlSubpath": "/community",
                "tags": ["forum"],
                "urlProbe": "{urlMain}/users/{username}.json",
            },
            "Not Username": {
                "url": "https://other.example/{username}",
                "checkType": "status_code",
                "type": "email",
            },
        },
    }
    path = tmp_path / "engines.json"
    path.write_text(json.dumps(data))
    sources, rules = import_sites(path)
    assert len(sources) == len(rules) == 1
    assert sources[0]["template"] == "https://forum.example/community/u/{}"
    assert rules[0]["probe"] == "https://forum.example/users/{}.json"
    assert rules[0]["evidence"] == "discourse-user"


def test_engine_credentials_are_never_silently_dropped(tmp_path: Path) -> None:
    path = tmp_path / "authenticated.json"
    path.write_text(
        json.dumps(
            {
                "engines": {
                    "Auth": {
                        "site": {
                            "url": "{urlMain}/{username}",
                            "checkType": "status_code",
                            "headers": {"Authorization": "secret"},
                        }
                    }
                },
                "sites": {"Auth Fixture": {"engine": "Auth", "urlMain": "https://forum.example"}},
            }
        )
    )
    assert import_sites(path) == ([], [])


def test_whatsmyname_excludes_custom_requests_and_example_identities(tmp_path: Path) -> None:
    from tools.import_whatsmyname import import_sites as import_wmn

    valid = {
        "name": "WMN Fixture",
        "uri_check": "https://wmn.example/u/{account}",
        "e_code": 200,
        "e_string": "profile:username",
        "m_code": 404,
        "m_string": "User not found",
        "cat": "social",
        "known": ["never-export-this"],
    }
    sites = [valid, valid | {"name": "Duplicate"}]
    for key, value in (
        ("headers", {"Cookie": "secret"}),
        ("post_body", "query"),
        ("valid", False),
        ("e_code", 302),
    ):
        sites.append(valid | {"name": key, key: value})
    path = tmp_path / "wmn.json"
    path.write_text(json.dumps({"sites": sites}))
    sources, rules = import_wmn(path)
    assert len(sources) == len(rules) == 1
    assert rules[0]["presence"] == ["profile:username"]
    assert "never-export-this" not in json.dumps([sources, rules])
