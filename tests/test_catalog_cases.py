"""Reference coverage must bind to an exact endpoint and preserve disabled/invalid cases."""

import re

import pytest

from idlink.plugins.sherlock import ProbeRule
from tools.catalog_cases import Example, reference_roots


def test_random_controls_cover_every_supported_username_format() -> None:
    from idlink.core.catalog import PROBE_SOURCES, USERNAME_PLATFORMS
    from tools.catalog_cases import negative_roots

    roots = negative_roots()
    assert {name for name, _ in roots} == USERNAME_PLATFORMS
    for name, value in roots:
        rule = PROBE_SOURCES.get(name)
        assert not rule or not rule.pattern or re.fullmatch(rule.pattern, value)


def test_reference_coverage_uses_exact_urls_and_valid_handles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tools.catalog_cases as cases

    def rule(path: str) -> ProbeRule:
        return ProbeRule(
            label="fixture",
            url="https://fixture.example/" + path + "/{}",
            probe="https://fixture.example/" + path + "/{}",
            kind="status_code",
            pattern=r"[a-z]{5,12}",
        )

    monkeypatch.setattr(
        cases,
        "PROBE_SOURCES",
        {
            "valid": rule("user"),
            "disabled": rule("old"),
            "invalid": rule("other"),
            "unmatched": rule("new"),
        },
    )
    rows = [
        Example.model_validate(
            {"url": "https://fixture.example/user/{username}/", "usernameClaimed": "alice"}
        ),
        Example.model_validate(
            {"url": "https://fixture.example/old/{}", "username_claimed": "alice", "disabled": True}
        ),
        Example.model_validate(
            {"url": "https://fixture.example/other/{}", "usernameClaimed": "bad-handle"}
        ),
        Example.model_validate(
            {"url": "https://unrelated.example/new/{}", "usernameClaimed": "alice"}
        ),
    ]
    roots, disabled = reference_roots(rows)
    assert roots == [("valid", "alice")]
    assert disabled == frozenset({"disabled"})
