"""
Cthulu Trading Loop Module

This module contains the core trading loop logic, extracted from __main__.py
for better modularity, testability, and maintainability.

The trading loop handles:
- Market data ingestion
- Dynamic indicator calculation
- Signal generation
- Risk approval and position sizing
- Order execution
- Position monitoring
- Exit strategy evaluation
- Health checks and reconnection

All error handling, logging, and state management is preserved from the original implementation.
"""

import time
import logging
import os
import tempfile
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
import pandas as pd

from cthulu.strategy.base import Strategy, SignalType
from cthulu.execution.engine import ExecutionEngine, OrderRequest, OrderType, OrderStatus
from cthulu.risk.evaluator import RiskEvaluator
from cthulu.position.tracker import PositionTracker
from cthulu.position.lifecycle import PositionLifecycle
from cthulu.position.adoption import TradeAdoptionManager, TradeAdoptionPolicy
from cthulu.persistence.database import Database, TradeRecord, SignalRecord
from cthulu.observability.metrics import MetricsCollector
from cthulu.connector.mt5_connector import MT5Connector
from cthulu.data.layer import DataLayer


@dataclass
class PositionSizeDecision:
    """
    Complete position sizing decision with full audit trail.
    
    Centralizes all position size adjustments into a single, traceable decision.
    """
    base_size: float
    adjustments: List[Tuple[str, float]] = field(default_factory=list)  # (reason, multiplier)
    final_size: float = 0.0
    reasoning: str = ""
    
    def apply_adjustment(self, reason: str, multiplier: float) -> None:
        """Apply an adjustment to the position size."""
        self.adjustments.append((reason, multiplier))
        
    def compute_final(self, min_lot: float = 0.01, volume_step: float = 0.01) -> float:
        """Compute final size after all adjustments."""
        current = self.base_size
        for reason, mult in self.adjustments:
            current *= mult
        
        # Round to volume step
        if volume_step > 0:
            current = round(round(current / volume_step) * volume_step, 2)
        
        # Ensure minimum lot
        self.final_size = max(min_lot, current)
        
        # Build reasoning string
        if self.adjustments:
            parts = [f"{reason}={mult:.2f}" for reason, mult in self.adjustments]
            self.reasoning = f"{self.base_size:.2f} × ({' × '.join(parts)}) → {self.final_size:.2f}"
        else:
            self.reasoning = f"{self.base_size:.2f} → {self.final_size:.2f} (no adjustments)"
        
        return self.final_size


@dataclass
class TradingLoopContext:
    """
    Context object containing all dependencies needed by the trading loop.
    
    This dataclass provides clean dependency injection and makes the trading
    loop testable in isolation.
    """
    # Core trading components
    connector: MT5Connector
    data_layer: DataLayer
    execution_engine: ExecutionEngine
    risk_manager: RiskEvaluator
    position_tracker: PositionTracker
    position_lifecycle: PositionLifecycle
    trade_adoption_manager: TradeAdoptionManager
    exit_coordinator: PositionLifecycle
    database: Database
    metrics: MetricsCollector
    logger: logging.Logger
    
    # Configuration
    symbol: str
    timeframe: Any  # MT5 timeframe constant
    poll_interval: int
    lookback_bars: int
    dry_run: bool
    
    # Trading components
    indicators: List[Any]
    exit_strategies: List[Any]
    trade_adoption_policy: TradeAdoptionPolicy
    config: Dict[str, Any]
    
    # Optional components
    strategy: Optional[Strategy] = None
    advisory_manager: Optional[Any] = None
    exporter: Optional[Any] = None  # Prometheus exporter
    ml_collector: Optional[Any] = None
    position_manager: Optional[Any] = None
    summary_path: Optional[Any] = None
    persist_summary_fn: Optional[Any] = None
    dynamic_sltp_manager: Optional[Any] = None  # Dynamic SL/TP management
    adaptive_drawdown_manager: Optional[Any] = None  # Adaptive drawdown management
    profit_scaler: Optional[Any] = None  # Profit scaling manager for partial profit taking
    adaptive_account_manager: Optional[Any] = None  # Dynamic phase & timeframe management
    adaptive_loss_curve: Optional[Any] = None  # Non-linear loss tolerance
    cognition_engine: Optional[Any] = None  # AI/ML cognition engine for signal enhancement
    
    # Observability collectors (in-process for real-time data)
    indicator_collector: Optional[Any] = None
    system_health_collector: Optional[Any] = None
    comprehensive_collector: Optional[Any] = None
    
    # Hektor (Vector Studio) semantic memory integration
    hektor_adapter: Optional[Any] = None
    hektor_retriever: Optional[Any] = None
    
    # ML Enhancement Manager (automatic ML integration)
    ml_enhancement_manager: Optional[Any] = None
    
    # CLI args
    args: Optional[Any] = None


def ensure_runtime_indicators(df: pd.DataFrame, indicators: List, strategy: Strategy, 
                               config: Dict[str, Any], logger: logging.Logger) -> List:
    """
    Ensure indicators required by the active strategy/config are present.
    
    This function inspects the given strategy and configuration to find
    indicators (or indicator parameters) that the strategies expect to exist
    in the market data (e.g., EMA periods, RSI period, ADX). If missing,
    it creates indicator instances (temporary) and returns them so the
    main loop will calculate their columns during the same iteration.
    
    Args:
        df: Market data DataFrame
        indicators: List of configured indicators
        strategy: Trading strategy instance
        config: Configuration dictionary
        logger: Logger instance
        
    Returns:
        List of additional indicator instances to add
    """
    from cthulu.indicators.rsi import RSI
    from cthulu.indicators.adx import ADX
    from cthulu.indicators.atr import ATR
    # Optional runtime indicators - use specific ImportError
    try:
        from cthulu.indicators.macd import MACD
    except ImportError:
        MACD = None
    try:
        from cthulu.indicators.bollinger import BollingerBands
    except ImportError:
        BollingerBands = None
    try:
        from cthulu.indicators.stochastic import Stochastic
    except ImportError:
        Stochastic = None
    try:
        from cthulu.indicators.supertrend import Supertrend
    except ImportError:
        Supertrend = None
    try:
        from cthulu.indicators.vwap import VWAP
    except ImportError:
        VWAP = None
    
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
                except (ValueError, TypeError):
                    pass  # Non-integer period values are skipped
    
    # Strategy instance inspection (handle StrategySelectorAdapter wrapping)
    try:
        from cthulu.strategy.strategy_selector import StrategySelector
        from cthulu.strategy.selector_adapter import StrategySelectorAdapter
        
        strategy_to_inspect = strategy
        if isinstance(strategy_to_inspect, StrategySelectorAdapter):
            strategy_to_inspect = getattr(strategy_to_inspect, 'selector', strategy_to_inspect)
        
        if isinstance(strategy_to_inspect, StrategySelector):
            for s in strategy_to_inspect.strategies.values():
                collect_ema_periods(s)
        else:
            collect_ema_periods(strategy)
    except ImportError:
        collect_ema_periods(strategy)
    
    # Also check config-level strategies
    try:
        strat_cfg = config.get('strategy', {}) if isinstance(config, dict) else {}
        if strat_cfg.get('type') == 'dynamic':
            for s in strat_cfg.get('strategies', []):
                params = s.get('params', {}) if isinstance(s.get('params', {}), dict) else {}
                for attr in ('fast_period', 'slow_period', 'fast_ema', 'slow_ema'):
                    if attr in params and params[attr]:
                        try:
                            required_emas.add(int(params[attr]))
                        except (ValueError, TypeError):
                            pass  # Invalid period value
        else:
            params = strat_cfg.get('params', {}) if isinstance(strat_cfg.get('params', {}), dict) else {}
            for attr in ('fast_period', 'slow_period', 'fast_ema', 'slow_ema'):
                if attr in params and params[attr]:
                    try:
                        required_emas.add(int(params[attr]))
                    except (ValueError, TypeError):
                        pass  # Invalid period value
    except (KeyError, AttributeError) as e:
        logger.debug(f"Config strategy parsing skipped: {e}")
    
    # Check for RSI requirement
    needs_rsi = False
    rsi_period = 14  # default
    try:
        # If strategy is a selector (or adapter), check sub-strategies for RSI needs
        from cthulu.strategy.strategy_selector import StrategySelector
        from cthulu.strategy.selector_adapter import StrategySelectorAdapter
        
        strategy_to_check = strategy
        if isinstance(strategy_to_check, StrategySelectorAdapter):
            strategy_to_check = getattr(strategy_to_check, 'selector', strategy_to_check)
        
        if isinstance(strategy_to_check, StrategySelector):
            for s in strategy_to_check.strategies.values():
                if hasattr(s, 'rsi_period'):
                    needs_rsi = True
                    rsi_period = int(getattr(s, 'rsi_period'))
                    break
                if hasattr(s, 'rsi_oversold') or hasattr(s, 'rsi_overbought'):
                    needs_rsi = True
                    break
        else:
            if hasattr(strategy, 'rsi_period'):
                needs_rsi = True
                rsi_period = int(strategy.rsi_period)
            elif hasattr(strategy, 'rsi_oversold') or hasattr(strategy, 'rsi_overbought'):
                needs_rsi = True
    except Exception as e:
        logger.debug("Failed to determine RSI requirement from strategy: %s", e, exc_info=True)
    
    # Check if RSI already exists
    if needs_rsi:
        # Ensure we add the strategy-specific RSI period (and also add default rsi if desired)
        rsi_col = f'rsi_{rsi_period}' if rsi_period != 14 else 'rsi'
        has_rsi = rsi_col in df.columns or any(getattr(i, 'name', '').upper() == 'RSI' for i in indicators)
        if not has_rsi:
            extra_indicators.append(RSI(period=rsi_period))
            logger.debug(f"Added runtime RSI indicator (period={rsi_period})")
    else:
        # Check config-level dynamic strategies for RSI needs as a fallback
        try:
            strat_cfg = config.get('strategy', {}) if isinstance(config, dict) else {}
            if strat_cfg.get('type') == 'dynamic':
                for s in strat_cfg.get('strategies', []):
                    params = s.get('params', {}) if isinstance(s.get('params', {}), dict) else {}
                    if 'rsi_period' in params and params['rsi_period']:
                        rp = int(params['rsi_period'])
                        rsi_col = f'rsi_{rp}' if rp != 14 else 'rsi'
                        if rsi_col not in df.columns and not any(getattr(i, 'name', '').upper() == 'RSI' for i in indicators):
                            extra_indicators.append(RSI(period=rp))
                            logger.debug(f"Added runtime RSI indicator from config (period={rp})")
                            break
        except Exception as e:
            logger.debug("Failed to inspect strategy config for RSI requirement: %s", e, exc_info=True)
    
    # Check for ATR requirement
    needs_atr = False
    atr_period = 14
    try:
        if hasattr(strategy, 'atr_period'):
            needs_atr = True
            atr_period = int(strategy.atr_period)
        elif hasattr(strategy, 'use_atr') and strategy.use_atr:
            needs_atr = True
        # Strategy name-based heuristic (scalping strategies often need ATR)
        elif getattr(strategy, 'name', '').lower().find('scalp') != -1 or strategy.__class__.__name__.lower().find('scalp') != -1:
            needs_atr = True
    except Exception as e:
        logger.debug("Failed to determine ATR requirement from strategy: %s", e, exc_info=True)
    
    if needs_atr:
        has_atr = 'atr' in df.columns or any(getattr(i, 'name', '').upper() == 'ATR' for i in indicators)
        if not has_atr:
            extra_indicators.append(ATR(period=atr_period))
            logger.debug(f"Added runtime ATR indicator (period={atr_period})")
    
    # Check for ADX requirement
    needs_adx = False
    try:
        from cthulu.strategy.strategy_selector import StrategySelector
        from cthulu.strategy.selector_adapter import StrategySelectorAdapter
        
        strategy_to_check = strategy
        if isinstance(strategy_to_check, StrategySelectorAdapter):
            strategy_to_check = getattr(strategy_to_check, 'selector', strategy_to_check)
        
        if isinstance(strategy_to_check, StrategySelector):
            needs_adx = True  # Dynamic selector uses ADX for regime detection
    except Exception as e:
        logger.debug("Failed to determine ADX requirement: %s", e, exc_info=True)
    
    if needs_adx:
        has_adx = 'adx' in df.columns or any(getattr(i, 'name', '').upper() == 'ADX' for i in indicators)
        if not has_adx:
            extra_indicators.append(ADX(period=14))
            logger.debug("Added runtime ADX indicator for regime detection")

    # Check config-specified indicators and add runtime instances when requested
    try:
        conf_inds = config.get('indicators', []) if isinstance(config, dict) else []
        for ind in conf_inds:
            try:
                t = (ind.get('type') or '').lower()
                params = ind.get('params', {}) or {}
                if t in ('macd',) and MACD is not None:
                    extra_indicators.append(MACD(**params))
                elif t in ('bollinger', 'bollingerbands') and BollingerBands is not None:
                    extra_indicators.append(BollingerBands(**params))
                elif t in ('stochastic',) and Stochastic is not None:
                    extra_indicators.append(Stochastic(**params))
                elif t in ('supertrend',) and Supertrend is not None:
                    # Accept common alias 'atr_multiplier' -> 'multiplier'
                    try:
                        if 'atr_multiplier' in params and 'multiplier' not in params:
                            params = dict(params)
                            params['multiplier'] = params.pop('atr_multiplier')
                    except Exception:
                        pass
                    extra_indicators.append(Supertrend(**params))
                elif t in ('vwap',) and VWAP is not None:
                    extra_indicators.append(VWAP(**params))
            except Exception:
                continue
    except Exception:
        pass

    # Special-case: for scalping strategies, ensure an ATR column is present immediately
    try:
        strat_name = getattr(strategy, 'name', '') or strategy.__class__.__name__
        if (('scalp' in str(strat_name).lower()) or ('scalp' in strategy.__class__.__name__.lower())) and 'atr' not in df.columns:
            try:
                # Compute ATR fallback directly and attach in-place
                from cthulu.indicators.atr import ATR
                atr_ind = ATR(period=getattr(strategy, 'atr_period', 14))
                atr_series = atr_ind.calculate(df)
                if atr_series is not None:
                    if isinstance(atr_series, pd.Series):
                        df['atr'] = atr_series
                    else:
                        # If DataFrame, pick primary 'atr' column if present
                        if 'atr' in atr_series.columns:
                            df['atr'] = atr_series['atr']
                        else:
                            df['atr'] = atr_series.iloc[:, 0]
                # Remove any ATR instance from extra_indicators to avoid duplicate joins
                try:
                    extra_indicators = [i for i in extra_indicators if i.__class__.__name__.upper() != 'ATR']
                except Exception:
                    pass
            except Exception:
                logger.exception('Failed to compute inline ATR for scalping strategy')
    except Exception:
        pass

    # Compute EMA columns inline for any required EMA periods detected earlier.
    try:
        if required_emas:
            for p in sorted(required_emas):
                col = f'ema_{p}'
                if col not in df.columns and 'close' in df.columns:
                    try:
                        df[col] = df['close'].ewm(span=int(p), adjust=False).mean()
                        logger.debug(f"Computed runtime EMA column: {col}")
                    except Exception:
                        logger.exception(f"Failed to compute runtime EMA for period {p}")
    except Exception:
        logger.exception('Failed during runtime EMA computation')

    return extra_indicators


