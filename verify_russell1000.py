import pandas as pd
import numpy as np

def analyze_russell1000():
    # Load the Russell 3000 list and grab the top 1000
    r3k_df = pd.read_csv('backend/russell3000.csv', header=None)
    # File has BOM so clean it up
    r3k_df[0] = r3k_df[0].str.replace('\ufeff', '')

    # Take the top 1000 tickers to simulate the Russell 1000
    r1k_tickers = r3k_df[0].tolist()[:1000]

    print(f"Loaded {len(r1k_tickers)} tickers representing the Russell 1000.")

    # Load all trades
    trades = pd.read_csv('unified_trades.csv')
    trades = trades[trades['Result'] != 'Open'].copy()

    # Filter for Russell 1000 trades
    r1k_trades = trades[trades['Ticker'].isin(r1k_tickers)].copy()
    print(f"Total Breakout Trades in Russell 1000 over 10 years: {len(r1k_trades)}")

    # ----------------------------------------------------
    # Baseline Output (RS >= 90, AD >= 60, ATR >= 3.0)
    # ----------------------------------------------------
    top_perf = r1k_trades[
        (r1k_trades['RS_Rating'] >= 90) &
        (r1k_trades['AD_Rating'] >= 60) &
        (r1k_trades['ATR_Risk'] >= 3.0)
    ]

    b_wins = len(top_perf[top_perf['Result'] == 'Win'])
    b_losses = len(top_perf) - b_wins
    b_wr = b_wins / len(top_perf) * 100 if len(top_perf) > 0 else 0
    b_gp = top_perf[top_perf['Result'] == 'Win']['PnL'].sum()
    b_gl = abs(top_perf[top_perf['Result'] == 'Loss']['PnL'].sum())
    b_pf = b_gp / b_gl if b_gl > 0 else 999

    print(f"\n--- Russell 1000 Only (RS>=90, AD>=60, ATR>=3.0) ---")
    print(f"Trades:   {len(top_perf)}")
    print(f"Win Rate: {b_wr:.2f}% ({b_wins} Wins / {b_losses} Losses)")
    print(f"PF:       {b_pf:.2f}")

    # What if we apply the Russell 3000 optimized ATR (ATR >= 4.0)?
    top_perf_4 = r1k_trades[
        (r1k_trades['RS_Rating'] >= 90) &
        (r1k_trades['AD_Rating'] >= 60) &
        (r1k_trades['ATR_Risk'] >= 4.0)
    ]

    b_wins4 = len(top_perf_4[top_perf_4['Result'] == 'Win'])
    b_losses4 = len(top_perf_4) - b_wins4
    b_wr4 = b_wins4 / len(top_perf_4) * 100 if len(top_perf_4) > 0 else 0
    b_gp4 = top_perf_4[top_perf_4['Result'] == 'Win']['PnL'].sum()
    b_gl4 = abs(top_perf_4[top_perf_4['Result'] == 'Loss']['PnL'].sum())
    b_pf4 = b_gp4 / b_gl4 if b_gl4 > 0 else 999

    print(f"\n--- Russell 1000 Only (RS>=90, AD>=60, ATR>=4.0) ---")
    print(f"Trades:   {len(top_perf_4)}")
    print(f"Win Rate: {b_wr4:.2f}% ({b_wins4} Wins / {b_losses4} Losses)")
    print(f"PF:       {b_pf4:.2f}")

if __name__ == "__main__":
    analyze_russell1000()