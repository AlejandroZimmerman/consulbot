import hashlib
import logging
import os
import unicodedata
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

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

BASE = "https://www.caf.com"
BLOCK_MARKER = Path(__file__).resolve().parent.parent / ".caf_waf_blocked_until"
BLOCK_HOURS = int(os.getenv("CAF_BLOCK_HOURS", "24"))

ENABLE_LINKEDIN_FALLBACK = os.getenv("CAF_ENABLE_LINKEDIN_FALLBACK", "1").strip().lower() not in {
    "0", "false", "no"
}
LINKEDIN_QUERY = os.getenv(
    "CAF_LINKEDIN_QUERY",
    "CAF banco de desarrollo de america latina y el caribe",
)
LINKEDIN_LOCATION = os.getenv("CAF_LINKEDIN_LOCATION", "Latin America")
LINKEDIN_PAGE_STEPS = int(os.getenv("CAF_LINKEDIN_PAGES", "2"))


def _is_waf_page(html: str) -> bool:
    text = html.lower()
    waf_markers = (
        "incapsula",
        "_incapsula_resource",
        "request unsuccessful",
        "incident id",
        "noindex, nofollow",
    )
    return any(marker in text for marker in waf_markers)


def _read_block_until() -> datetime:
    if not BLOCK_MARKER.exists():
        return None
    try:
        content = BLOCK_MARKER.read_text(encoding="utf-8").strip()
        if not content:
            return None
        ts = datetime.fromisoformat(content)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    except Exception:
        return None


def _is_temporarily_disabled() -> bool:
    block_until = _read_block_until()
    if block_until is None:
        return False
    if block_until <= datetime.now(timezone.utc):
        try:
            BLOCK_MARKER.unlink(missing_ok=True)
        except Exception:
            pass
        return False
    return True


def _set_temporary_block() -> None:
    block_until = datetime.now(timezone.utc) + timedelta(hours=BLOCK_HOURS)
    BLOCK_MARKER.write_text(block_until.isoformat(), encoding="utf-8")


def _uid(prefix: str, href: str, title: str) -> str:
    return f"{prefix}_" + hashlib.md5(f"{href}{title}".encode()).hexdigest()[:12]


def _linkedin_stable_href(href: str) -> str:
    # LinkedIn agrega refId/trackingId que cambian cada request — se filtran
    # para que el mismo job genere siempre el mismo ID.
    return href.split("?")[0].rstrip("/")


def _norm(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text)
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    return " ".join(plain.lower().split())


def _looks_like_caf_company(company: str) -> bool:
    norm = _norm(company)
    return (
        "banco de desarrollo de america latina" in norm
        or "caf -banco de desarrollo" in norm
        or norm == "caf"
    )


def _abs_href(href: str) -> str:
    if href.startswith("http"):
        return href
    return BASE + href


def _extract_jobs_from_html(html: str, default_url: str) -> list[dict]:
    jobs = []
    soup = BeautifulSoup(html, "html.parser")

    items = (
        soup.select("article, .job-item, .vacancy-item, li.item")
        or soup.select("div.content-list li")
    )

    for item in items[:25]:
        a = item.select_one("a[href]")
        title_el = item.select_one("h2, h3, .title") or a
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if len(title) < 8:
            continue
        href = a["href"] if a else ""
        if href:
            href = _abs_href(href)
        jobs.append({
            "id": _uid("caf", href or default_url, title),
            "title": title,
            "org": "CAF",
            "body": item.get_text(separator=" ", strip=True)[:1000],
            "url": href,
            "date": "",
            "source": "CAF Portal",
        })

    if jobs:
        return jobs

    for a in soup.select("a[href]"):
        title = a.get_text(strip=True)
        href = a.get("href", "").strip()
        if not title or not href:
            continue
        text = f"{title} {href}".lower()
        if any(k in text for k in ["consultor", "vacante", "convocatoria", "analyst", "consultant"]):
            href = _abs_href(href)
            jobs.append({
                "id": _uid("caf", href, title),
                "title": title,
                "org": "CAF",
                "body": title,
                "url": href,
                "date": "",
                "source": "CAF Portal",
            })

    return jobs


