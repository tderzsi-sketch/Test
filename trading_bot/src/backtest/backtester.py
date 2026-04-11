"""
backtester.py - Test trading strategies on historical data before going live.

Backtesting simulates running your strategy on past price data to see how
it would have performed. It is an essential step before deploying any bot
with real money.

IMPORTANT WARNINGS:
  1. Past performance does NOT guarantee future results.
  2. Backtests are optimistic — they ignore slippage (the difference between
     the price you see and the price you actually get), market impact, and
     data-snooping bias.
  3. Always paper-trade for several weeks after a successful backtest before
     considering live trading.

Metrics explained:
  Total return %  : Percentage gain/loss over the test period.
  Sharpe ratio    : Risk-adjusted return. > 1.0 is good, > 2.0 is excellent.
  Max drawdown %  : Worst peak-to-trough loss. Keep this below 20%.
  Win rate %      : Percentage of trades that were profitable.
  Total trades    : Number of completed round-trips (buy + sell).
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from loguru import logger

from src.strategies.base_strategy import BaseStrategy, BUY, SELL


class Backtester:
    """
    Simulates a strategy on historical OHLCV data.

    Usage:
        from src.data.market_data import MarketDataFetcher
        from src.strategies.ema_crossover import EMACrossoverStrategy
        from src.backtest.backtester import Backtester

        data     = MarketDataFetcher().get_historical_data("AAPL", "5m", "30d")
        strategy = EMACrossoverStrategy()
        bt       = Backtester(initial_capital=10_000)
        results  = bt.run(strategy, data)

        bt.print_summary(results)
        bt.plot_results(results, save_path="logs/backtest.png")
    """

    def __init__(
        self,
        initial_capital: float = 10_000.0,
        commission_per_trade: float = 0.0,
        stop_loss_pct: float = 0.005,
        take_profit_pct: float = 0.015,
    ):
        """
        Args:
            initial_capital:      Starting cash in USD.
            commission_per_trade: Per-trade commission cost in USD.
                                  Alpaca charges $0 — set to 0.0.
            stop_loss_pct:        Stop-loss as a fraction (default: 0.5%).
            take_profit_pct:      Take-profit as a fraction (default: 1.5%).
        """
        self.initial_capital = initial_capital
        self.commission = commission_per_trade
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct

    def run(self, strategy: BaseStrategy, data: pd.DataFrame) -> dict:
        """
        Run the backtest and return a results dictionary.

        Simulation rules:
          - We only take LONG (buy) trades — no short selling.
          - Entry is at the bar's closing price (conservative assumption).
          - Stop-loss and take-profit are checked on every subsequent bar.
          - Only one position is held at a time per this simple backtester.
          - Commission is charged on every entry and exit.

        Args:
            strategy: An instance of any BaseStrategy subclass.
            data:     OHLCV DataFrame from MarketDataFetcher.

        Returns:
            Dict with keys:
              "equity_curve" : DataFrame indexed by timestamp with 'portfolio_value'
              "trades"       : DataFrame of all completed trades
              "metrics"      : Dict of performance statistics
        """
        logger.info(
            f"Backtesting {type(strategy).__name__} | "
            f"Capital: ${self.initial_capital:,.2f} | "
            f"Bars: {len(data)}"
        )

        if data.empty:
            logger.error("Cannot backtest on empty data.")
            return {"equity_curve": pd.DataFrame(), "trades": pd.DataFrame(), "metrics": {}}

        # Generate signals for all bars at once
        signals_df = strategy.generate_signals(data)

        # State variables
        capital = self.initial_capital
        position_shares = 0
        entry_price = 0.0
        stop_price = 0.0
        target_price = 0.0

        trades = []
        equity_curve = []

        for timestamp, row in signals_df.iterrows():
            close = float(row["Close"])
            high = float(row["High"])
            low = float(row["Low"])
            signal = int(row.get("signal", 0))

            # ── Check stop-loss / take-profit on open position ────────────────
            if position_shares > 0:
                # Use the bar's low to check if stop was breached
                if low <= stop_price:
                    exit_price = stop_price  # Assume we got filled at stop price
                    pnl = (exit_price - entry_price) * position_shares - self.commission
                    capital += position_shares * exit_price - self.commission
                    trades.append({
                        "exit_type": "stop_loss",
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "shares": position_shares,
                        "pnl": round(pnl, 2),
                        "timestamp": timestamp,
                    })
                    logger.debug(
                        f"Stop-loss hit at ${exit_price:.2f} | PnL: ${pnl:.2f}"
                    )
                    position_shares = 0

                # Use the bar's high to check if take-profit was hit
                elif high >= target_price:
                    exit_price = target_price
                    pnl = (exit_price - entry_price) * position_shares - self.commission
                    capital += position_shares * exit_price - self.commission
                    trades.append({
                        "exit_type": "take_profit",
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "shares": position_shares,
                        "pnl": round(pnl, 2),
                        "timestamp": timestamp,
                    })
                    logger.debug(
                        f"Take-profit hit at ${exit_price:.2f} | PnL: ${pnl:.2f}"
                    )
                    position_shares = 0

            # ── Act on strategy signals ───────────────────────────────────────
            if signal == BUY and position_shares == 0:
                # Buy with 95% of available capital (leave 5% buffer)
                max_spend = capital * 0.95
                shares = int(max_spend / close)
                if shares > 0:
                    cost = shares * close + self.commission
                    capital -= cost
                    position_shares = shares
                    entry_price = close
                    stop_price = round(close * (1 - self.stop_loss_pct), 2)
                    target_price = round(close * (1 + self.take_profit_pct), 2)
                    logger.debug(
                        f"BUY {shares}×${close:.2f} | "
                        f"Stop: ${stop_price} | Target: ${target_price}"
                    )

            elif signal == SELL and position_shares > 0:
                # Close on signal
                pnl = (close - entry_price) * position_shares - self.commission
                capital += position_shares * close - self.commission
                trades.append({
                    "exit_type": "signal",
                    "entry_price": entry_price,
                    "exit_price": close,
                    "shares": position_shares,
                    "pnl": round(pnl, 2),
                    "timestamp": timestamp,
                })
                logger.debug(
                    f"SELL signal at ${close:.2f} | PnL: ${pnl:.2f}"
                )
                position_shares = 0

            # Record portfolio value at this bar
            portfolio_value = capital + (position_shares * close)
            equity_curve.append({
                "timestamp": timestamp,
                "portfolio_value": round(portfolio_value, 2),
            })

        # Close any remaining position at the last bar
        if position_shares > 0:
            final_price = float(signals_df["Close"].iloc[-1])
            pnl = (final_price - entry_price) * position_shares - self.commission
            capital += position_shares * final_price - self.commission
            trades.append({
                "exit_type": "end_of_test",
                "entry_price": entry_price,
                "exit_price": final_price,
                "shares": position_shares,
                "pnl": round(pnl, 2),
                "timestamp": signals_df.index[-1],
            })

        equity_df = pd.DataFrame(equity_curve).set_index("timestamp")
        trades_df = pd.DataFrame(trades) if trades else pd.DataFrame()
        metrics = self._calculate_metrics(equity_df, trades_df)

        logger.info(
            f"Backtest complete | Return: {metrics.get('total_return_pct', 0):.1f}% | "
            f"Win rate: {metrics.get('win_rate_pct', 0):.1f}% | "
            f"Trades: {metrics.get('total_trades', 0)}"
        )
        return {
            "equity_curve": equity_df,
            "trades": trades_df,
            "metrics": metrics,
        }

    def _calculate_metrics(
        self, equity_df: pd.DataFrame, trades_df: pd.DataFrame
    ) -> dict:
        """Compute standard performance statistics from equity curve and trades."""
        if equity_df.empty:
            return {}

        initial = self.initial_capital
        final = float(equity_df["portfolio_value"].iloc[-1])
        total_return_pct = ((final - initial) / initial) * 100

        # Sharpe Ratio: annualised risk-adjusted return
        # We approximate "daily" returns from intraday bars for simplicity
        returns = equity_df["portfolio_value"].pct_change().dropna()
        if returns.std() > 0:
            sharpe = (returns.mean() / returns.std()) * np.sqrt(252 * 78)
            # 78 = approximate number of 5-minute bars in a trading day
        else:
            sharpe = 0.0

        # Maximum drawdown: worst peak-to-trough decline
        rolling_max = equity_df["portfolio_value"].cummax()
        drawdowns = (equity_df["portfolio_value"] - rolling_max) / rolling_max
        max_drawdown_pct = float(drawdowns.min()) * 100

        # Win rate
        if not trades_df.empty and "pnl" in trades_df.columns:
            completed = trades_df.dropna(subset=["pnl"])
            total_trades = len(completed)
            wins = len(completed[completed["pnl"] > 0])
            win_rate_pct = (wins / total_trades * 100) if total_trades > 0 else 0.0
            avg_win = float(completed[completed["pnl"] > 0]["pnl"].mean()) if wins > 0 else 0.0
            avg_loss = float(completed[completed["pnl"] <= 0]["pnl"].mean()) if (total_trades - wins) > 0 else 0.0
        else:
            total_trades = 0
            win_rate_pct = 0.0
            avg_win = 0.0
            avg_loss = 0.0

        return {
            "initial_capital": initial,
            "final_capital": round(final, 2),
            "total_return_pct": round(total_return_pct, 2),
            "sharpe_ratio": round(sharpe, 2),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "total_trades": total_trades,
            "win_rate_pct": round(win_rate_pct, 2),
            "avg_win_usd": round(avg_win, 2),
            "avg_loss_usd": round(avg_loss, 2),
        }

    def print_summary(self, results: dict) -> None:
        """Print a formatted performance summary to the console."""
        m = results.get("metrics", {})
        if not m:
            print("No results to display.")
            return

        reward_risk = (
            abs(m["avg_win_usd"] / m["avg_loss_usd"])
            if m.get("avg_loss_usd") and m["avg_loss_usd"] != 0 else 0
        )

        print("\n" + "=" * 52)
        print("         BACKTEST RESULTS SUMMARY")
        print("=" * 52)
        print(f"  Starting capital  : ${m['initial_capital']:>12,.2f}")
        print(f"  Final capital     : ${m['final_capital']:>12,.2f}")
        print(f"  Total return      : {m['total_return_pct']:>11.2f}%")
        print(f"  Sharpe ratio      : {m['sharpe_ratio']:>12.2f}")
        print(f"  Max drawdown      : {m['max_drawdown_pct']:>11.2f}%")
        print("-" * 52)
        print(f"  Total trades      : {m['total_trades']:>12}")
        print(f"  Win rate          : {m['win_rate_pct']:>11.2f}%")
        print(f"  Avg winning trade : ${m['avg_win_usd']:>11.2f}")
        print(f"  Avg losing trade  : ${m['avg_loss_usd']:>11.2f}")
        print(f"  Reward/risk ratio : {reward_risk:>12.2f}x")
        print("=" * 52 + "\n")

    def plot_results(
        self,
        results: dict,
        title: str = "Backtest — Equity Curve",
        save_path: str = None,
    ) -> None:
        """
        Plot the equity curve with buy/sell markers.

        Args:
            results:   Output from run().
            title:     Chart title.
            save_path: If provided, save the chart to this file path instead
                       of displaying it (useful for headless servers).
                       Example: "logs/AAPL_backtest.png"
        """
        equity = results.get("equity_curve", pd.DataFrame())
        trades = results.get("trades", pd.DataFrame())

        if equity.empty:
            logger.warning("No equity data to plot.")
            return

        fig, ax = plt.subplots(figsize=(14, 6))

        # ── Equity curve ──────────────────────────────────────────────────────
        ax.plot(
            equity.index,
            equity["portfolio_value"],
            linewidth=2,
            color="#2196F3",
            label="Portfolio Value",
            zorder=3,
        )
        ax.axhline(
            self.initial_capital,
            color="#9E9E9E",
            linestyle="--",
            linewidth=1,
            label=f"Starting Capital (${self.initial_capital:,.0f})",
        )

        # ── Shade profit / loss areas ──────────────────────────────────────────
        ax.fill_between(
            equity.index,
            self.initial_capital,
            equity["portfolio_value"],
            where=equity["portfolio_value"] >= self.initial_capital,
            alpha=0.15,
            color="#4CAF50",
            label="Profit",
        )
        ax.fill_between(
            equity.index,
            self.initial_capital,
            equity["portfolio_value"],
            where=equity["portfolio_value"] < self.initial_capital,
            alpha=0.15,
            color="#F44336",
            label="Loss",
        )

        # ── Format axes ───────────────────────────────────────────────────────
        ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel("Date / Time")
        ax.set_ylabel("Portfolio Value ($)")
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda x, _: f"${x:,.0f}")
        )
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper left")

        # ── Metrics annotation box ────────────────────────────────────────────
        m = results.get("metrics", {})
        if m:
            info = (
                f"Return: {m.get('total_return_pct', 0):.1f}%\n"
                f"Sharpe: {m.get('sharpe_ratio', 0):.2f}\n"
                f"Max DD: {m.get('max_drawdown_pct', 0):.1f}%\n"
                f"Win rate: {m.get('win_rate_pct', 0):.0f}%\n"
                f"Trades: {m.get('total_trades', 0)}"
            )
            ax.text(
                0.99, 0.97, info,
                transform=ax.transAxes,
                fontsize=9,
                verticalalignment="top",
                horizontalalignment="right",
                bbox=dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.8),
            )

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches="tight")
            logger.info(f"Backtest chart saved → {save_path}")
            plt.close(fig)
        else:
            plt.show()
