from socketserver import BaseServer
from unittest import TestCase
from unittest.mock import patch

from cthulu_agent.server import DashboardHTTPServer


class DashboardHTTPServerTests(TestCase):
    def test_client_disconnects_are_suppressed_but_other_errors_are_reported(self):
        server = DashboardHTTPServer(("127.0.0.1", 0), lambda *_: None)
        client_address = ("127.0.0.1", 12345)
        try:
            with patch.object(BaseServer, "handle_error") as default_handler:
                try:
                    raise ConnectionResetError("client disconnected")
                except ConnectionResetError:
                    server.handle_error(None, client_address)
                default_handler.assert_not_called()

                try:
                    raise RuntimeError("unexpected server error")
                except RuntimeError:
                    server.handle_error(None, client_address)
                default_handler.assert_called_once_with(None, client_address)
        finally:
            server.server_close()
