# Automated Stock Trading Bot

A beginner-friendly, fully commented Python trading bot for US intraday stock
trading via the [Alpaca](https://alpaca.markets) brokerage API.

> **Disclaimer**: This project is for educational purposes only. Trading involves
> real financial risk. Never trade with money you cannot afford to lose. Past
> backtest results do not guarantee future performance.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Market Data Retrieval](#2-market-data-retrieval)
3. [Trading Strategies](#3-trading-strategies)
4. [Risk Management](#4-risk-management)
5. [Order Execution](#5-order-execution)
6. [Backtesting](#6-backtesting)
7. [Live Deployment](#7-live-deployment)
8. [Security Best Practices](#8-security-best-practices)
9. [Regulatory Considerations](#9-regulatory-considerations)
10. [Quick-Start](#10-quick-start)
11. [Project Structure](#11-project-structure)
12. [Resources and Further Reading](#12-resources-and-further-reading)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        TradingBot (bot.py)                      │
│                                                                 │
│   ┌──────────────┐   ┌─────────────┐   ┌──────────────────┐   │
│   │ MarketData   │──▶│  Strategy   │──▶│   RiskManager    │   │
│   │  Fetcher     │   │ (EMA/VWAP)  │   │ (sizing, limits) │   │
│   └──────────────┘   └─────────────┘   └──────────────────┘   │
│         │                                        │              │
│   Yahoo Finance                        ┌─────────▼────────┐    │
│   (historical)                         │  OrderManager    │    │
│                                        │  (Alpaca API)    │    │
│                                        └──────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### Components

| Component | File | Responsibility |
|---|---|---|
| `TradingBot` | `src/bot.py` | Main loop, market-hours logic, orchestration |
| `MarketDataFetcher` | `src/data/market_data.py` | Download OHLCV data from Yahoo Finance |
| `EMACrossoverStrategy` | `src/strategies/ema_crossover.py` | EMA9/21 crossover with RSI filter |
| `RSIVWAPStrategy` | `src/strategies/rsi_vwap.py` | RSI + VWAP mean-reversion |
| `RiskManager` | `src/risk/risk_manager.py` | Position sizing, stop-loss, daily limits |
| `OrderManager` | `src/execution/order_manager.py` | Place/cancel orders via Alpaca |
| `Backtester` | `src/backtest/backtester.py` | Simulate strategy on historical data |

### Technology Stack

| Purpose | Library | Why |
|---|---|---|
| Broker API | `alpaca-py` | Free paper trading, zero commission, excellent API |
| Market data | `yfinance` | Free Yahoo Finance wrapper, no API key needed |
| Data processing | `pandas`, `numpy` | Industry-standard tabular data tools |
| Technical indicators | `pandas-ta` | 150+ indicators, native pandas integration |
| Charting | `matplotlib` | Plot equity curves and trades |
| Config management | `python-dotenv` | Load API keys from `.env` securely |
| Logging | `loguru` | Drop-in structured logging with rotation |

---

## 2. Market Data Retrieval

Price data is retrieved from **Yahoo Finance** using `yfinance`. No API key
is required. The `MarketDataFetcher` class wraps all data access:

```python
from src.data.market_data import MarketDataFetcher

fetcher = MarketDataFetcher()

# OHLCV data — 5-minute bars, last 5 days
data = fetcher.get_historical_data("AAPL", interval="5m", period="5d")
print(data.tail())
#                            Open    High     Low   Close     Volume
# 2024-06-03 15:55:00-04:00  192.5  192.8  192.4  192.6  1234567

# Current price snapshot
price = fetcher.get_current_price("AAPL")  # e.g. 192.60

# Multiple symbols at once
basket = fetcher.get_multiple_symbols_data(["AAPL", "MSFT", "TSLA"])
```

### Supported Intervals

| Interval | Description | Max lookback |
|---|---|---|
| `1m` | 1-minute bars | 7 days |
| `5m` | 5-minute bars | 60 days |
| `15m` | 15-minute bars | 60 days |
| `1h` | Hourly bars | 730 days |
| `1d` | Daily bars | Unlimited |

> **Tip**: For backtests longer than 60 days, use `interval="1d"` (daily bars)
> with `period="2y"` or longer.

---

## 3. Trading Strategies

All strategies inherit from `BaseStrategy` and must implement `generate_signals()`,
which returns the input DataFrame extended with a `signal` column containing:
- `BUY` (1) — open a long position
- `SELL` (-1) — close an existing position  
- `HOLD` (0) — do nothing

### Strategy 1 — EMA Crossover (`ema_crossover.py`)

**Concept**: A trend-following strategy. When a fast (9-period) EMA crosses
above a slow (21-period) EMA, momentum is building upward → BUY. When it
crosses below → SELL. An RSI filter avoids buying into already-overbought
conditions.

**Best for**: Trending markets with clear directional moves.

**Weakness**: Produces many false signals in choppy, sideways markets.

```python
from src.strategies.ema_crossover import EMACrossoverStrategy

strategy = EMACrossoverStrategy(short_period=9, long_period=21)
signals = strategy.generate_signals(data)
# New columns: ema_short, ema_long, rsi, signal
```

**Signal logic**:
```
BUY  when EMA(9) crosses above EMA(21)  AND  RSI < 70
SELL when EMA(9) crosses below EMA(21)  AND  RSI > 30
HOLD otherwise
```

### Strategy 2 — RSI + VWAP (`rsi_vwap.py`)

**Concept**: A mean-reversion strategy. RSI below 30 means a stock is oversold
(potential bounce). VWAP (Volume-Weighted Average Price) acts as intraday
support. Buying when RSI is oversold AND price is still above VWAP filters
out weak setups.

**Best for**: Stocks with clear intraday patterns and high volume.

**Weakness**: Can suffer in strong trending markets where RSI stays extreme.

```python
from src.strategies.rsi_vwap import RSIVWAPStrategy

strategy = RSIVWAPStrategy(rsi_period=14, rsi_oversold=30, rsi_overbought=70)
signals = strategy.generate_signals(data)
# New columns: rsi, vwap, signal
```

**Signal logic**:
```
BUY  when RSI < 30  AND  Close >= VWAP   (oversold + bullish context)
SELL when RSI > 70  AND  Close < VWAP    (overbought + bearish context)
HOLD otherwise
```

### Adding Your Own Strategy

```python
# src/strategies/my_strategy.py
from src.strategies.base_strategy import BaseStrategy, BUY, SELL, HOLD
import pandas as pd

class MyStrategy(BaseStrategy):
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        # ... your logic here ...
        df["signal"] = HOLD  # Fill with BUY/SELL/HOLD
        return df
```

---

## 4. Risk Management

Risk management is the most critical component. The `RiskManager` enforces
four rules:

### Rule 1 — Fixed Fractional Position Sizing

Never risk more than **1% of your account** on any single trade.

```
dollar_risk    = account_balance × 0.01       # e.g. $100 on a $10,000 account
risk_per_share = |entry_price − stop_loss|    # e.g. $0.75
shares         = dollar_risk / risk_per_share  # e.g. 133 shares
```

```python
from src.risk.risk_manager import RiskManager

rm = RiskManager(account_balance=10_000)
shares = rm.calculate_position_size(entry_price=150.0, stop_loss_price=149.25)
# → 133 shares
```

### Rule 2 — Stop-Loss (0.5% default)

Every trade exits automatically at a loss if price drops 0.5% from entry.
This is enforced via Alpaca bracket orders (the exchange manages it — even
if the bot goes offline your protection remains).

```python
stop = rm.calculate_stop_loss(entry_price=150.0, side="buy")   # → $149.25
```

### Rule 3 — Take-Profit (1.5% default)

Target 1.5% gain per trade, giving a **3:1 reward-to-risk ratio**. You only
need a ~25% win rate to be profitable with this ratio.

```python
target = rm.calculate_take_profit(entry_price=150.0, side="buy")  # → $152.25
```

### Rule 4 — Daily Loss Limit (3%)

If cumulative daily losses exceed 3% of the starting balance, the bot stops
opening new positions for the rest of the day.

```python
if rm.is_daily_loss_limit_hit():
    # bot pauses new entries
```

### Risk Parameters (in `config/settings.py`)

| Parameter | Default | Description |
|---|---|---|
| `MAX_RISK_PER_TRADE` | `0.01` | 1% of account risked per trade |
| `STOP_LOSS_PCT` | `0.005` | 0.5% stop-loss distance |
| `TAKE_PROFIT_PCT` | `0.015` | 1.5% take-profit distance |
| `MAX_OPEN_POSITIONS` | `5` | Maximum concurrent positions |
| `MAX_DAILY_LOSS_PCT` | `0.03` | 3% daily loss halt |

---

## 5. Order Execution

Orders are placed via the **Alpaca REST API** using the `alpaca-py` SDK.
We exclusively use **bracket orders** — a single API call that creates three
linked orders: market entry, stop-loss, and take-profit.

```python
from src.execution.order_manager import OrderManager

om = OrderManager()  # Reads credentials from .env

# Bracket order (recommended — exchange manages your exits automatically)
om.place_bracket_order(
    symbol="AAPL",
    qty=133,
    side="buy",
    stop_loss=149.25,
    take_profit=152.25,
)

# Simple orders
om.buy("AAPL", qty=10)
om.sell("AAPL", qty=10)

# End-of-day cleanup (IMPORTANT — run before 4pm)
om.close_all_positions()

# Account info
account = om.get_account()
print(f"Equity: ${float(account.equity):,.2f}")
```

### Order Flow

```
1. BUY signal received
       │
       ▼
2. Risk check: daily loss limit? max positions?
       │
       ▼
3. Calculate position size, stop-loss, take-profit
       │
       ▼
4. Place bracket order via Alpaca API
       │
       ├──▶ Price hits take_profit → exchange auto-fills sell limit order
       │
       └──▶ Price hits stop_loss  → exchange auto-fills stop order
```

---

## 6. Backtesting

Test your strategy on historical data before risking real money.

```bash
# From the trading_bot/ directory:
python scripts/run_backtest.py
```

Edit the configuration at the top of `run_backtest.py`:

```python
SYMBOL   = "AAPL"           # What to backtest
INTERVAL = "5m"             # Candle size
PERIOD   = "30d"            # How far back
STRATEGY = EMACrossoverStrategy()
INITIAL_CAPITAL = 10_000
```

**Sample output**:
```
====================================================
         BACKTEST RESULTS SUMMARY
====================================================
  Starting capital  :    $10,000.00
  Final capital     :    $10,847.32
  Total return      :         8.47%
  Sharpe ratio      :          1.24
  Max drawdown      :        -3.21%
  Total trades      :           18
  Win rate          :        61.11%
  Avg winning trade :       $142.30
  Avg losing trade  :        -$63.44
  Reward/risk ratio :         2.24x
====================================================
```

The script also saves an equity curve chart to `logs/`.

### Interpreting Results

| Metric | Poor | Acceptable | Good |
|---|---|---|---|
| Total return | < 0% | 0–10% | > 10% |
| Sharpe ratio | < 0.5 | 0.5–1.0 | > 1.0 |
| Max drawdown | < -30% | -10% to -30% | > -10% |
| Win rate | < 30% | 30–50% | > 50% |

> **Important**: A good backtest does not guarantee live trading profits.
> Backtests suffer from **look-ahead bias** and don't account for slippage.
> Always paper-trade for several weeks before going live.

---

## 7. Live Deployment

### Step 1: Install dependencies

```bash
cd trading_bot/
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2: Configure credentials

```bash
cp .env.example .env
# Open .env and add your Alpaca keys
```

### Step 3: Paper trading (start here — always)

```bash
# Confirm PAPER_TRADING=true in .env, then:
python scripts/run_bot.py
```

Watch the console logs and the Alpaca paper trading dashboard at
`https://app.alpaca.markets` (select "Paper Trading" in the top left).

### Step 4: Monitor and iterate

Paper-trade for **at least 4–6 weeks** across different market conditions
(trending, choppy, news-driven) before considering live trading.

### Cloud deployment (optional)

To run the bot 24/7 without leaving your computer on, deploy to a small
cloud VM (e.g. AWS t3.micro ~$8/month, DigitalOcean Droplet ~$6/month):

```bash
# On the server, run with nohup to keep it running after you log out:
nohup python scripts/run_bot.py > logs/stdout.log 2>&1 &

# Or use systemd / supervisor for proper process management
# Or use screen / tmux for interactive sessions
```

---

## 8. Security Best Practices

### Protect your API keys

1. **Never hard-code** API keys in source files.
2. Store them in `.env` and load with `python-dotenv`.
3. Add `.env` to `.gitignore` — it is already included here.
4. Generate **paper trading keys** separately from live keys.
5. Rotate keys immediately if you suspect exposure.

### Alpaca API key permissions

When generating keys, Alpaca lets you restrict permissions. For a bot that
only buys and sells its own positions, you only need:
- Trading: enabled
- Market data: enabled
- Account management: read-only is sufficient

### Rate limits

Alpaca's free tier allows **200 API calls per minute**. The bot adds 1-second
delays between symbol evaluations and sleeps between cycles to stay well
within this limit. If you add many symbols, increase `TRADE_INTERVAL_SECONDS`.

### Runaway order protection

- All orders use `TimeInForce.DAY` — they auto-cancel if not filled by close.
- Bracket orders auto-close via the exchange even if the bot crashes.
- `close_all_positions()` is called on `KeyboardInterrupt`.
- The daily loss limit halts the bot if losses become severe.

---

## 9. Regulatory Considerations

> **Disclaimer**: This is general information, not legal or financial advice.
> Consult a qualified professional for advice specific to your situation.

### Pattern Day Trader (PDT) Rule (USA)

If you make **4 or more day trades in 5 business days** in a US margin account
with **less than $25,000**, your broker will flag you as a Pattern Day Trader
and restrict trading. Options to avoid this:

- Maintain ≥ $25,000 account balance at all times.
- Limit yourself to ≤ 3 day trades per 5-day rolling window.
- Use a cash account (slower but no PDT restriction).
- Trade with an offshore broker (different regulations apply).

### Tax implications

- In the US, day trading profits are taxed as **ordinary income** (not capital gains rates).
- Keep detailed records of every trade: date, symbol, quantity, entry price, exit price, P&L.
- Alpaca provides end-of-year 1099 forms and trade history exports.
- Consult a CPA familiar with trading taxation.

### Market manipulation

Automated trading bots must not engage in:
- Wash trading (buying and selling the same security to create artificial volume)
- Spoofing (placing orders with no intention of filling them)
- Front-running (trading ahead of known client orders)

This bot only trades based on publicly available price signals and never
interacts with order flow in a manipulative way.

### Jurisdiction

Regulations differ significantly by country. Before deploying any automated
trading system, verify the rules in your jurisdiction regarding:
- Licensing requirements for algorithmic trading
- Reporting obligations
- Leverage and margin restrictions

---

## 10. Quick-Start

```bash
# 1. Clone and enter the project
cd trading_bot/

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up configuration
cp .env.example .env
# Edit .env — add your Alpaca paper trading API keys

# 5. Run a backtest (no API key needed for this step)
python scripts/run_backtest.py

# 6. Run the paper trading bot (requires Alpaca keys)
python scripts/run_bot.py

# 7. Run the test suite
python -m pytest tests/ -v
```

---

## 11. Project Structure

```
trading_bot/
│
├── .env.example              ← Template for API keys (copy to .env)
├── requirements.txt          ← Python dependencies
│
├── config/
│   └── settings.py           ← All configuration parameters
│
├── src/
│   ├── bot.py                ← Main bot loop + orchestration
│   │
│   ├── data/
│   │   └── market_data.py    ← Yahoo Finance data fetcher
│   │
│   ├── strategies/
│   │   ├── base_strategy.py  ← Abstract base class for all strategies
│   │   ├── ema_crossover.py  ← EMA 9/21 crossover + RSI filter
│   │   └── rsi_vwap.py       ← RSI + VWAP mean-reversion
│   │
│   ├── risk/
│   │   └── risk_manager.py   ← Position sizing, stop-loss, daily limits
│   │
│   ├── execution/
│   │   └── order_manager.py  ← Alpaca order placement and management
│   │
│   └── backtest/
│       └── backtester.py     ← Historical simulation + performance metrics
│
├── scripts/
│   ├── run_backtest.py       ← Run a backtest (edit symbol/strategy here)
│   └── run_bot.py            ← Start the live/paper bot
│
├── tests/
│   └── test_strategies.py    ← Unit tests (run with pytest)
│
└── logs/                     ← Log files and backtest charts (auto-created)
```

---

## 12. Resources and Further Reading

### Books

| Title | Author | Focus |
|---|---|---|
| *Algorithmic Trading* | Ernest P. Chan | Quantitative strategy development |
| *Quantitative Trading* | Ernest P. Chan | How to set up a quant trading business |
| *Trading Systems and Methods* | Perry Kaufman | Comprehensive strategy encyclopedia |
| *Python for Finance* | Yves Hilpisch | Python applied to financial analysis |
| *Advances in Financial ML* | Marcos Lopez de Prado | Modern ML techniques for trading |

### Online Courses

- **Udemy**: "Algorithmic Trading A-Z with Python, Machine Learning & AWS"
- **Coursera**: "Machine Learning for Trading" (Google Cloud)
- **QuantConnect Bootcamp**: Free, browser-based algorithmic trading education
- **Alpaca Learn**: Official tutorials at `https://alpaca.markets/learn`

### Tools and Platforms

| Tool | Use case |
|---|---|
| [QuantConnect](https://quantconnect.com) | Cloud-based backtesting, live trading, large data library |
| [Backtrader](https://backtrader.com) | Python backtesting framework with live execution |
| [Zipline](https://zipline.io) | Pythonic backtesting (used by Quantopian) |
| [vectorbt](https://vectorbt.dev) | Fast vectorised backtesting with interactive charts |
| [TradingView Pine Script](https://tradingview.com) | Visual strategy prototyping |

### Communities

- Reddit: r/algotrading, r/quant
- Discord: Algorithmic Trading servers
- GitHub: search "algorithmic trading python"
- Stack Overflow: tag `[algorithmic-trading]`

### Key Concepts to Study Next

1. **Walk-forward optimisation** — how to tune parameters without overfitting
2. **Monte Carlo simulation** — stress-test your strategy against randomised scenarios
3. **Portfolio-level risk** — correlation between positions, sector exposure
4. **Market microstructure** — bid-ask spreads, order book dynamics, slippage
5. **Machine learning signals** — using ML models as a signal source
6. **Options strategies** — hedging a long portfolio with puts