async def _fetch_sitemap_fallback(client: httpx.AsyncClient) -> list[dict]:
    sitemap_url = f"{BASE}/sitemap.xml"
    try:
        resp = await client.get(sitemap_url)
        if resp.status_code >= 400 or _is_waf_page(resp.text):
            return []
        soup = BeautifulSoup(resp.text, "xml")
        jobs = []
        for loc in soup.select("url > loc")[:300]:
            href = (loc.text or "").strip()
            if not href:
                continue
            low = href.lower()
            if any(k in low for k in ["consult", "vacante", "convocatoria", "licitacion", "jobs", "trabaja"]):
                title = href.rstrip("/").split("/")[-1].replace("-", " ").strip().title()
                jobs.append({
                    "id": _uid("caf", href, title or href),
                    "title": title or "Oportunidad CAF",
                    "org": "CAF",
                    "body": title or href,
                    "url": href,
                    "date": "",
                    "source": "CAF Sitemap",
                })
                if len(jobs) >= 20:
                    break
        return jobs
    except Exception as e:
        log.warning(f"CAF sitemap fallback falló: {e}")
        return []


async def _fetch_linkedin_fallback(client: httpx.AsyncClient) -> list[dict]:
    if not ENABLE_LINKEDIN_FALLBACK:
        return []

    jobs = []
    enc_query = urllib.parse.quote(LINKEDIN_QUERY)
    enc_location = urllib.parse.quote(LINKEDIN_LOCATION)

    for page in range(max(LINKEDIN_PAGE_STEPS, 1)):
        start = page * 25
        url = (
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
            f"?keywords={enc_query}&location={enc_location}&start={start}"
        )

        try:
            resp = await client.get(url)
            if resp.status_code >= 400:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("div.base-search-card")
            for card in cards:
                title_el = card.select_one("h3.base-search-card__title")
                company_el = card.select_one("h4.base-search-card__subtitle")
                location_el = card.select_one("span.job-search-card__location")
                link_el = card.select_one("a.base-card__full-link")
                date_el = card.select_one("time")

                title = " ".join(title_el.get_text(" ", strip=True).split()) if title_el else ""
                company = " ".join(company_el.get_text(" ", strip=True).split()) if company_el else ""
                location = " ".join(location_el.get_text(" ", strip=True).split()) if location_el else ""
                href = link_el.get("href", "").strip() if link_el else ""
                date = date_el.get("datetime", "").strip() if date_el else ""

                if not title or not href:
                    continue
                if not _looks_like_caf_company(company):
                    continue

                stable_href = _linkedin_stable_href(href)
                jobs.append({
                    "id": _uid("cafli", stable_href, title),
                    "title": title,
                    "org": "CAF",
                    "body": f"{company} | {location}".strip(" |"),
                    "url": href,
                    "date": date,
                    "source": "LinkedIn Jobs (public)",
                })
        except Exception as e:
            log.warning(f"CAF LinkedIn fallback falló (start={start}): {e}")

    return jobs


async def fetch_caf() -> list[dict]:
    jobs = []
    urls = [
        f"{BASE}/es/sobre-caf/trabaja-con-nosotros/",
        f"{BASE}/es/sobre-caf/trabaja-con-nosotros/consultores/",
    ]

    waf_detected = False
    blocked_now = _is_temporarily_disabled()
    if blocked_now:
        block_until = _read_block_until()
        until = block_until.strftime("%Y-%m-%d %H:%M UTC") if block_until else "desconocido"
        log.warning(f"CAF portal omitido temporalmente por bloqueo WAF hasta {until}")

    async with httpx.AsyncClient(headers=HEADERS, timeout=25, follow_redirects=True) as client:
        if not blocked_now:
            for url in urls:
                try:
                    resp = await client.get(url)
                    if resp.status_code >= 400:
                        log.warning(f"CAF endpoint no disponible ({url}): HTTP {resp.status_code}")
                        continue

                    if _is_waf_page(resp.text):
                        waf_detected = True
                        log.warning(f"CAF bloqueado por WAF/Incapsula en {url}")
                        continue

                    jobs.extend(_extract_jobs_from_html(resp.text, url))

                except Exception as e:
                    log.warning(f"CAF fetch falló ({url}): {e}")

            if not jobs:
                jobs.extend(await _fetch_sitemap_fallback(client))

        if not jobs:
            jobs.extend(await _fetch_linkedin_fallback(client))

    seen, unique = set(), []
    for j in jobs:
        if j["id"] not in seen:
            seen.add(j["id"])
            unique.append(j)

    if not unique and waf_detected:
        _set_temporary_block()
        log.warning(f"CAF en cooldown por {BLOCK_HOURS}h debido a bloqueo WAF")

    log.info(f"CAF: {len(unique)} vacantes")
    return unique
