"""
run_bot.py - Start the live (or paper) trading bot.

BEFORE RUNNING:
  1. Copy .env.example to .env:
       cp .env.example .env

  2. Open .env and paste your Alpaca API credentials.
     Get free keys at: https://app.alpaca.markets
     (Paper Trading → Overview → API Keys)

  3. Confirm PAPER_TRADING=true in your .env file.
     This uses fake money — safe for testing.

  4. Run from the trading_bot/ directory:
       python scripts/run_bot.py

  5. Stop the bot anytime with Ctrl+C.
     It will close all positions before exiting.

GOING LIVE:
  Only change PAPER_TRADING=false after:
  - Running paper trades for at least 4–6 weeks
  - Achieving consistent results in backtests
  - Understanding the regulatory requirements in your country
"""
import sys
import os

# Ensure imports resolve from the trading_bot/ root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from config import settings
from src.bot import TradingBot
from src.strategies.ema_crossover import EMACrossoverStrategy
from src.strategies.rsi_vwap import RSIVWAPStrategy

# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  CONFIGURATION — edit these values                                          │
# └─────────────────────────────────────────────────────────────────────────────┘

# Choose one strategy (uncomment the one you want to use):
STRATEGY = EMACrossoverStrategy(short_period=9, long_period=21)
# STRATEGY = RSIVWAPStrategy()

# Symbols to trade. Set to None to use the default list in config/settings.py
SYMBOLS = None
# SYMBOLS = ["AAPL", "MSFT"]   # Uncomment to override

# ─────────────────────────────────────────────────────────────────────────────


def setup_logging():
    """Set up structured logging to both console and a rotating log file."""
    os.makedirs("logs", exist_ok=True)
    logger.add(
        settings.LOG_FILE,
        rotation="1 day",      # Create a new file each day
        retention="14 days",   # Keep two weeks of logs
        level=settings.LOG_LEVEL,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}",
        enqueue=True,          # Thread-safe logging
    )


def show_startup_banner(strategy_name: str) -> None:
    mode = "PAPER TRADING (fake money)" if settings.PAPER_TRADING else "LIVE TRADING (REAL MONEY)"
    symbols = SYMBOLS or settings.SYMBOLS
    print("\n" + "=" * 60)
    print("          AUTOMATED STOCK TRADING BOT")
    print("=" * 60)
    print(f"  Mode     : {mode}")
    print(f"  Strategy : {strategy_name}")
    print(f"  Symbols  : {symbols}")
    print(f"  Risk/trade: {settings.MAX_RISK_PER_TRADE * 100:.1f}% of account")
    print(f"  Stop-loss : {settings.STOP_LOSS_PCT * 100:.2f}%")
    print(f"  Take-profit: {settings.TAKE_PROFIT_PCT * 100:.2f}%")
    print(f"  Max positions: {settings.MAX_OPEN_POSITIONS}")
    print("=" * 60)


def confirm_live_trading() -> bool:
    """Require explicit confirmation before starting live trading."""
    print("\n" + "!" * 60)
    print("  WARNING: LIVE TRADING MODE IS ACTIVE")
    print("  Real money will be traded on your Alpaca account.")
    print("  You can lose money. Only proceed if you understand the risks.")
    print("!" * 60)
    answer = input("\nType 'CONFIRM' (all caps) to start, or press Enter to abort: ")
    return answer.strip() == "CONFIRM"


def main():
    setup_logging()
    strategy_name = type(STRATEGY).__name__
    show_startup_banner(strategy_name)

    # Extra confirmation gate for live trading
    if not settings.PAPER_TRADING:
        if not confirm_live_trading():
            print("Aborted. Set PAPER_TRADING=true in .env to run safely.")
            return

    logger.info(f"Starting bot | {strategy_name} | Paper: {settings.PAPER_TRADING}")

    bot = TradingBot(strategy=STRATEGY, symbols=SYMBOLS)
    bot.run()


if __name__ == "__main__":
    main()
