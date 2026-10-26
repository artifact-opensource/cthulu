import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime

from cthulu.execution.engine import ExecutionEngine, OrderRequest, OrderType, OrderStatus
from cthulu.persistence.database import Database
from cthulu.observability.telemetry import Telemetry
from cthulu import constants
import os
import json


class TestExecutionEngine(unittest.TestCase):
    @patch('cthulu.execution.engine.mt5')
    def test_place_order_resolves_position_ticket(self, mock_mt5):
        # Mock MT5 constants
        mock_mt5.TRADE_RETCODE_DONE = 10009
        mock_mt5.ORDER_TYPE_BUY = 0
        mock_mt5.ORDER_FILLING_IOC = 1
        
        # Mock MT5 result for order_send
        mock_result = MagicMock()
        mock_result.retcode = 10009
        mock_result.price = 1.2345
        mock_result.volume = 0.1
        mock_result.order = 777
        mock_result.comment = 'done'

        mock_mt5.order_send.return_value = mock_result

        # Mock positions_get to return a matching position
        mock_pos = MagicMock()
        mock_pos.ticket = 888
        mock_pos.symbol = 'EURUSD'
        mock_pos.volume = 0.1
        mock_pos.magic = constants.DEFAULT_MAGIC
        mock_pos.time = datetime.now().timestamp()

        mock_mt5.positions_get.return_value = [mock_pos]

        # Setup a connector stub with required methods
        connector = MagicMock()
        connector.is_connected.return_value = True
        connector.get_symbol_info.return_value = {'ask': 1.2346, 'bid': 1.2344}
        connector.get_account_info.return_value = {'trade_allowed': True}

        # Create a temp DB + telemetry helper for provenance persistence
        import tempfile, os
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp.close()
        db = Database(tmp.name)
        from cthulu.observability.telemetry import Telemetry
        telemetry = Telemetry(db)

        engine = ExecutionEngine(connector=connector, telemetry=telemetry)

        order_req = OrderRequest(
            signal_id='s1',
            symbol='EURUSD',
            side='BUY',
            volume=0.1,
            order_type=OrderType.MARKET
        )

        result = engine.place_order(order_req)

        self.assertEqual(result.status, OrderStatus.FILLED)
        self.assertEqual(result.order_id, 777)
        self.assertEqual(result.position_ticket, 888)

        # Verify provenance metadata attached and persisted in DB
        self.assertIn('provenance', order_req.metadata)
        prov_rows = db.get_recent_provenance(limit=5)
        self.assertGreaterEqual(len(prov_rows), 1)
        # The most recent entry should match client_tag
        self.assertEqual(prov_rows[0].get('client_tag'), order_req.client_tag)
        # Clean up temp DB
        try:
            os.remove(tmp.name)
        except Exception:
            pass

    @patch('cthulu.execution.engine.mt5')
    def test_ml_collector_receives_provenance_id(self, mock_mt5):
        # Mock MT5 constants
        mock_mt5.TRADE_RETCODE_DONE = 10009
        mock_mt5.ORDER_TYPE_BUY = 0
        mock_mt5.ORDER_FILLING_IOC = 1
        
        mock_result = MagicMock()
        mock_result.retcode = 10009
        mock_result.price = 1.2345
        mock_result.volume = 0.1
        mock_result.order = 999
        mock_result.comment = 'done'
        mock_mt5.order_send.return_value = mock_result
        mock_mt5.positions_get.return_value = []

        connector = MagicMock()
        connector.is_connected.return_value = True
        connector.get_symbol_info.return_value = {'ask': 1.2346, 'bid': 1.2344}
        connector.get_account_info.return_value = {'trade_allowed': True}

        import tempfile
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp.close()
        db = Database(tmp.name)
        telemetry = Telemetry(db)

        ml_mock = MagicMock()
        engine = ExecutionEngine(connector=connector, telemetry=telemetry, ml_collector=ml_mock)

        order_req = OrderRequest(
            signal_id='s2',
            symbol='EURUSD',
            side='BUY',
            volume=0.05,
            order_type=OrderType.MARKET
        )

        engine.place_order(order_req)

        # Ensure ML collector called with provenance_id present
        ml_mock.record_order.assert_called()
        call_args = ml_mock.record_order.call_args[0][0]
        self.assertIn('provenance_id', call_args)

        try:
            os.remove(tmp.name)
        except Exception:
            pass


if __name__ == '__main__':
    unittest.main()




