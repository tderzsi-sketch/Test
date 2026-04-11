"""
base_strategy.py - Abstract base class that every strategy must implement.

All strategies in this project inherit from BaseStrategy and must provide
a generate_signals() method that adds a 'signal' column to the price data.

Signal values:
  BUY  ( 1) — open a long position
  SELL (-1) — close an existing long position
  HOLD ( 0) — do nothing this bar
"""
from abc import ABC, abstractmethod
import pandas as pd


# ── Signal constants ───────────────────────────────────────────────────────────
# Import these in any file that needs to check or produce signals.
BUY = 1
SELL = -1
HOLD = 0


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.

    Subclasses must implement generate_signals(). Everything else is
    inherited for free — including the convenience get_latest_signal().
    """

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Analyse OHLCV price data and return a copy with a 'signal' column.

        Args:
            data: DataFrame with columns Open, High, Low, Close, Volume.
                  Produced by MarketDataFetcher.get_historical_data().

        Returns:
            Same DataFrame extended with:
              - A 'signal' column: BUY (1), SELL (-1), or HOLD (0) per row.
              - Any indicator columns the strategy calculated (e.g. ema_short).
        """
        ...

    def get_latest_signal(self, data: pd.DataFrame) -> int:
        """
        Convenience method: run the strategy and return the signal for
        the most recent (last) bar only.

        This is what the live bot calls every trade cycle.

        Returns:
            BUY, SELL, or HOLD for the latest candle.
        """
        signals = self.generate_signals(data)
        if signals.empty or "signal" not in signals.columns:
            return HOLD
        return int(signals["signal"].iloc[-1])
