import hashlib
import logging
import re

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
BASE = "https://www.cepal.org"
URLS = [
    f"{BASE}/es/oportunidades-empleo",
    f"{BASE}/en/employment",
]

KEYWORDS = (
    "consultor",
    "consultora",
    "consultant",
    "vacancy",
    "vacancies",
    "opening",
    "job opening",
    "position",
)
SKIP_LINKS = {
    "/es/oportunidades-empleo",
    "/en/employment",
    "/es",
    "/en",
}


def _uid(href: str, title: str) -> str:
    return "cepal_" + hashlib.md5(f"{href}{title}".encode()).hexdigest()[:12]


def _abs_href(href: str) -> str:
    if href.startswith("http"):
        return href
    return BASE + href


def _is_access_denied(resp_text: str) -> bool:
    lower = resp_text.lower()
    return "access denied" in lower or "request id" in lower


def _parse_items(soup: BeautifulSoup) -> list[dict]:
    jobs = []

    items = (
        soup.select("article.node--type-vacancy")
        or soup.select("div.view-content .views-row")
        or soup.select("table.views-table tbody tr")
        or soup.select("li.views-row")
    )

    for item in items[:20]:
        a = item.select_one("a[href]")
        title_el = item.select_one("h3, h2, td.views-field-title, .node__title") or a
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if len(title) < 8:
            continue
        href = a["href"] if a else ""
        if href:
            href = _abs_href(href)

        jobs.append({
            "id": _uid(href or "", title),
            "title": title,
            "org": "CEPAL / ECLAC",
            "body": item.get_text(separator=" ", strip=True)[:1500],
            "url": href,
            "date": "",
            "source": "CEPAL Empleo",
        })

    if jobs:
        return jobs

    for a in soup.select("a[href]"):
        title = " ".join(a.get_text(separator=" ", strip=True).split())
        href = a.get("href", "").strip()
        if not href or href.startswith("#"):
            continue
        combo = f"{title} {href}".lower()

        if href in SKIP_LINKS:
            continue
        if not any(k in combo for k in KEYWORDS):
            continue
        if re.search(r"(facebook|twitter|youtube|linkedin|areas-trabajo)", combo):
            continue

        abs_href = _abs_href(href)
        jobs.append({
            "id": _uid(abs_href, title or abs_href),
            "title": title or "Oportunidad CEPAL",
            "org": "CEPAL / ECLAC",
            "body": title or abs_href,
            "url": abs_href,
            "date": "",
            "source": "CEPAL Empleo",
        })

    return jobs


async def fetch_cepal() -> list[dict]:
    jobs = []
    async with httpx.AsyncClient(headers=HEADERS, timeout=25, follow_redirects=True) as client:
        for url in URLS:
            try:
                resp = await client.get(url)
                resp.raise_for_status()

                if _is_access_denied(resp.text):
                    log.warning(f"CEPAL acceso denegado en {url}")
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")

                jobs.extend(_parse_items(soup))

            except Exception as e:
                log.error(f"CEPAL fetch falló ({url}): {e}")

    seen, unique = set(), []
    for j in jobs:
        if j["id"] not in seen:
            seen.add(j["id"])
            unique.append(j)

    log.info(f"CEPAL: {len(unique)} vacantes")
    return unique
