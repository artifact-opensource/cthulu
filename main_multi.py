"""
Multi-Symbol Main Entry Point
Launches the multi-symbol orchestrator with the shared Cthulu components.
"""
import argparse
import asyncio
import logging
import math
import sys
import time
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from execution_mode import ExecutionModeError, require_legacy_execution, require_trading_enabled

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


def print_banner():
    banner = """
_________   __  .__          .__
\\_   ___ \\_/  |_|  |__  __ __|  |  __ __
/    \\  \\/\\   __\\  |  \\|  |  \\  | |  |  \\
\\     \\____|  | |   Y  \\  |  /  |_|  |  /
 \\______  /|__| |___|  /____/|____/____/
        \\/           \\/

    -----------------------------
     Cthulu v5.3.0 Multi-Symbol
    -----------------------------
    """
    print(banner)


def _get_singleton_lock():
    from cthulu.__main__ import _singleton_lock

    return _singleton_lock


class _MultiRiskEvaluatorAdapter:
    def __init__(self, components):
        self.components = components

    def evaluate(self, signal):
        if not isinstance(signal, dict):
            return {"approved": False, "reason": "Signal is invalid", "lot_size": 0.0}

        from cthulu.strategy.base import Signal, SignalType

        raw_direction = signal.get("direction") or signal.get("side")
        if hasattr(raw_direction, "value"):
            raw_direction = raw_direction.value
        direction = str(raw_direction or "").strip().lower()
        if direction in {"buy", "long"}:
            signal_side = SignalType.LONG
            order_direction = "buy"
        elif direction in {"sell", "short"}:
            signal_side = SignalType.SHORT
            order_direction = "sell"
        else:
            return {
                "approved": False,
                "reason": f"Signal direction is invalid: {raw_direction!r}",
                "lot_size": 0.0,
            }

        symbol = signal.get("symbol")
        if not symbol:
            return {"approved": False, "reason": "Signal symbol is missing", "lot_size": 0.0}

        try:
            account_info = self.components.connector.get_account_info()
            if not isinstance(account_info, dict):
                raise RuntimeError("Account information is unavailable")

            positions = self.components.position_manager.monitor_positions()
            if positions is None:
                raise RuntimeError("Open positions are unavailable")

            from core.multi_symbol import MultiSymbolOrchestrator, _configured_timeframe

            symbol_key = MultiSymbolOrchestrator._symbol_key
            current_positions = sum(
                1 for position in positions
                if symbol_key(getattr(position, "symbol", "")) == symbol_key(symbol)
            )

            entry_price = signal.get("price")
            if entry_price is None:
                entry_price = signal.get("entry_price")
            stop_loss = signal.get("stop_loss")
            if stop_loss is None:
                stop_loss = signal.get("sl")
            take_profit = signal.get("take_profit")
            if take_profit is None:
                take_profit = signal.get("tp")
            confidence = float(signal.get("confidence", 0.5))
            if not math.isfinite(confidence):
                raise ValueError("Signal confidence must be finite")

            timeframe = signal.get("timeframe") or _configured_timeframe(self.components.config)
            metadata = signal.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}

            risk_signal = Signal(
                id=str(signal.get("id") or f"multi-{symbol}-{datetime.now().timestamp()}"),
                timestamp=datetime.now(),
                symbol=str(symbol),
                timeframe=str(timeframe),
                side=signal_side,
                action=order_direction.upper(),
                price=float(entry_price) if entry_price is not None else None,
                stop_loss=float(stop_loss) if stop_loss is not None else None,
                take_profit=float(take_profit) if take_profit is not None else None,
                confidence=confidence,
                reason=str(signal.get("reason") or signal.get("strategy") or "Multi-symbol signal"),
                metadata=metadata,
            )
            approved, reason, lot_size = self.components.risk_manager.approve(
                risk_signal,
                account_info,
                current_positions,
            )
            lot_size = float(lot_size)
            if not approved:
                return {"approved": False, "reason": str(reason), "lot_size": 0.0}
            if not math.isfinite(lot_size) or lot_size <= 0:
                return {
                    "approved": False,
                    "reason": "Risk evaluator returned an invalid position size",
                    "lot_size": 0.0,
                }
            return {"approved": True, "reason": str(reason), "lot_size": lot_size}
        except Exception as exc:
            logger.exception("Multi-symbol risk evaluation failed for %s", symbol)
            return {"approved": False, "reason": str(exc), "lot_size": 0.0}


