"""
Cthulu Autonomous Trading System

Main orchestrator implementing the Phase 2 autonomous trading loop.
"""

import sys
import time
import signal as sig_module
import subprocess
import logging
import argparse
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from cthulu.connector.mt5_connector import mt5
import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

__version__ = "4.0.0"

from cthulu.connector.mt5_connector import MT5Connector, ConnectionConfig
from cthulu.data.layer import DataLayer
from cthulu.strategy.base import Strategy, SignalType
from cthulu.execution.engine import ExecutionEngine, OrderRequest, OrderType, OrderStatus
from cthulu.risk.manager import RiskManager, RiskLimits
from cthulu.position.manager import PositionManager
from cthulu.position.trade_manager import TradeManager, TradeAdoptionPolicy
from cthulu.persistence.database import Database, TradeRecord, SignalRecord
from cthulu.observability.logger import setup_logger
from cthulu.observability.metrics import MetricsCollector

# Exit strategies
from cthulu.exit.trailing_stop import TrailingStop
from cthulu.exit.time_based import TimeBasedExit
from cthulu.exit.profit_target import ProfitTargetExit
from cthulu.exit.adverse_movement import AdverseMovementExit

# Indicators
from cthulu.indicators.rsi import RSI
from cthulu.indicators.macd import MACD
from cthulu.indicators.bollinger import BollingerBands
from cthulu.indicators.stochastic import Stochastic
from cthulu.indicators.adx import ADX
from cthulu.indicators.supertrend import Supertrend
from cthulu.indicators.vwap import VWAP, AnchoredVWAP


# Global shutdown flag
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    shutdown_requested = True
    print("\nShutdown signal received, closing positions...")


from config_schema import Config
from config.mindsets import apply_mindset, list_mindsets


def load_indicators(indicator_configs: Dict[str, Any]) -> List:
    """
    Load and configure indicators.
    
    Args:
        indicator_configs: Dictionary of indicator configurations
        
    Returns:
        List of configured indicator instances
    """
    indicators = []
    indicator_map = {
        'rsi': RSI,
        'macd': MACD,
        'bollinger': BollingerBands,
        'stochastic': Stochastic,
        'adx': ADX,
        'supertrend': Supertrend,
        'vwap': VWAP,
        'anchored_vwap': AnchoredVWAP
    }
    
    import inspect

    def _prepare_params_for(cls, params: Dict[str, Any]) -> Dict[str, Any]:
        # Map common legacy aliases to current param names
        legacy_map = {
            'smooth': 'smooth_k',
            'smoothK': 'smooth_k',
            'overbought': 'overbought',
            'oversold': 'oversold'
        }

        # Copy so we don't mutate original
        params_copy = dict(params or {})

        # Apply legacy mappings
        for old, new in legacy_map.items():
            if old in params_copy and new not in params_copy:
                params_copy[new] = params_copy.pop(old)

        # Inspect constructor to keep only supported params (ignore others)
        try:
            sig = inspect.signature(cls.__init__)
            valid_names = {p.name for p in sig.parameters.values() if p.name != 'self' and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)}
            filtered = {k: v for k, v in params_copy.items() if k in valid_names}
            return filtered
        except Exception:
            # If anything goes wrong, fallback to passing original params and let the caller handle errors
            return params_copy

    # Handle both list and dict formats
    if isinstance(indicator_configs, list):
        # List format: [{"type": "rsi", "params": {...}}, ...]
        for indicator_config in indicator_configs:
            indicator_type = indicator_config.get('type', '').lower()
            params = indicator_config.get('params', {})

            if indicator_type in indicator_map:
                filtered = _prepare_params_for(indicator_map[indicator_type], params)
                indicator = indicator_map[indicator_type](**filtered)
                indicators.append(indicator)
    else:
        # Dict format: {"rsi": {...}, "macd": {...}}
        for indicator_type, params in indicator_configs.items():
            indicator_type_lower = indicator_type.lower()

            if indicator_type_lower in indicator_map:
                filtered = _prepare_params_for(indicator_map[indicator_type_lower], params)
                indicator = indicator_map[indicator_type_lower](**filtered)
                indicators.append(indicator)

    return indicators


def load_strategy(strategy_config: Dict[str, Any]) -> Strategy:
    """
    Load and configure trading strategy.
    
    Args:
        strategy_config: Strategy configuration
        
    Returns:
        Configured strategy instance or StrategySelector for dynamic mode
    """
    from cthulu.strategy.sma_crossover import SmaCrossover
    from cthulu.strategy.ema_crossover import EmaCrossover
    from cthulu.strategy.momentum_breakout import MomentumBreakout
    from cthulu.strategy.scalping import ScalpingStrategy
    from cthulu.strategy.strategy_selector import StrategySelector

    # Normalize strategy config: keep nested 'params' but expose its keys at top-level
    strat_cfg = dict(strategy_config) if isinstance(strategy_config, dict) else {}
    params = strat_cfg.get('params', {}) if isinstance(strat_cfg.get('params', {}), dict) else {}
    # Expose param keys at top-level without removing nested structure
    for k, v in params.items():
        if k not in strat_cfg:
            strat_cfg[k] = v

    strategy_type = strat_cfg.get('type', '').lower()
    
    # Dynamic strategy selection mode
    if strategy_type == 'dynamic':
        dynamic_config = strategy_config.get('dynamic_selection', {})
        strategies_config = strategy_config.get('strategies', [])
        
        # Load all configured strategies
        strategies = []
        for strat_cfg in strategies_config:
            # Normalize each child strategy config similarly
            child = dict(strat_cfg) if isinstance(strat_cfg, dict) else {}
            child_params = child.get('params', {}) if isinstance(child.get('params', {}), dict) else {}
            for k, v in child_params.items():
                if k not in child:
                    child[k] = v
            strat_type = child.get('type', '').lower()
            if strat_type == 'sma_crossover':
                strategies.append(SmaCrossover(config=child))
            elif strat_type == 'ema_crossover':
                strategies.append(EmaCrossover(config=child))
            elif strat_type == 'momentum_breakout':
                strategies.append(MomentumBreakout(config=child))
            elif strat_type == 'scalping':
                strategies.append(ScalpingStrategy(config=child))
                
        if not strategies:
            raise ValueError("Dynamic mode requires at least one strategy configuration")
            
        return StrategySelector(strategies=strategies, config=dynamic_config)
    
    # Single strategy mode
    elif strategy_type == 'sma_crossover':
        return SmaCrossover(config=strat_cfg)
    elif strategy_type == 'ema_crossover':
        return EmaCrossover(config=strat_cfg)
    elif strategy_type == 'momentum_breakout':
        return MomentumBreakout(config=strat_cfg)
    elif strategy_type == 'scalping':
        return ScalpingStrategy(config=strat_cfg)
    else:
        raise ValueError(f"Unknown strategy type: {strategy_type}")


def load_exit_strategies(exit_configs: Dict[str, Any]) -> List:
    """
    Load and configure exit strategies.
    
    Args:
        exit_configs: Dictionary of exit strategy configurations
        
    Returns:
        List of configured exit strategy instances, sorted by priority (highest first)
    """
    exit_strategies = []
    exit_map = {
        'trailing_stop': TrailingStop,
        'time_based': TimeBasedExit,
        'profit_target': ProfitTargetExit,
        'adverse_movement': AdverseMovementExit
    }

    # Handle both list and dict formats
    if isinstance(exit_configs, list):
        # List format: [{"type": "trailing_stop", "enabled": true, ...}, ...]
        for exit_config in exit_configs:
            exit_type = exit_config.get('type', '').lower()
            enabled = exit_config.get('enabled', True)

            if exit_type in exit_map and enabled:
                strategy = exit_map[exit_type](exit_config)
                exit_strategies.append(strategy)
    else:
        # Dict format: {"trailing_stop": {...}, "time_based": {...}}
        for exit_type, config_ in exit_configs.items():
            exit_type_lower = exit_type.lower()
            enabled = config_.get('enabled', True)

            if exit_type_lower in exit_map and enabled:
                strategy = exit_map[exit_type_lower](config_)
                exit_strategies.append(strategy)

    # Sort by priority (highest first)
    exit_strategies.sort(key=lambda x: x.priority, reverse=True)

    return exit_strategies

