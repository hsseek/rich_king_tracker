import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

from app.logging_config import setup_logging
from app.store.sqlite_store import SqliteStore
from app.notify.telegram import send_telegram

log = logging.getLogger("health")

def minutes_since(iso_ts: str) -> int:
    # iso_ts is stored as datetime.now(timezone.utc).isoformat()
    dt = datetime.fromisoformat(iso_ts)
    now = datetime.now(timezone.utc)
    return int((now - dt).total_seconds() // 60)

def main():
    project_root = Path(__file__).resolve().parents[1]
    env_path = Path(__file__).resolve().parent / ".env"

    load_dotenv(dotenv_path=env_path)

    setup_logging(
        log_dir=os.environ.get("LOG_DIR", str(project_root / "logs")),
        log_file=os.environ.get("HEALTH_LOG_FILE", "health.log"),
        level=logging.INFO,
    )

    try:
        token = os.environ["TELEGRAM_BOT_TOKEN"]
        chat_id = os.environ["TELEGRAM_CHAT_ID"]
    except KeyError as e:
        log.exception("Missing env var: %s", e)
        raise

    db_path = os.environ.get("ALERT_DB", str(project_root / "alerts.db"))
    stale_minutes = int(os.environ.get("HEALTH_STALE_MINUTES", "70"))

    log.info("Health check started | db_path=%s", db_path)

    store = SqliteStore(path=db_path)
    last = store.get_latest_run()

    if not last:
        msg = "[Health] No runs recorded yet."
        send_telegram(token, chat_id, msg)
        log.info("Sent: %s", msg)
        return

    status = last["status"]
    started_at = last["started_at"]
    finished_at = last["finished_at"]
    tickers = last["tickers"] or ""
    alerts_sent = last["alerts_sent"] or 0
    err = last["error_message"]

    anchor_ts = finished_at or started_at
    age_min = minutes_since(anchor_ts)
    stale_flag = "STALE" if age_min > stale_minutes else "OK"

    lines = [
        f"[Health] {stale_flag}",
        f"- last_status: {status}",
        f"- tickers: {tickers}",
        f"- started_at(UTC): {started_at}",
        f"- finished_at(UTC): {finished_at}",
        f"- age_minutes: {age_min}",
        f"- alerts_sent(last_run): {alerts_sent}",
    ]
    if status == "ERROR" and err:
        lines.append(f"- last_error: {err[:500]}")

    msg = "\n".join(lines)
    send_telegram(token, chat_id, msg)
    log.info("Health report sent successfully")

if __name__ == "__main__":
    main()
