# backtest/metrics.py

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os


def calculate_metrics(trades_path="results/trades.csv", initial_capital=100000):
    """
    Reads trades CSV and computes all key performance metrics.
    """

    df = pd.read_csv(trades_path)

    if df.empty:
        print("No trades found.")
        return

    # ── Basic Stats ──────────────────────────────────────────
    total_trades  = len(df)
    wins          = df[df['result'] == 'WIN']
    losses        = df[df['result'] == 'LOSS']

    win_rate      = len(wins) / total_trades * 100
    avg_win       = wins['pnl'].mean()
    avg_loss      = abs(losses['pnl'].mean())
    risk_reward   = avg_win / avg_loss if avg_loss != 0 else 0

    total_pnl     = df['pnl'].sum()
    final_capital = initial_capital + total_pnl
    total_return  = (total_pnl / initial_capital) * 100

    gross_profit  = wins['pnl'].sum()
    gross_loss    = abs(losses['pnl'].sum())
    profit_factor = gross_profit / gross_loss if gross_loss != 0 else float('inf')

    # ── Expectancy ───────────────────────────────────────────
    # Expected value per trade
    expectancy = (win_rate/100 * avg_win) - ((1 - win_rate/100) * avg_loss)

    # ── Equity Curve & Drawdown ──────────────────────────────
    df['cumulative_pnl']    = df['pnl'].cumsum()
    df['equity']            = initial_capital + df['cumulative_pnl']
    df['rolling_max']       = df['equity'].cummax()
    df['drawdown']          = df['equity'] - df['rolling_max']
    df['drawdown_pct']      = (df['drawdown'] / df['rolling_max']) * 100

    max_drawdown     = df['drawdown_pct'].min()
    max_drawdown_abs = df['drawdown'].min()

    # ── Sharpe Ratio (simplified) ────────────────────────────
    # Using per-trade returns
    df['trade_return'] = df['pnl'] / initial_capital
    sharpe = (df['trade_return'].mean() / df['trade_return'].std()) * np.sqrt(252) \
             if df['trade_return'].std() != 0 else 0

    # ── Exit Reason Breakdown ────────────────────────────────
    exit_breakdown = df['exit_reason'].value_counts()

    # ── Print Report ─────────────────────────────────────────
    print("\n" + "="*55)
    print("         STRATEGY PERFORMANCE REPORT")
    print("="*55)

    print(f"\n📊 OVERVIEW")
    print(f"   Initial Capital     : ₹{initial_capital:,.0f}")
    print(f"   Final Capital       : ₹{final_capital:,.0f}")
    print(f"   Total PnL           : ₹{total_pnl:+,.0f}")
    print(f"   Total Return        : {total_return:+.2f}%")

    print(f"\n🎯 TRADE STATISTICS")
    print(f"   Total Trades        : {total_trades}")
    print(f"   Winners             : {len(wins)}")
    print(f"   Losers              : {len(losses)}")
    print(f"   Win Rate            : {win_rate:.1f}%")
    print(f"   Avg Win             : ₹{avg_win:,.0f}")
    print(f"   Avg Loss            : ₹{avg_loss:,.0f}")
    print(f"   Risk-Reward Ratio   : 1:{risk_reward:.2f}")

    print(f"\n📈 PERFORMANCE METRICS")
    print(f"   Expectancy/Trade    : ₹{expectancy:+,.0f}")
    print(f"   Profit Factor       : {profit_factor:.2f}")
    print(f"   Sharpe Ratio        : {sharpe:.2f}")
    print(f"   Max Drawdown        : {max_drawdown:.2f}%  (₹{max_drawdown_abs:,.0f})")

    print(f"\n🚪 EXIT BREAKDOWN")
    for reason, count in exit_breakdown.items():
        print(f"   {reason:<20}: {count} trades")

    print(f"\n🏆 TOP 5 TRADES")
    top5 = df.nlargest(5, 'pnl')[['ticker', 'entry_time', 'pnl', 'result', 'exit_reason']]
    print(top5.to_string(index=False))

    print(f"\n💀 WORST 5 TRADES")
    worst5 = df.nsmallest(5, 'pnl')[['ticker', 'entry_time', 'pnl', 'result', 'exit_reason']]
    print(worst5.to_string(index=False))

    print("\n" + "="*55)

    # ── Plot Equity Curve ────────────────────────────────────
    plot_equity_curve(df, initial_capital)

    return df


def plot_equity_curve(df, initial_capital):
    """Generates and saves the equity curve chart."""

    fig, axes = plt.subplots(2, 1, figsize=(12, 8))
    fig.suptitle('Nifty 50 Momentum Breakout Strategy', fontsize=14, fontweight='bold')

    # ── Plot 1: Equity Curve ─────────────────────────────────
    ax1 = axes[0]
    ax1.plot(range(len(df)), df['equity'], color='#2ecc71', linewidth=2, label='Equity')
    ax1.axhline(y=initial_capital, color='gray', linestyle='--', linewidth=1, label='Starting Capital')
    ax1.fill_between(range(len(df)), df['equity'], initial_capital,
                     where=df['equity'] >= initial_capital, alpha=0.2, color='green')
    ax1.fill_between(range(len(df)), df['equity'], initial_capital,
                     where=df['equity'] < initial_capital, alpha=0.2, color='red')
    ax1.set_title('Equity Curve')
    ax1.set_ylabel('Capital (₹)')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'₹{x:,.0f}'))

    # ── Plot 2: Drawdown ─────────────────────────────────────
    ax2 = axes[1]
    ax2.fill_between(range(len(df)), df['drawdown_pct'], 0, color='red', alpha=0.4)
    ax2.plot(range(len(df)), df['drawdown_pct'], color='red', linewidth=1)
    ax2.set_title('Drawdown %')
    ax2.set_ylabel('Drawdown (%)')
    ax2.set_xlabel('Trade Number')
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('results/equity_curve.png', dpi=150, bbox_inches='tight')
    print("\n  📊 Equity curve saved → results/equity_curve.png")
    plt.show()


if __name__ == "__main__":
    calculate_metrics()