"""Ensure the entire suite is offline, even if an adapter regresses."""

import socket
from collections.abc import Iterator
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail immediately on attempts to open a real network connection."""
    monkeypatch.setenv("IDLINK_HTTP_ENGINE", "python")
    with (
        patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")),
        patch.object(socket, "getaddrinfo", side_effect=AssertionError("DNS forbidden")),
    ):
        yield
