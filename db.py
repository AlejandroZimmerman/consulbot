"""Módulo de base de datos SQLite para deduplicación de vacantes."""
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "seen_jobs.db"


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS seen_jobs (
                id       TEXT PRIMARY KEY,
                title    TEXT,
                org      TEXT,
                seen_at  TEXT
            )
        """)


def is_new(job_id: str) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT 1 FROM seen_jobs WHERE id = ?", (job_id,)
        ).fetchone()
    return row is None


def mark_seen(job_id: str, title: str, org: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO seen_jobs (id, title, org, seen_at) VALUES (?,?,?,?)",
            (job_id, title, org, datetime.utcnow().isoformat()),
        )
