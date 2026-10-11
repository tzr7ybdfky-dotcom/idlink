"""Contract for public, unauthenticated platform plugins."""

from abc import ABC, abstractmethod

from idlink.core.models import Profile


class PluginError(Exception):
    """Network, access-policy or malformed upstream response failure."""


class PlatformPlugin(ABC):
    """Fetch one public profile; missing profiles return None."""

    name: str

    @abstractmethod
    async def fetch(self, username: str) -> Profile | None:
        """Fetch derived public data or raise PluginError on upstream failure."""
