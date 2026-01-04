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
            con.execute("""
              CREATE TABLE IF NOT EXISTS health_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_signature TEXT,
                last_sent_at TEXT,
                last_ok_date_seoul TEXT
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

    def get_health_state(self) -> dict:
        with sqlite3.connect(self.path) as con:
            row = con.execute(
                "SELECT last_signature, last_sent_at, last_ok_date_seoul "
                "FROM health_state WHERE id=1"
            ).fetchone()

        if not row:
            return {"last_signature": None, "last_sent_at": None, "last_ok_date_seoul": None}

        return {"last_signature": row[0], "last_sent_at": row[1], "last_ok_date_seoul": row[2]}

    def update_health_state(
        self,
        last_signature: Optional[str],
        last_sent_at: Optional[str],
        last_ok_date_seoul: Optional[str],
    ) -> None:
        with sqlite3.connect(self.path) as con:
            con.execute(
                "INSERT INTO health_state(id, last_signature, last_sent_at, last_ok_date_seoul) "
                "VALUES(1, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "last_signature=excluded.last_signature, "
                "last_sent_at=excluded.last_sent_at, "
                "last_ok_date_seoul=excluded.last_ok_date_seoul",
                (last_signature, last_sent_at, last_ok_date_seoul),
            )
