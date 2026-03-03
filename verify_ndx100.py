import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup
import requests

def analyze_ndx100():
    # Attempt to fetch current NDX 100 tickers (or use a representative static list for backtest)
    # Wikipedia is reliable for this
    print("Fetching current NASDAQ 100 tickers...")
    try:
        url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
        html = requests.get(url).text
        soup = BeautifulSoup(html, 'html.parser')
        table = soup.find('table', {'id': 'constituents'})
        df_ndx = pd.read_html(str(table))[0]
        ndx_tickers = df_ndx['Ticker'].tolist()
    except Exception as e:
        print(f"Error fetching NDX 100: {e}")
        # Fallback to a major representative static list if wikipedia fails
        ndx_tickers = ['AAPL', 'MSFT', 'AMZN', 'NVDA', 'META', 'GOOGL', 'GOOG', 'TSLA', 'AVGO', 'PEP', 'COST', 'CSCO', 'TMUS', 'NFLX', 'CMCSA', 'ADBE', 'AMD', 'TXN', 'INTC', 'HON', 'QCOM', 'AMGN', 'INTU', 'SBUX', 'ISRG', 'AMAT', 'MDLZ', 'BKNG', 'GILD', 'ADP', 'ADI', 'VRTX', 'REGN', 'PANW', 'MU', 'LRCX', 'CSX', 'PYPL', 'MELI', 'KLAC', 'SNPS', 'CDNS', 'MAR', 'ASML', 'ORLY', 'CTAS', 'CHTR', 'FTNT', 'ABNB', 'NXPI', 'MNST', 'PCAR', 'LULU', 'WDAY', 'DXCM', 'KDP', 'KHC', 'PAYX', 'ROST', 'MRVL', 'AEP', 'IDXX', 'EXC', 'FAST', 'EA', 'CTSH', 'ODFL', 'BIIB', 'VRSK', 'CEG', 'WBA', 'CSGP', 'BKR', 'ON', 'DDOG', 'GEHC', 'TTD', 'FANG', 'CRWD', 'DLTR', 'MCHP', 'WBD', 'EBAY', 'ILMN', 'SIRI', 'GFS', 'TEAM', 'ROKU', 'ZM', 'DOCU', 'OKTA', 'CRWD', 'DDOG', 'SPLK', 'LCID', 'RIVN']

    print(f"Found {len(ndx_tickers)} NDX 100 tickers.")

    # Load all trades from the full Russell 3000 backtest
    trades = pd.read_csv('unified_trades.csv')
    trades = trades[trades['Result'] != 'Open'].copy()

    # Filter for NDX 100
    ndx_trades = trades[trades['Ticker'].isin(ndx_tickers)].copy()
    print(f"\nTotal NDX 100 Breakout Trades over 10 years: {len(ndx_trades)}")

    # ----------------------------------------------------
    # Baseline Output (RS >= 90, AD >= 60, ATR >= 3.0)
    # ----------------------------------------------------
    top_perf = ndx_trades[
        (ndx_trades['RS_Rating'] >= 90) &
        (ndx_trades['AD_Rating'] >= 60) &
        (ndx_trades['ATR_Risk'] >= 3.0)
    ]

    b_wins = len(top_perf[top_perf['Result'] == 'Win'])
    b_losses = len(top_perf) - b_wins
    b_wr = b_wins / len(top_perf) * 100 if len(top_perf) > 0 else 0
    b_gp = top_perf[top_perf['Result'] == 'Win']['PnL'].sum()
    b_gl = abs(top_perf[top_perf['Result'] == 'Loss']['PnL'].sum())
    b_pf = b_gp / b_gl if b_gl > 0 else 999

    print(f"\n--- NASDAQ 100 Only (RS>=90, AD>=60, ATR>=3.0) ---")
    print(f"Trades:   {len(top_perf)}")
    print(f"Win Rate: {b_wr:.2f}% ({b_wins} Wins / {b_losses} Losses)")
    print(f"PF:       {b_pf:.2f}")

    # What if we apply the Russell 3000 optimized ATR (ATR >= 4.0)?
    top_perf_4 = ndx_trades[
        (ndx_trades['RS_Rating'] >= 90) &
        (ndx_trades['AD_Rating'] >= 60) &
        (ndx_trades['ATR_Risk'] >= 4.0)
    ]

    b_wins4 = len(top_perf_4[top_perf_4['Result'] == 'Win'])
    b_losses4 = len(top_perf_4) - b_wins4
    b_wr4 = b_wins4 / len(top_perf_4) * 100 if len(top_perf_4) > 0 else 0
    b_gp4 = top_perf_4[top_perf_4['Result'] == 'Win']['PnL'].sum()
    b_gl4 = abs(top_perf_4[top_perf_4['Result'] == 'Loss']['PnL'].sum())
    b_pf4 = b_gp4 / b_gl4 if b_gl4 > 0 else 999

    print(f"\n--- NASDAQ 100 Only (RS>=90, AD>=60, ATR>=4.0) ---")
    print(f"Trades:   {len(top_perf_4)}")
    print(f"Win Rate: {b_wr4:.2f}% ({b_wins4} Wins / {b_losses4} Losses)")
    print(f"PF:       {b_pf4:.2f}")

if __name__ == "__main__":
    analyze_ndx100()