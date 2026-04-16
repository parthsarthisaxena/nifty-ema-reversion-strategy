# backtest/engine.py

import pandas as pd
import numpy as np
import os
import sys
import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.signals import compute_signals

# ── Trading Cost Constants ────────────────────────────────────
BROKERAGE_PER_ORDER = 20       # ₹20 flat per order (Zerodha)
ORDERS_PER_TRADE    = 2        # entry + exit
BROKERAGE_PER_TRADE = BROKERAGE_PER_ORDER * ORDERS_PER_TRADE  # ₹40

STT_RATE            = 0.000025  # 0.025% on sell turnover
SLIPPAGE_RATE       = 0.0005   # 0.05% slippage on entry & exit


def apply_slippage(price, direction, action):
    """
    Slippage works against you always:
    - Long  entry : you buy  slightly HIGHER than signal price
    - Long  exit  : you sell slightly LOWER  than signal price
    - Short entry : you sell slightly LOWER  than signal price
    - Short exit  : you buy  slightly HIGHER than signal price
    """
    if direction == 'long':
        if action == 'entry':
            return price * (1 + SLIPPAGE_RATE)   # pay more to buy
        else:
            return price * (1 - SLIPPAGE_RATE)   # receive less when selling
    else:  # short
        if action == 'entry':
            return price * (1 - SLIPPAGE_RATE)   # sell at lower price
        else:
            return price * (1 + SLIPPAGE_RATE)   # buy back at higher price


def calculate_costs(exit_price, shares, direction):
    """
    Calculate total transaction costs for a trade.
    STT is charged on sell side turnover.
    """
    sell_turnover = exit_price * shares
    stt           = sell_turnover * STT_RATE
    total_cost    = BROKERAGE_PER_TRADE + stt
    return total_cost


