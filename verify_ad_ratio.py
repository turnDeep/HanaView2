import pandas as pd
import yfinance as yf
import numpy as np

def calculate_ad_ratio(df, window=50):
    """
    Calculates the Accumulation/Distribution Ratio (Up Volume / Down Volume)
    over a specified rolling window (default 50 days).
    """
    # Define up days (close > previous close) and down days
    is_up_day = df['close'] > df['close'].shift(1)
    is_down_day = df['close'] < df['close'].shift(1)

    # Isolate volume for up and down days
    up_volume = pd.Series(np.where(is_up_day, df['volume'], 0), index=df.index)
    down_volume = pd.Series(np.where(is_down_day, df['volume'], 0), index=df.index)

    # Calculate rolling sums
    rolling_up_vol = up_volume.rolling(window).sum()
    rolling_down_vol = down_volume.rolling(window).sum()

    # Calculate ratio (add small epsilon to avoid division by zero)
    ad_ratio = rolling_up_vol / np.where(rolling_down_vol == 0, 1, rolling_down_vol)

    return ad_ratio

def analyze_ad_ratio_filter():
    print("Loading baseline trades...")
    # Load all trades
    trades = pd.read_csv('unified_trades.csv')
    trades = trades[trades['Result'] != 'Open'].copy()

    # We want to compare against the baseline: RS >= 90, ATR >= 3.0
    # But this time, instead of AD_Rating >= 60, we'll test AD_Ratio
    base_trades = trades[(trades['RS_Rating'] >= 90) & (trades['ATR_Risk'] >= 3.0)].copy()

    print(f"Total Base Trades (RS >= 90, ATR >= 3.0): {len(base_trades)}")

    # Now we need to fetch historical data for these specific tickers to calculate AD Ratio at the time of breakout
    unique_tickers = base_trades['Ticker'].unique()
    print(f"Fetching data to calculate AD Ratio for {len(unique_tickers)} tickers...")

    # Create a dictionary to hold AD Ratio series for each ticker
    ad_ratio_dict = {}

    for i, ticker in enumerate(unique_tickers):
        try:
            df = yf.download(ticker, start='2015-01-01', end='2025-12-31', progress=False)
            if df.empty: continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.columns = [c.lower() for c in df.columns]

            # Calculate AD ratio
            ad_r = calculate_ad_ratio(df, window=50)
            # Shift by 1 day because the trade logic uses yesterday's metrics for today's breakout
            ad_ratio_dict[ticker] = ad_r.shift(1)
        except Exception as e:
            pass

        if (i+1) % 50 == 0:
            print(f" Processed {i+1}/{len(unique_tickers)} tickers...")

    # Map AD Ratios back to trades
    base_trades['AD_Ratio'] = np.nan
    base_trades['Date'] = pd.to_datetime(base_trades['Date'])

    for idx, row in base_trades.iterrows():
        t = row['Ticker']
        d = row['Date']
        if t in ad_ratio_dict:
            series = ad_ratio_dict[t]
            # Handle timezone naive/aware matching
            if d.tz is not None and series.index.tz is None:
                d = d.tz_localize(None)
            elif d.tz is None and series.index.tz is not None:
                d = d.tz_localize(series.index.tz)

            try:
                # Get index location to grab the exact matching date
                iloc_idx = series.index.get_indexer([d], method='ffill')[0]
                if iloc_idx >= 0:
                    base_trades.at[idx, 'AD_Ratio'] = series.iloc[iloc_idx]
            except Exception:
                pass

    # Drop rows where we couldn't calculate AD Ratio
    valid_trades = base_trades.dropna(subset=['AD_Ratio']).copy()
    print(f"\nCalculated AD Ratio for {len(valid_trades)} trades.\n")

    # ----------------------------------------------------
    # Baseline Output (AD Rating >= 60) for comparison
    # ----------------------------------------------------
    baseline_perf = valid_trades[valid_trades['AD_Rating'] >= 60]
    b_wins = len(baseline_perf[baseline_perf['Result'] == 'Win'])
    b_losses = len(baseline_perf) - b_wins
    b_wr = b_wins / len(baseline_perf) * 100 if len(baseline_perf) > 0 else 0
    b_gp = baseline_perf[baseline_perf['Result'] == 'Win']['PnL'].sum()
    b_gl = abs(baseline_perf[baseline_perf['Result'] == 'Loss']['PnL'].sum())
    b_pf = b_gp / b_gl if b_gl > 0 else 999
    print(f"[Reference] AD Rating >= 60: Trades={len(baseline_perf)}, WinRate={b_wr:.2f}%, PF={b_pf:.2f}\n")

    # ----------------------------------------------------
    # Grid Search Output (AD Ratio from 1.0 to 1.5)
    # ----------------------------------------------------
    thresholds = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5]
    results = []

    for t in thresholds:
        filtered = valid_trades[valid_trades['AD_Ratio'] >= t]
        count = len(filtered)
        if count == 0:
            results.append({'AD_Ratio': f">= {t:.1f}", 'Trades': 0, 'WinRate': 0, 'PF': 0})
            continue

        wins = len(filtered[filtered['Result'] == 'Win'])
        wr = wins / count * 100

        gp = filtered[filtered['Result'] == 'Win']['PnL'].sum()
        gl = abs(filtered[filtered['Result'] == 'Loss']['PnL'].sum())
        pf = gp / gl if gl > 0 else 999

        results.append({
            'AD_Ratio': f">= {t:.1f}",
            'Trades': count,
            'WinRate': wr,
            'PF': pf,
            'Total_Return': filtered['PnL'].sum()
        })

    df_results = pd.DataFrame(results)

    print("--- AD Ratio Replacement Grid Search Results (Sorted by PF) ---")
    print(df_results.sort_values('PF', ascending=False).to_string(index=False, float_format="%.2f"))

    print("\n--- AD Ratio Replacement Grid Search Results (Sorted by Win Rate) ---")
    print(df_results.sort_values('WinRate', ascending=False).to_string(index=False, float_format="%.2f"))

if __name__ == "__main__":
    analyze_ad_ratio_filter()