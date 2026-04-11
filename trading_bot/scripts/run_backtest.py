"""
run_backtest.py - Test a strategy on historical data before live trading.

HOW TO USE:
  1. Edit the configuration section below (symbol, strategy, capital).
  2. Run from the trading_bot/ directory:
       python scripts/run_backtest.py
  3. Review the printed metrics and the saved chart in logs/.

The backtest does NOT require an Alpaca account — it uses only
Yahoo Finance data (free, no API key needed).
"""
import sys
import os

# Add the trading_bot/ directory to the Python path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from src.data.market_data import MarketDataFetcher
from src.strategies.ema_crossover import EMACrossoverStrategy
from src.strategies.rsi_vwap import RSIVWAPStrategy
from src.backtest.backtester import Backtester

# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  CONFIGURATION — edit these values                                          │
# └─────────────────────────────────────────────────────────────────────────────┘

SYMBOL = "AAPL"           # Ticker to backtest, e.g. "AAPL", "MSFT", "SPY"

# Bar interval. Intraday options: "1m", "5m", "15m", "1h"
# Note: Yahoo Finance only provides intraday data for the last 60 days.
# For longer backtests use "1d" (daily bars) and a longer period.
INTERVAL = "5m"

# How far back to look. Use "5d", "30d", "60d" for intraday.
# Use "1y", "2y" for daily ("1d") interval backtests.
PERIOD = "30d"

INITIAL_CAPITAL = 10_000  # Starting portfolio value in USD

# Which strategy to test. Change this to RSIVWAPStrategy() to try the other one.
STRATEGY = EMACrossoverStrategy(short_period=9, long_period=21)
# STRATEGY = RSIVWAPStrategy()

# ─────────────────────────────────────────────────────────────────────────────


def main():
    strategy_name = type(STRATEGY).__name__
    logger.info(
        f"Starting backtest | Symbol: {SYMBOL} | Strategy: {strategy_name} | "
        f"Interval: {INTERVAL} | Period: {PERIOD} | Capital: ${INITIAL_CAPITAL:,}"
    )

    # 1. Download historical price data
    fetcher = MarketDataFetcher()
    data = fetcher.get_historical_data(SYMBOL, interval=INTERVAL, period=PERIOD)

    if data.empty:
        print(
            f"\nERROR: No data returned for '{SYMBOL}'. "
            "Check the symbol and try a shorter period."
        )
        return

    print(f"\nLoaded {len(data)} bars: {data.index[0].date()} → {data.index[-1].date()}")

    # 2. Run the backtest
    bt = Backtester(
        initial_capital=INITIAL_CAPITAL,
        stop_loss_pct=0.005,    # 0.5% stop-loss
        take_profit_pct=0.015,  # 1.5% take-profit
    )
    results = bt.run(STRATEGY, data)

    if not results.get("metrics"):
        print("Backtest produced no results — try a longer period or different symbol.")
        return

    # 3. Print summary table
    bt.print_summary(results)

    # 4. Show trade log (last 15 trades)
    trades = results.get("trades", None)
    if trades is not None and not trades.empty:
        print("Trade Log (most recent 15):")
        print("-" * 75)
        display_cols = ["exit_type", "entry_price", "exit_price", "shares", "pnl", "timestamp"]
        available = [c for c in display_cols if c in trades.columns]
        print(trades[available].tail(15).to_string(index=False))
        print()

    # 5. Save equity chart
    os.makedirs("logs", exist_ok=True)
    chart_path = f"logs/{SYMBOL}_{strategy_name}_{INTERVAL}.png"
    bt.plot_results(
        results,
        title=f"{SYMBOL} — {strategy_name} ({INTERVAL} bars, {PERIOD})",
        save_path=chart_path,
    )
    print(f"Chart saved → {chart_path}")
    print("\nTip: Edit SYMBOL, STRATEGY, INTERVAL, or PERIOD above to try different settings.")


if __name__ == "__main__":
    main()
