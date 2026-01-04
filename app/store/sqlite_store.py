# app/store/sqlite_store.py
import sqlite3
from typing import Optional
from datetime import datetime, timezone

class SqliteStore:
    def __init__(self, path: str = "alerts.db"):
        self.path = path
        with sqlite3.connect(self.path) as con:
            con.execute("""
              CREATE TABLE IF NOT EXISTS alerts (
                ticker TEXT PRIMARY KEY,
                last_alert_ts TEXT
              )
            """)
            con.execute("""
              CREATE TABLE IF NOT EXISTS run_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                error_message TEXT,
                tickers TEXT,
                alerts_sent INTEGER DEFAULT 0
              )
            """)

    def get_last_alert_ts(self, ticker: str) -> Optional[str]:
        with sqlite3.connect(self.path) as con:
            row = con.execute(
                "SELECT last_alert_ts FROM alerts WHERE ticker=?",
                (ticker,),
            ).fetchone()
        return row[0] if row else None

    def set_last_alert_ts(self, ticker: str, ts: str) -> None:
        with sqlite3.connect(self.path) as con:
            con.execute(
                "INSERT INTO alerts(ticker,last_alert_ts) VALUES(?,?) "
                "ON CONFLICT(ticker) DO UPDATE SET last_alert_ts=excluded.last_alert_ts",
                (ticker, ts),
            )

    def start_run(self, tickers: list[str]) -> int:
        started_at = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.path) as con:
            cur = con.execute(
                "INSERT INTO run_history(started_at,status,tickers) VALUES(?,?,?)",
                (started_at, "RUNNING", ",".join(tickers)),
            )
            return int(cur.lastrowid)

    def finish_run(self, run_id: int, status: str, alerts_sent: int = 0, error_message: str | None = None) -> None:
        finished_at = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.path) as con:
            con.execute(
                "UPDATE run_history SET finished_at=?, status=?, alerts_sent=?, error_message=? WHERE id=?",
                (finished_at, status, alerts_sent, error_message, run_id),
            )

    def get_latest_run(self) -> dict | None:
        with sqlite3.connect(self.path) as con:
            row = con.execute(
                "SELECT id, started_at, finished_at, status, error_message, tickers, alerts_sent "
                "FROM run_history ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "started_at": row[1],
            "finished_at": row[2],
            "status": row[3],
            "error_message": row[4],
            "tickers": row[5],
            "alerts_sent": row[6],
        }