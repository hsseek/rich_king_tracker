import os
import logging
from pathlib import Path
from dotenv import load_dotenv

from app.logging_config import setup_logging
from app.data_providers.yahoo_yfinance import fetch_ohlc
from app.strategy.ema_regime import (
    compute_indicators,
    drop_incomplete_last_bar,
    compute_regime_1h,
    detect_exec_15m_signal,
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

    store = SqliteStore(path=os.environ.get("ALERT_DB", "alerts.db"))

    run_id = store.start_run(tickers)
    alerts_sent = 0

    try:
        exec_interval = os.environ.get("EXEC_INTERVAL", "15m")
        regime_interval = os.environ.get("REGIME_INTERVAL", "1h")
        exec_confirm_bars = int(os.environ.get("EXEC_CONFIRM_BARS", "2"))

        lookback_days_15m = int(os.environ.get("LOOKBACK_DAYS_15M", "10"))
        lookback_days_1h = int(os.environ.get("LOOKBACK_DAYS_1H", "30"))

        log.info(
            "Monitor started | tickers=%s | regime_tf=%s | exec_tf=%s | confirm_bars=%d",
            tickers, regime_interval, exec_interval, exec_confirm_bars
        )

        for ticker in tickers:
            log.info("[%s] Fetching data | 1h=%dd | 15m=%dd", ticker, lookback_days_1h, lookback_days_15m)

            df_1h = fetch_ohlc(ticker, interval=regime_interval, lookback_days=lookback_days_1h)
            df_15m = fetch_ohlc(ticker, interval=exec_interval, lookback_days=lookback_days_15m)

            df_1h = drop_incomplete_last_bar(df_1h, regime_interval)
            df_15m = drop_incomplete_last_bar(df_15m, exec_interval)

            if df_1h.empty or df_15m.empty:
                log.warning("[%s] No data returned after dropping incomplete bars", ticker)
                continue

            # Dedupe on last closed 15m bar (highest frequency)
            last_exec_ts = str(df_15m.index[-1])
            if store.get_last_alert_ts(ticker) == last_exec_ts:
                log.info("[%s] Already processed this 15m bar | ts=%s", ticker, last_exec_ts)
                continue

            # 1h regime (R1)
            regime = compute_regime_1h(df_1h)

            ind_1h = compute_indicators(df_1h)
            ind_15m = compute_indicators(df_15m)

            last_1h = ind_1h.iloc[-1]
            last_15m = ind_15m.iloc[-1]

            # Log (grouped, plain words, most important first)
            log.info(
                "[%s] Multi-timeframe snapshot\n"
                "  Regime (1h): %s | EMA(9)=%.2f EMA(21)=%.2f slope(EMA21)=%.5f | last_closed=%s\n"
                "  Execution (15m): EMA(3)=%.2f vs EMA(9)=%.2f | last_closed=%s\n"
                "  Price (15m close): %.2f",
                ticker,
                regime,
                last_1h["EMA9"],
                last_1h["EMA21"],
                last_1h["EMA21_slope"],
                last_1h.name,
                last_15m["EMA3"],
                last_15m["EMA9"],
                last_15m.name,
                last_15m["Close"],
            )

            exec_signal = detect_exec_15m_signal(df_15m, confirm_bars=exec_confirm_bars)

            # Policy (P1) + Exit rule (X1)
            # BUY: only when 1h regime is UP and 15m signal is BUY
            if regime == "UP" and exec_signal == "BUY":
                msg = (
                    f"[{ticker}] BUY signal (MTF)\n"
                    f"- Regime(1h): UP (EMA9>EMA21 & slope>0)\n"
                    f"- Execution(15m): EMA3>EMA9 persisted {exec_confirm_bars} bars\n"
                    f"- 1h_ts: {last_1h.name}\n"
                    f"- 15m_ts: {last_15m.name}\n"
                    f"- 15m_close: {last_15m['Close']:.2f}"
                )
                send_telegram(token, chat_id, msg)
                alerts_sent += 1
                log.info("[%s] BUY signal sent", ticker)

            # SELL (X1): 15m bearish persists AND 1h regime is no longer UP
            if regime != "UP" and exec_signal == "SELL":
                msg = (
                    f"[{ticker}] SELL signal (MTF)\n"
                    f"- Regime(1h): {regime} (not UP)\n"
                    f"- Execution(15m): EMA3<EMA9 persisted {exec_confirm_bars} bars\n"
                    f"- 1h_ts: {last_1h.name}\n"
                    f"- 15m_ts: {last_15m.name}\n"
                    f"- 15m_close: {last_15m['Close']:.2f}"
                )
                send_telegram(token, chat_id, msg)
                alerts_sent += 1
                log.info("[%s] SELL signal sent", ticker)

            if exec_signal is None:
                log.info("[%s] No execution signal on 15m (persist=%d)", ticker, exec_confirm_bars)
            else:
                log.info("[%s] Execution signal=%s (regime=%s)", ticker, exec_signal, regime)

            store.set_last_alert_ts(ticker, last_exec_ts)

    except Exception as e:
        store.finish_run(run_id, status="ERROR", alerts_sent=alerts_sent, error_message=str(e))
        log.exception("Monitor finished | ERROR")
        raise


if __name__ == "__main__":
    main()
