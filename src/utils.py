from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import re


def utc_now() -> datetime:
    """Return timezone-aware UTC datetime for all persistence operations."""
    return datetime.now(timezone.utc)


def utc_today() -> date:
    return utc_now().date()


def to_iso_date(value: date) -> str:
    return value.isoformat()


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def normalize_topic(topic: str) -> str:
    cleaned = re.sub(r"\s+", " ", topic.strip().lower())
    return cleaned


def stable_hash(parts: list[str]) -> str:
    payload = "||".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
