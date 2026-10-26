"""
Intelligent Position Sizing — Cthulu Autonomous Trading
Implements half-Kelly Criterion with dynamic adjustments for optimal
position sizing on a micro/small account.

Kelly Formula:  f* = (win_rate × avg_win − (1 − win_rate) × avg_loss) / avg_win
Half-Kelly:     lot_frac = f* × 0.5   (conservative — lower variance, still +EV)

Adjustments applied multiplicatively:
  1. Account-size scaling (micro-lot caps)
  2. Session multiplier (from SessionScheduler)
  3. Macro confidence (from MarketIntelligence)
  4. Signal confidence (from strategy)
  5. Anti-martingale: 3 consecutive losses on a symbol → minimum lot
  6. Sliding window: only last N trades used for win-rate calculation

Persistence: trade results saved to disk so stats survive restarts.
"""
import json
import logging
import math
from collections import deque
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

# Persistent performance file
PERF_FILE = Path(__file__).parent.parent / "data" / "trading_performance.json"

# Sliding window size for per-symbol stats
DEFAULT_WINDOW = 20

# Minimum trades before switching from fixed-fractional to Kelly
MIN_TRADES_FOR_KELLY = 5


# ─── Data classes ────────────────────────────────────────────────────

@dataclass
class TradeRecord:
    """A single closed trade result."""
    pnl: float
    timestamp: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {'pnl': self.pnl, 'timestamp': self.timestamp}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'TradeRecord':
        return cls(pnl=d.get('pnl', 0.0), timestamp=d.get('timestamp', 0.0))


