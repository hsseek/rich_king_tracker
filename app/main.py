import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
from typing import TypedDict, Optional

from app.logging_config import setup_logging
from app.data_providers.yahoo_yfinance import fetch_ohlc
from app.strategy.ema_regime import (
    compute_indicators,
    drop_incomplete_last_bar,
    compute_regime_1h,
    detect_exec_signal,
)
from app.notify.telegram import send_telegram
from app.store.sqlite_store import SqliteStore

log = logging.getLogger("monitor")


class TickerSnapshot(TypedDict):
    """A dictionary holding all computed data for a ticker at a point in time."""
    ticker: str
    regime: str
    exec_signal: Optional[str]
    last_1h: dict
    last_exec: dict
    last_exec_ts: str  # Added for deduplication
    emi: float
    ts_1h_str: str
    ts_exec_str: str


def process_ticker(
    ticker: str,
    regime_interval: str,
    exec_interval: str,
    lookback_days_regime: int,
    lookback_days_exec: int,
    exec_confirm_bars: int,
) -> Optional[TickerSnapshot]:
    """
    Fetches data, computes indicators, and returns a snapshot for a single ticker.
    Returns None if data fetching or processing fails.
    """
    log.info(f"[{ticker}] Fetching data | {regime_interval}={lookback_days_regime}d | {exec_interval}={lookback_days_exec}d")
    try:
        df_1h = fetch_ohlc(ticker, interval=regime_interval, lookback_days=lookback_days_regime)
        df_exec = fetch_ohlc(ticker, interval=exec_interval, lookback_days=lookback_days_exec)

        df_1h = drop_incomplete_last_bar(df_1h, regime_interval)
        df_exec = drop_incomplete_last_bar(df_exec, exec_interval)

        if df_1h.empty or df_exec.empty:
            log.warning(f"[{ticker}] No data returned after dropping incomplete bars")
            return None

        # --- Calculations ---
        regime = compute_regime_1h(df_1h)
        ind_1h = compute_indicators(df_1h)
        ind_exec = compute_indicators(df_exec)

        last_1h = ind_1h.iloc[-1]
        last_exec = ind_exec.iloc[-1]

        exec_signal = detect_exec_signal(df_exec, confirm_bars=exec_confirm_bars)

        # --- Formatting &Derived Metrics---
        ET = ZoneInfo("America/New_York")
        ts_1h_str = last_1h.name.astimezone(ET).strftime('%Y-%m-%d %H:%M ET')
        ts_exec_str = last_exec.name.astimezone(ET).strftime('%Y-%m-%d %H:%M ET')
        emi = ((last_exec['EMA3'] - last_exec['EMA9']) / last_exec['Close']) * 1000

        return TickerSnapshot(
            ticker=ticker,
            regime=regime,
            exec_signal=exec_signal,
            last_1h=last_1h.to_dict(),
            last_exec=last_exec.to_dict(),
            last_exec_ts=str(last_exec.name),
            emi=emi,
            ts_1h_str=ts_1h_str,
            ts_exec_str=ts_exec_str,
        )
    except Exception as e:
        log.error(f"[{ticker}] Failed to process ticker: {e}", exc_info=True)
        return None


def format_signal_message(snapshot: TickerSnapshot, exec_confirm_bars: int, exec_interval: str, is_manual_snapshot: bool = False) -> str:
    """Formats a message string from a TickerSnapshot."""
    ticker = snapshot['ticker']
    regime = snapshot['regime']
    exec_signal = snapshot['exec_signal']

    # Determine title and status context
    if is_manual_snapshot:
        title = f"[{ticker}] Manual Snapshot"
        if regime == "UP" and exec_signal == "BUY":
            status = f"Potential BUY signal active ({exec_confirm_bars} bars)"
        elif regime != "UP" and exec_signal == "SELL":
            status = f"Potential SELL signal active ({exec_confirm_bars} bars)"
        else:
            status = "No signal active"
    elif exec_signal:
        title = f"[{ticker}] {exec_signal} signal (MTF)"
        status = f"Execution: EMA3 {'<' if exec_signal == 'SELL' else '>'} EMA9 (persisted {exec_confirm_bars} bars)"
    else:
        # Should not happen in main flow, but good for safety
        return f"[{ticker}] No active signal."

    # Common message body
    body = (
        f"Strength (EMI): {snapshot['emi']:.2f}\n"
        f"Conviction (RVI): {snapshot['last_exec']['RVI']:.2f}\n"
        f"Regime(1h): {regime} (EMA9={snapshot['last_1h']['EMA9']:.2f}, EMA21={snapshot['last_1h']['EMA21']:.2f}, Slope={snapshot['last_1h']['EMA21_slope']:.4f})\n"
        f"Execution({exec_interval}): EMA3={snapshot['last_exec']['EMA3']:.2f}, EMA9={snapshot['last_exec']['EMA9']:.2f}\n"
        f"Timestamps:\n"
        f"    - 1h: {snapshot['ts_1h_str']}\n"
        f"    - {exec_interval}: {snapshot['ts_exec_str']}\n"
        f"Price({exec_interval}_close): {snapshot['last_exec']['Close']:.2f}"
    )

    if is_manual_snapshot:
        return f"{title}\nStatus: {status}\n{body}"
    else:
        return f"{title}\n{body}"

