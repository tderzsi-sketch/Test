"""
settings.py - All bot configuration in one place.

Sensitive values (API keys) are read from a .env file so they are never
hard-coded into the source code. Everything else is tunable here.

Quick-start:
  1. Copy .env.example to .env
  2. Add your Alpaca API key and secret
  3. Keep PAPER_TRADING=true until you've validated your strategy
"""
import os
from dotenv import load_dotenv

# Load variables from .env file into the environment
load_dotenv()

# ── Alpaca API credentials ─────────────────────────────────────────────────────
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = os.getenv(
    "ALPACA_BASE_URL", "https://paper-api.alpaca.markets"
)
# True = paper (fake) money. False = real money. Always start with True!
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"

# ── Symbols to trade ───────────────────────────────────────────────────────────
# Add or remove ticker symbols here. The bot will trade all of them.
SYMBOLS = ["AAPL", "MSFT", "TSLA", "NVDA", "SPY"]

# ── Market schedule (US Eastern Time) ─────────────────────────────────────────
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0

# The bot closes all positions this many minutes BEFORE the 4pm close.
# This avoids accidental overnight holds (day traders must close same-day).
CLOSE_POSITIONS_MINUTES_BEFORE_CLOSE = 15

# How many seconds to wait between each full scan of all symbols
TRADE_INTERVAL_SECONDS = 60

# ── EMA Crossover strategy settings ───────────────────────────────────────────
EMA_SHORT_PERIOD = 9    # Fast EMA — reacts quickly to price changes
EMA_LONG_PERIOD = 21    # Slow EMA — shows the broader trend
RSI_PERIOD = 14         # Standard RSI window
RSI_OVERSOLD = 30       # RSI below this = oversold (potential buy zone)
RSI_OVERBOUGHT = 70     # RSI above this = overbought (potential sell zone)

# ── RSI + VWAP strategy settings ──────────────────────────────────────────────
VWAP_DEVIATION_THRESHOLD = 0.002  # 0.2% — how far from VWAP counts as a signal

# ── Risk management ────────────────────────────────────────────────────────────
MAX_RISK_PER_TRADE = 0.01     # Risk at most 1% of account balance per trade
STOP_LOSS_PCT = 0.005         # Exit at a loss if price drops 0.5% from entry
TAKE_PROFIT_PCT = 0.015       # Exit at a profit if price rises 1.5% from entry
                              # (3:1 reward-to-risk ratio)
MAX_OPEN_POSITIONS = 5        # Never hold more than 5 stocks simultaneously
MAX_DAILY_LOSS_PCT = 0.03     # Stop trading for the day after a 3% total loss

# ── Data settings ──────────────────────────────────────────────────────────────
HISTORICAL_PERIOD = "60d"    # Max lookback for indicator calculation
INTRADAY_INTERVAL = "5m"     # Candle size: "1m", "5m", "15m", "1h"
                             # Note: Yahoo Finance limits intraday to last 60 days

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = "logs/trading_bot.log"
