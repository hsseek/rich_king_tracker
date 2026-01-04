import yfinance as yf
import pandas as pd

def fetch_hourly(ticker: str, lookback_days: int = 10) -> pd.DataFrame:
    df = yf.download(
        tickers=ticker,
        period=f"{lookback_days}d",
        interval="1h",
        auto_adjust=False,
        progress=False,
        threads=False,
    ).dropna()

    # Robustly normalize columns for both single- and multi-ticker returns
    if isinstance(df.columns, pd.MultiIndex):
        lvl0 = set(df.columns.get_level_values(0))
        lvl1 = set(df.columns.get_level_values(1))

        if ticker in lvl0:
            df = df.xs(ticker, axis=1, level=0)
        elif ticker in lvl1:
            df = df.xs(ticker, axis=1, level=1)
        else:
            raise KeyError(
                f"Ticker '{ticker}' not found in MultiIndex columns. "
                f"Level0 sample={list(sorted(lvl0))[:6]}, Level1 sample={list(sorted(lvl1))[:6]}"
            )

    return df.dropna()
