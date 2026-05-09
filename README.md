# ConsulBot

A Telegram bot that monitors job and consultancy openings across major international organizations and delivers real-time notifications — filtered by relevance to your profile.

Built to solve a personal problem: checking seven different portals manually every few days is tedious and easy to miss. ConsulBot does it automatically twice a day, scores each posting, and sends only what's worth reading.

**Zero cost.** No paid APIs, no cloud services required.

---

## What it does

Every 12 hours the bot fetches new postings from seven sources, deduplicates against a local SQLite database, scores each position using keyword matching, and pushes Telegram notifications for anything that clears the relevance threshold.

```
ConsulBot — 09/05 08:00
⭐⭐ *Data Scientist — Development Impact Evaluation*
🏛 BID / IDB
🌐 Remoto / Home-based
📊 Score 8/10 — Match: data, econometr, research
📅 2026-05-07
🔗 Ver convocatoria
```

Positions that require physical presence outside Argentina are automatically filtered out. The scorer distinguishes remote roles, Buenos Aires on-site, and overseas-only postings using both structured API fields and free-text heuristics.

---

## Sources monitored

| Organization | Method |
|---|---|
| BID / IDB | Internal SuccessFactors API (JSON) |
| World Bank | HTML scraping — Workday portal + DIME jobs page |
| CEPAL / ECLAC | HTML scraping — employment portal |
| UNDP / PNUD | RSS feeds (Argentina + Economics track) |
| CAF | HTML scraping with LinkedIn public fallback |
| IMF / FMI | HTML scraping — recruitment page |
| BCRA | Sitemap-driven scraping of institutional postings |

The CAF portal uses Incapsula WAF, so the scraper detects blocks, sets a 24-hour cooldown, and falls back to LinkedIn's public jobs API for the same employer.

---

## Architecture

```
bot.py               — orchestrator: runs all sources in parallel via asyncio.gather()
scorer.py            — keyword scorer + remote/location detection
db.py                — SQLite deduplication layer (seen_jobs.db)
sources/
  iadb.py            — BID: two POST queries (Buenos Aires + consultant keyword)
  worldbank.py       — World Bank: Workday portal + DIME page
  cepal.py           — CEPAL: HTML with multi-selector fallback
  undp.py            — UNDP: feedparser over RSS
  caf.py             — CAF: HTML → sitemap → LinkedIn fallback chain
  imf.py             — IMF: link extraction from recruitment page
  bcra.py            — BCRA: sitemap-driven, sequential article fetching
run_consulbot.sh     — cron wrapper with per-window deduplication and lock
```

Each source returns a uniform `list[dict]` with `id`, `title`, `org`, `body`, `url`, `date`. The scorer receives that dict and returns `{relevant, score, reason, remote_ok}`. The bot only calls the Telegram API for jobs where `relevant=True`.

The cron wrapper uses an atomic `mkdir` lock to prevent overlapping runs and tracks a per-12h window key so the job never fires twice in the same window even if cron misfires.

---

## Scoring

`scorer.py` assigns a 1–10 score based on keyword hits in title + body:

- **+2 per positive keyword** — economics, data, statistics, policy, evaluation, remote/Argentina location markers, consultant, etc.
- **−3 per negative keyword** — driver, nurse, legal counsel, etc.
- **+2 bonus** if the title directly matches a high-signal role (analyst, economist, researcher…)
- Threshold: `score >= 5` and location not confirmed overseas-only

The keyword lists are intentional and easy to tune for any profile.

---

## Setup

### Prerequisites
- Python 3.9+
- A Telegram bot token (from [@BotFather](https://t.me/botfather))
- Your Telegram chat ID (from [@userinfobot](https://t.me/userinfobot))

### Install

```bash
git clone https://github.com/your-username/consulbot
cd consulbot
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt                      # or: uv sync
```

Create a `.env` file:

```
TELEGRAM_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

### Run

```bash
python bot.py
```

The first run processes all current postings and marks them as seen. Subsequent runs only notify on new ones.

### Schedule (Mac/Linux)

```bash
crontab -e
```

```
0 */6 * * * /path/to/consulbot/run_consulbot.sh
```

The wrapper script ensures at most one run per 12-hour window regardless of cron frequency.

### Schedule (Windows)

Use Task Scheduler → trigger every 6 hours → action: run `python bot.py` from the project directory with the `.venv` interpreter.

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_TOKEN` | — | Bot token from BotFather |
| `TELEGRAM_CHAT_ID` | — | Your Telegram user/chat ID |
| `CAF_BLOCK_HOURS` | `24` | WAF cooldown duration in hours |
| `CAF_ENABLE_LINKEDIN_FALLBACK` | `1` | Set to `0` to disable LinkedIn fallback |
| `CAF_LINKEDIN_PAGES` | `2` | Pages to fetch from LinkedIn (25 results each) |

To tune relevance, edit the keyword lists in `scorer.py` and adjust the `score >= 5` threshold.

---

## Stack

- **Python 3.9+** with `asyncio`
- **httpx** — async HTTP client
- **BeautifulSoup4 + lxml** — HTML/XML parsing
- **feedparser** — RSS parsing
- **python-telegram-bot** — Telegram Bot API
- **SQLite** (stdlib) — deduplication store
- **python-dotenv** — environment config
