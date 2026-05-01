from __future__ import annotations

from datetime import date, timedelta

from src.spaced_repetition import ScheduleUpdate
from src.storage import Storage


def _make_storage(tmp_path) -> Storage:
    db_path = tmp_path / "test_revision_ia.db"
    return Storage(str(db_path))


def _seed_topic_with_cards(storage: Storage, topic_name: str, count: int) -> tuple[int, list[int]]:
    topic = storage.get_or_create_topic(topic_name)
    cards = [
        {
            "title": f"Card {idx}",
            "body": f"Body {idx}",
            "card_type": "concept",
            "icon": "",
        }
        for idx in range(1, count + 1)
    ]
    storage.add_cards(topic_id=topic["id"], cards=cards)

    with storage._connect() as conn:  # noqa: SLF001 - test helper access
        rows = conn.execute(
            "SELECT id FROM cards WHERE topic_id = ? ORDER BY id ASC",
            (topic["id"],),
        ).fetchall()
    return topic["id"], [int(row["id"]) for row in rows]


def test_get_or_create_topic_is_idempotent(tmp_path) -> None:
    storage = _make_storage(tmp_path)

    first = storage.get_or_create_topic("Planes")
    second = storage.get_or_create_topic("   planes   ")

    assert first["id"] == second["id"]


def test_fetch_feed_page_prioritizes_due_then_new_then_top_up(tmp_path) -> None:
    storage = _make_storage(tmp_path)
    topic_id, ids = _seed_topic_with_cards(storage, "Planes", count=6)
    today = date(2026, 5, 1)

    with storage._connect() as conn:  # noqa: SLF001 - test fixture data setup
        conn.execute(
            "UPDATE cards SET seen_count = 1, next_review_date = ?, repetition_count = 2 WHERE id = ?",
            (today.isoformat(), ids[0]),
        )
        conn.execute(
            "UPDATE cards SET seen_count = 1, next_review_date = ?, repetition_count = 1 WHERE id = ?",
            ((today - timedelta(days=1)).isoformat(), ids[1]),
        )
        conn.execute(
            "UPDATE cards SET seen_count = 1, next_review_date = ?, last_reviewed_at = ? WHERE id = ?",
            ((today + timedelta(days=2)).isoformat(), "2026-04-20T10:00:00+00:00", ids[4]),
        )
        conn.execute(
            "UPDATE cards SET seen_count = 1, next_review_date = ?, last_reviewed_at = ? WHERE id = ?",
            ((today + timedelta(days=3)).isoformat(), "2026-04-21T10:00:00+00:00", ids[5]),
        )

    first_cards, state = storage.fetch_feed_page(
        topic_id=topic_id,
        batch_size=4,
        pagination_state={},
        today=today,
    )

    first_ids = [int(card["id"]) for card in first_cards]
    assert first_ids == [ids[1], ids[0], ids[2], ids[3]]

    second_cards, _ = storage.fetch_feed_page(
        topic_id=topic_id,
        batch_size=4,
        pagination_state=state,
        today=today,
    )
    second_ids = [int(card["id"]) for card in second_cards]
    assert second_ids == [ids[4], ids[5]]


def test_record_review_updates_card_and_persists_review_history(tmp_path) -> None:
    storage = _make_storage(tmp_path)
    topic_id, ids = _seed_topic_with_cards(storage, "Roman Empire", count=1)
    card_id = ids[0]

    with storage._connect() as conn:  # noqa: SLF001 - test helper access
        card = dict(
            conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        )

    update = ScheduleUpdate(
        easiness_factor=2.6,
        interval=6,
        repetition_count=2,
        next_review_date=date(2026, 5, 7),
        is_mastered=False,
    )
    storage.record_review(card=card, schedule=update, feedback_label="medium", quality=3)

    with storage._connect() as conn:  # noqa: SLF001 - test helper access
        updated = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        reviews = conn.execute("SELECT * FROM reviews WHERE card_id = ?", (card_id,)).fetchall()

    assert int(updated["seen_count"]) == 1
    assert int(updated["interval"]) == 6
    assert int(updated["repetition_count"]) == 2
    assert updated["next_review_date"] == "2026-05-07"
    assert len(reviews) == 1
    assert int(reviews[0]["quality"]) == 3

    snapshot = storage.get_progress_snapshot(topic_id=topic_id)
    assert snapshot["total_cards"] == 1
    assert snapshot["seen_cards"] == 1
    assert snapshot["reviewed_today"] == 1
