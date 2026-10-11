"""Habr policy notice: no network parser under the current service terms."""

from idlink.core.models import Profile
from idlink.plugins.base import PlatformPlugin, PluginError


class HabrPlugin(PlatformPlugin):
    """Refuse collection rather than treating a policy restriction as absence."""

    name = "habr"

    async def fetch(self, username: str) -> Profile | None:
        """No HTTP requests; use GitHub public API or seek Habr permission."""
        raise PluginError(
            "Habr отключён: условия ограничивают сбор и копирование данных; "
            "используйте GitHub или получите разрешение площадки."
        )