def ensure_runtime_indicators(df, indicators, strategy, config, logger):
    """Ensure indicators required by the active strategy/config are present.

    This function inspects the given strategy and configuration to find
    indicators (or indicator parameters) that the strategies expect to exist
    in the market data (e.g., EMA periods, RSI period, ADX). If missing,
    it creates indicator instances (temporary) and returns them so the
    main loop will calculate their columns during the same iteration.
    """
    # Avoid circular imports at module load-time; indicator classes are already imported above
    required_emas = set()
    extra_indicators = []

    def collect_ema_periods(obj):
        if obj is None:
            return
        for attr in ('fast_period', 'slow_period', 'fast_ema', 'slow_ema', 'short_window', 'long_window'):
            if hasattr(obj, attr):
                try:
                    val = int(getattr(obj, attr))
                    if 'ema' in attr or 'fast_period' in attr or 'slow_period' in attr or 'fast_ema' in attr or 'slow_ema' in attr:
                        required_emas.add(val)
                except Exception:
                    pass

    # Strategy instance inspection
    try:
        from cthulu.strategy.strategy_selector import StrategySelector
        if isinstance(strategy, StrategySelector):
            for s in strategy.strategies.values():
                collect_ema_periods(s)
        else:
            collect_ema_periods(strategy)
    except Exception:
        collect_ema_periods(strategy)

    # Also check config-level strategies
    try:
        strat_cfg = config.get('strategy', {}) if isinstance(config, dict) else {}
        if strat_cfg.get('type') == 'dynamic':
            for s in strat_cfg.get('strategies', []):
                params = s.get('params', {}) if isinstance(s.get('params', {}), dict) else {}
                for key in ('fast_ema', 'slow_ema', 'fast_period', 'slow_period'):
                    if key in params and params[key]:
                        try:
                            required_emas.add(int(params[key]))
                        except Exception:
                            pass

        # If scalping present, ensure scalping defaults
        try:
            if strat_cfg.get('type') == 'dynamic':
                for s in strat_cfg.get('strategies', []):
                    if s.get('type', '').lower() == 'scalping':
                        p = s.get('params', {}) or {}
                        if p.get('fast_ema'):
                            required_emas.add(int(p.get('fast_ema')))
                        if p.get('slow_ema'):
                            required_emas.add(int(p.get('slow_ema')))
            else:
                if strat_cfg.get('type', '').lower() == 'scalping':
                    p = strat_cfg.get('params', {}) or {}
                    if p.get('fast_ema'):
                        required_emas.add(int(p.get('fast_ema')))
                    if p.get('slow_ema'):
                        required_emas.add(int(p.get('slow_ema')))
        except Exception:
            pass
    except Exception:
        pass

    # Always include scalping defaults if strategy includes scalping
    try:
        from cthulu.strategy.strategy_selector import StrategySelector
        if isinstance(strategy, StrategySelector):
            if 'scalping' in (name.lower() for name in strategy.strategies.keys()):
                required_emas.update({5, 10})
        else:
            if getattr(strategy, 'name', '').lower() == 'scalping':
                required_emas.update({getattr(strategy, 'fast_ema', 5), getattr(strategy, 'slow_ema', 10)})
    except Exception:
        # Best effort: also check config strategies
        try:
            if strat_cfg.get('type') == 'dynamic':
                for s in strat_cfg.get('strategies', []):
                    if s.get('type', '').lower() == 'scalping':
                        required_emas.update({5, 10})
        except Exception:
            pass

    # Compute EMA columns if missing
    try:
        if required_emas:
            for p in sorted(required_emas):
                col = f'ema_{p}'
                if col not in df.columns:
                    df[col] = df['close'].ewm(span=int(p), adjust=False).mean()
            logger.debug(f"Computed EMA columns: {[f'ema_{p}' for p in sorted(required_emas)]}")
    except Exception:
        logger.exception('Failed to compute EMA columns; continuing')

    # Gather existing indicator types already present
    existing_types = set()
    for ind in indicators:
        existing_types.add(ind.__class__.__name__.lower())

    # Helper to check and append indicator instances if missing
    def _add_indicator_if_missing(ind_cls, typename, params=None):
        params = params or {}
        # If an instance of this class with matching key params exists, skip
        for ind in indicators:
            if ind.__class__.__name__.lower() == typename:
                # Simple param match: check period-like keys
                if params:
                    # Compare any matching param
                    match = True
                    for k, v in params.items():
                        if ind.params.get(k) != v:
                            match = False
                            break
                    if match:
                        return
                else:
                    return
        # Not present — create and append
        try:
            inst = ind_cls(**params) if params else ind_cls()
            extra_indicators.append(inst)
            logger.info(f"Added runtime indicator: {inst.name} with params {getattr(inst, 'params', {})}")
        except Exception:
            logger.exception(f"Failed to create runtime indicator {typename}")

    # Ensure RSI if strategies reference it
    try:
        rsi_periods = set()
        # Strategy attrs
        try:
            if hasattr(strategy, 'rsi_period'):
                rsi_periods.add(int(getattr(strategy, 'rsi_period')))
        except Exception:
            pass
        # Config strategies
        try:
            if strat_cfg.get('type') == 'dynamic':
                for s in strat_cfg.get('strategies', []):
                    params = s.get('params', {}) or {}
                    if 'rsi_period' in params and params.get('rsi_period'):
                        rsi_periods.add(int(params.get('rsi_period')))
            else:
                if 'rsi_period' in strat_cfg.get('params', {}) and strat_cfg['params'].get('rsi_period'):
                    rsi_periods.add(int(strat_cfg['params'].get('rsi_period')))
        except Exception:
            pass

        # If scalping uses rsi attribute, include
        try:
            if getattr(strategy, 'name', '').lower() == 'scalping':
                rsi_periods.add(getattr(strategy, 'rsi_period', 7) or 7)
        except Exception:
            pass

        for p in rsi_periods:
            col = 'rsi' if p == 14 else f'rsi_{p}'
            if col not in df.columns:
                _add_indicator_if_missing(RSI, 'rsi', params={'period': p})
    except Exception:
        logger.exception('Failed to ensure RSI')

    # Ensure ATR if scalping (or any strategy references `atr`)
    try:
        need_atr = False
        # Strategy-level check
        try:
            if getattr(strategy, 'name', '').lower() == 'scalping':
                need_atr = True
            # Some strategies may have an atr_period attribute
            if hasattr(strategy, 'atr_period'):
                need_atr = True
        except Exception:
            pass

        # Config-level check
        try:
            if strat_cfg.get('type') == 'dynamic':
                for s in strat_cfg.get('strategies', []):
                    p = s.get('params', {}) or {}
                    if 'atr_period' in p or 'atr' in p:
                        need_atr = True
            else:
                if 'atr_period' in strat_cfg.get('params', {}) or 'atr' in strat_cfg.get('params', {}):
                    need_atr = True
        except Exception:
            pass

        # If ATR is needed and missing, compute it here with sensible default
        if need_atr and 'atr' not in df.columns:
            try:
                from cthulu.indicators.atr import calculate_atr
                # Prefer strategy-specific period, else default 14
                period = getattr(strategy, 'atr_period', None) or strat_cfg.get('params', {}).get('atr_period', 14) or 14
                period = int(period)
                df['atr'] = calculate_atr(df, period=period)
                logger.info(f"Computed runtime ATR (period={period})")
            except Exception:
                logger.exception('Failed to compute runtime ATR')
    except Exception:
        logger.exception('Failed to ensure ATR')

    # Ensure ADX if strategy selector needs it (regime detection uses ADX)
    try:
        need_adx = False
        try:
            from cthulu.strategy.strategy_selector import StrategySelector
            if isinstance(strategy, StrategySelector):
                need_adx = True
        except Exception:
            # If any config strategy mentions adx in params, we should include it
            try:
                for s in strat_cfg.get('strategies', []):
                    if 'adx' in (s.get('params') or {}):
                        need_adx = True
            except Exception:
                pass
        if need_adx and 'adx' not in df.columns:
            _add_indicator_if_missing(ADX, 'adx', params={'period': 14})
    except Exception:
        logger.exception('Failed to ensure ADX')

    # Generic fallback: ensure other indicators (macd, bollinger, stochastic, supertrend, vwap) if strategy params mention them
    try:
        # MACD: check for 'macd' mention in config or 'signal_period' in strategy params
        need_macd = False
        try:
            # Check explicit indicators in config
            if any((i.get('type', '').lower() == 'macd') for i in config.get('indicators', [])):
                need_macd = True
            # Check strategy params
            for s in strat_cfg.get('strategies', []):
                p = s.get('params', {}) or {}
                if any(k in p for k in ('macd', 'signal_period', 'signal_period')):
                    need_macd = True
        except Exception:
            pass
        if need_macd and 'macd' not in df.columns and 'macd' not in existing_types:
            _add_indicator_if_missing(MACD, 'macd', params={'fast_period': 12, 'slow_period': 26, 'signal_period': 9})

        # Bollinger
        if 'bb_upper' not in df.columns and 'bollingerbands' not in existing_types:
            # If configured in file, ensure it; otherwise no-op
            try:
                if any((i.get('type', '').lower() == 'bollinger') for i in config.get('indicators', [])):
                    _add_indicator_if_missing(BollingerBands, 'bollingerbands', params={'period': 20, 'std_dev': 2.0})
            except Exception:
                pass

        # Stochastic
        if ('stoch_k' not in df.columns or 'stoch_d' not in df.columns) and 'stochastic' not in existing_types:
            try:
                if any((i.get('type', '').lower() == 'stochastic') for i in config.get('indicators', [])):
                    _add_indicator_if_missing(Stochastic, 'stochastic', params={'k_period': 14, 'd_period': 3, 'smooth_k': 3})
            except Exception:
                pass

        # Supertrend
        if 'supertrend' not in df.columns and 'supertrend' not in existing_types:
            try:
                if any((i.get('type', '').lower() == 'supertrend') for i in config.get('indicators', [])):
                    # Use canonical parameter names expected by Supertrend.__init__
                    _add_indicator_if_missing(Supertrend, 'supertrend', params={'period': 10, 'multiplier': 3.0})
            except Exception:
                pass

        # VWAP
        if 'vwap' not in df.columns and 'vwap' not in existing_types:
            try:
                if any((i.get('type', '').lower() == 'vwap') for i in config.get('indicators', [])):
                    _add_indicator_if_missing(VWAP, 'vwap', params={})
            except Exception:
                pass
    except Exception:
        logger.exception('Failed to ensure generic indicators')

    return extra_indicators


