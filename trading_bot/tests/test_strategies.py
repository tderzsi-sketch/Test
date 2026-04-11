"""
test_strategies.py - Unit tests for strategies, risk manager, and backtester.

Run all tests from the trading_bot/ directory:
    python -m pytest tests/ -v

Run a specific test class:
    python -m pytest tests/test_strategies.py::TestRiskManager -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.strategies.base_strategy import BUY, SELL, HOLD
from src.strategies.ema_crossover import EMACrossoverStrategy
from src.strategies.rsi_vwap import RSIVWAPStrategy
from src.risk.risk_manager import RiskManager
from src.backtest.backtester import Backtester

EASTERN = ZoneInfo("America/New_York")


# ── Test data factory ──────────────────────────────────────────────────────────

def make_ohlcv(n: int = 120, start_price: float = 150.0, trend: str = "up") -> pd.DataFrame:
    """
    Generate synthetic OHLCV data for testing.

    Args:
        n:           Number of 5-minute bars.
        start_price: Starting close price.
        trend:       "up", "down", or "sideways".
    """
    np.random.seed(42)
    dates = [
        datetime(2024, 6, 3, 9, 30, tzinfo=EASTERN) + timedelta(minutes=5 * i)
        for i in range(n)
    ]

    if trend == "up":
        drift = np.linspace(0, 10, n)
    elif trend == "down":
        drift = np.linspace(0, -10, n)
    else:
        drift = np.zeros(n)

    noise = np.random.normal(0, 0.2, n)
    closes = np.maximum(start_price + drift + noise, 1.0)

    highs = closes + np.abs(np.random.normal(0, 0.1, n))
    lows = closes - np.abs(np.random.normal(0, 0.1, n))
    opens = closes + np.random.normal(0, 0.05, n)

    return pd.DataFrame(
        {
            "Open": opens,
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": np.random.randint(500_000, 2_000_000, n).astype(float),
        },
        index=pd.DatetimeIndex(dates),
    )


# ── EMA Crossover tests ────────────────────────────────────────────────────────

class TestEMACrossoverStrategy:

    def test_signal_column_present(self):
        data = make_ohlcv(120)
        result = EMACrossoverStrategy().generate_signals(data)
        assert "signal" in result.columns

    def test_signals_only_valid_values(self):
        data = make_ohlcv(120)
        result = EMACrossoverStrategy().generate_signals(data)
        assert set(result["signal"].unique()).issubset({BUY, SELL, HOLD})

    def test_indicator_columns_present(self):
        data = make_ohlcv(120)
        result = EMACrossoverStrategy().generate_signals(data)
        for col in ("ema_short", "ema_long", "rsi"):
            assert col in result.columns, f"Missing column: {col}"

    def test_insufficient_data_returns_hold(self):
        """With only 10 bars we can't compute a 21-period EMA — must return HOLD."""
        data = make_ohlcv(10)
        signal = EMACrossoverStrategy().get_latest_signal(data)
        assert signal == HOLD

    def test_invalid_period_raises(self):
        with pytest.raises(ValueError):
            EMACrossoverStrategy(short_period=21, long_period=9)

    def test_uptrend_generates_buy_signals(self):
        """An up-trending price series should eventually produce at least one BUY."""
        data = make_ohlcv(200, trend="up")
        result = EMACrossoverStrategy().generate_signals(data)
        assert (result["signal"] == BUY).any(), "Expected at least one BUY in uptrend"

    def test_returns_dataframe(self):
        data = make_ohlcv(120)
        result = EMACrossoverStrategy().generate_signals(data)
        assert isinstance(result, pd.DataFrame)


# ── RSI + VWAP tests ───────────────────────────────────────────────────────────

class TestRSIVWAPStrategy:

    def test_signal_column_present(self):
        data = make_ohlcv(120)
        result = RSIVWAPStrategy().generate_signals(data)
        assert "signal" in result.columns

    def test_signals_only_valid_values(self):
        data = make_ohlcv(120)
        result = RSIVWAPStrategy().generate_signals(data)
        assert set(result["signal"].unique()).issubset({BUY, SELL, HOLD})

    def test_vwap_and_rsi_columns_present(self):
        data = make_ohlcv(120)
        result = RSIVWAPStrategy().generate_signals(data)
        assert "rsi" in result.columns
        assert "vwap" in result.columns

    def test_insufficient_data_returns_hold(self):
        data = make_ohlcv(5)
        signal = RSIVWAPStrategy().get_latest_signal(data)
        assert signal == HOLD

    def test_vwap_is_positive(self):
        """VWAP must always be a positive price."""
        data = make_ohlcv(120)
        result = RSIVWAPStrategy().generate_signals(data)
        assert (result["vwap"] > 0).all()

    def test_rsi_range(self):
        """RSI must be between 0 and 100."""
        data = make_ohlcv(120)
        result = RSIVWAPStrategy().generate_signals(data)
        assert result["rsi"].between(0, 100).all()


