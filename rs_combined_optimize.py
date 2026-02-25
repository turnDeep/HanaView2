import os
import sys
import warnings
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

# Add the project root to sys.path to import backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath('.'))

try:
    from backend.hwb_scanner import HWBAnalyzer
except ImportError:
    # Fallback if running from a different directory
    sys.path.append('/app')
    from backend.hwb_scanner import HWBAnalyzer

warnings.filterwarnings('ignore')

def rs_score(series):
    if len(series) < 252: return np.nan
    c = series.iloc[-1]
    # Handle potential missing data by using what's available or the first item
    p63  = series.iloc[-64]  if len(series) > 63  else series.iloc[0]
    p126 = series.iloc[-127] if len(series) > 126 else series.iloc[0]
    p252 = series.iloc[-253] if len(series) > 252 else series.iloc[0]

    # Avoid division by zero
    if p63 == 0 or p126 == 0 or p252 == 0: return np.nan

    return 0.4*(c/p63-1) + 0.2*(c/p126-1) + 0.2*(c/p252-1)

def compute_rs_at_date(close_series, target_date, window=252):
    try:
        # Use get_indexer with method='ffill' to handle nearest date matching
        iloc_arr = close_series.index.get_indexer([target_date], method='ffill')
        idx = int(iloc_arr[0])

        if idx < 0 or idx < 252: return np.nan

        current_score = rs_score(close_series.iloc[:idx+1])
        if np.isnan(current_score): return np.nan

        # Calculate RS score for all trading days in the past year to determine percentile
        # Sampling every 5 days for speed optimization
        rolling_scores = []
        # Look back 252 trading days (approx 1 year)
        start_idx = max(252, idx - window)

        for i in range(start_idx, idx+1, 5):
            s = rs_score(close_series.iloc[:i+1])
            if not np.isnan(s): rolling_scores.append(s)

        if not rolling_scores: return np.nan

        # Percentile rank
        pct = np.sum(np.array(rolling_scores) < current_score) / len(rolling_scores) * 98 + 1
        return min(99, max(1, pct))
    except Exception as e:
        # print(f"RS error: {e}")
        return np.nan

def get_data(ticker):
    try:
        df = yf.download(ticker, start='2015-01-01', end='2025-12-01', progress=False, timeout=10)
        if df.empty or len(df) < 252: return None, None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]

        # Required columns
        if 'close' not in df.columns or 'high' not in df.columns or 'low' not in df.columns:
            return None, None

        df['sma200'] = df['close'].rolling(200).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        df['atr14']  = (df['high'] - df['low']).rolling(14).mean()

        dd = df.dropna(subset=['sma200','ema200']).copy()

        # Weekly data
        dw = df.resample('W-MON').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'})
        dw['sma200'] = dw['close'].rolling(200).mean()

        return dd, dw
    except Exception as e:
        print(f"Data fetch error for {ticker}: {e}")
        return None, None

def process_ticker(ticker, analyzer):
    dd, dw = get_data(ticker)
    if dd is None: return []

    trades = []
    # Using HWBAnalyzer logic
    try:
        setups = analyzer.optimized_rule2_setups(dd, dw, full_scan=True)
    except Exception as e:
        print(f"Setup scan error for {ticker}: {e}")
        return []

    for setup in setups:
        try:
            fvgs = analyzer.optimized_fvg_detection(dd, setup)
            for fvg in fvgs:
                si = dd.index.get_loc(setup['date'])
                fi = dd.index.get_loc(fvg['formation_date'])

                fl = float(fvg['lower_bound'])
                fu = float(fvg['upper_bound'])

                # Analyze breakout
                rh = -1.0
                # Look for highest high between setup and fvg
                # Note: fvg['formation_date'] is the 3rd candle of FVG.
                # Range is from setup date to FVG date.
                # Logic from hwb_scanner.py usually takes max high.

                # Check scanning range
                scan_start = si + 1
                scan_end = fi
                if scan_end <= scan_start:
                    # Fallback logic if dates are weird
                    scan_start = max(0, si - 10)
                    scan_end = si + 1

                rd = dd.iloc[scan_start:scan_end]
                if not rd.empty:
                    rh = float(rd['high'].max())
                else:
                    # If no intermediate candles, use setup high or fvg high
                    rh = float(max(dd.iloc[si]['high'], dd.iloc[fi]['high']))

                bo = None
                # Check for breakout in the next 60 days
                for i in range(fi + 1, min(fi + 61, len(dd))):
                    c = dd.iloc[i]
                    # Check invalidation: Close below FVG lower bound * 0.98 (Stop Loss violation before entry)
                    # Actually rule says: "FVG lower bound as support". If price drops below, setup invalidated.
                    if c['low'] < fl * 0.98:
                        break

                    # Breakout Trigger: Close > Resistance High * 1.001
                    if c['close'] > rh * 1.001:
                        bo = {'idx': i, 'date': dd.index[i], 'price': float(c['close'])}
                        break

                if not bo: continue

                # Trade parameters
                ed = bo['date']
                ep = bo['price']
                eb = dd.iloc[bo['idx']]

                sl = fl * 0.98
                if sl >= ep: continue # Should not happen if logic is correct

                risk = ep - sl
                tp = ep + risk * 2.0 # Standard 1:2 RR for stats

                # Factor Calculations
                rs_val = compute_rs_at_date(dd['close'], ed)
                atr_val = float(eb.get('atr14', 0))
                atr_risk = risk / atr_val if atr_val > 0 else 0
                fvg_gap = (fu - fl) / fl * 100
                bo_str = (ep / rh - 1) * 100
                days_fvg = (ed - fvg['formation_date']).days

                # Determine outcome
                outcome = 'Running'
                pnl_pct = 0.0
                ei = bo['idx']

                for j in range(ei + 1, len(dd)):
                    bar = dd.iloc[j]
                    if float(bar['low']) <= sl:
                        outcome = 'Loss'
                        pnl_pct = (sl - ep) / ep * 100
                        break
                    elif float(bar['high']) >= tp:
                        outcome = 'Win'
                        pnl_pct = (tp - ep) / ep * 100
                        break

                # If still running, calculate current PnL
                if outcome == 'Running':
                    current_price = dd.iloc[-1]['close']
                    pnl_pct = (current_price - ep) / ep * 100

                trades.append({
                    'Ticker': ticker,
                    'Entry': ed,
                    'Result': outcome,
                    'PnL%': pnl_pct,
                    'RS': rs_val,
                    'ATR_Risk': atr_risk,
                    'FVG_Gap': fvg_gap,
                    'BO_Strength': bo_str,
                    'DaysFVGBO': days_fvg
                })

        except Exception as e:
            # print(f"Trade logic error for {ticker}: {e}")
            continue

    return trades

