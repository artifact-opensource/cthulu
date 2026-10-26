"""
Cthulu Interactive Setup Wizard

A friendly, non-overwhelming configuration wizard that helps users configure
Cthulu's key trading parameters before starting.
Designed to be:
- Comprehensive yet concise
- Smart with defaults
- Non-destructive to existing config

Usage:
    from config.wizard import run_setup_wizard
    config = run_setup_wizard(config_path)
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, List
from copy import deepcopy

# Available mindsets as a small local fallback (can be overridden elsewhere)
MINDSETS = {
    "1": ("conservative", "Lower risk, wider stops, capital preservation"),
    "2": ("balanced", "Moderate risk, standard settings (recommended)"),
    "3": ("aggressive", "Higher risk, faster entries, tighter stops"),
    "4": ("ultra_aggressive", "Ultra high-frequency scalping with dynamic strategies (expert traders)"),
}

TIMEFRAMES = {
    "1": ("TIMEFRAME_M1", "1 Minute"),
    "2": ("TIMEFRAME_M5", "5 Minutes"),
    "3": ("TIMEFRAME_M15", "15 Minutes"),
    "4": ("TIMEFRAME_M30", "30 Minutes"),
    "5": ("TIMEFRAME_H1", "1 Hour (recommended)"),
    "6": ("TIMEFRAME_H4", "4 Hours"),
    "7": ("TIMEFRAME_D1", "Daily"),
    "8": ("TIMEFRAME_W1", "Weekly"),
    "9": ("TIMEFRAME_MN1", "Monthly"),
}

COMMON_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD",
    "EURUSD#", "GBPUSD#", "XAUUSD#", "BTCUSD#",
]


def clear_screen():
    """Clear terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_banner():
    """Print Cthulu setup banner."""
    banner = r"""
_________   __  .__          .__         
\_   ___ \_/  |_|  |__  __ __|  |  __ __ 
/    \  \/\   __\  |  \|  |  \  | |  |  \
\     \____|  | |   Y  \  |  /  |_|  |  /
 \______  /|__| |___|  /____/|____/____/ 
        \/           \/                  
                                         
    ─────────────────────────────
           Cthulu v5.3.0
    Interactive Setup Wizard
    """
    try:
        safe_print("\033[96m" + banner + "\033[0m")
    except Exception:
        # Fallback to a plain ASCII banner
        safe_print("*** Cthulu v5.3.0 - Interactive Setup Wizard ***")


def print_section(title: str, step: int = None, total_steps: int = None):
    """Print a section header with optional progress indicator."""
    if step is not None and total_steps is not None:
        progress = f" [{step}/{total_steps}]"
        title_with_progress = f"{title}{progress}"
    else:
        title_with_progress = title

    safe_print(f"\n\033[93m{'═' * 60}\033[0m")
    safe_print(f"\033[93m  {title_with_progress}\033[0m")
    safe_print(f"\033[93m{'═' * 60}\033[0m\n")


def print_option(key: str, label: str, description: str = "", selected: bool = False):
    """Print a menu option with enhanced visual styling."""
    if selected:
        marker = "\033[92m●\033[0m"  # Green filled circle for selected
        key_color = "\033[92m"  # Green key for selected
    else:
        marker = "\033[90m○\033[0m"  # Gray empty circle for unselected
        key_color = "\033[96m"  # Cyan key for unselected

    if description:
        safe_print(f"  {key_color}[{key}]\033[0m {marker} \033[97m{label}\033[0m - \033[90m{description}\033[0m")
    else:
        safe_print(f"  {key_color}[{key}]\033[0m {marker} \033[97m{label}\033[0m")


import sys


def safe_print(text: str):
    """Print text but gracefully handle UnicodeEncodeError on restricted consoles."""
    try:
        print(text)
    except UnicodeEncodeError:
        # Replace non-ascii characters to avoid crashing terminals with narrow encodings
        try:
            safe = text.encode('ascii', errors='replace').decode('ascii')
            print(safe)
        except Exception:
            # Last resort: strip non-printable characters
            filtered = ''.join(ch if ord(ch) < 128 else '?' for ch in text)
            print(filtered)


def print_success(msg: str):
    """Print a success message with green checkmark."""
    safe_print(f"\033[92m  ✓ {msg}\033[0m")


def print_info(msg: str):
    """Print an info message with blue info icon."""
    safe_print(f"\033[94m  ℹ {msg}\033[0m")


def print_warning(msg: str):
    """Print a warning message with yellow warning icon."""
    safe_print(f"\033[93m  ⚠ {msg}\033[0m")


def print_error(msg: str):
    """Print an error message with red X icon."""
    safe_print(f"\033[91m  ✗ {msg}\033[0m")


class WizardCancelled(Exception):
    """Raised when the wizard is cancelled by the user or input stream closes."""


def get_input(prompt: str, default: str = "") -> str:
    """Get user input with optional default.

    Handles EOF/interrupts gracefully by raising WizardCancelled so callers can
    abort the interactive wizard without an unhandled traceback.
    """
    try:
        if default:
            result = input(f"  {prompt} [{default}]: ").strip()
            return result if result else default
        return input(f"  {prompt}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n\nInput stream closed or interrupted. Cancelling setup.")
        raise WizardCancelled()


def get_float(prompt: str, default: float, min_val: float = 0, max_val: float = float('inf')) -> float:
    """Get a float input with validation."""
    while True:
        try:
            result = get_input(prompt, str(default))
            val = float(result)
            if min_val <= val <= max_val:
                return val
            print(f"\033[91m  Please enter a value between {min_val} and {max_val}\033[0m")
        except ValueError:
            print("\033[91m  Please enter a valid number\033[0m")


def get_int(prompt: str, default: int, min_val: int = 0, max_val: int = 100) -> int:
    """Get an integer input with validation."""
    while True:
        try:
            result = get_input(prompt, str(default))
            val = int(result)
            if min_val <= val <= max_val:
                return val
            print(f"\033[91m  Please enter a value between {min_val} and {max_val}\033[0m")
        except ValueError:
            print("\033[91m  Please enter a valid integer\033[0m")


def choose_mindset() -> str:
    """Let user choose a trading mindset."""
    print_section("STEP 1: Trading Mindset", 1, 7)
    print("  Choose your risk tolerance and trading style:\n")
    
    for key, (name, desc) in MINDSETS.items():
        print_option(key, name.capitalize(), desc)
    
    print()
    while True:
        choice = get_input("Select mindset (1-4)", "2")
        if choice in MINDSETS:
            selected = MINDSETS[choice][0]
            print_success(f"Selected: {selected.capitalize()}")
            return selected
        print("\033[91m  Invalid choice. Enter 1, 2, 3, or 4.\033[0m")


