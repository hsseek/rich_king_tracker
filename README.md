# RichKingTracker
## Overview
This project monitors U.S. stocks/ETFs and sends **BUY / SELL signals** based on a **multi-timeframe regime model**.
The design philosophy is:
> **Use a slower timeframe to define the market regime, and a faster timeframe to time entries and exits.**

This avoids overreacting to noise while still responding quickly to real trend changes.

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

# Timeframe
REGIME_INTERVAL=1h
EXEC_INTERVAL=15m
EXEC_CONFIRM_BARS=2

LOOKBACK_DAYS_1H=30
LOOKBACK_DAYS_15M=10

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

## Timeframes used

| Purpose              | Timeframe             | Why                                         |
| -------------------- | --------------------- | ------------------------------------------- |
| **Market regime**    | **1-hour candles**    | Stable enough to define trend direction     |
| **Execution signal** | **15-minute candles** | Responsive enough for earlier entries/exits |

```
                    ┌──────────────────────────┐
                    │   1-hour candles (1h)    │
                    │                          │
                    │  EMA(9), EMA(21)         │
                    │  EMA(21) slope           │
                    └─────────────┬────────────┘
                                  │
                                  ▼
                       ┌────────────────────┐
                       │  Regime decision   │
                       │                    │
                       │  UP / DOWN / NEUTRAL
                       └──────────┬─────────┘
                                  │
               ┌──────────────────┴──────────────────────┐
               │                                         │
               ▼                                         ▼
        (Regime = UP)                              (Regime ≠ UP)
      Allow BUY signals                         Allow SELL signals
      Block SELL signals                        Block BUY signals
               │                                         │
               ▼                                         ▼
      ┌───────────────────┐                   ┌───────────────────┐
      │ 15-minute candles │                   │ 15-minute candles │
      │                   │                   │                   │
      │ EMA(3) vs EMA(9)  │                   │ EMA(3) vs EMA(9)  │
      │ persistence (2x)  │                   │ persistence (2x)  │
      └─────────┬─────────┘                   └─────────┬─────────┘
                │                                       │
                ▼                                       ▼
         BUY notification                       SELL notification

```
Note that the faster timeframe never overrides the slower timeframe.

---

## When this model works well / when it fails

This section exists as a reminder to **future me** of the strengths and limits of the current multi-timeframe regime model.
It is intentionally explicit and conservative.

---

### ✅ When this model works well

This model performs best under the following conditions:

#### 1) The stock exhibits real directional movement

* Small- to mid-cap growth stocks
* Strategic or thematic companies (AI, semiconductors, energy transition, defense, etc.)
* Stocks reacting to **earnings, guidance, or macro narratives**

The model assumes that trends exist and can persist for **hours to days**.

---

#### 2) Trends develop over hours to days (not minutes)

* This is **not** a scalping model
* This is **not** a long-term buy-and-hold valuation model
* Best suited for:

  * Early trend participation
  * Swing-style entries and exits

---

#### 3) Liquidity is reasonable

* Clean 15-minute candles
* EMA(3) and EMA(9) reflect consensus price action
* No single trade dominates a candle

Liquidity matters because EMA-based logic assumes aggregated behavior, not isolated prints.

---

### ⚠️ When this model underperforms or fails

This model is **not universal**. It will struggle under these conditions:

#### 1) Strongly range-bound or choppy markets

* EMA(3) and EMA(9) cross frequently
* 1-hour regime may oscillate between NEUTRAL and UP/DOWN
* Expect:

  * More signals
  * Lower signal quality
  * Reduced edge

This is a known and accepted limitation of trend-following logic.

---

#### 2) Very low-liquidity stocks

* EMAs can be distorted by a small number of trades
* Indicators reflect noise rather than consensus
* Signals may appear “technically correct” but economically meaningless

---

#### 3) Single-candle news shocks

* Sudden gaps caused by news may invalidate EMA confirmation logic
* This model **reacts after confirmation**, not instantly
* It is designed to avoid false starts, not to front-run news

---

### Mental checklist before trusting a signal

When a BUY or SELL notification arrives, pause and ask:

1. Is the **1-hour regime** clearly aligned with the signal?
2. Did the **15-minute condition persist**, or is it marginal?
3. Is this a **low-volume session or holiday**?
4. Is this stock historically **trend-clean or whipsaw-prone**?

If (1) or (2) is unclear, treat the signal as **informational**, not actionable.


---

## Indicators and definitions

### EMA (Exponential Moving Average)

EMA is computed on the **Close** price and weights recent data more heavily.

For period `N`:

* `α = 2 / (N + 1)`
* `EMA_t = α * Close_t + (1 - α) * EMA_(t-1)`

We compute:

| EMA         | Meaning                    |
| ----------- | -------------------------- |
| **EMA(3)**  | Very short-term momentum   |
| **EMA(9)**  | Short-term baseline        |
| **EMA(21)** | Medium-term trend baseline |

---

### EMA(21) slope

* `EMA21_slope_t = EMA21_t - EMA21_(t-1)`

Interpretation:

| Slope    | Meaning                   |
| -------- | ------------------------- |
| Positive | Medium-term trend rising  |
| Negative | Medium-term trend falling |

The slope is critical: it prevents treating flat EMA crossings as real trend changes.

---

## Regime definition (1-hour timeframe)

The **1-hour regime** defines the market context.

