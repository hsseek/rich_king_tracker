# Gemini Project Instructions — RichKingTracker

You are working on a Python-based stock monitoring and notification system.

## Project intent
- This is a **decision-support tool**, not an auto-trader.
- Signals must be explainable, logged, and low-noise.
- Avoid overengineering unless explicitly requested.

## Current strategy (authoritative)
- Multi-timeframe regime model:
  - Regime: 1-hour candles
  - Execution: 15-minute candles
- Only **closed candles** are tradable.
- Pre-market and after-hours data are included.
- Data source: Yahoo Finance via yfinance.

### Regime definition (1h)
- UP: EMA(9) > EMA(21) AND EMA(21) slope > 0
- DOWN: EMA(9) < EMA(21) AND EMA(21) slope < 0
- NEUTRAL: otherwise

### Execution signal (15m)
- BUY: EMA(3) > EMA(9) persists for N bars
- SELL: EMA(3) < EMA(9) persists for N bars
- Default persistence: N = 2

### Signal policy
- Signal-only mode (no position tracking).
- Deduplicate alerts by last processed closed candle timestamp.
- SELL requires:
  - bearish execution signal
  - AND regime is not UP

## Engineering constraints
- Prefer incremental patches over rewrites.
- Preserve SQLite schema unless a change is explicitly justified.
- Logs must remain readable when run via cron.
- Avoid acting on partial / still-forming candles.

## What NOT to do unless asked
- Do not introduce ML models.
- Do not optimize for profit or backtest unless requested.
- Do not remove existing logging or health reporting.
- Do not add real-time streaming or WebSocket logic.

## How to respond
- Explain *why* before changing logic.
- When modifying code, specify:
  - files changed
  - new behavior
  - backward-compatibility impact
- Keep explanations practical and concise.

