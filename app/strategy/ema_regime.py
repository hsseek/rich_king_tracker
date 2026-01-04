import pandas as pd
import numpy as np


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    Wilder-style RSI using EMA smoothing (common implementation).
    """
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_val = 100 - (100 / (1 + rs))
    return rsi_val.fillna(0)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    ATR using rolling mean of True Range (sufficient for filtering noise).
    """
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)

    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    return tr.rolling(window=period, min_periods=period).mean()


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    # EMAs (close-based)
    out["EMA3"] = ema(out["Close"], 3)
    out["EMA9"] = ema(out["Close"], 9)
    out["EMA21"] = ema(out["Close"], 21)

    # Slopes
    out["EMA21_slope"] = out["EMA21"].diff()

    # RSI(5)
    out["RSI5"] = rsi(out["Close"], period=5)

    # ATR(5)
    out["ATR5"] = atr(out, period=5)

    # Gap for distance filter
    out["GAP_3_9"] = out["EMA3"] - out["EMA9"]

    return out


def detect_confirmed_switch(df: pd.DataFrame) -> bool:
    """
    Existing logic: downtrend -> (uptrend for 2 consecutive candles),
    based on EMA9/EMA21 and EMA21 slope.
    """
    ind = compute_indicators(df)

    down = (ind["EMA9"] < ind["EMA21"]) & (ind["EMA21_slope"] < 0)
    up = (ind["EMA9"] > ind["EMA21"]) & (ind["EMA21_slope"] > 0)

    if len(ind) < 30:
        return False

    return bool(down.iloc[-3] and up.iloc[-2] and up.iloc[-1])


def detect_short_momentum_up_2h(df: pd.DataFrame, k: float = 0.15) -> bool:
    """
    Alert condition:
      ShortMomentumUp[t] := (EMA3 > EMA9) AND (RSI5 > 50) AND (RSI5 rising)
                            AND (EMA3 - EMA9 > k * ATR5)
      Trigger if ShortMomentumUp holds for the last 2 closed candles.

    Notes:
    - Uses the last two rows of the computed indicators (assumed closed candles).
    - Requires ATR5 to exist (needs at least 5 bars).
    """
    ind = compute_indicators(df)

    if len(ind) < 7:
        return False

    # Last two closed candles
    t = ind.iloc[-1]
    t1 = ind.iloc[-2]

    # Ensure ATR is available (rolling min_periods=period)
    if pd.isna(t["ATR5"]) or pd.isna(t1["ATR5"]):
        return False

    def short_up(row, prev_row) -> bool:
        gap = row["GAP_3_9"]
        thr = k * row["ATR5"]
        return bool(
            (row["EMA3"] > row["EMA9"])
            and (row["RSI5"] > 50)
            and (row["RSI5"] > prev_row["RSI5"])  # RSI rising
            and (gap > thr)
        )

    return short_up(t1, ind.iloc[-3]) and short_up(t, t1)
