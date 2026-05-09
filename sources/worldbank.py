"""
Fuente: Banco Mundial / World Bank Group
Portal: careers.worldbank.org (Workday)
La búsqueda filtra por "consultant" y "Buenos Aires" / remoto.
Nota: el BM está eliminando STCs para 2027, pero ETC y roles de staff
y contratos via PIU (Project Implementation Units) siguen activos.
"""
import hashlib
import logging
import httpx
from bs4 import BeautifulSoup

log = logging.getLogger("consulbot")

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; consulbot/1.0)"}

# El portal del Banco Mundial usa Workday — scrapeamos la página de búsqueda
# con filtros de texto. También monitoreamos el portal de DIME (Development Impact).
URLS = [
    "https://worldbankgroup.csod.com/ux/ats/careersite/4/home?c=worldbankgroup&sq=consultant",
    # Portal de DIME — convocatorias frecuentes de RA y STC para investigación
    "https://www.worldbank.org/en/about/unit/unit-dec/impactevaluation/JobOpenings",
]


def _uid(href: str, title: str) -> str:
    return "wb_" + hashlib.md5(f"{href}{title}".encode()).hexdigest()[:12]


async def fetch_worldbank() -> list[dict]:
    jobs = []
    async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        for url in URLS:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                # DIME jobs page — estructura más simple
                if "impactevaluation" in url:
                    for item in soup.select("div.item, li, p")[:30]:
                        text = item.get_text(strip=True)
                        if len(text) < 20:
                            continue
                        # Heurística: buscar texto con "consultant", "RA", "analyst"
                        lower = text.lower()
                        if any(kw in lower for kw in ["consultant", "research assistant", "analyst", "sta "]):
                            a = item.select_one("a[href]")
                            href = a["href"] if a else url
                            if href and not href.startswith("http"):
                                href = "https://www.worldbank.org" + href
                            title = (item.select_one("strong, b, a") or item).get_text(strip=True)[:120]
                            jobs.append({
                                "id":    _uid(href, title),
                                "title": title,
                                "org":   "Banco Mundial / World Bank",
                                "body":  text[:1500],
                                "url":   href,
                                "date":  "",
                                "source": "WB DIME Jobs",
                            })
                else:
                    # Portal Workday — las tarjetas de trabajo
                    cards = (
                        soup.select("li[class*='job']")
                        or soup.select("div[class*='job-listing']")
                        or soup.select("section[class*='jobList'] li")
                    )
                    for card in cards[:25]:
                        a = card.select_one("a[href]")
                        title_el = card.select_one("h2, h3, span[class*='title']") or a
                        if not title_el:
                            continue
                        title = title_el.get_text(strip=True)
                        href  = a["href"] if a else ""
                        if href and not href.startswith("http"):
                            href = "https://worldbankgroup.csod.com" + href
                        jobs.append({
                            "id":    _uid(href or url, title),
                            "title": title,
                            "org":   "Banco Mundial / World Bank",
                            "body":  card.get_text(separator=" ", strip=True)[:1500],
                            "url":   href,
                            "date":  "",
                            "source": "WB Careers",
                        })

            except Exception as e:
                log.error(f"WorldBank fetch falló ({url}): {e}")

    # deduplicar
    seen, unique = set(), []
    for j in jobs:
        if j["id"] not in seen:
            seen.add(j["id"])
            unique.append(j)

    log.info(f"Banco Mundial: {len(unique)} vacantes")
    return unique
