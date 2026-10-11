"""Robots wildcard, precedence and agent-group edge cases."""

from idlink.core.robots import RobotsPolicy


def test_longest_rule_and_wildcards() -> None:
    policy = RobotsPolicy(
        "User-agent: *\nDisallow: /users/*/private/\n"
        "Allow: /users/alex/private/public$\nCrawl-delay: 10"
    )
    assert not policy.can_fetch("https://example.org/users/alex/private/data")
    assert policy.can_fetch("https://example.org/users/alex/private/public")
    assert not policy.can_fetch("https://example.org/users/alex/private/public/more")
    assert policy.delay == 10


def test_specific_agent_groups_merge_and_override_wildcard() -> None:
    policy = RobotsPolicy(
        "User-agent: *\nDisallow: /\nUser-agent: idlink\nDisallow: /x\n"
        "User-agent: idlink\nAllow: /x\nDisallow: /y"
    )
    assert policy.can_fetch("https://example.org/x")
    assert not policy.can_fetch("https://example.org/y")
    assert policy.can_fetch("https://example.org/z")