# ── Risk manager tests ─────────────────────────────────────────────────────────

class TestRiskManager:

    def test_position_size_basic(self):
        """
        Account = $10,000, risk = 1% = $100.
        Entry $150, stop $149 → risk/share = $1 → 100 shares.
        """
        rm = RiskManager(account_balance=10_000)
        shares = rm.calculate_position_size(
            entry_price=150.0,
            stop_loss_price=149.0,
            risk_fraction=0.01,
        )
        assert shares == 100

    def test_position_size_minimum_one(self):
        """Even with a tiny account we always trade at least 1 share."""
        rm = RiskManager(account_balance=50)
        shares = rm.calculate_position_size(
            entry_price=1000.0,
            stop_loss_price=999.0,
        )
        assert shares >= 1

    def test_stop_loss_long(self):
        rm = RiskManager(account_balance=10_000)
        stop = rm.calculate_stop_loss(100.0, side="buy", pct=0.005)
        assert stop == pytest.approx(99.50, abs=0.01)

    def test_stop_loss_short(self):
        rm = RiskManager(account_balance=10_000)
        stop = rm.calculate_stop_loss(100.0, side="sell", pct=0.005)
        assert stop == pytest.approx(100.50, abs=0.01)

    def test_take_profit_long(self):
        rm = RiskManager(account_balance=10_000)
        target = rm.calculate_take_profit(100.0, side="buy", pct=0.015)
        assert target == pytest.approx(101.50, abs=0.01)

    def test_take_profit_short(self):
        rm = RiskManager(account_balance=10_000)
        target = rm.calculate_take_profit(100.0, side="sell", pct=0.015)
        assert target == pytest.approx(98.50, abs=0.01)

    def test_daily_loss_limit_triggered(self):
        """Losing 4% of $10,000 ($400) should trigger the 3% daily limit."""
        rm = RiskManager(account_balance=10_000)
        rm.update_balance(9_600)
        assert rm.is_daily_loss_limit_hit() is True

    def test_daily_loss_not_triggered(self):
        """Losing only 1% should NOT trigger the limit."""
        rm = RiskManager(account_balance=10_000)
        rm.update_balance(9_900)
        assert rm.is_daily_loss_limit_hit() is False

    def test_daily_profit_never_triggers(self):
        """A profit should never trigger the loss limit."""
        rm = RiskManager(account_balance=10_000)
        rm.update_balance(11_000)
        assert rm.is_daily_loss_limit_hit() is False

    def test_max_positions_allows_below_limit(self):
        rm = RiskManager(account_balance=10_000)
        assert rm.can_open_position(open_positions=3) is True

    def test_max_positions_blocks_at_limit(self):
        rm = RiskManager(account_balance=10_000)
        # Default MAX_OPEN_POSITIONS is 5
        assert rm.can_open_position(open_positions=5) is False

    def test_balance_update_tracks_pnl(self):
        rm = RiskManager(account_balance=10_000)
        rm.update_balance(10_500)
        assert rm.daily_pnl == pytest.approx(500.0)
        assert rm.account_balance == pytest.approx(10_500.0)


# ── Backtester tests ───────────────────────────────────────────────────────────

class TestBacktester:

    def test_run_returns_required_keys(self):
        data = make_ohlcv(150)
        bt = Backtester(initial_capital=10_000)
        results = bt.run(EMACrossoverStrategy(), data)
        assert "equity_curve" in results
        assert "trades" in results
        assert "metrics" in results

    def test_equity_curve_starts_at_capital(self):
        data = make_ohlcv(150)
        bt = Backtester(initial_capital=10_000)
        results = bt.run(EMACrossoverStrategy(), data)
        first_val = float(results["equity_curve"]["portfolio_value"].iloc[0])
        # First bar: no position, so portfolio value ≈ initial capital
        assert abs(first_val - 10_000) < 500

    def test_metrics_keys_present(self):
        data = make_ohlcv(150)
        bt = Backtester(initial_capital=10_000)
        results = bt.run(EMACrossoverStrategy(), data)
        expected_keys = {
            "initial_capital", "final_capital", "total_return_pct",
            "sharpe_ratio", "max_drawdown_pct", "total_trades", "win_rate_pct",
        }
        assert expected_keys.issubset(results["metrics"].keys())

    def test_empty_data_handled_gracefully(self):
        bt = Backtester(initial_capital=10_000)
        results = bt.run(EMACrossoverStrategy(), pd.DataFrame())
        assert results["equity_curve"].empty

    def test_final_capital_is_positive(self):
        data = make_ohlcv(150)
        bt = Backtester(initial_capital=10_000)
        results = bt.run(EMACrossoverStrategy(), data)
        assert results["metrics"]["final_capital"] > 0
