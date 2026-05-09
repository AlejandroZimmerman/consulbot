import hashlib
import logging
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger("consulbot")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
}
BASE = "https://www.bcra.gob.ar"
SITEMAPS = [
    f"{BASE}/post-sitemap.xml",
    f"{BASE}/news-sitemap.xml",
    f"{BASE}/page-sitemap.xml",
]

POSITIVE = (
    "licitacion",
    "licitaciones",
    "consultor",
    "consultoria",
    "adquisicion",
    "vacante",
    "vacantes",
)
NEGATIVE = (
    "premio",
    "pintura",
    "homenaje",
    "aniversario",
    "feriado",
    "conicet",
    "bopreal",
    "lebac",
    "moneda extranjera",
)
MAX_AGE_DAYS = 365


def _uid(href: str, title: str) -> str:
    return "bcra_" + hashlib.md5(f"{href}{title}".encode()).hexdigest()[:12]


def _norm(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text)
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    return plain.lower()


def _looks_relevant(text: str) -> bool:
    norm = _norm(text)
    if any(k in norm for k in NEGATIVE):
        return False

    if any(k in norm for k in POSITIVE):
        return True

    if "convocatoria" in norm and any(
        k in norm for k in ("consultor", "vacante", "licit")
    ):
        return True

    return False


def _is_recent(lastmod: str) -> bool:
    if not lastmod:
        return True
    try:
        iso = lastmod.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
        return age <= timedelta(days=MAX_AGE_DAYS)
    except Exception:
        return True


async def _load_candidates(client: httpx.AsyncClient) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []

    for sitemap in SITEMAPS:
        try:
            resp = await client.get(sitemap)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "xml")

            for url_tag in soup.select("url"):
                loc_tag = url_tag.select_one("loc")
                if not loc_tag or not loc_tag.text.strip():
                    continue

                loc = loc_tag.text.strip()
                lastmod_tag = url_tag.select_one("lastmod")
                lastmod = lastmod_tag.text.strip() if lastmod_tag else ""

                if not _is_recent(lastmod):
                    continue

                if _looks_relevant(loc):
                    candidates.append((loc, lastmod))
        except Exception as e:
            log.error(f"BCRA sitemap falló ({sitemap}): {e}")

    candidates.sort(key=lambda x: x[1], reverse=True)
    seen = set()
    unique: list[tuple[str, str]] = []
    for loc, lastmod in candidates:
        if loc in seen:
            continue
        seen.add(loc)
        unique.append((loc, lastmod))

    return unique[:30]


async def _parse_article(client: httpx.AsyncClient, url: str, lastmod: str) -> Optional[dict]:
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        title = ""
        og_title = soup.select_one('meta[property="og:title"]')
        if og_title and og_title.get("content"):
            title = og_title.get("content", "").strip()
        if not title and soup.title:
            title = soup.title.get_text(strip=True)
        if not title:
            h1 = soup.select_one("h1")
            title = h1.get_text(strip=True) if h1 else ""

        desc = ""
        meta_desc = soup.select_one('meta[name="description"]')
        if meta_desc and meta_desc.get("content"):
            desc = meta_desc.get("content", "").strip()
        if not desc:
            p = soup.select_one("article p, .entry-content p, .post-content p, main p")
            desc = p.get_text(separator=" ", strip=True) if p else ""

        if not title or not _looks_relevant(f"{title} {desc}"):
            return None

        return {
            "id": _uid(url, title),
            "title": title,
            "org": "BCRA",
            "body": (desc or title)[:1200],
            "url": url,
            "date": (lastmod or "")[:10],
            "source": "BCRA Sitio institucional",
        }
    except Exception as e:
        log.error(f"BCRA detalle falló ({url}): {e}")
        return None


async def fetch_bcra() -> list[dict]:
    jobs = []

    async with httpx.AsyncClient(headers=HEADERS, timeout=25, follow_redirects=True) as client:
        candidates = await _load_candidates(client)
        for url, lastmod in candidates:
            job = await _parse_article(client, url, lastmod)
            if job is None:
                continue
            jobs.append(job)
            if len(jobs) >= 20:
                break

    seen = set()
    unique = []
    for j in jobs:
        if j["id"] in seen:
            continue
        seen.add(j["id"])
        unique.append(j)

    log.info(f"BCRA: {len(unique)} convocatorias")
    return unique
