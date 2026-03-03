import pandas as pd
import numpy as np

def calculate_returns():
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

    # Parameters
    initial_capital = 1_000_000  # 1,000,000 JPY
    risk_per_trade = 0.02        # Risk 2% of total equity per trade on the stop loss

    # Simulation 1: Fixed Fractional Risk (Risking 2% of current account equity per trade)
    # The 'PnL' column is the percentage return of the entire position size.
    # We know the risk is 1:3.
    # If it's a Loss, they lose 1R. If it's a Win, they win 3R.
    # Therefore, if we risk 2% of the account, a Loss = -2% account growth.
    # A Win = +6% account growth.

    equity_curve_fixed_risk = [initial_capital]
    current_equity = initial_capital

    for idx, row in top_perf.iterrows():
        if row['Result'] == 'Win':
            # 3R win
            current_equity *= (1.0 + (risk_per_trade * 3.0))
        elif row['Result'] == 'Loss':
            # 1R loss
            current_equity *= (1.0 - risk_per_trade)

        equity_curve_fixed_risk.append(current_equity)

    final_equity_fixed_risk = equity_curve_fixed_risk[-1]

    # Simulation 2: Compounding the entire account per trade (All-In)
    # This assumes we put 100% of the account equity into the stock.
    # The 'PnL' column shows the exact percentage change of the stock from Entry to Exit.
    # E.g., if PnL is 15.0, the stock went up 15%.

    equity_curve_all_in = [initial_capital]
    current_equity_all = initial_capital

    for idx, row in top_perf.iterrows():
        pnl_decimal = row['PnL'] / 100.0
        current_equity_all *= (1.0 + pnl_decimal)
        equity_curve_all_in.append(current_equity_all)

    final_equity_all_in = equity_curve_all_in[-1]

    print(f"Total Trades: {len(top_perf)}")
    print(f"Period: {top_perf['Date'].min().date()} to {top_perf['Date'].max().date()}")
    print("\n--- Simulation 1: Fixed Fractional Risk (2% Risk per trade) ---")
    print("This is the professional standard. You size your position so that if it hits the Stop Loss, you only lose 2% of your total account.")
    print(f"Starting Capital: 1,000,000 JPY")
    print(f"Final Capital:    {final_equity_fixed_risk:,.0f} JPY")
    print(f"Total Return:     {((final_equity_fixed_risk / initial_capital) - 1.0) * 100:.2f}%")

    print("\n--- Simulation 2: Full Compounding (All-In per trade) ---")
    print("You invest the entire current account balance into every single trade. (High risk, assumes trades don't overlap in time).")
    print(f"Starting Capital: 1,000,000 JPY")
    print(f"Final Capital:    {final_equity_all_in:,.0f} JPY")
    print(f"Total Return:     {((final_equity_all_in / initial_capital) - 1.0) * 100:.2f}%")

if __name__ == "__main__":
    calculate_returns()