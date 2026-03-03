import pandas as pd
import numpy as np
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import os

pd.options.mode.chained_assignment = None

def get_tickers():
    if os.path.exists('backend/russell3000.csv'):
        df = pd.read_csv('backend/russell3000.csv', header=None)
        return df[0].tolist()
    return ['AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMZN']

def calc_rs_rating(df):
    if len(df) < 252:
        return pd.Series([50]*len(df), index=df.index)
    close = df['close']
    r63 = close.pct_change(63).fillna(0) * 100
    r126 = close.pct_change(126).fillna(0) * 100
    r189 = close.pct_change(189).fillna(0) * 100
    r252 = close.pct_change(252).fillna(0) * 100
    raw_rs = (r63 * 0.4) + (r126 * 0.2) + (r189 * 0.2) + (r252 * 0.2)
    return raw_rs.rolling(252).rank(pct=True) * 99

def calc_ad_rating(df):
    if len(df) < 65:
        return pd.Series([50]*len(df), index=df.index)
    close, high, low, vol = df['close'], df['high'], df['low'], df['volume']
    hl_diff = np.where(high - low == 0, 0.0001, high - low)
    mf_multiplier = ((close - low) - (high - close)) / hl_diff
    mf_volume = mf_multiplier * vol
    cmf = pd.Series(mf_volume).rolling(65).sum() / np.where(vol.rolling(65).sum() == 0, 1, vol.rolling(65).sum())
    return ((cmf + 1) / 2) * 100

def fetch_and_prep_data(ticker):
    try:
        df = yf.download(ticker, start='2015-01-01', end='2025-12-31', progress=False)
        if df.empty or len(df) < 260: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        if df['close'].iloc[-1] < 5: return None

        df['sma200'] = df['close'].rolling(200).mean()
        df['atr14'] = (df['high'] - df['low']).rolling(14).mean()
        df['rs_rating'] = calc_rs_rating(df)
        df['ad_rating'] = calc_ad_rating(df)

        df = df.dropna(subset=['sma200'])
        return df
    except Exception:
        return None

def analyze_ticker_vectorized(ticker):
    df = fetch_and_prep_data(ticker)
    if df is None: return []

    # Pre-calculate 20-day rolling values (shifted by 1 to represent "yesterday's view of the last 20 days")
    df['res_20d'] = df['high'].rolling(20).max().shift(1)
    df['low_20d'] = df['low'].rolling(20).min().shift(1)

    # VCP approximations (shifted 1)
    hl_range = (df['high'] - df['low']) / df['close']
    df['vcp_volatility'] = hl_range.rolling(10).mean().shift(1)
    df['vcp_tight'] = df['vcp_volatility'] < 0.08

    df['vol_sma50'] = df['volume'].rolling(50).mean().shift(1)
    df['vcp_dryup'] = df['volume'].shift(1) < df['vol_sma50']

    # FVG Approximation (shifted 1): any day in last 20 days where low > high[2 days ago] * 1.001
    fvg_mask = df['low'] > df['high'].shift(2) * 1.001
    df['has_fvg'] = fvg_mask.rolling(20).max().shift(1) > 0

    # Base Logic
    # Resistance is valid
    cond_res = df['res_20d'].notna() & (df['res_20d'] > 0)
    # Base is valid and not too deep (0.5% to 30%)
    cond_base = df['low_20d'].notna() & (df['res_20d'] > df['low_20d'] * 1.005) & (df['res_20d'] < df['low_20d'] * 1.30)

    # Breakout logic: Today's close > Resistance, but yesterday's close was <= Resistance
    # And we don't chase > 10%
    cond_breakout = (df['close'] > df['res_20d']) & (df['close'].shift(1) <= df['res_20d']) & (df['close'] <= df['res_20d'] * 1.10)

    # Combine conditions
    trigger_mask = cond_res & cond_base & cond_breakout

    breakout_dates = df.index[trigger_mask]

    trades = []

    # We still need a tiny loop over the actual triggers to simulate the trade future
    # But there should only be a handful per ticker

    last_exit_idx = 0

    for b_date in breakout_dates:
        idx = df.index.get_loc(b_date)

        # Avoid overlapping trades
        if idx <= last_exit_idx:
            continue

        b_bar = df.iloc[idx]

        ep = float(b_bar['close'])
        stop_loss = float(b_bar['low_20d']) * 0.98
        atr = float(b_bar['atr14'])

        risk = ep - stop_loss
        atr_risk = risk / atr if atr > 0 else 0
        tp = ep + (risk * 3.0) # 1:3 RR

        # Simulate forward
        future_df = df.iloc[idx+1:]
        if future_df.empty:
            continue

        # Vectorized check
        loss_mask = future_df['low'] <= stop_loss
        win_mask = future_df['high'] >= tp

        loss_idx = loss_mask.idxmax() if loss_mask.any() else None
        win_idx = win_mask.idxmax() if win_mask.any() else None

        result = 'Open'
        pnl = 0.0

        if loss_idx is not None and win_idx is not None:
            if loss_idx < win_idx:
                result = 'Loss'
                pnl = (stop_loss - ep)/ep*100
                last_exit_idx = df.index.get_loc(loss_idx)
            else:
                result = 'Win'
                pnl = (tp - ep)/ep*100
                last_exit_idx = df.index.get_loc(win_idx)
        elif loss_idx is not None:
            result = 'Loss'
            pnl = (stop_loss - ep)/ep*100
            last_exit_idx = df.index.get_loc(loss_idx)
        elif win_idx is not None:
            result = 'Win'
            pnl = (tp - ep)/ep*100
            last_exit_idx = df.index.get_loc(win_idx)
        else:
            # Still open at end of data
            last_exit_idx = len(df) - 1

        if result != 'Open':
            trades.append({
                'Ticker': ticker,
                'Date': b_date,
                'Result': result,
                'PnL': pnl,
                'RS_Rating': b_bar['rs_rating'],
                'AD_Rating': b_bar['ad_rating'],
                'VCP_Tight': b_bar['vcp_tight'],
                'VCP_DryUp': b_bar['vcp_dryup'],
                'ATR_Risk': atr_risk,
                'Has_FVG': bool(b_bar['has_fvg'])
            })

    return trades

def main():
    tickers = get_tickers()
    print(f"Running Vectorized Unified Backtest on {len(tickers)} tickers...")

    all_trades = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(analyze_ticker_vectorized, t): t for t in tickers}

        completed = 0
        for f in as_completed(futures):
            completed += 1
            try:
                res = f.result(timeout=120)
                if res:
                    all_trades.extend(res)
            except Exception as e:
                pass

            if completed % 50 == 0:
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
    ad_ranges = [50, 60, 70]
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