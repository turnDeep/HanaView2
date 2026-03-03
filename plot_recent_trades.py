import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

def plot_recent_trades():
    # Load baseline trades
    trades = pd.read_csv('unified_trades.csv')
    trades = trades[trades['Result'] != 'Open'].copy()

    # Filter for Top Performance
    top_perf = trades[
        (trades['RS_Rating'] >= 90) &
        (trades['AD_Rating'] >= 60) &
        (trades['ATR_Risk'] >= 3.0)
    ].copy()

    # Sort by Date chronologically
    top_perf['Date'] = pd.to_datetime(top_perf['Date'])
    top_perf = top_perf.sort_values('Date').reset_index(drop=True)

    # Get the 5 most recent trades
    recent_trades = top_perf.tail(5)

    print("Generating charts for the 5 most recent top performance trades...")

    for i, row in recent_trades.iterrows():
        ticker = row['Ticker']
        entry_date = row['Date']
        result = row['Result']
        pnl = row['PnL']

        # We need data around the trade. Let's get 60 days before and 30 days after
        start_date = entry_date - pd.Timedelta(days=60)
        end_date = entry_date + pd.Timedelta(days=60)

        # Download data
        try:
            df = yf.download(ticker, start=start_date, end=end_date, progress=False)
            if df.empty:
                print(f"No data for {ticker}")
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.columns = [c.lower() for c in df.columns]

            # Recalculate the 20d High/Low manually for the chart
            df['res_20d'] = df['high'].rolling(20).max().shift(1)
            df['low_20d'] = df['low'].rolling(20).min().shift(1)

            # Ensure the entry date exists in the dataframe, or get the closest next day
            # (sometimes yfinance index might not perfectly match the localized date string)
            if entry_date.tz is not None and df.index.tz is None:
                entry_date_naive = entry_date.tz_localize(None)
            else:
                entry_date_naive = entry_date

            entry_idx = df.index.get_indexer([entry_date_naive], method='bfill')[0]

            if entry_idx == -1 or entry_idx >= len(df):
                print(f"Could not align index for {ticker}")
                continue

            # Extract entry metrics
            b_bar = df.iloc[entry_idx]
            ep = float(b_bar['close'])
            stop_loss = float(b_bar['low_20d']) * 0.98
            atr14 = (df['high'] - df['low']).rolling(14).mean().iloc[entry_idx]
            risk = ep - stop_loss
            tp = ep + (risk * 3.0)

            # Set up the plot (Candlesticks + Volume)
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={'height_ratios': [3, 1]})

            # Colors for candles
            colors = np.where(df['close'] >= df['open'], 'g', 'r')

            # Plot candles
            for idx_c in range(len(df)):
                d = df.index[idx_c]
                o = df['open'].iloc[idx_c]
                h = df['high'].iloc[idx_c]
                l = df['low'].iloc[idx_c]
                c = df['close'].iloc[idx_c]
                color = colors[idx_c]

                ax1.plot([d, d], [l, h], color=color, linewidth=1.5)
                ax1.plot([d, d], [o, c], color=color, linewidth=4)

            # Plot 20-day resistance (the breakout level)
            ax1.plot(df.index, df['res_20d'], color='blue', linestyle='--', alpha=0.6, label='20d Resistance (Breakout Level)')

            # Plot Entry, Stop Loss, and Take Profit lines starting from entry date
            entry_x = df.index[entry_idx]
            ax1.axhline(y=ep, color='purple', linestyle='-', linewidth=1.5, xmin=0.5, label=f'Entry ({ep:.2f})')
            ax1.axhline(y=stop_loss, color='red', linestyle='-.', linewidth=1.5, xmin=0.5, label=f'Stop Loss (-1R: {stop_loss:.2f})')
            ax1.axhline(y=tp, color='green', linestyle='-.', linewidth=1.5, xmin=0.5, label=f'Take Profit (+3R: {tp:.2f})')

            # Mark the specific entry point with a marker
            ax1.scatter(entry_x, ep, color='gold', edgecolor='black', s=150, zorder=5, marker='*', label='Buy Trigger')

            # Format main chart
            title_str = f"{ticker} - HWB Breakout | {entry_date.strftime('%Y-%m-%d')} | Result: {result} ({pnl:+.1f}%)"
            ax1.set_title(title_str, fontsize=14, fontweight='bold')
            ax1.set_ylabel('Price')
            ax1.grid(True, alpha=0.3)
            ax1.legend(loc='upper left')

            # Format x-axis dates
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))

            # Plot Volume
            ax2.bar(df.index, df['volume'], color=colors, alpha=0.7)

            # Plot 50-day volume SMA
            vol_sma = df['volume'].rolling(50).mean()
            ax2.plot(df.index, vol_sma, color='orange', linestyle='-', linewidth=1.5, label='50d Vol SMA')

            ax2.set_ylabel('Volume')
            ax2.grid(True, alpha=0.3)
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
            ax2.legend(loc='upper left')

            plt.xticks(rotation=45)
            plt.tight_layout()

            file_name = f"chart_{ticker}_{entry_date.strftime('%Y%m%d')}.png"
            plt.savefig(file_name)
            plt.close()
            print(f"Generated chart: {file_name}")

        except Exception as e:
            print(f"Error plotting {ticker}: {e}")

if __name__ == "__main__":
    plot_recent_trades()