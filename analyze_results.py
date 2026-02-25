import pandas as pd
import numpy as np

def optimize(df):
    if df.empty:
        print("No trades found.")
        return

    # Drop duplicates
    before = len(df)
    df.drop_duplicates(subset=['Ticker', 'Entry'], inplace=True)
    after = len(df)
    if before != after:
        print(f"Dropped {before - after} duplicate trades. Remaining: {after}")

    # Filter out 'Running' trades for win rate calculation if desired,
    # or treat them based on current PnL. For standard backtest, we often use closed trades.
    # Here we stick to Win/Loss outcome determined by TP/SL.
    df_closed = df[df['Result'].isin(['Win', 'Loss'])].copy()

    best_score = -1
    best_params = None
    results = []

    # Grid Search
    rs_thresholds = [70, 80, 85, 90]
    fvg_thresholds = [0.5, 1.0, 1.5]
    bo_thresholds = [1.0, 1.5, 2.0]
    atr_thresholds = [3.0, 4.0, 5.0]

    print("\nRunning Grid Search Optimization (with ATR Risk)...")

    for rs_t in rs_thresholds:
        for fvg_t in fvg_thresholds:
            for bo_t in bo_thresholds:
                for atr_t in atr_thresholds:
                    # Apply filters
                    # Handle NaNs in RS by treating them as 0 (fail filter)
                    mask = (df_closed['RS'].fillna(0) >= rs_t) & \
                           (df_closed['FVG_Gap'] >= fvg_t) & \
                           (df_closed['BO_Strength'] >= bo_t) & \
                           (df_closed['ATR_Risk'] >= atr_t)

                    filtered = df_closed[mask]

                    if len(filtered) < 10: continue # Ignore small sample sizes

                    wins = len(filtered[filtered['Result'] == 'Win'])
                    losses = len(filtered[filtered['Result'] == 'Loss'])
                    total = wins + losses

                    if total == 0: continue

                    win_rate = wins / total * 100

                    gross_profit = filtered[filtered['Result'] == 'Win']['PnL%'].sum()
                    gross_loss = abs(filtered[filtered['Result'] == 'Loss']['PnL%'].sum())

                    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
                    cum_ret = filtered['PnL%'].sum()

                    # Scoring metric: PF * log(Trades) to balance quality and quantity
                    # Or just prioritize PF with minimum trades
                    score = pf

                    res = {
                        'RS': rs_t,
                        'FVG': fvg_t,
                        'BO': bo_t,
                        'ATR': atr_t,
                        'Trades': total,
                        'WinRate': win_rate,
                        'PF': pf,
                        'Return': cum_ret
                    }
                    results.append(res)

                    if score > best_score:
                        best_score = score
                        best_params = res

    # Sort results by PF descending
    results.sort(key=lambda x: x['PF'], reverse=True)

    print("Optimization Results (Top 20 by PF)")
    print("="*90)
    print(f"{'RS':<5} {'FVG':<5} {'BO':<5} {'ATR':<5} {'Trades':<8} {'WinRate':<10} {'PF':<8} {'Return':<10}")
    print("-" * 90)

    for r in results[:20]:
        print(f"{r['RS']:<5} {r['FVG']:<5.1f} {r['BO']:<5.1f} {r['ATR']:<5.1f} {r['Trades']:<8} {r['WinRate']:<10.1f} {r['PF']:<8.2f} {r['Return']:<10.1f}")

    print()
    if best_params:
        print("Best Combination based on PF:")
        print(best_params)

if __name__ == "__main__":
    try:
        df = pd.read_csv('rs_combined_trades.csv')
        optimize(df)
    except Exception as e:
        print(f"Error: {e}")
