import os
import logging
from pathlib import Path
from dotenv import load_dotenv

from app.logging_config import setup_logging
from app.data_providers.yahoo_yfinance import fetch_hourly
from app.strategy.ema_regime import (
    detect_confirmed_switch,
    detect_short_momentum_up_2h,
    compute_indicators,
)
from app.notify.telegram import send_telegram
from app.store.sqlite_store import SqliteStore

log = logging.getLogger("monitor")


def main():
    # Cron-safe env loading (your current approach)
    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(dotenv_path=env_path)

    setup_logging(
        log_dir=os.environ.get("LOG_DIR", "logs"),
        log_file=os.environ.get("LOG_FILE", "monitor.log"),
        level=logging.INFO,
    )

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    tickers = os.environ.get("TICKERS", "QQQ").split(",")
    tickers = [t.strip().upper() for t in tickers if t.strip()]

    # Distance filter parameter (ATR-multiple)
    gap_atr_k = float(os.environ.get("GAP_ATR_K", "0.15"))

    store = SqliteStore(path=os.environ.get("ALERT_DB", "alerts.db"))

    run_id = store.start_run(tickers)
    alerts_sent = 0

    try:
        log.info("Monitor started | tickers=%s | GAP_ATR_K=%.3f", tickers, gap_atr_k)

        for ticker in tickers:
            log.info("[%s] Fetching hourly data", ticker)

            df = fetch_hourly(ticker, lookback_days=10)
            if df.empty:
                log.warning("[%s] No data returned", ticker)
                continue

            ind = compute_indicators(df)
            last = ind.iloc[-1]
            prev = ind.iloc[-2]

            rsi5_tag = "RSI5"
            rsi5 = float(last[rsi5_tag])
            rsi5_prev = prev[rsi5_tag]
            rsi5_delta = last[rsi5_tag] - rsi5_prev

            # Diagnostics: log price + indicators + distance filter terms
            gap = float(last["GAP_3_9"])
            atr5 = float(last["ATR5"]) if not (last["ATR5"] != last["ATR5"]) else float("nan")  # NaN-safe
            thr = gap_atr_k * atr5 if atr5 == atr5 else float("nan")

            log.info(
                "[%s] Last closed 1-hour candle @ %s\n"
                "  Momentum (short-term): EMA(3)=%.2f vs EMA(9)=%.2f (gap=%.4f, threshold=k*ATR=%.4f, k=%.3f) | RSI(5)=%.2f (delta=%.2f)\n"
                "  Volatility: ATR(5)=%.4f\n"
                "  Trend (medium-term): EMA(21)=%.2f (slope per hour=%.5f)\n"
                "  Price (OHLC): open=%.2f high=%.2f low=%.2f close=%.2f",
                ticker,
                last.name,
                last["EMA3"],
                last["EMA9"],
                gap,
                thr,
                gap_atr_k,
                rsi5,
                rsi5_delta,
                atr5,
                last["EMA21"],
                last["EMA21_slope"],
                last["Open"],
                last["High"],
                last["Low"],
                last["Close"],
            )

            last_bar_ts = str(last.name)
            if store.get_last_alert_ts(ticker) == last_bar_ts:
                log.info("[%s] Already processed this bar", ticker)
                continue

            # (A) New: short momentum alert (2h persistence + distance filter)
            if detect_short_momentum_up_2h(df, k=gap_atr_k):
                msg = (
                    f"[{ticker}] ShortMomentumUp confirmed (2h)\n"
                    f"- ts: {last_bar_ts}\n"
                    f"- C: {last['Close']:.2f}\n"
                    f"- EMA3-EMA9: {gap:.4f} > {thr:.4f} (k={gap_atr_k:.3f}, ATR5={atr5:.4f})\n"
                    f"- RSI5: {last['RSI5']:.2f} (rising)"
                )
                send_telegram(token, chat_id, msg)
                alerts_sent += 1
                log.info("[%s] SHORT MOMENTUM ALERT SENT", ticker)

            # (B) Existing: downtrend -> uptrend (EMA9/EMA21) confirmed
            if detect_confirmed_switch(df):
                msg = f"[{ticker}] Downtrend → Uptrend confirmed (2h) at {last_bar_ts}"
                send_telegram(token, chat_id, msg)
                alerts_sent += 1
                log.info("[%s] TREND SWITCH ALERT SENT", ticker)
            else:
                log.info("[%s] No trend-switch signal", ticker)

            store.set_last_alert_ts(ticker, last_bar_ts)

        store.finish_run(run_id, status="OK", alerts_sent=alerts_sent)
        log.info("Monitor finished | OK | alerts_sent=%d", alerts_sent)

    except Exception as e:
        store.finish_run(run_id, status="ERROR", alerts_sent=alerts_sent, error_message=str(e))
        log.exception("Monitor finished | ERROR")
        raise


if __name__ == "__main__":
    main()
