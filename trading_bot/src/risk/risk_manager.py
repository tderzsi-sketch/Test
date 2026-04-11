"""
risk_manager.py - Position sizing and risk controls.

Risk management is the most important part of any trading system.
Even a mediocre strategy with good risk management can be profitable,
while a great strategy with poor risk management will eventually blow up.

Key principles implemented here:
  1. Fixed fractional position sizing — never risk more than 1% per trade.
  2. Stop-loss orders — automatically exit losing trades at a set price.
  3. Take-profit orders — lock in gains at a target price.
  4. Daily loss limit — stop trading for the day if losses exceed 3%.
  5. Max positions limit — don't spread capital across too many stocks.
"""
from loguru import logger
from config import settings


class RiskManager:
    """
    Calculates position sizes and enforces portfolio-level risk limits.

    Usage:
        rm = RiskManager(account_balance=10_000.0)

        # How many shares to buy?
        shares = rm.calculate_position_size(entry_price=150.0)

        # Where to put stop-loss and take-profit?
        stop  = rm.calculate_stop_loss(150.0, side="buy")   # e.g. 149.25
        target = rm.calculate_take_profit(150.0, side="buy") # e.g. 152.25

        # Is it safe to trade?
        if rm.is_daily_loss_limit_hit(): ...
        if not rm.can_open_position(open_positions=3): ...
    """

    def __init__(self, account_balance: float):
        """
        Args:
            account_balance: Current total equity (cash + open positions).
        """
        self.account_balance = account_balance
        self.starting_balance = account_balance  # Balance at bot start today
        self.daily_pnl = 0.0                     # Running profit/loss today

    def update_balance(self, new_balance: float) -> None:
        """
        Call this after each trade or at the start of each cycle to keep
        the balance current. The risk manager uses it to track daily P&L.
        """
        change = new_balance - self.account_balance
        self.daily_pnl += change
        self.account_balance = new_balance
        logger.debug(
            f"Balance updated: ${new_balance:,.2f} | "
            f"Daily P&L: ${self.daily_pnl:+.2f}"
        )

    # ── Position sizing ────────────────────────────────────────────────────────

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss_price: float = None,
        risk_fraction: float = settings.MAX_RISK_PER_TRADE,
    ) -> int:
        """
        Calculate how many shares to buy so that if the stop-loss is hit
        we lose at most `risk_fraction` of our account balance.

        The formula is:
            dollar_risk    = account_balance × risk_fraction
            risk_per_share = |entry_price − stop_loss_price|
            shares         = floor(dollar_risk / risk_per_share)

        Example:
            account = $10,000, risk = 1% = $100
            entry = $150, stop_loss = $149.25 → risk/share = $0.75
            shares = floor(100 / 0.75) = 133 shares

        Args:
            entry_price:     Price we plan to enter the trade.
            stop_loss_price: Price at which we exit at a loss.
                             Defaults to entry × (1 − STOP_LOSS_PCT).
            risk_fraction:   Fraction of account to risk (default: 0.01 = 1%).

        Returns:
            Number of whole shares to buy. Always at least 1.
        """
        if stop_loss_price is None:
            stop_loss_price = entry_price * (1 - settings.STOP_LOSS_PCT)

        dollar_risk = self.account_balance * risk_fraction
        risk_per_share = abs(entry_price - stop_loss_price)

        if risk_per_share <= 0:
            logger.warning(
                "Risk per share is zero (entry == stop_loss). "
                "Defaulting to 1 share."
            )
            return 1

        shares = int(dollar_risk / risk_per_share)
        shares = max(1, shares)  # Always buy at least 1 share

        logger.info(
            f"Position sizing: {shares} shares | "
            f"Dollar risk: ${dollar_risk:.2f} | "
            f"Risk/share: ${risk_per_share:.4f} | "
            f"Entry: ${entry_price:.2f} | Stop: ${stop_loss_price:.2f}"
        )
        return shares

    # ── Stop-loss and take-profit calculation ──────────────────────────────────

    def calculate_stop_loss(
        self,
        entry_price: float,
        side: str = "buy",
        pct: float = settings.STOP_LOSS_PCT,
    ) -> float:
        """
        Calculate the stop-loss price for a trade.

        For a long (buy) trade:  stop_loss = entry × (1 − pct)
        For a short (sell) trade: stop_loss = entry × (1 + pct)

        The default stop of 0.5% means we lose at most 0.5% on the stock
        price itself (actual dollar loss is limited by position sizing).

        Args:
            entry_price: The price at which we entered the trade.
            side:        "buy" for long trades, "sell" for short trades.
            pct:         Stop distance as a fraction (default: 0.005 = 0.5%).

        Returns:
            Stop-loss price rounded to 2 decimal places.
        """
        if side == "buy":
            stop = round(entry_price * (1 - pct), 2)
        else:
            stop = round(entry_price * (1 + pct), 2)
        logger.debug(
            f"Stop-loss ({side}): entry ${entry_price:.2f} → "
            f"stop ${stop:.2f} ({pct * 100:.2f}%)"
        )
        return stop

    def calculate_take_profit(
        self,
        entry_price: float,
        side: str = "buy",
        pct: float = settings.TAKE_PROFIT_PCT,
    ) -> float:
        """
        Calculate the take-profit price for a trade.

        For a long (buy) trade:  take_profit = entry × (1 + pct)
        For a short (sell) trade: take_profit = entry × (1 − pct)

        The default target of 1.5% vs a 0.5% stop gives a 3:1
        reward-to-risk ratio. This means we only need a ~25% win rate
        to break even — a comfortable margin for beginners.

        Args:
            entry_price: The price at which we entered the trade.
            side:        "buy" for long trades, "sell" for short trades.
            pct:         Target distance as a fraction (default: 0.015 = 1.5%).

        Returns:
            Take-profit price rounded to 2 decimal places.
        """
        if side == "buy":
            target = round(entry_price * (1 + pct), 2)
        else:
            target = round(entry_price * (1 - pct), 2)
        logger.debug(
            f"Take-profit ({side}): entry ${entry_price:.2f} → "
            f"target ${target:.2f} ({pct * 100:.2f}%)"
        )
        return target

    # ── Portfolio-level guards ─────────────────────────────────────────────────

    def is_daily_loss_limit_hit(self) -> bool:
        """
        Returns True if today's cumulative loss has exceeded the maximum
        allowed daily loss (MAX_DAILY_LOSS_PCT of the starting balance).

        When True, the bot should stop opening new positions for the rest
        of the day to prevent a bad day from becoming a catastrophic one.
        """
        if self.daily_pnl >= 0:
            return False  # We're in profit — no concern

        loss_fraction = abs(self.daily_pnl) / self.starting_balance
        if loss_fraction >= settings.MAX_DAILY_LOSS_PCT:
            logger.warning(
                f"Daily loss limit hit! Lost ${abs(self.daily_pnl):.2f} "
                f"({loss_fraction * 100:.1f}% of ${self.starting_balance:,.2f}). "
                f"No new positions for the rest of the day."
            )
            return True
        return False

    def can_open_position(self, open_positions: int) -> bool:
        """
        Returns True if we are allowed to open another position.

        Prevents over-diversification and ensures we have enough buying
        power left for each position to be properly sized.

        Args:
            open_positions: Number of currently open positions.
        """
        if open_positions >= settings.MAX_OPEN_POSITIONS:
            logger.warning(
                f"Max positions reached ({open_positions}/{settings.MAX_OPEN_POSITIONS}). "
                f"Not opening new positions until one closes."
            )
            return False
        return True
