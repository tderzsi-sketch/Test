"""
market_data.py - Retrieves historical and real-time stock price data.

We use Yahoo Finance (via the yfinance library) because:
  - It's completely free with no API key required
  - It covers all US stocks and ETFs
  - It provides OHLCV data at 1-minute to monthly intervals

Limitation: Intraday data (1m, 5m, 15m, etc.) is only available
for the last 60 days. For longer backtests, use daily ("1d") interval.
"""
import yfinance as yf
import pandas as pd
from loguru import logger

from config import settings


class MarketDataFetcher:
    """
    Downloads stock price data from Yahoo Finance.

    Example usage:
        fetcher = MarketDataFetcher()

        # Get 5-minute candles for the last 5 days
        data = fetcher.get_historical_data("AAPL", interval="5m", period="5d")

        # Get the current price
        price = fetcher.get_current_price("AAPL")

        # Get data for multiple stocks at once
        all_data = fetcher.get_multiple_symbols_data(["AAPL", "MSFT", "TSLA"])
    """

    def get_historical_data(
        self,
        symbol: str,
        interval: str = settings.INTRADAY_INTERVAL,
        period: str = settings.HISTORICAL_PERIOD,
    ) -> pd.DataFrame:
        """
        Download OHLCV (Open, High, Low, Close, Volume) candle data.

        Args:
            symbol:   Stock ticker, e.g. "AAPL", "MSFT", "SPY"
            interval: Candle size — "1m", "5m", "15m", "1h", "1d", "1wk"
                      Intraday intervals are capped at 60 days lookback.
            period:   How far back to go — "1d", "5d", "1mo", "3mo", "60d", "1y"

        Returns:
            DataFrame with columns: Open, High, Low, Close, Volume
            The index is a DatetimeIndex in UTC.
            Returns an empty DataFrame if the request fails.
        """
        try:
            logger.debug(f"Fetching {interval} bars for {symbol} (last {period})")
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=period, interval=interval)

            if data.empty:
                logger.warning(
                    f"Yahoo Finance returned no data for '{symbol}'. "
                    f"Check the symbol name and try a shorter period."
                )
                return pd.DataFrame()

            # Keep only the standard OHLCV columns
            data = data[["Open", "High", "Low", "Close", "Volume"]].copy()
            data.dropna(inplace=True)

            logger.info(
                f"Fetched {len(data)} {interval} bars for {symbol} "
                f"({data.index[0].date()} → {data.index[-1].date()})"
            )
            return data

        except Exception as exc:
            logger.error(f"Failed to fetch data for {symbol}: {exc}")
            return pd.DataFrame()

    def get_current_price(self, symbol: str) -> float:
        """
        Return the most recent price for a symbol.

        Uses Yahoo Finance's fast_info endpoint which is lighter than
        downloading a full history. Falls back to the last close in
        the 1-day history if fast_info is unavailable.

        Returns:
            Price as a float, or 0.0 if the lookup fails.
        """
        try:
            ticker = yf.Ticker(symbol)
            price = float(ticker.fast_info.last_price)
            logger.debug(f"Current price of {symbol}: ${price:.2f}")
            return price
        except Exception:
            # Fallback: use the most recent close from today's 1-minute data
            try:
                data = self.get_historical_data(symbol, interval="1m", period="1d")
                if not data.empty:
                    return float(data["Close"].iloc[-1])
            except Exception:
                pass
            logger.error(f"Could not get current price for {symbol}")
            return 0.0

    def get_multiple_symbols_data(
        self,
        symbols: list,
        interval: str = settings.INTRADAY_INTERVAL,
        period: str = "5d",
    ) -> dict:
        """
        Fetch price data for several symbols in one call.

        Args:
            symbols:  List of ticker strings, e.g. ["AAPL", "MSFT"]
            interval: Candle size (same options as get_historical_data)
            period:   Lookback period (same options as get_historical_data)

        Returns:
            Dict mapping symbol → DataFrame. Symbols that failed are omitted.
        """
        result = {}
        for symbol in symbols:
            data = self.get_historical_data(symbol, interval=interval, period=period)
            if not data.empty:
                result[symbol] = data
            # Small pause to be polite to the API
            import time
            time.sleep(0.3)

        logger.info(
            f"Fetched data for {len(result)}/{len(symbols)} symbols successfully"
        )
        return result
