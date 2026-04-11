"""
bot.py - The main trading bot orchestrator.

This is the "brain" of the system. It ties together all components:
  MarketDataFetcher → grabs fresh price data every cycle
  Strategy          → analyses data and outputs BUY/SELL/HOLD signals
  RiskManager       → sizes positions and enforces safety limits
  OrderManager      → sends orders to Alpaca

The bot runs in an infinite loop, checking each symbol every
TRADE_INTERVAL_SECONDS seconds. Before market close it shuts
down cleanly and closes all open positions.

Flow per cycle:
  1. Is the market open? If not, sleep and retry.
  2. Are we approaching close? Close all positions and wait.
  3. Update account balance for risk calculations.
  4. For each symbol:
      a. Fetch the latest 5-day price data.
      b. Run the strategy → get signal for the latest bar.
      c. If BUY and no current position → size position → bracket order.
      d. If SELL and we have a position → close position.
  5. Sleep for TRADE_INTERVAL_SECONDS, then repeat.
"""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from loguru import logger

from config import settings
from src.data.market_data import MarketDataFetcher
from src.strategies.base_strategy import BUY, SELL
from src.risk.risk_manager import RiskManager
from src.execution.order_manager import OrderManager

EASTERN = ZoneInfo("America/New_York")


class TradingBot:
    """
    Automated intraday trading bot for US stocks.

    Usage:
        from src.strategies.ema_crossover import EMACrossoverStrategy
        bot = TradingBot(strategy=EMACrossoverStrategy())
        bot.run()

    The bot will keep running until you press Ctrl+C. On exit it will
    close all open positions before terminating.
    """

    def __init__(self, strategy, symbols: list = None):
        """
        Args:
            strategy: Any BaseStrategy subclass instance, e.g. EMACrossoverStrategy()
            symbols:  List of tickers to trade. Defaults to settings.SYMBOLS.
        """
        self.strategy = strategy
        self.symbols = symbols or settings.SYMBOLS

        logger.info(f"Initialising TradingBot ({type(strategy).__name__})")

        # Initialise sub-components
        self.data_fetcher = MarketDataFetcher()
        self.order_manager = OrderManager()

        # Get current account balance to initialise the risk manager
        account = self.order_manager.get_account()
        starting_balance = float(account.equity) if account else 10_000.0
        self.risk_manager = RiskManager(account_balance=starting_balance)

        logger.info(
            f"Bot ready | Strategy: {type(strategy).__name__} | "
            f"Symbols: {self.symbols} | "
            f"Balance: ${starting_balance:,.2f} | "
            f"Mode: {'PAPER' if settings.PAPER_TRADING else 'LIVE'}"
        )

    # ── Market hours helpers ───────────────────────────────────────────────────

    def is_market_open(self) -> bool:
        """
        Return True during US stock market hours (9:30 AM – 4:00 PM ET,
        Monday to Friday).

        We use Eastern Time because that's what NYSE and NASDAQ operate on.
        """
        now = datetime.now(tz=EASTERN)

        # Skip weekends
        if now.weekday() >= 5:  # 5=Saturday, 6=Sunday
            return False

        open_time = now.replace(
            hour=settings.MARKET_OPEN_HOUR,
            minute=settings.MARKET_OPEN_MINUTE,
            second=0, microsecond=0,
        )
        close_time = now.replace(
            hour=settings.MARKET_CLOSE_HOUR,
            minute=settings.MARKET_CLOSE_MINUTE,
            second=0, microsecond=0,
        )
        return open_time <= now < close_time

    def is_near_close(self) -> bool:
        """
        Return True when we are within CLOSE_POSITIONS_MINUTES_BEFORE_CLOSE
        minutes of market close.

        We close all positions early to guarantee we exit before 4pm.
        Even 15 minutes of slippage time is enough for this simple bot.
        """
        now = datetime.now(tz=EASTERN)
        close_time = now.replace(
            hour=settings.MARKET_CLOSE_HOUR,
            minute=settings.MARKET_CLOSE_MINUTE,
            second=0, microsecond=0,
        )
        minutes_left = (close_time - now).total_seconds() / 60
        return 0 < minutes_left <= settings.CLOSE_POSITIONS_MINUTES_BEFORE_CLOSE

    # ── Per-symbol trade logic ─────────────────────────────────────────────────

    def trade_symbol(self, symbol: str) -> None:
        """
        Run one complete trade evaluation cycle for a single symbol.

        Steps:
          1. Fetch fresh price history.
          2. Generate a signal with the strategy.
          3. Check what position we currently hold.
          4. If BUY and flat → open a bracket order.
             If SELL and long → close the position.
        """
        try:
            # 1. Fetch data
            data = self.data_fetcher.get_historical_data(
                symbol,
                interval=settings.INTRADAY_INTERVAL,
                period="5d",
            )
            if data.empty:
                logger.warning(f"{symbol}: no data available, skipping.")
                return

            # 2. Get the latest signal
            signal = self.strategy.get_latest_signal(data)
            current_price = float(data["Close"].iloc[-1])

            # 3. Check current position
            position = self.order_manager.get_position(symbol)
            has_position = position is not None

            # 4a. BUY signal — open a new position if we don't already have one
            if signal == BUY and not has_position:

                # Safety checks before placing the order
                if self.risk_manager.is_daily_loss_limit_hit():
                    logger.info(f"{symbol}: skipping BUY — daily loss limit active")
                    return

                open_count = len(self.order_manager.get_positions())
                if not self.risk_manager.can_open_position(open_count):
                    return

                # Calculate order parameters
                stop_loss = self.risk_manager.calculate_stop_loss(current_price, "buy")
                take_profit = self.risk_manager.calculate_take_profit(current_price, "buy")
                qty = self.risk_manager.calculate_position_size(
                    entry_price=current_price,
                    stop_loss_price=stop_loss,
                )

                logger.info(
                    f"Opening BUY on {symbol} | "
                    f"Price: ${current_price:.2f} | Qty: {qty} | "
                    f"SL: ${stop_loss} | TP: ${take_profit}"
                )

                self.order_manager.place_bracket_order(
                    symbol=symbol,
                    qty=qty,
                    side="buy",
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                )

            # 4b. SELL signal — close an existing long position
            elif signal == SELL and has_position:
                logger.info(f"Closing position on {symbol} — SELL signal received")
                self.order_manager.close_position(symbol)

            else:
                logger.debug(
                    f"{symbol}: HOLD | Price: ${current_price:.2f} | "
                    f"Signal: {signal} | Position: {'open' if has_position else 'flat'}"
                )

        except Exception as exc:
            logger.error(f"Error during trade cycle for {symbol}: {exc}")

    # ── Main loop ──────────────────────────────────────────────────────────────

    def run(self) -> None:
        """
        Start the bot. Runs indefinitely until Ctrl+C.

        The loop:
          - If market is closed: wait 60 seconds and check again.
          - If near close: close all positions and pause.
          - Otherwise: cycle through all symbols, then sleep.
        """
        logger.info("Bot started. Press Ctrl+C to stop.")

        try:
            while True:
                # ── Market closed ──────────────────────────────────────────────
                if not self.is_market_open():
                    now = datetime.now(tz=EASTERN)
                    logger.info(
                        f"Market is closed ({now.strftime('%A %H:%M ET')}). "
                        f"Checking again in 60 seconds..."
                    )
                    time.sleep(60)
                    continue

                # ── Near end-of-day: close everything ─────────────────────────
                if self.is_near_close():
                    logger.info(
                        f"Market closes in ≤{settings.CLOSE_POSITIONS_MINUTES_BEFORE_CLOSE} "
                        f"minutes — closing all positions."
                    )
                    self.order_manager.close_all_positions()
                    # Sleep past the close to avoid re-entering the near-close block
                    time.sleep(settings.CLOSE_POSITIONS_MINUTES_BEFORE_CLOSE * 60 + 120)
                    continue

                # ── Active trading cycle ───────────────────────────────────────
                logger.info(
                    f"--- Trade cycle | {datetime.now(tz=EASTERN).strftime('%H:%M:%S ET')} ---"
                )

                # Refresh the account balance for risk calculations
                account = self.order_manager.get_account()
                if account:
                    self.risk_manager.update_balance(float(account.equity))

                # Evaluate each symbol in turn
                for symbol in self.symbols:
                    self.trade_symbol(symbol)
                    time.sleep(1)  # Brief pause between symbols — respects rate limits

                # Wait before next cycle
                logger.info(
                    f"Cycle done. Next cycle in {settings.TRADE_INTERVAL_SECONDS}s."
                )
                time.sleep(settings.TRADE_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            logger.info("Bot stopped by user (Ctrl+C). Closing all positions...")
            self.order_manager.close_all_positions()
            logger.info("All done. Goodbye!")