def main():
    # --- Setup ---
    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(dotenv_path=env_path)

    setup_logging(
        log_dir=os.environ.get("LOG_DIR", "logs"),
        log_file=os.environ.get("LOG_FILE", "monitor.log"),
        level=logging.INFO,
    )

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        log.error("TELEGRAM_BOT_TOKEN not set")
        raise ValueError("TELEGRAM_BOT_TOKEN not set")
        
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not chat_id:
        log.error("TELEGRAM_CHAT_ID not set")
        raise ValueError("TELEGRAM_CHAT_ID not set")
    
    tickers_str = os.environ.get("TICKERS")
    if not tickers_str:
        log.error("TICKERS not set")
        raise ValueError("TICKERS environment variable not set. Please add it to your .env file.")
    tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()]
    
    store = SqliteStore(path=os.environ.get("ALERT_DB", "alerts.db"))

    # --- Configuration ---
    exec_interval = os.environ.get("EXEC_INTERVAL", "30m")
    regime_interval = os.environ.get("REGIME_INTERVAL", "1h")
    exec_confirm_bars = int(os.environ.get("EXEC_CONFIRM_BARS", "3"))
    lookback_days_regime = int(os.environ.get("LOOKBACK_DAYS_REGIME", "30"))
    lookback_days_exec = int(os.environ.get("LOOKBACK_DAYS_EXEC", "20"))

    log.info(f"Monitor started with configuration:")
    log.info(f"  Tickers: {', '.join(tickers)}")
    log.info(f"  Regime Timeframe: {regime_interval} (Lookback: {lookback_days_regime} days)")
    log.info(f"  Execution Timeframe: {exec_interval} (Lookback: {lookback_days_exec} days)")
    log.info(f"  Execution Confirmation Bars: {exec_confirm_bars}")

    run_id = store.start_run(tickers)
    alerts_sent = 0
    # --- Main Loop ---
    try:
        for ticker in tickers:
            snapshot = process_ticker(
                ticker, regime_interval, exec_interval, lookback_days_regime, lookback_days_exec, exec_confirm_bars
            )

            if not snapshot:
                continue

            # Dedupe on last closed execution bar (highest frequency)
            last_exec_ts = snapshot['last_exec_ts']
            if store.get_last_alert_ts(ticker) == last_exec_ts:
                log.info(f"[{ticker}] Already processed this {exec_interval} bar | ts={last_exec_ts}")
                continue

            # Log snapshot
            log.info(
                f"[{ticker}] Multi-timeframe snapshot\n"
                f"  Regime ({regime_interval}): {snapshot['regime']} | EMA(9)={snapshot['last_1h']['EMA9']:.2f} EMA(21)={snapshot['last_1h']['EMA21']:.2f} slope(EMA21)={snapshot['last_1h']['EMA21_slope']:.5f} | last_closed={snapshot['ts_1h_str']}\n"
                f"  Execution ({exec_interval}): EMA(3)={snapshot['last_exec']['EMA3']:.2f} vs EMA(9)={snapshot['last_exec']['EMA9']:.2f} | last_closed={snapshot['ts_exec_str']}\n"
                f"  Price ({exec_interval} close): {snapshot['last_exec']['Close']:.2f}"
            )
            
            # --- Signal Logic & Notification ---
            regime = snapshot['regime']
            exec_signal = snapshot['exec_signal']

            should_send = (regime == "UP" and exec_signal == "BUY") or \
                          (regime != "UP" and exec_signal == "SELL")

            if should_send:
                msg = format_signal_message(snapshot, exec_confirm_bars, exec_interval)
                send_telegram(token, chat_id, msg)
                alerts_sent += 1
                log.info(f"[{ticker}] {exec_signal} signal sent")

            log.info(f"[{ticker}] Execution signal={exec_signal} (regime={regime})")
            store.set_last_alert_ts(ticker, last_exec_ts)

    except Exception as e:
        store.finish_run(run_id, status="ERROR", alerts_sent=alerts_sent, error_message=str(e))
        log.exception("Monitor finished | ERROR")
        raise
    else:
        store.finish_run(run_id, status="OK", alerts_sent=alerts_sent)


if __name__ == "__main__":
    main()