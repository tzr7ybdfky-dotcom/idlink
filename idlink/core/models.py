"""Validated domain models; profiles exist only in memory."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class Profile(BaseModel):
    """Derived public profile data, without source text or images."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    platform: str = Field(min_length=1)
    username: str = Field(min_length=1)
    url: str
    avatar_phash: int | None = Field(default=None, ge=0, lt=2**64)
    avatar_is_default: bool = False
    bio_tokens: frozenset[str] = frozenset()
    outbound_links: frozenset[str] = frozenset()
    activity_hist: tuple[int, ...] | None = None
    fetched_at: AwareDatetime

    @field_validator("activity_hist")
    @classmethod
    def validate_histogram(cls, value: tuple[int, ...] | None) -> tuple[int, ...] | None:
        """Require exactly 24 nonnegative UTC bins."""
        if value is not None and (len(value) != 24 or any(x < 0 for x in value)):
            raise ValueError("activity_hist must contain 24 nonnegative bins")
        return value


class Signal(BaseModel):
    """Evidence with an explanation and optional limitation."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    name: str = Field(min_length=1)
    log_lr: float
    explanation: str = Field(min_length=1)
    counter: str | None = None

    @field_validator("explanation")
    @classmethod
    def nonblank_explanation(cls, value: str) -> str:
        """Reject whitespace-only explanations."""
        if not value.strip():
            raise ValueError("explanation must not be blank")
        return value


class Edge(BaseModel):
    """Probabilistic association, never an identity assertion."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    a: str
    b: str
    probability: float = Field(ge=0, le=1)
    signals: list[Signal]
    verdict: Literal["связь маловероятна", "возможна", "вероятно связаны"]
