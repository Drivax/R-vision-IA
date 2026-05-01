from __future__ import annotations

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
