"""
Cthulu Trade CLI

Command-line interface for placing manual trades through Cthulu.
"""

import argparse
import json
import sys
from pathlib import Path

import MetaTrader5 as mt5
from cthulu import constants


def main():
    parser = argparse.ArgumentParser(
        description="Place a manual trade through Cthulu",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Cthulu-trade --symbol BTCUSD# --side BUY --volume 0.01
  Cthulu-trade --symbol EURUSD --side SELL --volume 0.1 --sl 1.0850 --tp 1.0750
  Cthulu-trade --symbol XAUUSD --side BUY --volume 0.05 --comment "Gold scalp"
  Cthulu-trade --close 485496556  # Close position by ticket
  Cthulu-trade --list  # List all open positions
        """
    )
    
    # Trade actions
    parser.add_argument('--symbol', type=str, help='Trading symbol (e.g., BTCUSD#, EURUSD)')
    parser.add_argument('--side', type=str, choices=['BUY', 'SELL', 'buy', 'sell'], 
                       help='Trade direction')
    parser.add_argument('--volume', type=float, help='Lot size (e.g., 0.01, 0.1, 1.0)')
    parser.add_argument('--sl', type=float, default=0.0, help='Stop loss price')
    parser.add_argument('--tp', type=float, default=0.0, help='Take profit price')
    parser.add_argument('--comment', type=str, default='Cthulu manual trade', 
                       help='Trade comment')
    
    # Position management
    parser.add_argument('--close', type=int, metavar='TICKET',
                       help='Close position by ticket number')
    parser.add_argument('--close-all', action='store_true',
                       help='Close all open positions')
    parser.add_argument('--list', action='store_true', dest='list_positions',
                       help='List all open positions')
    
    # Config
    parser.add_argument('--config', type=str, default='config.json',
                       help='Path to Cthulu config file')
    parser.add_argument('--dry-run', action='store_true',
                       help='Simulate without placing real trades')
    
    args = parser.parse_args()
    
    # Load config for MT5 connection
    config_path = Path(args.config)
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
    else:
        print(f"Warning: Config file not found: {config_path}")
        config = {}
    
    # Initialize MT5
    mt5_config = config.get('mt5', {})
    
    if not mt5.initialize(
        path=mt5_config.get('path'),
        login=mt5_config.get('login'),
        password=mt5_config.get('password'),
        server=mt5_config.get('server'),
        timeout=mt5_config.get('timeout', 60000)
    ):
        print(f"❌ Failed to initialize MT5: {mt5.last_error()}")
        return 1
    
    account = mt5.account_info()
    print(f"Connected to MT5 | Account: {account.login} | Balance: ${account.balance:.2f}")
    
    try:
        # List positions
        if args.list_positions:
            positions = mt5.positions_get()
            if not positions:
                print("\nNo open positions")
            else:
                print(f"\n{'Ticket':<12} {'Symbol':<10} {'Side':<5} {'Volume':<8} {'Price':<12} {'P&L':>10}")
                print("-" * 65)
                for p in positions:
                    side = "BUY" if p.type == 0 else "SELL"
                    print(f"{p.ticket:<12} {p.symbol:<10} {side:<5} {p.volume:<8.2f} {p.price_open:<12.5f} ${p.profit:>9.2f}")
                print("-" * 65)
                total_pnl = sum(p.profit for p in positions)
                print(f"{'Total':<47} ${total_pnl:>9.2f}")
            mt5.shutdown()
            return 0
        
        # Close position
        if args.close:
            position = mt5.positions_get(ticket=args.close)
            if not position:
                print(f"❌ Position #{args.close} not found")
                mt5.shutdown()
                return 1
            
            pos = position[0]
            close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(pos.symbol).bid if pos.type == 0 else mt5.symbol_info_tick(pos.symbol).ask
            
            request = {
                'action': mt5.TRADE_ACTION_DEAL,
                'symbol': pos.symbol,
                'volume': pos.volume,
                'type': close_type,
                'position': pos.ticket,
                'price': price,
                'deviation': 20,
                'magic': constants.DEFAULT_MAGIC,
                'comment': 'Cthulu close',
                'type_time': mt5.ORDER_TIME_GTC,
                'type_filling': mt5.ORDER_FILLING_IOC,
            }
            
            if args.dry_run:
                print(f"[DRY RUN] Would close position #{pos.ticket}")
                mt5.shutdown()
                return 0
            
            result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"✅ Position #{pos.ticket} closed | P&L: ${pos.profit:.2f}")
            else:
                print(f"❌ Failed to close: {result.comment}")
            
            mt5.shutdown()
            return 0
        
        # Close all positions
        if args.close_all:
            positions = mt5.positions_get()
            if not positions:
                print("No positions to close")
                mt5.shutdown()
                return 0
            
            for pos in positions:
                close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
                price = mt5.symbol_info_tick(pos.symbol).bid if pos.type == 0 else mt5.symbol_info_tick(pos.symbol).ask
                
                request = {
                    'action': mt5.TRADE_ACTION_DEAL,
                    'symbol': pos.symbol,
                    'volume': pos.volume,
                    'type': close_type,
                    'position': pos.ticket,
                    'price': price,
                    'deviation': 20,
                    'magic': constants.DEFAULT_MAGIC,
                    'comment': 'Cthulu close all',
                    'type_time': mt5.ORDER_TIME_GTC,
                    'type_filling': mt5.ORDER_FILLING_IOC,
                }
                
                if args.dry_run:
                    print(f"[DRY RUN] Would close #{pos.ticket} {pos.symbol}")
                    continue
                
                result = mt5.order_send(request)
                if result.retcode == mt5.TRADE_RETCODE_DONE:
                    print(f"✅ Closed #{pos.ticket} {pos.symbol} | P&L: ${pos.profit:.2f}")
                else:
                    print(f"❌ Failed #{pos.ticket}: {result.comment}")
            
            mt5.shutdown()
            return 0
        
        # Place new trade
        if args.symbol and args.side and args.volume:
            symbol = args.symbol
            side = args.side.upper()
            volume = args.volume
            
            # Get current price
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                print(f"❌ Symbol not found: {symbol}")
                mt5.shutdown()
                return 1
            
            price = tick.ask if side == 'BUY' else tick.bid
            order_type = mt5.ORDER_TYPE_BUY if side == 'BUY' else mt5.ORDER_TYPE_SELL
            
            request = {
                'action': mt5.TRADE_ACTION_DEAL,
                'symbol': symbol,
                'volume': volume,
                'type': order_type,
                'price': price,
                'sl': args.sl,
                'tp': args.tp,
                'deviation': 20,
                'magic': constants.DEFAULT_MAGIC,
                'comment': args.comment,
                'type_time': mt5.ORDER_TIME_GTC,
                'type_filling': mt5.ORDER_FILLING_IOC,
            }
            
            print(f"\n{side} {volume} lots of {symbol} @ {price:.5f}")
            if args.sl > 0:
                print(f"  Stop Loss: {args.sl}")
            if args.tp > 0:
                print(f"  Take Profit: {args.tp}")
            
            if args.dry_run:
                print("\n[DRY RUN] Order not placed")
                mt5.shutdown()
                return 0
            
            result = mt5.order_send(request)
            
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"\n✅ Order filled! Ticket: #{result.order}")
            else:
                print(f"\n❌ Order failed: {result.comment}")
                mt5.shutdown()
                return 1
        else:
            if not (args.list_positions or args.close or args.close_all):
                parser.print_help()
                print("\nError: Specify --symbol, --side, --volume for a new trade")
                print("       or use --list, --close, --close-all for position management")
        
    finally:
        mt5.shutdown()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())




