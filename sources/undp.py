"""
Fuente: UNDP / PNUD
UNDP tiene RSS feeds oficiales y gratuitos para consultorías.
https://jobs.undp.org/cj_rss_feed.cfm
Usamos el feed de todas las consultorías + el feed de Argentina específicamente.
"""
import hashlib
import logging
import httpx
import feedparser

log = logging.getLogger("consulbot")

RSS_FEEDS = [
    # Feed específico de Argentina
    "https://jobs.undp.org/rss_feeds/ARG.xml",
    # Feed de Economics / Sustainable Finance (el área más relevante)
    "https://jobs.undp.org/cj_rss_feed.cfm?type=1&lev=5",
]


def _uid(entry_id: str) -> str:
    return "undp_" + hashlib.md5(entry_id.encode()).hexdigest()[:12]


async def fetch_undp() -> list[dict]:
    jobs = []
    async with httpx.AsyncClient(timeout=20) as client:
        for url in RSS_FEEDS:
            try:
                resp = await client.get(url)
                feed = feedparser.parse(resp.text)

                for entry in feed.entries[:30]:
                    entry_id = entry.get("id") or entry.get("link") or entry.get("title", "")
                    title    = entry.get("title", "").strip()
                    if not title:
                        continue

                    jobs.append({
                        "id":    _uid(entry_id),
                        "title": title,
                        "org":   "UNDP / PNUD",
                        "body":  entry.get("summary", ""),
                        "url":   entry.get("link", ""),
                        "date":  entry.get("published", ""),
                        "source": "UNDP RSS",
                    })

            except Exception as e:
                log.error(f"UNDP RSS falló ({url}): {e}")

    seen, unique = set(), []
    for j in jobs:
        if j["id"] not in seen:
            seen.add(j["id"])
            unique.append(j)

    log.info(f"UNDP: {len(unique)} vacantes")
    return unique
