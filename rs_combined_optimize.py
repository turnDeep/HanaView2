import pandas as pd
import numpy as np
import yfinance as yf
import sys
import os
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# Add backend to path so we can import modules
sys.path.append(os.path.abspath('backend'))

try:
    from hwb_scanner import HWBAnalyzer
except ImportError:
    # If backend is not in path, try adding current directory
    sys.path.append(os.getcwd())
    from backend.hwb_scanner import HWBAnalyzer

# Suppress warnings
warnings.filterwarnings('ignore')

def calculate_rs_series(df):
    """
    Calculate RS Rating series using IBD formula (40-20-20-20) and rolling rank.
    """
    if len(df) < 252:
        return pd.Series([50] * len(df), index=df.index)

    close = df['close']

    # Calculate ROC for different periods
    r63 = close.pct_change(63) * 100
    r126 = close.pct_change(126) * 100
    r189 = close.pct_change(189) * 100
    r252 = close.pct_change(252) * 100

    # IBD Formula
    rs_score = 0.40 * r63 + 0.20 * r126 + 0.20 * r189 + 0.20 * r252

    # Rolling percentile rank (rank of current score vs past 252 scores)
    rs_rating = rs_score.rolling(window=252).rank(pct=True) * 99
    rs_rating = rs_rating.fillna(50)

    return rs_rating

def fetch_data(ticker):
    try:
        # Download only necessary columns to save memory
        df = yf.download(ticker, start='2015-01-01', end='2025-12-31', progress=False, auto_adjust=True)
        if df.empty:
            return None, None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df.columns = [c.lower() for c in df.columns]

        # Minimum liquidity filter (e.g. price > 5, volume > 100k)
        if df['close'].iloc[-1] < 5 or df['volume'].mean() < 50000:
             return None, None

        # Calculate MAs needed for HWB
        df['sma200'] = df['close'].rolling(window=200).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        df['atr14'] = (df['high'] - df['low']).rolling(window=14).mean()

        # Filter valid data
        df = df.dropna(subset=['sma200', 'ema200'])

        if len(df) < 252:
            return None, None

        # Weekly data for trend filter
        df_weekly = df.resample('W-MON').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        })
        df_weekly['sma200'] = df_weekly['close'].rolling(window=200).mean()

        return df, df_weekly
    except Exception as e:
        return None, None

def analyze_ticker(ticker, analyzer):
    df, df_weekly = fetch_data(ticker)
    if df is None:
        return []

    # Calculate RS Series
    rs_series = calculate_rs_series(df)

    trades = []

    # Run HWB Scan
    try:
        setups = analyzer.optimized_rule2_setups(df, df_weekly, full_scan=True)

        for setup in setups:
            fvgs = analyzer.optimized_fvg_detection(df, setup)

            for fvg in fvgs:
                # Find Breakout
                formation_idx = df.index.get_indexer([fvg['formation_date']], method='nearest')[0]
                fvg_lower = float(fvg['lower_bound'])
                fvg_upper = float(fvg['upper_bound'])

                # Setup start to formation
                setup_start_idx = df.index.get_indexer([setup['date']], method='nearest')[0]

                # Logic for resistance
                start_lookback = setup_start_idx
                end_lookback = formation_idx

                # Ensure valid range
                if end_lookback <= start_lookback:
                     start_lookback = max(0, formation_idx - 20)

                if start_lookback >= end_lookback: # Should not happen if data valid
                     continue

                period_slice = df.iloc[start_lookback:end_lookback+1]
                if period_slice.empty:
                    continue

                resistance_high = float(period_slice['high'].max())

                breakout = None
                stop_loss = fvg_lower * 0.98

                # Look for breakout in next 60 days
                for i in range(formation_idx + 1, min(formation_idx + 60, len(df))):
                    bar = df.iloc[i]
                    current_close = float(bar['close'])
                    current_low = float(bar['low'])

                    if current_low < stop_loss:
                        break # Setup invalidated

                    if current_close > resistance_high * 1.001:
                        breakout = {
                            'date': df.index[i],
                            'price': current_close,
                            'index': i
                        }
                        break

                if breakout:
                    entry_date = breakout['date']
                    entry_price = breakout['price']
                    entry_idx = breakout['index']

                    # Calculate Trade Result
                    result = 'Open'
                    pnl_pct = 0.0
                    exit_date = df.index[-1]

                    risk = entry_price - stop_loss
                    take_profit = entry_price + risk * 2.0 # 1:2 RR

                    for j in range(entry_idx + 1, len(df)):
                        bar = df.iloc[j]
                        curr_low = float(bar['low'])
                        curr_high = float(bar['high'])

                        if curr_low <= stop_loss:
                            result = 'Loss'
                            pnl_pct = (stop_loss - entry_price) / entry_price * 100
                            exit_date = df.index[j]
                            break
                        elif curr_high >= take_profit:
                            result = 'Win'
                            pnl_pct = (take_profit - entry_price) / entry_price * 100
                            exit_date = df.index[j]
                            break

                    # Calculate Factors at Breakout
                    try:
                        rs_val = rs_series.loc[entry_date]
                    except KeyError:
                        # Fallback if exact date missing
                        rs_val = rs_series.asof(entry_date)
                        if pd.isna(rs_val): rs_val = 50

                    fvg_gap_pct = (fvg_upper - fvg_lower) / fvg_lower * 100
                    bo_strength_pct = (entry_price / resistance_high - 1) * 100

                    atr = float(df.iloc[entry_idx]['atr14'])
                    atr_risk = risk / atr if atr > 0 else 0

                    trades.append({
                        'Ticker': ticker,
                        'Entry Date': entry_date,
                        'Exit Date': exit_date,
                        'Result': result,
                        'PnL%': pnl_pct,
                        'RS Rating': rs_val,
                        'FVG_Gap%': fvg_gap_pct,
                        'BO_Strength%': bo_strength_pct,
                        'ATR_Risk': atr_risk
                    })

    except Exception as e:
        # print(f"Error analyzing {ticker}: {e}")
        return []

    return trades

