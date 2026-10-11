"""Avatar acceptance boundaries and real in-memory image decoding."""

from datetime import UTC, datetime
from io import BytesIO

import pytest
from PIL import Image

from idlink.core.models import Profile
from idlink.signals.avatar import compare, phash_bytes


@pytest.mark.parametrize("distance,weight", [(0, 4.0), (4, 4.0), (5, 1.5), (8, 1.5), (9, 0)])
def test_hamming_boundaries(distance: int, weight: float) -> None:
    a = Profile(
        platform="a",
        username="x",
        url="https://example.org/a",
        avatar_phash=0,
        fetched_at=datetime.now(UTC),
    )
    b = a.model_copy(update={"avatar_phash": (1 << distance) - 1})
    assert compare(a, b).log_lr == weight
    assert compare(a.model_copy(update={"avatar_is_default": True}), b).log_lr == 0


def test_hash_image_in_memory() -> None:
    stream = BytesIO()
    Image.new("RGB", (32, 32), "red").save(stream, format="PNG")
    assert 0 <= phash_bytes(stream.getvalue()) < 2**64
    with pytest.raises(ValueError):
        phash_bytes(b"not an image")
