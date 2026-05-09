# ConsulBot

A Telegram bot that monitors job openings across international organizations and public institutions and delivers real-time notifications filtered by relevance to my profile.

Built to solve a personal problem: checking multiple different portals manually every few days is easy to miss. This does it automatically twice a day, scores each posting, and sends only what's worth reading.

---

## What it does

Every 12 hours the bot fetches new postings from all sources in parallel, deduplicates against a local database, scores each position by relevance, and sends a Telegram notification for anything that clears the threshold.

---

## How it's built

The project has four main pieces:

- **Sources** — one module per organization, each returning a uniform list of job postings. Some use public APIs, others RSS feeds, others HTML scraping. One source includes a fallback chain for when the main portal blocks automated requests.
- **Scorer** — keyword-based relevance engine that assigns a 1–10 score and detects whether the role is doable from Buenos Aires.
- **Deduplication layer** — SQLite database that tracks every seen job ID so the same posting never triggers a second notification.
- **Orchestrator** — fetches all sources in parallel, filters by score, and calls the Telegram API only for relevant results.

The bot also includes a shell wrapper for scheduled execution that prevents overlapping runs using an atomic lock.

---

## Setup

Requires Python 3.9+ and a free Telegram bot (instructions [here](https://core.telegram.org/bots#botfather)). Configure credentials in a `.env` file and run:

```bash
python bot.py
```

The first run marks all current postings as seen. From then on it only notifies on new ones. Scheduling can be set up with cron (Mac/Linux) or Task Scheduler (Windows).

---

## Configuration

Relevance tuning is done by editing the keyword lists in `scorer.py` — no code changes needed, just add or remove terms that match your profile.

| Variable | Description |
|---|---|
| `TELEGRAM_TOKEN` | Bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Your Telegram user ID |