class TradingLoop:
    """
    Main trading loop implementation.
    
    This class encapsulates the core trading loop logic, making it testable
    and maintainable while preserving all error handling and state management.
    """
    
    def __init__(self, context: TradingLoopContext):
        """
        Initialize the trading loop with its context.
        
        Args:
            context: TradingLoopContext containing all dependencies
        """
        self.ctx = context
        self.loop_count = 0
        self._shutdown_requested = False
        
        # CRITICAL FIX: Trade cooldown to prevent rapid-fire entries
        self._last_trade_time: Optional[datetime] = None
        self._min_trade_interval_seconds = self.ctx.config.get('min_trade_interval', 60)  # 1 minute default
        self._last_signal_direction: Optional[str] = None
        self._consecutive_same_direction = 0
    
    def request_shutdown(self):
        """Request graceful shutdown of the trading loop."""
        self._shutdown_requested = True
    
    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        return self._shutdown_requested
    
    def _check_trade_cooldown(self, signal) -> bool:
        """
        Check if we should wait before placing another trade.
        
        Returns True if OK to trade, False if in cooldown.
        """
        if self._last_trade_time is None:
            return True
        
        elapsed = (datetime.now() - self._last_trade_time).total_seconds()
        if elapsed < self._min_trade_interval_seconds:
            self.ctx.logger.info(
                f"Trade cooldown active: {elapsed:.0f}s / {self._min_trade_interval_seconds}s"
            )
            return False
        
        return True
    
    def _record_trade_executed(self, signal):
        """Record that a trade was executed for cooldown tracking."""
        self._last_trade_time = datetime.now()
        
        # Track direction for consecutive same-direction prevention
        direction = 'LONG' if signal.side == SignalType.LONG else 'SHORT'
        if direction == self._last_signal_direction:
            self._consecutive_same_direction += 1
        else:
            self._consecutive_same_direction = 1
        self._last_signal_direction = direction
    
    def _calculate_final_position_size(
        self, 
        signal,
        base_size: float,
        entry_confluence_result=None,
        balance: float = 0.0,
        market_data: Optional[pd.DataFrame] = None
    ) -> PositionSizeDecision:
        """
        Centralized position sizing with full audit trail.
        
        All position size adjustments happen here for transparency and debugging.
        Now includes ML Enhancement Manager for intelligent position sizing.
        
        Args:
            signal: Trading signal
            base_size: Base position size from risk manager
            entry_confluence_result: Optional entry confluence analysis result
            balance: Current account balance
            market_data: Optional market data for ML features
            
        Returns:
            PositionSizeDecision with full reasoning trail
        """
        decision = PositionSizeDecision(base_size=base_size)
        
        # ==========================================================
        # ML ENHANCEMENT: Get ML-driven position size recommendation
        # This integrates RL Position Sizer + Cognition Engine
        # ==========================================================
        if self.ctx.ml_enhancement_manager and market_data is not None:
            try:
                # Build account state for ML
                account_info = self.ctx.connector.get_account_info()
                equity = float(account_info.get('equity', balance)) if account_info else balance
                
                # Calculate drawdown
                peak_balance = balance  # Simplified - could track actual peak
                drawdown_pct = max(0, (peak_balance - equity) / peak_balance * 100) if peak_balance > 0 else 0
                
                # Get recent win rate from metrics
                recent_win_rate = 0.5
                try:
                    if self.ctx.metrics:
                        stats = self.ctx.metrics.get_statistics()
                        recent_win_rate = stats.get('win_rate', 0.5)
                except Exception:
                    pass
                
                # Get current exposure
                current_exposure = 0.0
                try:
                    positions = self.ctx.position_manager.get_positions(symbol=self.ctx.symbol)
                    for pos in positions:
                        current_exposure += getattr(pos, 'volume', 0) * 0.01  # Rough exposure calc
                except Exception:
                    pass
                
                account_state = {
                    'balance': balance,
                    'equity': equity,
                    'drawdown_pct': drawdown_pct,
                    'recent_win_rate': recent_win_rate,
                    'exposure_pct': current_exposure,
                    'max_position_pct': self.ctx.config.get('risk', {}).get('max_position_size_percent', 2.0) / 100,
                    'remaining_daily_risk': 1.0  # Simplified
                }
                
                ml_mult, ml_details = self.ctx.ml_enhancement_manager.get_position_size_recommendation(
                    signal=signal,
                    market_data=market_data,
                    account_state=account_state,
                    base_size=base_size
                )
                
                if ml_mult != 1.0:
                    # Build reason string from ML details
                    ml_reasons = ml_details.get('reasons', [])
                    reason_str = ', '.join(ml_reasons) if ml_reasons else 'ML'
                    decision.apply_adjustment(f"ml({reason_str})", ml_mult)
                    
                    self.ctx.logger.info(f"ML sizing: {ml_mult:.2f}x - {ml_reasons}")
                    
            except Exception as e:
                self.ctx.logger.debug(f"ML enhancement sizing failed: {e}")
        
        # 1. Entry Quality Adjustment (from confluence filter)
        if entry_confluence_result and hasattr(entry_confluence_result, 'position_mult'):
            mult = entry_confluence_result.position_mult
            if mult != 1.0:
                decision.apply_adjustment(
                    f"entry_quality({entry_confluence_result.quality.value})", 
                    mult
                )
        
        # 2. Adaptive Loss Curve Adjustment
        if self.ctx.adaptive_loss_curve and balance > 0:
            try:
                max_loss = self.ctx.adaptive_loss_curve.get_max_loss(balance, per_trade=True)
                entry_price = getattr(signal, 'price', 0) or getattr(signal, 'entry_price', 0)
                stop_loss = getattr(signal, 'stop_loss', 0)
                
                if entry_price > 0 and stop_loss > 0:
                    pip_distance = abs(entry_price - stop_loss)
                    if pip_distance > 0:
                        # Calculate what size respects max loss
                        loss_adjusted_size = max_loss / (pip_distance * 10)  # Rough pip value
                        current_projected = base_size
                        for _, m in decision.adjustments:
                            current_projected *= m
                        
                        if loss_adjusted_size < current_projected:
                            # Need to reduce - calculate multiplier
                            loss_mult = loss_adjusted_size / current_projected if current_projected > 0 else 1.0
                            if loss_mult < 1.0:
                                decision.apply_adjustment("loss_curve", loss_mult)
            except Exception as e:
                self.ctx.logger.debug(f"Loss curve adjustment failed: {e}")
        
        # 3. Cognition Size Multiplier (from AI/ML signal enhancement)
        # Note: This is now also handled by ML Enhancement Manager, but kept for backward compatibility
        try:
            cognition_mult = getattr(signal, '_cognition_size_mult', 1.0)
            if cognition_mult != 1.0 and not self.ctx.ml_enhancement_manager:
                # Only apply if ML manager not already handling this
                decision.apply_adjustment("cognition", cognition_mult)
        except Exception:
            pass
        
        # 4. Performance-based adjustment (optional - based on recent win rate)
        # Disabled by default - enable via config: risk.performance_based_sizing: true
        performance_sizing_enabled = self.ctx.config.get('risk', {}).get('performance_based_sizing', False)
        if performance_sizing_enabled:
            try:
                if self.ctx.metrics:
                    stats = self.ctx.metrics.get_statistics()
                    win_rate = stats.get('win_rate', 0.5)
                    if win_rate < 0.35:
                        # Struggling - reduce size
                        decision.apply_adjustment("low_win_rate", 0.75)
                    elif win_rate > 0.65:
                        # Performing well - can increase slightly
                        decision.apply_adjustment("high_win_rate", 1.10)
            except Exception:
                pass
        
        # Get volume constraints from broker
        min_lot = 0.01
        volume_step = 0.01
        try:
            symbol_info = self.ctx.connector.get_symbol_info(self.ctx.symbol)
            if symbol_info:
                min_lot = symbol_info.get('volume_min', 0.01)
                volume_step = symbol_info.get('volume_step', 0.01)
        except Exception:
            pass
        
        # Compute final size
        decision.compute_final(min_lot=min_lot, volume_step=volume_step)
        
        return decision

    def run(self) -> int:
        """
        Execute the main trading loop.
        
        Returns:
            Exit code (0 for success, 1 for error)
        """
        self.ctx.logger.info("Starting autonomous trading loop...")
        self.ctx.logger.info("Press Ctrl+C to shutdown gracefully")
        
        # Log collector status
        self.ctx.logger.info(f"Collectors: indicator={self.ctx.indicator_collector is not None}, "
                            f"comprehensive={self.ctx.comprehensive_collector is not None}, "
                            f"system_health={self.ctx.system_health_collector is not None}")
        
        # ==========================================================
        # ML ENHANCEMENT: Log ML status at startup
        # ==========================================================
        if self.ctx.ml_enhancement_manager:
            ml_state = self.ctx.ml_enhancement_manager.get_state()
            self.ctx.logger.info(f"ML Enhancement ACTIVE: {ml_state['components']}")
            
            # Wire cognition engine from ML manager if not already set
            if not self.ctx.cognition_engine:
                cognition = self.ctx.ml_enhancement_manager.get_cognition_engine()
                if cognition:
                    self.ctx.cognition_engine = cognition
                    self.ctx.logger.info("Cognition engine wired from ML Enhancement Manager")
        else:
            self.ctx.logger.info("ML Enhancement not active - using rule-based logic only")
        
        try:
            while not self._shutdown_requested:
                self.loop_count += 1
                loop_start = datetime.now()
                self.ctx.logger.debug(f"Loop #{self.loop_count} started at {loop_start}")
                
                # Execute one iteration of the trading loop
                try:
                    self._execute_loop_iteration()
                except Exception as e:
                    self.ctx.logger.error(f"Error in loop iteration: {e}", exc_info=True)
                
                # Wait for next cycle
                loop_duration = (datetime.now() - loop_start).total_seconds()
                self.ctx.logger.debug(f"Loop completed in {loop_duration:.2f}s")
                
                sleep_time = max(0, self.ctx.poll_interval - loop_duration)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                
                # Debug/testing: exit after max_loops if requested
                try:
                    if self.ctx.args and getattr(self.ctx.args, 'max_loops', 0) and \
                       self.loop_count >= int(self.ctx.args.max_loops):
                        self.ctx.logger.info(f"Reached max_loops={self.ctx.args.max_loops}; exiting main loop for test")
                        break
                except Exception:
                    pass
        
        except KeyboardInterrupt:
            self.ctx.logger.info("Keyboard interrupt received")
            # Save ML models on shutdown
            if self.ctx.ml_enhancement_manager:
                try:
                    self.ctx.ml_enhancement_manager.shutdown()
                except Exception as e:
                    self.ctx.logger.debug(f"ML shutdown error: {e}")
            raise  # Re-raise to allow main shutdown handler to catch it
        except Exception as e:
            self.ctx.logger.error(f"Fatal error in main loop: {e}", exc_info=True)
            return 1
        
        # Graceful shutdown - save ML models
        if self.ctx.ml_enhancement_manager:
            try:
                self.ctx.ml_enhancement_manager.shutdown()
            except Exception as e:
                self.ctx.logger.debug(f"ML shutdown error: {e}")
        
        return 0
    
    def _execute_loop_iteration(self):
        """Execute one iteration of the trading loop."""
        # Ensure position_manager has current symbol context for fallback
        if self.ctx.position_manager and hasattr(self.ctx.position_manager, 'context_symbol'):
            if not self.ctx.position_manager.context_symbol:
                self.ctx.position_manager.context_symbol = self.ctx.symbol
        
        # 1. Market data ingestion
        self.ctx.logger.info(f"Loop #{self.loop_count}: Fetching market data...")
        df = self._ingest_market_data()
        if df is None:
            self.ctx.logger.warning("No market data received, skipping iteration")
            return
        
        # 2. Calculate indicators
        self.ctx.logger.info(f"Loop #{self.loop_count}: Calculating indicators...")
        df = self._calculate_indicators(df)
        if df is None:
            self.ctx.logger.warning("Indicator calculation failed")
            return
        
        # 3. Check pending entries (queued for better price)
        self._check_pending_entries(df)
        
        # 4. Generate strategy signals
        self.ctx.logger.info(f"Loop #{self.loop_count}: Generating signals...")
        signal = self._generate_signal(df)
        
        # 5. Process entry signals
        if signal:
            self._process_entry_signal(signal)
        
        # 6. Scan and adopt external trades
        self._adopt_external_trades()
        
        # 7. Monitor positions and check exits
        self._monitor_positions(df)
        
        # 8. Health monitoring
        self._check_connection_health()
        
        # 9. Performance monitoring
        self._report_performance_metrics()
    
    def _check_pending_entries(self, df: pd.DataFrame):
        """
        Check if any pending entries should now execute.
        
        Pending entries are signals that were queued to wait for better price.
        """
        try:
            from cthulu.cognition.entry_confluence import get_entry_confluence_filter
            
            confluence_filter = get_entry_confluence_filter()
            current_price = float(df['close'].iloc[-1])
            current_bar = df.iloc[-1]
            
            ready_entries = confluence_filter.check_pending_entries(
                symbol=self.ctx.symbol,
                current_price=current_price,
                current_bar=current_bar
            )
            
            for entry in ready_entries:
                self.ctx.logger.info(f"Pending entry ready: {entry['signal_id']} - {entry['reason']}")
                
                # Create a synthetic signal for the ready entry
                from cthulu.strategy.base import Signal, SignalType
                
                direction = SignalType.LONG if entry['direction'] == 'long' else SignalType.SHORT
                size_mult = entry.get('size_mult', 1.0)
                
                # Get ATR for SL/TP calculation
                atr = float(df['atr'].iloc[-1]) if 'atr' in df.columns else current_price * 0.01
                
                if direction == SignalType.LONG:
                    stop_loss = current_price - (atr * 2.0)
                    take_profit = current_price + (atr * 4.0)
                else:
                    stop_loss = current_price + (atr * 2.0)
                    take_profit = current_price - (atr * 4.0)
                
                # Use clean base ID (strip any existing _pending suffixes to prevent cascade)
                base_id = entry['signal_id'].replace('_pending', '').rstrip('_')
                clean_id = f"{base_id}_exec_{int(datetime.now().timestamp())}"
                
                synthetic_signal = Signal(
                    id=clean_id,
                    timestamp=datetime.now(),
                    symbol=self.ctx.symbol,
                    timeframe=str(self.ctx.timeframe),
                    side=direction,
                    action='BUY' if direction == SignalType.LONG else 'SELL',
                    price=current_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    confidence=0.75 if not entry.get('timeout') else 0.5,
                    reason=f"Pending entry: {entry['reason']}",
                    metadata={
                        'pending_entry': True,
                        'waited_bars': entry['waited_bars'],
                        'size_mult': size_mult,
                        'skip_confluence_filter': True  # Skip re-filtering for pending entries
                    }
                )
                
                # Store size multiplier for later use
                synthetic_signal._pending_size_mult = size_mult
                
                self._process_entry_signal(synthetic_signal)
                
        except ImportError:
            pass  # Entry confluence filter not available
        except Exception as e:
            self.ctx.logger.debug(f"Pending entry check failed: {e}")
    
    def _ingest_market_data(self) -> Optional[pd.DataFrame]:
        """
        Ingest market data from MT5.
        
        Returns:
            DataFrame with market data, or None on error
        """
        try:
            rates = self.ctx.connector.get_rates(
                symbol=self.ctx.symbol,
                timeframe=self.ctx.timeframe,
                count=self.ctx.lookback_bars
            )
            
            if rates is None or len(rates) == 0:
                self.ctx.logger.warning("No market data received, skipping cycle")
                time.sleep(self.ctx.poll_interval)
                return None
            
            df = self.ctx.data_layer.normalize_rates(rates, symbol=self.ctx.symbol)
            self.ctx.logger.debug(f"Retrieved {len(df)} bars for {self.ctx.symbol}")
            return df
        
        except Exception as e:
            self.ctx.logger.error(f"Market data error: {e}", exc_info=True)
            time.sleep(self.ctx.poll_interval)
            return None
    
    def _calculate_indicators(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """
        Calculate all required indicators.
        
        Args:
            df: Market data DataFrame
            
        Returns:
            DataFrame with indicators, or None on error
        """
        try:
            # Calculate SMA indicators for strategy (use strategy params when available)
            try:
                sma_periods_calculated = set()
                
                # Check direct strategy attributes
                short_w = getattr(self.ctx.strategy, 'short_window', None)
                long_w = getattr(self.ctx.strategy, 'long_window', None)
                if short_w and long_w:
                    df[f'sma_{short_w}'] = df['close'].rolling(window=int(short_w)).mean()
                    df[f'sma_{long_w}'] = df['close'].rolling(window=int(long_w)).mean()
                    sma_periods_calculated.add(int(short_w))
                    sma_periods_calculated.add(int(long_w))
                
                # For StrategySelector, calculate SMAs for all contained strategies
                if hasattr(self.ctx.strategy, 'strategies'):
                    for strategy_name, strategy in self.ctx.strategy.strategies.items():
                        sw = getattr(strategy, 'short_window', None)
                        lw = getattr(strategy, 'long_window', None)
                        if sw and int(sw) not in sma_periods_calculated:
                            df[f'sma_{sw}'] = df['close'].rolling(window=int(sw)).mean()
                            sma_periods_calculated.add(int(sw))
                        if lw and int(lw) not in sma_periods_calculated:
                            df[f'sma_{lw}'] = df['close'].rolling(window=int(lw)).mean()
                            sma_periods_calculated.add(int(lw))
                
                # Always ensure common defaults exist
                if 20 not in sma_periods_calculated:
                    df['sma_20'] = df['close'].rolling(window=20).mean()
                if 50 not in sma_periods_calculated:
                    df['sma_50'] = df['close'].rolling(window=50).mean()
            except Exception:
                # If anything goes wrong, compute defaults and continue
                df['sma_20'] = df['close'].rolling(window=20).mean()
                df['sma_50'] = df['close'].rolling(window=50).mean()
            
            # Compute required EMA columns for strategies
            df = self._compute_ema_columns(df)
            
            # Add price levels for momentum breakout strategy
            try:
                needs_price_levels = False
                lookback_period = 20  # default
                
                # Check if current strategy is momentum breakout
                if hasattr(self.ctx.strategy, 'lookback_period') or \
                   (hasattr(self.ctx.strategy, '__class__') and 'momentum_breakout' in str(self.ctx.strategy.__class__).lower()):
                    needs_price_levels = True
                    lookback_period = getattr(self.ctx.strategy, 'lookback_period', 20)
                
                # Check if strategy selector contains momentum breakout
                elif hasattr(self.ctx.strategy, 'strategies'):
                    for strategy_name, strategy in self.ctx.strategy.strategies.items():
                        if 'momentum_breakout' in str(strategy.__class__).lower():
                            needs_price_levels = True
                            lookback_period = getattr(strategy, 'lookback_period', 20)
                            break
                
                if needs_price_levels:
                    # Add price levels
                    df[f'high_{lookback_period}'] = df['high'].rolling(window=lookback_period).max()
                    df[f'low_{lookback_period}'] = df['low'].rolling(window=lookback_period).min()
                    
                    # Add volume analysis
                    df[f'volume_avg_{lookback_period}'] = df['volume'].rolling(window=lookback_period).mean()
                    
                    self.ctx.logger.debug(f"Added price levels and volume analysis for lookback period {lookback_period}")
            except Exception as e:
                self.ctx.logger.debug(f"Could not add price levels: {e}")
            
            # Ensure runtime indicators (RSI/ATR/MACD/etc.) are added if the strategy needs them
            try:
                extra_indicators = ensure_runtime_indicators(
                    df, self.ctx.indicators, self.ctx.strategy, self.ctx.config, self.ctx.logger
                )
                if extra_indicators:
                    self.ctx.indicators.extend(extra_indicators)
                    try:
                        names = [getattr(i, 'name', i.__class__.__name__) for i in extra_indicators]
                    except Exception:
                        names = [i.__class__.__name__ for i in extra_indicators]
                    self.ctx.logger.info(f"Added {len(extra_indicators)} runtime indicators: {names}")
            except Exception:
                self.ctx.logger.exception('Failed to ensure runtime indicators')
            
            # Calculate configured indicators (and any runtime-added ones)
            try:
                for indicator in self.ctx.indicators:
                    try:
                        indicator_data = indicator.calculate(df)
                        if indicator_data is None:
                            continue

                        # Normalize Series -> DataFrame
                        if isinstance(indicator_data, pd.Series):
                            series_name = indicator_data.name or getattr(indicator, 'name', indicator.__class__.__name__).lower()
                            indicator_data = indicator_data.to_frame(name=series_name)

                        # Determine a base name for this indicator (use provided 'name' if available)
                        base = getattr(indicator, 'name', None) or indicator.__class__.__name__
                        base = str(base).lower()

                        # Build rename map to avoid column overlaps in df
                        rename_map = {}
                        for col in list(indicator_data.columns):
                            # If column already looks namespaced to this indicator (e.g., 'rsi_7' for RSI),
                            # keep that suffix but prefix with 'runtime_'. If the column equals the base name
                            # (e.g., 'adx'), use 'runtime_adx'. Otherwise namespace under indicator base.
                            if col == base or col.startswith(f"{base}_"):
                                new_col = f"runtime_{col}"
                            else:
                                new_col = f"runtime_{base}_{col}"

                            # Ensure deterministic uniqueness if df already has this column
                            final_col = new_col
                            i = 1
                            while final_col in df.columns:
                                final_col = f"{new_col}_{i}"
                                i += 1

                            if final_col != col:
                                rename_map[col] = final_col

                        if rename_map:
                            indicator_data = indicator_data.rename(columns=rename_map)
                            self.ctx.logger.debug(f"Renamed indicator columns to avoid overlap: {rename_map}")

                        # Join indicator data safely; if any columns overlap pandas will
                        # append the provided suffix to the joined columns to avoid
                        # raising ValueError about overlapping columns.
                        try:
                            df = df.join(indicator_data, how='left', rsuffix=f"_ind_{base}")
                        except Exception:
                            # As a final fallback, explicitly rename overlapping columns
                            # on the indicator side and then join.
                            overlaps = set(df.columns).intersection(indicator_data.columns)
                            if overlaps:
                                rename_map2 = {c: f"{c}_ind_{base}" for c in overlaps}
                                indicator_data = indicator_data.rename(columns=rename_map2)
                            df = df.join(indicator_data, how='left')

                    except Exception:
                        self.ctx.logger.exception(
                            f"Failed to calculate indicator {getattr(indicator, 'name', indicator.__class__.__name__)}"
                        )
            except Exception:
                self.ctx.logger.exception('Failed during indicator calculations')
            
            # Create friendly aliases for commonly-required indicators (so strategies can rely on expected column names)
            try:
                # RSI alias
                rsi_period = getattr(self.ctx.strategy, 'rsi_period', None)
                try:
                    rsi_period_int = int(rsi_period) if rsi_period is not None else None
                except Exception:
                    rsi_period_int = None
                rsi_col = f"rsi_{rsi_period_int}" if rsi_period_int and rsi_period_int != 14 else 'rsi'
                if rsi_col not in df.columns:
                    # find runtime-produced RSI columns (be permissive in matching)
                    rsi_candidates = [c for c in df.columns if 'rsi' in c.lower() and c.startswith('runtime_')]
                    if rsi_candidates:
                        # Prefer candidate that contains the period string, then exact 'rsi', else fallback to first
                        chosen = None
                        if rsi_period_int:
                            for c in rsi_candidates:
                                if f"rsi_{rsi_period_int}" in c.lower():
                                    chosen = c
                                    break
                        if not chosen:
                            for c in rsi_candidates:
                                if c.lower().endswith('rsi') or c.lower().endswith('rsi_'):
                                    chosen = c
                                    break
                        chosen = chosen or rsi_candidates[0]
                        df[rsi_col] = df[chosen]
                        self.ctx.logger.debug(f"Created RSI alias column '{rsi_col}' from '{chosen}'")
                # ATR alias
                if 'atr' not in df.columns:
                    atr_candidates = [c for c in df.columns if c.startswith('runtime_atr')]
                    if atr_candidates:
                        df['atr'] = df[atr_candidates[0]]
                        self.ctx.logger.debug(f"Created ATR alias column 'atr' from '{atr_candidates[0]}'")
                # ADX alias
                if 'adx' not in df.columns:
                    adx_candidates = [c for c in df.columns if 'adx' in c.lower() and c.startswith('runtime_')]
                    if adx_candidates:
                        # pick primary adx value if present
                        chosen = None
                        for c in adx_candidates:
                            if c.lower().endswith('adx') or c == 'runtime_adx':
                                chosen = c
                                break
                        chosen = chosen or adx_candidates[0]
                        df['adx'] = df[chosen]
                        self.ctx.logger.debug(f"Created ADX alias column 'adx' from '{chosen}'")
            except Exception:
                self.ctx.logger.exception('Failed while creating indicator alias columns')

            # Fallback: if required indicators are still missing, compute them directly
            try:
                # RSI fallback
                rsi_col = None
                try:
                    rsi_period = getattr(self.ctx.strategy, 'rsi_period', None)
                    rsi_period_int = int(rsi_period) if rsi_period is not None else None
                    rsi_col = f"rsi_{rsi_period_int}" if rsi_period_int and rsi_period_int != 14 else 'rsi'
                except Exception:
                    rsi_col = 'rsi'

                if rsi_col and rsi_col not in df.columns:
                    try:
                        from cthulu.indicators.rsi import RSI
                        rsi_ind = RSI(period=rsi_period_int or 14)
                        rsi_data = rsi_ind.calculate(df)
                        if isinstance(rsi_data, pd.Series):
                            rsi_name = rsi_data.name or (f"rsi_{rsi_period_int}" if rsi_period_int else 'rsi')
                            rsi_data = rsi_data.to_frame(name=rsi_name)

                        # Rename to runtime-safe column names for joining
                        rename_map = {}
                        for col in list(rsi_data.columns):
                            if col == 'rsi' or col.startswith('rsi_'):
                                new_col = f"runtime_{col}"
                            else:
                                new_col = f"runtime_rsi_{col}"
                            final_col = new_col
                            i = 1
                            while final_col in df.columns:
                                final_col = f"{new_col}_{i}"
                                i += 1
                            if final_col != col:
                                rename_map[col] = final_col

                        if rename_map:
                            rsi_data = rsi_data.rename(columns=rename_map)
                            self.ctx.logger.debug(f"Renamed RSI fallback columns: {rename_map}")

                        # Ensure overlapping columns don't raise merge errors
                        try:
                            df = df.join(rsi_data, how='left', rsuffix="_ind_rsi")
                        except Exception:
                            overlaps = set(df.columns).intersection(rsi_data.columns)
                            if overlaps:
                                rename_map2 = {c: f"{c}_ind_rsi" for c in overlaps}
                                rsi_data = rsi_data.rename(columns=rename_map2)
                            df = df.join(rsi_data, how='left')
                        # create alias if needed
                        if rsi_col not in df.columns:
                            candidates = [c for c in df.columns if 'rsi' in c.lower() and c.startswith('runtime_')]
                            if candidates:
                                chosen = None
                                if rsi_period_int:
                                    for c in candidates:
                                        if f"rsi_{rsi_period_int}" in c.lower():
                                            chosen = c
                                            break
                                chosen = chosen or candidates[0]
                                df[rsi_col] = df[chosen]
                                self.ctx.logger.debug(f"Created RSI alias '{rsi_col}' from '{chosen}' in fallback")
                    except Exception:
                        self.ctx.logger.exception('RSI fallback calculation failed')

                # ATR fallback
                if 'atr' not in df.columns:
                    try:
                        from cthulu.indicators.atr import ATR
                        atr_ind = ATR(period=getattr(self.ctx.strategy, 'atr_period', 14))
                        atr_data = atr_ind.calculate(df)
                        if isinstance(atr_data, pd.Series):
                            atr_name = atr_data.name or 'atr'
                            atr_data = atr_data.to_frame(name=atr_name)

                        # Rename similarly
                        rename_map = {}
                        for col in list(atr_data.columns):
                            if col == 'atr' or col.startswith('atr_'):
                                new_col = f"runtime_{col}"
                            else:
                                new_col = f"runtime_atr_{col}"
                            final_col = new_col
                            i = 1
                            while final_col in df.columns:
                                final_col = f"{new_col}_{i}"
                                i += 1
                            if final_col != col:
                                rename_map[col] = final_col
                        if rename_map:
                            atr_data = atr_data.rename(columns=rename_map)
                        try:
                            df = df.join(atr_data, how='left', rsuffix="_ind_atr")
                        except Exception:
                            overlaps = set(df.columns).intersection(atr_data.columns)
                            if overlaps:
                                rename_map2 = {c: f"{c}_ind_atr" for c in overlaps}
                                atr_data = atr_data.rename(columns=rename_map2)
                            df = df.join(atr_data, how='left')
                        if 'atr' not in df.columns:
                            candidates = [c for c in df.columns if 'atr' in c.lower() and c.startswith('runtime_')]
                            if candidates:
                                df['atr'] = df[candidates[0]]
                                self.ctx.logger.debug(f"Created ATR alias 'atr' from '{candidates[0]}' in fallback")
                    except Exception:
                        self.ctx.logger.exception('ATR fallback calculation failed')
            except Exception:
                self.ctx.logger.exception('Failed during indicator fallback calculations')

            self.ctx.logger.debug(f"Calculated SMA, ATR, and {len(self.ctx.indicators)} additional indicators")
            # Debug: log indicator columns for easy troubleshooting
            try:
                indicator_cols = [c for c in df.columns if any(k in c.lower() for k in ('rsi', 'atr', 'adx'))]
                self.ctx.logger.debug(f"Indicator-related columns: {indicator_cols}")
            except Exception:
                pass
            
            # Feed indicator data to in-process collector for real-time monitoring
            self._update_indicator_collector(df)
            
            # Feed comprehensive metrics with current data
            self._update_comprehensive_collector(df)
            
            return df
        
        except Exception as e:
            self.ctx.logger.error(f"Indicator calculation error: {e}", exc_info=True)
            time.sleep(self.ctx.poll_interval)
            return None
    
    def _compute_ema_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute required EMA columns for strategies.
        
        Args:
            df: Market data DataFrame
            
        Returns:
            DataFrame with EMA columns added
        """
        try:
            required_emas = set()
            
            def collect_ema_periods(obj):
                if obj is None:
                    return
                # Common attribute names used across strategies
                for attr in ('fast_period', 'slow_period', 'fast_ema', 'slow_ema', 'short_window', 'long_window', 'fast_ma', 'slow_ma'):
                    if hasattr(obj, attr):
                        try:
                            val = int(getattr(obj, attr))
                            # Collect EMA periods from MA-related attributes
                            if any(x in attr for x in ('ema', 'fast_period', 'slow_period', 'fast_ma', 'slow_ma')):
                                required_emas.add(val)
                        except Exception:
                            pass
            
            # If using StrategySelector (or StrategySelectorAdapter), inspect child strategies
            try:
                from cthulu.strategy.strategy_selector import StrategySelector
                from cthulu.strategy.selector_adapter import StrategySelectorAdapter
                
                # Handle StrategySelectorAdapter wrapping a StrategySelector
                strategy_to_inspect = self.ctx.strategy
                if isinstance(strategy_to_inspect, StrategySelectorAdapter):
                    strategy_to_inspect = getattr(strategy_to_inspect, 'selector', strategy_to_inspect)
                
                if isinstance(strategy_to_inspect, StrategySelector):
                    for s in strategy_to_inspect.strategies.values():
                        collect_ema_periods(s)
                else:
                    collect_ema_periods(self.ctx.strategy)
            except ImportError:
                collect_ema_periods(self.ctx.strategy)
            except Exception:
                collect_ema_periods(self.ctx.strategy)
            
            # Also inspect scalping-specific attrs
            try:
                if hasattr(self.ctx.strategy, 'fast_ema'):
                    required_emas.add(int(getattr(self.ctx.strategy, 'fast_ema')))
                if hasattr(self.ctx.strategy, 'slow_ema'):
                    required_emas.add(int(getattr(self.ctx.strategy, 'slow_ema')))
            except Exception:
                pass
            
            # Fallback: collect EMA periods from configuration to ensure coverage
            try:
                strat_cfg = self.ctx.config.get('strategy', {}) if isinstance(self.ctx.config, dict) else {}
                if strat_cfg.get('type') == 'dynamic':
                    for s in strat_cfg.get('strategies', []):
                        params = s.get('params', {}) if isinstance(s.get('params', {}), dict) else {}
                        for key in ('fast_ema', 'slow_ema', 'fast_period', 'slow_period', 'short_window', 'long_window', 'fast_ma', 'slow_ma'):
                            if key in params and params[key]:
                                try:
                                    required_emas.add(int(params[key]))
                                except Exception:
                                    pass
                else:
                    params = strat_cfg.get('params', {}) if isinstance(strat_cfg.get('params', {}), dict) else {}
                    for key in ('fast_ema', 'slow_ema', 'fast_period', 'slow_period', 'short_window', 'long_window', 'fast_ma', 'slow_ma'):
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
                        from cthulu.strategy.selector_adapter import StrategySelectorAdapter
                        
                        strategy_to_check = self.ctx.strategy
                        if isinstance(strategy_to_check, StrategySelectorAdapter):
                            strategy_to_check = getattr(strategy_to_check, 'selector', strategy_to_check)
                        
                        if isinstance(strategy_to_check, StrategySelector):
                            if 'scalping' in (name.lower() for name in strategy_to_check.strategies.keys()):
                                scalping_periods.update({5, 10})
                    except Exception:
                        # Direct strategy instance
                        try:
                            if getattr(self.ctx.strategy, 'name', '').lower() == 'scalping':
                                scalping_periods.update({
                                    getattr(self.ctx.strategy, 'fast_ema', 5),
                                    getattr(self.ctx.strategy, 'slow_ema', 10)
                                })
                        except Exception:
                            pass
                    
                    required_emas.update({int(x) for x in scalping_periods if x})
                except Exception:
                    pass
                
                self.ctx.logger.debug(f"Collected EMA periods from config: {sorted(required_emas)}")
            except Exception:
                pass
            
            # Compute EMA columns
            if required_emas:
                self.ctx.logger.info(f"Computing EMA periods: {sorted(required_emas)}")
                for p in sorted(required_emas):
                    col = f'ema_{p}'
                    if col not in df.columns:
                        df[col] = df['close'].ewm(span=int(p), adjust=False).mean()
                self.ctx.logger.debug(f"Computed EMA columns: {[f'ema_{p}' for p in sorted(required_emas)]}")
        except Exception:
            self.ctx.logger.exception('Failed to compute EMA columns; continuing')
        
        return df
    
    def _generate_signal(self, df: pd.DataFrame):
        """
        Generate trading signal from strategy.
        
        Args:
            df: Market data DataFrame with indicators
            
        Returns:
            Signal object or None
        """
        try:
            current_bar = df.iloc[-1]
            
            # Diagnostic: log presence of RSI/ATR before strategy signal generation
            try:
                rsi_period = getattr(self.ctx.strategy, 'rsi_period', None)
                try:
                    rsi_period_int = int(rsi_period) if rsi_period is not None else None
                except Exception:
                    rsi_period_int = None
                rsi_col = f"rsi_{rsi_period_int}" if rsi_period_int and rsi_period_int != 14 else 'rsi'
                has_rsi = rsi_col in current_bar.index
                has_atr = 'atr' in current_bar.index
                self.ctx.logger.debug(f"Before strategy signal: has_rsi={has_rsi} (col={rsi_col}), has_atr={has_atr}")
                if has_rsi:
                    self.ctx.logger.debug(f"rsi value: {current_bar.get(rsi_col)}")
                if has_atr:
                    self.ctx.logger.debug(f"atr value: {current_bar.get('atr')}")
            except Exception:
                self.ctx.logger.exception('Failed to log indicator presence before strategy signal')
            
            # If dynamic selector (or adapter wrapping one), use its generator method
            try:
                from cthulu.strategy.strategy_selector import StrategySelector
                from cthulu.strategy.selector_adapter import StrategySelectorAdapter
                
                strategy_to_use = self.ctx.strategy
                if isinstance(strategy_to_use, StrategySelectorAdapter):
                    # Use full dataframe for proper regime detection
                    signal = strategy_to_use.generate_signal_with_data(df, current_bar)
                elif isinstance(strategy_to_use, StrategySelector):
                    signal = strategy_to_use.generate_signal(df, current_bar)
                else:
                    signal = self.ctx.strategy.on_bar(current_bar)
            except Exception:
                # Fallback by duck-typing
                if hasattr(self.ctx.strategy, 'generate_signal'):
                    signal = self.ctx.strategy.generate_signal(df, current_bar)
                else:
                    signal = self.ctx.strategy.on_bar(current_bar)
            
            if signal:
                self.ctx.logger.info(
                    f"Signal generated: {signal.side.name} {signal.symbol} "
                    f"(confidence: {signal.confidence:.2f})"
                )
                
                # Cognition Engine Enhancement - Apply AI/ML signal adjustments
                if self.ctx.cognition_engine:
                    try:
                        signal_direction = 'long' if signal.side == SignalType.LONG else 'short'
                        enhancement = self.ctx.cognition_engine.enhance_signal(
                            signal_direction=signal_direction,
                            signal_confidence=signal.confidence,
                            symbol=self.ctx.symbol,
                            market_data=df
                        )
                        
                        # Apply confidence adjustment
                        original_conf = signal.confidence
                        signal.confidence = min(1.0, signal.confidence * enhancement.confidence_multiplier)
                        
                        # Store size multiplier for later use in position sizing
                        signal._cognition_size_mult = enhancement.size_multiplier
                        signal._cognition_reasons = enhancement.reasons
                        signal._cognition_warnings = enhancement.warnings
                        
                        if enhancement.reasons:
                            self.ctx.logger.info(f"Cognition boost: {', '.join(enhancement.reasons)}")
                        if enhancement.warnings:
                            self.ctx.logger.warning(f"Cognition warnings: {', '.join(enhancement.warnings)}")
                        
                        if original_conf != signal.confidence:
                            self.ctx.logger.info(
                                f"Signal confidence adjusted: {original_conf:.2f} → {signal.confidence:.2f} "
                                f"(size mult: {enhancement.size_multiplier:.2f})"
                            )
                        
                        # Check if trading is advisable
                        should_trade, reason = self.ctx.cognition_engine.should_trade(
                            self.ctx.symbol, df
                        )
                        if not should_trade:
                            self.ctx.logger.info(f"Cognition advises against trading: {reason}")
                            return None
                            
                    except Exception as e:
                        self.ctx.logger.warning(f"Cognition enhancement failed: {e}")
            else:
                self.ctx.logger.info("Strategy returned NO SIGNAL for this bar")
            
            return signal
        
        except Exception as e:
            self.ctx.logger.error(f"Strategy signal error: {e}", exc_info=True)
            return None
    
    def _process_entry_signal(self, signal):
        """
        Process an entry signal (risk approval + execution).
        
        CRITICAL CHANGE: Now includes Entry Confluence Filter as quality gate.
        Signals must pass entry quality analysis before execution.
        
        ADDITIONAL SAFEGUARD: Prevents opposite direction trades on same symbol.
        
        Args:
            signal: Trading signal from strategy
        """
        if signal.side not in [SignalType.LONG, SignalType.SHORT]:
            return
        
        try:
            # ==========================================================
            # COOLDOWN CHECK - Prevent rapid-fire trading
            # ==========================================================
            if not self._check_trade_cooldown(signal):
                self.ctx.logger.info("Skipping signal due to trade cooldown")
                return
            
            # Get current account info and positions
            account_info = self.ctx.connector.get_account_info()
            balance = float(account_info.get('balance', 0)) if account_info else 0
            equity = float(account_info.get('equity', balance)) if account_info else balance
            
            # CRITICAL: Get positions directly from MT5 for accurate count
            try:
                import MetaTrader5 as mt5
                mt5_positions = mt5.positions_get(symbol=self.ctx.symbol)
                current_positions = len(mt5_positions) if mt5_positions else 0
                
                # ==========================================================
                # CRITICAL FIX: Prevent opposite direction trades
                # ==========================================================
                if mt5_positions:
                    existing_directions = set()
                    for pos in mt5_positions:
                        # MT5 type: 0 = BUY, 1 = SELL
                        pos_dir = 'LONG' if pos.type == 0 else 'SHORT'
                        existing_directions.add(pos_dir)
                    
                    signal_direction = 'LONG' if signal.side == SignalType.LONG else 'SHORT'
                    opposite_direction = 'SHORT' if signal_direction == 'LONG' else 'LONG'
                    
                    if opposite_direction in existing_directions:
                        self.ctx.logger.warning(
                            f"BLOCKED: {signal_direction} signal while {opposite_direction} positions exist. "
                            f"Close existing positions first or let them run."
                        )
                        return
                        
            except Exception as e:
                self.ctx.logger.debug(f"MT5 position check fallback: {e}")
                current_positions = len(self.ctx.position_manager.get_positions(symbol=self.ctx.symbol))
            
            # ============================================================
            # ENTRY CONFLUENCE FILTER - Quality Gate (NEW)
            # This is the critical addition that prevents blind entries
            # ============================================================
            entry_confluence_result = None
            
            # Skip confluence filter for pending entries (already filtered)
            skip_confluence = (
                hasattr(signal, 'metadata') and 
                signal.metadata.get('skip_confluence_filter', False)
            )
            
            if skip_confluence:
                self.ctx.logger.debug("Skipping confluence filter for pending entry")
            else:
                try:
                    from cthulu.cognition.entry_confluence import get_entry_confluence_filter
                    
                    # Get current market data for analysis
                    df = self.ctx.data_layer.get_cached_data(self.ctx.symbol)
                    if df is None or len(df) == 0:
                        # Fallback: fetch fresh data
                        rates = self.ctx.connector.get_rates(
                            symbol=self.ctx.symbol,
                            timeframe=self.ctx.timeframe,
                            count=self.ctx.lookback_bars
                        )
                        if rates is not None:
                            df = self.ctx.data_layer.normalize_rates(rates, symbol=self.ctx.symbol)
                    
                    if df is not None and len(df) > 20:
                        signal_direction = 'long' if signal.side == SignalType.LONG else 'short'
                        current_price = float(df['close'].iloc[-1])
                        signal_price = getattr(signal, 'price', None) or getattr(signal, 'entry_price', None)
                        atr = float(df['atr'].iloc[-1]) if 'atr' in df.columns else None
                        
                        confluence_filter = get_entry_confluence_filter(config=self.ctx.config.get('entry_confluence', {}))
                        entry_confluence_result = confluence_filter.analyze_entry(
                            signal_direction=signal_direction,
                            current_price=current_price,
                            symbol=self.ctx.symbol,
                            market_data=df,
                            atr=atr,
                            signal_entry_price=signal_price
                        )
                        
                        # Log entry analysis
                        self.ctx.logger.info(f"Entry confluence: {entry_confluence_result.quality.value} "
                                            f"(score={entry_confluence_result.score:.0f}, "
                                            f"mult={entry_confluence_result.position_mult:.2f})")
                        
                        if entry_confluence_result.reasons:
                            self.ctx.logger.debug(f"  Entry reasons: {entry_confluence_result.reasons[:3]}")
                        if entry_confluence_result.warnings:
                            self.ctx.logger.warning(f"  Entry warnings: {entry_confluence_result.warnings}")
                        
                        # ==========================================================
                        # STRICT QUALITY GATE - Only GOOD/PREMIUM entries proceed
                        # MARGINAL entries get queued, POOR/REJECT are blocked
                        # ==========================================================
                        from cthulu.cognition.entry_confluence import EntryQuality
                        
                        # REJECT: Signal invalidated - block entirely
                        if entry_confluence_result.quality == EntryQuality.REJECT:
                            self.ctx.logger.info(f"❌ Entry REJECTED: {entry_confluence_result.quality.value} "
                                                f"(score={entry_confluence_result.score:.0f}) - Signal invalidated")
                            return
                        
                        # POOR: Bad entry conditions - block entirely (don't even queue)
                        if entry_confluence_result.quality == EntryQuality.POOR:
                            self.ctx.logger.info(f"⏸️ Entry POOR quality: score={entry_confluence_result.score:.0f} - "
                                                f"Waiting for better market conditions")
                            return
                        
                        # MARGINAL: Suboptimal entry - queue for better price, don't execute now
                        if entry_confluence_result.quality == EntryQuality.MARGINAL:
                            if entry_confluence_result.optimal_entry:
                                confluence_filter.register_pending_entry(
                                    signal_id=signal.id,
                                    signal_direction=signal_direction,
                                    optimal_entry=entry_confluence_result.optimal_entry,
                                    symbol=self.ctx.symbol
                                )
                                self.ctx.logger.info(f"⏳ Entry QUEUED (MARGINAL): Waiting for better price @ "
                                                    f"{entry_confluence_result.optimal_entry:.5f}")
                            else:
                                self.ctx.logger.info(f"⏸️ Entry MARGINAL with no better level identified - SKIP")
                            return
                        
                        # Legacy gate check (for should_enter=False that isn't covered above)
                        if not entry_confluence_result.should_enter:
                            self.ctx.logger.info(f"Entry rejected by confluence filter: "
                                                f"{entry_confluence_result.quality.value} quality, "
                                                f"score={entry_confluence_result.score:.0f}")
                            
                            # Register for pending entry if waiting is recommended
                            if entry_confluence_result.wait_for_better and entry_confluence_result.optimal_entry:
                                confluence_filter.register_pending_entry(
                                    signal_id=signal.id,
                                    signal_direction=signal_direction,
                                    optimal_entry=entry_confluence_result.optimal_entry,
                                    symbol=self.ctx.symbol
                                )
                                self.ctx.logger.info(f"Signal queued: waiting for better entry at "
                                                    f"{entry_confluence_result.optimal_entry:.5f}")
                            return
                        
                        # At this point, only GOOD or PREMIUM quality entries proceed
                        self.ctx.logger.info(f"✅ Entry quality APPROVED: {entry_confluence_result.quality.value}")
                            
                except ImportError:
                    self.ctx.logger.debug("Entry confluence filter not available, proceeding without")
                except Exception as e:
                    self.ctx.logger.warning(f"Entry confluence analysis failed: {e}")
            
            # Adaptive Account Manager check (if available)
            if self.ctx.adaptive_account_manager:
                try:
                    phase_config = self.ctx.adaptive_account_manager.update(balance, equity)
                    
                    # Check if can trade based on phase limits
                    can_trade, trade_reason = self.ctx.adaptive_account_manager.can_open_trade()
                    if not can_trade:
                        self.ctx.logger.info(f"Phase limit: {trade_reason}")
                        return
                    
                    # Validate signal confidence/RR against phase requirements
                    signal_confidence = getattr(signal, 'confidence', 0.5)
                    signal_rr = getattr(signal, 'risk_reward', 1.5)
                    is_valid, valid_reason = self.ctx.adaptive_account_manager.validate_signal(
                        signal_confidence, signal_rr
                    )
                    if not is_valid:
                        self.ctx.logger.info(f"Signal validation failed: {valid_reason}")
                        return
                    
                    # Log phase info
                    state = self.ctx.adaptive_account_manager.get_state()
                    self.ctx.logger.debug(f"Account phase: {state.phase.value}, "
                                         f"timeframe: {state.active_timeframe.value}")
                except Exception as e:
                    self.ctx.logger.debug(f"Adaptive account manager check failed: {e}")
            
            # Risk approval
            approved, reason, position_size = self.ctx.risk_manager.approve(
                signal=signal,
                account_info=account_info,
                current_positions=current_positions
            )
            
            # ==========================================================
            # CENTRALIZED POSITION SIZING - Full audit trail
            # All adjustments happen in one place for transparency
            # Now with ML Enhancement Manager integration
            # ==========================================================
            if approved and position_size > 0:
                # Get market data for ML features (use cached from confluence filter or fetch fresh)
                ml_market_data = df if 'df' in dir() and df is not None else None
                if ml_market_data is None:
                    try:
                        ml_market_data = self.ctx.data_layer.get_cached_data(self.ctx.symbol)
                    except Exception:
                        pass
                
                size_decision = self._calculate_final_position_size(
                    signal=signal,
                    base_size=position_size,
                    entry_confluence_result=entry_confluence_result,
                    balance=balance,
                    market_data=ml_market_data
                )
                position_size = size_decision.final_size
                
                # Log the complete sizing decision
                self.ctx.logger.info(f"Position sizing: {size_decision.reasoning}")
            
            if approved:
                self.ctx.logger.info(f"Risk approved: {position_size:.2f} lots - {reason}")
                
                if not self.ctx.dry_run:
                    self._execute_order(signal, position_size)
                else:
                    self.ctx.logger.info("[DRY RUN] Would place order here")
            else:
                self.ctx.logger.info(f"Risk rejected: {reason}")
        
        except Exception as e:
            self.ctx.logger.error(f"Order execution error: {e}", exc_info=True)
    
    def _execute_order(self, signal, position_size: float):
        """
        Execute an order based on signal.
        
        Args:
            signal: Trading signal
            position_size: Approved position size in lots
        """
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
            if self.ctx.advisory_manager and self.ctx.advisory_manager.enabled:
                decision = self.ctx.advisory_manager.decide(order_req, signal)
            else:
                decision = {'action': 'execute', 'result': None}
        except Exception:
            self.ctx.logger.exception('Advisory manager decision failed; defaulting to execute')
            decision = {'action': 'execute', 'result': None}
        
        if decision['action'] == 'execute':
            self._execute_real_order(order_req, signal)
        elif decision['action'] == 'advisory':
            self._record_advisory_signal(signal)
        elif decision['action'] == 'ghost':
            self._record_ghost_signal(signal, decision.get('result'))
        else:
            self.ctx.logger.warning('Advisory manager rejected order request')
    
    def _execute_real_order(self, order_req: OrderRequest, signal):
        """Execute a real order."""
        self.ctx.logger.info(f"Placing {order_req.side} order for {order_req.volume} lots")
        result = self.ctx.execution_engine.place_order(order_req)
        
        if result.status == OrderStatus.FILLED:
            self.ctx.logger.info(
                f"Order filled: ticket={result.order_id}, "
                f"price={result.fill_price:.5f}"
            )
            
            # CRITICAL: Record trade for cooldown
            self._record_trade_executed(signal)
            
            # Track position - ensure symbol is properly passed
            track_metadata = signal.metadata.copy() if signal.metadata else {}
            track_metadata['symbol'] = signal.symbol
            track_metadata['side'] = order_req.side
            self.ctx.position_manager.track_position(result, signal_metadata=track_metadata)
            
            # ==========================================================
            # PUBLISH TRADE EVENT TO EVENT BUS (Non-blocking metrics)
            # ==========================================================
            try:
                from cthulu.observability.trade_event_bus import publish_trade_opened
                account_info = self.ctx.connector.get_account_info()
                balance = float(account_info.get('balance', 0)) if account_info else 0
                
                publish_trade_opened(
                    ticket=result.order_id,
                    symbol=signal.symbol,
                    side=order_req.side,
                    volume=result.filled_volume,
                    price=result.fill_price,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                    source="system",
                    strategy=self.ctx.strategy.__class__.__name__ if self.ctx.strategy else "",
                    signal_id=signal.id,
                    account_balance=balance,
                    confidence=signal.confidence
                )
            except Exception as e:
                self.ctx.logger.debug(f"Event bus publish (non-critical): {e}")
            
            # Record in database
            signal_record = SignalRecord(
                timestamp=signal.timestamp,
                symbol=signal.symbol,
                side=signal.side.name,
                confidence=signal.confidence,
                price=result.fill_price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                metadata=signal.metadata,
                executed=True,
                execution_timestamp=datetime.now()
            )
            # compatibility: set strategy_name after construction in case dataclass signature differs
            try:
                signal_record.strategy_name = self.ctx.strategy.__class__.__name__
            except Exception:
                pass
            self.ctx.database.record_signal(signal_record)
            
            # Store signal context in Hektor for semantic memory
            try:
                indicators = signal.metadata.get('indicators', {}) if signal.metadata else {}
                regime = signal.metadata.get('regime', 'UNKNOWN') if signal.metadata else 'UNKNOWN'
                self._store_signal_in_hektor(signal, indicators, regime)
            except Exception:
                pass  # Non-critical
            
            trade_record = TradeRecord(
                signal_id=signal.id,
                order_id=result.order_id,
                symbol=signal.symbol,
                side=signal.side.name,
                entry_price=result.fill_price,
                volume=result.filled_volume,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                entry_time=datetime.now()
            )
            self.ctx.database.record_trade(trade_record)
        else:
            self.ctx.logger.error(
                f"Order failed: {result.status.name} - {result.message}"
            )
    
    def _record_advisory_signal(self, signal):
        """Record an advisory (non-executed) signal."""
        self.ctx.logger.info('Advisory decision: not executing order; recording advisory signal')
        signal_record = SignalRecord(
            timestamp=signal.timestamp,
            symbol=signal.symbol,
            side=signal.side.name,
            confidence=signal.confidence,
            price=None,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            metadata={**signal.metadata, 'advisory': True},
            executed=False
        )
        # compatibility: set strategy_name after construction
        try:
            signal_record.strategy_name = self.ctx.strategy.__class__.__name__
        except Exception:
            pass
        self.ctx.database.record_signal(signal_record)
    
    def _record_ghost_signal(self, signal, result):
        """Record a ghost trade signal."""
        self.ctx.logger.info('Ghost decision: small test trade executed (or attempted)')
        signal_record = SignalRecord(
            timestamp=signal.timestamp,
            symbol=signal.symbol,
            side=signal.side.name,
            confidence=signal.confidence,
            price=getattr(result, 'fill_price', None) if result else None,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            metadata={
                **signal.metadata,
                'advisory': 'ghost',
                'advisory_result': getattr(result, 'order_id', None) if result else None
            },
            executed=False
        )
        # compatibility: set strategy_name after construction
        try:
            signal_record.strategy_name = self.ctx.strategy.__class__.__name__
        except Exception:
            pass
        self.ctx.database.record_signal(signal_record)
    
    def _store_signal_in_hektor(self, signal, indicators: Dict[str, Any], regime: str):
        """Store signal context in Hektor for semantic memory.
        
        Args:
            signal: Trading signal
            indicators: Current indicator values
            regime: Market regime classification
        """
        if not self.ctx.hektor_adapter:
            return
        
        try:
            context = {
                'indicators': indicators,
                'regime': regime,
                'symbol': signal.symbol,
                'timestamp': datetime.now().isoformat()
            }
            self.ctx.hektor_adapter.store_signal(signal, context)
        except Exception as e:
            self.ctx.logger.debug(f"Hektor signal storage (non-critical): {e}")
    
    def _store_trade_in_hektor(self, trade, outcome: Dict[str, Any]):
        """Store completed trade in Hektor for semantic memory.
        
        Args:
            trade: Completed trade record
            outcome: Trade outcome details
        """
        if not self.ctx.hektor_adapter:
            return
        
        try:
            self.ctx.hektor_adapter.store_trade(trade, outcome)
        except Exception as e:
            self.ctx.logger.debug(f"Hektor trade storage (non-critical): {e}")
    
    def _get_hektor_context(self, signal, indicators: Dict[str, Any], regime: str) -> Optional[str]:
        """Retrieve relevant historical context from Hektor.
        
        Args:
            signal: Current trading signal
            indicators: Current indicator values
            regime: Market regime
            
        Returns:
            Formatted context string or None
        """
        if not self.ctx.hektor_retriever:
            return None
        
        try:
            contexts = self.ctx.hektor_retriever.get_similar_signals(
                signal, indicators, regime, k=5, min_score=0.7
            )
            if contexts:
                return self.ctx.hektor_retriever.format_context_window(contexts)
        except Exception as e:
            self.ctx.logger.debug(f"Hektor context retrieval (non-critical): {e}")
        
        return None
    
    def _adopt_external_trades(self):
        """Scan and adopt external trades if enabled."""
        try:
            if self.ctx.trade_adoption_policy and getattr(self.ctx.trade_adoption_policy, 'enabled', False):
                adopted = self.ctx.trade_adoption_manager.scan_and_adopt()
                if adopted > 0:
                    self.ctx.logger.info(f"Adopted {adopted} external trade(s)")
        except Exception as e:
            self.ctx.logger.error(f"Trade adoption scan error: {e}", exc_info=True)
    
    def _monitor_positions(self, df: pd.DataFrame):
        """
        Monitor open positions and check exit strategies.
        Also applies dynamic SL/TP management.
        
        Args:
            df: Market data DataFrame with indicators
        """
        try:
            if not self.ctx.position_manager:
                self.ctx.logger.debug("Position manager unavailable; skipping position monitoring")
                return
            positions = self.ctx.position_manager.monitor_positions()
            if positions:
                self.ctx.logger.debug(f"Monitoring {len(positions)} open positions")
                total_pnl = sum(p.unrealized_pnl for p in positions)
                self.ctx.logger.debug(f"Total unrealized P&L: {total_pnl:.2f}")
            
            # Get account info for exit strategies
            account_info = self.ctx.connector.get_account_info()
            
            # Get ATR for dynamic SL/TP
            atr_value = df['atr'].iloc[-1] if 'atr' in df.columns else None
            
            # PROFIT SCALING - Run scaling cycle for all positions
            try:
                ps_present = bool(getattr(self.ctx, 'profit_scaler', None))
                ps_enabled = False
                try:
                    ps_enabled = bool(getattr(getattr(self.ctx, 'profit_scaler', None), 'config', None) and getattr(self.ctx.profit_scaler.config, 'enabled', False))
                except Exception:
                    ps_enabled = False
                self.ctx.logger.debug(f"Profit scaler status: present={ps_present}, enabled={ps_enabled}")
            except Exception:
                pass

            if self.ctx.profit_scaler and account_info:
                try:
                    balance = float(account_info.get('balance', 0)) if isinstance(account_info, dict) else float(getattr(account_info, 'balance', 0))
                    scaling_results = self.ctx.profit_scaler.run_scaling_cycle(balance)
                    if scaling_results:
                        for sr in scaling_results:
                            if sr.get('success'):
                                self.ctx.logger.info(f"Profit scaling: {sr}")
                            elif sr.get('skipped'):
                                # Non-actionable condition (e.g., position at minimum lot) - log at debug level to avoid noise
                                self.ctx.logger.debug(f"Profit scaling skipped: {sr.get('error')}")
                            elif sr.get('error'):
                                self.ctx.logger.warning(f"Profit scaling issue: {sr.get('error')}")
                except Exception as e:
                    self.ctx.logger.error(f"Profit scaling cycle error: {e}")
            
            # COGNITION EXIT SIGNALS - AI/ML enhanced exit decisions
            if self.ctx.cognition_engine and positions:
                try:
                    # Get current indicators
                    current_bar = df.iloc[-1] if len(df) > 0 else {}
                    indicators = {
                        'rsi': current_bar.get('rsi', current_bar.get('rsi_14', 50)),
                        'atr': atr_value or 0,
                        'adx': current_bar.get('adx', 20),
                        'macd': current_bar.get('macd', 0),
                        'bb_upper': current_bar.get('bb_upper', 0),
                        'bb_lower': current_bar.get('bb_lower', 0)
                    }
                    
                    # Convert positions to dict format for cognition engine
                    pos_dicts = []
                    for p in positions:
                        pos_dicts.append({
                            'ticket': p.ticket,
                            'symbol': p.symbol,
                            'type': 0 if p.side.lower() == 'buy' else 1,
                            'price_open': p.open_price,
                            'price_current': p.current_price,
                            'volume': p.volume,
                            'profit': p.unrealized_pnl,
                            'time': getattr(p, 'open_time', None)
                        })
                    
                    exit_signals = self.ctx.cognition_engine.get_exit_signals(
                        pos_dicts, df, indicators
                    )
                    
                    for exit_sig in exit_signals:
                        if exit_sig.should_exit and exit_sig.confidence > 0.7:
                            self.ctx.logger.info(
                                f"Cognition exit signal: #{exit_sig.ticket} "
                                f"urgency={exit_sig.urgency.value} conf={exit_sig.confidence:.2f} "
                                f"reasons: {', '.join(exit_sig.reasons)}"
                            )
                            # Mark position for priority exit
                            for p in positions:
                                if p.ticket == exit_sig.ticket:
                                    p._cognition_exit = exit_sig
                                    break
                                    
                except Exception as e:
                    self.ctx.logger.debug(f"Cognition exit signals error: {e}")
            
            # Check each position against exit strategies
            for position in positions:
                # DYNAMIC SL/TP MANAGEMENT
                if self.ctx.dynamic_sltp_manager and atr_value and account_info:
                    try:
                        self._apply_dynamic_sltp(position, atr_value, account_info, df)
                    except Exception as e:
                        self.ctx.logger.error(f"Dynamic SL/TP error for {position.ticket}: {e}")
                
                # Prepare market data for exit strategies
                exit_data = {
                    'current_price': position.current_price,
                    'current_data': df.iloc[-1],
                    'account_info': account_info,
                    'indicators': {
                        'atr': atr_value
                    }
                }
                
                # Check exit strategies (already sorted by priority)
                for exit_strategy in self.ctx.exit_strategies:
                    if not exit_strategy.is_enabled():
                        continue
                    
                    exit_signal = exit_strategy.should_exit(position, exit_data)
                    
                    if exit_signal:
                        self._process_exit_signal(position, exit_signal)
                        # Exit after first strategy triggers (highest priority wins)
                        break
        
        except Exception as e:
            self.ctx.logger.error(f"Position monitoring error: {e}", exc_info=True)
    
    def _apply_dynamic_sltp(self, position, atr_value: float, account_info: dict, df: pd.DataFrame):
        """
        Apply dynamic SL/TP management to a position.
        
        Args:
            position: Position to manage
            atr_value: Current ATR value
            account_info: Account information
            df: Market data DataFrame
        """
        try:
            # Get account metrics
            if isinstance(account_info, dict):
                balance = float(account_info.get('balance') or account_info.get('Balance') or 0.0)
                equity = float(account_info.get('equity') or account_info.get('Equity') or balance)
            else:
                balance = float(getattr(account_info, 'balance', 0.0))
                equity = float(getattr(account_info, 'equity', balance))
            
            # Calculate drawdown
            initial_balance = self.ctx.dynamic_sltp_manager.positions_managed.get(
                'initial_balance', balance
            )
            if 'initial_balance' not in self.ctx.dynamic_sltp_manager.positions_managed:
                self.ctx.dynamic_sltp_manager.positions_managed['initial_balance'] = balance
            
            peak_balance = max(balance, self.ctx.dynamic_sltp_manager.positions_managed.get('peak_balance', balance))
            self.ctx.dynamic_sltp_manager.positions_managed['peak_balance'] = peak_balance
            
            drawdown_pct = ((peak_balance - balance) / peak_balance * 100) if peak_balance > 0 else 0
            
            # Get position details
            entry_price = position.open_price
            current_price = position.current_price
            # Be defensive about attribute names: some PositionInfo instances use 'side' or 'type'
            side = getattr(position, 'side', None) or getattr(position, 'type', None) or getattr(position, 'position_type', None)
            # Some modules use 'sl'/'tp' while others use 'stop_loss'/'take_profit'
            current_sl = getattr(position, 'sl', None)
            if current_sl is None:
                current_sl = getattr(position, 'stop_loss', None)
            current_tp = getattr(position, 'tp', None)
            if current_tp is None:
                current_tp = getattr(position, 'take_profit', None)
            
            # Get symbol info for symbol-aware SL/TP safety
            symbol_info = None
            try:
                sym = getattr(position, 'symbol', None)
                if sym and getattr(self.ctx, 'connector', None):
                    symbol_info = self.ctx.connector.get_symbol_info(sym)
            except Exception:
                symbol_info = None

            # Get update recommendation
            update = self.ctx.dynamic_sltp_manager.update_position_sltp(
                ticket=position.ticket,
                entry_price=entry_price,
                current_price=current_price,
                side=side,
                current_sl=current_sl,
                current_tp=current_tp,
                atr=atr_value,
                balance=balance,
                equity=equity,
                drawdown_pct=drawdown_pct,
                initial_balance=initial_balance,
                symbol_info=symbol_info
            )

            # Log ATR and reasoning for transparency
            try:
                self.ctx.logger.info(
                    f"Dynamic SL/TP proposal for {position.ticket}: atr={atr_value:.4f}, reason={update.get('reasoning', '')}, action={update.get('action')}"
                )
                # Also emit detailed debug for full update payload
                self.ctx.logger.debug(f"Dynamic SL/TP update detail for {position.ticket}: {update}")
            except Exception:
                pass

            # Sanity guard: reject SL/TP that are unreasonably close to current price
            try:
                min_sl_pct = float(self.ctx.config.get('dynamic_sltp', {}).get('min_sl_distance_pct', 0.001))
                min_sl_distance = max(current_price * min_sl_pct, 0.0001)
                if update.get('update_sl') and update.get('new_sl') is not None:
                    new_sl_val = float(update['new_sl'])
                    if abs(new_sl_val - current_price) < min_sl_distance:
                        self.ctx.logger.warning(
                            f"Sanity check: skipping SL update for {position.ticket} as new SL ({new_sl_val}) is within {min_sl_distance:.4f} of current price {current_price}"
                        )
                        update['update_sl'] = False
            except Exception:
                pass

            # Apply updates if needed
            if update['update_sl'] or update['update_tp']:
                new_sl = update['new_sl'] if update['update_sl'] else current_sl
                new_tp = update['new_tp'] if update['update_tp'] else current_tp
                
                # Broker-level sanity: check symbol's minimum stops before attempting modify
                try:
                    sym = getattr(position, 'symbol', None)
                    if sym and symbol_info:
                        point = symbol_info.get('point')
                        stops_level = symbol_info.get('trade_stops_level') or symbol_info.get('trade_freeze_level')
                        if point and stops_level and update.get('update_sl') and new_sl is not None:
                            min_dist = float(point) * float(stops_level)
                            diff = abs(current_price - float(new_sl))
                            self.ctx.logger.debug(f"Broker min check: point={point}, stops_level={stops_level}, min_dist={min_dist}, diff={diff}")
                            if diff < min_dist - 1e-12:
                                self.ctx.logger.warning(
                                    f"Skipping SL update for {position.ticket}: desired SL {new_sl} is within broker min stop distance {min_dist} of current price {current_price}"
                                )
                                # Emit metric and do not attempt modify
                                try:
                                    if getattr(self.ctx, 'metrics', None):
                                        self.ctx.metrics.increment('dynamic_sltp.skipped_too_close')
                                except Exception:
                                    pass
                                update['update_sl'] = False
                except Exception:
                    pass

                # If still needs update, attempt modify
                success = False
                if update.get('update_sl') or update.get('update_tp'):
                    success = self.ctx.position_lifecycle.modify_position(
                        position.ticket, sl=new_sl, tp=new_tp
                    )
                    # Retry once after refreshing tracker from MT5 to handle transient state mismatches
                    if not success:
                        try:
                            self.ctx.position_lifecycle.refresh_positions()
                            success = self.ctx.position_lifecycle.modify_position(position.ticket, sl=new_sl, tp=new_tp)
                        except Exception:
                            # Ignore errors during retry
                            pass

                if success:
                    self.ctx.logger.info(
                        f"Dynamic SL/TP: {update['action']} - Position {position.ticket} "
                        f"SL: {current_sl} -> {new_sl}, TP: {current_tp} -> {new_tp}"
                    )
                else:
                    # Gather diagnostics for failed SL/TP application
                    tracker_state = None
                    try:
                        tracker_state = self.ctx.position_tracker.get_position(position.ticket) if getattr(self.ctx, 'position_tracker', None) else None
                    except Exception:
                        tracker_state = "<error_reading_tracker>"
                    mt5_state = None
                    try:
                        mt5_state = self.ctx.connector.get_position_by_ticket(position.ticket) if getattr(self.ctx, 'connector', None) else None
                    except Exception as e:
                        mt5_state = f"<error_fetching_mt5:{e}>"

                    self.ctx.logger.warning(
                        f"Failed to apply dynamic SL/TP to position {position.ticket} after retry. "
                        f"update={update}, tracker={tracker_state}, mt5={mt5_state}, "
                        f"current_sl={current_sl}, current_tp={current_tp}, new_sl={new_sl}, new_tp={new_tp}"
                    )

                    # Emit metric if metrics collector available
                    try:
                        if getattr(self.ctx, 'metrics', None):
                            self.ctx.metrics.increment('dynamic_sltp.failures')
                    except Exception:
                        pass
        
        except Exception as e:
            self.ctx.logger.error(f"Error applying dynamic SL/TP: {e}", exc_info=True)
    
    def _process_exit_signal(self, position, exit_signal):
        """
        Process an exit signal.
        
        Args:
            position: Position to close
            exit_signal: Exit signal from strategy
        """
        self.ctx.logger.info(
            f"Exit triggered by {exit_signal.strategy_name}: "
            f"{exit_signal.reason}"
        )
        
        if not self.ctx.dry_run:
            # Close position
            close_result = self.ctx.position_manager.close_position(
                ticket=position.ticket,
                reason=exit_signal.reason,
                partial_volume=exit_signal.partial_volume
            )
            
            if close_result.status == OrderStatus.FILLED:
                pnl = position.unrealized_pnl
                exit_price = close_result.fill_price
                exit_time = datetime.now()
                
                self.ctx.logger.info(
                    f"Position closed: ticket={position.ticket}, "
                    f"P&L={pnl:.2f}"
                )
                
                # Update database with CLOSED status
                self.ctx.database.update_trade_exit(
                    order_id=position.ticket,
                    exit_price=exit_price,
                    exit_time=exit_time,
                    profit=pnl,
                    exit_reason=exit_signal.reason
                )
                
                # Calculate trade duration
                duration_seconds = 0
                try:
                    open_time = getattr(position, 'open_time', None)
                    if open_time:
                        duration_seconds = (exit_time - open_time).total_seconds()
                except Exception:
                    pass
                
                # ==========================================================
                # PUBLISH TRADE CLOSED EVENT TO EVENT BUS (Non-blocking)
                # ==========================================================
                try:
                    from cthulu.observability.trade_event_bus import publish_trade_closed
                    account_info = self.ctx.connector.get_account_info()
                    balance = float(account_info.get('balance', 0)) if account_info else 0
                    
                    publish_trade_closed(
                        ticket=position.ticket,
                        symbol=position.symbol,
                        side=getattr(position, 'side', getattr(position, 'type', 'BUY')),
                        volume=position.volume,
                        entry_price=position.open_price,
                        exit_price=close_result.fill_price,
                        pnl=position.unrealized_pnl,
                        duration_seconds=duration_seconds,
                        source="system",
                        exit_reason=exit_signal.reason,
                        account_balance=balance
                    )
                except Exception as e:
                    self.ctx.logger.debug(f"Event bus publish close (non-critical): {e}")
                
                # Record trade completed for comprehensive metrics (ML training)
                try:
                    if self.ctx.comprehensive_collector:
                        is_win = pnl > 0
                        self.ctx.comprehensive_collector.record_trade_completed(
                            is_win=is_win,
                            pnl=pnl,
                            duration_seconds=duration_seconds
                        )
                except Exception:
                    self.ctx.logger.debug('Failed to record trade in comprehensive collector', exc_info=True)
                
                # ==========================================================
                # ML ENHANCEMENT: Record trade outcome for RL learning
                # ==========================================================
                try:
                    if self.ctx.ml_enhancement_manager:
                        poll_interval = self.ctx.poll_interval or 60
                        duration_bars = int(duration_seconds / poll_interval) if poll_interval > 0 else 0
                        
                        self.ctx.ml_enhancement_manager.record_trade_outcome(
                            ticket=position.ticket,
                            pnl=pnl,
                            exit_price=exit_price,
                            duration_bars=duration_bars,
                            exit_reason=exit_signal.reason
                        )
                        self.ctx.logger.debug(f"ML learning: recorded trade outcome pnl={pnl:.2f}")
                except Exception as e:
                    self.ctx.logger.debug(f'ML enhancement trade recording failed: {e}')
                
                # Record outcome in training data logger for ML
                try:
                    from cthulu.cognition.training_logger import log_trade_outcome
                    outcome = 'WIN' if pnl > 0 else ('LOSS' if pnl < 0 else 'BREAKEVEN')
                    log_trade_outcome(
                        ticket=position.ticket,
                        outcome=outcome,
                        pnl=pnl,
                        exit_price=exit_price
                    )
                except ImportError:
                    pass
                except Exception:
                    self.ctx.logger.debug('Failed to log trade outcome for ML training', exc_info=True)
                
                # Store trade outcome in Hektor for semantic memory
                try:
                    outcome = {
                        'pnl': pnl,
                        'result': 'WIN' if pnl > 0 else 'LOSS' if pnl < 0 else 'BREAKEVEN',
                        'exit_price': exit_price,
                        'exit_time': exit_time.isoformat(),
                        'exit_reason': exit_signal.reason,
                        'symbol': position.symbol
                    }
                    self._store_trade_in_hektor(position, outcome)
                except Exception:
                    pass  # Non-critical
                
                # Record position closed for metrics
                try:
                    self.ctx.metrics.record_position_closed(position.symbol)
                    # Also record the trade result with PnL
                    self.ctx.metrics.record_trade(pnl, position.symbol)
                except Exception:
                    self.ctx.logger.debug('Failed to record position closed in metrics', exc_info=True)
                
                # Update risk manager
                self.ctx.risk_manager.record_trade_result(pnl)
            else:
                self.ctx.logger.error(
                    f"Failed to close position {position.ticket}: "
                    f"{close_result.message}"
                )
        else:
            self.ctx.logger.info("[DRY RUN] Would close position here")
    
    def _check_connection_health(self):
        """Check connection health and reconnect if necessary."""
        try:
            if not self.ctx.connector.is_connected():
                self.ctx.logger.warning("Connection lost, attempting reconnect...")
                
                success = self.ctx.connector.reconnect()
                if success:
                    self.ctx.logger.info("Reconnection successful")
                    # Reconcile positions after reconnect
                    reconciled = self.ctx.position_manager.reconcile_positions()
                    self.ctx.logger.info(f"Reconciled {reconciled} positions")
                else:
                    self.ctx.logger.error("Reconnection failed; will keep trying on subsequent cycles")
                    # Avoid tight-looping on repeated failures; wait a short backoff
                    try:
                        time.sleep(min(30, self.ctx.poll_interval))
                    except Exception:
                        pass
        except Exception as e:
            self.ctx.logger.error(f"Health check error: {e}", exc_info=True)
    
    def _report_performance_metrics(self):
        """Report performance metrics periodically."""
        # Publish periodic performance metrics every 10 loops for near-real-time observability
        if self.loop_count % 10 == 0:
            self.ctx.logger.info(f"Performance metrics after {self.loop_count} loops:")
            
            # Sync latest position stats into metrics
            stats = self.ctx.position_manager.get_statistics()
            try:
                pos_summary = self.ctx.position_manager.get_position_summary_by_symbol()
                self.ctx.metrics.sync_with_positions_summary(stats, pos_summary)
                
                # Persist summary if function provided
                if self.ctx.persist_summary_fn and self.ctx.summary_path:
                    try:
                        self.ctx.persist_summary_fn(self.ctx.metrics, self.ctx.logger, self.ctx.summary_path)
                    except Exception:
                        self.ctx.logger.exception('Failed to persist periodic metrics summary')
                
                # Ensure a Prometheus exporter exists (fallback) and publish metrics
                if self.ctx.exporter is None:
                    try:
                        # Initialize exporter unconditionally as a fallback to ensure metrics are exposed
                        from cthulu.observability.prometheus import PrometheusExporter
                        prom_cfg = self.ctx.config.get('observability', {}).get('prometheus', {}) if getattr(self.ctx, 'config', None) else {}
                        exporter = PrometheusExporter(prefix=prom_cfg.get('prefix', 'Cthulu'))
                        # Use config path if specified, otherwise use platform-appropriate defaults
                        default_path = None
                        if os.name == 'nt':
                            # Windows: Use user's temp directory
                            temp_dir = tempfile.gettempdir()
                            default_path = os.path.join(temp_dir, "cthulu_metrics", "Cthulu_metrics.prom")
                        else:
                            # Unix/Linux: Prefer XDG_RUNTIME_DIR, fall back to /tmp
                            runtime_dir = os.getenv('XDG_RUNTIME_DIR')
                            if runtime_dir and os.path.exists(runtime_dir):
                                default_path = os.path.join(runtime_dir, "cthulu", "metrics", "Cthulu_metrics.prom")
                            else:
                                default_path = "/tmp/cthulu_metrics/Cthulu_metrics.prom"
                        
                        exporter._file_path = prom_cfg.get('textfile_path') or default_path
                        
                        # Ensure directory exists
                        try:
                            os.makedirs(os.path.dirname(exporter._file_path), exist_ok=True)
                        except Exception as e:
                            self.ctx.logger.warning(f"Failed to create metrics directory: {e}")
                        http_port = prom_cfg.get('http_port', 8181)
                        try:
                            import threading
                            from http.server import BaseHTTPRequestHandler, HTTPServer
                            class _MetricsHandler(BaseHTTPRequestHandler):
                                def do_GET(self):
                                    if self.path != '/metrics':
                                        self.send_response(404)
                                        self.end_headers()
                                        return
                                    try:
                                        body = exporter.export_text().encode('utf-8')
                                        self.send_response(200)
                                        self.send_header('Content-Type', 'text/plain; version=0.0.4')
                                        self.send_header('Content-Length', str(len(body)))
                                        self.end_headers()
                                        self.wfile.write(body)
                                    except Exception:
                                        self.send_response(500)
                                        self.end_headers()
                            def _serve():
                                server = HTTPServer(('0.0.0.0', int(http_port)), _MetricsHandler)
                                exporter.logger.info(f"Starting fallback metrics HTTP server on port {http_port}")
                                try:
                                    server.serve_forever()
                                except Exception:
                                    exporter.logger.exception('Fallback metrics HTTP server stopped')
                            t = threading.Thread(target=_serve, daemon=True)
                            t.start()
                        except Exception:
                            self.ctx.logger.exception('Failed to start fallback HTTP metrics server')
                        self.ctx.exporter = exporter
                        self.ctx.logger.info('Prometheus exporter (fallback) initialized in trading loop')
                    except Exception:
                        self.ctx.logger.exception('Failed to initialize fallback Prometheus exporter')

                # Publish to Prometheus exporter if present
                if self.ctx.exporter is not None:
                    try:
                        self.ctx.metrics.publish_to_prometheus(self.ctx.exporter)
                        try:
                            fp = getattr(self.ctx.exporter, '_file_path', None)
                            self.ctx.exporter.write_to_file(fp)
                        except Exception:
                            self.ctx.logger.debug('Failed to write Prometheus metrics to file')
                    except Exception:
                        self.ctx.logger.debug('Failed to publish metrics to Prometheus exporter')
            except Exception:
                self.ctx.logger.exception('Failed to sync position summary into metrics')
            
            self.ctx.logger.info(f"Position stats: {stats}")
    
    def _update_indicator_collector(self, df: pd.DataFrame):
        """Update the indicator collector with real-time indicator data."""
        if not self.ctx.indicator_collector:
            return
        
        try:
            current_bar = df.iloc[-1]
            updates = {
                'symbol': self.ctx.symbol,
                'timeframe': str(self.ctx.timeframe),
                'price_current': float(current_bar.get('close', 0)),
            }
            
            # RSI
            for col in df.columns:
                if 'rsi' in col.lower():
                    val = current_bar.get(col)
                    if val is not None and not pd.isna(val):
                        updates['rsi_value'] = float(val)
                        updates['rsi_overbought'] = float(val) >= 70
                        updates['rsi_oversold'] = float(val) <= 30
                    break
            
            # ADX
            adx_val = current_bar.get('adx') or current_bar.get('runtime_adx')
            if adx_val is not None and not pd.isna(adx_val):
                updates['adx_value'] = float(adx_val)
                updates['adx_trend_strength'] = 'strong' if float(adx_val) >= 50 else ('moderate' if float(adx_val) >= 25 else 'weak')
            
            # ATR
            atr_val = current_bar.get('atr') or current_bar.get('runtime_atr')
            if atr_val is not None and not pd.isna(atr_val):
                updates['atr_value'] = float(atr_val)
            
            # Volume
            volume = current_bar.get('volume') or current_bar.get('tick_volume')
            if volume is not None and not pd.isna(volume):
                updates['volume_current'] = float(volume)
            
            self.ctx.indicator_collector.update_snapshot(**updates)
            self.ctx.logger.info(f"Indicator collector updated: RSI={updates.get('rsi_value', 0):.1f}, ADX={updates.get('adx_value', 0):.1f}")
            
        except Exception as e:
            self.ctx.logger.warning(f"Error updating indicator collector: {e}")
    
    def _update_comprehensive_collector(self, df: pd.DataFrame = None):
        """Update the comprehensive collector with real-time trading data."""
        if not self.ctx.comprehensive_collector:
            self.ctx.logger.debug("Comprehensive collector not available")
            return
        
        try:
            # Get account info from connector
            if self.ctx.connector and self.ctx.connector.connected:
                try:
                    import MetaTrader5 as mt5
                    account_info = mt5.account_info()
                    if account_info:
                        self.ctx.comprehensive_collector.update_account_metrics(
                            balance=account_info.balance,
                            equity=account_info.equity,
                            margin=account_info.margin,
                            free_margin=account_info.margin_free,
                            margin_level=account_info.margin_level if account_info.margin_level else 0.0
                        )
                except Exception as e:
                    self.ctx.logger.debug(f"Failed to get MT5 account info: {e}")
            
            # Get position info
            try:
                positions = self.ctx.position_tracker.get_all_positions() if self.ctx.position_tracker else []
                open_count = len(positions)
                unrealized_pnl = sum(getattr(p, 'unrealized_pnl', 0) or 0 for p in positions)
                self.ctx.comprehensive_collector.update_position_metrics(
                    active_positions=open_count,
                    unrealized_pnl=unrealized_pnl
                )
            except Exception as e:
                self.ctx.logger.debug(f"Failed to get position info: {e}")
            
            # Update price data if df provided
            if df is not None and len(df) > 0:
                try:
                    current_bar = df.iloc[-1]
                    self.ctx.comprehensive_collector.update_price_metrics(
                        current_price=float(current_bar.get('close', 0)),
                        symbol=self.ctx.symbol
                    )
                except Exception as e:
                    self.ctx.logger.debug(f"Failed to update price metrics: {e}")
                    
        except Exception as e:
            self.ctx.logger.warning(f"Error updating comprehensive collector: {e}")


