# RichKingTracker

Python-based intraday (1-hour candle) monitor for ETFs/stocks (default: QQQ).  
It fetches hourly OHLCV data, computes common technical indicators, detects short-term momentum conditions with a persistence rule, and sends Telegram notifications. The project also supports hourly health reports via Telegram and writes structured logs to file.

## Features
- Hourly OHLCV fetch (Yahoo Finance via `yfinance`)
- Indicators:
  - EMA(3), EMA(9), EMA(21)
  - RSI(5)
  - ATR(5)
  - Derived values: EMA gap, EMA(21) slope, RSI delta
- Signals:
  - **ShortMomentumUp (2h persistence)**: fast momentum condition, confirmed only if it persists for 2 consecutive closed hourly candles
  - Optional legacy signal: downtrend → uptrend regime switch (EMA9/EMA21 + slope)
- Notifications:
  - Telegram alerts for signals
  - Hourly Telegram health report (last run time, status, last error, etc.)
- Logging:
  - Console + rotating file log
  - Readable multi-line grouped log for each processed candle
- Designed to scale to multiple tickers via `TICKERS=QQQ,SPY,...`

## Quick Start

### 1) Create a virtual environment and install dependencies
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
````

### 2) Configure environment variables

Create `app/.env`:

```env
# Required (Telegram)
TELEGRAM_BOT_TOKEN=xxxx
TELEGRAM_CHAT_ID=yyyy

# Optional
TICKERS=QQQ
ALERT_DB=/home/<user>/PythonProjects/RichKingTracker/alerts.db
LOG_DIR=/home/<user>/PythonProjects/RichKingTracker/logs
LOG_FILE=monitor.log

# Short-momentum distance filter
GAP_ATR_K=0.15

# Health report
HEALTH_STALE_MINUTES=70
HEALTH_LOG_FILE=health.log
```

### 3) Run the monitor

```bash
python -m app.main
```

### 4) Run the health report

```bash
python -m app.health_report
```

## Scheduling (cron example)

These cron rules schedule jobs in US Eastern time (DST-safe) using `CRON_TZ`.
Important: `CRON_TZ` applies to all lines below it until you set it again.

Monitor (every 10 minutes during US pre-market, regular hours, and after-hours; Mon–Fri):

```bash
# ---------- RichKingTracker (US market sessions) ----------
CRON_TZ=America/New_York

# Pre-market: 04:00–09:20 ET, every 10 minutes (Mon–Fri)
*/10 4-8 * * 1-5  cd /home/sun/PythonProjects/RichKingTracker && /home/sun/PythonProjects/RichKingTracker/.venv/bin/python -m app.main >> logs/cron_monitor.out 2>&1
0,10,20 9 * * 1-5  cd /home/sun/PythonProjects/RichKingTracker && /home/sun/PythonProjects/RichKingTracker/.venv/bin/python -m app.main >> logs/cron_monitor.out 2>&1

# Core session: 09:30–15:50 ET, every 10 minutes (Mon–Fri)
30-59/10 9  * * 1-5  cd /home/sun/PythonProjects/RichKingTracker && /home/sun/PythonProjects/RichKingTracker/.venv/bin/python -m app.main >> logs/cron_monitor.out 2>&1
*/10      10-15 * * 1-5  cd /home/sun/PythonProjects/RichKingTracker && /home/sun/PythonProjects/RichKingTracker/.venv/bin/python -m app.main >> logs/cron_monitor.out 2>&1

# Immediate post-close: 16:00–16:20 ET (Mon–Fri)
0,10,20 16 * * 1-5  cd /home/sun/PythonProjects/RichKingTracker && /home/sun/PythonProjects/RichKingTracker/.venv/bin/python -m app.main >> logs/cron_monitor.out 2>&1

# After-hours: 16:30–19:50 ET, every 10 minutes (Mon–Fri)
30-59/10 16 * * 1-5  cd /home/sun/PythonProjects/RichKingTracker && /home/sun/PythonProjects/RichKingTracker/.venv/bin/python -m app.main >> logs/cron_monitor.out 2>&1
*/10      17-19 * * 1-5  cd /home/sun/PythonProjects/RichKingTracker && /home/sun/PythonProjects/RichKingTracker/.venv/bin/python -m app.main >> logs/cron_monitor.out 2>&1

# HEALTH: every 30 minutes during 04:00–19:30 ET (Mon–Fri)
*/30 4-19 * * 1-5  cd /home/sun/PythonProjects/RichKingTracker && /home/sun/PythonProjects/RichKingTracker/.venv/bin/python -m app.health_report >> logs/cron_health.out 2>&1

# HEALTH: daily heartbeat (08:05 ET every day)
5 8 * * *  cd /home/sun/PythonProjects/RichKingTracker && /home/sun/PythonProjects/RichKingTracker/.venv/bin/python -m app.health_report >> logs/cron_health.out 2>&1

# If needed for other jobs:
# CRON_TZ=Asia/Seoul
```

