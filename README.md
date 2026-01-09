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
TELEGRAM_PERSONAL_CHAT_ID=zzzz

# Optional
TICKERS=QQQ
ALERT_DB=/home/<user>/PythonProjects/RichKingTracker/alerts.db
LOG_DIR=/home/<user>/PythonProjects/RichKingTracker/logs
LOG_FILE=monitor.log

# Timeframe
REGIME_INTERVAL=1h
EXEC_INTERVAL=30m
EXEC_CONFIRM_BARS=3
LOOKBACK_DAYS_REGIME=30
LOOKBACK_DAYS_EXEC=20

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
| **Execution signal** | **30-minute candles** | Responsive enough for earlier entries/exits |

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
      │ 30-minute candles │                   │ 30-minute candles │
      │                   │                   │                   │
      │ EMA(3) vs EMA(9)  │                   │ EMA(3) vs EMA(9)  │
      │ persistence (3x)  │                   │ persistence (3x)  │
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

### Execution Momentum Index (EMI)

The EMI measures the strength of the execution signal by quantifying the separation between the fast and slow EMAs on the 15-minute chart, normalized by price.

-   **Formula:** `EMI = ((EMA3 - EMA9) / Close) * 1000`
-   **Interpretation:**
    -   A positive EMI indicates BUY momentum; a negative EMI indicates SELL momentum.
    -   A larger absolute value (e.g., `1.5` vs `0.5`) suggests stronger momentum for the signal.
    -   Because it is normalized, it can be compared across different stocks and price levels.

---

### Relative Volume Index (RVI)

The RVI measures the conviction behind a signal by comparing the trading volume of the signal candle to the recent average.

-   **Formula:** `RVI = Volume_of_signal_candle / Average_volume_over_last_20_candles`
-   **Interpretation:**
    -   `RVI > 1.0`: The signal occurred on above-average volume, suggesting higher conviction.
    -   `RVI < 1.0`: The signal occurred on below-average volume, suggesting weaker conviction.
    -   It provides a dimension of analysis independent of price-based indicators like EMAs.

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

## Execution signal (30-minute timeframe)

The **execution signal** determines *when* to act.

We use a simple, fast rule:

| Condition       | Meaning                     |
| --------------- | --------------------------- |
| EMA(3) > EMA(9) | Short-term bullish momentum |
| EMA(3) < EMA(9) | Short-term bearish momentum |

To avoid reacting to a single noisy candle, the condition must hold for:

* **`EXEC_CONFIRM_BARS = 3` consecutive closed 30-minute candles**

---

## BUY / SELL decision logic

### BUY signal

A **BUY** notification is sent when **both** are true:

1. **1-hour regime is UP**
2. **30-minute execution signal is bullish**, confirmed for 3 bars
   (`EMA(3) > EMA(9)` persists)

Interpretation:

> “The broader trend is up, and short-term momentum has aligned with it.”

---

### SELL signal (exit logic)

A **SELL** notification is sent when **both** are true:

1. **1-hour regime is no longer UP** (DOWN or NEUTRAL)
2. **30-minute execution signal is bearish**, confirmed for 3 bars
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

## Notes / caveats

* Yahoo Finance hourly candles may align on `:30` instead of `:00`.
* Weekends and U.S. holidays produce no new candles.
* This system is **monitoring and notification only**, not automated trading.
* Signals are designed for **decision support**, not blind execution.
