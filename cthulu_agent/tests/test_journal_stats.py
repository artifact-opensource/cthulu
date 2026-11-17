import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from cthulu_agent.journal import Journal


class JournalStatsTests(unittest.TestCase):
    def test_stats_count_closed_trades_by_utc_close_date(self):
        day_start = datetime(2026, 11, 5, tzinfo=timezone.utc).timestamp()
        journal = Journal()
        self.addCleanup(journal._db.close)

        trades = [
            ("closed", day_start - 1, 100, 2.0),
            ("closed", day_start, 40, 2.0),
            ("closed", day_start + 100, -20, -1.0),
            ("closed", day_start + 200, 0, 0.0),
            ("closed", day_start + 86400, -50, -2.5),
            ("open", day_start + 300, -70, -3.5),
        ]
        for status, ts_close, pnl, r_multiple in trades:
            journal.trade_add(
                status=status,
                ts_open=day_start,
                ts_close=ts_close,
                pnl=pnl,
                r_multiple=r_multiple,
                symbol="EURUSD",
            )

        with patch("cthulu_agent.journal._now", return_value=day_start + 500):
            stats = journal.stats()

        self.assertEqual(stats["today"], {
            "date": "2026-11-05",
            "trades": 3,
            "wins": 1,
            "losses": 1,
            "win_rate": 0.333,
            "pnl": 20,
            "avg_r": 0.333,
            "profit_factor": 2.0,
        })
        self.assertEqual(stats["trades"], 5)
