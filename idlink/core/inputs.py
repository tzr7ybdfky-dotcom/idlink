"""Validated seed classification; no email guessing or username enumeration."""

import re
from urllib.parse import urlsplit

from idlink.plugins.gravatar import email_hash


def seed_kind(value: str) -> str:
    """Classify an explicit email/hash, public domain, or username."""
    if not value.strip() or any(x.isspace() for x in value):
        raise ValueError("input must not be blank or contain whitespace")
    if "@" in value or re.fullmatch(r"[0-9a-fA-F]{32}|[0-9a-fA-F]{64}", value):
        email_hash(value)
        return "gravatar"
    if "." in value or "://" in value:
        if "://" in value:
            parsed = urlsplit(value)
            if parsed.scheme != "https" or parsed.path not in {"", "/"} or parsed.query:
                raise ValueError("domain input must be an HTTPS origin without a path or query")
            domain = parsed.netloc
        else:
            domain = value
        if not re.fullmatch(
            r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}", domain
        ):
            raise ValueError("invalid public domain")
        if domain.lower().endswith((".local", ".internal", ".localhost", ".test")):
            raise ValueError("local domains are not supported")
        return "website"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value):
        raise ValueError("invalid username")
    return "username"
