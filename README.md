# Revision IA

Revision IA is a production-ready Streamlit web app that turns any topic into a social-style learning feed powered by AI generation and spaced repetition.

## What It Does

- Takes a user topic (for example: planes, Roman Empire, quantum physics)
- Generates atomic micro-learning cards (definitions, concepts, facts, comparisons, examples)
- Displays cards in a vertical feed with fast interactions
- Captures feedback: easy, medium, hard
- Schedules reviews with the SM-2 algorithm
- Tracks retention and daily progress
- Persists topics, cards, and review history in SQLite

## Project Structure

app.py  -> main Streamlit application
src/
	content_generator.py  -> topic to micro-content generation (OpenAI + local fallback)
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

If no key is set, the app automatically uses a local fallback generator.

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

## Notes

- The feed prioritizes due cards, then unseen cards, then older reviewed cards to keep the stream active.
- UI is optimized for both desktop and mobile with a dark-friendly design.
