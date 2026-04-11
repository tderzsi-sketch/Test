"""
rsi_vwap.py - RSI + VWAP mean-reversion strategy.

How it works:
  VWAP (Volume-Weighted Average Price) is the average price of a stock
  weighted by how much volume traded at each price. It resets at the
  start of every trading day and acts as a key support/resistance level
  that institutional traders watch closely.

  RSI (Relative Strength Index) measures the speed and magnitude of
  recent price changes on a 0–100 scale:
    < 30 = oversold (price may bounce up)
    > 70 = overbought (price may pull back)

  Combining both filters out low-quality signals:
    BUY  when RSI < 30 (oversold) AND price is ABOVE VWAP (still bullish)
    SELL when RSI > 70 (overbought) AND price is BELOW VWAP (bearish)
    HOLD otherwise

  This is a mean-reversion strategy — it bets that extreme RSI readings
  will revert to the mean, especially when confirmed by VWAP position.
"""
import pandas as pd
import pandas_ta as ta
from loguru import logger

from config import settings
from src.strategies.base_strategy import BaseStrategy, BUY, SELL, HOLD


class RSIVWAPStrategy(BaseStrategy):
    """
    RSI + VWAP mean-reversion strategy for intraday trading.

    Best suited for stocks with regular intraday patterns and enough
    volume for VWAP to be meaningful (avoid low-volume micro-caps).

    Parameters:
        rsi_period:    RSI window (default: 14)
        rsi_oversold:  RSI threshold for oversold condition (default: 30)
        rsi_overbought: RSI threshold for overbought condition (default: 70)
    """

    def __init__(
        self,
        rsi_period: int = settings.RSI_PERIOD,
        rsi_oversold: float = settings.RSI_OVERSOLD,
        rsi_overbought: float = settings.RSI_OVERBOUGHT,
    ):
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought

    def _calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        """
        Calculate the intraday VWAP that resets each trading day.

        Formula: VWAP = cumulative(typical_price × volume) / cumulative(volume)
        Typical price = (High + Low + Close) / 3

        We group by date so VWAP restarts every morning at 9:30am.
        """
        df = df.copy()
        typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
        df["_pv"] = typical_price * df["Volume"]

        # Extract the date portion of the DatetimeIndex for grouping
        df["_date"] = df.index.date

        cumulative_pv = df.groupby("_date")["_pv"].cumsum()
        cumulative_vol = df.groupby("_date")["Volume"].cumsum()

        vwap = cumulative_pv / cumulative_vol
        return vwap

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate RSI + VWAP signals on OHLCV data.

        Added columns in the returned DataFrame:
          rsi    : RSI values (0–100)
          vwap   : Intraday VWAP (resets daily)
          signal : BUY / SELL / HOLD per bar
        """
        min_bars = self.rsi_period + 2
        if data.empty or len(data) < min_bars:
            logger.warning(
                f"RSIVWAPStrategy needs at least {min_bars} bars "
                f"(got {len(data)}). Returning all HOLD."
            )
            df = data.copy()
            df["signal"] = HOLD
            return df

        df = data.copy()

        # ── Step 1: Calculate indicators ──────────────────────────────────────
        df["rsi"] = ta.rsi(df["Close"], length=self.rsi_period)
        df["vwap"] = self._calculate_vwap(df)

        df.dropna(inplace=True)

        # ── Step 2: Build signal conditions ───────────────────────────────────
        df["signal"] = HOLD

        # Buy: price is oversold AND still above VWAP (bullish context)
        buy_mask = (df["rsi"] < self.rsi_oversold) & (df["Close"] >= df["vwap"])

        # Sell: price is overbought AND has fallen below VWAP (bearish context)
        sell_mask = (df["rsi"] > self.rsi_overbought) & (df["Close"] < df["vwap"])

        df.loc[buy_mask, "signal"] = BUY
        df.loc[sell_mask, "signal"] = SELL

        n_buy = int(buy_mask.sum())
        n_sell = int(sell_mask.sum())
        logger.debug(
            f"RSIVWAPStrategy: {n_buy} buy, {n_sell} sell signals "
            f"across {len(df)} bars"
        )
        return df
