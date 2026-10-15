"""Public server metadata only; control-account identities are never bundled."""

import hashlib
import re
from importlib.resources import files
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator


class FederatedServer(BaseModel):
    """A server passed anonymous metadata and negative-account endpoint checks."""

    model_config = ConfigDict(extra="forbid")
    domain: str = Field(pattern=r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
    software: Literal["mastodon-compatible"]
    version: str
    checked_at: str
    positive_control: Literal["found", "not_tested"]
    negative_control: Literal["missing"]

    @field_validator("version")
    @classmethod
    def numeric_version(cls, value: str) -> str:
        """Keep only the version number, not arbitrary server-supplied suffixes."""
        match = re.match(r"[4-9]\.\d+\.\d+", value)
        if match is None:
            raise ValueError("unsupported Mastodon-compatible version")
        return match.group()

    @property
    def name(self) -> str:
        """Stable identifier independent of the snapshot order."""
        return "fediverse-" + hashlib.sha256(self.domain.encode()).hexdigest()[:16]

    @property
    def template(self) -> str:
        """Browser-facing local profile, never an API or federated cached copy."""
        return f"https://{self.domain}/@{{}}"


SERVERS = TypeAdapter(list[FederatedServer]).validate_json(
    files("idlink.data").joinpath("fediverse_servers.json").read_bytes()
)
