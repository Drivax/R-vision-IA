from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
import random
import re
from typing import Any

from src.utils import normalize_topic
from src.wiki_scraper import WikiTopicData, WikipediaScraper
from typing import Optional

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None


@dataclass
class LearningCard:
    title: str
    body: str
    card_type: str
    icon: str
    image_url: Optional[str] = None


class ContentGenerator:
    """Generate short-form learning cards with Wikipedia scraping as source of truth."""

    def __init__(self, storage=None) -> None:
        self._openai_client = None
        self._wiki = WikipediaScraper(storage=storage)
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key and OpenAI:
            self._openai_client = OpenAI(api_key=api_key)

    def generate(self, topic: str, count: int = 24) -> list[dict[str, str]]:
        wiki_topic = self._wiki.scrape_topic(topic)
        if wiki_topic:
            wiki_cards = self._generate_from_wikipedia(wiki_topic=wiki_topic, count=count)
            if len(wiki_cards) >= count:
                return wiki_cards[:count]

            if self._openai_client:
                enriched = self._generate_with_openai(topic=wiki_topic.title, count=count, source=wiki_topic)
                merged = self._merge_cards(primary=wiki_cards, secondary=enriched, count=count)
                if merged:
                    return merged

            fallback_fill = self._generate_fallback(topic=wiki_topic.title, count=count - len(wiki_cards))
            return [*wiki_cards, *fallback_fill][:count]

        if self._openai_client:
            cards = self._generate_with_openai(topic=topic, count=count, source=None)
            if cards:
                return cards
        return self._generate_fallback(topic=topic, count=count)

    def _generate_from_wikipedia(self, wiki_topic: WikiTopicData, count: int) -> list[dict[str, str]]:
        cards: list[LearningCard] = []
        topic_title = wiki_topic.title

        if wiki_topic.summary:
            cards.append(
                LearningCard(
                    title=f"Definition: {topic_title}",
                    body=self._truncate(wiki_topic.summary),
                    card_type="definition",
                    icon="📘",
                    image_url=wiki_topic.image_url,
                )
            )

        for heading, content in wiki_topic.sections:
            cards.append(
                LearningCard(
                    title=f"Key Concept: {heading}",
                    body=self._truncate(content),
                    card_type="concept",
                    icon="🧠",
                )
            )
            if len(cards) >= count:
                return [asdict(card) for card in cards[:count]]

        for key, value in wiki_topic.key_facts:
            cards.append(
                LearningCard(
                    title=f"Fact: {key}",
                    body=self._truncate(f"{topic_title} - {value}"),
                    card_type="fact",
                    icon="✨",
                )
            )
            if len(cards) >= count:
                return [asdict(card) for card in cards[:count]]

        for idx, item in enumerate(wiki_topic.highlights, start=1):
            cards.append(
                LearningCard(
                    title=f"Example #{idx}: {topic_title}",
                    body=self._truncate(item),
                    card_type="example",
                    icon="🌍",
                )
            )
            if len(cards) >= count:
                return [asdict(card) for card in cards[:count]]

        comparison_pairs = self._comparison_pairs(wiki_topic)
        for left, right in comparison_pairs:
            cards.append(
                LearningCard(
                    title=f"Comparison: {left} vs {right}",
                    body=self._truncate(
                        f"In {topic_title}, compare {left.lower()} with {right.lower()} to understand differences in role, scale, and impact."
                    ),
                    card_type="comparison",
                    icon="⚖️",
                )
            )
            if len(cards) >= count:
                return [asdict(card) for card in cards[:count]]

        return [asdict(card) for card in cards[:count]]

    def _generate_with_openai(self, topic: str, count: int, source: WikiTopicData | None) -> list[dict[str, str]]:
        source_context = ""
        if source:
            facts = "; ".join(f"{k}: {v}" for k, v in source.key_facts[:6])
            sections = "; ".join(h for h, _ in source.sections[:6])
            highlights = "; ".join(source.highlights[:6])
            source_context = (
                f"Use these verified Wikipedia details. Summary: {source.summary}. "
                f"Sections: {sections}. Facts: {facts}. Highlights: {highlights}. "
                f"Source URL: {source.url}."
            )

        prompt = (
            "Create atomic micro-learning cards for a social feed. "
            f"Topic: {topic}. Generate exactly {count} cards in JSON array format. "
            "Each object must contain: title, body, card_type, icon. "
            "card_type should be one of: definition, concept, fact, comparison, example, question. "
            "Keep each body under 280 characters, accurate, engaging, and beginner-friendly. "
            f"{source_context}"
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

    def _merge_cards(
        self,
        primary: list[dict[str, str]],
        secondary: list[dict[str, str]],
        count: int,
    ) -> list[dict[str, str]]:
        merged: list[dict[str, str]] = []
        seen: set[str] = set()
        for candidate in [*primary, *secondary]:
            title = candidate.get("title", "").strip().lower()
            body = candidate.get("body", "").strip().lower()
            signature = f"{title}::{body}"
            if not title or not body or signature in seen:
                continue
            merged.append(candidate)
            seen.add(signature)
            if len(merged) >= count:
                break
        return merged

    def _comparison_pairs(self, wiki_topic: WikiTopicData) -> list[tuple[str, str]]:
        section_names = [name for name, _ in wiki_topic.sections if len(name) > 2]
        pairs: list[tuple[str, str]] = []
        for idx in range(0, len(section_names) - 1, 2):
            pairs.append((section_names[idx], section_names[idx + 1]))
            if len(pairs) >= 4:
                break
        return pairs

    def _truncate(self, text: str, max_len: int = 280) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if len(cleaned) <= max_len:
            return cleaned
        return cleaned[: max_len - 3].rstrip() + "..."

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
