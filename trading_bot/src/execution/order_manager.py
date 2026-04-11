"""
order_manager.py - Place, monitor, and cancel orders via the Alpaca API.

Alpaca is a commission-free stock broker with a developer-friendly REST API.
It offers two environments:
  Paper trading: https://paper-api.alpaca.markets  (fake money, safe to test)
  Live trading:  https://api.alpaca.markets        (real money — be careful!)

IMPORTANT: Always develop and test with PAPER_TRADING=true. Only switch to
live trading after thorough paper-trading validation over several weeks.

Alpaca account setup (free):
  1. Go to https://app.alpaca.markets and sign up
  2. Click "Paper Trading" in the left sidebar
  3. Go to "Overview" → "API Keys" → click the + icon to generate keys
  4. Copy the API key and secret into your .env file
"""
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    TakeProfitRequest,
    StopLossRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce
from loguru import logger

from config import settings


class OrderManager:
    """
    Manages all order-related operations with Alpaca.

    Usage:
        om = OrderManager()

        # Simple market orders
        om.buy("AAPL", qty=10)
        om.sell("AAPL", qty=10)

        # Bracket order (recommended) — entry + auto stop-loss + take-profit
        om.place_bracket_order("AAPL", qty=10, side="buy",
                               stop_loss=148.50, take_profit=152.50)

        # Account and position info
        account = om.get_account()
        positions = om.get_positions()

        # End-of-day cleanup
        om.close_all_positions()
    """

    def __init__(self):
        if not settings.ALPACA_API_KEY or not settings.ALPACA_SECRET_KEY:
            raise ValueError(
                "Missing Alpaca credentials.\n"
                "Please set ALPACA_API_KEY and ALPACA_SECRET_KEY in your .env file.\n"
                "Get free keys at: https://app.alpaca.markets"
            )

        self.client = TradingClient(
            api_key=settings.ALPACA_API_KEY,
            secret_key=settings.ALPACA_SECRET_KEY,
            paper=settings.PAPER_TRADING,
        )
        mode = "PAPER (fake money)" if settings.PAPER_TRADING else "LIVE (real money!)"
        logger.info(f"OrderManager ready — {mode}")

    # ── Account information ────────────────────────────────────────────────────

    def get_account(self):
        """
        Retrieve account equity, cash, and buying power.

        Returns:
            Alpaca Account object with attributes like:
              .equity        — total portfolio value
              .cash          — uninvested cash
              .buying_power  — available to spend
            Returns None on failure.
        """
        try:
            account = self.client.get_account()
            logger.info(
                f"Account | Equity: ${float(account.equity):,.2f} | "
                f"Cash: ${float(account.cash):,.2f} | "
                f"Buying power: ${float(account.buying_power):,.2f}"
            )
            return account
        except Exception as exc:
            logger.error(f"Could not fetch account info: {exc}")
            return None

    def get_positions(self) -> list:
        """
        Return a list of all currently open positions.

        Each item has attributes like .symbol, .qty, .avg_entry_price,
        .unrealized_pl (profit/loss), .market_value, etc.
        """
        try:
            positions = self.client.get_all_positions()
            if positions:
                logger.debug(
                    f"Open positions: "
                    + ", ".join(f"{p.symbol}×{p.qty}" for p in positions)
                )
            return positions
        except Exception as exc:
            logger.error(f"Could not fetch positions: {exc}")
            return []

    def get_position(self, symbol: str):
        """
        Return the open position for a specific symbol, or None if flat.

        Args:
            symbol: Ticker, e.g. "AAPL"
        """
        try:
            return self.client.get_open_position(symbol)
        except Exception:
            return None  # Alpaca raises an error when there's no position

    # ── Placing orders ─────────────────────────────────────────────────────────

    def buy(self, symbol: str, qty: int):
        """
        Place a simple market buy order.

        A market order executes immediately at the best available price.
        No stop-loss or take-profit is attached — use place_bracket_order
        for safer trading with automatic exits.

        Args:
            symbol: Stock ticker, e.g. "AAPL"
            qty:    Number of shares to buy
        """
        return self._market_order(symbol, qty, OrderSide.BUY)

    def sell(self, symbol: str, qty: int):
        """
        Place a simple market sell order.

        Args:
            symbol: Stock ticker, e.g. "AAPL"
            qty:    Number of shares to sell
        """
        return self._market_order(symbol, qty, OrderSide.SELL)

    def _market_order(self, symbol: str, qty: int, side: OrderSide):
        """Internal helper that submits a plain market order."""
        try:
            request = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=side,
                time_in_force=TimeInForce.DAY,  # Auto-cancel if not filled by close
            )
            order = self.client.submit_order(request)
            logger.info(
                f"Market {side.value.upper()}: {qty}×{symbol} | Order ID: {order.id}"
            )
            return order
        except Exception as exc:
            logger.error(f"Failed to place {side.value} order for {symbol}: {exc}")
            return None

    def place_bracket_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        stop_loss: float,
        take_profit: float,
    ):
        """
        Place a bracket order — the recommended way to trade.

        A bracket order bundles three orders together:
          1. Entry: market order to enter the position immediately.
          2. Stop-loss: automatically closes if price moves against you.
          3. Take-profit: automatically closes if price hits your target.

        The exchange manages orders 2 and 3, so even if your bot goes
        offline your positions are still protected.

        Args:
            symbol:      Ticker, e.g. "AAPL"
            qty:         Number of shares
            side:        "buy" (long) or "sell" (short)
            stop_loss:   Price at which to exit at a loss, e.g. 148.50
            take_profit: Price at which to take profit, e.g. 152.50

        Returns:
            Order object, or None on failure.
        """
        try:
            order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
            request = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=order_side,
                time_in_force=TimeInForce.DAY,
                order_class="bracket",
                take_profit=TakeProfitRequest(limit_price=take_profit),
                stop_loss=StopLossRequest(stop_price=stop_loss),
            )
            order = self.client.submit_order(request)
            logger.info(
                f"Bracket {side.upper()}: {qty}×{symbol} | "
                f"Stop: ${stop_loss:.2f} | Target: ${take_profit:.2f} | "
                f"Order ID: {order.id}"
            )
            return order
        except Exception as exc:
            logger.error(f"Failed to place bracket order for {symbol}: {exc}")
            return None

    # ── Managing existing orders ───────────────────────────────────────────────

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel a single open order by its ID.

        Returns True on success, False on failure.
        """
        try:
            self.client.cancel_order_by_id(order_id)
            logger.info(f"Cancelled order {order_id}")
            return True
        except Exception as exc:
            logger.error(f"Could not cancel order {order_id}: {exc}")
            return False

    def cancel_all_orders(self) -> None:
        """Cancel all open orders across all symbols."""
        try:
            self.client.cancel_orders()
            logger.info("All open orders cancelled")
        except Exception as exc:
            logger.error(f"Could not cancel all orders: {exc}")

    # ── Closing positions ──────────────────────────────────────────────────────

    def close_position(self, symbol: str) -> None:
        """
        Close the entire position for one symbol at market price.

        Args:
            symbol: Ticker to close, e.g. "AAPL"
        """
        try:
            self.client.close_position(symbol)
            logger.info(f"Closed position in {symbol}")
        except Exception as exc:
            logger.error(f"Could not close position for {symbol}: {exc}")

    def close_all_positions(self) -> None:
        """
        Close every open position at market price and cancel all open orders.

        IMPORTANT: Call this before market close every day. Day traders
        must not hold positions overnight or they face margin calls.
        """
        try:
            self.client.close_all_positions(cancel_orders=True)
            logger.info("All positions closed and all orders cancelled")
        except Exception as exc:
            logger.error(f"Could not close all positions: {exc}")
