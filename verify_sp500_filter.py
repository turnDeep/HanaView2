import pandas as pd
import yfinance as yf
import numpy as np

def fetch_sp500_data():
    print("Fetching SPY data...")
    spy = yf.download('SPY', start='2015-01-01', end='2025-12-31', progress=False)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)
    spy.columns = [c.lower() for c in spy.columns]

    # Calculate SMAs and EMAs
    periods = [5, 9, 21, 50, 100, 150, 200]

    for p in periods:
        spy[f'sma_{p}'] = spy['close'].rolling(window=p).mean()
        spy[f'ema_{p}'] = spy['close'].ewm(span=p, adjust=False).mean()

    # Shift by 1 day to prevent lookahead bias (we use yesterday's close/MA for today's trade)
    spy_shifted = spy.shift(1)

    # Create boolean masks indicating if SPY close is above the respective MA
    for p in periods:
        spy_shifted[f'above_sma_{p}'] = spy_shifted['close'] > spy_shifted[f'sma_{p}']
        spy_shifted[f'above_ema_{p}'] = spy_shifted['close'] > spy_shifted[f'ema_{p}']

    return spy_shifted

def analyze_market_filters():
    # Load the 4767 base trades
    trades = pd.read_csv('unified_trades.csv')
    trades = trades[trades['Result'] != 'Open'].copy()

    # Filter for the "Top Performance" condition (RS >= 90, AD >= 60, ATR >= 3.0)
    top_perf = trades[
        (trades['RS_Rating'] >= 90) &
        (trades['AD_Rating'] >= 60) &
        (trades['ATR_Risk'] >= 3.0)
    ].copy()

    print(f"\nBaseline Top Performance Trades: {len(top_perf)}")
    baseline_wins = len(top_perf[top_perf['Result'] == 'Win'])
    baseline_winrate = baseline_wins / len(top_perf) * 100
    gp = top_perf[top_perf['Result'] == 'Win']['PnL'].sum()
    gl = abs(top_perf[top_perf['Result'] == 'Loss']['PnL'].sum())
    baseline_pf = gp / gl if gl > 0 else 999

    print(f"Baseline Win Rate: {baseline_winrate:.2f}% | Baseline PF: {baseline_pf:.2f}")

    # Fetch SPY data
    spy = fetch_sp500_data()

    # Convert 'Date' column in trades to datetime if not already
    top_perf['Date'] = pd.to_datetime(top_perf['Date'])

    # Ensure SPY index is timezone-naive if trades are naive, or vice versa
    if top_perf['Date'].dt.tz is not None:
        spy.index = spy.index.tz_convert(top_perf['Date'].dt.tz)
    else:
        spy.index = spy.index.tz_localize(None)

    # Merge trades with SPY data based on 'Date'
    # We use left join to keep all trades and attach the shifted SPY data for that date
    merged = pd.merge(top_perf, spy, left_on='Date', right_index=True, how='left')

    results = []
    periods = [5, 9, 21, 50, 100, 150, 200]

    for ma_type in ['sma', 'ema']:
        for p in periods:
            filter_col = f'above_{ma_type}_{p}'

            # Filter trades where SPY was above the MA
            filtered_trades = merged[merged[filter_col] == True]

            # Excluded trades
            excluded_trades = merged[merged[filter_col] == False]
            excluded_wins = len(excluded_trades[excluded_trades['Result'] == 'Win'])
            excluded_losses = len(excluded_trades[excluded_trades['Result'] == 'Loss'])

            count = len(filtered_trades)
            if count == 0:
                continue

            wins = len(filtered_trades[filtered_trades['Result'] == 'Win'])
            losses = count - wins
            wr = wins / count * 100

            gp = filtered_trades[filtered_trades['Result'] == 'Win']['PnL'].sum()
            gl = abs(filtered_trades[filtered_trades['Result'] == 'Loss']['PnL'].sum())
            pf = gp / gl if gl > 0 else 999

            results.append({
                'Filter': f'SPY > {ma_type.upper()}{p}',
                'Trades_Kept': count,
                'Win_Rate': wr,
                'PF': pf,
                'Excluded_Losses': excluded_losses,
                'Excluded_Wins': excluded_wins,
                'Return_Sum': filtered_trades['PnL'].sum()
            })

    df_results = pd.DataFrame(results)

    print("\n--- Market Filter Results (Sorted by Profit Factor) ---")
    print(df_results.sort_values('PF', ascending=False).to_string(index=False, float_format="%.2f"))

    print("\n--- Market Filter Results (Sorted by Win Rate) ---")
    print(df_results.sort_values('Win_Rate', ascending=False).to_string(index=False, float_format="%.2f"))

if __name__ == "__main__":
    analyze_market_filters()