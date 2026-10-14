"""Search results link to browser pages, never raw account API endpoints."""

import pytest

from idlink.core.catalog import SOURCES
from idlink.core.profile_urls import is_api_url, public_profile_url


@pytest.mark.parametrize(
    "url",
    [
        "https://api.mojang.com/users/profiles/minecraft/alice",
        "https://www.bandlab.com/api/v1.3/users/alice",
        "https://forum.example/u/alice/summary.json",
        "https://pathfinder-api.kai.w3spaces.com/public-profile-api/alice",
    ],
)
def test_api_endpoints_are_identified(url: str) -> None:
    assert is_api_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://community.apollographql.com/u/alice",
        "https://wiki.placeholderapi.com/users/alice/",
        "https://git.mtapi.io/alice",
    ],
)
def test_public_hosts_with_api_in_name_remain_usable(url: str) -> None:
    assert not is_api_url(url)


def test_correct_profile_page_and_unknown_api_suppression() -> None:
    assert public_profile_url("Minecraft", "alice", "https://api.mojang.com/users/alice") == (
        "https://namemc.com/profile/alice"
    )
    assert public_profile_url("Unknown", "alice", "https://api.example/alice") is None
    assert public_profile_url("GitHub", "alice", "https://github.com/alice") == (
        "https://github.com/alice"
    )


def test_all_automatic_username_sources_have_public_profile_routes() -> None:
    routes = []
    for source in SOURCES:
        if source.automatic and source.input_kind == "username" and source.template:
            assert not is_api_url(source.template), source.label
            routes.append(source.template.rstrip("/").casefold())
    assert len(routes) == len(set(routes))