def main():
    """Main autonomous trading loop for Phase 2."""
    
    # Load environment variables from .env
    from dotenv import load_dotenv
    import os
    load_dotenv()
    
    # Parse arguments
    epilog = (
        "Examples:\n"
        "  herald --config config.json                    # Interactive setup + trading\n"
        "  herald --config config.json --skip-setup       # Skip wizard, use existing config\n"
        "  herald --config config.json --dry-run          # Simulate without real orders\n"
        "  herald --config config.json --mindset aggressive\n"
        "\n"
        "Workflow:\n"
        "  Cthulu starts with an interactive setup wizard that guides you through\n"
        "  configuring symbol, timeframe, risk limits, and strategy settings.\n"
        "  Use --skip-setup to bypass the wizard for automated/headless runs.\n"
        "\n"
        "Mindsets:\n"
        "  aggressive    - Higher risk, faster entries, tighter stops\n"
        "  balanced      - Moderate risk, standard settings (default)\n"
        "  conservative  - Lower risk, wider stops, capital preservation"
    )

    parser = argparse.ArgumentParser(
        description=f"Cthulu — Adaptive Trading Intelligence (v{__version__})",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--config', type=str, required=True, help="Path to JSON config file")
    parser.add_argument('--log-level', type=str, default='INFO', 
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help="Logging level (DEBUG, INFO, WARNING, ERROR)")
    parser.add_argument('--dry-run', action='store_true', 
                       help="Dry run mode (simulate orders without placing them)")
    parser.add_argument('--symbol', type=str, default=None, help="Override trading symbol in config (e.g. GOLD#m)")
    parser.add_argument('--adopt-only', action='store_true', help="Only run external trade adoption and exit")
    parser.add_argument('--mindset', type=str, default=None,
                       choices=['aggressive', 'balanced', 'conservative', 'ultra_aggressive', 'ultra'],
                       help="Trading mindset/risk profile (aggressive, balanced, conservative, ultra_aggressive)")
    parser.add_argument('--skip-setup', action='store_true',
                       help="Skip interactive setup wizard (for automation/headless runs)")
    parser.add_argument('--wizard', action='store_true',
                       help="Open the interactive setup wizard and optionally start profiles")
    parser.add_argument('--wizard-ai', action='store_true',
                       help="Run the lightweight NLP-based wizard (describe intent in natural language)")
    parser.add_argument('--no-prompt', action='store_true',
                       help="Do not prompt on shutdown; leave positions open (useful for automated runs)")
    parser.add_argument('--manual-prompt', action='store_true',
                       help="Enable persistent interactive manual trade prompt in the terminal (interactive only)")
    parser.add_argument('--enable-rpc', action='store_true', help='Enable local RPC server (binds to localhost)')
    parser.add_argument('--rpc-host', type=str, default='127.0.0.1', help='RPC server host (default 127.0.0.1)')
    parser.add_argument('--rpc-port', type=int, default=8181, help='RPC server port (default 8181)')
    # GUI / headless control
    parser.add_argument('--no-gui', action='store_true', help='Disable auto-launching the desktop GUI (headless)')
    parser.add_argument('--headless', action='store_true', help='Alias for --no-gui (run without GUI)')

    # Runtime ML toggle (CLI) — mutually exclusive enable/disable
    ml_group = parser.add_mutually_exclusive_group()
    ml_group.add_argument('--enable-ml', dest='enable_ml', action='store_true', help='Enable ML instrumentation (overrides config)')
    ml_group.add_argument('--disable-ml', dest='enable_ml', action='store_false', help='Disable ML instrumentation (overrides config)')
    parser.set_defaults(enable_ml=None)
    parser.add_argument('--version', action='version', version=f"Cthulu {__version__}")
    parser.add_argument('--max-loops', type=int, default=0, help='Exit after N main loop iterations (0 = run until shutdown)')
    args = parser.parse_args()

    # If adopt-only is requested, skip interactive setup to avoid blocking prompts
    if args.adopt_only:
        args.skip_setup = True

    # Run interactive setup wizard (default behavior, skip with --skip-setup or --adopt-only)
    if args.wizard_ai:
        from config.wizard import run_nlp_wizard
        result = run_nlp_wizard(args.config)
        if result is None:
            print("Setup cancelled. Exiting.")
            return 0
        print("\nNLP wizard completed. Exiting.")
        return 0

    if args.wizard:
        from config.wizard import run_setup_wizard
        result = run_setup_wizard(args.config)
        if result is None:
            print("Setup cancelled. Exiting.")
            return 0
        # Wizard completed — continue to start Cthulu (do not exit).
        print("\nWizard completed. Continuing to start Herald...\n")
        # Avoid running the setup wizard twice (also guarded by not args.skip_setup later)
        args.skip_setup = True

    if not args.skip_setup and not args.adopt_only:
        from config.wizard import run_setup_wizard
        result = run_setup_wizard(args.config)
        if result is None:
            print("Setup cancelled. Exiting.")
            return 0
        print("\nStarting Cthulu with configured settings...\n")
    logger = setup_logger(
        name='herald',
        level=args.log_level,
        log_file='Cthulu.log',
        json_format=False
    )
    
    # Register signal handlers
    sig_module.signal(sig_module.SIGINT, signal_handler)
    sig_module.signal(sig_module.SIGTERM, signal_handler)
    
    logger.info("=" * 70)
    logger.info(f"Cthulu Autonomous Trading System v{__version__} - Phase 2")
    logger.info("=" * 70)
    
    # Load configuration using typed schema and mapping
    try:
        cfg = Config.load(args.config)
        logger.info(f"Configuration loaded from {args.config}")
        # Use model_dump() for Pydantic v2 compatibility
        config = cfg.model_dump() if hasattr(cfg, 'model_dump') else cfg.dict()
        
        # Apply mindset if specified
        if args.mindset:
            config = apply_mindset(config, args.mindset)
            logger.info(f"Applied '{args.mindset}' trading mindset")
            logger.info(f"  Risk: position_size_pct={config['risk'].get('position_size_pct', 2.0)}%, "
                       f"max_daily_loss=${config['risk'].get('max_daily_loss', 50)}")
        # Symbol override from CLI
        if args.symbol:
            config['trading']['symbol'] = args.symbol
            logger.info(f"Overriding trading symbol via CLI: {args.symbol}")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return 1
        
    # Initialize modules
    try:
        # 1. MT5 Connector
        logger.info("Initializing MT5 connector...")
        connection_config = ConnectionConfig(**config['mt5'])
        connector = MT5Connector(connection_config)
        
        # 2. Data Layer
        logger.info("Initializing data layer...")
        data_layer = DataLayer(cache_enabled=config.get('cache_enabled', True))
        
        # 3. Risk Manager
        logger.info("Initializing risk manager...")
        risk_config = config.get('risk', {})
        # Build RiskLimits with mapping and defaults
        risk_limits = RiskLimits(
            max_position_size_pct=risk_config.get('max_position_size_pct', 0.02),
            max_total_exposure_pct=risk_config.get('max_total_exposure_pct', 0.10),
            max_daily_loss_pct=risk_config.get('max_daily_loss_pct', 0.05),
            max_positions_per_symbol=risk_config.get('max_positions_per_symbol', 1),
            max_total_positions=risk_config.get('max_total_positions', 3),
            min_risk_reward_ratio=risk_config.get('min_risk_reward_ratio', 1.0),
        )
        risk_manager = RiskManager(risk_limits)
        
        # Ensure ml_collector is defined (safe default) so the execution engine construction does not raise
        ml_collector = None
        
        # 4. Execution Engine
        logger.info("Initializing execution engine...")
        execution_engine = ExecutionEngine(connector, risk_config=risk_config, ml_collector=ml_collector)
        
        # 5. Position Manager
        logger.info("Initializing position manager...")
        position_manager = PositionManager(connector, execution_engine)
        
        # 5b. Trade Manager (for adopting external trades)
        trade_adoption_config = config.get('orphan_trades', {})
        trade_adoption_policy = TradeAdoptionPolicy(
            enabled=trade_adoption_config.get('enabled', False),
            adopt_symbols=trade_adoption_config.get('adopt_symbols', []),
            ignore_symbols=trade_adoption_config.get('ignore_symbols', []),
            apply_exit_strategies=trade_adoption_config.get('apply_exit_strategies', True),
            max_adoption_age_hours=trade_adoption_config.get('max_adoption_age_hours', 0.0),
            log_only=trade_adoption_config.get('log_only', False)
        )
        # Provide default stop percentage and RR from risk config
        default_stop_pct = risk_config.get('emergency_stop_loss_pct', 8.0)
        default_rr = config.get('strategy', {}).get('params', {}).get('risk_reward_ratio', 2.0)
        trade_manager = TradeManager(position_manager, trade_adoption_policy, default_stop_pct=default_stop_pct, default_rr=default_rr, config=config)
        if trade_adoption_policy.enabled:
            logger.info(f"External trade adoption ENABLED (log_only: {trade_adoption_policy.log_only})")
        else:
            logger.info("External trade adoption disabled")
        
        # 6. Persistence
        logger.info("Initializing database...")
        db_path = config.get('database', {}).get('path', 'Cthulu.db')
        database = Database(db_path)
        
        # 7. Metrics
        logger.info("Initializing metrics collector...")
        metrics = MetricsCollector(database=database)

        # Terminal UI integration removed per user request.
        ui = None

        # Optional Prometheus exporter
        exporter = None
        try:
            prom_cfg = config.get('observability', {}).get('prometheus', {}) if isinstance(config, dict) else {}
            if prom_cfg.get('enabled', False):
                from cthulu.observability.prometheus import PrometheusExporter
                exporter = PrometheusExporter(prefix=prom_cfg.get('prefix', 'Cthulu'))
                logger.info('Prometheus exporter initialized')
        except Exception:
            logger.exception('Failed to initialize Prometheus exporter; continuing without it')

        # Attach metrics to execution engine if it exists so PositionManager can report opens
        try:
            if 'execution_engine' in locals() and execution_engine is not None:
                execution_engine.metrics = metrics
        except Exception:
            logger.debug('Failed to attach metrics to execution engine')
        
        # 7b. ML instrumentation collector (optional, configurable via config['ml'] or CLI)
        def init_ml_collector(config, args, logger):
            ml_collector = None
            try:
                ml_config = config.get('ml', {}) if isinstance(config, dict) else {}
                ml_enabled = ml_config.get('enabled', True)
                # CLI overrides config when provided
                if hasattr(args, 'enable_ml') and args.enable_ml is not None:
                    ml_enabled = args.enable_ml
                if ml_enabled:
                    from cthulu.ML_RL.instrumentation import MLDataCollector
                    ml_prefix = ml_config.get('prefix', 'events')
                    ml_collector = MLDataCollector(prefix=ml_prefix)
                    logger.info('MLDataCollector initialized')
                else:
                    logger.info('ML instrumentation disabled via config/CLI')
            except Exception:
                logger.exception('Failed to initialize MLDataCollector; continuing without it')
            return ml_collector

        ml_collector = init_ml_collector(config, args, logger)

        # Advisory manager (advisory/ghost modes)
        try:
            from cthulu.advisory.manager import AdvisoryManager
            advisory_cfg = config.get('advisory', {}) if isinstance(config, dict) else {}
            advisory_manager = AdvisoryManager(advisory_cfg, execution_engine, ml_collector)
            if advisory_manager.enabled:
                logger.info(f"AdvisoryManager enabled (mode={advisory_manager.mode})")
        except Exception:
            advisory_manager = None
            logger.exception('Failed to initialize AdvisoryManager; continuing without it')


        # 8. Load indicators
        logger.info("Loading indicators...")
        try:
            indicators = load_indicators(config.get('indicators', []))
            logger.info(f"Loaded {len(indicators)} indicators")
        except Exception as e:
            logger.exception('Failed to initialize indicators')
            logger.error('Configuration contains invalid indicator settings; please review your config and re-run the wizard')
            print('\nError: Failed to initialize indicators. See logs for details. Aborting startup.')
            return 1
        
        # 9. Load strategy
        logger.info("Loading trading strategy...")
        try:
            logger.debug("Strategy config: %s", config.get('strategy'))
            strategy = load_strategy(config['strategy'])
            logger.info(f"Loaded strategy: {strategy.__class__.__name__}")
        except Exception as e:
            logger.exception('Failed to initialize trading strategy')
            logger.error('Configuration contains invalid strategy settings; please review your config and re-run the wizard')
            print('\nError: Failed to initialize trading strategy. See logs for details. Aborting startup.')
            return 1
        
        # 10. Load exit strategies
        logger.info("Loading exit strategies...")
        exit_strategies = load_exit_strategies(config.get('exit_strategies', []))
        logger.info(f"Loaded {len(exit_strategies)} exit strategies")
        for es in exit_strategies:
            logger.info(f"  - {es.name} (priority: {es.priority}, enabled: {es.is_enabled()})")

        # 11. Start trade monitor (optional, non-blocking)
        try:
            from cthulu.monitoring.trade_monitor import TradeMonitor
            monitor = TradeMonitor(position_manager, trade_manager=trade_manager, poll_interval=config.get('monitor_poll_interval', 5.0), ml_collector=ml_collector if ml_collector else None)
            monitor.start()
            logger.info(f"TradeMonitor started (ml_collector={type(monitor.ml_collector)})")
        except Exception:
            logger.exception('Failed to start TradeMonitor; continuing without it')

        # Persisted summary helper and GUI autostart/monitoring
        def _persist_summary(metrics_collector, logger_obj, out_path: Path):
            try:
                from io import StringIO
                stream = StringIO()
                handler = logging.StreamHandler(stream)
                handler.setLevel(logging.INFO)
                logger_obj.addHandler(handler)
                try:
                    metrics_collector.print_summary()
                finally:
                    logger_obj.removeHandler(handler)
                content = stream.getvalue()
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with open(out_path, 'w', encoding='utf-8') as fh:
                    fh.write(content)
                    
                # Also persist strategy info if using dynamic selector
                try:
                    from cthulu.strategy.strategy_selector import StrategySelector
                    if isinstance(strategy, StrategySelector):
                        with open(out_path.parent / 'strategy_info.txt', 'w', encoding='utf-8') as fh:
                            fh.write(f"Current Strategy: {strategy.current_strategy.name if strategy.current_strategy else 'None'}\n")
                            fh.write(f"Current Regime: {strategy.current_regime}\n")
                            fh.write(f"\nAvailable Strategies:\n")
                            for name in strategy.strategies.keys():
                                perf = strategy.performance[name]
                                fh.write(f"  - {name}: {perf.signals_count} signals, {perf.win_rate:.1%} win rate\n")
                except Exception:
                    pass
                    
            except Exception:
                logger_obj.exception('Failed to persist metrics summary')

        # Summary file path (persisted so terminal summary survives backgrounding)
        summary_path = Path(__file__).parent / 'logs' / 'latest_summary.txt'

        # Print and persist an initial summary now that metrics exists
        try:
            _persist_summary(metrics, logger, summary_path)
        except Exception:
            logger.exception('Failed to persist initial metrics summary')

        # Auto-launch GUI by default unless explicitly disabled in config
        gui_proc = None
        try:
            ui_cfg = config.get('ui', {}) if isinstance(config, dict) else {}
            autostart_gui = True
            if 'enabled' in ui_cfg:
                autostart_gui = bool(ui_cfg.get('enabled'))
            if 'autostart' in ui_cfg:
                autostart_gui = bool(ui_cfg.get('autostart'))

            # Respect CLI headless flags to disable GUI regardless of config
            if getattr(args, 'no_gui', False) or getattr(args, 'headless', False):
                autostart_gui = False
                logger.info('GUI autostart disabled via CLI (--no-gui/--headless)')

            if autostart_gui:
                gui_cmd = [sys.executable, '-m', 'Cthulu.ui.desktop']
                try:
                    # Capture GUI stdout/stderr to files to diagnose immediate failures
                    gui_out = Path(__file__).parent / 'logs' / 'gui_stdout.log'
                    gui_err = Path(__file__).parent / 'logs' / 'gui_stderr.log'
                    gui_out.parent.mkdir(parents=True, exist_ok=True)
                    out_f = open(gui_out, 'a', encoding='utf-8')
                    err_f = open(gui_err, 'a', encoding='utf-8')
                    gui_proc = subprocess.Popen(gui_cmd, stdout=out_f, stderr=err_f)
                    # Wait briefly to detect immediate failures
                    time.sleep(0.5)
                    if gui_proc.poll() is not None:
                        # Process exited quickly — treat as launch failure
                        logger.error('Desktop GUI process exited immediately (check logs/gui_stderr.log)')
                        try:
                            out_f.close(); err_f.close()
                        except Exception:
                            pass
                        gui_proc = None
                    else:
                        logger.info('Desktop GUI launched (best-effort). Closing GUI will stop Herald.')
                        # Hide console window on Windows so terminal goes to background
                        try:
                            if os.name == 'nt':
                                import ctypes
                                hwnd = ctypes.windll.kernel32.GetConsoleWindow()
                                if hwnd:
                                    ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
                        except Exception:
                            logger.exception('Failed to hide console window')
                except Exception:
                    logger.exception('Failed to launch Desktop GUI; continuing in terminal mode')

            # If GUI started and is still running, monitor it and request shutdown when it exits
            if gui_proc is not None:
                import threading

                def _monitor_gui(p):
                    try:
                        p.wait()
                        rc = p.returncode
                        logger.info('GUI process exited with return code %s', rc)
                        # If GUI exited cleanly (user closed it), treat as explicit shutdown request.
                        # If GUI crashed (non-zero), keep Cthulu running as the primary terminal and restore console.
                        if rc == 0:
                            # If the GUI process exited cleanly, check whether it was a short-lived
                            # instance that exited because another GUI instance is already running
                            lock_file = Path(__file__).parent / 'logs' / '.gui_lock'
                            another_active = False
                            if lock_file.exists():
                                try:
                                    with open(lock_file, 'r') as f:
                                        other_pid = int(f.read().strip())
                                    if other_pid != p.pid:
                                        # Check whether the other PID is alive
                                        alive = False
                                        if os.name == 'nt':
                                            try:
                                                import ctypes
                                                kernel32 = ctypes.windll.kernel32
                                                PROCESS_QUERY_INFORMATION = 0x0400
                                                handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, 0, other_pid)
                                                if handle:
                                                    kernel32.CloseHandle(handle)
                                                    alive = True
                                            except Exception:
                                                alive = False
                                        else:
                                            try:
                                                os.kill(other_pid, 0)
                                                alive = True
                                            except Exception:
                                                alive = False

                                        if alive:
                                            another_active = True
                                            logger.info('GUI instance exited because another GUI (pid=%s) is active; continuing Herald', other_pid)
                                except Exception:
                                    logger.exception('Error while inspecting GUI lock file')

                            if another_active:
                                # Expected behaviour (another GUI is the canonical instance); do not request shutdown.
                                return

                            # Otherwise treat as a user-closed GUI and request shutdown
                            logger.info('GUI closed by user; requesting shutdown of Herald')
                            global shutdown_requested
                            shutdown_requested = True
                        else:
                            logger.error('GUI crashed (non-zero exit). Continuing in terminal mode.')
                            try:
                                # Attempt to restore console visibility on Windows so operator can see terminal
                                if os.name == 'nt':
                                    import ctypes
                                    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
                                    if hwnd:
                                        ctypes.windll.user32.ShowWindow(hwnd, 1)  # SW_SHOWNORMAL
                            except Exception:
                                logger.exception('Failed to restore console window')
                    except Exception:
                        logger.exception('GUI monitor thread exception')

                gui_thread = threading.Thread(target=_monitor_gui, args=(gui_proc,), daemon=True, name='GUIMonitor')
                gui_thread.start()
        except Exception:
            logger.exception('Failed to handle GUI autostart')

        # 11b. Optional interactive manual trade prompt (runs in background thread if enabled and interactive)
        def _manual_trade_prompt_thread(ex_engine, pos_manager, db, default_symbol: str):
            """Background thread that offers a persistent prompt to the user to place manual trades.

            This thread uses blocking input() calls so must only be used in interactive terminals.
            It will construct an OrderRequest and submit it via the provided ExecutionEngine.
            """
            import threading
            import sys

            thread_name = threading.current_thread().name
            logger.info(f"Manual trade prompt thread started ({thread_name})")
            try:
                while True:
                    try:
                        ans = input('\nPlace manual trade? (y/N): ').strip().lower()
                    except EOFError:
                        # Non-interactive stream closed
                        logger.info('Manual prompt input closed; stopping prompt thread')
                        break

                    if ans not in ('y', 'yes'):
                        # small delay to avoid tight loop and reduce prompt spam
                        time.sleep(2.0)
                        continue

                    # Gather trade details
                    try:
                        symbol = input(f"Symbol [{default_symbol}]: ").strip() or default_symbol
                        side = (input("Side (BUY/SELL) [BUY]: ").strip() or 'BUY').upper()
                        volume_raw = input("Volume (lots) [0.01]: ").strip() or '0.01'
                        volume = float(volume_raw)
                        price_raw = input("Price (enter 'market' or a numeric limit price) [market]: ").strip() or 'market'
                        sl_raw = input("Stop Loss (optional, leave blank for none): ").strip() or None
                        tp_raw = input("Take Profit (optional, leave blank for none): ").strip() or None
                    except Exception as e:
                        logger.exception(f"Manual prompt input error: {e}")
                        continue

                    # Determine order type
                    try:
                        if price_raw.lower() in ('market', 'm', 'current', 'c'):
                            order_type = OrderType.MARKET
                            price = None
                        else:
                            order_type = OrderType.LIMIT
                            price = float(price_raw)
                    except Exception as e:
                        logger.error(f"Invalid price input: {e}")
                        continue

                    sl = float(sl_raw) if sl_raw else None
                    tp = float(tp_raw) if tp_raw else None

                    # Build and submit order
                    order_req = OrderRequest(
                        signal_id='manual_prompt',
                        symbol=symbol,
                        side='BUY' if side == 'BUY' else 'SELL',
                        volume=volume,
                        order_type=order_type,
                        price=price,
                        sl=sl,
                        tp=tp
                    )

                    logger.info(f"Manual request: {order_req.side} {order_req.volume} {order_req.symbol} @ {order_req.price or 'market'}")

                    try:
                        res = ex_engine.place_order(order_req)
                        if res and res.status == OrderStatus.FILLED:
                            logger.info(f"Manual order filled: ticket={res.order_id} price={res.fill_price}")
                            # Track position in registry
                            try:
                                tracked = pos_manager.track_position(res, signal_metadata={})
                                if tracked:
                                    logger.info(f"Tracked manual position: #{tracked.ticket}")
                                # Record to DB
                                try:
                                    tr = TradeRecord(
                                        signal_id='manual_prompt',
                                        order_id=res.order_id,
                                        symbol=order_req.symbol,
                                        side=order_req.side,
                                        entry_price=res.fill_price,
                                        volume=res.filled_volume,
                                        entry_time=datetime.now(),
                                    )
                                    db.record_trade(tr)
                                except Exception:
                                    logger.exception('Failed to record manual trade to DB')
                            except Exception:
                                logger.exception('Failed to track manual position')
                        else:
                            logger.error(f"Manual order failed: {getattr(res,'message',str(res))}")
                    except Exception:
                        logger.exception('Error placing manual order via ExecutionEngine')

            except Exception:
                logger.exception('Manual prompt thread failed')

        # Start interactive prompt only if explicitly requested via CLI (--manual-prompt)
        try:
            import sys as _sys
            if args.manual_prompt:
                try:
                    import threading as _threading
                    prompt_thread = _threading.Thread(target=_manual_trade_prompt_thread, args=(execution_engine, position_manager, database, config.get('trading', {}).get('symbol', '')), daemon=True, name='manual-prompt')
                    prompt_thread.start()
                    logger.info('Manual trade prompt enabled (CLI flag)')
                    logger.info('Tip: Use --manual-prompt to enable the terminal prompt interactively')
                except Exception:
                    logger.exception('Failed to start manual trade prompt thread')
            else:
                logger.info('Manual trade prompt not started (use --manual-prompt to enable)')
        except Exception:
            logger.exception('Error initializing manual trade prompt')

        # Start RPC server by default (no CLI flag required) - local-only by design
        try:
            import os as _os
            token = _os.getenv('Cthulu_API_TOKEN')
            from cthulu.rpc.server import run_rpc_server
            try:
                if not token:
                    logger.warning('Cthulu_API_TOKEN not set; RPC server running locally unauthenticated')
                rpc_thread, rpc_server = run_rpc_server(args.rpc_host, args.rpc_port, token, execution_engine, risk_manager, position_manager, database)
                logger.info('RPC server started (default enabled)')
            except Exception:
                logger.exception('Failed to start RPC server')
        except Exception:
            logger.exception('Error initializing RPC server')

        # 11b. Optional News / Calendar ingest pipeline (opt-in via config or env)
        try:
            news_cfg = config.get('news', {}) if isinstance(config, dict) else {}
            env_enable = os.getenv('NEWS_INGEST_ENABLED')
            news_enabled = news_cfg.get('enabled', False) or (env_enable == '1')
            news_ingestor = None
            if news_enabled:
                from cthulu.news import RssAdapter, NewsApiAdapter, FREDAdapter, TradingEconomicsAdapter, NewsIngestor, NewsManager
                adapters = []
                # RSS fallback
                if os.getenv('NEWS_USE_RSS', str(news_cfg.get('use_rss', True))).lower() in ('1', 'true', 'yes'):
                    feeds = os.getenv('NEWS_RSS_FEEDS', news_cfg.get('rss_feeds', ''))
                    feeds_list = [f.strip() for f in feeds.split(',') if f.strip()]
                    if feeds_list:
                        adapters.append(RssAdapter(feeds=feeds_list))

                # API-based adapters
                if os.getenv('NEWSAPI_KEY'):
                    adapters.append(NewsApiAdapter(api_key=os.getenv('NEWSAPI_KEY')))
                if os.getenv('FRED_API_KEY'):
                    adapters.append(FREDAdapter(api_key=os.getenv('FRED_API_KEY')))

                cache_ttl = int(os.getenv('NEWS_CACHE_TTL', news_cfg.get('cache_ttl', 300)))
                news_manager = NewsManager(adapters=adapters, cache_ttl=cache_ttl)

                cal_adapter = None
                if os.getenv('ECON_CAL_API_KEY'):
                    cal_adapter = TradingEconomicsAdapter(api_key=os.getenv('ECON_CAL_API_KEY'))

                if ml_collector is None:
                    logger.warning('News ingest requested but MLDataCollector is not initialized; skipping NewsIngestor')
                else:
                    interval = int(os.getenv('NEWS_INGEST_INTERVAL', news_cfg.get('interval_seconds', 300)))
                    news_ingestor = NewsIngestor(news_manager, cal_adapter, ml_collector, interval_seconds=interval)
                    news_ingestor.start()
                    logger.info('NewsIngestor started (interval %ss). Adapters: %s calendar=%s', interval, [type(a).__name__ for a in adapters], type(cal_adapter).__name__ if cal_adapter else None)
                    # Wire monitor -> news_manager for real-time alerts
                    try:
                        if 'monitor' in locals() and monitor:
                            monitor.news_manager = news_manager
                            monitor.news_alert_window = int(os.getenv('NEWS_ALERT_WINDOW', news_cfg.get('alert_window', 600)))
                            logger.info('TradeMonitor wired to NewsManager for alerts (window %ss)', monitor.news_alert_window)
                    except Exception:
                        logger.exception('Failed to wire NewsManager to TradeMonitor')
        except Exception:
            logger.exception('Failed to initialize NewsIngestor; continuing without it')
            
    except Exception as e:
        logger.error(f"Failed to initialize modules: {e}", exc_info=True)
        return 1
        
    # Connect to MT5
    try:
        logger.info("Connecting to MetaTrader 5...")
        if not connector.connect():
            logger.error("Failed to connect to MT5")
            return 1
            
        account_info = connector.get_account_info()
        logger.info(f"Connected to MT5 account {account_info['login']}")
        logger.info(f"Balance: {account_info['balance']:.2f}, Equity: {account_info['equity']:.2f}")
        
        # Reconcile any existing Cthulu positions from previous session
        reconciled = position_manager.reconcile_positions()
        if reconciled > 0:
            logger.info(f"Reconciled {reconciled} existing Cthulu position(s)")
        
        # Adopt any external trades if enabled
        if args.adopt_only:
            if trade_adoption_policy.enabled:
                adopted = trade_manager.scan_and_adopt()
                logger.info(f"Adopted {adopted} external trade(s) (adopt-only mode). Exiting.")
            else:
                logger.warning("Adopt-only requested but external trade adoption is disabled in config.")
            return 0
        else:
            if trade_adoption_policy.enabled:
                adopted = trade_manager.scan_and_adopt()
                if adopted > 0:
                    logger.info(f"Adopted {adopted} external trade(s)")

        # If user requested adoption only mode, exit after adoption
        if args.adopt_only:
            logger.info("Adopt-only mode complete. Exiting.")
            return 0
        
    except Exception as e:
        logger.error(f"Connection error: {e}", exc_info=True)
        return 1
        
    # Trading configuration
    trading_config = config.get('trading', {})
    symbol = trading_config.get('symbol')
    timeframe = getattr(mt5, trading_config.get('timeframe'))
    poll_interval = trading_config.get('poll_interval', 60)
    lookback_bars = trading_config.get('lookback_bars', 500)
    
    logger.info(f"Trading configuration: {symbol} on {config['trading']['timeframe']}")
    logger.info(f"Poll interval: {poll_interval}s, Lookback: {lookback_bars} bars")
    
    if args.dry_run:
        logger.warning("DRY RUN MODE - No real orders will be placed")
        
    # Main trading loop
    logger.info("Starting autonomous trading loop...")
    logger.info("Press Ctrl+C to shutdown gracefully")
    
    loop_count = 0
    global shutdown_requested
    
    try:
        while not shutdown_requested:
            loop_count += 1
            loop_start = datetime.now()
            logger.debug(f"Loop #{loop_count} started at {loop_start}")
            
            # 4. Market data ingestion
            try:
                rates = connector.get_rates(
                    symbol=symbol,
                    timeframe=timeframe,
                    count=lookback_bars
                )
                
                if rates is None or len(rates) == 0:
                    logger.warning("No market data received, skipping cycle")
                    time.sleep(poll_interval)
                    continue
                    
                df = data_layer.normalize_rates(rates, symbol=symbol)
                logger.debug(f"Retrieved {len(df)} bars for {symbol}")
                
            except Exception as e:
                logger.error(f"Market data error: {e}", exc_info=True)
                time.sleep(poll_interval)
                continue
                
            # 5. Calculate indicators
            try:
                # Calculate SMA indicators for strategy (use strategy params when available)
                try:
                    short_w = getattr(strategy, 'short_window', None)
                    long_w = getattr(strategy, 'long_window', None)
                    if short_w and long_w:
                        df[f'sma_{short_w}'] = df['close'].rolling(window=int(short_w)).mean()
                        df[f'sma_{long_w}'] = df['close'].rolling(window=int(long_w)).mean()
                    else:
                        # Fallback to legacy defaults
                        df['sma_20'] = df['close'].rolling(window=20).mean()
                        df['sma_50'] = df['close'].rolling(window=50).mean()
                except Exception:
                    # If anything goes wrong, compute defaults and continue
                    df['sma_20'] = df['close'].rolling(window=20).mean()
                    df['sma_50'] = df['close'].rolling(window=50).mean()
                
                # Compute required EMA columns for strategies (so EMA-based strategies find their inputs)
                try:
                    required_emas = set()

                    def collect_ema_periods(obj):
                        if obj is None:
                            return
                        # Common attribute names used across strategies
                        for attr in ('fast_period', 'slow_period', 'fast_ema', 'slow_ema', 'short_window', 'long_window'):
                            if hasattr(obj, attr):
                                try:
                                    val = int(getattr(obj, attr))
                                    # skip sma names (short/long windows already handled)
                                    if 'ema' in attr or 'fast_period' in attr or 'slow_period' in attr or 'fast_ema' in attr or 'slow_ema' in attr:
                                        required_emas.add(val)
                                except Exception:
                                    pass

                    # If using StrategySelector, inspect child strategies
                    try:
                        from cthulu.strategy.strategy_selector import StrategySelector
                        if isinstance(strategy, StrategySelector):
                            for s in strategy.strategies.values():
                                collect_ema_periods(s)
                        else:
                            collect_ema_periods(strategy)
                    except Exception:
                        collect_ema_periods(strategy)

                    # Also inspect scalping-specific attrs
                    try:
                        if hasattr(strategy, 'fast_ema'):
                            required_emas.add(int(getattr(strategy, 'fast_ema')))
                        if hasattr(strategy, 'slow_ema'):
                            required_emas.add(int(getattr(strategy, 'slow_ema')))
                    except Exception:
                        pass

                    # Fallback: collect EMA periods from configuration to ensure coverage
                    try:
                        strat_cfg = config.get('strategy', {}) if isinstance(config, dict) else {}
                        if strat_cfg.get('type') == 'dynamic':
                            for s in strat_cfg.get('strategies', []):
                                params = s.get('params', {}) if isinstance(s.get('params', {}), dict) else {}
                                for key in ('fast_ema', 'slow_ema', 'fast_period', 'slow_period', 'short_window', 'long_window'):
                                    if key in params and params[key]:
                                        try:
                                            required_emas.add(int(params[key]))
                                        except Exception:
                                            pass
                        else:
                            params = strat_cfg.get('params', {}) if isinstance(strat_cfg.get('params', {}), dict) else {}
                            for key in ('fast_ema', 'slow_ema', 'fast_period', 'slow_period', 'short_window', 'long_window'):
                                if key in params and params[key]:
                                    try:
                                        required_emas.add(int(params[key]))
                                    except Exception:
                                        pass

                        # If scalping is part of configured strategies ensure its default EMAs are included
                        try:
                            scalping_periods = set()
                            # Check dynamic strategies
                            if strat_cfg.get('type') == 'dynamic':
                                for s in strat_cfg.get('strategies', []):
                                    if s.get('type', '').lower() == 'scalping':
                                        params = s.get('params', {}) or {}
                                        # scalping may define explicit fast_ema/slow_ema
                                        if params.get('fast_ema'):
                                            scalping_periods.add(int(params.get('fast_ema')))
                                        if params.get('slow_ema'):
                                            scalping_periods.add(int(params.get('slow_ema')))
                            else:
                                if strat_cfg.get('type', '').lower() == 'scalping':
                                    params = strat_cfg.get('params', {}) or {}
                                    if params.get('fast_ema'):
                                        scalping_periods.add(int(params.get('fast_ema')))
                                    if params.get('slow_ema'):
                                        scalping_periods.add(int(params.get('slow_ema')))

                            # If scalping is present among runtime strategies, add defaults (5,10) as safe fallback
                            try:
                                from cthulu.strategy.strategy_selector import StrategySelector
                                if isinstance(strategy, StrategySelector):
                                    if 'scalping' in (name.lower() for name in strategy.strategies.keys()):
                                        scalping_periods.update({5, 10})
                            except Exception:
                                # Direct strategy instance
                                try:
                                    if getattr(strategy, 'name', '').lower() == 'scalping':
                                        scalping_periods.update({getattr(strategy, 'fast_ema', 5), getattr(strategy, 'slow_ema', 10)})
                                except Exception:
                                    pass

                            required_emas.update({int(x) for x in scalping_periods if x})
                        except Exception:
                            pass

                        logger.debug(f"Collected EMA periods from config: {sorted(required_emas)}")
                    except Exception:
                        pass

                    # Compute EMA columns
                    if required_emas:
                        for p in sorted(required_emas):
                            col = f'ema_{p}'
                            if col not in df.columns:
                                df[col] = df['close'].ewm(span=int(p), adjust=False).mean()
                        logger.debug(f"Computed EMA columns: {[f'ema_{p}' for p in sorted(required_emas)]}")
                except Exception:
                    logger.exception('Failed to compute EMA columns; continuing')

                # Ensure runtime indicators (RSI/ATR/MACD/etc.) are added if the strategy needs them
                try:
                    extra_indicators = ensure_runtime_indicators(df, indicators, strategy, config, logger)
                    if extra_indicators:
                        indicators.extend(extra_indicators)
                        try:
                            names = [getattr(i, 'name', i.__class__.__name__) for i in extra_indicators]
                        except Exception:
                            names = [i.__class__.__name__ for i in extra_indicators]
                        logger.info(f"Added {len(extra_indicators)} runtime indicators: {names}")
                except Exception:
                    logger.exception('Failed to ensure runtime indicators')

                # Calculate configured indicators (and any runtime-added ones)
                try:
                    for indicator in indicators:
                        try:
                            indicator_data = indicator.calculate(df)
                            if indicator_data is not None:
                                df = df.join(indicator_data, how='left')
                        except Exception:
                            logger.exception(f"Failed to calculate indicator {getattr(indicator, 'name', indicator.__class__.__name__)}")
                except Exception:
                    logger.exception('Failed during indicator calculations')

                logger.debug(f"Calculated SMA, ATR, and {len(indicators)} additional indicators")
                
            except Exception as e:
                logger.error(f"Indicator calculation error: {e}", exc_info=True)
                time.sleep(poll_interval)
                continue
                
            # 6. Generate strategy signals
            try:
                current_bar = df.iloc[-1]
                # Diagnostic: log presence of RSI/ATR before strategy signal generation
                try:
                    rsi_period = getattr(strategy, 'rsi_period', None)
                    try:
                        rsi_period_int = int(rsi_period) if rsi_period is not None else None
                    except Exception:
                        rsi_period_int = None
                    rsi_col = f"rsi_{rsi_period_int}" if rsi_period_int and rsi_period_int != 14 else 'rsi'
                    has_rsi = rsi_col in current_bar.index
                    has_atr = 'atr' in current_bar.index
                    logger.debug(f"Before strategy signal: has_rsi={has_rsi} (col={rsi_col}), has_atr={has_atr}")
                    if has_rsi:
                        logger.debug(f"rsi value: {current_bar.get(rsi_col)}")
                    if has_atr:
                        logger.debug(f"atr value: {current_bar.get('atr')}")
                except Exception:
                    logger.exception('Failed to log indicator presence before strategy signal')

                # If dynamic selector, use its generator method
                try:
                    from cthulu.strategy.strategy_selector import StrategySelector
                    if isinstance(strategy, StrategySelector):
                        signal = strategy.generate_signal(df, current_bar)
                    else:
                        signal = strategy.on_bar(current_bar)
                except Exception:
                    # Fallback by duck-typing
                    if hasattr(strategy, 'generate_signal'):
                        signal = strategy.generate_signal(df, current_bar)
                    else:
                        signal = strategy.on_bar(current_bar)

                if signal:
                    logger.info(
                        f"Signal generated: {signal.side.name} {signal.symbol} "
                        f"(confidence: {signal.confidence:.2f})"
                    )

            except Exception as e:
                logger.error(f"Strategy signal error: {e}", exc_info=True)
                signal = None
                
            # 7. Process entry signals
            if signal and signal.side in [SignalType.LONG, SignalType.SHORT]:
                try:
                    # Get current account info and positions
                    account_info = connector.get_account_info()
                    current_positions = len(position_manager.get_positions(symbol=symbol))
                    
                    # Risk approval
                    approved, reason, position_size = risk_manager.approve(
                        signal=signal,
                        account_info=account_info,
                        current_positions=current_positions
                    )
                    
                    if approved:
                        logger.info(f"Risk approved: {position_size:.2f} lots - {reason}")
                        
                        if not args.dry_run:
                            # Create order request
                            order_req = OrderRequest(
                                signal_id=signal.id,
                                symbol=signal.symbol,
                                side="BUY" if signal.side == SignalType.LONG else "SELL",
                                volume=position_size,
                                order_type=OrderType.MARKET,
                                sl=signal.stop_loss,
                                tp=signal.take_profit
                            )

                            # Advisory / ghost handling
                            try:
                                if 'advisory_manager' in locals() and advisory_manager and advisory_manager.enabled:
                                    decision = advisory_manager.decide(order_req, signal)
                                else:
                                    decision = {'action': 'execute', 'result': None}
                            except Exception:
                                logger.exception('Advisory manager decision failed; defaulting to execute')
                                decision = {'action': 'execute', 'result': None}

                            if decision['action'] == 'execute':
                                # Execute order
                                logger.info(f"Placing {order_req.side} order for {order_req.volume} lots")
                                result = execution_engine.place_order(order_req)

                                if result.status == OrderStatus.FILLED:
                                    logger.info(
                                        f"Order filled: ticket={result.order_id}, "
                                        f"price={result.fill_price:.5f}"
                                    )
                                    
                                    # Track position
                                    position_info = position_manager.track_position(result, signal_metadata=signal.metadata)
                                    
                                    # Record in database
                                    signal_record = SignalRecord(
                                        timestamp=signal.timestamp,
                                        symbol=signal.symbol,
                                        side=signal.side.name,
                                        confidence=signal.confidence,
                                        price=result.fill_price,
                                        stop_loss=signal.stop_loss,
                                        take_profit=signal.take_profit,
                                        strategy_name=strategy.__class__.__name__,
                                        metadata=signal.metadata,
                                        executed=True,
                                        execution_timestamp=datetime.now()
                                    )
                                    database.record_signal(signal_record)
                                    
                                    trade_record = TradeRecord(
                                        signal_id=signal.id,
                                        order_id=result.order_id,
                                        symbol=signal.symbol,
                                        side=signal.side.name,
                                        entry_price=result.fill_price,
                                        volume=result.filled_volume,
                                        stop_loss=signal.stop_loss,
                                        take_profit=signal.take_profit,
                                        entry_time=datetime.now(),
                                        commission=result.commission
                                    )
                                    database.record_trade(trade_record)
                                    
                                else:
                                    logger.error(
                                        f"Order failed: {result.status.name} - {result.message}"
                                    )

                            elif decision['action'] == 'advisory':
                                logger.info('Advisory decision: not executing order; recording advisory signal')
                                signal_record = SignalRecord(
                                    timestamp=signal.timestamp,
                                    symbol=signal.symbol,
                                    side=signal.side.name,
                                    confidence=signal.confidence,
                                    price=None,
                                    stop_loss=signal.stop_loss,
                                    take_profit=signal.take_profit,
                                    strategy_name=strategy.__class__.__name__,
                                    metadata={**signal.metadata, 'advisory': True},
                                    executed=False
                                )
                                database.record_signal(signal_record)

                            elif decision['action'] == 'ghost':
                                logger.info('Ghost decision: small test trade executed (or attempted)')
                                res = decision.get('result')
                                # Record ghost attempt (do not adopt as live trade)
                                signal_record = SignalRecord(
                                    timestamp=signal.timestamp,
                                    symbol=signal.symbol,
                                    side=signal.side.name,
                                    confidence=signal.confidence,
                                    price=getattr(res, 'fill_price', None) if res else None,
                                    stop_loss=signal.stop_loss,
                                    take_profit=signal.take_profit,
                                    strategy_name=strategy.__class__.__name__,
                                    metadata={**signal.metadata, 'advisory': 'ghost', 'advisory_result': getattr(res, 'order_id', None) if res else None},
                                    executed=False
                                )
                                database.record_signal(signal_record)

                            else:
                                logger.warning('Advisory manager rejected order request')

                        else:
                            logger.info("[DRY RUN] Would place order here")
                    else:
                        logger.info(f"Risk rejected: {reason}")
                        
                except Exception as e:
                    logger.error(f"Order execution error: {e}", exc_info=True)
            
            # 7b. Scan and adopt external trades
            try:
                if trade_adoption_policy.enabled:
                    adopted = trade_manager.scan_and_adopt()
                    if adopted > 0:
                        logger.info(f"Adopted {adopted} external trade(s)")
            except Exception as e:
                logger.error(f"Trade adoption scan error: {e}", exc_info=True)
                    
            # 8. Monitor positions and check exits
            try:
                positions = position_manager.monitor_positions()
                if positions:
                    logger.debug(f"Monitoring {len(positions)} open positions")

                    total_pnl = sum(p.unrealized_pnl for p in positions)
                    logger.debug(f"Total unrealized P&L: {total_pnl:.2f}")

                # Push latest positions and metrics to UI when available
                try:
                    if 'ui' in locals() and ui is not None:
                        # Convert PositionInfo -> serializable dicts
                        simple_positions = []
                        for p in positions:
                            simple_positions.append({
                                'ticket': getattr(p, 'ticket', None),
                                'symbol': getattr(p, 'symbol', None),
                                'side': getattr(p, 'side', None),
                                'volume': getattr(p, 'volume', 0.0),
                                'price': getattr(p, 'open_price', getattr(p, 'entry_price', None)),
                                'sl': getattr(p, 'stop_loss', None),
                                'tp': getattr(p, 'take_profit', None),
                                'pnl': getattr(p, 'unrealized_pnl', 0.0),
                            })

                except Exception:
                    logger.exception('Failed to update Terminal UI')

                # Check each position against exit strategies
                for position in positions:
                        # Prepare market data for exit strategies
                        exit_data = {
                            'current_price': position.current_price,
                            'current_data': df.iloc[-1],
                            'account_info': account_info,
                            'indicators': {
                                'atr': df['atr'].iloc[-1] if 'atr' in df.columns else None
                            }
                        }
                        
                        # Check exit strategies (already sorted by priority)
                        for exit_strategy in exit_strategies:
                            if not exit_strategy.is_enabled():
                                continue
                                
                            exit_signal = exit_strategy.should_exit(position, exit_data)
                            
                            if exit_signal:
                                logger.info(
                                    f"Exit triggered by {exit_signal.strategy_name}: "
                                    f"{exit_signal.reason}"
                                )
                                
                                if not args.dry_run:
                                    # Close position
                                    close_result = position_manager.close_position(
                                        ticket=position.ticket,
                                        reason=exit_signal.reason,
                                        partial_volume=exit_signal.partial_volume
                                    )
                                    
                                    if close_result.status == OrderStatus.FILLED:
                                        logger.info(
                                            f"Position closed: ticket={position.ticket}, "
                                            f"P&L={position.unrealized_pnl:.2f}"
                                        )
                                        
                                        # Update database
                                        database.update_trade_exit(
                                            order_id=position.ticket,
                                            exit_price=close_result.fill_price,
                                            exit_time=datetime.now(),
                                            profit=position.unrealized_pnl,
                                            exit_reason=exit_signal.reason
                                        )

                                        # Record position closed for metrics (PositionManager already records the realized trade)
                                        try:
                                            metrics.record_position_closed(position.symbol)
                                        except Exception:
                                            logger.debug('Failed to record position closed in metrics', exc_info=True)

                                        # Update risk manager
                                        risk_manager.record_trade_result(position.unrealized_pnl)
                                        
                                    else:
                                        logger.error(
                                            f"Failed to close position {position.ticket}: "
                                            f"{close_result.message}"
                                        )
                                else:
                                    logger.info("[DRY RUN] Would close position here")
                                    
                                # Exit after first strategy triggers (highest priority wins)
                                break
                                
            except Exception as e:
                logger.error(f"Position monitoring error: {e}", exc_info=True)
                
            # 9. Health monitoring
            try:
                if not connector.is_connected():
                    logger.warning("Connection lost, attempting reconnect...")

                    success = connector.reconnect()
                    if success:
                        logger.info("Reconnection successful")
                        # Reconcile positions after reconnect
                        reconciled = position_manager.reconcile_positions()
                        logger.info(f"Reconciled {reconciled} positions")
                    else:
                        logger.error("Reconnection failed; will keep trying on subsequent cycles")
                        # Avoid tight-looping on repeated failures; wait a short backoff before next iteration
                        try:
                            time.sleep(min(30, poll_interval))
                        except Exception:
                            pass
                        # Continue to next loop and keep attempting reconnection
                        continue
                        
            except Exception as e:
                logger.error(f"Health check error: {e}", exc_info=True)
                
            # Performance monitoring
            if loop_count % 100 == 0:
                logger.info(f"Performance metrics after {loop_count} loops:")
                # Sync latest position stats into metrics and persist the printed summary
                stats = position_manager.get_statistics()
                try:
                    pos_summary = position_manager.get_position_summary_by_symbol()
                    metrics.sync_with_positions_summary(stats, pos_summary)
                    try:
                        _persist_summary(metrics, logger, summary_path)
                    except Exception:
                        logger.exception('Failed to persist periodic metrics summary')
                    # Publish to Prometheus exporter if present
                    try:
                        if exporter is not None:
                            metrics.publish_to_prometheus(exporter)
                    except Exception:
                        logger.debug('Failed to publish metrics to Prometheus exporter')
                except Exception:
                    logger.exception('Failed to sync position summary into metrics')
                logger.info(f"Position stats: {stats}")
                
            # 10. Wait for next cycle
            loop_duration = (datetime.now() - loop_start).total_seconds()
            logger.debug(f"Loop completed in {loop_duration:.2f}s")
            
            sleep_time = max(0, poll_interval - loop_duration)
            if sleep_time > 0:
                time.sleep(sleep_time)

            # Debug/testing: exit after max_loops if requested
            try:
                if getattr(args, 'max_loops', 0) and loop_count >= int(args.max_loops):
                    logger.info(f"Reached max_loops={args.max_loops}; exiting main loop for test")
                    break
            except Exception:
                pass
                
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Fatal error in main loop: {e}", exc_info=True)
        return 1
    finally:
        # Cleanup and shutdown
        logger.info("Initiating graceful shutdown...")
        
        try:
            # Ask user what to do with open positions (do NOT force-close by default)
            if not args.dry_run:
                # Prefer to prompt the user, but be resilient if stdin was consumed earlier
                def _prompt_console(prompt_text: str, default: str = 'n') -> str:
                    try:
                        # Try normal input first
                        if sys.stdin.isatty() and not getattr(args, 'no_prompt', False):
                            return input(prompt_text).strip().lower()
                        # Fall back to opening the platform console directly (works when stdin has been redirected)
                        if os.name == 'nt':
                            with open('CONIN$', 'r') as con:
                                print(prompt_text, end='', flush=True)
                                return con.readline().strip().lower()
                        else:
                            with open('/dev/tty', 'r') as tty:
                                print(prompt_text, end='', flush=True)
                                return tty.readline().strip().lower()
                    except Exception:
                        return default.lower()

                # Ask user explicitly what to do with open positions
                choice = _prompt_console("\nShutdown requested. What should I do with open positions?\n  [A] Close ALL positions\n  [N] Leave positions OPEN (default)\n  [S] Close specific tickets (comma-separated)\nChoose (A/n/s): ", 'n')

                if choice in ('a', 'all'):
                    logger.info("User requested: close ALL positions")
                    close_results = position_manager.close_all_positions("System shutdown")
                    logger.info(f"Closed {len(close_results)} positions")
                elif choice in ('s', 'select'):
                    tickets = _prompt_console("Enter ticket numbers to close (comma-separated): ", '')
                    ids = [int(x.strip()) for x in tickets.split(',') if x.strip().isdigit()]
                    closed = 0
                    for t in ids:
                        res = position_manager.close_position(ticket=t, reason="User shutdown request")
                        if res and getattr(res, 'status', None) == getattr(res, 'status', None):
                            closed += 1
                    logger.info(f"Closed {closed} user-selected positions")
                else:
                    logger.info("User chose to leave open positions untouched")

            # Print final metrics and persist to summary file
            logger.info("Final performance metrics:")
            try:
                _persist_summary(metrics, logger, summary_path)
            except Exception:
                logger.exception('Failed to persist final metrics summary')
            
            # Disconnect from MT5
            connector.disconnect()
            logger.info("Disconnected from MT5")

            # Stop NewsIngestor if it was started
            try:
                if 'news_ingestor' in locals() and news_ingestor:
                    news_ingestor.stop()
                    logger.info('NewsIngestor stopped')
            except Exception:
                logger.exception('Failed to stop NewsIngestor cleanly')

            # Close ML collector if present
            try:
                if 'ml_collector' in locals() and ml_collector:
                    ml_collector.close()
                    logger.info('MLDataCollector closed')
            except Exception:
                logger.exception('Failed to close MLDataCollector')
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}", exc_info=True)
            
        logger.info("=" * 70)
        logger.info("Cthulu Autonomous Trading System - Stopped")
        logger.info("=" * 70)
        
    return 0


if __name__ == "__main__":
    import traceback
    try:
        sys.exit(main())
    except Exception as e:
        # Ensure any unhandled startup exception is captured to disk for post-mortem analysis
        try:
            log_dir = Path(__file__).parent / 'logs'
            log_dir.mkdir(parents=True, exist_ok=True)
            crash_path = log_dir / 'startup_crash.log'
            with open(crash_path, 'w', encoding='utf-8') as fh:
                fh.write('Unhandled exception during startup:\n')
                fh.write('Exception: ' + repr(e) + '\n\n')
                fh.write(traceback.format_exc())
        except Exception:
            pass
        # Also print to stderr so calling process can capture it
        print('Fatal error during Cthulu startup. See logs/startup_crash.log for details.', file=sys.stderr)
        raise




