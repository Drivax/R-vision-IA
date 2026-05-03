from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Optional

from src.spaced_repetition import ScheduleUpdate
from src.utils import normalize_topic, stable_hash, to_iso_date, utc_now, utc_today

WIKI_CACHE_TTL_DAYS = 7


class Storage:
    """SQLite persistence layer for cards, scheduling state, and review analytics."""

    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self._run_migrations()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    card_type TEXT NOT NULL,
                    icon TEXT,
                    content_hash TEXT NOT NULL,
                    seen_count INTEGER NOT NULL DEFAULT 0,
                    easiness_factor REAL NOT NULL DEFAULT 2.5,
                    interval INTEGER NOT NULL DEFAULT 0,
                    repetition_count INTEGER NOT NULL DEFAULT 0,
                    next_review_date TEXT,
                    last_reviewed_at TEXT,
                    is_mastered INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    image_url TEXT,
                    UNIQUE(topic_id, content_hash),
                    FOREIGN KEY(topic_id) REFERENCES topics(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    card_id INTEGER NOT NULL,
                    reviewed_at TEXT NOT NULL,
                    feedback_label TEXT NOT NULL,
                    quality INTEGER NOT NULL,
                    prev_easiness_factor REAL NOT NULL,
                    prev_interval INTEGER NOT NULL,
                    prev_repetition_count INTEGER NOT NULL,
                    new_easiness_factor REAL NOT NULL,
                    new_interval INTEGER NOT NULL,
                    new_repetition_count INTEGER NOT NULL,
                    next_review_date TEXT NOT NULL,
                    FOREIGN KEY(card_id) REFERENCES cards(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS wiki_cache (
                    normalized_topic TEXT PRIMARY KEY,
                    wiki_title TEXT NOT NULL,
                    wiki_url TEXT NOT NULL,
                    summary TEXT,
                    paragraphs_json TEXT,
                    key_facts_json TEXT,
                    sections_json TEXT,
                    highlights_json TEXT,
                    cached_at TEXT NOT NULL
                );
                """
            )

    def _run_migrations(self) -> None:
        """Add columns introduced after initial schema creation (idempotent)."""
        new_columns = [
            ("cards", "image_url", "TEXT"),
            ("wiki_cache", "image_url", "TEXT"),
        ]
        with self._connect() as conn:
            for table, column, col_type in new_columns:
                try:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                except sqlite3.OperationalError:
                    pass  # column already exists

    def get_or_create_topic(self, topic_name: str) -> dict[str, Any]:
        normalized = normalize_topic(topic_name)
        now = utc_now().isoformat()

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM topics WHERE normalized_name = ?",
                (normalized,),
            ).fetchone()
            if row:
                return dict(row)

            conn.execute(
                "INSERT INTO topics (name, normalized_name, created_at) VALUES (?, ?, ?)",
                (topic_name.strip(), normalized, now),
            )
            created = conn.execute(
                "SELECT * FROM topics WHERE normalized_name = ?",
                (normalized,),
            ).fetchone()
            return dict(created)

    def list_topics(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM topics ORDER BY created_at DESC"
            ).fetchall()
            return [dict(row) for row in rows]

    def count_cards_for_topic(self, topic_id: int) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM cards WHERE topic_id = ?",
                (topic_id,),
            ).fetchone()
            return int(row["count"]) if row else 0

    def add_cards(self, topic_id: int, cards: list[dict[str, str]]) -> int:
        now = utc_now().isoformat()
        inserted = 0

        with self._connect() as conn:
            for card in cards:
                digest = stable_hash([
                    card.get("title", ""),
                    card.get("body", ""),
                    card.get("card_type", ""),
                ])
                try:
                    conn.execute(
                        """
                        INSERT INTO cards (
                            topic_id, title, body, card_type, icon, content_hash, image_url, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            topic_id,
                            card["title"].strip(),
                            card["body"].strip(),
                            card.get("card_type", "concept"),
                            card.get("icon", ""),
                            digest,
                            card.get("image_url") or None,
                            now,
                        ),
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    continue

        return inserted

    def fetch_feed_batch(
        self,
        topic_id: int,
        shown_ids: list[int],
        batch_size: int,
        today: date | None = None,
    ) -> list[dict[str, Any]]:
        check_date = today or utc_today()

        def not_in_clause(ids: list[int]) -> tuple[str, list[int]]:
            if not ids:
                return "", []
            placeholders = ",".join("?" for _ in ids)
            return f" AND id NOT IN ({placeholders})", ids

        excluded_sql, excluded_args = not_in_clause(shown_ids)
        due_limit = max(1, int(batch_size * 0.7))

        with self._connect() as conn:
            due_rows = conn.execute(
                f"""
                SELECT * FROM cards
                WHERE topic_id = ?
                    AND next_review_date IS NOT NULL
                    AND date(next_review_date) <= date(?)
                    {excluded_sql}
                ORDER BY date(next_review_date) ASC, repetition_count ASC, id ASC
                LIMIT ?
                """,
                [topic_id, to_iso_date(check_date), *excluded_args, due_limit],
            ).fetchall()

            remaining = batch_size - len(due_rows)
            if remaining <= 0:
                return [dict(row) for row in due_rows]

            new_rows = conn.execute(
                f"""
                SELECT * FROM cards
                WHERE topic_id = ?
                    AND seen_count = 0
                    {excluded_sql}
                ORDER BY id ASC
                LIMIT ?
                """,
                [topic_id, *excluded_args, remaining],
            ).fetchall()

            remaining -= len(new_rows)
            if remaining <= 0:
                return [dict(row) for row in [*due_rows, *new_rows]]

            # If we run out of due/new cards, surface older reviewed cards to keep the feed alive.
            top_up_rows = conn.execute(
                f"""
                SELECT * FROM cards
                WHERE topic_id = ?
                    AND seen_count > 0
                    AND (
                        next_review_date IS NULL
                        OR date(next_review_date) > date(?)
                    )
                    {excluded_sql}
                ORDER BY COALESCE(last_reviewed_at, created_at) ASC
                LIMIT ?
                """,
                [topic_id, to_iso_date(check_date), *excluded_args, remaining],
            ).fetchall()

            return [dict(row) for row in [*due_rows, *new_rows, *top_up_rows]]

    def fetch_feed_page(
        self,
        topic_id: int,
        batch_size: int,
        pagination_state: dict[str, Any] | None = None,
        today: date | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Return a stable feed page using keyset-like cursors per card lane.

        The feed is assembled in three lanes, in this order:
        1) due cards, 2) unseen cards, 3) reviewed top-up cards.
        """
        check_date = today or utc_today()
        state = pagination_state or {}
        served_ids = set(state.get("served_ids", []))
        due_limit = max(1, int(batch_size * 0.7))

        due_cursor = state.get("due_cursor") or {
            "next_review_date": None,
            "repetition_count": 0,
            "id": 0,
        }
        new_cursor = state.get("new_cursor") or {"id": 0}
        top_up_cursor = state.get("top_up_cursor") or {
            "sort_value": None,
            "id": 0,
        }

        with self._connect() as conn:
            due_rows = conn.execute(
                """
                SELECT * FROM cards
                WHERE topic_id = ?
                    AND next_review_date IS NOT NULL
                    AND date(next_review_date) <= date(?)
                    AND (
                        ? IS NULL
                        OR date(next_review_date) > date(?)
                        OR (
                            date(next_review_date) = date(?)
                            AND (
                                repetition_count > ?
                                OR (repetition_count = ? AND id > ?)
                            )
                        )
                    )
                ORDER BY date(next_review_date) ASC, repetition_count ASC, id ASC
                LIMIT ?
                """,
                (
                    topic_id,
                    to_iso_date(check_date),
                    due_cursor.get("next_review_date"),
                    due_cursor.get("next_review_date"),
                    due_cursor.get("next_review_date"),
                    int(due_cursor.get("repetition_count", 0)),
                    int(due_cursor.get("repetition_count", 0)),
                    int(due_cursor.get("id", 0)),
                    due_limit,
                ),
            ).fetchall()

            due_cards = [dict(row) for row in due_rows if int(row["id"]) not in served_ids]

            if due_cards:
                last_due = due_cards[-1]
                due_cursor = {
                    "next_review_date": last_due["next_review_date"],
                    "repetition_count": int(last_due["repetition_count"]),
                    "id": int(last_due["id"]),
                }

            remaining = batch_size - len(due_cards)
            if remaining <= 0:
                cards = due_cards
                new_state = {
                    "due_cursor": due_cursor,
                    "new_cursor": new_cursor,
                    "top_up_cursor": top_up_cursor,
                    "served_ids": [*served_ids, *[int(card["id"]) for card in cards]],
                }
                return cards, new_state

            new_rows = conn.execute(
                """
                SELECT * FROM cards
                WHERE topic_id = ?
                    AND seen_count = 0
                    AND id > ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (topic_id, int(new_cursor.get("id", 0)), remaining * 2),
            ).fetchall()

            new_cards = [dict(row) for row in new_rows if int(row["id"]) not in served_ids][:remaining]
            if new_cards:
                new_cursor = {"id": int(new_cards[-1]["id"])}

            remaining -= len(new_cards)
            if remaining <= 0:
                cards = [*due_cards, *new_cards]
                new_state = {
                    "due_cursor": due_cursor,
                    "new_cursor": new_cursor,
                    "top_up_cursor": top_up_cursor,
                    "served_ids": [*served_ids, *[int(card["id"]) for card in cards]],
                }
                return cards, new_state

            top_up_rows = conn.execute(
                """
                SELECT *, COALESCE(last_reviewed_at, created_at) AS sort_value
                FROM cards
                WHERE topic_id = ?
                    AND seen_count > 0
                    AND (
                        next_review_date IS NULL
                        OR date(next_review_date) > date(?)
                    )
                    AND (
                        ? IS NULL
                        OR COALESCE(last_reviewed_at, created_at) > ?
                        OR (
                            COALESCE(last_reviewed_at, created_at) = ?
                            AND id > ?
                        )
                    )
                ORDER BY sort_value ASC, id ASC
                LIMIT ?
                """,
                (
                    topic_id,
                    to_iso_date(check_date),
                    top_up_cursor.get("sort_value"),
                    top_up_cursor.get("sort_value"),
                    top_up_cursor.get("sort_value"),
                    int(top_up_cursor.get("id", 0)),
                    remaining * 2,
                ),
            ).fetchall()

            top_up_cards = [dict(row) for row in top_up_rows if int(row["id"]) not in served_ids][:remaining]
            if top_up_cards:
                last_top = top_up_cards[-1]
                top_up_cursor = {
                    "sort_value": last_top["sort_value"],
                    "id": int(last_top["id"]),
                }

            cards = [*due_cards, *new_cards, *top_up_cards]
            new_state = {
                "due_cursor": due_cursor,
                "new_cursor": new_cursor,
                "top_up_cursor": top_up_cursor,
                "served_ids": [*served_ids, *[int(card["id"]) for card in cards]],
            }
            return cards, new_state

    def record_review(
        self,
        card: dict[str, Any],
        schedule: ScheduleUpdate,
        feedback_label: str,
        quality: int,
    ) -> None:
        now = utc_now().isoformat()

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE cards
                SET
                    seen_count = seen_count + 1,
                    easiness_factor = ?,
                    interval = ?,
                    repetition_count = ?,
                    next_review_date = ?,
                    last_reviewed_at = ?,
                    is_mastered = ?
                WHERE id = ?
                """,
                (
                    schedule.easiness_factor,
                    schedule.interval,
                    schedule.repetition_count,
                    to_iso_date(schedule.next_review_date),
                    now,
                    1 if schedule.is_mastered else 0,
                    card["id"],
                ),
            )

            conn.execute(
                """
                INSERT INTO reviews (
                    card_id,
                    reviewed_at,
                    feedback_label,
                    quality,
                    prev_easiness_factor,
                    prev_interval,
                    prev_repetition_count,
                    new_easiness_factor,
                    new_interval,
                    new_repetition_count,
                    next_review_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card["id"],
                    now,
                    feedback_label,
                    quality,
                    float(card["easiness_factor"]),
                    int(card["interval"]),
                    int(card["repetition_count"]),
                    schedule.easiness_factor,
                    schedule.interval,
                    schedule.repetition_count,
                    to_iso_date(schedule.next_review_date),
                ),
            )

    def get_progress_snapshot(self, topic_id: int | None = None) -> dict[str, Any]:
        params: list[Any] = []
        filter_sql = ""
        if topic_id is not None:
            filter_sql = "WHERE topic_id = ?"
            params.append(topic_id)

        with self._connect() as conn:
            totals = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS total_cards,
                    SUM(CASE WHEN seen_count > 0 THEN 1 ELSE 0 END) AS seen_cards,
                    SUM(CASE WHEN is_mastered = 1 THEN 1 ELSE 0 END) AS mastered_cards,
                    SUM(
                        CASE
                            WHEN next_review_date IS NOT NULL AND date(next_review_date) <= date(?)
                            THEN 1
                            ELSE 0
                        END
                    ) AS due_cards
                FROM cards
                {filter_sql}
                """,
                [to_iso_date(utc_today()), *params],
            ).fetchone()

            today_reviews = conn.execute(
                """
                SELECT
                    COUNT(*) AS review_count,
                    AVG(quality) AS avg_quality
                FROM reviews r
                JOIN cards c ON c.id = r.card_id
                WHERE date(r.reviewed_at) = date(?)
                    AND (? IS NULL OR c.topic_id = ?)
                """,
                [to_iso_date(utc_today()), topic_id, topic_id],
            ).fetchone()

            total_cards = int(totals["total_cards"] or 0)
            seen_cards = int(totals["seen_cards"] or 0)
            mastered_cards = int(totals["mastered_cards"] or 0)
            due_cards = int(totals["due_cards"] or 0)
            reviewed_today = int(today_reviews["review_count"] or 0)
            avg_quality = float(today_reviews["avg_quality"] or 0.0)

            retention_score = 0.0
            if seen_cards > 0:
                retention_score = round((mastered_cards / seen_cards) * 100, 1)

            return {
                "total_cards": total_cards,
                "seen_cards": seen_cards,
                "mastered_cards": mastered_cards,
                "due_cards": due_cards,
                "reviewed_today": reviewed_today,
                "retention_score": retention_score,
                "avg_quality_today": round(avg_quality, 2),
            }

    # ------------------------------------------------------------------
    # Wikipedia cache
    # ------------------------------------------------------------------

    def get_wiki_cache(self, normalized_topic: str):
        """Return cached WikiTopicData for *normalized_topic* or None if absent/stale."""
        from src.wiki_scraper import WikiTopicData  # local import to avoid circular

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM wiki_cache WHERE normalized_topic = ?",
                [normalized_topic],
            ).fetchone()

        if row is None:
            return None

        cached_at = datetime.fromisoformat(row["cached_at"])
        age = datetime.now(timezone.utc) - cached_at.replace(tzinfo=timezone.utc)
        if age.days >= WIKI_CACHE_TTL_DAYS:
            return None

        return WikiTopicData(
            title=row["wiki_title"],
            url=row["wiki_url"],
            summary=row["summary"] or "",
            paragraphs=json.loads(row["paragraphs_json"] or "[]"),
            key_facts=[tuple(x) for x in json.loads(row["key_facts_json"] or "[]")],
            sections=[tuple(x) for x in json.loads(row["sections_json"] or "[]")],
            highlights=json.loads(row["highlights_json"] or "[]"),
            image_url=row["image_url"] if row["image_url"] else None,
        )

    def set_wiki_cache(self, normalized_topic: str, data) -> None:
        """Persist a WikiTopicData result to the cache table."""
        now = utc_now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO wiki_cache
                    (normalized_topic, wiki_title, wiki_url, summary,
                     paragraphs_json, key_facts_json, sections_json,
                     highlights_json, image_url, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(normalized_topic) DO UPDATE SET
                    wiki_title = excluded.wiki_title,
                    wiki_url = excluded.wiki_url,
                    summary = excluded.summary,
                    paragraphs_json = excluded.paragraphs_json,
                    key_facts_json = excluded.key_facts_json,
                    sections_json = excluded.sections_json,
                    highlights_json = excluded.highlights_json,
                    image_url = excluded.image_url,
                    cached_at = excluded.cached_at
                """,
                [
                    normalized_topic,
                    data.title,
                    data.url,
                    data.summary,
                    json.dumps(data.paragraphs),
                    json.dumps(data.key_facts),
                    json.dumps(data.sections),
                    json.dumps(data.highlights),
                    data.image_url,
                    now,
                ],
            )
