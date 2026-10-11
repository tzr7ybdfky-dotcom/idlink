"""In-memory pHash extraction and conservative avatar evidence."""

import warnings
from io import BytesIO

import imagehash
from PIL import Image, UnidentifiedImageError

from idlink.core.models import Profile, Signal


def phash_bytes(content: bytes) -> int:
    """Hash an image without writing bytes to disk; reject oversized images."""
    if len(content) > 5_000_000:
        raise ValueError("avatar exceeds 5 MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                if image.width * image.height > 4_000_000:
                    raise ValueError("avatar exceeds 4 million pixels")
                return int(str(imagehash.phash(image.convert("RGB"), hash_size=8)), 16)
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ) as exc:
        raise ValueError("invalid or oversized avatar") from exc


def compare(a: Profile, b: Profile) -> Signal:
    """Use Hamming distance only for non-default, available 64-bit hashes."""
    weight = 0.0
    explanation = "Аватар отсутствует; вклад 0."
    if a.avatar_is_default or b.avatar_is_default:
        explanation = "Есть стандартный аватар; вклад 0."
    elif a.avatar_phash is not None and b.avatar_phash is not None:
        distance = (a.avatar_phash ^ b.avatar_phash).bit_count()
        weight = 4.0 if distance <= 4 else 1.5 if distance <= 8 else 0.0
        explanation = f"Расстояние pHash: {distance}/64; вклад {weight:g}."
    return Signal(
        name="avatar",
        log_lr=weight,
        explanation=explanation,
        counter="Картинку можно скопировать; похожий аватар не доказывает связь.",
    )
