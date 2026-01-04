import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

from app.logging_config import setup_logging
from app.store.sqlite_store import SqliteStore
from app.notify.telegram import send_telegram

log = logging.getLogger("health")
SEOUL_TZ = ZoneInfo("Asia/Seoul")


def minutes_since(iso_ts: str) -> int:
    dt = datetime.fromisoformat(iso_ts)
    now = datetime.now(timezone.utc)
    return int((now - dt).total_seconds() // 60)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def seoul_today_str() -> str:
    return datetime.now(SEOUL_TZ).date().isoformat()


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

    # Optional: send one OK heartbeat per Seoul day
    daily_ok_enabled = os.environ.get("HEALTH_DAILY_OK", "1") == "1"

    log.info("Health check started | db_path=%s", db_path)

    store = SqliteStore(path=db_path)
    last = store.get_latest_run()
    hs = store.get_health_state()

    # --- case: no runs yet ---
    if not last:
        signature = "NO_RUNS"
        if hs["last_signature"] != signature:
            msg = "[Health] No runs recorded yet."
            send_telegram(token, chat_id, msg)
            store.update_health_state(signature, utc_now_iso(), hs["last_ok_date_seoul"])
            log.info("Health report sent (NO_RUNS).")
        else:
            log.info("Health report suppressed (NO_RUNS unchanged).")
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

    # Signature: changes when a new run completes, state flips, tickers change, etc.
    signature = f"{stale_flag}|{status}|{tickers}|{anchor_ts}|alerts={alerts_sent}"

    must_send = False
    reasons: list[str] = []

    # 1) Always send on ERROR
    if status == "ERROR":
        must_send = True
        reasons.append("status=ERROR")

    # 2) Always send on STALE
    if stale_flag == "STALE":
        must_send = True
        reasons.append("state=STALE")

    # 3) Send when signature changed (i.e., meaningful update)
    if hs["last_signature"] != signature:
        must_send = True
        reasons.append("signature_changed")

    # 4) Optional: once-per-day OK heartbeat (Seoul date)
    today_seoul = seoul_today_str()
    if daily_ok_enabled and stale_flag == "OK" and status == "OK":
        if hs["last_ok_date_seoul"] != today_seoul:
            must_send = True
            reasons.append("daily_ok_heartbeat")

    if not must_send:
        log.info("Health report suppressed (no change). signature=%s", signature)
        return

    lines = [
        f"[Health] {stale_flag} ({', '.join(reasons)})",
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

    # update SQLite health state after successful send
    last_ok_date_seoul = hs["last_ok_date_seoul"]
    if daily_ok_enabled and stale_flag == "OK" and status == "OK":
        last_ok_date_seoul = today_seoul

    store.update_health_state(signature, utc_now_iso(), last_ok_date_seoul)
    log.info("Health report sent successfully. signature=%s", signature)


if __name__ == "__main__":
    main()
