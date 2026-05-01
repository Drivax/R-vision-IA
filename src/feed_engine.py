from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.spaced_repetition import CardScheduleState, FEEDBACK_TO_QUALITY, SM2Scheduler
from src.storage import Storage
from src.utils import utc_today


@dataclass(slots=True)
class ReviewResult:
    label: str
    quality: int
    next_review_date: str
    interval: int


class FeedEngine:
    """Coordinates feed retrieval and review updates across storage and SM-2."""

    def __init__(self, storage: Storage, scheduler: SM2Scheduler) -> None:
        self.storage = storage
        self.scheduler = scheduler

    def get_next_batch(
        self,
        topic_id: int,
        shown_ids: list[int],
        batch_size: int = 8,
    ) -> list[dict[str, Any]]:
        return self.storage.fetch_feed_batch(
            topic_id=topic_id,
            shown_ids=shown_ids,
            batch_size=batch_size,
            today=utc_today(),
        )

    def apply_feedback(self, card: dict[str, Any], feedback_label: str) -> ReviewResult:
        label = feedback_label.strip().lower()
        if label not in FEEDBACK_TO_QUALITY:
            raise ValueError(f"Unsupported feedback label: {feedback_label}")

        quality = FEEDBACK_TO_QUALITY[label]
        state = CardScheduleState(
            easiness_factor=float(card["easiness_factor"]),
            interval=int(card["interval"]),
            repetition_count=int(card["repetition_count"]),
        )
        schedule = self.scheduler.review(state, quality=quality, review_date=utc_today())
        self.storage.record_review(
            card=card,
            schedule=schedule,
            feedback_label=label,
            quality=quality,
        )

        return ReviewResult(
            label=label,
            quality=quality,
            next_review_date=schedule.next_review_date.isoformat(),
            interval=schedule.interval,
        )
