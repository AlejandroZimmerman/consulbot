import hashlib
import logging
import httpx
from bs4 import BeautifulSoup

log = logging.getLogger("consulbot")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; consulbot/1.0)"}


def _uid(href: str, title: str) -> str:
    return "imf_" + hashlib.md5(f"{href}{title}".encode()).hexdigest()[:12]


async def fetch_imf() -> list[dict]:
    jobs = []
    urls = [
        "https://www.imf.org/en/About/Recruitment",
    ]
    async with httpx.AsyncClient(headers=HEADERS, timeout=25, follow_redirects=True) as client:
        for url in urls:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                for a in soup.select("a[href]"):
                    text = a.get_text(strip=True).lower()
                    if any(k in text for k in ["economist", "consultant", "analyst", "advisor", "statistician"]):
                        href = a["href"]
                        if not href.startswith("http"):
                            href = "https://www.imf.org" + href
                        title = a.get_text(strip=True)
                        if len(title) < 5:
                            continue
                        jobs.append({
                            "id":    _uid(href, title),
                            "title": title,
                            "org":   "FMI / IMF",
                            "body":  title,
                            "url":   href,
                            "date":  "",
                            "source": "IMF Careers",
                        })

            except Exception as e:
                log.error(f"IMF fetch falló ({url}): {e}")

    seen, unique = set(), []
    for j in jobs:
        if j["id"] not in seen:
            seen.add(j["id"])
            unique.append(j)

    log.info(f"IMF: {len(unique)} vacantes")
    return unique
