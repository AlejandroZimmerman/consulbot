import hashlib
import logging
import httpx
from bs4 import BeautifulSoup

log = logging.getLogger("consulbot")

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; consulbot/1.0)"}

URLS = [
    "https://worldbankgroup.csod.com/ux/ats/careersite/4/home?c=worldbankgroup&sq=consultant",
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

                if "impactevaluation" in url:
                    for item in soup.select("div.item, li, p")[:30]:
                        text = item.get_text(strip=True)
                        if len(text) < 20:
                            continue
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

    seen, unique = set(), []
    for j in jobs:
        if j["id"] not in seen:
            seen.add(j["id"])
            unique.append(j)

    log.info(f"Banco Mundial: {len(unique)} vacantes")
    return unique
