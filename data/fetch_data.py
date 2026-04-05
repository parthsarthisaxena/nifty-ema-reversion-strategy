# data/fetch_data.py

import yfinance as yf
import pandas as pd
import os

# Nifty 50 tickers (yfinance format — .NS suffix for NSE)
NIFTY50_TICKERS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
    "LT.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS", "HCLTECH.NS",
    "SUNPHARMA.NS", "TITAN.NS", "ULTRACEMCO.NS", "BAJFINANCE.NS", "WIPRO.NS"
]
# Using 20 for speed — easy to add all 50 later

def fetch_data(ticker, period="60d", interval="15m"):
    """
    Fetch OHLCV data for a single ticker.
    period: max 60d for 15m data via yfinance
    interval: 15m
    """
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if df.empty:
            print(f"No data for {ticker}")
            return None
        df.dropna(inplace=True)
        print(f"Fetched {len(df)} rows for {ticker}")
        return df
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None


def fetch_all(save=True):
    """
    Fetch data for all Nifty 50 tickers and optionally save as CSV.
    """
    all_data = {}
    for ticker in NIFTY50_TICKERS:
        df = fetch_data(ticker)
        if df is not None:
            all_data[ticker] = df
            if save:
                path = f"data/{ticker.replace('.', '_')}_15m.csv"
                df.to_csv(path)
                print(f"Saved → {path}")
    return all_data


if __name__ == "__main__":
    fetch_all(save=True)
    NIFTY50_TICKERS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS",
    "LT.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS",
    "TITAN.NS", "ULTRACEMCO.NS", "BAJFINANCE.NS", "WIPRO.NS"
    # Removed: KOTAKBANK, SUNPHARMA, HCLTECH — consistent losers
]