def choose_symbol(current: str = "EURUSD") -> str:
    """Let user choose or enter a trading symbol."""
    print_section("STEP 2: Trading Symbol", 2, 7)
    print("  Enter the symbol you want to trade.\n")
    print(f"  \033[90mCommon symbols: {', '.join(COMMON_SYMBOLS[:5])}\033[0m")
    print(f"  \033[90mNote: Some brokers use suffixes like # or .m\033[0m\n")
    
    symbol = get_input("Symbol", current).upper()
    print_success(f"Symbol: {symbol}")
    return symbol


def choose_timeframe(current: str = "TIMEFRAME_H1") -> str:
    """Let user choose a timeframe."""
    print_section("STEP 3: Timeframe", 3, 7)
    print("  Select your trading timeframe:\n")
    
    for key, (tf, desc) in TIMEFRAMES.items():
        selected = tf == current
        print_option(key, desc, "", selected)
    
    print()
    print_info("You may choose multiple timeframes by comma-separating numbers (e.g., 2,5 for M15 and H1).")
    while True:
        choice = get_input("Select timeframe(s) (1-9)", "5")
        parts = [p.strip() for p in choice.split(',') if p.strip()]
        if all(p in TIMEFRAMES for p in parts):
            # Return single timeframe if one chosen, else return comma-separated list
            if len(parts) == 1:
                selected_tf = TIMEFRAMES[parts[0]][0]
                print_success(f"Timeframe: {TIMEFRAMES[parts[0]][1]}")
                return selected_tf
            else:
                selected = [TIMEFRAMES[p][0] for p in parts]
                labels = [TIMEFRAMES[p][1] for p in parts]
                print_success(f"Timeframes: {', '.join(labels)}")
                return ",".join(selected)
        print("\033[91m  Invalid choice. Enter 1-9 or comma-separated list.\033[0m")


def configure_risk(current_risk: Dict[str, Any]) -> Dict[str, Any]:
    """Configure risk management settings."""
    print_section("STEP 4: Risk Management", 4, 7)
    print("  Set your risk limits to protect your capital.\n")
    
    risk = deepcopy(current_risk)
    
    # Daily loss limit
    print_info("Maximum daily loss - trading stops if this limit is hit")
    risk['max_daily_loss'] = get_float(
        "Max daily loss ($)", 
        current_risk.get('max_daily_loss', 50.0),
        min_val=1, max_val=10000
    )
    
    # Position size percentage
    print()
    print_info("Position size as % of equity per trade")
    risk['position_size_pct'] = get_float(
        "Position size (%)", 
        current_risk.get('position_size_pct', 2.0),
        min_val=0.1, max_val=10
    )
    
    # Max positions
    print()
    print_info("Maximum simultaneous open positions")
    risk['max_total_positions'] = get_int(
        "Max positions", 
        current_risk.get('max_total_positions', 3),
        min_val=1, max_val=10
    )
    
    print()
    print_success(f"Daily loss limit: ${risk['max_daily_loss']}")
    print_success(f"Position size: {risk['position_size_pct']}% of equity")
    print_success(f"Max positions: {risk['max_total_positions']}")
    
    return risk


