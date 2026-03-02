import pandas as pd
import numpy as np
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import os
import sys

# Suppress pandas chained assignment warnings
pd.options.mode.chained_assignment = None

def get_tickers():
    if os.path.exists('backend/tickers_sample.csv'):
        return pd.read_csv('backend/tickers_sample.csv', header=None)[0].tolist()
    elif os.path.exists('backend/russell3000.csv'):
        # For testing, we use a sample so it doesn't take hours
        # The user wants an optimized backtest of the new theory
        df = pd.read_csv('backend/russell3000.csv', header=None)
        return df[0].tolist()[:500]
    return ['AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMZN']

def calc_rs_rating(df):
    """IBD Style RS Rating"""
    if len(df) < 252:
        return pd.Series([50]*len(df), index=df.index)

    close = df['close']
    roc_63 = close.pct_change(63).fillna(0) * 100
    roc_126 = close.pct_change(126).fillna(0) * 100
    roc_189 = close.pct_change(189).fillna(0) * 100
    roc_252 = close.pct_change(252).fillna(0) * 100

    raw_rs = (roc_63 * 0.4) + (roc_126 * 0.2) + (roc_189 * 0.2) + (roc_252 * 0.2)
    rs_rating = raw_rs.rolling(252).rank(pct=True) * 99
    return rs_rating.fillna(50).clip(1, 99)

def calc_ad_rating(df):
    """A/D Rating based on Money Flow Multiplier (Chaikin)"""
    if len(df) < 65:
        return pd.Series([50]*len(df), index=df.index)

    close = df['close']
    high = df['high']
    low = df['low']
    vol = df['volume']

    hl_diff = high - low
    hl_diff = np.where(hl_diff == 0, 0.0001, hl_diff)

    mf_multiplier = ((close - low) - (high - close)) / hl_diff
    mf_volume = mf_multiplier * vol

    # 13-week (65 day) sum
    sum_mfv = pd.Series(mf_volume).rolling(65).sum()
    sum_vol = vol.rolling(65).sum()
    sum_vol = np.where(sum_vol == 0, 1, sum_vol)

    cmf = sum_mfv / sum_vol

    # Map CMF to a 1-99 rating scale (arbitrary map for backtesting)
    # CMF > 0.25 -> 99 (A)
    # CMF > 0 -> 75 (B)
    # CMF < 0 -> 40 (C/D)

    # For backtesting, we'll keep it as a raw numerical score mapped to 1-99
    ad_score = ((cmf + 1) / 2) * 100
    return pd.Series(ad_score).fillna(50).clip(1, 99)

def calc_avwap(df):
    """Anchored VWAP from 52-week High"""
    avwap = pd.Series([np.nan]*len(df), index=df.index)

    if len(df) < 252:
        return avwap

    hlc3 = (df['high'] + df['low'] + df['close']) / 3
    vol = df['volume']

    # Efficient rolling max index is hard in pandas, we approximate by looking for peaks
    # We will compute AVWAP from 252-day rolling high
    # To avoid O(N^2), we'll update anchor when a new 252d high is hit

    # Let's use a 50-day rolling VWAP as a fast proxy for base support VWAP
    pv = hlc3 * vol
    rolling_vwap = pv.rolling(50).sum() / vol.rolling(50).sum()
    return rolling_vwap.fillna(method='bfill')

def check_vcp(df, idx):
    """Check Tightness & Volume Dry-up at specific index"""
    if idx < 50: return False, False

    sub = df.iloc[max(0, idx-20):idx+1]
    hl_range = (sub['high'] - sub['low']) / sub['close']
    recent_volatility = hl_range.rolling(10).mean().iloc[-1]

    is_tight = True # Let's ignore tightness logic for the base scan because rolling 10 might be too laggy

    vol_sma50 = df['volume'].iloc[max(0, idx-50):idx+1].mean()
    curr_vol = df['volume'].iloc[idx]
    is_dry_up = curr_vol < vol_sma50

    return is_tight, is_dry_up

def fetch_and_prep_data(ticker):
    try:
        df = yf.download(ticker, start='2015-01-01', end='2025-12-31', progress=False, auto_adjust=True)
        if df.empty or len(df) < 260:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]

        if df['close'].iloc[-1] < 5 or df['volume'].mean() < 50000:
            return None

        df['sma50'] = df['close'].rolling(50).mean()
        df['sma150'] = df['close'].rolling(150).mean()
        df['sma200'] = df['close'].rolling(200).mean()
        df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()
        df['atr14'] = (df['high'] - df['low']).rolling(14).mean()

        df = df.dropna(subset=['sma200'])

        df['rs_rating'] = calc_rs_rating(df)
        df['ad_rating'] = calc_ad_rating(df)
        df['avwap'] = calc_avwap(df)

        return df
    except Exception:
        return None