## Data model (1-hour candle)

Each hourly candle includes OHLC:

* **open**: first traded price during the hour
* **high**: highest traded price during the hour
* **low**: lowest traded price during the hour
* **close**: last traded price at the end of the hour

All indicators are computed from these candles.

## Indicators and definitions

### EMA (Exponential Moving Average)

EMA is computed on the **Close** price and weights recent data more heavily.

For period `N`, the smoothing factor is:

* `α = 2 / (N + 1)`

Recursive formula:

* `EMA_t = α * Close_t + (1 - α) * EMA_(t-1)`

We compute:

* **EMA(3)**: very short-term responsiveness (fast momentum)
* **EMA(9)**: short-term baseline
* **EMA(21)**: medium-term baseline

### RSI (Relative Strength Index), RSI(5)

RSI measures the relative magnitude of recent gains vs losses over `N` periods, scaled 0–100.

We use Wilder-style smoothing (EMA-style) on gains and losses:

* `delta_t = Close_t - Close_(t-1)`
* `gain_t = max(delta_t, 0)`
* `loss_t = max(-delta_t, 0)`
* `avg_gain_t = WilderEMA(gain, N)`
* `avg_loss_t = WilderEMA(loss, N)`
* `RS_t = avg_gain_t / avg_loss_t`
* `RSI_t = 100 - (100 / (1 + RS_t))`

Interpretation (common rule of thumb):

* RSI > 50 suggests bullish short-term momentum
* RSI < 50 suggests bearish short-term momentum

### ATR (Average True Range), ATR(5)

ATR measures volatility. It is computed from True Range (TR):

`TR_t = max(
  High_t - Low_t,
  abs(High_t - Close_(t-1)),
  abs(Low_t  - Close_(t-1))
)`

ATR(5) is the rolling average of TR over the last 5 hourly candles.

Interpretation:

* Larger ATR means higher volatility (bigger typical price movement per hour)

### Derived values

* **RSI delta**: `RSI5_delta_t = RSI5_t - RSI5_(t-1)`

  * Used to ensure RSI is rising (momentum acceleration)
* **EMA gap**: `GAP_3_9_t = EMA3_t - EMA9_t`

  * Positive means very short-term momentum exceeds short-term baseline
* **EMA(21) slope**: `EMA21_slope_t = EMA21_t - EMA21_(t-1)`

  * Positive slope suggests medium-term trend rising; negative suggests falling

## Signal logic

### ShortMomentumUp (2-hour persistence)

A candle satisfies `ShortMomentumUp` if:

* EMA(3) > EMA(9)
* RSI(5) > 50
* RSI(5) is rising (RSI5_delta > 0)
* EMA gap exceeds a volatility-normalized threshold:

  * `GAP_3_9 > k * ATR(5)`
  * `k` is configurable via `GAP_ATR_K` (default 0.15)

An alert triggers only if the condition holds for **two consecutive closed 1-hour candles**.

### Health reporting

The monitor writes run records into SQLite (`run_history`), including:

* start/finish timestamps (UTC)
* OK/ERROR status
* last error message (if any)
* alert count

The health report reads the latest record and sends a status summary via Telegram.

## Notes / Caveats

* Hourly timestamps from Yahoo may align on `:30` rather than `:00` depending on the data source behavior.
* Weekends/holidays produce no new candles; the monitor will repeatedly see the last available candle and skip reprocessing via SQLite dedupe.
* This project is for monitoring and notification only (not an automated trading system).