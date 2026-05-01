from __future__ import annotations

from datetime import date

import pytest

from src.spaced_repetition import CardScheduleState, SM2Scheduler


def test_sm2_first_two_successful_reviews_follow_standard_intervals() -> None:
    scheduler = SM2Scheduler()
    today = date(2026, 5, 1)

    first = scheduler.review(
        state=CardScheduleState(easiness_factor=2.5, interval=0, repetition_count=0),
        quality=5,
        review_date=today,
    )
    assert first.repetition_count == 1
    assert first.interval == 1
    assert first.next_review_date.isoformat() == "2026-05-02"

    second = scheduler.review(
        state=CardScheduleState(
            easiness_factor=first.easiness_factor,
            interval=first.interval,
            repetition_count=first.repetition_count,
        ),
        quality=5,
        review_date=first.next_review_date,
    )
    assert second.repetition_count == 2
    assert second.interval == 6


def test_sm2_hard_feedback_resets_repetition_and_shortens_interval() -> None:
    scheduler = SM2Scheduler()
    today = date(2026, 5, 1)

    update = scheduler.review(
        state=CardScheduleState(easiness_factor=2.1, interval=12, repetition_count=4),
        quality=1,
        review_date=today,
    )

    assert update.repetition_count == 0
    assert update.interval == 1
    assert update.next_review_date.isoformat() == "2026-05-02"


def test_sm2_mastery_flag_turns_true_for_long_interval_and_high_repetition() -> None:
    scheduler = SM2Scheduler()

    update = scheduler.review(
        state=CardScheduleState(easiness_factor=2.6, interval=25, repetition_count=4),
        quality=5,
        review_date=date(2026, 5, 1),
    )

    assert update.repetition_count == 5
    assert update.interval >= 21
    assert update.is_mastered is True


def test_sm2_rejects_invalid_quality() -> None:
    scheduler = SM2Scheduler()

    with pytest.raises(ValueError):
        scheduler.review(
            state=CardScheduleState(easiness_factor=2.5, interval=0, repetition_count=0),
            quality=7,
            review_date=date(2026, 5, 1),
        )