@dataclass
class SymbolPerformance:
    """Sliding-window performance stats for one symbol."""
    symbol: str
    window_size: int = DEFAULT_WINDOW

    # Raw trade results (sliding window)
    recent_trades: List[TradeRecord] = field(default_factory=list)

    # Derived (recomputed on every update)
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.5
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 1.0
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    total_profit: float = 0.0
    total_loss: float = 0.0

    def record(self, pnl: float, timestamp: float = 0.0):
        """Add a trade result and recompute stats over the sliding window."""
        import time as _time
        ts = timestamp or _time.time()
        self.recent_trades.append(TradeRecord(pnl=pnl, timestamp=ts))

        # Trim to window
        if len(self.recent_trades) > self.window_size:
            self.recent_trades = self.recent_trades[-self.window_size:]

        # Streak tracking (across ALL trades, not just window)
        if pnl > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            self.consecutive_wins = 0

        self._recompute()

    def _recompute(self):
        """Recompute derived stats from the sliding window."""
        trades = self.recent_trades
        self.total_trades = len(trades)

        win_pnls = [t.pnl for t in trades if t.pnl > 0]
        loss_pnls = [abs(t.pnl) for t in trades if t.pnl <= 0]

        self.wins = len(win_pnls)
        self.losses = len(loss_pnls)
        self.win_rate = self.wins / self.total_trades if self.total_trades > 0 else 0.5

        self.total_profit = sum(win_pnls)
        self.total_loss = sum(loss_pnls)

        self.avg_win = self.total_profit / self.wins if self.wins > 0 else 0.0
        self.avg_loss = self.total_loss / self.losses if self.losses > 0 else 0.0
        self.profit_factor = (
            self.total_profit / self.total_loss if self.total_loss > 0 else float('inf')
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            'symbol': self.symbol,
            'window_size': self.window_size,
            'recent_trades': [t.to_dict() for t in self.recent_trades],
            'total_trades': self.total_trades,
            'wins': self.wins,
            'losses': self.losses,
            'win_rate': self.win_rate,
            'avg_win': self.avg_win,
            'avg_loss': self.avg_loss,
            'profit_factor': self.profit_factor,
            'consecutive_wins': self.consecutive_wins,
            'consecutive_losses': self.consecutive_losses,
            'total_profit': self.total_profit,
            'total_loss': self.total_loss,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'SymbolPerformance':
        perf = cls(
            symbol=d.get('symbol', ''),
            window_size=d.get('window_size', DEFAULT_WINDOW),
        )
        perf.recent_trades = [
            TradeRecord.from_dict(t) for t in d.get('recent_trades', [])
        ]
        perf.consecutive_wins = d.get('consecutive_wins', 0)
        perf.consecutive_losses = d.get('consecutive_losses', 0)
        perf._recompute()
        return perf


# ─── Main sizer ──────────────────────────────────────────────────────

class IntelligentSizer:
    """
    Calculate optimal lot size using half-Kelly + dynamic adjustments.

    Usage::

        sizer = IntelligentSizer()
        lot = sizer.calculate_lot_size(
            symbol='GOLDm#',
            account_balance=52.0,
            atr=1.5,
            signal_confidence=0.7,
            session_multiplier=1.0,
            macro_confidence=0.6,
            leverage=1000,
        )
        # → 0.02

        # After a trade closes:
        sizer.record_trade_result('GOLDm#', pnl=3.50)
    """

    # ── Balance → max-lot table (linear interpolation between tiers) ──
    _BALANCE_TIERS = [
        #  (balance_usd, max_lot)
        (0,    0.01),
        (50,   0.05),
        (100,  0.10),
        (250,  0.25),
        (500,  0.50),
        (1000, 1.00),
        (5000, 5.00),
    ]

    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}

        self.kelly_fraction = config.get('kelly_fraction', 0.5)   # half-Kelly
        self.min_lot = config.get('min_lot', 0.01)
        self.base_risk_pct = config.get('base_risk_pct', 1.0)     # 1% risk when no Kelly data
        self.window_size = config.get('trade_window', DEFAULT_WINDOW)
        self.min_trades = config.get('min_trades_for_kelly', MIN_TRADES_FOR_KELLY)
        self.anti_martingale_streak = config.get('anti_martingale_streak', 3)

        # Performance tracking (per-symbol)
        self._performance: Dict[str, SymbolPerformance] = {}
        self._load_performance()

        logger.info(
            f"IntelligentSizer initialised: kelly_frac={self.kelly_fraction}, "
            f"base_risk={self.base_risk_pct}%, window={self.window_size}, "
            f"min_lot={self.min_lot}, anti_martingale_after={self.anti_martingale_streak}"
        )

    # ── Public API ───────────────────────────────────────────────────

    def calculate_lot_size(
        self,
        symbol: str,
        account_balance: float,
        atr: float = 0.0,
        signal_confidence: float = 0.5,
        session_multiplier: float = 1.0,
        macro_confidence: float = 0.5,
        leverage: int = 1000,
    ) -> float:
        """
        Calculate optimal lot size for a new trade.

        Args:
            symbol:             Trading instrument name
            account_balance:    Current account equity (USD)
            atr:                Current Average True Range
            signal_confidence:  Strategy signal strength (0.0 – 1.0)
            session_multiplier: Session-based intensity (0.0 – 1.5)
            macro_confidence:   Macro regime confidence (0.0 – 1.0)
            leverage:           Account leverage ratio

        Returns:
            Lot size (float, ≥ min_lot, ≤ balance-scaled max)
        """
        perf = self._performance.get(symbol)
        max_lot = self._max_lot_for_balance(account_balance)

        # ── Step 1: Anti-martingale guard ─────────────────────────────
        if perf and perf.consecutive_losses >= self.anti_martingale_streak:
            logger.info(
                f"🛑 {symbol}: {perf.consecutive_losses} consecutive losses → min lot {self.min_lot}"
            )
            return self.min_lot

        # ── Step 2: Base risk amount ─────────────────────────────────
        risk_pct = self.base_risk_pct / 100.0
        risk_amount = account_balance * risk_pct

        # ── Step 3: Kelly multiplier (if enough history) ─────────────
        kelly_mult = 1.0
        if perf and perf.total_trades >= self.min_trades:
            raw_kelly = self._kelly_criterion(
                perf.win_rate, perf.avg_win, perf.avg_loss
            )
            if raw_kelly > 0:
                kelly_mult = raw_kelly * self.kelly_fraction
                kelly_mult = max(0.1, min(3.0, kelly_mult))
            else:
                # Kelly says don't trade — still allow minimum
                logger.warning(f"⚠️ {symbol}: negative Kelly ({raw_kelly:.3f}) → min lot")
                return self.min_lot

        # ── Step 4: Confidence & session scaling ─────────────────────
        conf_scale = 0.5 + signal_confidence * 0.5        # 0.5–1.0
        session_scale = max(0.0, session_multiplier)       # 0.0–1.5
        macro_scale = 0.3 + macro_confidence * 0.7         # 0.3–1.0

        # ── Step 5: Combine ──────────────────────────────────────────
        adjusted_risk = (
            risk_amount
            * kelly_mult
            * conf_scale
            * session_scale
            * macro_scale
        )

        # ── Step 6: Convert risk → lot size ──────────────────────────
        if atr > 0 and account_balance > 0:
            # SL ≈ 2 × ATR; risk_per_lot ≈ sl_distance
            sl_distance = atr * 2.0
            lot_size = adjusted_risk / max(sl_distance, 0.01)
        else:
            # Fallback: fraction of balance / 1000 (micro-lot land)
            lot_size = adjusted_risk / max(account_balance * 0.1, 1.0)

        # ── Step 7: Clamp ────────────────────────────────────────────
        lot_size = max(self.min_lot, min(max_lot, lot_size))
        lot_size = round(lot_size, 2)

        logger.info(
            f"📐 {symbol}: kelly={kelly_mult:.2f} × conf={conf_scale:.2f} × "
            f"session={session_scale:.2f} × macro={macro_scale:.2f} "
            f"→ {lot_size:.2f} lots  (risk=${adjusted_risk:.2f}, max={max_lot})"
        )
        return lot_size

    def record_trade_result(self, symbol: str, pnl: float):
        """Record a closed trade P&L for the given symbol."""
        if symbol not in self._performance:
            self._performance[symbol] = SymbolPerformance(
                symbol=symbol, window_size=self.window_size
            )
        self._performance[symbol].record(pnl)
        self._save_performance()

        p = self._performance[symbol]
        logger.info(
            f"📊 {symbol}: {p.wins}W/{p.losses}L over last {p.total_trades} "
            f"(WR={p.win_rate:.0%}, PF={p.profit_factor:.2f}, "
            f"streak: {'W' + str(p.consecutive_wins) if p.consecutive_wins else 'L' + str(p.consecutive_losses)})"
        )

    def get_performance(self, symbol: str) -> Optional[SymbolPerformance]:
        return self._performance.get(symbol)

    def get_all_performance(self) -> Dict[str, SymbolPerformance]:
        return dict(self._performance)

    # ── Kelly criterion ──────────────────────────────────────────────

    @staticmethod
    def _kelly_criterion(win_rate: float, avg_win: float, avg_loss: float) -> float:
        """
        f* = (win_rate × avg_win − (1 − win_rate) × avg_loss) / avg_win

        Returns raw Kelly fraction.  Can be negative (= don't trade).
        """
        if avg_win <= 0 or avg_loss <= 0 or win_rate <= 0:
            return 0.0

        p = win_rate
        q = 1.0 - p
        f = (p * avg_win - q * avg_loss) / avg_win
        return f

    # ── Balance-scaled max lot ───────────────────────────────────────

    @classmethod
    def _max_lot_for_balance(cls, balance: float) -> float:
        """
        Interpolate max lot from the balance tier table.

        $50 → 0.05, $100 → 0.10, $500 → 0.50, etc.
        Below $50 → 0.01.
        """
        tiers = cls._BALANCE_TIERS
        if balance <= 0:
            return 0.01

        # Below first tier
        if balance <= tiers[0][0]:
            return tiers[0][1]

        # Linear interpolation
        for i in range(1, len(tiers)):
            lo_bal, lo_lot = tiers[i - 1]
            hi_bal, hi_lot = tiers[i]
            if balance <= hi_bal:
                frac = (balance - lo_bal) / (hi_bal - lo_bal) if hi_bal != lo_bal else 0
                return round(lo_lot + frac * (hi_lot - lo_lot), 2)

        # Above last tier — cap at last entry
        return tiers[-1][1]

    # ── Persistence ──────────────────────────────────────────────────

    def _load_performance(self):
        try:
            if PERF_FILE.exists():
                with open(PERF_FILE) as f:
                    data = json.load(f)
                for sym, stats in data.items():
                    self._performance[sym] = SymbolPerformance.from_dict(stats)
                logger.info(
                    f"Loaded performance data for {len(self._performance)} symbols"
                )
        except Exception as e:
            logger.debug(f"Performance load error: {e}")

    def _save_performance(self):
        try:
            PERF_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(PERF_FILE, 'w') as f:
                json.dump(
                    {sym: perf.to_dict() for sym, perf in self._performance.items()},
                    f,
                    indent=2,
                )
        except Exception as e:
            logger.debug(f"Performance save error: {e}")