def main():
    if not os.path.exists('all_tickers.csv'):
        print("all_tickers.csv not found.")
        return

    tickers_df = pd.read_csv('all_tickers.csv')
    tickers = tickers_df['Ticker'].tolist()

    analyzer = HWBAnalyzer()

    # Load previously processed tickers if exists
    processed_tickers = set()
    trades_file = 'rs_combined_trades.csv'

    if os.path.exists(trades_file):
        try:
            existing_df = pd.read_csv(trades_file)
            if not existing_df.empty and 'Ticker' in existing_df.columns:
                processed_tickers = set(existing_df['Ticker'].unique())
            print(f"Resuming scan. Already processed {len(processed_tickers)} tickers.")
        except:
            print("Error reading existing trades file. Starting fresh.")

    print(f"Starting scan for {len(tickers)} tickers...")

    batch_trades = []

    for i, ticker in enumerate(tickers):
        if ticker in processed_tickers:
            continue

        t_trades = process_ticker(ticker, analyzer)
        if t_trades:
            batch_trades.extend(t_trades)

        # Save every 10 tickers
        if (i + 1) % 10 == 0 or i == len(tickers) - 1:
            if batch_trades:
                batch_df = pd.DataFrame(batch_trades)
                # Append to file
                if not os.path.exists(trades_file):
                    batch_df.to_csv(trades_file, index=False)
                else:
                    batch_df.to_csv(trades_file, mode='a', header=False, index=False)

                batch_trades = [] # Clear buffer

            print(f"Processed {i + 1}/{len(tickers)} tickers.")

    # Final optimize
    print("Scan complete. Running optimization...")
    if os.path.exists(trades_file):
        df = pd.read_csv(trades_file)
        optimize(df)
    else:
        print("No trades collected.")

def optimize(df):
    if df.empty:
        print("No trades found.")
        return

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

    print("\nRunning Grid Search Optimization...")

    for rs_t in rs_thresholds:
        for fvg_t in fvg_thresholds:
            for bo_t in bo_thresholds:
                # Apply filters
                # Handle NaNs in RS by treating them as 0 (fail filter)
                mask = (df_closed['RS'].fillna(0) >= rs_t) & \
                       (df_closed['FVG_Gap'] >= fvg_t) & \
                       (df_closed['BO_Strength'] >= bo_t)

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

    # Write results to file
    with open('rs_combined_results.txt', 'w') as f:
        f.write("Optimization Results (Top 20 by PF)\n")
        f.write("="*80 + "\n")
        f.write(f"{'RS':<5} {'FVG':<5} {'BO':<5} {'Trades':<8} {'WinRate':<10} {'PF':<8} {'Return':<10}\n")
        f.write("-" * 80 + "\n")

        for r in results[:20]:
            f.write(f"{r['RS']:<5} {r['FVG']:<5.1f} {r['BO']:<5.1f} {r['Trades']:<8} {r['WinRate']:<10.1f} {r['PF']:<8.2f} {r['Return']:<10.1f}\n")

        f.write("\n")
        if best_params:
            f.write("Best Combination based on PF:\n")
            f.write(str(best_params))

    print(f"Optimization complete. Results saved to rs_combined_results.txt")

if __name__ == "__main__":
    main()
