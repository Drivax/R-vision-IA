from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.content_generator import ContentGenerator
from src.feed_engine import FeedEngine
from src.spaced_repetition import SM2Scheduler
from src.storage import Storage
from src.ui_components import (
    inject_styles,
    render_card,
    render_empty_feed,
    render_hero,
    render_related_subject_buttons,
    render_session_history,
    render_stats,
    render_topic_controls,
)
from src.utils import utc_now


SEED_CARDS_PER_TOPIC = 24
BATCH_SIZE = 8


def _ensure_state() -> None:
    defaults = {
        "topic_name": "",
        "topic_id": None,
        "feed_cards": [],
        "feed_card_ids": set(),
        "pagination_state": {
            "due_cursor": {"next_review_date": None, "repetition_count": 0, "id": 0},
            "new_cursor": {"id": 0},
            "top_up_cursor": {"sort_value": None, "id": 0},
            "served_ids": [],
        },
        "session_events": [],
        "last_feedback": "",
        "related_subjects": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


@st.cache_resource
def get_storage() -> Storage:
    return Storage(db_path=str(Path("data") / "revision_ia.db"))


@st.cache_resource
def get_content_generator() -> ContentGenerator:
    return ContentGenerator(storage=get_storage())


@st.cache_resource
def get_feed_engine() -> FeedEngine:
    storage = get_storage()
    scheduler = SM2Scheduler()
    return FeedEngine(storage=storage, scheduler=scheduler)


def _seed_topic_cards(topic_id: int, topic_name: str, storage: Storage) -> int:
    existing = storage.count_cards_for_topic(topic_id)
    if existing >= SEED_CARDS_PER_TOPIC:
        return 0

    missing = SEED_CARDS_PER_TOPIC - existing
    generator = get_content_generator()
    cards = generator.generate(topic=topic_name, count=missing)
    return storage.add_cards(topic_id=topic_id, cards=cards)


def _append_event(action: str, title: str = "", detail: str = "") -> None:
    st.session_state.session_events.append(
        {
            "at": utc_now().strftime("%H:%M:%S"),
            "action": action,
            "title": title,
            "detail": detail,
        }
    )


def _reset_topic_feed_state() -> None:
    st.session_state.feed_cards = []
    st.session_state.feed_card_ids = set()
    st.session_state.pagination_state = {
        "due_cursor": {"next_review_date": None, "repetition_count": 0, "id": 0},
        "new_cursor": {"id": 0},
        "top_up_cursor": {"sort_value": None, "id": 0},
        "served_ids": [],
    }


def _load_next_batch(engine: FeedEngine, topic_id: int) -> None:
    batch, next_state = engine.get_next_batch(
        topic_id=topic_id,
        pagination_state=st.session_state.pagination_state,
        batch_size=BATCH_SIZE,
    )
    st.session_state.pagination_state = next_state
    if batch:
        new_cards = [card for card in batch if int(card["id"]) not in st.session_state.feed_card_ids]
        st.session_state.feed_cards.extend(new_cards)
        for card in new_cards:
            st.session_state.feed_card_ids.add(int(card["id"]))
            _append_event(action="card_loaded", title=card["title"], detail=card["card_type"])


def _activate_topic(storage: Storage, engine: FeedEngine, topic_name: str) -> None:
    topic = storage.get_or_create_topic(topic_name)
    st.session_state.topic_name = topic["name"]
    st.session_state.topic_id = topic["id"]
    _reset_topic_feed_state()
    _append_event(action="topic_activated", title=topic["name"])

    inserted = _seed_topic_cards(topic_id=topic["id"], topic_name=topic["name"], storage=storage)
    st.session_state.related_subjects = get_content_generator().suggest_related_subjects(topic=topic["name"], limit=6)
    _load_next_batch(engine=engine, topic_id=topic["id"])

    if inserted:
        st.success(f"Generated {inserted} new learning cards for {topic['name']}.")


def _handle_feedback(engine: FeedEngine, card: dict) -> None:
    result = engine.apply_feedback(card=card, feedback_label=st.session_state[f"feedback_{card['id']}"])
    st.session_state.last_feedback = (
        f"Saved: {result.label.title()} • next review in {result.interval} day(s) ({result.next_review_date})."
    )
    _append_event(
        action="review_submitted",
        title=card["title"],
        detail=f"{result.label} -> next {result.next_review_date} ({result.interval}d)",
    )


def main() -> None:
    st.set_page_config(
        page_title="Révision IA",
        page_icon="🧠",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    _ensure_state()
    inject_styles()

    storage = get_storage()
    engine = get_feed_engine()

    render_hero(st.session_state.topic_name or None)

    topic_input, start_clicked = render_topic_controls(st.session_state.topic_name)
    if start_clicked and topic_input.strip():
        _activate_topic(storage=storage, engine=engine, topic_name=topic_input.strip())

    snapshot = storage.get_progress_snapshot(topic_id=st.session_state.topic_id)
    render_stats(snapshot)
    render_session_history(st.session_state.session_events)

    if st.session_state.last_feedback:
        st.info(st.session_state.last_feedback)

    if not st.session_state.topic_id:
        st.caption("Pick a topic to generate your first feed.")
        return

    if not st.session_state.feed_cards:
        _load_next_batch(engine=engine, topic_id=st.session_state.topic_id)

    feedback_events: list[tuple[int, str]] = []
    has_example_cards = False

    for card in st.session_state.feed_cards:
        if str(card.get("card_type", "")).lower() == "example":
            has_example_cards = True
        feedback = render_card(card)
        if feedback:
            feedback_events.append((card["id"], feedback))

    if feedback_events:
        card_map = {card["id"]: card for card in st.session_state.feed_cards}
        reviewed_ids: set[int] = set()
        for card_id, feedback in feedback_events:
            st.session_state[f"feedback_{card_id}"] = feedback
            _handle_feedback(engine=engine, card=card_map[card_id])
            reviewed_ids.add(int(card_id))

        if reviewed_ids:
            st.session_state.feed_cards = [
                card for card in st.session_state.feed_cards if int(card["id"]) not in reviewed_ids
            ]
        st.rerun()

    if has_example_cards and st.session_state.related_subjects:
        related_selection = render_related_subject_buttons(
            subjects=st.session_state.related_subjects,
            key_prefix=f"related_{st.session_state.topic_id}",
        )
        if related_selection:
            _append_event(action="related_subject_selected", title=related_selection)
            _activate_topic(storage=storage, engine=engine, topic_name=related_selection)
            st.rerun()

    col_a, col_b = st.columns([2, 5])
    if col_a.button("Load more", use_container_width=True):
        before = len(st.session_state.feed_cards)
        _load_next_batch(engine=engine, topic_id=st.session_state.topic_id)
        after = len(st.session_state.feed_cards)
        if after == before:
            render_empty_feed()
            _append_event(action="feed_exhausted", detail="No additional cards for this session window")

    if col_b.button("Refresh due cards", use_container_width=True):
        _reset_topic_feed_state()
        _append_event(action="feed_reset", detail="Feed cursors reset to prioritize due cards")
        _load_next_batch(engine=engine, topic_id=st.session_state.topic_id)
        st.rerun()


if __name__ == "__main__":
    main()
