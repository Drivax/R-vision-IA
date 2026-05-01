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
    render_stats,
    render_topic_controls,
)


SEED_CARDS_PER_TOPIC = 24
BATCH_SIZE = 8


def _ensure_state() -> None:
    defaults = {
        "topic_name": "",
        "topic_id": None,
        "feed_cards": [],
        "last_feedback": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


@st.cache_resource
def get_storage() -> Storage:
    return Storage(db_path=str(Path("data") / "revision_ia.db"))


@st.cache_resource
def get_content_generator() -> ContentGenerator:
    return ContentGenerator()


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


def _load_next_batch(storage: Storage, engine: FeedEngine, topic_id: int) -> None:
    shown_ids = [int(card["id"]) for card in st.session_state.feed_cards]
    batch = engine.get_next_batch(topic_id=topic_id, shown_ids=shown_ids, batch_size=BATCH_SIZE)
    if batch:
        st.session_state.feed_cards.extend(batch)


def _activate_topic(storage: Storage, engine: FeedEngine, topic_name: str) -> None:
    topic = storage.get_or_create_topic(topic_name)
    st.session_state.topic_name = topic["name"]
    st.session_state.topic_id = topic["id"]
    st.session_state.feed_cards = []

    inserted = _seed_topic_cards(topic_id=topic["id"], topic_name=topic["name"], storage=storage)
    _load_next_batch(storage=storage, engine=engine, topic_id=topic["id"])

    if inserted:
        st.success(f"Generated {inserted} new learning cards for {topic['name']}.")


def _handle_feedback(engine: FeedEngine, card: dict) -> None:
    result = engine.apply_feedback(card=card, feedback_label=st.session_state[f"feedback_{card['id']}"])
    st.session_state.last_feedback = (
        f"Saved: {result.label.title()} • next review in {result.interval} day(s) ({result.next_review_date})."
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

    if st.session_state.last_feedback:
        st.info(st.session_state.last_feedback)

    if not st.session_state.topic_id:
        st.caption("Pick a topic to generate your first feed.")
        return

    if not st.session_state.feed_cards:
        _load_next_batch(storage=storage, engine=engine, topic_id=st.session_state.topic_id)

    feedback_events: list[tuple[int, str]] = []

    for card in st.session_state.feed_cards:
        feedback = render_card(card)
        if feedback:
            feedback_events.append((card["id"], feedback))

    if feedback_events:
        card_map = {card["id"]: card for card in st.session_state.feed_cards}
        for card_id, feedback in feedback_events:
            st.session_state[f"feedback_{card_id}"] = feedback
            _handle_feedback(engine=engine, card=card_map[card_id])
        st.rerun()

    col_a, col_b = st.columns([2, 5])
    if col_a.button("Load more", use_container_width=True):
        before = len(st.session_state.feed_cards)
        _load_next_batch(storage=storage, engine=engine, topic_id=st.session_state.topic_id)
        after = len(st.session_state.feed_cards)
        if after == before:
            render_empty_feed()

    if col_b.button("Refresh due cards", use_container_width=True):
        st.session_state.feed_cards = []
        _load_next_batch(storage=storage, engine=engine, topic_id=st.session_state.topic_id)
        st.rerun()


if __name__ == "__main__":
    main()
