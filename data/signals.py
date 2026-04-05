# strategy/signals.py

import pandas as pd
import numpy as np
import datetime


def load_nifty_regime(nifty_path="data/NIFTY_INDEX_15m.csv"):
    
    """
    Load Nifty index and compute daily regime.
    Returns a dict: {date -> 'bullish' or 'bearish'}
    """
    try:
        nifty = pd.read_csv(nifty_path, index_col=0, skiprows=[1])
        nifty = nifty[nifty.index != 'Datetime']
        nifty.index = pd.to_datetime(nifty.index, utc=True, errors='coerce')
        nifty = nifty[nifty.index.notna()]
        nifty['Close'] = pd.to_numeric(nifty['Close'], errors='coerce')
        print(f"  Nifty data loaded: {len(nifty)} rows")
        print(f"  Date range: {nifty.index.min()} to {nifty.index.max()}")
         
        if nifty.index.tzinfo is not None:
            nifty.index = nifty.index.tz_convert('Asia/Kolkata')
        else:
            nifty.index = nifty.index.tz_localize('Asia/Kolkata')

        nifty['Close'] = pd.to_numeric(nifty['Close'], errors='coerce')
        nifty.dropna(subset=['Close'], inplace=True)

        # Daily close — resample to day
        daily = nifty['Close'].resample('D').last().dropna()

        # 20-day EMA of daily closes
        daily_ema = daily.ewm(span=20, adjust=False).mean()

        # Regime per day
        regime = {}
        for date, close in daily.items():
            ema = daily_ema[date]
            regime[date.date()] = 'bullish' if close >= ema else 'bearish'

        bullish_days = sum(1 for v in regime.values() if v == 'bullish')
        bearish_days = sum(1 for v in regime.values() if v == 'bearish')
        print(f"  Regime filter: {bullish_days} bullish days, "
              f"{bearish_days} bearish days loaded")
        return regime

    except Exception as e:
        print(f"  Warning: Could not load Nifty regime ({e}). Trading all days.")
        return {}


def compute_signals(df, regime=None):
    """
    10 EMA Reversion Strategy — with Nifty Regime Filter

    ENTRY CONDITIONS:
    - First 15-min candle range > 1% (strong momentum day)
    - Bullish day : first candle GREEN + Close > 10 EMA → look for LONG
    - Bearish day : first candle RED   + Close < 10 EMA → look for SHORT
    - Price touches 10 EMA within 9:15–10:30 AM
    - Nifty index must be ABOVE its 20-day EMA (regime filter)

    EXIT:
    - SL  : 0.6% from entry
    - TP1 : 0.9% (50% position)
    - TP2 : 2.5% (50% position)
    - Time: 3:10 PM if still open
    """
    df = df.copy()

    # ── 10 EMA ───────────────────────────────────────────────
    df['ema10'] = df['Close'].ewm(span=10, adjust=False).mean()

    # ── Timezone ─────────────────────────────────────────────
    df.index = pd.to_datetime(df.index)
    if df.index.tzinfo is not None:
        df.index = df.index.tz_convert('Asia/Kolkata')
    else:
        df.index = df.index.tz_localize('Asia/Kolkata')

    df['date'] = df.index.date
    df['time'] = df.index.time

    first_candle_time = datetime.time(9, 15)
    session_end       = datetime.time(12, 0)

    # ── Initialize signal columns ─────────────────────────────
    df['long_signal']  = False
    df['short_signal'] = False
    df['entry_price']  = np.nan
    df['sl']           = np.nan
    df['tp1']          = np.nan
    df['tp2']          = np.nan
    df['day_bias']     = 'neutral'

    for date, day_df in df.groupby('date'):

        # ── Regime filter ─────────────────────────────────────
        if regime:
            day_regime = regime.get(date, 'bearish')
            if day_regime == 'bearish':
                allowed_bias = 'bearish'
            else:
                allowed_bias = 'bullish'
        else:
            allowed_bias = None  # skip entire day — market in downtrend

        # ── First candle analysis ─────────────────────────────
        first_candles = day_df[day_df['time'] == first_candle_time]
        if first_candles.empty:
            continue

        fc       = first_candles.iloc[0]
        fc_range = (fc['High'] - fc['Low']) / fc['Open'] * 100
        fc_green = fc['Close'] > fc['Open']
        fc_red   = fc['Close'] < fc['Open']
        fc_above = fc['Close'] > fc['ema10']
        fc_below = fc['Close'] < fc['ema10']

        if fc_range <= 1.0:
            continue

        if fc_green and fc_above:
            bias = 'bullish'
        elif fc_red and fc_below:
            bias = 'bearish'
        else:
            continue

# ADD THIS LINE:
        if allowed_bias is not None and bias != allowed_bias:
            continue 

        # ── Find EMA touch ────────────────────────────────────
        session_df   = day_df[
            (day_df['time'] > first_candle_time) &
            (day_df['time'] <= session_end)
        ]
        signal_given = False

        for idx, row in session_df.iterrows():
            if signal_given:
                break

            ema         = row['ema10']
            ema_touched = row['Low'] <= ema <= row['High']

            if not ema_touched:
                continue

            if bias == 'bullish':
                entry = ema
                sl    = entry * (1 - 0.006)
                tp1   = entry * (1 + 0.009)
                tp2   = entry * (1 + 0.025)
                df.at[idx, 'long_signal']  = True

            else:
                entry = ema
                sl    = entry * (1 + 0.006)
                tp1   = entry * (1 - 0.009)
                tp2   = entry * (1 - 0.025)
                df.at[idx, 'short_signal'] = True

            df.at[idx, 'entry_price'] = entry
            df.at[idx, 'sl']          = sl
            df.at[idx, 'tp1']         = tp1
            df.at[idx, 'tp2']         = tp2
            df.at[idx, 'day_bias']    = bias
            signal_given              = True

    return df


if __name__ == "__main__":
    import os

    files = [f for f in os.listdir("data") if f.endswith(".csv")
             and "NIFTY_INDEX" not in f]

    if not files:
        print("No CSV files found.")
    else:
        regime = load_nifty_regime()

        df = pd.read_csv(
            f"data/{files[0]}",
            index_col=0,
            parse_dates=True,
            skiprows=[1]
        )
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(inplace=True)

        result    = compute_signals(df, regime=regime)
        long_sig  = result[result['long_signal']  == True]
        short_sig = result[result['short_signal'] == True]

        print(f"Testing on    : {files[0]}")
        print(f"Total candles : {len(df)}")
        print(f"Long  signals : {len(long_sig)}")
        print(f"Short signals : {len(short_sig)}")
        print(f"Total signals : {len(long_sig) + len(short_sig)}")
        