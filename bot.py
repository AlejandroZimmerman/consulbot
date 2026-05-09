"""
ConsulBot — Telegram bot que monitorea consultorías de organismos internacionales.
Versión GRATUITA: no usa API de Anthropic, filtra por keywords.

Fuentes: BID, Banco Mundial, CEPAL, UNDP, CAF, FMI, BCRA.
Uso:  python bot.py
"""

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path

from telegram import Bot
from telegram.constants import ParseMode
from dotenv import load_dotenv

from db import init_db, is_new, mark_seen
from scorer import score_job
from sources.iadb      import fetch_iadb
from sources.worldbank import fetch_worldbank
from sources.cepal     import fetch_cepal
from sources.undp      import fetch_undp
from sources.caf       import fetch_caf
from sources.imf       import fetch_imf
from sources.bcra      import fetch_bcra

load_dotenv()

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
LOG_PATH         = Path(__file__).parent / "consulbot.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()]
)
log = logging.getLogger("consulbot")


def format_message(job: dict, scoring: dict) -> str:
    score  = scoring.get("score", 0)
    reason = scoring.get("reason", "")
    remote = scoring.get("remote_ok")

    stars = "🔥🔥🔥" if score >= 9 else ("⭐⭐" if score >= 7 else "⭐")

    if remote is True:
        loc = "🌐 Remoto / Home-based"
    elif remote is None:
        loc = "📍 Ubicación no especificada"
    else:
        loc = "🏢 Requiere presencia"

    # Mostrar ubicaciones reales si las tenemos (del IADB)
    locations_raw = job.get("_locations", "")
    if locations_raw:
        # Limpiar y resumir: "Argentina Buenos Aires , Peru Lima , ..." → "Buenos Aires, Lima, ..."
        cities = [
            part.strip().split()[-1]          # última palabra de cada "País Ciudad"
            for part in locations_raw.split(",")
            if part.strip()
        ][:5]
        loc_detail = f"\n📌 {', '.join(cities)}"
    else:
        loc_detail = ""

    modality = job.get("_modality", "")
    if modality:
        loc = f"{'🌐' if 'remote' in modality.lower() else '🏢'} {modality}"

    lines = [
        f"{stars} *{job['title']}*",
        f"🏛 {job['org']}",
        loc + loc_detail,
        f"📊 Score {score}/10 — _{reason}_",
    ]
    if job.get("date"):
        lines.append(f"📅 {str(job['date'])[:10]}")
    if job.get("url"):
        lines.append(f"🔗 [Ver convocatoria]({job['url']})")
    return "\n".join(lines)


async def run():
    log.info("=" * 55)
    log.info(f"ConsulBot iniciado — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    init_db()

    bot = Bot(token=TELEGRAM_TOKEN)

    # Fetch todas las fuentes en paralelo
    results = await asyncio.gather(
        fetch_iadb(),
        fetch_worldbank(),
        fetch_cepal(),
        fetch_undp(),
        fetch_caf(),
        fetch_imf(),
        fetch_bcra(),
        return_exceptions=True,
    )

    all_jobs = []
    for r in results:
        if isinstance(r, list):
            all_jobs.extend(r)
        else:
            log.error(f"Fuente falló: {r}")

    log.info(f"Total vacantes obtenidas: {len(all_jobs)}")

    new_jobs = [j for j in all_jobs if is_new(j["id"])]
    log.info(f"Nuevas (no vistas antes): {len(new_jobs)}")

    sent = 0
    for job in new_jobs:
        mark_seen(job["id"], job["title"], job["org"])

        # Pasar campos extra del IADB al scorer
        scoring = score_job(
            job["title"],
            job["body"],
            job["org"],
            _modality=job.get("_modality", ""),
            _locations=job.get("_locations", ""),
        )
        log.info(f"  [{scoring['score']}/10] {job['org']} — {job['title'][:55]}")

        if scoring.get("relevant"):
            msg = format_message(job, scoring)
            try:
                await bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=msg,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True,
                )
                sent += 1
                await asyncio.sleep(0.4)
            except Exception as e:
                log.error(f"Telegram error: {e}")

    # Resumen si no hubo nada relevante
    if sent == 0:
        summary = (
            f"🤖 *ConsulBot* — {datetime.now().strftime('%d/%m %H:%M')}\n"
            f"Revisé {len(new_jobs)} vacantes nuevas. Sin matches hoy."
        )
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=summary,
            parse_mode=ParseMode.MARKDOWN,
        )

    log.info(f"Notificaciones enviadas: {sent}. Pipeline completo.")


if __name__ == "__main__":
    asyncio.run(run())
