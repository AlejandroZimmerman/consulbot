"""
Fuente: BID / Inter-American Development Bank
Usa la API interna que el portal jobs.iadb.org llama para renderizar
resultados (SuccessFactors). Descubierta monitoreando llamadas de red.

  POST https://jobs.iadb.org/services/recruiting/v1/jobs

Dos búsquedas:
  1. locationText="buenos aires" → vacantes donde BA es una opción
  2. searchKeyword="consultant" sin filtro de ciudad → captura remotos
"""
import logging
import httpx

log = logging.getLogger("consulbot")

API_URL = "https://jobs.iadb.org/services/recruiting/v1/jobs"
JOB_URL = "https://jobs.iadb.org/job/{url_title}/{job_id}-en_US"

HEADERS = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": "Mozilla/5.0 (compatible; consulbot/1.0)",
    "Referer": "https://jobs.iadb.org/search/",
}

SEARCHES = [
    # Todos los roles donde Buenos Aires es una opción (sin filtro de keyword)
    {"searchKeyword": "", "locationText": "buenos aires",
     "locale": "en_US", "resultsPerPage": 50, "currentPage": 0},
    # Consultorías sin filtro de ciudad (captura remotos sin BA explícita)
    {"searchKeyword": "consultant", "locationText": "",
     "locale": "en_US", "resultsPerPage": 50, "currentPage": 0},
]


async def fetch_iadb() -> list[dict]:
    jobs = []
    seen_ids: set[str] = set()

    async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
        for payload in SEARCHES:
            try:
                resp = await client.post(API_URL, json=payload)
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("jobSearchResult", []):
                    r = item.get("response", {})
                    job_id    = str(r.get("id", ""))
                    title     = r.get("unifiedStandardTitle", "").strip()
                    url_title = r.get("unifiedUrlTitle", r.get("urlTitle", ""))
                    modality  = r.get("cust_workModality", [])   # ["Remote"] o ["On site"]
                    locations = r.get("jobLocationShort", [])    # ["Argentina Buenos Aires ", ...]
                    start_dt  = r.get("unifiedStandardStart", "")

                    if not title or job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)

                    url      = JOB_URL.format(url_title=url_title, job_id=job_id)
                    mod_text = modality[0] if modality else ""
                    loc_text = ", ".join(locations) if locations else ""

                    # Body descriptivo para el scorer (en caso de que no use los campos directos)
                    body = (f"Work modality: {mod_text}. "
                            f"Locations: {loc_text}. "
                            f"{title}.")

                    jobs.append({
                        "id":        f"iadb_{job_id}",
                        "title":     title,
                        "org":       "BID / IDB",
                        "body":      body,
                        "url":       url,
                        "date":      start_dt,
                        "source":    "IADB API",
                        "_modality": mod_text,   # campo directo para el scorer
                        "_locations": loc_text,  # campo directo para el scorer
                    })

            except Exception as e:
                loc = payload.get("locationText", "") or "global"
                log.error(f"IADB API falló ({loc}): {e}")

    log.info(f"IADB: {len(jobs)} vacantes")
    return jobs
