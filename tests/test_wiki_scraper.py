from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.wiki_scraper import WikipediaScraper


def test_parse_topic_html_extracts_summary_sections_and_facts() -> None:
    html = """
    <html>
      <body>
        <h1 id="firstHeading">Car</h1>
        <table class="infobox">
          <tr><th>Type</th><td>Vehicle</td></tr>
          <tr><th>Wheels</th><td>Typically four</td></tr>
        </table>
        <div id="mw-content-text">
          <div class="mw-parser-output">
            <p>A car is a wheeled motor vehicle used for transportation and is one of the most common forms of personal mobility worldwide.</p>
            <h2><span class="mw-headline">History</span></h2>
            <p>Cars evolved from horse-drawn carriages through major engineering milestones in powertrain, safety, and manufacturing.</p>
            <h2><span class="mw-headline">Technology</span></h2>
            <p>Modern cars combine sensors, software, and mechanical systems to optimize performance and reliability.</p>
            <ul>
              <li>Electric vehicles use battery packs and electric motors.</li>
            </ul>
          </div>
        </div>
      </body>
    </html>
    """

    scraper = WikipediaScraper()
    topic = scraper._parse_topic_html(html=html, url="https://en.wikipedia.org/wiki/Car")  # noqa: SLF001

    assert topic is not None
    assert topic.title == "Car"
    assert topic.summary.startswith("A car is a wheeled motor vehicle")
    assert ("Type", "Vehicle") in topic.key_facts
    assert topic.sections[0][0] == "History"
    assert topic.highlights[0].startswith("Electric vehicles")


def test_parse_topic_html_extracts_related_topics_from_see_also() -> None:
    html = """
    <html>
      <body>
        <h1 id="firstHeading">Automobile</h1>
        <div id="mw-content-text">
          <div class="mw-parser-output">
            <p>An automobile is a wheeled motor vehicle used for transportation and daily mobility around the world.</p>
            <h2><span class="mw-headline">See also</span></h2>
            <ul>
              <li><a href="/wiki/Electric_vehicle">Electric vehicle</a></li>
              <li><a href="/wiki/Hybrid_vehicle">Hybrid vehicle</a></li>
              <li><a href="/wiki/Automobile">Automobile</a></li>
            </ul>
          </div>
        </div>
      </body>
    </html>
    """

    scraper = WikipediaScraper()
    topic = scraper._parse_topic_html(html=html, url="https://en.wikipedia.org/wiki/Automobile")  # noqa: SLF001

    assert topic is not None
    assert topic.related_topics == ["Electric vehicle", "Hybrid vehicle"]


def test_parse_topic_html_extracts_related_topics_from_paragraph_links() -> None:
    html = """
    <html>
      <body>
        <h1 id="firstHeading">Automobile</h1>
        <div id="mw-content-text">
          <div class="mw-parser-output">
            <p>An automobile is a wheeled motor vehicle used for transportation and daily mobility around the world.</p>
            <h2><span class="mw-headline">See also</span></h2>
            <p>Related topics include <a href="/wiki/Electric_vehicle">Electric vehicle</a> and <a href="/wiki/Hybrid_vehicle">Hybrid vehicle</a>.</p>
          </div>
        </div>
      </body>
    </html>
    """

    scraper = WikipediaScraper()
    topic = scraper._parse_topic_html(html=html, url="https://en.wikipedia.org/wiki/Automobile")  # noqa: SLF001

    assert topic is not None
    assert topic.related_topics == ["Electric vehicle", "Hybrid vehicle"]


@pytest.mark.parametrize(
    ("raw_src", "expected"),
    [
        ("//upload.wikimedia.org/image.jpg", "https://upload.wikimedia.org/image.jpg"),
        ("/images/car.jpg", "https://en.wikipedia.org/images/car.jpg"),
        ("https://upload.wikimedia.org/image.jpg", "https://upload.wikimedia.org/image.jpg"),
    ],
)
def test_parse_topic_html_normalizes_image_url_to_https(raw_src: str, expected: str) -> None:
    html = f"""
    <html>
      <body>
        <h1 id="firstHeading">Car</h1>
        <div id="mw-content-text">
          <div class="mw-parser-output">
            <p>A car is a wheeled motor vehicle used for transportation and is one of the most common forms of personal mobility worldwide.</p>
            <figure>
              <img src="{raw_src}" width="600" />
            </figure>
          </div>
        </div>
      </body>
    </html>
    """

    scraper = WikipediaScraper()
    topic = scraper._parse_topic_html(html=html, url="https://en.wikipedia.org/wiki/Car")  # noqa: SLF001

    assert topic is not None
    assert topic.image_url == expected


def test_parse_topic_html_skips_tiny_icon_and_uses_next_image_candidate() -> None:
    html = """
    <html>
      <body>
        <h1 id="firstHeading">Car</h1>
        <table class="infobox">
          <tr>
            <td><img src="/tiny-icon.png" width="18" /></td>
          </tr>
        </table>
        <div id="mw-content-text">
          <div class="mw-parser-output">
            <p>A car is a wheeled motor vehicle used for transportation and is one of the most common forms of personal mobility worldwide.</p>
            <figure>
              <img src="//upload.wikimedia.org/full-image.jpg" width="640" />
            </figure>
          </div>
        </div>
      </body>
    </html>
    """

    scraper = WikipediaScraper()
    topic = scraper._parse_topic_html(html=html, url="https://en.wikipedia.org/wiki/Car")  # noqa: SLF001

    assert topic is not None
    assert topic.image_url == "https://upload.wikimedia.org/full-image.jpg"


