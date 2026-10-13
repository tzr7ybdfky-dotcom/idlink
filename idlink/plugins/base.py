"""Contract for public, unauthenticated platform plugins."""

from abc import ABC, abstractmethod
from typing import Literal

from idlink.core.models import Profile

ErrorKind = Literal[
    "network",
    "dns",
    "timeout",
    "robots",
    "blocked",
    "http",
    "response",
    "redirect",
    "unverified",
    "policy",
]


class PluginError(Exception):
    """Network, access-policy or evidence failure with a machine-readable reason."""

    def __init__(self, message: str, *, kind: ErrorKind = "network") -> None:
        super().__init__(message)
        self.kind = kind


class PlatformPlugin(ABC):
    """Fetch one public profile; missing profiles return None."""

    name: str

    @abstractmethod
    async def fetch(self, username: str) -> Profile | None:
        """Fetch derived public data or raise PluginError on upstream failure."""
