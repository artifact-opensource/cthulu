"""Start the RPC server with an OpsController bound for local testing.

Usage: python scripts/start_rpc_with_ops.py

This script is intended for development / staging only.
"""
from cthulu.rpc.server import run_rpc_server
from cthulu.ops.controller import OpsController

# The objects below would normally be created by bootstrap; pass None for now
ops = OpsController()

# Example start (binds 127.0.0.1:8000)
thread, httpd = run_rpc_server('127.0.0.1', 8000, token=None, execution_engine=None, risk_manager=None, position_manager=None, database=None, ops_controller=ops)
print('RPC server started on 127.0.0.1:8000 (thread running)')
# Keep running
thread.join()
