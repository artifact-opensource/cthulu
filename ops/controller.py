import logging
from typing import Optional, Dict, Any

logger = logging.getLogger('cthulu.ops')

class OpsController:
    """Minimal Ops controller that delegates to runtime components when available.

    This controller is intentionally conservative: it only performs actions if
    underlying components expose the expected methods. It records operations in
    logs and returns structured results.
    """
    def __init__(self, orchestrator: Optional[object] = None, execution_engine: Optional[object] = None,
                 position_manager: Optional[object] = None, database: Optional[object] = None):
        self.orchestrator = orchestrator
        self.execution_engine = execution_engine
        self.position_manager = position_manager
        self.database = database

    def get_status(self) -> Dict[str, Any]:
        status = {
            'mode': getattr(self.orchestrator, 'mode', 'unknown'),
            'execution_engine': bool(self.execution_engine),
            'position_manager': bool(self.position_manager),
            'database': bool(self.database),
        }
        # MT5 connector health
        try:
            conn = getattr(self.execution_engine, 'connector', None)
            status['mt5_up'] = getattr(conn, 'is_connected', False) if conn is not None else None
        except Exception:
            status['mt5_up'] = None
        # open positions
        try:
            status['open_positions'] = len(self.position_manager.get_positions()) if self.position_manager else None
        except Exception:
            status['open_positions'] = None
        return status

    def perform_command(self, command: str, component: Optional[str], params: Dict[str, Any], actor: str) -> Dict[str, Any]:
        logger.info("Ops command requested: %s on %s by %s -> %s", command, component, actor, params)
        # Safety checks: refuse unknown commands
        if command not in ('start', 'stop', 'restart', 'dry-run-on', 'dry-run-off'):
            return {'status': 'error', 'reason': 'unknown_command'}

        # start/stop/restart orchestrator
        if component in (None, 'orchestrator'):
            orch = self.orchestrator
            if not orch:
                return {'status': 'error', 'reason': 'orchestrator_not_available'}
            try:
                if command == 'start' and hasattr(orch, 'start'):
                    orch.start()
                    return {'status': 'ok', 'action': 'started'}
                if command == 'stop' and hasattr(orch, 'stop'):
                    orch.stop()
                    return {'status': 'ok', 'action': 'stopped'}
                if command == 'restart' and hasattr(orch, 'restart'):
                    orch.restart()
                    return {'status': 'ok', 'action': 'restarted'}
                if command == 'dry-run-on' and hasattr(orch, 'set_mode'):
                    orch.set_mode('dry-run')
                    return {'status': 'ok', 'action': 'dry-run_on'}
                if command == 'dry-run-off' and hasattr(orch, 'set_mode'):
                    orch.set_mode('live')
                    return {'status': 'ok', 'action': 'dry-run_off'}
            except Exception as e:
                logger.exception('Failed to perform orchestration command')
                return {'status': 'error', 'reason': str(e)}

        # connector commands
        if component == 'connector':
            conn = getattr(self.execution_engine, 'connector', None)
            if not conn:
                return {'status': 'error', 'reason': 'connector_not_available'}
            try:
                if command == 'restart' and hasattr(conn, 'restart'):
                    conn.restart()
                    return {'status': 'ok', 'action': 'connector_restarted'}
                if command == 'stop' and hasattr(conn, 'stop'):
                    conn.stop()
                    return {'status': 'ok', 'action': 'connector_stopped'}
                if command == 'start' and hasattr(conn, 'start'):
                    conn.start()
                    return {'status': 'ok', 'action': 'connector_started'}
            except Exception as e:
                logger.exception('Failed to perform connector command')
                return {'status': 'error', 'reason': str(e)}

        return {'status': 'error', 'reason': 'unsupported_component_or_action'}