def run_backtest(df, ticker, initial_capital=100000, regime=None):
    """
    Simulates trade execution with:
    - Partial exits (TP1 50%, TP2 50%)
    - Realistic brokerage (₹40/trade)
    - STT on sell side
    - Slippage (0.05% on entry & exit)
    """

    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df.dropna(inplace=True)

    df = compute_signals(df, regime=regime)

    capital      = initial_capital
    position     = 0
    trades       = []
    equity       = []

    entry_price  = 0
    sl           = 0
    tp1          = 0
    tp2          = 0
    entry_time   = None
    shares_total = 0
    shares_left  = 0
    tp1_hit      = False
    tp1_pnl      = 0
    direction    = None

    time_exit    = datetime.time(15, 0)

    for i in range(len(df)):
        row          = df.iloc[i]
        timestamp    = df.index[i]
        curr_time    = timestamp.time()

        # Track equity
        if position != 0:
            if direction == 'long':
                unreal = shares_left * (row['Close'] - entry_price)
            else:
                unreal = shares_left * (entry_price - row['Close'])
            equity.append({'time': timestamp, 'equity': capital + unreal})
        else:
            equity.append({'time': timestamp, 'equity': capital})

        # ── ENTRY ──────────────────────────────────────────────
        if position == 0:

            if row['long_signal'] or row['short_signal']:
                direction   = 'long' if row['long_signal'] else 'short'
                raw_entry   = row['entry_price']

                # Apply slippage to entry
                entry_price = apply_slippage(raw_entry, direction, 'entry')

                sl          = row['sl']
                tp1         = row['tp1']
                tp2         = row['tp2']
                tp1_hit     = False
                tp1_pnl     = 0

                # Position sizing: risk 1% of capital
                if direction == 'long':
                    risk_per_share = entry_price - sl
                else:
                    risk_per_share = sl - entry_price

                risk_amount  = capital * 0.01
                shares_total = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0
                shares_left  = shares_total
                entry_time   = timestamp
                position     = 1 if direction == 'long' else -1

                if shares_total > 0:
                    print(f"  {'LONG' if direction=='long' else 'SHORT'} ENTRY | "
                          f"{timestamp} | ₹{entry_price:.2f} (slippage applied) | "
                          f"Shares: {shares_total}")

        # ── EXIT ───────────────────────────────────────────────
        elif position != 0 and shares_left > 0:

            half      = shares_total // 2
            do_exit   = curr_time >= time_exit

            if direction == 'long':

                # TP1
                if not tp1_hit and row['High'] >= tp1:
                    exit_p   = apply_slippage(tp1, direction, 'exit')
                    gross    = half * (exit_p - entry_price)
                    cost     = calculate_costs(exit_p, half, direction)
                    net      = gross - cost
                    capital += net
                    shares_left -= half
                    tp1_hit  = True
                    tp1_pnl  = net
                    print(f"    TP1     | {timestamp} | Net: +₹{net:.0f} "
                          f"(cost ₹{cost:.0f})")

                # TP2
                if tp1_hit and row['High'] >= tp2:
                    exit_p    = apply_slippage(tp2, direction, 'exit')
                    gross     = shares_left * (exit_p - entry_price)
                    cost      = calculate_costs(exit_p, shares_left, direction)
                    net       = gross - cost
                    capital  += net
                    total_net = tp1_pnl + net
                    trades.append(_trade(ticker, direction, entry_time,
                                        timestamp, entry_price, exit_p,
                                        total_net, 'WIN', 'TP2'))
                    print(f"    TP2     | {timestamp} | Trade Net: +₹{total_net:.0f}")
                    position = 0; shares_left = 0

                # SL
                elif row['Low'] <= sl:
                    exit_p    = apply_slippage(sl, direction, 'exit')
                    gross     = shares_left * (exit_p - entry_price)
                    cost      = calculate_costs(exit_p, shares_left, direction)
                    net       = gross - cost
                    capital  += net
                    total_net = tp1_pnl + net
                    result    = 'WIN' if total_net > 0 else 'LOSS'
                    reason    = 'SL_after_TP1' if tp1_hit else 'STOP LOSS'
                    trades.append(_trade(ticker, direction, entry_time,
                                        timestamp, entry_price, exit_p,
                                        total_net, result, reason))
                    print(f"    SL      | {timestamp} | Trade Net: ₹{total_net:.0f}")
                    position = 0; shares_left = 0

                # Time exit
                elif do_exit:
                    exit_p    = apply_slippage(row['Close'], direction, 'exit')
                    gross     = shares_left * (exit_p - entry_price)
                    cost      = calculate_costs(exit_p, shares_left, direction)
                    net       = gross - cost
                    capital  += net
                    total_net = tp1_pnl + net
                    result    = 'WIN' if total_net > 0 else 'LOSS'
                    trades.append(_trade(ticker, direction, entry_time,
                                        timestamp, entry_price, exit_p,
                                        total_net, result, 'TIME EXIT'))
                    print(f"    TIME    | {timestamp} | Trade Net: ₹{total_net:.0f}")
                    position = 0; shares_left = 0

            elif direction == 'short':

                # TP1
                if not tp1_hit and row['Low'] <= tp1:
                    exit_p   = apply_slippage(tp1, direction, 'exit')
                    gross    = half * (entry_price - exit_p)
                    cost     = calculate_costs(exit_p, half, direction)
                    net      = gross - cost
                    capital += net
                    shares_left -= half
                    tp1_hit  = True
                    tp1_pnl  = net
                    print(f"    TP1     | {timestamp} | Net: +₹{net:.0f} "
                          f"(cost ₹{cost:.0f})")

                # TP2
                if tp1_hit and row['Low'] <= tp2:
                    exit_p    = apply_slippage(tp2, direction, 'exit')
                    gross     = shares_left * (entry_price - exit_p)
                    cost      = calculate_costs(exit_p, shares_left, direction)
                    net       = gross - cost
                    capital  += net
                    total_net = tp1_pnl + net
                    trades.append(_trade(ticker, direction, entry_time,
                                        timestamp, entry_price, exit_p,
                                        total_net, 'WIN', 'TP2'))
                    print(f"    TP2     | {timestamp} | Trade Net: +₹{total_net:.0f}")
                    position = 0; shares_left = 0

                # SL
                elif row['High'] >= sl:
                    exit_p    = apply_slippage(sl, direction, 'exit')
                    gross     = shares_left * (entry_price - exit_p)
                    cost      = calculate_costs(exit_p, shares_left, direction)
                    net       = gross - cost
                    capital  += net
                    total_net = tp1_pnl + net
                    result    = 'WIN' if total_net > 0 else 'LOSS'
                    reason    = 'SL_after_TP1' if tp1_hit else 'STOP LOSS'
                    trades.append(_trade(ticker, direction, entry_time,
                                        timestamp, entry_price, exit_p,
                                        total_net, result, reason))
                    print(f"    SL      | {timestamp} | Trade Net: ₹{total_net:.0f}")
                    position = 0; shares_left = 0

                # Time exit
                elif do_exit:
                    exit_p    = apply_slippage(row['Close'], direction, 'exit')
                    gross     = shares_left * (entry_price - exit_p)
                    cost      = calculate_costs(exit_p, shares_left, direction)
                    net       = gross - cost
                    capital  += net
                    total_net = tp1_pnl + net
                    result    = 'WIN' if total_net > 0 else 'LOSS'
                    trades.append(_trade(ticker, direction, entry_time,
                                        timestamp, entry_price, exit_p,
                                        total_net, result, 'TIME EXIT'))
                    print(f"    TIME    | {timestamp} | Trade Net: ₹{total_net:.0f}")
                    position = 0; shares_left = 0

    return trades, pd.DataFrame(equity)


