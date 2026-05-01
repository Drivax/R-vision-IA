from __future__ import annotations

from typing import Any

import streamlit as st


def inject_styles() -> None:
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=Manrope:wght@400;600;700&display=swap');

            :root {
                --bg: #0f1720;
                --surface: #152232;
                --surface-2: #1d3149;
                --text: #f4f8ff;
                --muted: #b8c6da;
                --accent: #26d7a7;
                --accent-2: #ffb347;
                --danger: #ff6b6b;
            }

            .stApp {
                background:
                    radial-gradient(1200px 600px at -10% -20%, #1f3048 0%, transparent 50%),
                    radial-gradient(1000px 500px at 110% -10%, #1e3a5f 0%, transparent 55%),
                    linear-gradient(180deg, #0b1118 0%, #0f1720 100%);
                color: var(--text);
            }

            h1, h2, h3, h4 {
                font-family: "Space Grotesk", sans-serif;
                color: var(--text);
                letter-spacing: 0.2px;
            }

            p, span, label, .stMarkdown, .stTextInput {
                font-family: "Manrope", sans-serif;
                color: var(--text);
            }

            .rev-hero {
                border: 1px solid #274464;
                border-radius: 18px;
                padding: 1.2rem 1.1rem;
                background: linear-gradient(140deg, rgba(40,70,102,.68), rgba(25,35,53,.76));
                box-shadow: 0 10px 34px rgba(0, 0, 0, 0.25);
                margin-bottom: 1rem;
            }

            .rev-card {
                border: 1px solid #284462;
                background: linear-gradient(170deg, rgba(28,43,62,.9), rgba(20,32,49,.95));
                border-radius: 16px;
                padding: 1rem 1rem 0.8rem;
                box-shadow: 0 8px 26px rgba(0, 0, 0, 0.25);
                margin-bottom: 0.9rem;
            }

            .rev-card-meta {
                color: var(--muted);
                font-size: 0.86rem;
                letter-spacing: 0.2px;
                margin-bottom: 0.3rem;
            }

            .rev-pill {
                display: inline-block;
                background: #223750;
                border: 1px solid #2d4d6d;
                color: #cbe3ff;
                border-radius: 999px;
                padding: 0.15rem 0.55rem;
                margin-right: 0.45rem;
                margin-bottom: 0.35rem;
                font-size: 0.75rem;
            }

            .rev-empty {
                border: 1px dashed #345476;
                border-radius: 14px;
                padding: 1rem;
                background: rgba(20, 31, 45, 0.65);
                color: var(--muted);
            }

            [data-testid="stMetricValue"] {
                color: #eaf3ff;
                font-family: "Space Grotesk", sans-serif;
            }

            [data-testid="stSidebar"] {
                background: linear-gradient(180deg, rgba(17,27,41,0.95) 0%, rgba(14,21,33,0.98) 100%);
                border-right: 1px solid #2f4b68;
            }

            .stButton > button {
                border-radius: 10px;
                border: 1px solid #2f4f71;
                font-family: "Manrope", sans-serif;
                font-weight: 600;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero(topic_name: str | None) -> None:
    subtitle = "Pick a topic and scroll your daily learning feed."
    if topic_name:
        subtitle = f"Learning stream active for: {topic_name}"

    st.markdown(
        f"""
        <div class="rev-hero">
            <h1 style="margin: 0 0 0.3rem 0;">Révision IA</h1>
            <p style="margin: 0; color: #d4e2f5;">{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_topic_controls(topic_name: str) -> tuple[str, bool]:
    col_topic, col_action = st.columns([5, 1])
    with col_topic:
        new_topic = st.text_input(
            "Topic",
            value=topic_name,
            placeholder="Example: planes, Roman Empire, quantum physics",
            label_visibility="collapsed",
        )
    with col_action:
        load_clicked = st.button("Start", use_container_width=True, type="primary")

    return new_topic, load_clicked


def render_stats(snapshot: dict[str, Any]) -> None:
    st.sidebar.subheader("Progress")
    c1, c2 = st.sidebar.columns(2)
    c1.metric("Retention", f"{snapshot['retention_score']}%")
    c2.metric("Today", snapshot["reviewed_today"])

    c3, c4 = st.sidebar.columns(2)
    c3.metric("Mastered", snapshot["mastered_cards"])
    c4.metric("Due", snapshot["due_cards"])

    st.sidebar.caption(
        f"Seen {snapshot['seen_cards']} / {snapshot['total_cards']} cards • Avg quality today: {snapshot['avg_quality_today']}"
    )


def render_card(card: dict[str, Any]) -> str | None:
    st.markdown('<div class="rev-card">', unsafe_allow_html=True)
    icon = card.get("icon", "") or "📝"
    st.markdown(
        f"<div class='rev-card-meta'>{icon} {card['card_type'].title()}</div>",
        unsafe_allow_html=True,
    )
    st.subheader(card["title"])
    st.write(card["body"])

    badges = []
    if card.get("next_review_date"):
        badges.append(f"<span class='rev-pill'>Next review: {card['next_review_date']}</span>")
    if int(card.get("repetition_count", 0)) > 0:
        badges.append(f"<span class='rev-pill'>Repetition: {card['repetition_count']}</span>")

    if badges:
        st.markdown("".join(badges), unsafe_allow_html=True)

    col_easy, col_medium, col_hard = st.columns(3)
    feedback = None
    if col_easy.button("I knew this", key=f"easy_{card['id']}", use_container_width=True):
        feedback = "easy"
    if col_medium.button("This is new", key=f"medium_{card['id']}", use_container_width=True):
        feedback = "medium"
    if col_hard.button("I forgot", key=f"hard_{card['id']}", use_container_width=True):
        feedback = "hard"

    st.markdown("</div>", unsafe_allow_html=True)
    return feedback


def render_empty_feed() -> None:
    st.markdown(
        """
        <div class="rev-empty">
            <strong>Your feed is caught up.</strong><br/>
            Try another topic or come back later for the next scheduled reviews.
        </div>
        """,
        unsafe_allow_html=True,
    )