class _MultiTradeManagerAdapter:
    FAILED_ORDER_COOLDOWN_SECONDS = 30 * 60

    def __init__(self, components):
        self.components = components
        self._failed_symbol_retry_until = {}

    @staticmethod
    def _failed_symbol_key(symbol):
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("Failed-order cooldown requires a symbol")
        return symbol.strip().casefold()

    def get_failed_symbol_remaining(self, symbol):
        symbol_key = self._failed_symbol_key(symbol)
        retry_until = self._failed_symbol_retry_until.get(symbol_key)
        if retry_until is None:
            return 0.0

        remaining = retry_until - time.monotonic()
        if remaining <= 0:
            self._failed_symbol_retry_until.pop(symbol_key, None)
            return 0.0
        return remaining

    def record_failed_order(self, symbol):
        symbol_key = self._failed_symbol_key(symbol)
        self._failed_symbol_retry_until[symbol_key] = (
            time.monotonic() + self.FAILED_ORDER_COOLDOWN_SECONDS
        )

    def get_all_positions(self):
        return self.components.position_manager.monitor_positions()

    def register_trade(self, ticket, signal, result):
        try:
            from cthulu.position.manager import PositionInfo as ManagedPositionInfo
            from cthulu.position.tracker import PositionInfo as TrackedPositionInfo

            try:
                details = self.components.connector.get_position_by_ticket(int(ticket))
            except Exception:
                logger.exception("Could not retrieve filled position %s; using order details", ticket)
                details = None
            if not isinstance(details, dict):
                details = {}

            symbol = str(details.get("symbol") or signal.get("symbol") or "")
            raw_type = details.get("type")
            side = (
                "buy"
                if raw_type in (0, "0", "buy", "BUY")
                else str(signal.get("direction") or signal.get("side") or "sell").lower()
            )
            if side in {"long", "buy"}:
                side = "buy"
            elif side in {"short", "sell"}:
                side = "sell"
            else:
                raise ValueError(f"Unrecognized position side: {side!r}")

            volume_value = details.get("volume")
            if volume_value is None:
                volume_value = result.get("volume")
            volume = float(volume_value)
            price_value = details.get("price_open")
            if price_value is None:
                price_value = result.get("price")
            if price_value is None:
                price_value = signal.get("price") or signal.get("entry_price")
            open_price = float(price_value)
            current_price = float(details.get("price_current") or open_price)
            stop_loss = details.get("sl")
            if stop_loss is None:
                stop_loss = signal.get("stop_loss")
            take_profit = details.get("tp")
            if take_profit is None:
                take_profit = signal.get("take_profit")
            profit = float(details.get("profit") or 0.0)
            position_ticket = int(ticket)

            tracked_position = TrackedPositionInfo(
                ticket=position_ticket,
                symbol=symbol,
                type=side,
                volume=volume,
                open_price=open_price,
                current_price=current_price,
                sl=stop_loss,
                tp=take_profit,
                profit=profit,
            )
            self.components.position_tracker.track_position(tracked_position)
            self.components.position_lifecycle.persist_position(tracked_position)

            managed_position = ManagedPositionInfo(
                ticket=position_ticket,
                symbol=symbol,
                volume=volume,
                open_price=open_price,
                current_price=current_price,
                side=side.upper(),
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
            self.components.position_manager.add_position(managed_position)
            return True
        except Exception:
            logger.exception("Could not track filled multi-symbol position %s", ticket)
            return False


class _MultiExecutionEngineAdapter:
    def __init__(self, components, engine):
        self.components = components
        self.engine = engine

    def execute(self, signal, lot_size):
        direction = str(signal.get("direction") or signal.get("side") or "").lower()
        if direction in {"long", "buy"}:
            direction = "buy"
        elif direction in {"short", "sell"}:
            direction = "sell"
        else:
            return {"success": False, "error": "Signal direction is invalid"}

        try:
            ticket = self.engine.execute_order(
                symbol=signal["symbol"],
                order_type=direction,
                volume=lot_size,
                sl=signal.get("stop_loss"),
                tp=signal.get("take_profit"),
                comment=str(signal.get("strategy") or "multi-symbol"),
            )
        except Exception as exc:
            logger.exception("Multi-symbol order execution failed for %s", signal.get("symbol"))
            return {"success": False, "error": str(exc)}
        if not ticket:
            return {"success": False, "error": "Execution engine did not return a filled ticket"}

        price = signal.get("price")
        if price is None:
            price = signal.get("entry_price")
        return {
            "success": True,
            "ticket": int(ticket),
            "price": price,
            "volume": lot_size,
        }

    def close_position(self, ticket, reason=""):
        try:
            tracked_position = self.components.position_tracker.get_position(ticket)
            if tracked_position is not None:
                closed = self.components.position_lifecycle.close_position(ticket, reason=reason)
            else:
                result = self.engine.close_position(ticket)
                if hasattr(result, "status"):
                    from cthulu.execution.engine import OrderStatus

                    closed = result.status == OrderStatus.FILLED
                else:
                    closed = bool(result)
                if closed:
                    self.components.position_manager.remove_position(ticket)
                    self.components.database.remove_position(ticket)
            if not closed:
                logger.error("Could not close position %s after exit signal: %s", ticket, reason)
            return bool(closed)
        except Exception:
            logger.exception("Multi-symbol close failed for position %s", ticket)
            return False


class _MultiExitCoordinatorAdapter:
    def __init__(self, strategies):
        from exit.coordinator import ExitCoordinator

        self.coordinator = ExitCoordinator()
        for strategy in strategies or []:
            self.coordinator.register_strategy(strategy)

    def evaluate(self, position, current_price, indicators):
        from exit.exit_manager import ExitDecision

        current_data = dict(indicators or {})
        current_data["current_price"] = current_price
        current_data.setdefault("close", current_price)
        decision = self.coordinator.evaluate_exit(position, current_data=current_data)
        return decision or ExitDecision(
            should_exit=False,
            strategy_name="none",
            reason="No exit strategy triggered",
            priority=0,
        )


def _prepare_multi_components(components):
    required = (
        "connector",
        "risk_manager",
        "execution_engine",
        "position_tracker",
        "position_manager",
        "position_lifecycle",
        "trade_adoption_manager",
        "database",
    )
    missing = [name for name in required if not hasattr(components, name)]
    if missing:
        raise RuntimeError(f"Bootstrap is missing Multi-symbol components: {', '.join(missing)}")
    if components.position_manager is None:
        raise RuntimeError("Position manager failed to initialize")

    engine = components.execution_engine
    components.mt5_connector = components.connector
    components.risk_evaluator = _MultiRiskEvaluatorAdapter(components)
    components.trade_manager = _MultiTradeManagerAdapter(components)
    components.execution_engine = _MultiExecutionEngineAdapter(components, engine)
    components.exit_coordinator = _MultiExitCoordinatorAdapter(
        getattr(components, "exit_strategies", None)
    )
    components.lifecycle_manager = components.trade_adoption_manager


def _build_parser():
    parser = argparse.ArgumentParser(description="Start the Cthulu multi-symbol engine")
    parser.add_argument("config_positional", nargs="?", help="Configuration file path")
    parser.add_argument("--config", dest="config_option", help="Configuration file path")
    parser.add_argument("--mindset", default=None)
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--enable-ml", action="store_true", default=None)
    return parser


async def main(argv=None):
    try:
        require_trading_enabled()
        require_legacy_execution()
    except ExecutionModeError as exc:
        logger.error("Multi-symbol engine not started: %s", exc)
        return 1

    parser = _build_parser()
    args = parser.parse_args(argv)
    if (
        args.config_option
        and args.config_positional
        and args.config_option != args.config_positional
    ):
        parser.error("Positional config and --config must match when both are provided")
    config_path = args.config_option or args.config_positional or "config_multi.json"

    components = None
    connected = False
    lock = _get_singleton_lock()
    lock_acquired = False
    try:
        if not lock.acquire():
            logger.error("Another Cthulu engine instance is already running")
            return 1
        lock_acquired = True

        from core.bootstrap import CthuluBootstrap

        logger.info("Phase 1: Bootstrapping multi-symbol system...")
        bootstrap = CthuluBootstrap(logger=logger)
        components = bootstrap.bootstrap(config_path, args)
        watchlist = components.config.get("watchlist")
        if not isinstance(watchlist, list) or len(watchlist) < 2:
            raise ValueError("Multi-symbol configuration must contain at least two watchlist entries")
        _prepare_multi_components(components)

        logger.info("Phase 2: Connecting to MT5 bridge...")
        if not components.connector.connect():
            raise ConnectionError("Failed to connect to MT5 bridge")
        connected = True
        if not isinstance(components.connector.get_account_info(), dict):
            raise ConnectionError("MT5 account information is unavailable")

        print_banner()
        logger.info("Phase 3: Starting Multi-symbol orchestrator...")
        from core.multi_symbol import MultiSymbolOrchestrator

        orchestrator = MultiSymbolOrchestrator(components, components.config)
        await orchestrator.run()
        return 0
    except KeyboardInterrupt:
        logger.info("Shutdown requested...")
        return 0
    except Exception:
        logger.exception("Multi-symbol startup or runtime failed")
        return 1
    finally:
        if components is not None:
            if connected:
                try:
                    components.connector.disconnect()
                except Exception:
                    logger.exception("Failed to disconnect from MT5 during shutdown")
            database = getattr(components, "database", None)
            if database is not None:
                try:
                    database.close()
                except Exception:
                    logger.exception("Failed to close the database during shutdown")
        if lock_acquired:
            lock.release()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