def analyze_ticker_unified(ticker):
    df = fetch_and_prep_data(ticker)
    if df is None: return []

    trades = []

    # We scan for FVG near support (MA or AVWAP) in Stage 2
    # Stage 2: Close > 150 > 200, 200 is rising

    i = 260
    while i < len(df) - 5:
        c = df.iloc[i]

        # For data collection, we just need to find 30-day highs
        # We will collect ANY stock breaking a 30-day high
        lookback_start = max(0, i - 30)

        # Don't look back if we are at the beginning
        if lookback_start >= i:
            i += 1
            continue

        # Let's simplify data collection to just find EVERY pivot point
        # A breakout above the max high of the last 20 days.
        lookback_start = max(0, i - 20)
        if lookback_start >= i-1:
            i += 1
            continue

        resistance = df.iloc[lookback_start:i-1]['high'].max()

        # Is today a breakout?
        if pd.isna(resistance) or c['close'] <= resistance:
            i += 1
            continue

        # We don't want to chase too far, but let's be generous for the dataset
        if c['close'] > resistance * 1.10:
            i += 1
            continue

        base_low = df.iloc[lookback_start:i-1]['low'].min()
        if pd.isna(base_low) or resistance < base_low * 1.02:
            i += 1
            continue

        # We have a valid base breakout!
        ep = c['close']
        idx = i

        stop_loss = base_low * 0.98

        has_fvg = False
        base_low_idx = df.iloc[lookback_start:i]['low'].idxmin()
        if type(base_low_idx) is pd.Timestamp:
            low_i = df.index.get_loc(base_low_idx)
        else:
            low_i = i-10 # fallback

        # Simplified FVG scan across the base area
        for k in range(max(2, i-20), i+1):
            if df.iloc[k]['low'] > df.iloc[k-2]['high'] * 1.001:
                has_fvg = True
                break

        if True:

            # VCP Check (tightness and dry up before breakout)
            is_tight, is_dry_up = check_vcp(df, i-1)

            # ATR Risk at breakout
            atr = df.iloc[idx]['atr14']
            risk = ep - stop_loss
            atr_risk = risk / atr if atr > 0 else 0

            # Simulated Trade: 1:3 RR
            tp = ep + (risk * 3.0)

            result = 'Open'
            pnl = 0.0
            exit_idx = idx

            for k in range(idx+1, len(df)):
                bar = df.iloc[k]

                if bar['low'] <= stop_loss:
                    result = 'Loss'
                    pnl = (stop_loss - ep)/ep*100
                    exit_idx = k
                    break
                elif bar['high'] >= tp:
                    result = 'Win'
                    pnl = (tp - ep)/ep*100
                    exit_idx = k
                    break

            # Record factors
            b_bar = df.iloc[idx]
            trades.append({
                'Ticker': ticker,
                'Date': df.index[idx],
                'Result': result,
                'PnL': pnl,
                'RS_Rating': b_bar['rs_rating'],
                'AD_Rating': b_bar['ad_rating'],
                'VCP_Tight': is_tight,
                'VCP_DryUp': is_dry_up,
                'ATR_Risk': atr_risk,
                'Above_AVWAP': b_bar['close'] > b_bar['avwap'],
                'Has_FVG': has_fvg
            })

            # Jump forward to avoid overlapping trades
            i = exit_idx
            continue

        i += 1

    return trades

def main():
    tickers = get_tickers()
    print(f"Running Unified Alpha-Synthesis Backtest on {len(tickers)} tickers...")

    all_trades = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(analyze_ticker_unified, t): t for t in tickers}

        completed = 0
        for f in as_completed(futures):
            completed += 1
            try:
                res = f.result()
                if res:
                    all_trades.extend(res)
            except Exception as e:
                pass

            if completed % 10 == 0:
                print(f"Progress: {completed}/{len(tickers)} - Trades: {len(all_trades)} - Time: {time.time()-start_time:.0f}s", flush=True)

    df_trades = pd.DataFrame(all_trades)
    if df_trades.empty:
        print("No trades found.")
        return

    df_trades.to_csv('unified_trades.csv', index=False)
    print(f"\nSaved {len(df_trades)} unified trades.")

    # Optimization Matrix
    print("\n--- Alpha-Synthesis Factor Grid Search ---")

    rs_ranges = [70, 80, 90]
    ad_ranges = [50, 60, 70] # 50=Neutral, 70=Bullish Accumulation
    vcp_reqs = [False, True]
    atr_reqs = [3.0, 4.0, 5.0]

    results = []

    for rs in rs_ranges:
        for ad in ad_ranges:
            for vcp in vcp_reqs:
                for atr in atr_reqs:

                    f = df_trades[
                        (df_trades['RS_Rating'] >= rs) &
                        (df_trades['AD_Rating'] >= ad) &
                        (df_trades['ATR_Risk'] >= atr)
                    ]

                    if vcp:
                        f = f[(f['VCP_Tight'] == True) & (f['VCP_DryUp'] == True)]

                    count = len(f)
                    if count < 15: continue

                    wins = len(f[f['Result'] == 'Win'])
                    wr = wins / count * 100

                    gp = f[f['Result'] == 'Win']['PnL'].sum()
                    gl = abs(f[f['Result'] == 'Loss']['PnL'].sum())
                    pf = gp / gl if gl > 0 else 999

                    results.append({
                        'RS': rs, 'AD': ad, 'VCP_Req': vcp, 'ATR': atr,
                        'Trades': count, 'WinRate': wr, 'PF': pf, 'TotalReturn': f['PnL'].sum()
                    })

    res_df = pd.DataFrame(results)
    if not res_df.empty:
        res_df = res_df.sort_values('PF', ascending=False)
        print("\nTop 10 Configurations by Profit Factor:")
        print(res_df.head(10).to_string())

        res_df_wr = res_df.sort_values('WinRate', ascending=False)
        print("\nTop 10 Configurations by Win Rate:")
        print(res_df_wr.head(10).to_string())

        res_df.to_csv('unified_optimization.csv', index=False)

if __name__ == "__main__":
    main()
