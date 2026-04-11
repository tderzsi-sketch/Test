"""
ema_crossover.py - EMA Crossover strategy with RSI filter.

How it works:
  An Exponential Moving Average (EMA) gives more weight to recent prices
  than a simple average. When a fast (short) EMA crosses above a slow
  (long) EMA it signals that upward momentum is building — a buy signal.
  When it crosses below, momentum is turning negative — a sell signal.

  The RSI filter prevents buying when a stock is already overbought (RSI > 70)
  and prevents selling when it is already oversold (RSI < 30), which reduces
  false signals during choppy markets.

Signal logic:
  BUY  when short EMA crosses ABOVE long EMA  AND  RSI < 70
  SELL when short EMA crosses BELOW long EMA  AND  RSI > 30
  HOLD otherwise
"""
import pandas as pd
import pandas_ta as ta
from loguru import logger

from config import settings
from src.strategies.base_strategy import BaseStrategy, BUY, SELL, HOLD


class EMACrossoverStrategy(BaseStrategy):
    """
    Exponential Moving Average (EMA) crossover strategy.

    This is one of the most widely used trend-following strategies.
    It works best during trending markets and can produce many false
    signals during sideways/choppy price action.

    Parameters:
        short_period: The fast EMA window (default: 9 bars)
        long_period:  The slow EMA window (default: 21 bars)
        rsi_period:   The RSI window used as a filter (default: 14 bars)
    """

    def __init__(
        self,
        short_period: int = settings.EMA_SHORT_PERIOD,
        long_period: int = settings.EMA_LONG_PERIOD,
        rsi_period: int = settings.RSI_PERIOD,
    ):
        if short_period >= long_period:
            raise ValueError(
                f"short_period ({short_period}) must be less than "
                f"long_period ({long_period})"
            )
        self.short_period = short_period
        self.long_period = long_period
        self.rsi_period = rsi_period

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate EMA crossover signals on OHLCV data.

        Requires at least long_period + 2 rows of data to produce
        meaningful signals (anything less returns all HOLD).

        Added columns in the returned DataFrame:
          ema_short   : Fast EMA values
          ema_long    : Slow EMA values
          rsi         : RSI values
          signal      : BUY / SELL / HOLD per bar
        """
        min_bars = self.long_period + 2
        if data.empty or len(data) < min_bars:
            logger.warning(
                f"EMACrossover needs at least {min_bars} bars "
                f"(got {len(data)}). Returning all HOLD."
            )
            df = data.copy()
            df["signal"] = HOLD
            return df

        df = data.copy()

        # ── Step 1: Calculate indicators ──────────────────────────────────────
        df["ema_short"] = ta.ema(df["Close"], length=self.short_period)
        df["ema_long"] = ta.ema(df["Close"], length=self.long_period)
        df["rsi"] = ta.rsi(df["Close"], length=self.rsi_period)

        # Drop rows where indicators couldn't be calculated yet
        df.dropna(inplace=True)

        # ── Step 2: Detect crossover events ───────────────────────────────────
        # ema_above[i] is True when short EMA is above long EMA at bar i
        df["_ema_above"] = df["ema_short"] > df["ema_long"]

        # A crossover UP happens when ema_above flips from False to True
        df["_cross_up"] = df["_ema_above"] & ~df["_ema_above"].shift(1).fillna(False)

        # A crossover DOWN happens when ema_above flips from True to False
        df["_cross_down"] = ~df["_ema_above"] & df["_ema_above"].shift(1).fillna(True)

        # ── Step 3: Apply RSI filter and assign signals ───────────────────────
        df["signal"] = HOLD

        buy_mask = df["_cross_up"] & (df["rsi"] < settings.RSI_OVERBOUGHT)
        sell_mask = df["_cross_down"] & (df["rsi"] > settings.RSI_OVERSOLD)

        df.loc[buy_mask, "signal"] = BUY
        df.loc[sell_mask, "signal"] = SELL

        # Remove internal helper columns before returning
        df.drop(columns=["_ema_above", "_cross_up", "_cross_down"], inplace=True)

        n_buy = int(buy_mask.sum())
        n_sell = int(sell_mask.sum())
        logger.debug(
            f"EMACrossover({self.short_period}/{self.long_period}): "
            f"{n_buy} buy, {n_sell} sell signals across {len(df)} bars"
        )
        return df
