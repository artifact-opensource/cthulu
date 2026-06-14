"""
Session Scheduler — Cthulu Autonomous Trading
Adjusts trading aggressiveness based on market sessions and time of day.

Sessions (all times UTC):
  - Asian    (00:00–08:00 UTC / 05:00–13:00 PKT)  — conservative, crypto focus
  - London   (07:00–16:00 UTC / 12:00–21:00 PKT)  — aggressive gold/forex
  - New York (13:00–22:00 UTC / 18:00–03:00 PKT)  — aggressive everything
  - Off-hours (22:00–00:00 UTC)                    — conservative, crypto only
  - Weekend  (Fri 22:00 → Sun 22:00 UTC)           — crypto only, reduced

Session overlaps are resolved by taking the highest multiplier across
active sessions for each symbol.

Each symbol gets a session multiplier (0.0 – 1.5):
  - 1.0  = normal aggressiveness
  - 0.0  = don't trade this symbol in this session
  - 1.5  = peak overlap — highest liquidity, most aggressive
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class SessionScheduler:
    """
    Maps current UTC time → per-symbol trading intensity multiplier.

    Usage::

        scheduler = SessionScheduler()
        mult = scheduler.get_symbol_multiplier('BTCUSD#')   # → 0.8
        info = scheduler.get_session_info()                  # → dict
    """

    # ── Session windows (UTC hours, inclusive-start, exclusive-end) ──

    SESSIONS = {
        'asian':     (0, 8),     # 00:00–08:00
        'london':    (7, 16),    # 07:00–16:00
        'new_york':  (13, 22),   # 13:00–22:00
        'off_hours': (22, 24),   # 22:00–00:00  (wraps to asian at 00)
    }

    SESSION_DESCRIPTIONS = {
        'asian':     'Asian session — conservative, crypto focus',
        'london':    'London session — aggressive gold/forex',
        'new_york':  'New York session — aggressive everything',
        'overlap':   'London + NY overlap — PEAK liquidity, most aggressive',
        'off_hours': 'Off-hours — conservative, crypto only',
        'weekend':   'Weekend — forex & commodities closed, crypto only',
    }

    # Symbols most liquid during each session
    SESSION_SYMBOLS: Dict[str, List[str]] = {
        'asian':     ['BTCUSD#', 'ETHUSD#', 'GOLDm#', 'USDJPY'],
        'london':    ['GOLDm#', 'GOLD#', 'EURUSD', 'GBPUSD', 'OILCash#', 'BTCUSD#'],
        'new_york':  ['GOLDm#', 'GOLD#', 'EURUSD', 'OILCash#', 'BTCUSD#', 'ETHUSD#',
                      'GBPUSD', 'USDJPY', 'USDCHF'],
        'overlap':   ['GOLDm#', 'GOLD#', 'EURUSD', 'GBPUSD', 'OILCash#', 'BTCUSD#'],
        'off_hours': ['BTCUSD#', 'ETHUSD#'],
        'weekend':   ['BTCUSD#', 'ETHUSD#'],
    }

    # ── Per-symbol-group multipliers by session ──────────────────────
    #
    # Multiplier meaning:
    #   1.0 = normal sizing/confluence threshold
    #   0.0 = do NOT trade (market closed or illiquid)
    #   >1  = increase aggressiveness (peak liquidity)
    #   <1  = reduce size, require higher confluence

    SESSION_PROFILES: Dict[str, Dict[str, float]] = {
        'overlap': {
            'gold':   1.5,
            'oil':    1.3,
            'crypto': 1.0,
            'forex':  1.5,
        },
        'london': {
            'gold':   1.0,
            'oil':    0.7,
            'crypto': 0.8,
            'forex':  1.0,
        },
        'new_york': {
            'gold':   1.0,
            'oil':    1.0,
            'crypto': 0.8,
            'forex':  1.0,
        },
        'asian': {
            'gold':   0.5,
            'oil':    0.3,
            'crypto': 0.8,
            'forex':  0.3,
        },
        'off_hours': {
            'gold':   0.3,
            'oil':    0.3,
            'crypto': 0.8,
            'forex':  0.0,
        },
        'weekend': {
            'gold':   0.0,
            'oil':    0.0,
            'crypto': 0.7,   # lower liquidity weekends
            'forex':  0.0,
        },
    }

    # ── Symbol → group mapping ───────────────────────────────────────

    SYMBOL_GROUPS: Dict[str, str] = {
        # Gold
        'GOLDm#': 'gold', 'GOLD#': 'gold', 'XAUUSD': 'gold',
        # Oil
        'OILCash#': 'oil', 'USOIL': 'oil', 'BRENT': 'oil',
        # Crypto
        'BTCUSD#': 'crypto', 'BTCUSD': 'crypto',
        'ETHUSD#': 'crypto', 'ETHUSD': 'crypto',
        'LTCUSD#': 'crypto', 'XRPUSD#': 'crypto',
        # Forex
        'EURUSD': 'forex', 'GBPUSD': 'forex', 'USDJPY': 'forex',
        'USDCHF': 'forex', 'EURGBP': 'forex', 'EURJPY': 'forex',
        'AUDUSD': 'forex', 'NZDUSD': 'forex', 'USDCAD': 'forex',
    }

    # ─────────────────────────────────────────────────────────────────

    def __init__(self, config: Dict[str, Any] = None):
        config = config or {}
        self._custom_profiles = config.get('session_profiles', {})
        logger.info("SessionScheduler initialised")

    # ── Public API ───────────────────────────────────────────────────

    def get_current_session(self) -> str:
        """
        Return the name of the current dominant trading session.

        Overlap (London + NY open simultaneously) is surfaced explicitly
        because it's the highest-liquidity window of the day.
        """
        now = datetime.now(timezone.utc)

        if self._is_weekend(now):
            return 'weekend'

        h = now.hour

        # Overlap check first — most specific
        london_open = 7 <= h < 16
        ny_open = 13 <= h < 22

        if london_open and ny_open:
            return 'overlap'
        if london_open:
            return 'london'
        if ny_open:
            return 'new_york'
        if 0 <= h < 8:
            return 'asian'

        return 'off_hours'

    def get_session_info(self) -> Dict[str, Any]:
        """
        Return a rich dict describing the current session.

        Keys:
            session       — session name str
            description   — human-readable description
            utc_time      — current time formatted
            is_weekend    — bool
            symbols_active — list of symbols most liquid now
        """
        now = datetime.now(timezone.utc)
        session = self.get_current_session()

        return {
            'session': session,
            'description': self.SESSION_DESCRIPTIONS.get(session, 'Unknown'),
            'utc_time': now.strftime('%H:%M UTC'),
            'is_weekend': self._is_weekend(now),
            'symbols_active': self.SESSION_SYMBOLS.get(session, []),
        }

    def get_symbol_multiplier(self, symbol: str) -> float:
        """
        Return the session intensity multiplier for *symbol* right now.

        Multiplier mapping (spec):
          Gold:   1.0 London/NY, 0.5 Asian, 0.3 off-hours, 0.0 weekend
          Forex:  1.0 London/NY, 0.3 Asian, 0.0 off-hours, 0.0 weekend
          Crypto: 0.8 always (24/7), slight boost to 1.0 during overlap
          Oil:    1.0 NY, 0.7 London, 0.3 off-hours/Asian, 0.0 weekend
        """
        session = self.get_current_session()
        group = self.SYMBOL_GROUPS.get(symbol, 'forex')
        profile = self.SESSION_PROFILES.get(session, {})

        # Apply custom overrides
        if session in self._custom_profiles:
            profile = {**profile, **self._custom_profiles[session]}

        return profile.get(group, 0.5)

    def get_session_multipliers(self, symbols: List[str] = None) -> Dict[str, float]:
        """
        Return {symbol: multiplier} for every requested symbol (or all known).
        """
        if symbols is None:
            symbols = list(self.SYMBOL_GROUPS.keys())
        return {sym: self.get_symbol_multiplier(sym) for sym in symbols}

    # ── Internals ────────────────────────────────────────────────────

    @staticmethod
    def _is_weekend(now: datetime) -> bool:
        """
        Forex weekend: Friday 22:00 UTC → Sunday 22:00 UTC.
        Commodities follow the same window.
        Crypto never sleeps.
        """
        wd = now.weekday()  # 0=Mon … 6=Sun
        h = now.hour

        if wd == 4 and h >= 22:       # Friday after 22:00
            return True
        if wd == 5:                    # Saturday all day
            return True
        if wd == 6 and h < 22:        # Sunday before 22:00
            return True
        return False
