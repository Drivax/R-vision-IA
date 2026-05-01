# Revision IA

Revision IA is a production-ready Streamlit web app that turns any topic into a social-style learning feed powered by Wikipedia web scraping, AI-assisted enrichment, and spaced repetition.

## What It Does

- Takes a user topic (for example: planes, Roman Empire, quantum physics)
- Scrapes Wikipedia for the topic (for example: /wiki/Cars), extracts structured knowledge, and turns it into learning cards
- Generates atomic micro-learning cards (definitions, concepts, facts, comparisons, examples)
- Displays cards in a vertical feed with fast interactions
- Captures feedback: easy, medium, hard
- Schedules reviews with the SM-2 algorithm
- Tracks retention and daily progress
- Persists topics, cards, and review history in SQLite

## Project Structure

app.py  -> main Streamlit application
src/
	content_generator.py  -> Wikipedia-first card generation (optional OpenAI enrichment)
	wiki_scraper.py       -> direct Wikipedia HTML scraping and parsing
	feed_engine.py        -> feed retrieval and feedback orchestration
	spaced_repetition.py  -> SM-2 scheduling implementation
	storage.py            -> SQLite persistence and analytics queries
	ui_components.py      -> reusable Streamlit UI components and styling
	utils.py              -> date/time and normalization helpers

## Quick Start

1. Create and activate a Python virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Optional: set OpenAI credentials for AI-generated cards.

```bash
set OPENAI_API_KEY=your_key_here
set OPENAI_MODEL=gpt-4.1-mini
```

If no key is set, the app still works with Wikipedia-based generation and uses local fallback cards only when scraping fails.

4. Run the app:

```bash
streamlit run app.py
```

## Spaced Repetition Details (SM-2)

- Feedback to quality mapping:
	- easy -> 5
	- medium -> 3
	- hard -> 1
- For low quality (<3), repetition resets and next review is scheduled the next day.
- For successful reviews (>=3), interval grows as:
	- first success: 1 day
	- second success: 6 days
	- subsequent: previous interval * easiness factor
- Easiness factor is updated after each review and bounded at 1.3 minimum.

## Data Storage

SQLite database path: data/revision_ia.db

Main tables:
- topics
- cards
- reviews

The database is created automatically on first launch.

## Feed Pagination and Session History

- The feed uses cursor-based pagination across three lanes (due, new, top-up reviewed).
- Cursors and served card IDs are kept in session state to provide stable infinite pagination.
- Session history tracks topic activation, card loading, submitted reviews, feed resets, and exhaustion events.

## Run Tests

```bash
pytest -q
```

## Notes

- The feed prioritizes due cards, then unseen cards, then older reviewed cards to keep the stream active.
- UI is optimized for both desktop and mobile with a dark-friendly design.
- Content generation now uses Wikipedia scraping as the primary knowledge source to keep cards grounded in real topic data.