@dataclass
class _FakeResponse:
    status_code: int
    url: str
    text: str


def test_fetch_and_parse_rejects_non_english_wikipedia_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    scraper = WikipediaScraper()

    def fake_get(*args, **kwargs):  # noqa: ANN002, ANN003
        return _FakeResponse(
            status_code=200,
            url="https://fr.wikipedia.org/wiki/Automobile",
            text="<html><body><h1 id='firstHeading'>Automobile</h1></body></html>",
        )

    monkeypatch.setattr("src.wiki_scraper.requests.get", fake_get)

    result = scraper._fetch_and_parse("https://en.wikipedia.org/wiki/Automobile")  # noqa: SLF001
    assert result is None


def test_fetch_and_parse_follows_disambiguation_page(monkeypatch: pytest.MonkeyPatch) -> None:
    scraper = WikipediaScraper()

    disambiguation_html = """
    <html>
      <body>
        <h1 id="firstHeading">Mercury</h1>
        <div id="mw-content-text">
          <div class="mw-parser-output">
            <table id="disambigbox"><tr><td>This is a disambiguation page.</td></tr></table>
            <ul>
              <li><a href="/wiki/Mercury_(planet)">Mercury (planet)</a></li>
              <li><a href="/wiki/Mercury_(element)">Mercury (element)</a></li>
            </ul>
          </div>
        </div>
      </body>
    </html>
    """

    topic_html = """
    <html>
      <body>
        <h1 id="firstHeading">Mercury (planet)</h1>
        <div id="mw-content-text">
          <div class="mw-parser-output">
            <p>Mercury is the smallest planet in the Solar System and the closest to the Sun, with a heavily cratered surface and extreme temperatures.</p>
            <h2><span class="mw-headline">Orbit</span></h2>
            <p>Its orbit around the Sun takes about 88 Earth days and shows a high orbital eccentricity compared to other planets.</p>
          </div>
        </div>
      </body>
    </html>
    """

    def fake_get(url, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        if url.endswith("/wiki/Mercury"):
            return _FakeResponse(
                status_code=200,
                url="https://en.wikipedia.org/wiki/Mercury",
                text=disambiguation_html,
            )
        if url.endswith("/wiki/Mercury_(planet)"):
            return _FakeResponse(
                status_code=200,
                url="https://en.wikipedia.org/wiki/Mercury_(planet)",
                text=topic_html,
            )
        raise AssertionError(f"Unexpected URL fetched: {url}")

    monkeypatch.setattr("src.wiki_scraper.requests.get", fake_get)

    result = scraper._fetch_and_parse("https://en.wikipedia.org/wiki/Mercury")  # noqa: SLF001

    assert result is not None
    assert result.title == "Mercury (planet)"
    assert result.summary.startswith("Mercury is the smallest planet")


def test_fetch_and_parse_returns_none_when_disambiguation_has_no_valid_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scraper = WikipediaScraper()

    disambiguation_html = """
    <html>
      <body>
        <h1 id="firstHeading">Mercury</h1>
        <div id="mw-content-text">
          <div class="mw-parser-output">
            <table id="disambigbox"><tr><td>This is a disambiguation page.</td></tr></table>
            <ul>
              <li><a href="/wiki/Help:Contents">Help</a></li>
              <li><a href="/wiki/File:Mercury.jpg">Image</a></li>
            </ul>
          </div>
        </div>
      </body>
    </html>
    """

    def fake_get(*args, **kwargs):  # noqa: ANN002, ANN003
        return _FakeResponse(
            status_code=200,
            url="https://en.wikipedia.org/wiki/Mercury",
            text=disambiguation_html,
        )

    monkeypatch.setattr("src.wiki_scraper.requests.get", fake_get)

    result = scraper._fetch_and_parse("https://en.wikipedia.org/wiki/Mercury")  # noqa: SLF001
    assert result is None


def test_parse_topic_html_returns_none_when_missing_firstheading() -> None:
    """Test graceful handling of malformed HTML with missing title element."""
    html = """
    <html>
      <body>
        <div id="mw-content-text">
          <div class="mw-parser-output">
            <p>Some content without a title.</p>
          </div>
        </div>
      </body>
    </html>
    """

    scraper = WikipediaScraper()
    topic = scraper._parse_topic_html(html=html, url="https://en.wikipedia.org/wiki/Car")  # noqa: SLF001

    assert topic is None


def test_parse_topic_html_returns_none_when_missing_content_div() -> None:
    """Test graceful handling of malformed HTML with missing mw-content-text div."""
    html = """
    <html>
      <body>
        <h1 id="firstHeading">Car</h1>
      </body>
    </html>
    """

    scraper = WikipediaScraper()
    topic = scraper._parse_topic_html(html=html, url="https://en.wikipedia.org/wiki/Car")  # noqa: SLF001

    assert topic is None


def test_parse_topic_html_returns_none_when_all_content_blocks_empty() -> None:
    """Test graceful handling when all extractable content (paragraphs, facts, sections, highlights) is missing or insufficient."""
    html = """
    <html>
      <body>
        <h1 id="firstHeading">Car</h1>
        <div id="mw-content-text">
          <div class="mw-parser-output">
            <p>Short.</p>
          </div>
        </div>
      </body>
    </html>
    """

    scraper = WikipediaScraper()
    topic = scraper._parse_topic_html(html=html, url="https://en.wikipedia.org/wiki/Car")  # noqa: SLF001

    assert topic is None
