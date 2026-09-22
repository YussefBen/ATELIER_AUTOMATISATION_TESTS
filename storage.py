"""Stockage SQLite des runs de tests.

La base est placée dans le dossier personnel (hors du dossier du site) pour que
les déploiements automatiques de l'Action GitHub n'écrasent jamais l'historique.
"""
import json
import os
import sqlite3
import time

DB_PATH = os.environ.get(
    "RUNS_DB_PATH",
    os.path.join(os.path.expanduser("~"), "api_monitoring_runs.db"),
)


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                created_at REAL NOT NULL,
                trigger TEXT NOT NULL,
                passed INTEGER NOT NULL,
                failed INTEGER NOT NULL,
                errors INTEGER NOT NULL,
                total INTEGER NOT NULL,
                error_rate REAL NOT NULL,
                latency_ms_avg REAL,
                latency_ms_p95 REAL,
                availability REAL NOT NULL,
                verdict TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )


def save_run(run):
    s = run["summary"]
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO runs (api, timestamp, created_at, trigger, passed, failed, errors, total,
                              error_rate, latency_ms_avg, latency_ms_p95, availability, verdict, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run["api"], run["timestamp"], time.time(), run["trigger"],
                s["passed"], s["failed"], s["errors"], s["total"],
                s["error_rate"], s["latency_ms_avg"], s["latency_ms_p95"],
                s["availability"], s["verdict"], json.dumps(run, ensure_ascii=False),
            ),
        )
        return cur.lastrowid


def _row_to_run(row):
    run = json.loads(row["payload"])
    run["id"] = row["id"]
    run["created_at"] = row["created_at"]
    return run


def list_runs(limit=50):
    query = "SELECT id, created_at, payload FROM runs ORDER BY id DESC"
    params = ()
    if limit is not None:
        query += " LIMIT ?"
        params = (limit,)
    with _connect() as conn:
        return [_row_to_run(r) for r in conn.execute(query, params)]


def get_last_run():
    runs = list_runs(limit=1)
    return runs[0] if runs else None


def count_runs():
    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