def main():
    print("Script started.", flush=True)
    start_time = time.time()
    try:
        if os.path.exists('backend/tickers_sample.csv'):
            tickers_df = pd.read_csv('backend/tickers_sample.csv', header=None)
            tickers = tickers_df[0].tolist()
        elif os.path.exists('backend/russell3000.csv'):
            tickers_df = pd.read_csv('backend/russell3000.csv', header=None)
            tickers = tickers_df[0].tolist()
        else:
            print("Russell 3000 file not found, using sample.", flush=True)
            tickers = ['AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMZN', 'META', 'GOOGL', 'AMD', 'NFLX', 'SPY']
    except Exception:
        tickers = ['AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMZN']

    print(f"Loaded {len(tickers)} tickers. Starting parallel analysis...", flush=True)

    analyzer = HWBAnalyzer()
    all_trades = []

    # Use max_workers=10 for network IO bound tasks (yfinance)
    # Be careful not to rate limit myself
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_ticker = {executor.submit(analyze_ticker, ticker, analyzer): ticker for ticker in tickers}

        completed = 0
        total = len(tickers)

        for future in as_completed(future_to_ticker):
            completed += 1
            ticker = future_to_ticker[future]
            try:
                trades = future.result()
                if trades:
                    all_trades.extend(trades)
            except Exception as e:
                print(f"Ticker {ticker} generated an exception: {e}", flush=True)

            if completed % 10 == 0:
                print(f"Progress: {completed}/{total} ({len(all_trades)} trades found) - Time: {time.time()-start_time:.0f}s", flush=True)

    # Save trades
    trades_df = pd.DataFrame(all_trades)
    if not trades_df.empty:
        trades_df.to_csv('rs_combined_trades.csv', index=False)
        print(f"\nSaved {len(trades_df)} trades to rs_combined_trades.csv")

        # Optimization
        print("\nStarting Optimization Grid Search...")

        # Ranges
        rs_range = [70, 80, 85, 90, 95]
        fvg_range = [0.5, 1.0, 1.5, 2.0]
        bo_range = [0.5, 1.0, 1.5, 2.0]

        best_pf = 0
        best_combo = None
        results = []

        for rs in rs_range:
            for fvg in fvg_range:
                for bo in bo_range:
                    filtered = trades_df[
                        (trades_df['RS Rating'] >= rs) &
                        (trades_df['FVG_Gap%'] >= fvg) &
                        (trades_df['BO_Strength%'] >= bo)
                    ]

                    count = len(filtered)
                    if count < 20: continue # Minimum samples

                    wins = len(filtered[filtered['Result'] == 'Win'])
                    win_rate = wins / count * 100

                    gross_profit = filtered[filtered['Result'] == 'Win']['PnL%'].sum()
                    gross_loss = abs(filtered[filtered['Result'] == 'Loss']['PnL%'].sum())
                    pf = gross_profit / gross_loss if gross_loss > 0 else 999

                    results.append({
                        'RS': rs, 'FVG': fvg, 'BO': bo,
                        'Count': count, 'WinRate': win_rate, 'PF': pf,
                        'Return': filtered['PnL%'].sum()
                    })

        res_df = pd.DataFrame(results)
        if not res_df.empty:
            res_df = res_df.sort_values('PF', ascending=False)
            print("\nTop 10 Configurations:")
            print(res_df.head(10).to_string())
            res_df.to_csv('rs_optimization_results.csv', index=False)
        else:
            print("No configurations met minimum trade count.")
    else:
        print("No trades found.")

if __name__ == "__main__":
    main()
