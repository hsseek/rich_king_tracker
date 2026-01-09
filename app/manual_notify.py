import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Important: Import the new reusable functions from main
from app.main import process_ticker, format_signal_message
from app.notify.telegram import send_telegram

# Setup basic logging for the manual script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

def main():
    # --- Setup ---
    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(dotenv_path=env_path)

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        log.error("TELEGRAM_BOT_TOKEN environment variable not set. Please check your .env file.")
        raise ValueError("TELEGRAM_BOT_TOKEN not set")
        
    personal_chat_id = os.environ.get("TELEGRAM_PERSONAL_CHAT_ID")
    if not personal_chat_id:
        log.error("TELEGRAM_PERSONAL_CHAT_ID environment variable not set. Please add it to your .env file.")
        raise ValueError("TELEGRAM_PERSONAL_CHAT_ID not set")
    
    tickers_str = os.environ.get("TICKERS")
    if not tickers_str:
        log.error("TICKERS environment variable not set. Please add it to your .env file.")
        raise ValueError("TICKERS not set")
    tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()]

    log.info(f"Starting manual snapshot for tickers: {tickers} to chat ID: {personal_chat_id}")

    # --- Configuration ---
    exec_interval = os.environ.get("EXEC_INTERVAL", "30m")
    regime_interval = os.environ.get("REGIME_INTERVAL", "1h")
    exec_confirm_bars = int(os.environ.get("EXEC_CONFIRM_BARS", "3"))
    lookback_days_regime = int(os.environ.get("LOOKBACK_DAYS_REGIME", "30"))
    lookback_days_exec = int(os.environ.get("LOOKBACK_DAYS_EXEC", "20"))

    # --- Main Loop ---
    for ticker in tickers:
        snapshot = process_ticker(
            ticker, regime_interval, exec_interval, lookback_days_regime, lookback_days_exec, exec_confirm_bars
        )

        if not snapshot:
            error_msg = f"[{ticker}] Failed to generate manual snapshot. Check logs for details."
            send_telegram(token, personal_chat_id, error_msg)
            continue
            
        # Format the message using the centralized function
        # Pass `is_manual_snapshot=True` to get the snapshot-specific title and status
        msg = format_signal_message(snapshot, exec_confirm_bars, exec_interval, is_manual_snapshot=True)

        send_telegram(token, personal_chat_id, msg)

if __name__ == "__main__":
    main()