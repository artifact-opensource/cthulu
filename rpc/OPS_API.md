# Ops API — Contract

Base URL: `http://<host>:<port>` (RPC server binds locally by default)

Authentication: Bearer token via `Authorization: Bearer <token>` header (same token used by RPC endpoints).

Endpoints

1) GET /ops/status
- Description: Returns a JSON snapshot of system status
- Response: 200
  {
    "status": {
      "mode": "live|dry-run|unknown",
      "execution_engine": true/false,
      "position_manager": true/false,
      "database": true/false,
      "mt5_up": true/false|null,
      "open_positions": int|null
    }
  }

2) GET /ops/runbook?name=<section>
- Description: Returns an excerpt of the runbook (observability playbook). If `name` not provided, returns a top excerpt.
- Response: 200 {"runbook_excerpt": "..."}

3) GET /ops/audit?limit=50
- Description: Returns recent audit entries (from RPC audit log or provenance table)
- Response: 200 {"limit": <int>, "results": [ ... ]}

4) POST /ops/command
- Description: Request an operational command (two-step confirmation)
- Body (initial request):
  {
    "command": "start|stop|restart|dry-run-on|dry-run-off",
    "component": "orchestrator|connector|...",
    "params": { ... }
  }
- Response (initial): 200 {"requires_confirmation": true, "confirm_token": "...", "expires_in": 60}
- Body (confirmed request):
  {
    "command": "start",
    "component": "orchestrator",
    "confirm_token": "confirm_abcdef123",
    "params": { }
  }
- Response (executed): 200 {"result": {"status": "ok", "action": "started"}}
- Errors: 400/401/403/500 as appropriate

Audit
- All ops interactions are recorded in audit logs (configured by RPC SecurityManager). Use `/ops/audit` to query recent entries.

Safety
- All commands require confirmation token to execute.
- The Ops API will return 501 if the server does not have an OpsController bound.

Notes
- This contract is intentionally minimal and safe. The controller will refuse unsafe actions if the underlying orchestrator or connector objects do not expose safe methods.
