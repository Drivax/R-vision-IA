from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
import random
from typing import Any

from src.utils import normalize_topic

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None


@dataclass(slots=True)
class LearningCard:
    title: str
    body: str
    card_type: str
    icon: str


class ContentGenerator:
    """Generate short-form learning cards from a topic using AI with local fallback."""

    def __init__(self) -> None:
        self._openai_client = None
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key and OpenAI:
            self._openai_client = OpenAI(api_key=api_key)

    def generate(self, topic: str, count: int = 24) -> list[dict[str, str]]:
        if self._openai_client:
            cards = self._generate_with_openai(topic=topic, count=count)
            if cards:
                return cards
        return self._generate_fallback(topic=topic, count=count)

    def _generate_with_openai(self, topic: str, count: int) -> list[dict[str, str]]:
        prompt = (
            "Create atomic micro-learning cards for a social feed. "
            f"Topic: {topic}. Generate exactly {count} cards in JSON array format. "
            "Each object must contain: title, body, card_type, icon. "
            "card_type should be one of: definition, concept, fact, comparison, example, question. "
            "Keep each body under 280 characters, accurate, engaging, and beginner-friendly."
        )

        try:
            response = self._openai_client.responses.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                input=prompt,
                max_output_tokens=2500,
            )
            text = response.output_text
            payload = self._extract_json_array(text)
            cards: list[dict[str, str]] = []
            for item in payload:
                title = str(item.get("title", "")).strip()
                body = str(item.get("body", "")).strip()
                card_type = str(item.get("card_type", "concept")).strip().lower()
                icon = str(item.get("icon", ""))[:3]
                if title and body:
                    cards.append(
                        {
                            "title": title,
                            "body": body,
                            "card_type": card_type,
                            "icon": icon,
                        }
                    )
            return cards
        except Exception:
            return []

    def _extract_json_array(self, text: str) -> list[dict[str, Any]]:
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
        except json.JSONDecodeError:
            return []
        return []

    def _generate_fallback(self, topic: str, count: int) -> list[dict[str, str]]:
        normalized = normalize_topic(topic)
        pretty_topic = topic.strip().title()
        seed = int.from_bytes(normalized.encode("utf-8"), "little", signed=False) % (2**32)
        rng = random.Random(seed)

        stems = [
            ("Definition", "definition", "📘", "In simple terms, {topic} is {idea}."),
            ("Core Concept", "concept", "🧠", "A key idea in {topic} is {idea}."),
            ("Why It Matters", "example", "🌍", "You meet {topic} in real life when {idea}."),
            ("Quick Comparison", "comparison", "⚖️", "Think of {topic} like {idea}: similar structure, different scale."),
            ("Fun Fact", "fact", "✨", "Interesting angle: in {topic}, {idea}."),
            ("Mental Model", "concept", "🧩", "A useful model for {topic}: {idea}."),
            ("Common Mistake", "fact", "🚧", "People often confuse {topic} with {idea}."),
            ("Check Yourself", "question", "❓", "If you can explain why {idea}, you are learning {topic} well."),
        ]

        ideas = [
            "breaking the system into smaller parts makes it easier to reason about",
            "cause and effect are often delayed, so patterns appear over time",
            "trade-offs matter more than perfect solutions",
            "context changes outcomes, even with the same rules",
            "experts rely on first principles before memorizing details",
            "simple heuristics help under uncertainty",
            "visualizing flows can reveal hidden bottlenecks",
            "feedback loops can amplify or stabilize behavior",
            "constraints can spark better designs",
            "precision and approximation can both be useful depending on the goal",
            "historical evolution explains many modern conventions",
            "edge cases teach the deepest lessons",
            "small assumptions can create large downstream effects",
            "good questions are often more valuable than fast answers",
            "examples from daily life make abstract ideas stick",
            "comparison with adjacent domains improves understanding",
        ]

        cards: list[LearningCard] = []
        card_idx = 1
        while len(cards) < count:
            label, card_type, icon, template = rng.choice(stems)
            idea = rng.choice(ideas)
            title = f"{label}: {pretty_topic} #{card_idx}"
            body = template.format(topic=pretty_topic, idea=idea)
            cards.append(
                LearningCard(
                    title=title,
                    body=body,
                    card_type=card_type,
                    icon=icon,
                )
            )
            card_idx += 1

        return [asdict(card) for card in cards]