def _trade(ticker, direction, entry_time, exit_time,
           entry, exit_p, pnl, result, reason):
    """Helper to build trade dict."""
    return {
        'ticker'     : ticker,
        'direction'  : direction.upper(),
        'entry_time' : entry_time,
        'exit_time'  : exit_time,
        'entry'      : entry,
        'exit'       : exit_p,
        'pnl'        : pnl,
        'result'     : result,
        'exit_reason': reason
    }


def run_all(initial_capital=100000):

    files = [f for f in os.listdir("data") if f.endswith("_1h.csv")
         and "NSEI" not in f]
    all_trades = []

    print(f"\n{'='*60}")
    print(f"  10 EMA REVERSION — WITH REAL COSTS")
    print(f"  Brokerage : ₹{BROKERAGE_PER_TRADE}/trade")
    print(f"  STT       : {STT_RATE*100}% on sell side")
    print(f"  Slippage  : {SLIPPAGE_RATE*100}% per side")
    print(f"  Stocks    : {len(files)} | Capital: ₹{initial_capital:,}")
    print(f"{'='*60}")
    from data.signals import load_nifty_regime
    regime = load_nifty_regime()
    for file in files:
        ticker = file.replace("data/NSEI_1h.csv", "")
        print(f"\n[{ticker}]")

        df = pd.read_csv(
            f"data/{file}",
            index_col=0,
            parse_dates=True,
            skiprows=[1]
        )
        trades, equity = run_backtest(df, ticker, initial_capital,regime)

        if trades:
            all_trades.extend(trades)
        else:
            print(f"  No trades.")

    return all_trades


if __name__ == "__main__":
    trades = run_all()

    if trades:
        df_trades = pd.DataFrame(trades)
        df_trades.to_csv("results/trades.csv", index=False)
        print(f"\n{'='*60}")
        print(f"  BACKTEST COMPLETE (with real costs)")
        print(f"  Total trades : {len(df_trades)}")
        print(f"  Saved → results/trades.csv")
        print(f"{'='*60}")
    else:
        print("\nNo trades generated.")
