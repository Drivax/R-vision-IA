from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup


def _clean_text(value: str) -> str:
    no_refs = re.sub(r"\[[^\]]+\]", "", value)
    compact = re.sub(r"\s+", " ", no_refs).strip()
    return compact


def _make_https(src: str) -> str:
    """Normalise a relative or protocol-relative image URL to https://."""
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        return "https://en.wikipedia.org" + src
    return src


@dataclass
class WikiTopicData:
    title: str
    url: str
    summary: str
    paragraphs: list[str]
    key_facts: list[tuple[str, str]]
    sections: list[tuple[str, str]]
    highlights: list[str]
    image_url: Optional[str] = None


class WikipediaScraper:
    """Fetch and parse topic information directly from English Wikipedia pages.

    Only en.wikipedia.org is supported; redirects to other language editions
    are rejected.  Scraped results are cached in SQLite via an optional
    Storage instance to avoid repeated HTTP requests for the same topic.
    """

    BASE_URL = "https://en.wikipedia.org"

    def __init__(self, timeout: int = 10, storage=None) -> None:
        self.timeout = timeout
        self._storage = storage  # optional src.storage.Storage instance

    def scrape_topic(self, topic: str) -> Optional[WikiTopicData]:
        topic = topic.strip()
        if not topic:
            return None

        # --- cache lookup ---
        if self._storage is not None:
            from src.utils import normalize_topic
            normalized = normalize_topic(topic)
            cached = self._storage.get_wiki_cache(normalized)
            if cached is not None:
                return cached

        candidates = [
            f"{self.BASE_URL}/wiki/{quote(topic.replace(' ', '_'))}",
            f"{self.BASE_URL}/wiki/{quote(topic.title().replace(' ', '_'))}",
            f"{self.BASE_URL}/wiki/{quote(topic.lower().replace(' ', '_'))}",
        ]

        visited: set[str] = set()
        for url in candidates:
            if url in visited:
                continue
            visited.add(url)
            data = self._fetch_and_parse(url)
            if data:
                # --- cache store ---
                if self._storage is not None:
                    from src.utils import normalize_topic
                    self._storage.set_wiki_cache(normalize_topic(topic), data)
                return data
        return None

    def _fetch_and_parse(self, url: str) -> WikiTopicData | None:
        try:
            response = requests.get(
                url,
                timeout=self.timeout,
                headers={
                    "User-Agent": "RevisionIA/1.0 (educational project)",
                    "Accept-Language": "en",
                },
            )
        except requests.RequestException:
            return None

        if response.status_code != 200:
            return None

        # Wikipedia redirects aliases (e.g., Car -> Automobile), which is expected.
        # However we reject redirects to other language editions.
        final_url = response.url
        if "en.wikipedia.org" not in final_url or "/wiki/" not in final_url:
            return None

        return self._parse_topic_html(html=response.text, url=final_url)

    def _parse_topic_html(self, html: str, url: str) -> WikiTopicData | None:
        soup = BeautifulSoup(html, "html.parser")

        title_node = soup.select_one("#firstHeading")
        if not title_node:
            return None
        title = _clean_text(title_node.get_text(" ", strip=True))

        content = soup.select_one("div#mw-content-text")
        if not content:
            return None

        paragraphs: list[str] = []
        for p in content.select("div.mw-parser-output > p"):
            text = _clean_text(p.get_text(" ", strip=True))
            if len(text) < 60:
                continue
            paragraphs.append(text)
            if len(paragraphs) >= 6:
                break

        summary = paragraphs[0] if paragraphs else ""

        key_facts: list[tuple[str, str]] = []
        infobox = soup.select_one("table.infobox")
        if infobox:
            for row in infobox.select("tr"):
                key = row.select_one("th")
                value = row.select_one("td")
                if not key or not value:
                    continue
                k_text = _clean_text(key.get_text(" ", strip=True))
                v_text = _clean_text(value.get_text(" ", strip=True))
                if not k_text or not v_text:
                    continue
                if len(v_text) > 220:
                    v_text = v_text[:217].rstrip() + "..."
                key_facts.append((k_text, v_text))
                if len(key_facts) >= 10:
                    break

        sections: list[tuple[str, str]] = []
        for h in content.select("div.mw-parser-output > h2, div.mw-parser-output > h3"):
            heading_text = _clean_text(h.get_text(" ", strip=True))
            if not heading_text or heading_text.lower() in {"references", "external links", "see also"}:
                continue

            body_text = ""
            sibling = h.find_next_sibling()
            while sibling is not None and sibling.name not in {"h2", "h3"}:
                if sibling.name == "p":
                    maybe_text = _clean_text(sibling.get_text(" ", strip=True))
                    if len(maybe_text) >= 60:
                        body_text = maybe_text
                        break
                sibling = sibling.find_next_sibling()

            if body_text:
                sections.append((heading_text, body_text))
            if len(sections) >= 8:
                break

        highlights: list[str] = []
        for li in content.select("div.mw-parser-output > ul > li"):
            text = _clean_text(li.get_text(" ", strip=True))
            if len(text) < 50:
                continue
            if len(text) > 220:
                text = text[:217].rstrip() + "..."
            highlights.append(text)
            if len(highlights) >= 10:
                break

        if not summary and not key_facts and not sections and not highlights:
            return None

        image_url = self._extract_main_image(soup, content)

        return WikiTopicData(
            title=title,
            url=url,
            summary=summary,
            paragraphs=paragraphs,
            key_facts=key_facts,
            sections=sections,
            highlights=highlights,
            image_url=image_url,
        )

    def _extract_main_image(self, soup: BeautifulSoup, content: Any) -> Optional[str]:
        """Return an absolute HTTPS URL for the main article image, or None."""
        candidates = [
            # 1. Infobox image (most reliable for articles with infoboxes)
            soup.select_one("table.infobox img"),
            # 2. First figure image in article body
            content.select_one("figure img"),
            # 3. Any first image in the parser output
            content.select_one("div.mw-parser-output img"),
        ]
        for img in candidates:
            if img is None:
                continue
            src = img.get("src", "") or ""
            if not src or "Special:" in src:
                continue
            # Skip tiny icons / flags (width <= 30)
            try:
                width = int(img.get("width", 0) or 0)
                if 0 < width <= 30:
                    continue
            except (ValueError, TypeError):
                pass
            return _make_https(src)
        return None
