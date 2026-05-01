from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


FEEDBACK_TO_QUALITY = {
    "easy": 5,
    "medium": 3,
    "hard": 1,
}


@dataclass(slots=True)
class CardScheduleState:
    easiness_factor: float
    interval: int
    repetition_count: int


@dataclass(slots=True)
class ScheduleUpdate:
    easiness_factor: float
    interval: int
    repetition_count: int
    next_review_date: date
    is_mastered: bool


class SM2Scheduler:
    """Implements a pragmatic SM-2 scheduler tuned for short-form learning cards."""

    def review(
        self,
        state: CardScheduleState,
        quality: int,
        review_date: date,
    ) -> ScheduleUpdate:
        if quality < 0 or quality > 5:
            raise ValueError("Quality must be between 0 and 5")

        ef = state.easiness_factor if state.easiness_factor > 0 else 2.5
        rep = state.repetition_count
        interval = state.interval

        if quality < 3:
            rep = 0
            interval = 1
        else:
            rep += 1
            if rep == 1:
                interval = 1
            elif rep == 2:
                interval = 6
            else:
                interval = max(1, round(interval * ef))

        ef = ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        ef = max(1.3, ef)

        next_review = review_date + timedelta(days=interval)
        is_mastered = rep >= 5 and interval >= 21

        return ScheduleUpdate(
            easiness_factor=ef,
            interval=interval,
            repetition_count=rep,
            next_review_date=next_review,
            is_mastered=is_mastered,
        )


__all__ = [
    "CardScheduleState",
    "ScheduleUpdate",
    "SM2Scheduler",
    "FEEDBACK_TO_QUALITY",
]
