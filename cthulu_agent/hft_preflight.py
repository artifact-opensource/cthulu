"""Read-only MT5 safety checks for the live HFT launcher."""
from __future__ import annotations

import json
import math
import sys

from . import envfile
from .broker import MT5Broker


def main() -> int:
    envfile.load_env()
    broker = MT5Broker()
    try:
        broker.connect()
        account = broker.account()
        info = broker.mt5.account_info()
        positions = broker.positions()
        pending = broker.pending()
        symbols = broker.tradeable_symbols(0.0025)
        total_risk = 0.0
        failed_risk_checks = 0
        unprotected = 0

        for position in positions:
            if not position.sl:
                unprotected += 1
                continue
            order_type = broker.mt5.ORDER_TYPE_BUY if position.side == "buy" else broker.mt5.ORDER_TYPE_SELL
            result = broker.mt5.order_calc_profit(
                order_type,
                broker._sym(position.symbol),
                position.volume,
                position.price_open,
                position.sl,
            )
            if result is None or not math.isfinite(float(result)):
                failed_risk_checks += 1
            else:
                total_risk += max(0.0, -float(result))

        pending_sides = {
            "buy_limit": broker.mt5.ORDER_TYPE_BUY,
            "buy_stop": broker.mt5.ORDER_TYPE_BUY,
            "buy_stop_limit": broker.mt5.ORDER_TYPE_BUY,
            "sell_limit": broker.mt5.ORDER_TYPE_SELL,
            "sell_stop": broker.mt5.ORDER_TYPE_SELL,
            "sell_stop_limit": broker.mt5.ORDER_TYPE_SELL,
        }
        for order in pending:
            if not order.sl:
                unprotected += 1
                continue
            order_type = pending_sides.get(order.kind)
            result = (
                broker.mt5.order_calc_profit(
                    order_type,
                    broker._sym(order.symbol),
                    order.volume,
                    order.price,
                    order.sl,
                )
                if order_type is not None
                else None
            )
            if result is None or not math.isfinite(float(result)):
                failed_risk_checks += 1
            else:
                total_risk += max(0.0, -float(result))

        active_orders = len(positions) + len(pending)
        risk_pct = total_risk / account.equity * 100 if account.equity > 0 else None
        checks = {
            "live_account": account.real,
            "trading_allowed": bool(getattr(info, "trade_allowed", False)),
            "universe_available": bool(symbols),
            "active_order_cap": active_orders <= 10,
            "all_orders_protected": unprotected == 0,
            "risk_calculation_complete": failed_risk_checks == 0 and risk_pct is not None,
            "aggregate_risk_cap": risk_pct is not None and risk_pct <= 5.0,
        }
        result = {
            "account_mode": "live" if account.real else "demo",
            "checks": checks,
            "open_positions": len(positions),
            "pending_orders": len(pending),
            "active_orders": active_orders,
            "tradable_symbols": len(symbols),
            "unprotected_orders_or_positions": unprotected,
            "risk_calculations_failed": failed_risk_checks,
            "aggregate_stop_risk_pct": round(risk_pct, 3) if risk_pct is not None else None,
        }
        print(json.dumps(result, sort_keys=True))
        if not all(checks.values()):
            print("HFT preflight failed; services were not started.", file=sys.stderr)
            return 1
        return 0
    except Exception as exc:
        print(json.dumps({"preflight_error": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        broker.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