| Regime      | Condition                                  |
| ----------- | ------------------------------------------ |
| **UP**      | EMA(9) > EMA(21) **and** EMA(21) slope > 0 |
| **DOWN**    | EMA(9) < EMA(21) **and** EMA(21) slope < 0 |
| **NEUTRAL** | Anything else                              |

This regime changes slowly and filters out short-term noise.

---

## Execution signal (15-minute timeframe)

The **execution signal** determines *when* to act.

We use a simple, fast rule:

| Condition       | Meaning                     |
| --------------- | --------------------------- |
| EMA(3) > EMA(9) | Short-term bullish momentum |
| EMA(3) < EMA(9) | Short-term bearish momentum |

To avoid reacting to a single noisy candle, the condition must hold for:

* **`EXEC_CONFIRM_BARS = 2` consecutive closed 15-minute candles**

---

## BUY / SELL decision logic

### BUY signal

A **BUY** notification is sent when **both** are true:

1. **1-hour regime is UP**
2. **15-minute execution signal is bullish**, confirmed for 2 bars
   (`EMA(3) > EMA(9)` persists)

Interpretation:

> “The broader trend is up, and short-term momentum has aligned with it.”

---

### SELL signal (exit logic)

A **SELL** notification is sent when **both** are true:

1. **1-hour regime is no longer UP** (DOWN or NEUTRAL)
2. **15-minute execution signal is bearish**, confirmed for 2 bars
   (`EMA(3) < EMA(9)` persists)

Interpretation:

> “Short-term momentum has turned down and the higher-level trend no longer supports holding.”

---

### Note on positions

This project currently operates in **signal-only mode**:

* It does **not** track whether you are “in” or “out” of a position.
* It may emit multiple BUY signals during a prolonged uptrend, and multiple SELL signals during prolonged weakness.
* SQLite is used only to avoid duplicate alerts on the **same candle**, not to track positions.

This is intentional and keeps the system simple.

---

## Scheduling (cron example)

The monitor is scheduled to run **only when U.S. prices can actually change**, including:

* Pre-market (04:00–09:30 ET)
* Regular session (09:30–16:00 ET)
* After-hours (16:00–20:00 ET)

Cron is configured in **U.S. Eastern Time** so daylight saving time is handled automatically.

⚠️ `CRON_TZ` applies to all lines below it until reset.

```bash
CRON_TZ=America/New_York

# Pre-market (04:00–09:20 ET), every 10 minutes
*/10 4-8 * * 1-5  cd /home/<user>/PythonProjects/RichKingTracker && /home/<user>/PythonProjects/RichKingTracker/.venv/bin/python -m app.main >> logs/cron_monitor.out 2>&1
0-20/10 9 * * 1-5  cd /home/<user>/PythonProjects/RichKingTracker && /home/<user>/PythonProjects/RichKingTracker/.venv/bin/python -m app.main >> logs/cron_monitor.out 2>&1

# Regular session + immediate post-close (09:30–16:20 ET)
30-59/10 9  * * 1-5  cd /home/<user>/PythonProjects/RichKingTracker && /home/<user>/PythonProjects/RichKingTracker/.venv/bin/python -m app.main >> logs/cron_monitor.out 2>&1
*/10 10-15 * * 1-5  cd /home/<user>/PythonProjects/RichKingTracker && /home/<user>/PythonProjects/RichKingTracker/.venv/bin/python -m app.main >> logs/cron_monitor.out 2>&1
0-20/10 16 * * 1-5  cd /home/<user>/PythonProjects/RichKingTracker && /home/<user>/PythonProjects/RichKingTracker/.venv/bin/python -m app.main >> logs/cron_monitor.out 2>&1

# After-hours (16:30–19:50 ET)
30-59/10 16 * * 1-5  cd /home/<user>/PythonProjects/RichKingTracker && /home/<user>/PythonProjects/RichKingTracker/.venv/bin/python -m app.main >> logs/cron_monitor.out 2>&1
*/10 17-19 * * 1-5  cd /home/<user>/PythonProjects/RichKingTracker && /home/<user>/PythonProjects/RichKingTracker/.venv/bin/python -m app.main >> logs/cron_monitor.out 2>&1

# HEALTH: every 30 minutes during 04:00–20:00 ET (Mon–Fri)
*/30 4-19 * * 1-5  cd /home/sun/PythonProjects/RichKingTracker && /home/sun/PythonProjects/RichKingTracker/.venv/bin/python -m app.health_report >> logs/cron_health.out 2>&1

# HEALTH: daily heartbeat (08:05 ET every day)
5 8 * * *  cd /home/sun/PythonProjects/RichKingTracker && /home/sun/PythonProjects/RichKingTracker/.venv/bin/python -m app.health_report >> logs/cron_health.out 2>&1
```

If you have other cron jobs that should remain in local time, reset afterwards:

```bash
CRON_TZ=Asia/Seoul
```

---

## Health reporting

The monitor writes execution records into SQLite (`run_history`).

The health reporter:

* Runs periodically
* **Sends Telegram messages only when something meaningful changes**

  * ERROR
  * STALE (no recent runs)
  * New completed run
  * Optional once-per-day OK heartbeat (Seoul date)

This avoids repetitive “still OK” spam while ensuring failures are surfaced quickly.

---

## Notes / caveats

* Yahoo Finance hourly candles may align on `:30` instead of `:00`.
* Weekends and U.S. holidays produce no new candles.
* This system is **monitoring and notification only**, not automated trading.
* Signals are designed for **decision support**, not blind execution.