def configure_indicators(current_indicators: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Configure technical indicators."""
    print_section("STEP 6: Technical Indicators (Optional)", 6, 7)
    print("  Add technical indicators to enhance your strategy:\n")
    
    indicators = []
    
    print_option("1", "RSI", "Relative Strength Index - momentum oscillator")
    print_option("2", "MACD", "Moving Average Convergence Divergence")
    print_option("3", "Bollinger Bands", "Volatility indicator")
    print_option("4", "Stochastic", "Momentum indicator")
    print_option("5", "ADX", "Average Directional Index - trend strength")
    print_option("6", "Supertrend", "Trend-following indicator")
    print_option("7", "VWAP", "Volume Weighted Average Price")
    print_option("8", "VPT", "Volume Price Trend - volume-weighted momentum")
    print_option("9", "Volume Oscillator", "Volume momentum indicator")
    print_option("10", "Price Volume Trend", "Cumulative volume-price relationship")
    print_option("11", "ATR", "Average True Range - volatility measure")
    print_option("12", "Williams %R", "Momentum indicator for overbought/oversold")
    print_option("0", "None", "Skip indicators")
    print()
    
    choice = get_input("Select indicators (comma-separated, e.g., 1,2,6) or 0 for none, 00 for all 12", "0")
    
    if choice == "00":
        # Add all indicators
        indicators = [
            {'type': 'rsi', 'params': {'period': 14, 'overbought': 70, 'oversold': 30}},
            {'type': 'macd', 'params': {'fast_period': 12, 'slow_period': 26, 'signal_period': 9}},
            {'type': 'bollinger', 'params': {'period': 20, 'std_dev': 2.0}},
            {'type': 'stochastic', 'params': {'k_period': 14, 'd_period': 3, 'smooth': 3}},
            {'type': 'adx', 'params': {'period': 14}},
            {'type': 'supertrend', 'params': {'atr_period': 10, 'atr_multiplier': 3.0}},
            {'type': 'vwap', 'params': {}},
            {'type': 'vpt', 'params': {}},
            {'type': 'volume_oscillator', 'params': {'short_period': 5, 'long_period': 10}},
            {'type': 'price_volume_trend', 'params': {}},
            {'type': 'atr', 'params': {'period': 14}},
            {'type': 'williams_r', 'params': {'period': 14}}
        ]
        print_success("Added all 12 indicators")
    elif choice != "0":
        for ind_choice in choice.split(','):
            ind_choice = ind_choice.strip()
            
            if ind_choice == "1":
                period = get_int("RSI period", 14, min_val=5, max_val=50)
                indicators.append({
                    'type': 'rsi',
                    'params': {'period': period, 'overbought': 70, 'oversold': 30}
                })
                print_success(f"Added RSI with period {period}")
                
            elif ind_choice == "2":
                indicators.append({
                    'type': 'macd',
                    'params': {'fast_period': 12, 'slow_period': 26, 'signal_period': 9}
                })
                print_success("Added MACD with standard settings")
                
            elif ind_choice == "3":
                period = get_int("Bollinger Bands period", 20, min_val=10, max_val=50)
                std_dev = get_float("Standard deviations", 2.0, min_val=1.0, max_val=3.0)
                indicators.append({
                    'type': 'bollinger',
                    'params': {'period': period, 'std_dev': std_dev}
                })
                print_success(f"Added Bollinger Bands ({period}, {std_dev})")
                
            elif ind_choice == "4":
                indicators.append({
                    'type': 'stochastic',
                    'params': {'k_period': 14, 'd_period': 3, 'smooth': 3}
                })
                print_success("Added Stochastic oscillator")
                
            elif ind_choice == "5":
                period = get_int("ADX period", 14, min_val=10, max_val=30)
                indicators.append({
                    'type': 'adx',
                    'params': {'period': period}
                })
                print_success(f"Added ADX with period {period}")
                
            elif ind_choice == "6":
                period = get_int("Supertrend ATR period", 10, min_val=5, max_val=20)
                multiplier = get_float("ATR multiplier", 3.0, min_val=1.0, max_val=5.0)
                indicators.append({
                    'type': 'supertrend',
                    'params': {'atr_period': period, 'atr_multiplier': multiplier}
                })
                print_success(f"Added Supertrend ({period}, {multiplier})")
                
            elif ind_choice == "7":
                indicators.append({
                    'type': 'vwap',
                    'params': {}
                })
                print_success("Added VWAP")
                
            elif ind_choice == "8":
                indicators.append({
                    'type': 'vpt',
                    'params': {}
                })
                print_success("Added Volume Price Trend (VPT)")
                
            elif ind_choice == "9":
                short_period = get_int("Volume Oscillator short period", 5, min_val=3, max_val=20)
                long_period = get_int("Volume Oscillator long period", 10, min_val=5, max_val=50)
                indicators.append({
                    'type': 'volume_oscillator',
                    'params': {'short_period': short_period, 'long_period': long_period}
                })
                print_success(f"Added Volume Oscillator ({short_period}, {long_period})")
                
            elif ind_choice == "10":
                indicators.append({
                    'type': 'price_volume_trend',
                    'params': {}
                })
                print_success("Added Price Volume Trend")
                
            elif ind_choice == "11":
                period = get_int("ATR period", 14, min_val=5, max_val=30)
                indicators.append({
                    'type': 'atr',
                    'params': {'period': period}
                })
                print_success(f"Added ATR with period {period}")
                
            elif ind_choice == "12":
                period = get_int("Williams %R period", 14, min_val=5, max_val=30)
                indicators.append({
                    'type': 'williams_r',
                    'params': {'period': period}
                })
                print_success(f"Added Williams %R with period {period}")
    
    return indicators


def configure_strategy(current_strategy: Dict[str, Any]) -> Dict[str, Any]:
    """Configure strategy-specific settings.
    
    UPDATED: Three modes available:
    - Dynamic: Auto-selects ALL strategies/indicators (SAFE mode - Set And Forget)
    - Create Your Own: Full customization of strategies and indicators
    - Single Strategy: Use one strategy with manual indicator selection
    """
    print_section("STEP 5: Strategy Mode", 5, 7)
    
    strategy = deepcopy(current_strategy)
    params = strategy.get('params', {})
    
    # Ask which strategy mode
    print("  Choose strategy mode:\n")
    print_option("1", "🌊 Dynamic (SAFE Mode)", "Set And Forget - Auto-adapts to ALL market conditions")
    print_option("2", "🔧 Create Your Own", "Full customization - Choose YOUR strategies & indicators")
    print_option("3", "📊 Single Strategy", "Use one strategy only")
    print()
    
    mode_choice = get_input("Strategy mode (1-3)", "1")
    
    if mode_choice == "1":
        # Dynamic SAFE mode - AUTO-SELECT everything
        strategy['type'] = 'dynamic'
        strategy['dynamic_selection'] = {
            'regime_detection_enabled': True,
            'performance_tracking_enabled': True,
            'min_confidence_threshold': 0.6,
            'switch_cooldown_bars': 10
        }
        
        # Auto-include ALL strategies for dynamic mode
        strategy['strategies'] = [
            {'type': 'sma_crossover', 'params': {'fast_period': 10, 'slow_period': 30}},
            {'type': 'ema_crossover', 'params': {'fast_period': 12, 'slow_period': 26}},
            {'type': 'momentum_breakout', 'params': {'lookback_period': 20, 'breakout_threshold': 1.5}},
            {'type': 'scalping', 'params': {'quick_period': 5, 'trend_period': 20}},
            {'type': 'mean_reversion', 'params': {'bollinger_period': 20, 'bollinger_std': 2.0, 'rsi_period': 14}},
            {'type': 'trend_following', 'params': {'adx_period': 14, 'adx_threshold': 25, 'supertrend_period': 10}},
            {'type': 'rsi_reversal', 'params': {'rsi_overbought': 75, 'rsi_oversold': 25}}
        ]
        
        # Auto-include ALL indicators for dynamic mode
        strategy['auto_indicators'] = True  # Flag for bootstrap to add all indicators
        
        print()
        print_success("🌊 SAFE Mode Enabled - Set And Forget Engine")
        print_info("✓ ALL 7 strategies auto-selected and rotating based on market regime")
        print_info("✓ ALL indicators auto-enabled for maximum market awareness")
        print_info("✓ System will autonomously adapt to ANY market condition")
        
    elif mode_choice == "2":
        # Create Your Own mode - FULL CUSTOMIZATION
        strategy['type'] = 'dynamic'
        strategy['dynamic_selection'] = {
            'regime_detection_enabled': True,
            'performance_tracking_enabled': True,
            'min_confidence_threshold': 0.6,
            'switch_cooldown_bars': 10
        }
        
        print()
        print("  " + "="*50)
        print("  🔧 CREATE YOUR OWN - Strategy Selection")
        print("  " + "="*50)
        print("  Select which strategies to include in your custom mix:\n")
        
        available_strategies = [
            ('sma_crossover', 'SMA Crossover', 'Simple MA crossover', {'fast_period': 10, 'slow_period': 30}),
            ('ema_crossover', 'EMA Crossover', 'Exponential MA crossover', {'fast_period': 12, 'slow_period': 26}),
            ('momentum_breakout', 'Momentum Breakout', 'Price momentum detection', {'lookback_period': 20, 'breakout_threshold': 1.5}),
            ('scalping', 'Scalping', 'Fast scalping', {'quick_period': 5, 'trend_period': 20}),
            ('mean_reversion', 'Mean Reversion', 'Bollinger bounce', {'bollinger_period': 20, 'bollinger_std': 2.0, 'rsi_period': 14}),
            ('trend_following', 'Trend Following', 'ADX trend', {'adx_period': 14, 'adx_threshold': 25, 'supertrend_period': 10}),
            ('rsi_reversal', 'RSI Reversal', 'RSI reversals', {'rsi_overbought': 75, 'rsi_oversold': 25})
        ]
        
        selected_strategies = []
        for i, (strat_type, name, desc, default_params) in enumerate(available_strategies, 1):
            choice = get_input(f"  [{i}] Include {name}? ({desc}) [y/n]", "y").lower()
            if choice == 'y':
                selected_strategies.append({'type': strat_type, 'params': default_params})
                print_success(f"      ✓ Added {name}")
        
        if not selected_strategies:
            print_warning("No strategies selected! Adding SMA Crossover as default.")
            selected_strategies.append({'type': 'sma_crossover', 'params': {'fast_period': 10, 'slow_period': 30}})
        
        strategy['strategies'] = selected_strategies
        
        print()
        print("  " + "="*50)
        print("  🔧 CREATE YOUR OWN - Indicator Selection")
        print("  " + "="*50)
        print("  Select which indicators to enable:\n")
        
        # Let user select indicators
        strategy['custom_indicators'] = True
        strategy['selected_indicators'] = []
        
        available_indicators = [
            ('rsi', 'RSI', 'Relative Strength Index'),
            ('macd', 'MACD', 'Moving Average Conv/Div'),
            ('bollinger', 'Bollinger Bands', 'Volatility bands'),
            ('atr', 'ATR', 'Average True Range'),
            ('adx', 'ADX', 'Trend strength'),
            ('stochastic', 'Stochastic', 'Momentum oscillator'),
            ('supertrend', 'Supertrend', 'Trend indicator'),
            ('volume', 'Volume Profile', 'Volume analysis'),
            ('ichimoku', 'Ichimoku Cloud', 'Complete trend system'),
            ('williams_r', 'Williams %R', 'Momentum')
        ]
        
        for i, (ind_type, name, desc) in enumerate(available_indicators, 1):
            choice = get_input(f"  [{i}] Include {name}? ({desc}) [y/n]", "y").lower()
            if choice == 'y':
                strategy['selected_indicators'].append(ind_type)
                print_success(f"      ✓ Added {name}")
        
        print()
        print_success(f"🔧 Custom Configuration Complete: {len(selected_strategies)} strategies, {len(strategy.get('selected_indicators', []))} indicators")
        
    elif mode_choice == "3":
        # Single strategy mode - user selects manually
        print()
        print("  Choose your strategy:\n")
        print_option("1", "SMA Crossover", "Simple Moving Average crossover (recommended)")
        print_option("2", "EMA Crossover", "Exponential Moving Average crossover")
        print_option("3", "Momentum Breakout", "Price momentum and breakout detection")
        print_option("4", "Scalping", "Fast scalping with tight stops")
        print_option("5", "Mean Reversion", "Bollinger Band bounce strategy")
        print_option("6", "Trend Following", "ADX-confirmed trend following")
        print()
        
        strat_choice = get_input("Select strategy (1-6)", "1")
        
        if strat_choice == "1":
            strategy['type'] = 'sma_crossover'
            print_info("SMA Crossover uses fast and slow moving averages")
            
            params['fast_period'] = get_int(
                "Fast SMA period",
                params.get('fast_period', params.get('short_window', 10)),
                min_val=3, max_val=50
            )
            
            params['slow_period'] = get_int(
                "Slow SMA period",
                params.get('slow_period', params.get('long_window', 30)),
                min_val=10, max_val=200
            )
            
            # Ensure fast < slow
            if params['fast_period'] >= params['slow_period']:
                print_warning("Fast period must be less than slow period. Adjusting...")
                params['slow_period'] = params['fast_period'] + 20
            
            print()
            print_success(f"Fast SMA: {params['fast_period']} periods")
            print_success(f"Slow SMA: {params['slow_period']} periods")
            
        elif strat_choice == "2":
            strategy['type'] = 'ema_crossover'
            print_info("EMA Crossover uses exponential moving averages for faster response")
            
            params['fast_period'] = get_int("Fast EMA period", 12, min_val=3, max_val=50)
            params['slow_period'] = get_int("Slow EMA period", 26, min_val=10, max_val=200)
            
            if params['fast_period'] >= params['slow_period']:
                params['slow_period'] = params['fast_period'] + 10
            
            print_success(f"Fast EMA: {params['fast_period']}, Slow EMA: {params['slow_period']}")
            
        elif strat_choice == "3":
            strategy['type'] = 'momentum_breakout'
            print_info("Momentum Breakout detects strong price movements")
            
            params['lookback_period'] = get_int("Lookback period", 20, min_val=10, max_val=100)
            params['breakout_threshold'] = get_float("Breakout threshold (ATR multiplier)", 1.5, min_val=1.0, max_val=3.0)
            
            print_success(f"Lookback: {params['lookback_period']}, Threshold: {params['breakout_threshold']}")
            
        elif strat_choice == "4":
            strategy['type'] = 'scalping'
            print_info("Scalping strategy for quick trades with tight stops")
            
            params['quick_period'] = get_int("Quick period", 5, min_val=3, max_val=20)
            params['trend_period'] = get_int("Trend period", 20, min_val=10, max_val=50)
            
            print_success(f"Quick: {params['quick_period']}, Trend: {params['trend_period']}")
            
        elif strat_choice == "5":
            strategy['type'] = 'mean_reversion'
            print_info("Mean Reversion uses Bollinger Bands for bounce trades")
            
            params['bollinger_period'] = get_int("Bollinger Bands period", 20, min_val=10, max_val=50)
            params['bollinger_std'] = get_float("Standard deviations", 2.0, min_val=1.5, max_val=3.0)
            params['rsi_period'] = get_int("RSI period", 14, min_val=5, max_val=30)
            
            print_success(f"Bollinger: {params['bollinger_period']} ({params['bollinger_std']}σ), RSI: {params['rsi_period']}")
            
        elif strat_choice == "6":
            strategy['type'] = 'trend_following'
            print_info("Trend Following uses ADX for trend confirmation")
            
            params['adx_period'] = get_int("ADX period", 14, min_val=10, max_val=30)
            params['adx_threshold'] = get_int("ADX threshold", 25, min_val=15, max_val=35)
            params['supertrend_period'] = get_int("Supertrend ATR period", 10, min_val=5, max_val=20)
            
            print_success(f"ADX: {params['adx_period']} ({params['adx_threshold']}), Supertrend: {params['supertrend_period']}")
    
    strategy['params'] = params
    return strategy


def confirm_and_save(config: Dict[str, Any], config_path: str) -> bool:
    """Show summary and confirm save."""
    print_section("STEP 7: Configuration Summary", 7, 7)

    # Trading Configuration
    print("  \033[97m📊 Trading Configuration:\033[0m")
    print(f"    Symbol:           \033[96m{config['trading']['symbol']}\033[0m")
    print(f"    Timeframe:        \033[96m{config['trading']['timeframe']}\033[0m")

    # Strategy Configuration
    print("\n  \033[97m🎯 Strategy Configuration:\033[0m")
    strategy = config['strategy']
    if strategy.get('type') == 'dynamic':
        strategies_count = len(strategy.get('strategies', []))
        print(f"    Strategy:         \033[96mDynamic ({strategies_count} strategies)\033[0m")
    else:
        print(f"    Strategy:         \033[96m{strategy['type']}\033[0m")

    # Indicators
    indicators_count = len(config.get('indicators', []))
    if indicators_count > 0:
        print(f"    Indicators:       \033[96m{indicators_count} configured\033[0m")

    # Risk Management
    print("\n  \033[97m⚠️  Risk Management:\033[0m")
    print(f"    Max Daily Loss:   \033[93m${config['risk']['max_daily_loss']}\033[0m")
    print(f"    Position Size:    \033[93m{config['risk']['position_size_pct']}%\033[0m")
    print(f"    Max Positions:    \033[93m{config['risk']['max_total_positions']}\033[0m")

    print()
    confirm = get_input("Save this configuration? (y/n)", "y").lower()

    if confirm == 'y':
        # Backup existing config
        config_file = Path(config_path)
        if config_file.exists():
            backup_path = config_file.with_suffix('.json.bak')
            try:
                backup_path.write_text(config_file.read_text())
                print_info(f"Backed up existing config to {backup_path.name}")
            except PermissionError as e:
                print_warning(f"Could not create backup {backup_path.name} (permission denied). Continuing without backup: {e}")
            except Exception as e:
                print_warning(f"Could not create backup {backup_path.name}: {e}")

        # Save new config
        try:
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
        except PermissionError as e:
            print_error(f"Failed to write config to {config_path}: {e}")
            return False
        except Exception as e:
            print_error(f"Failed to write config to {config_path}: {e}")
            return False

        print_success(f"Configuration saved to {config_path}")
        return True
    else:
        print_warning("Configuration not saved.")
        return False


def save_profile_as_mindset(config: Dict[str, Any], mindset: str, timeframe: str) -> str:
    """Save the current configuration as a per-mindset profile in configs/mindsets/<mindset>/"""
    base_dir = Path(__file__).parent.parent / "configs" / "mindsets" / mindset
    base_dir.mkdir(parents=True, exist_ok=True)

    # timeframe may be 'TIMEFRAME_H1' or comma-separated; if multiple, return list later
    profiles = []
    for tf in (timeframe.split(',') if isinstance(timeframe, str) and ',' in timeframe else [timeframe]):
        suffix = tf.replace('TIMEFRAME_', '').lower()
        file_name = f"config_{mindset}_{suffix}.json"
        path = base_dir / file_name

        # Ensure orphan_trades exists and is enabled by default for live adoption
        if 'orphan_trades' not in config:
            config['orphan_trades'] = {
                'enabled': True,
                'adopt_symbols': [],
                'ignore_symbols': [],
                'apply_exit_strategies': True,
                'max_adoption_age_hours': 0,
                'log_only': False
            }

        with open(path, 'w') as f:
            json.dump(config, f, indent=2)

        profiles.append(str(path))

    return profiles[0] if len(profiles) == 1 else profiles


def parse_natural_language_intent(text: str) -> Dict[str, Any]:
    """Very lightweight intent parser for setup wizard.

    Extracts symbol, timeframe(s), mindset, position_size_pct, and max_daily_loss from free text.
    This is intentionally small and rule-based for reliability and privacy (no network calls).
    """
    import re
    intent = {}
    t = text.strip()
    lower = t.lower()

    # Mindset (many synonyms)
    if re.search(r"\b(aggressive|high[- ]?risk|high risk|highrisk)\b", lower):
        intent['mindset'] = 'aggressive'
    elif re.search(r"\b(conservative|low[- ]?risk|low risk|lowrisk)\b", lower):
        intent['mindset'] = 'conservative'
    elif re.search(r"\b(balanced|moderate|medium risk)\b", lower):
        intent['mindset'] = 'balanced'

    # Named asset shortcuts (user-friendly)
    named = {
        'gold': 'XAUUSD', 'xau': 'XAUUSD', 'silver': 'XAGUSD', 'xag': 'XAGUSD',
        'bitcoin': 'BTCUSD', 'btc': 'BTCUSD', 'eth': 'ETHUSD', 'ethereum': 'ETHUSD'
    }
    for name, sym in named.items():
        if re.search(rf"\b{name}\b", lower):
            intent['symbol'] = sym
            break

    # Symbol heuristics: prefer explicit common symbols first (case-insensitive)
    # First, look for explicit token with suffix like EURUSD# or GOLD#m
    suf_match = re.search(r"\b([A-Za-z]{3,6})([#mM]{1,2})\b", t)
    if suf_match:
        base = suf_match.group(1).upper()
        suffix = suf_match.group(2)
        # Normalize suffix ordering
        s_low = ''.join(ch for ch in suffix if ch in '#mM').lower()
        if '#m' in s_low:
            suf_norm = '#m'
        elif 'm#' in s_low:
            suf_norm = 'm#'
        elif '#' in s_low:
            suf_norm = '#'
        elif 'm' in s_low:
            suf_norm = 'm'
        else:
            suf_norm = ''
        # If a suffix was provided by the user, prefer the explicit token (e.g., 'GOLD#m')
        # rather than mapping a base name like 'GOLD' to a common asset name like 'XAUUSD'.
        if suf_norm:
            intent['symbol'] = (base + suf_norm).upper()
        else:
            # No suffix provided: if the base maps to a named asset (e.g., gold -> XAUUSD), use that mapping
            if base.lower() in named:
                intent['symbol'] = named[base.lower()]
            else:
                intent['symbol'] = base.upper()
    else:
        # Prefer longer/common symbols first to preserve suffixes like '#'
        try:
            for sym in sorted(COMMON_SYMBOLS, key=len, reverse=True):
                if sym.lower() in lower:
                    intent['symbol'] = sym
                    break
        except Exception:
            pass

        # Token scan fallback: accept ALL-UPPER tokens of 3-6 letters optionally suffixed
        if 'symbol' not in intent:
            tokens = re.findall(r"\b[\w#]+\b", t)
            for tok in tokens:
                alpha = ''.join(ch for ch in tok if ch.isalpha())
                if 3 <= len(alpha) <= 6 and tok.isupper():
                    suf = ''.join(ch for ch in tok if ch in '#mM')
                    s_low = suf.lower()
                    if '#m' in s_low:
                        suf_norm = '#m'
                    elif 'm#' in s_low:
                        suf_norm = 'm#'
                    elif '#' in s_low:
                        suf_norm = '#'
                    elif 'm' in s_low:
                        suf_norm = 'm'
                    else:
                        suf_norm = ''
                    intent['symbol'] = (alpha.upper() + suf_norm).upper()
                    break

    # Timeframes: flexible detection using numeric + unit patterns and word forms
    tf_candidates = []
    try:
        # Patterns: '15m' or '15 m' (digits then unit)
        for n, unit in re.findall(r"(\d+)\s*(m|h|d|w|mn)\b", lower):
            unit = unit.lower()
            if unit == 'm':
                if n == '1':
                    tf_candidates.append('TIMEFRAME_M1')
                elif n == '5':
                    tf_candidates.append('TIMEFRAME_M5')
                elif n == '15':
                    tf_candidates.append('TIMEFRAME_M15')
                elif n == '30':
                    tf_candidates.append('TIMEFRAME_M30')
            elif unit == 'h':
                if n == '1':
                    tf_candidates.append('TIMEFRAME_H1')
                elif n == '4':
                    tf_candidates.append('TIMEFRAME_H4')
            elif unit == 'd':
                tf_candidates.append('TIMEFRAME_D1')
            elif unit == 'w':
                tf_candidates.append('TIMEFRAME_W1')
            elif unit == 'mn':
                tf_candidates.append('TIMEFRAME_MN1')

        # Patterns: 'm15' or 'h1' (unit then digits)
        for unit, n in re.findall(r"\b(m|h|d|w|mn)\s*(\d+)\b", lower):
            unit = unit.lower()
            if unit == 'm':
                if n == '1':
                    tf_candidates.append('TIMEFRAME_M1')
                elif n == '5':
                    tf_candidates.append('TIMEFRAME_M5')
                elif n == '15':
                    tf_candidates.append('TIMEFRAME_M15')
                elif n == '30':
                    tf_candidates.append('TIMEFRAME_M30')
            elif unit == 'h':
                if n == '1':
                    tf_candidates.append('TIMEFRAME_H1')
                elif n == '4':
                    tf_candidates.append('TIMEFRAME_H4')
            elif unit == 'd':
                tf_candidates.append('TIMEFRAME_D1')
            elif unit == 'w':
                tf_candidates.append('TIMEFRAME_W1')
            elif unit == 'mn':
                tf_candidates.append('TIMEFRAME_MN1')

        # Compact forms like 'm15' or 'h1'
        for compact in re.findall(r"\b([mh]\d{1,2})\b", lower):
            unit = compact[0]
            n = compact[1:]
            if unit == 'm':
                if n == '1':
                    tf_candidates.append('TIMEFRAME_M1')
                elif n == '5':
                    tf_candidates.append('TIMEFRAME_M5')
                elif n == '15':
                    tf_candidates.append('TIMEFRAME_M15')
                elif n == '30':
                    tf_candidates.append('TIMEFRAME_M30')
            elif unit == 'h':
                if n == '1':
                    tf_candidates.append('TIMEFRAME_H1')
                elif n == '4':
                    tf_candidates.append('TIMEFRAME_H4')

        # Word forms
        if re.search(r"\bminute\b|\bminutes\b", lower) and 'TIMEFRAME_M1' not in tf_candidates:
            tf_candidates.append('TIMEFRAME_M1')
        if re.search(r"\bhour\b|\bhours\b", lower) and 'TIMEFRAME_H1' not in tf_candidates:
            tf_candidates.append('TIMEFRAME_H1')
        if re.search(r"\bdaily|daily|day\b", lower) and 'TIMEFRAME_D1' not in tf_candidates:
            tf_candidates.append('TIMEFRAME_D1')
    except Exception:
        pass

    if tf_candidates:
        # de-duplicate preserving order
        unique = list(dict.fromkeys(tf_candidates))
        # order by resolution (smaller timeframes first)
        TIMEFRAME_ORDER = {
            'TIMEFRAME_M1': 1, 'TIMEFRAME_M5': 5, 'TIMEFRAME_M15': 15, 'TIMEFRAME_M30': 30,
            'TIMEFRAME_H1': 60, 'TIMEFRAME_H4': 240, 'TIMEFRAME_D1': 1440, 'TIMEFRAME_W1': 10080, 'TIMEFRAME_MN1': 43200
        }
        unique.sort(key=lambda x: TIMEFRAME_ORDER.get(x, 99999))
        intent['timeframes'] = unique

    # Position size (percent) e.g., 1%, 2.5 percent, '2 percent'
    pct = re.search(r"(\d+(?:\.\d+)?)\s*(%|percent|pct)", lower)
    if pct:
        try:
            intent['position_size_pct'] = float(pct.group(1))
        except Exception:
            pass

    # Max daily loss e.g., $100, 100 dollars, max loss 100
    money = re.search(r"\$\s*(\d+(?:\.\d+)?)", lower)
    if not money:
        money = re.search(r"max\s*loss\s*(?:is|of|:)??\s*(\d+(?:\.\d+)?)\s*(dollars|usd)?", lower)
    if not money:
        # pattern: '200 dollars max loss' or '200 max loss'
        money = re.search(r"(\d+(?:\.\d+)?)\s*(dollars|usd)?\s*max\s*loss", lower)
    if money:
        try:
            intent['max_daily_loss'] = float(money.group(1))
        except Exception:
            pass

    return intent


def advanced_intent_parser(text: str) -> Optional[Dict[str, Any]]:
    """Optional advanced parser: use local spaCy or transformers when available.

    This function is best-effort: it will return None if no advanced library
    or model is available so callers can fall back to the rule-based parser.
    """
    try:
        # Try spaCy first (local, fast)
        import spacy
        try:
            nlp = spacy.load("en_core_web_sm")
        except Exception:
            # If model not installed, trying the small pipeline via blank English
            nlp = spacy.blank("en")

        doc = nlp(text)
        intent = {}

        # Use NER and token shapes to improve symbol detection and numeric extraction
        # Look for MONEY entities and numeric tokens
        for ent in getattr(doc, 'ents', []):
            if ent.label_ in ("MONEY",):
                # Expect like "$100" -> max_daily_loss
                m = re.search(r"(\d+(?:\.\d+)?)", ent.text)
                if m:
                    try:
                        intent['max_daily_loss'] = float(m.group(1))
                    except Exception:
                        pass

        # Fallback heuristics using tokens
        # percent tokens
        for token in doc:
            if token.like_num:
                nxt = token.nbor(1).text.lower() if token.i + 1 < len(doc) else ''
                if nxt in ('%', 'percent', 'pct'):
                    try:
                        intent['position_size_pct'] = float(token.text)
                    except Exception:
                        pass

        # Symbol detection: look for uppercase-like tokens or currency symbols
        for token in doc:
            txt = token.text.strip()
            if txt.isupper() and 3 <= len(txt) <= 6:
                intent['symbol'] = txt
                break

        # Timeframe words
        lower = text.lower()
        tfs = []
        if '15m' in lower or '15 m' in lower or '15-minute' in lower:
            tfs.append('TIMEFRAME_M15')
        if '1h' in lower or 'hour' in lower:
            tfs.append('TIMEFRAME_H1')
        if tfs:
            intent['timeframes'] = list(dict.fromkeys(tfs))

        return intent if intent else None
    except Exception:
        # Advanced parser not available or failed - caller should fallback
        return None


def transformer_intent_parser(text: str) -> Optional[dict]:
    """Best-effort transformer-based parser using sentence-transformers.

    This function is optional and will return None if `sentence_transformers`
    is not installed. It uses a small set of canned templates (examples)
    and picks the best-matching template via cosine similarity on SBERT
    embeddings. The returned dict includes a `_confidence` score (0..1).
    """
    try:
        from sentence_transformers import SentenceTransformer, util
    except Exception:
        return None

    try:
        model = SentenceTransformer('all-MiniLM-L6-v2')
    except Exception:
        try:
            model = SentenceTransformer('paraphrase-MiniLM-L6-v2')
        except Exception:
            return None

    # Lightweight example templates mapping to expected parsed fields
    templates = [
        ("Aggressive gold on M15 and H1 with 2% risk and $100 max loss", {
            'mindset': 'aggressive', 'symbol': 'XAUUSD', 'timeframes': ['TIMEFRAME_M15', 'TIMEFRAME_H1'], 'position_size_pct': 2.0, 'max_daily_loss': 100.0
        }),
        ("Conservative EURUSD 1m with 0.5% position size and $50 max loss", {
            'mindset': 'conservative', 'symbol': 'EURUSD', 'timeframes': ['TIMEFRAME_M1'], 'position_size_pct': 0.5, 'max_daily_loss': 50.0
        }),
        ("Balanced BTC on 5m, 1% position size", {
            'mindset': 'balanced', 'symbol': 'BTCUSD', 'timeframes': ['TIMEFRAME_M5'], 'position_size_pct': 1.0
        }),
        ("Trade gold H1 and M15, balanced", {
            'mindset': 'balanced', 'symbol': 'XAUUSD', 'timeframes': ['TIMEFRAME_H1', 'TIMEFRAME_M15']
        }),
        ("EURUSD daily 2 percent, 200 dollars max loss", {
            'symbol': 'EURUSD', 'timeframes': ['TIMEFRAME_D1'], 'position_size_pct': 2.0, 'max_daily_loss': 200.0
        }),
    ]

    texts = [t for t, _ in templates]
    emb_texts = model.encode(texts, convert_to_tensor=True)
    emb_input = model.encode([text], convert_to_tensor=True)
    cos_scores = util.cos_sim(emb_input, emb_texts)[0]

    # Pick best template
    best_idx = int(cos_scores.argmax())
    best_score = float(cos_scores[best_idx])
    best_template, best_fields = templates[best_idx]

    # Normalize confidence to 0..1 (SBERT cos_sim is -1..1)
    confidence = max(0.0, min(1.0, (best_score + 1) / 2))

    result = dict(best_fields)
    result['_confidence'] = confidence
    result['_source_template'] = best_template
    return result


def aggregate_intent_parsers(text: str) -> dict:
    """Run all available parsers and pick the strongest candidate.

    Strategy:
    - Attempt transformer parser (if available) and spaCy parser (if available).
    - Always run the rule-based parser.
    - Score candidates by number of fields parsed + confidence weight when present.
    - Return the chosen dict and log source.
    """
    candidates = []

    # Rule-based parser (always available)
    try:
        rb = parse_natural_language_intent(text)
        score_rb = len(rb.keys())
        candidates.append((rb, float(score_rb), 'rule-based'))
    except Exception:
        rb = {}

    # Advanced spaCy parser
    try:
        sp = advanced_intent_parser(text)
        if sp:
            score_sp = len(sp.keys()) + 0.1
            candidates.append((sp, float(score_sp), 'spacy'))
    except Exception:
        sp = None

    # Transformer parser
    try:
        tr = transformer_intent_parser(text)
        if tr:
            conf = float(tr.get('_confidence', 0.0))
            base_score = len([k for k in tr.keys() if not k.startswith('_')])
            score_tr = base_score + conf
            candidates.append((tr, float(score_tr), 'transformer'))
    except Exception:
        tr = None

    # Choose best candidate by score
    if not candidates:
        return {}

    candidates.sort(key=lambda x: x[1], reverse=True)
    best, best_score, source = candidates[0]

    # Prefer rule-based unless another parser is substantially stronger
    # (avoid accidental weaker transformer/spacy picks causing regressions)
    try:
        rb_score = next(s for (_, s, src) in candidates if src == 'rule-based')
    except StopIteration:
        rb_score = 0.0

    if source != 'rule-based' and best_score < (rb_score + 0.5):
        # pick rule-based instead
        best = next(c for (c, s, src) in candidates if src == 'rule-based')[0] if False else None
        # find the rule-based candidate tuple
        rb_candidate = next((c for (c, s, src) in candidates if src == 'rule-based'), None)
        if rb_candidate:
            best = rb_candidate[0]
            best_score = rb_candidate[1]
            source = 'rule-based'

    # Merge candidates by priority (highest score first) to produce a robust final result.
    merged = {}
    for cand, score, src in candidates:
        for k, v in cand.items():
            if k.startswith('_'):
                continue
            if k not in merged:
                merged[k] = v

    merged['_chosen_by'] = source
    merged['_score'] = best_score
    return merged


def run_nlp_wizard(config_path: str = "config.json") -> Optional[Dict[str, Any]]:
    """Run the lightweight NLP-driven setup wizard.

    Prompts the user for a natural-language intent sentence, parses it, and proposes a configuration.
    The user can accept, tweak defaults (one final edit), and save as a profile.
    """
    clear_screen()
    print_banner()
    print("  Cthulu NLP setup wizard (lightweight, local).")
    print("  Describe what you want (e.g., 'Aggressive GOLD#m M15 H1, 2% risk, $100 max loss')")
    print("  Leave blank to fall back to the interactive wizard.")

    text = input("  Describe your trading intent (e.g. 'Aggressive GOLD#m M15 H1, 2% risk, $100 max loss'): ").strip()
    if not text:
        print_info("No input provided — falling back to the interactive wizard.")
        return run_setup_wizard(config_path)

    # Offer advanced local NLP if available
    use_advanced = False
    try:
        adv_avail = False
        import importlib
        if importlib.util.find_spec('spacy') is not None:
            adv_avail = True
    except Exception:
        adv_avail = False

    if adv_avail:
        choice = get_input("Attempt advanced local NLP parsing if available? (y/N)", "N").lower()
        use_advanced = choice == 'y'

    parsed = None
    # Run aggregator to pick the strongest candidate among available parsers
    parsed = aggregate_intent_parsers(text)
    if not parsed:
        print_warning("Failed to parse intent — falling back to interactive wizard.")
        return run_setup_wizard(config_path)

    print_info(f"Parsed intent (chosen by {parsed.get('_chosen_by')} score={parsed.get('_score'):.2f}): { {k:v for k,v in parsed.items() if not k.startswith('_')} }")

    # Load existing config or defaults
    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file) as f:
            config = json.load(f)
        print_success(f"Loaded existing configuration from {config_path}")
    else:
        config = {
            "mt5": {"login": 0, "password": "", "server": ""},
            "trading": {"symbol": "EURUSD", "timeframe": "TIMEFRAME_H1", "poll_interval": 60, "lookback_bars": 500},
            "risk": {"max_daily_loss": 50.0, "position_size_pct": 2.0, "max_total_positions": 3},
            "strategy": {"type": "sma_crossover", "params": {"fast_period": 10, "slow_period": 30}},
            "exit_strategies": [],
            "indicators": []
        }

    # Apply parsed values (merge carefully)
    if 'symbol' in parsed:
        config['trading']['symbol'] = parsed['symbol']
        config['strategy'].setdefault('params', {})['symbol'] = parsed['symbol']
    if 'timeframes' in parsed and parsed['timeframes']:
        # take first timeframe as primary
        config['trading']['timeframe'] = parsed['timeframes'][0]
    if 'mindset' in parsed:
        # apply mindset overlay (affects defaults, but we keep it simple: store for save)
        selected_mindset = parsed['mindset']
    else:
        selected_mindset = 'balanced'
    if 'position_size_pct' in parsed:
        config['risk']['position_size_pct'] = parsed['position_size_pct']
    if 'max_daily_loss' in parsed:
        config['risk']['max_daily_loss'] = parsed['max_daily_loss']

    # Show summary and allow single edit
    print_section("NLP PROPOSED CONFIG")
    print(f"  Mindset (suggested): {selected_mindset}")
    print(f"  Symbol: {config['trading']['symbol']}")
    print(f"  Timeframe: {config['trading']['timeframe']}")
    print(f"  Position size (%): {config['risk']['position_size_pct']}")
    print(f"  Max daily loss ($): {config['risk']['max_daily_loss']}")

    edit = get_input("Would you like to edit any of these before saving? (y/N)", "N").lower()
    if edit == 'y':
        # Provide simple edits: symbol, timeframe, position size, daily loss, mindset
        new_symbol = get_input("Symbol", config['trading']['symbol']).upper()
        config['trading']['symbol'] = new_symbol
        config['strategy'].setdefault('params', {})['symbol'] = new_symbol

        # Timeframe selection via existing helper
        tf = choose_timeframe(config['trading'].get('timeframe', 'TIMEFRAME_H1'))
        config['trading']['timeframe'] = tf

        # Risk
        config['risk'] = configure_risk(config.get('risk', {}))

        selected_mindset = get_input("Mindset (aggressive/balanced/conservative)", selected_mindset)

    # Confirm and save
    save_choice = get_input("Save this configuration? (y/N)", "N").lower()
    if save_choice == 'y':
        saved = confirm_and_save(config, config_path)
        if saved:
            print_success(f"Configuration saved to {config_path}")
    else:
        print_info("Configuration not saved. You can run the wizard again or edit manually.")

    return config


def run_setup_wizard(config_path: str = "config.json") -> Optional[Dict[str, Any]]:
    """
    Run the interactive setup wizard.
    
    Args:
        config_path: Path to config.json file
        
    Returns:
        Updated configuration dict, or None if cancelled
    """
    clear_screen()
    print_banner()
    
    print("  Welcome to Cthulu! This wizard will help you configure")
    print("  the key trading parameters before you start.\n")
    print("  \033[90mPress Enter to accept defaults shown in [brackets].\033[0m\n")
    print_info("Answer 'y' to start a new setup (configure new settings). Answer 'n' to use the last saved configuration and start Cthulu immediately.")
    
    try:
        proceed = get_input("Start setup? (y/n)", "y").lower()
    except WizardCancelled:
        print_info("Setup cancelled (no input).")
        return None

    # n = skip wizard and continue using existing/default config
    if proceed == 'n':
        # Load existing config or fall back to example/defaults and return it so
        # the caller can continue startup without running the interactive wizard.
        config_file = Path(config_path)
        if config_file.exists():
            with open(config_file) as f:
                config = json.load(f)
            print_success(f"Loaded existing configuration from {config_path}")
        else:
            example_path = Path(config_path).parent / "config.example.json"
            if example_path.exists():
                with open(example_path) as f:
                    config = json.load(f)
                print_info("Starting from example configuration")
            else:
                print_warning("No existing config found. Using defaults.")
                config = {
                    "mt5": {"login": 0, "password": "", "server": ""},
                    "trading": {"symbol": "EURUSD", "timeframe": "TIMEFRAME_H1", "poll_interval": 60, "lookback_bars": 500},
                    "risk": {"max_daily_loss": 50.0, "position_size_pct": 2.0, "max_total_positions": 3},
                    "strategy": {"type": "sma_crossover", "params": {"fast_period": 10, "slow_period": 30}},
                    "exit_strategies": [],
                    "indicators": []
                }
        # If there is no on-disk config, write the chosen/default config so
        # the main startup path that calls `Config.load(path)` can find it.
        try:
            cfg_path = Path(config_path)
            if not cfg_path.exists():
                cfg_path.parent.mkdir(parents=True, exist_ok=True)
                with open(cfg_path, 'w', encoding='utf-8') as fh:
                    json.dump(config, fh, indent=2)
                print_success(f"Wrote default configuration to {config_path}")
        except Exception:
            print_warning("Failed to persist default config; continuing with in-memory config")

        print()
        print_info("Starting Cthulu with the existing configuration...")
        return config
    
    # Load existing config if available
    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file) as f:
            config = json.load(f)
        print_success(f"Loaded existing configuration from {config_path}")
    else:
        # Load from example
        example_path = Path(config_path).parent / "config.example.json"
        if example_path.exists():
            with open(example_path) as f:
                config = json.load(f)
            print_info("Starting from example configuration")
        else:
            print_warning("No existing config found. Using defaults.")
            config = {
                "mt5": {"login": 0, "password": "", "server": ""},
                "trading": {"symbol": "EURUSD", "timeframe": "TIMEFRAME_H1", "poll_interval": 60, "lookback_bars": 500},
                "risk": {"max_daily_loss": 50.0, "position_size_pct": 2.0, "max_total_positions": 3},
                "strategy": {"type": "sma_crossover", "params": {"fast_period": 10, "slow_period": 30}},
                "exit_strategies": [],
                "indicators": []
            }
    
    try:
        # Step 1: Mindset (applied as overlay later)
        mindset = choose_mindset()
        
        # Step 2: Symbol
        current_symbol = config.get('trading', {}).get('symbol', 'EURUSD')
        config['trading']['symbol'] = choose_symbol(current_symbol)
        
        # Also update symbol in strategy params if present
        if 'strategy' in config and 'params' in config['strategy']:
            config['strategy']['params']['symbol'] = config['trading']['symbol']
        
        # Step 3: Timeframe
        current_tf = config.get('trading', {}).get('timeframe', 'TIMEFRAME_H1')
        config['trading']['timeframe'] = choose_timeframe(current_tf)
        
        # Step 4: Risk Management
        config['risk'] = configure_risk(config.get('risk', {}))
        
        # Step 5: Strategy Settings
        config['strategy'] = configure_strategy(config.get('strategy', {}))
        
        # Step 5.5: Indicators (new)
        config['indicators'] = configure_indicators(config.get('indicators', []))
        
        # Step 6: Confirm and save (simplified)
        print()
        if confirm_and_save(config, config_path):
            print()
            print_success("Configuration saved. Starting Cthulu now...")
            print()
            return config
        else:
            print()
            print_info("Configuration not saved. Starting Cthulu with in-memory configuration...")
            print()
            return config
    except WizardCancelled:
        print_info('Setup cancelled (input closed). No changes saved.')
        return None


if __name__ == "__main__":
    # Allow running wizard standalone
    run_setup_wizard("config.json")




