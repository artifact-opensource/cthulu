"""
Multi-Symbol Trading Orchestrator
Runs independent analysis pipelines per symbol, shares portfolio-level risk.

Architecture:
  - Each symbol gets its own indicators, regime classifier, strategy selector
  - Portfolio-level: shared risk budget, max total positions, drawdown tracking
  - Scanner ranks all signals across symbols, executes best N
  - Symbol-specific config (lot sizes, sessions, strategy overrides)

Phase 1 of Cthulu Autonomous Trading System.
"""
import asyncio
from copy import deepcopy
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from execution_mode import ExecutionModeError, require_legacy_execution

logger = logging.getLogger(__name__)


def _resolve_mt5_timeframe(timeframe, mt5_module=None):
    if mt5_module is None:
        from cthulu.connector.mt5_connector import mt5 as mt5_module

    if isinstance(timeframe, str):
        name = timeframe.strip().upper()
        if not name.startswith("TIMEFRAME_"):
            name = f"TIMEFRAME_{name}"
        timeframe = getattr(mt5_module, name, None)
    if timeframe is None:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return timeframe


def _configured_timeframe(config: Dict[str, Any]) -> str:
    timeframe = config.get('timeframe')
    trading_config = config.get('trading')
    if not timeframe and isinstance(trading_config, dict):
        timeframe = trading_config.get('timeframe')
    return timeframe or 'M5'


@dataclass
class SymbolContext:
    """Per-symbol analysis state."""
    symbol: str
    timeframe: str = 'M5'
    market_data: Any = None
    indicators: Dict[str, Any] = field(default_factory=dict)
    regime: str = 'unknown'
    last_regime_update: float = 0.0
    last_signal_time: float = 0.0
    cooldown_until: float = 0.0  # Don't trade until this timestamp
    enabled: bool = True
    consecutive_losses: int = 0
    
    # Per-symbol config overrides
    max_positions: int = 2
    lot_size_override: Optional[float] = None
    strategy_overrides: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class ScoredSignal:
    """A signal with cross-symbol ranking score."""
    signal: Dict[str, Any]
    symbol: str
    score: float  # Combined: strategy confidence × regime fitness × confluence
    regime: str
    strategy: str
    timestamp: float = 0.0


class _MultiSymbolStrategyAdapter:
    def __init__(self, strategy: Any, symbol: str):
        self.strategy = strategy
        self.symbol = symbol

    def generate_signal(
        self,
        data: Any,
        indicators: Dict[str, Any],
        regime: str,
    ) -> Optional[Dict[str, Any]]:
        if data is None or len(data) == 0:
            return None

        bar = data.iloc[-1]
        if hasattr(self.strategy, "generate_signal_with_data"):
            raw_signal = self.strategy.generate_signal_with_data(data, bar)
        elif hasattr(self.strategy, "generate_signal"):
            raw_signal = self.strategy.generate_signal(data, bar)
        else:
            raw_signal = self.strategy.on_bar(bar)

        if raw_signal is None:
            return None
        if isinstance(raw_signal, dict):
            signal = raw_signal.copy()
        else:
            to_dict = getattr(raw_signal, "to_dict", None)
            if not callable(to_dict):
                logger.error("%s: Strategy returned an unsupported signal", self.symbol)
                return None
            signal = to_dict()

        metadata = signal.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            signal["metadata"] = metadata
        metadata.setdefault("market_regime", regime)
        metadata.setdefault("indicators", indicators)

        raw_direction = signal.get("direction") or signal.get("side") or signal.get("action")
        if hasattr(raw_direction, "value"):
            raw_direction = raw_direction.value
        direction = str(raw_direction or "").strip().lower()
        if direction in {"buy", "long"}:
            signal["direction"] = "buy"
        elif direction in {"sell", "short"}:
            signal["direction"] = "sell"
        else:
            logger.error("%s: Strategy signal has no valid direction", self.symbol)
            return None

        dynamic_selector = getattr(self.strategy, "selector", None)
        current_strategy = getattr(dynamic_selector, "current_strategy", None)
        strategy_name = (
            metadata.get("generated_by")
            or metadata.get("strategy_type")
            or signal.get("strategy")
            or getattr(current_strategy, "name", None)
            or getattr(self.strategy, "name", "unknown")
        )
        signal["symbol"] = self.symbol
        signal["strategy"] = str(strategy_name)
        signal.setdefault("strategy_score", metadata.get("strategy_score", 0.5))
        return signal


class MultiSymbolOrchestrator:
    """
    Orchestrates trading across multiple symbols.
    
    Flow per cycle:
    1. For each symbol: fetch data → indicators → regime → signal
    2. Collect all signals, rank by score
    3. Check portfolio-level risk budget
    4. Execute top N signals that fit within risk limits
    5. Manage ALL open positions across ALL symbols
    6. Evaluate exits across ALL positions
    """
    
    def __init__(self, components, config: Dict[str, Any]):
        """
        Args:
            components: SystemComponents from bootstrap
            config: Full config dict (must include 'watchlist' key)
        """
        self.components = components
        self.config = config
        self.timeframe = _configured_timeframe(config)
        self.loop_interval = config.get('loop_interval', 15)
        
        # Portfolio-level limits
        portfolio_config = config.get('portfolio', {})
        self.max_total_positions = portfolio_config.get('max_total_positions', 5)
        self.max_positions_per_symbol = portfolio_config.get('max_positions_per_symbol', 2)
        self.max_correlated_positions = portfolio_config.get('max_correlated_positions', 3)
        self.max_daily_loss_pct = portfolio_config.get('max_daily_loss_pct', 5.0)
        self.signal_cooldown_seconds = portfolio_config.get('signal_cooldown_seconds', 300)
        
        # Track daily P&L
        self._daily_start_equity = 0.0
        self._daily_date = None
        self._daily_loss_halt = False
        self._daily_tracking_initialized = False
        self._last_daily_limit_failure = None
        self._execution_halt_reason = None
        
        # Market Intelligence (Phase 2)
        self._macro: Optional[Any] = None
        try:
            from cognition.market_intel import MarketIntelligence
            intel_config = config.get('market_intel', {})
            self._macro = MarketIntelligence(intel_config)
            logger.info("Market Intelligence layer initialized ✅")
        except Exception as e:
            logger.warning(f"Market Intelligence init failed (non-fatal): {e}")
        
        self._current_macro_snapshot = None
        
        # Session Scheduler (Phase 3)
        self._session_scheduler = None
        try:
            from cognition.session_scheduler import SessionScheduler
            self._session_scheduler = SessionScheduler(config.get('sessions', {}))
            session_info = self._session_scheduler.get_session_info()
            logger.info(f"Session Scheduler initialized ✅ — {session_info['session']}: {session_info['description']}")
        except Exception as e:
            logger.warning(f"Session Scheduler init failed (non-fatal): {e}")
        
        # Intelligent Sizer (Phase 4)
        self._sizer = None
        try:
            from risk.intelligent_sizer import IntelligentSizer
            sizer_config = config.get('intelligent_sizing', {})
            self._sizer = IntelligentSizer(sizer_config)
            logger.info("Intelligent Sizer initialized ✅")
        except Exception as e:
            logger.warning(f"Intelligent Sizer init failed (non-fatal): {e}")
        
        # Correlation groups — positions in same group count together
        self._correlation_groups = {
            'gold': ['GOLDm#', 'GOLD#', 'GOLD', 'XAUUSD'],
            'oil': ['OILCash#', 'OILCash', 'OILCASH', 'USOIL', 'BRENT', 'WTI'],
            'crypto': ['BTCUSD#', 'ETHUSD#', 'BTCUSD', 'ETHUSD'],
            'eur': ['EURUSD', 'EURGBP', 'EURJPY'],
        }
        
        # Initialize per-symbol contexts
        self.symbols: Dict[str, SymbolContext] = {}
        self._init_symbol_contexts()
        
        # Strategy selectors (one per symbol for independent scoring)
        self._strategy_selectors: Dict[str, Any] = {}
        self._init_strategy_selectors()
        
        # Loop state
        self._running = False
        self._loop_count = 0
        
        logger.info(f"MultiSymbolOrchestrator initialized: {list(self.symbols.keys())}")
        logger.info(f"Portfolio limits: max_total={self.max_total_positions}, "
                    f"max_per_symbol={self.max_positions_per_symbol}, "
                    f"max_daily_loss={self.max_daily_loss_pct}%")
    
    def _init_symbol_contexts(self):
        """Initialize analysis contexts for all watchlist symbols."""
        watchlist = self.config.get('watchlist', [])
        symbol_configs = self.config.get('symbol_configs', {})
        
        for item in watchlist:
            if isinstance(item, str):
                sym = item
                sym_config = symbol_configs.get(sym, {})
            elif isinstance(item, dict):
                sym = item['symbol']
                sym_config = item
            else:
                continue
            
            ctx = SymbolContext(
                symbol=sym,
                timeframe=sym_config.get('timeframe', self.timeframe),
                max_positions=sym_config.get('max_positions', self.max_positions_per_symbol),
                lot_size_override=sym_config.get('lot_size', None),
                enabled=sym_config.get('enabled', True),
                strategy_overrides=sym_config.get('strategies', {}),
            )
            self.symbols[sym] = ctx
            logger.info(f"  Symbol {sym}: max_pos={ctx.max_positions}, "
                       f"lot_override={ctx.lot_size_override}, enabled={ctx.enabled}")
    
    def _init_strategy_selectors(self):
        """Create independent strategy selectors per symbol."""
        if not self.symbols:
            return
        
        strategy_config = self.config.get("strategy")
        if not isinstance(strategy_config, dict):
            raise ValueError("Multi-symbol configuration requires a strategy object")
        
        from core.strategy_factory import StrategyFactory

        factory = StrategyFactory(logger=logger)
        for sym, ctx in self.symbols.items():
            sym_strategy_config = deepcopy(strategy_config)
            if ctx.strategy_overrides:
                if not isinstance(ctx.strategy_overrides, dict):
                    raise ValueError(f"Strategy overrides for {sym} must be an object")
                sym_strategy_config.update(deepcopy(ctx.strategy_overrides))

            params = sym_strategy_config.setdefault("params", {})
            if not isinstance(params, dict):
                raise ValueError(f"Strategy parameters for {sym} must be an object")
            params["symbol"] = sym
            sym_strategy_config["timeframe"] = ctx.timeframe

            strategy = factory.create(sym_strategy_config)
            selector = _MultiSymbolStrategyAdapter(strategy, sym)
            self._strategy_selectors[sym] = selector
            dynamic_selector = getattr(strategy, "selector", None)
            strategy_count = len(getattr(dynamic_selector, "strategies", {})) or 1
            logger.info(f"  Strategy selector for {sym}: {strategy_count} strategies")
    
    async def run(self):
        """Main multi-symbol trading loop."""
        self._running = True
        
        # Initialize daily tracking
        await self._init_daily_tracking()
        
        logger.info("=" * 60)
        logger.info("MULTI-SYMBOL AUTONOMOUS TRADING LOOP STARTED")
        logger.info(f"Symbols: {list(self.symbols.keys())}")
        logger.info(f"Interval: {self.loop_interval}s")
        logger.info("=" * 60)
        
        while self._running:
            try:
                loop_start = time.time()
                await self._execute_cycle()
                
                elapsed = time.time() - loop_start
                sleep_time = max(0, self.loop_interval - elapsed)
                await asyncio.sleep(sleep_time)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cycle error: {e}", exc_info=True)
                await asyncio.sleep(5)
        
        logger.info("Multi-symbol trading loop stopped")
    
    def stop(self):
        self._running = False
    
    async def _init_daily_tracking(self):
        """Initialize daily P&L tracking."""
        self._daily_date = datetime.now(timezone.utc).date()
        self._daily_start_equity = 0.0
        self._daily_loss_halt = False
        self._daily_tracking_initialized = False
        try:
            acct = self.components.mt5_connector.get_account_info()
            if not isinstance(acct, dict):
                raise RuntimeError("Account information is unavailable")
            start_equity = acct.get("equity")
            if start_equity is None:
                start_equity = acct.get("balance")
            start_equity = float(start_equity)
            if not math.isfinite(start_equity) or start_equity <= 0:
                raise ValueError("Starting account equity must be positive and finite")
            self._daily_start_equity = start_equity
            self._daily_tracking_initialized = True
            self._last_daily_limit_failure = None
            logger.info("Daily tracking initialized: start_equity=$%.2f", start_equity)
            return True
        except Exception as e:
            failure = str(e) or type(e).__name__
            if failure != self._last_daily_limit_failure:
                logger.warning(
                    "Daily tracking unavailable; blocking new trades: %s",
                    failure,
                )
            self._last_daily_limit_failure = failure
            return False
    
    async def _check_daily_limits(self) -> bool:
        """Check if daily loss limit has been hit. Returns True if trading is OK."""
        if self.max_daily_loss_pct <= 0:
            return True
        today = datetime.now(timezone.utc).date()
        
        # Reset on new day
        if today != self._daily_date or not self._daily_tracking_initialized:
            return await self._init_daily_tracking()
        
        if self._daily_loss_halt:
            return False
        
        try:
            acct = self.components.mt5_connector.get_account_info()
            if not isinstance(acct, dict):
                raise RuntimeError("Account information is unavailable")
            current_equity = acct.get("equity")
            if current_equity is None:
                current_equity = acct.get("balance")
            current_equity = float(current_equity)
            if not math.isfinite(current_equity) or current_equity <= 0:
                raise ValueError("Current account equity must be positive and finite")
            if not math.isfinite(self._daily_start_equity) or self._daily_start_equity <= 0:
                raise ValueError("Daily starting equity is unavailable")

            self._last_daily_limit_failure = None
            daily_pnl_pct = (
                (current_equity - self._daily_start_equity)
                / self._daily_start_equity
                * 100
            )
            if daily_pnl_pct <= -self.max_daily_loss_pct:
                self._daily_loss_halt = True
                logger.warning(
                    "DAILY LOSS LIMIT HIT: %.1f%% (limit: -%.1f%%). "
                    "No new trades until tomorrow.",
                    daily_pnl_pct,
                    self.max_daily_loss_pct,
                )
                return False
            return True
        except Exception as e:
            failure = str(e) or type(e).__name__
            if failure != self._last_daily_limit_failure:
                logger.warning(
                    "Daily limit data unavailable; blocking new trades: %s",
                    failure,
                )
            self._last_daily_limit_failure = failure
            return False
    
    async def _execute_cycle(self):
        """Execute one full multi-symbol analysis + trade cycle."""
        try:
            require_legacy_execution()
        except ExecutionModeError as exc:
            logger.warning("Multi-symbol legacy execution paused: %s", exc)
            return

        self._loop_count += 1
        
        # FIRST: Scan for adoptions (must run before signal generation to avoid duplicates)
        await self._scan_adoptions()
        
        # Refresh macro snapshot (auto-caches, only hits APIs every 30 min)
        if self._macro:
            try:
                self._current_macro_snapshot = self._macro.get_snapshot()
            except Exception as e:
                logger.debug(f"Macro refresh error (non-fatal): {e}")
        
        # Check daily limits first
        if not await self._check_daily_limits():
            # Still manage existing positions even when halted
            await self._manage_all_positions()
            await self._evaluate_all_exits()
            if self._loop_count % 20 == 0:
                logger.info(f"[Cycle {self._loop_count}] Daily loss halt active — managing positions only")
            return

        if self._execution_halt_reason:
            await self._manage_all_positions()
            await self._evaluate_all_exits()
            if self._loop_count % 20 == 0:
                logger.critical(
                    "[Cycle %s] Trading halted: %s",
                    self._loop_count,
                    self._execution_halt_reason,
                )
            return
        
        # Phase 1: Scan all symbols
        all_signals: List[ScoredSignal] = []
        
        for sym, ctx in self.symbols.items():
            if not ctx.enabled:
                continue
            
            # Skip if on cooldown
            if time.time() < ctx.cooldown_until:
                continue
            
            # Skip if symbol had a recent failed order (extended 30-min cooldown)
            if hasattr(self.components, 'trade_manager') and self.components.trade_manager:
                remaining = self.components.trade_manager.get_failed_symbol_remaining(sym)
                if remaining > 0:
                    if self._loop_count % 40 == 0:  # Log every ~10 min
                        logger.info(f"{sym}: Failed order cooldown — {remaining:.0f}s remaining")
                    continue
            
            try:
                signal = await self._analyze_symbol(sym, ctx)
                if signal:
                    all_signals.append(signal)
            except Exception as e:
                logger.error(f"Analysis error for {sym}: {e}")
        
        # Phase 2: Rank signals
        all_signals.sort(key=lambda s: s.score, reverse=True)
        
        if all_signals:
            logger.info(f"[Cycle {self._loop_count}] Signals: "
                       + ", ".join(f"{s.symbol}({s.score:.2f})" for s in all_signals[:5]))
        
        # Phase 3: Execute top signals within portfolio limits
        for scored in all_signals:
            if await self._can_open_position(scored.symbol):
                executed = await self._execute_signal(scored)
                if executed:
                    # Set cooldown for this symbol
                    self.symbols[scored.symbol].cooldown_until = (
                        time.time() + self.signal_cooldown_seconds
                    )
                    logger.info(f"Cooldown set for {scored.symbol}: {self.signal_cooldown_seconds}s")
        
        # Phase 4: Manage existing positions
        await self._manage_all_positions()
        
        # Phase 5: Evaluate exits
        await self._evaluate_all_exits()
        
        # Phase 6: Re-scan adoptions (catch any that appeared during this cycle)
        await self._scan_adoptions()
        
        # Periodic logging
        if self._loop_count % 20 == 0:  # Every ~5 minutes at 15s interval
            await self._log_portfolio_status()
    
    async def _analyze_symbol(self, sym: str, ctx: SymbolContext) -> Optional[ScoredSignal]:
        """Run full analysis pipeline for one symbol."""
        
        # Fetch market data
        try:
            data = self._fetch_symbol_data(sym, ctx)
        except Exception as e:
            logger.debug(f"No data for {sym}: {e}")
            return None
        
        if data is None or len(data) < 50:
            return None
        
        # Check data freshness via bar timestamps
        # If the latest bar time hasn't changed across cycles, market is closed
        try:
            if len(data) >= 2:
                last_bar_time = data['time'].iloc[-1] if 'time' in data.columns else data.index[-1]
                last_bar_key = f'_last_bar_time_{sym}'
                prev_bar_time = getattr(self, last_bar_key, None)
                setattr(self, last_bar_key, last_bar_time)
                
                if prev_bar_time is not None and last_bar_time == prev_bar_time:
                    stale_key = f'_stale_count_{sym}'
                    stale_count = getattr(self, stale_key, 0) + 1
                    setattr(self, stale_key, stale_count)
                    
                    # After 4 consecutive cycles with same latest bar (60s at 15s)
                    # This means no new M5 candle has formed — market is closed
                    if stale_count >= 4:
                        if stale_count == 4 or stale_count % 120 == 0:
                            logger.info(f"{sym}: Market stale (no new bar for {stale_count * self.loop_interval}s) — skipping signals")
                        # Still update market data for position management
                        ctx.market_data = data
                        return None
                else:
                    setattr(self, f'_stale_count_{sym}', 0)
        except Exception as e:
            logger.debug(f"{sym}: Bar freshness check error (non-fatal): {e}")
        
        ctx.market_data = data
        
        selector = self._strategy_selectors.get(sym)
        if selector is None:
            logger.error("%s: No strategy selector was initialized", sym)
            return None

        # Calculate indicators
        indicators = await self._calculate_indicators(data, selector)
        ctx.indicators = indicators
        
        # Update regime (every 5 min per symbol)
        now = time.time()
        if now - ctx.last_regime_update > 300:
            ctx.last_regime_update = now
            regime_classifier = getattr(self.components, "regime_classifier", None)
            if regime_classifier is not None:
                try:
                    ctx.regime = regime_classifier.classify(
                    indicators=indicators, market_data=data
                    )
                except Exception as exc:
                    logger.debug("%s: Regime classification failed: %s", sym, exc)
                    ctx.regime = 'unknown'
        
        # Generate signal via this symbol's strategy selector
        signal = selector.generate_signal(
            data=data, indicators=indicators, regime=ctx.regime
        )
        
        if signal is None:
            self._publish_legacy_context(sym, ctx, data, indicators, None)
            return None
        if not isinstance(signal, dict):
            logger.error("%s: Strategy selector returned an invalid signal", sym)
            return None
        
        # Ensure symbol is set correctly
        signal['symbol'] = sym
        raw_direction = signal.get('direction') or signal.get('side')
        if hasattr(raw_direction, 'value'):
            raw_direction = raw_direction.value
        direction = str(raw_direction or "").strip().lower()
        if direction in {"buy", "long"}:
            signal["direction"] = "buy"
        elif direction in {"sell", "short"}:
            signal["direction"] = "sell"
        else:
            logger.error("%s: Strategy signal has no valid direction", sym)
            return None
        
        # Apply confluence filter
        entry_confluence = getattr(self.components, "entry_confluence", None)
        if entry_confluence:
            try:
                confluence = entry_confluence.analyze(
                    signal=signal, data=data, indicators=indicators
                )
                
                if confluence['should_reject']:
                    logger.debug(f"{sym}: Signal rejected by confluence: {confluence['reason']}")
                    self._publish_legacy_context(sym, ctx, data, indicators, signal, rejection=confluence['reason'])
                    return None
                
                signal['confidence'] *= confluence['confidence_multiplier']
                signal['confluence_score'] = confluence['score']
            except Exception as e:
                logger.debug(f"{sym}: Confluence filter error: {e}")
        
        # Calculate cross-symbol ranking score
        strategy_score = signal.get('strategy_score', 0.5)
        confidence = signal.get('confidence', 0.5)
        confluence_score = signal.get('confluence_score', 50) / 100.0
        
        # Penalize symbols with consecutive losses
        loss_penalty = max(0.5, 1.0 - (ctx.consecutive_losses * 0.15))
        
        # Apply macro bias (Phase 2)
        macro_multiplier = 1.0
        if self._current_macro_snapshot:
            macro = self._current_macro_snapshot
            direction = signal.get('direction', '')
            bias = self._get_macro_bias_for_symbol(sym, macro)
            
            # If signal aligns with macro bias, boost score
            # If signal opposes macro bias, penalize score
            if direction == 'buy' and bias > 0:
                macro_multiplier = 1.0 + (bias * 0.3)  # Up to +30% boost
            elif direction == 'sell' and bias < 0:
                macro_multiplier = 1.0 + (abs(bias) * 0.3)
            elif direction == 'buy' and bias < -0.3:
                macro_multiplier = 1.0 - (abs(bias) * 0.4)  # Up to -40% penalty
            elif direction == 'sell' and bias > 0.3:
                macro_multiplier = 1.0 - (bias * 0.4)
            
            # In crisis mode, heavily penalize counter-trend trades
            if macro.regime == 'crisis':
                if (direction == 'sell' and sym in ['GOLDm#', 'GOLD#']):
                    macro_multiplier *= 0.3  # Don't short gold in crisis
                elif (direction == 'buy' and sym in ['BTCUSD#']):
                    macro_multiplier *= 0.5  # Careful with BTC in crisis
            
            signal['macro_bias'] = bias
            signal['macro_regime'] = macro.regime
        
        # Apply session multiplier (Phase 3)
        session_multiplier = 1.0
        if self._session_scheduler:
            session_multiplier = self._session_scheduler.get_symbol_multiplier(sym)
            signal['session'] = self._session_scheduler.get_current_session()
            signal['session_multiplier'] = session_multiplier
            
            # If session multiplier is 0, don't trade this symbol at all
            if session_multiplier <= 0:
                logger.debug(f"{sym}: Session {signal['session']} — symbol disabled")
                self._publish_legacy_context(sym, ctx, data, indicators, signal, rejection="session multiplier is zero")
                return None
        
        combined_score = (
            strategy_score * 0.25 + 
            confidence * 0.25 + 
            confluence_score * 0.35 +
            max(0, macro_multiplier - 0.7) * 0.15  # Macro contributes 15%
        ) * loss_penalty * macro_multiplier * session_multiplier

        self._publish_legacy_context(sym, ctx, data, indicators, signal, score=combined_score)
        self._notify_signal(signal, ctx, indicators)
        
        return ScoredSignal(
            signal=signal,
            symbol=sym,
            score=combined_score,
            regime=ctx.regime,
            strategy=signal.get('strategy', 'unknown'),
            timestamp=time.time()
        )

    def _notify_signal(
        self,
        signal: Dict[str, Any],
        ctx: SymbolContext,
        indicators: Dict[str, Any],
    ) -> None:
        discord_config = self.config.get("discord", {})
        if not isinstance(discord_config, dict):
            return
        if not discord_config.get("enabled", True) or not discord_config.get(
            "alert_on_signals", True
        ):
            return

        try:
            from integrations.discord_notifier import (
                NotificationChannel,
                get_discord_notifier,
            )

            notifier = get_discord_notifier()
            if (
                not notifier.enabled
                or not notifier.webhooks.get(NotificationChannel.SIGNALS)
            ):
                return

            now = time.time()
            if (
                self.signal_cooldown_seconds > 0
                and now - ctx.last_signal_time < self.signal_cooldown_seconds
            ):
                return

            confidence_value = signal.get("confidence")
            confidence = (
                0.5 if confidence_value is None else float(confidence_value)
            )
            if not math.isfinite(confidence):
                logger.error(
                    "%s: Signal confidence is invalid; Discord notification skipped",
                    ctx.symbol,
                )
                return

            quality = signal.get("confluence_quality")
            if hasattr(quality, "value"):
                quality = quality.value
            if quality is not None:
                quality = str(quality)

            confluence_reasons = signal.get("confluence_reasons")
            if not isinstance(confluence_reasons, list):
                confluence_reasons = None

            notification_indicators = {}
            for name, value in indicators.items():
                try:
                    numeric_value = float(value)
                except (TypeError, ValueError, OverflowError):
                    continue
                if math.isfinite(numeric_value):
                    notification_indicators[str(name).upper()] = numeric_value
                    if len(notification_indicators) == 4:
                        break

            queued = notifier.notify_signal_quality(
                symbol=ctx.symbol,
                direction=str(signal.get("direction", "")).upper(),
                confidence=confidence,
                strategy=str(signal.get("strategy") or "unknown"),
                indicators=notification_indicators,
                confluence_quality=quality,
                confluence_score=(
                    signal.get("confluence_score")
                    if quality is not None
                    else None
                ),
                confluence_reasons=(
                    confluence_reasons if quality is not None else None
                ),
                entry_price=signal.get("price") or signal.get("entry_price"),
                stop_loss=signal.get("stop_loss"),
                take_profit=signal.get("take_profit"),
                risk_reward=signal.get("risk_reward"),
                timeframe=str(ctx.timeframe),
            )
            if not queued:
                logger.warning(
                    "%s: Discord signal notification could not be queued",
                    ctx.symbol,
                )
                return
            ctx.last_signal_time = now
        except Exception:
            logger.exception(
                "%s: Failed to queue Discord signal notification",
                ctx.symbol,
            )

    @staticmethod
    def _publish_legacy_context(sym, ctx, data, indicators, signal, score=None, rejection=""):
        try:
            from legacy_bridge import publish_legacy_context

            bar = data.iloc[-1].to_dict() if hasattr(data, "iloc") and len(data) else {}
            if bar and "time" not in bar and hasattr(data, "index"):
                bar["time"] = str(data.index[-1])
            publish_legacy_context(
                sym,
                str(ctx.timeframe),
                bar=bar,
                indicators=indicators,
                signal=signal,
                regime=ctx.regime,
                strategy=(signal or {}).get("strategy", "unknown") if isinstance(signal, dict) else "unknown",
                score=score,
                rejection=rejection,
            )
        except Exception:
            logger.exception("%s: Failed to publish Legacy analysis for the agent", sym)

    def _fetch_symbol_data(self, symbol: str, ctx: SymbolContext):
        """Fetch MT5 rates and normalize them using the shared Legacy data layer."""
        timeframe = _resolve_mt5_timeframe(ctx.timeframe)

        rates = self.components.mt5_connector.get_rates(
            symbol=symbol,
            timeframe=timeframe,
            count=200,
        )
        if rates is None or len(rates) == 0:
            return None
        return self.components.data_layer.normalize_rates(rates, symbol=symbol)
    
    async def _calculate_indicators(
        self,
        data,
        selector: Optional[_MultiSymbolStrategyAdapter] = None,
    ) -> Dict[str, Any]:
        """Calculate indicators and add the columns required by each strategy."""
        if data is None or data.empty:
            return {}

        from indicators.adx import calculate_adx
        from indicators.atr import calculate_atr
        from indicators.bollinger import calculate_bollinger_bands
        from indicators.macd import calculate_macd
        from indicators.rsi import calculate_rsi

        if "volume" not in data.columns and "tick_volume" in data.columns:
            data["volume"] = data["tick_volume"]

        strategy = getattr(selector, "strategy", selector)
        dynamic_selector = getattr(strategy, "selector", None)
        children = getattr(dynamic_selector, "strategies", {})
        strategies = list(children.values()) if isinstance(children, dict) else [strategy]

        def add_period(periods, value):
            try:
                period = int(value)
            except (TypeError, ValueError):
                return
            if period > 0:
                periods.add(period)

        sma_periods = {20, 50}
        ema_periods = {5, 10, 12, 20, 26}
        rsi_periods = {14}
        adx_periods = {14}
        atr_periods = {14}
        lookback_periods = {20}
        bollinger_specs = {(20, 2.0)}
        macd_specs = []

        for child in strategies:
            for attribute in ("short_window", "long_window", "fast_ma", "slow_ma"):
                value = getattr(child, attribute, None)
                if value is not None:
                    add_period(sma_periods, value)
            for attribute in (
                "fast_period",
                "slow_period",
                "fast_ema",
                "slow_ema",
                "fast_ma",
                "slow_ma",
            ):
                value = getattr(child, attribute, None)
                if value is not None:
                    add_period(ema_periods, value)

            add_period(rsi_periods, getattr(child, "rsi_period", None))
            add_period(adx_periods, getattr(child, "adx_period", None))
            add_period(atr_periods, getattr(child, "atr_period", None))
            add_period(lookback_periods, getattr(child, "lookback_period", None))

            bb_period = getattr(child, "ma_period", None)
            bb_std = getattr(child, "bb_std", None)
            if bb_period is not None and bb_std is not None:
                try:
                    bollinger_specs.add((int(bb_period), float(bb_std)))
                except (TypeError, ValueError):
                    pass

        configured_indicators = self.config.get("indicators", [])
        if isinstance(configured_indicators, dict):
            configured_indicators = [
                {"type": indicator_type, "params": params}
                for indicator_type, params in configured_indicators.items()
            ]
        if not isinstance(configured_indicators, list):
            configured_indicators = []

        for indicator_config in configured_indicators:
            if not isinstance(indicator_config, dict):
                continue
            indicator_type = str(indicator_config.get("type", "")).lower()
            params = indicator_config.get("params", {})
            if not isinstance(params, dict):
                continue
            if indicator_type == "rsi":
                add_period(rsi_periods, params.get("period", 14))
            elif indicator_type == "adx":
                add_period(adx_periods, params.get("period", 14))
            elif indicator_type == "atr":
                add_period(atr_periods, params.get("period", 14))
            elif indicator_type in {"bollinger", "bollingerbands"}:
                try:
                    bollinger_specs.add(
                        (int(params.get("period", 20)), float(params.get("std_dev", 2.0)))
                    )
                except (TypeError, ValueError):
                    pass
            elif indicator_type == "macd":
                try:
                    spec = (
                        int(params.get("fast_period", 12)),
                        int(params.get("slow_period", 26)),
                        int(params.get("signal_period", 9)),
                    )
                except (TypeError, ValueError):
                    continue
                if all(period > 0 for period in spec) and spec not in macd_specs:
                    macd_specs.append(spec)

        for period in sorted(sma_periods):
            data[f"sma_{period}"] = data["close"].rolling(window=period).mean()
        for period in sorted(ema_periods):
            data[f"ema_{period}"] = data["close"].ewm(span=period, adjust=False).mean()
        for period in sorted(lookback_periods):
            data[f"high_{period}"] = data["high"].rolling(window=period).max()
            data[f"low_{period}"] = data["low"].rolling(window=period).min()
            if "volume" in data.columns:
                data[f"volume_avg_{period}"] = data["volume"].rolling(window=period).mean()

        for period in sorted(rsi_periods):
            rsi = calculate_rsi(data, period=period)
            column = "rsi" if period == 14 else f"rsi_{period}"
            data[column] = rsi
            data[f"rsi_{period}"] = rsi
        for period in sorted(adx_periods):
            adx = calculate_adx(data, period=period)
            column = "adx" if period == 14 else f"adx_{period}"
            data[column] = adx
            data[f"adx_{period}"] = adx
        for period in sorted(atr_periods):
            atr = calculate_atr(data, period=period)
            column = "atr" if period == 14 else f"atr_{period}"
            data[column] = atr
            data[f"atr_{period}"] = atr

        if not macd_specs:
            macd_specs.append((12, 26, 9))
        for index, (fast_period, slow_period, signal_period) in enumerate(macd_specs):
            macd, macd_signal, macd_histogram = calculate_macd(
                data,
                fast=fast_period,
                slow=slow_period,
                signal_period=signal_period,
            )
            if index == 0:
                data["macd"] = macd
                data["macd_signal"] = macd_signal
                data["signal"] = macd_signal
                data["macd_histogram"] = macd_histogram

        for period, std_dev in sorted(bollinger_specs):
            upper, middle, lower = calculate_bollinger_bands(
                data,
                period=period,
                std_dev=std_dev,
            )
            suffix = f"{period}_{std_dev}"
            data[f"bb_upper_{suffix}"] = upper
            data[f"bb_middle_{period}"] = middle
            data[f"bb_lower_{suffix}"] = lower
            if period == 20 and std_dev == 2.0:
                data["bb_upper"] = upper
                data["bb_middle"] = middle
                data["bb_lower"] = lower

        def latest(column):
            return float(data[column].iloc[-1])

        indicators = {
            "RSI": latest("rsi"),
            "rsi": latest("rsi"),
            "ADX": latest("adx"),
            "adx": latest("adx"),
            "ATR": latest("atr"),
            "atr": latest("atr"),
            "MACD": (
                latest("macd"),
                latest("macd_signal"),
                latest("macd_histogram"),
            ),
            "macd": latest("macd"),
            "BB": (
                latest("bb_upper"),
                latest("bb_middle"),
                latest("bb_lower"),
            ),
            "bb_upper": latest("bb_upper"),
            "bb_middle": latest("bb_middle"),
            "bb_lower": latest("bb_lower"),
        }
        for period in sorted(sma_periods):
            indicators[f"SMA_{period}"] = latest(f"sma_{period}")
        for period in sorted(ema_periods):
            indicators[f"EMA_{period}"] = latest(f"ema_{period}")

        return indicators
    
    async def _can_open_position(self, symbol: str) -> bool:
        """Check if portfolio risk budget allows a new position."""
        try:
            positions = self.components.trade_manager.get_all_positions()
            total_open = len(positions)
            
            # Total position limit
            if total_open >= self.max_total_positions:
                logger.debug(f"Portfolio full: {total_open}/{self.max_total_positions}")
                return False
            
            # Per-symbol limit
            sym_positions = sum(
                1 for p in positions
                if self._symbol_key(p.symbol) == self._symbol_key(symbol)
            )
            sym_ctx = self._get_symbol_context(symbol)
            max_per_sym = sym_ctx.max_positions if sym_ctx else self.max_positions_per_symbol
            
            if sym_positions >= max_per_sym:
                logger.debug(f"{symbol} full: {sym_positions}/{max_per_sym}")
                return False
            
            # Correlation group limit
            group = self._get_correlation_group(symbol)
            if group:
                group_positions = sum(
                    1 for p in positions 
                    if self._get_correlation_group(p.symbol) == group
                )
                if group_positions >= self.max_correlated_positions:
                    logger.debug(f"Correlation group '{group}' full: {group_positions}/{self.max_correlated_positions}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Position check error: {e}")
            return False
    
    def _get_correlation_group(self, symbol: str) -> Optional[str]:
        """Get the correlation group a symbol belongs to."""
        key = self._symbol_key(symbol)
        for group_name, symbols in self._correlation_groups.items():
            if key in {self._symbol_key(candidate) for candidate in symbols}:
                return group_name
        return None

    @staticmethod
    def _symbol_key(symbol: str) -> str:
        normalized = "".join(char for char in str(symbol).upper() if char.isalnum())
        if normalized.startswith(("GOLD", "XAU")):
            return "GOLD"
        if normalized.startswith("BTCUSD"):
            return "BTCUSD"
        if normalized.startswith("ETHUSD"):
            return "ETHUSD"
        if normalized in {"WTI", "OILCASH", "USOIL", "BRENT"}:
            return "OIL"
        return normalized

    def _get_symbol_context(self, symbol: str) -> Optional[SymbolContext]:
        exact = self.symbols.get(symbol)
        if exact:
            return exact
        key = self._symbol_key(symbol)
        return next((ctx for name, ctx in self.symbols.items() if self._symbol_key(name) == key), None)
    
    def _get_macro_bias_for_symbol(self, symbol: str, macro) -> float:
        """Map a trading symbol to its macro directional bias."""
        key = self._symbol_key(symbol)
        if key == "GOLD":
            return macro.gold_bias
        elif key == "OIL":
            return macro.oil_bias
        elif key in ("BTCUSD", "ETHUSD"):
            return macro.crypto_bias
        # EUR group
        elif symbol in ('EURUSD', 'EURGBP', 'EURJPY'):
            return macro.forex_eur_bias
        # Unknown — no bias
        return 0.0

    @staticmethod
    def _normalize_risk_capped_lot_size(
        candidate_size: float,
        risk_approved_size: float,
        symbol_info: Optional[Dict[str, Any]],
    ) -> tuple[float, str]:
        if not isinstance(symbol_info, dict):
            return 0.0, "broker volume specifications are unavailable"

        try:
            candidate = float(candidate_size)
            approved = float(risk_approved_size)
            min_lot = float(symbol_info.get("volume_min") or 0.0)
            volume_step = float(symbol_info.get("volume_step") or min_lot)
            max_lot = float(symbol_info.get("volume_max") or approved)
        except (TypeError, ValueError):
            return 0.0, "broker volume specifications are invalid"

        values = (candidate, approved, min_lot, volume_step, max_lot)
        if not all(math.isfinite(value) for value in values):
            return 0.0, "position size or broker volume specifications are not finite"
        if candidate <= 0 or approved <= 0:
            return 0.0, "position size is not positive"
        if min_lot <= 0 or volume_step <= 0 or max_lot <= 0:
            return 0.0, "broker minimum, step, and maximum volumes must be positive"

        volume = min(candidate, approved, max_lot)
        volume = math.floor((volume + 1e-12) / volume_step) * volume_step
        volume = round(volume, 8)
        if volume + 1e-12 < min_lot:
            return 0.0, (
                f"risk-adjusted volume is below broker minimum {min_lot:g}"
            )
        return volume, ""
    
    async def _execute_signal(self, scored: ScoredSignal) -> bool:
        """Execute a scored signal with portfolio-aware risk sizing."""
        signal = scored.signal
        
        try:
            # Risk evaluation
            risk_result = self.components.risk_evaluator.evaluate(signal)
            
            if not isinstance(risk_result, dict):
                logger.error("%s: Risk evaluator returned an invalid result", scored.symbol)
                return False

            if not risk_result.get('approved'):
                logger.info(
                    "%s: Risk rejected: %s",
                    scored.symbol,
                    risk_result.get('reason', 'no reason provided'),
                )
                return False

            try:
                risk_approved_size = float(risk_result['lot_size'])
            except (KeyError, TypeError, ValueError):
                logger.error(
                    "%s: Risk evaluator returned an invalid approved lot size",
                    scored.symbol,
                )
                return False
            if not math.isfinite(risk_approved_size) or risk_approved_size <= 0:
                logger.error(
                    "%s: Risk evaluator approved a non-positive or invalid lot size",
                    scored.symbol,
                )
                return False
            try:
                session_multiplier = float(signal.get('session_multiplier', 1.0))
            except (TypeError, ValueError):
                logger.error("%s: Invalid session size multiplier", scored.symbol)
                return False
            if not math.isfinite(session_multiplier) or session_multiplier < 0:
                logger.error("%s: Invalid session size multiplier", scored.symbol)
                return False
            if session_multiplier == 0:
                logger.info("%s: Session sizing multiplier is zero; skipping trade", scored.symbol)
                return False

            lot_size = risk_approved_size
            account_info = None
            account_balance = None
            account_equity = None
            drawdown_manager = getattr(self.components, "adaptive_drawdown_manager", None)
            if self._sizer or drawdown_manager:
                try:
                    account_info = self.components.mt5_connector.get_account_info()
                    if not isinstance(account_info, dict):
                        raise ValueError("account information is unavailable")
                    account_balance = float(account_info.get("balance") or 0.0)
                    account_equity = float(account_info.get("equity") or 0.0)
                    if (
                        not math.isfinite(account_balance)
                        or not math.isfinite(account_equity)
                        or account_balance <= 0
                        or account_equity <= 0
                    ):
                        raise ValueError("account balance and equity must be positive")
                except Exception:
                    logger.exception(
                        "%s: Cannot retrieve valid account equity for risk sizing",
                        scored.symbol,
                    )
                    return False
            
            # Intelligent sizing (Phase 4) — replaces simple lot_size_override
            if self._sizer:
                sym_ctx = self.symbols.get(scored.symbol)
                atr = sym_ctx.indicators.get('ATR', 0) if sym_ctx else 0
                macro_conf = (
                    self._current_macro_snapshot.confidence
                    if self._current_macro_snapshot
                    else 0.5
                )
                try:
                    candidate_size = self._sizer.calculate_lot_size(
                        symbol=scored.symbol,
                        account_balance=account_equity,
                        atr=atr,
                        signal_confidence=signal.get('confidence', 0.5),
                        session_multiplier=session_multiplier,
                        macro_confidence=macro_conf,
                        leverage=account_info.get('leverage', 1000),
                    )
                    candidate_size = float(candidate_size)
                    if not math.isfinite(candidate_size) or candidate_size <= 0:
                        logger.error(
                            "%s: Intelligent sizer returned an invalid lot size",
                            scored.symbol,
                        )
                        return False
                    lot_size = min(lot_size, candidate_size)
                except Exception:
                    logger.exception(
                        "%s: Intelligent sizing failed; retaining the risk-approved size",
                        scored.symbol,
                    )
                    sym_ctx = self.symbols.get(scored.symbol)
                    if sym_ctx and sym_ctx.lot_size_override is not None:
                        try:
                            override = float(sym_ctx.lot_size_override)
                        except (TypeError, ValueError):
                            logger.error(
                                "%s: Invalid per-symbol lot size override",
                                scored.symbol,
                            )
                            return False
                        if not math.isfinite(override) or override < 0:
                            logger.error(
                                "%s: Invalid per-symbol lot size override",
                                scored.symbol,
                            )
                            return False
                        if override > 0:
                            lot_size = min(lot_size, override)
                    lot_size = min(lot_size, lot_size * session_multiplier)
            else:
                # Fallback: per-symbol lot size override
                sym_ctx = self.symbols.get(scored.symbol)
                if sym_ctx and sym_ctx.lot_size_override is not None:
                    try:
                        override = float(sym_ctx.lot_size_override)
                    except (TypeError, ValueError):
                        logger.error("%s: Invalid per-symbol lot size override", scored.symbol)
                        return False
                    if not math.isfinite(override) or override < 0:
                        logger.error("%s: Invalid per-symbol lot size override", scored.symbol)
                        return False
                    if override > 0:
                        lot_size = min(lot_size, override)
                lot_size = min(lot_size, lot_size * session_multiplier)
            
            # Adaptive drawdown adjustment (always applies as final safety)
            if drawdown_manager:
                try:
                    dd_settings = drawdown_manager.update(
                        account_balance, account_equity
                    )
                    if not dd_settings.allow_new_trades:
                        logger.info(
                            "%s: Adaptive drawdown manager blocked new trades",
                            scored.symbol,
                        )
                        return False
                    dd_multiplier = float(dd_settings.position_size_multiplier)
                    if not math.isfinite(dd_multiplier) or dd_multiplier < 0:
                        logger.error(
                            "%s: Adaptive drawdown manager returned an invalid size multiplier",
                            scored.symbol,
                        )
                        return False
                    lot_size = min(lot_size, lot_size * dd_multiplier)
                except Exception:
                    logger.exception(
                        "%s: Adaptive drawdown sizing failed; rejecting the trade",
                        scored.symbol,
                    )
                    return False

            try:
                symbol_info = self.components.mt5_connector.get_symbol_info(scored.symbol)
            except Exception:
                logger.exception(
                    "%s: Cannot retrieve broker volume specifications",
                    scored.symbol,
                )
                return False
            lot_size, sizing_error = self._normalize_risk_capped_lot_size(
                lot_size, risk_approved_size, symbol_info
            )
            if lot_size <= 0:
                logger.info("%s: Risk sizing rejected trade: %s", scored.symbol, sizing_error)
                return False
            
            logger.info(f"🎯 EXECUTING: {signal.get('direction','?').upper()} {scored.symbol} "
                       f"| lots={lot_size:.2f} | score={scored.score:.2f} "
                       f"| strategy={scored.strategy} | regime={scored.regime}")
            
            # Execute
            result = self.components.execution_engine.execute(
                signal=signal, lot_size=lot_size
            )
            
            if result['success']:
                logger.info(f"✅ Order filled: Ticket #{result['ticket']} | "
                           f"Price: {result['price']} | Volume: {result['volume']}")
                
                # Register trade
                registered = self.components.trade_manager.register_trade(
                    ticket=result['ticket'], signal=signal, result=result
                )
                if registered is False:
                    self._execution_halt_reason = (
                        f"Filled position {result['ticket']} could not be tracked"
                    )
                    logger.critical(
                        "%s: %s; halting new trades",
                        scored.symbol,
                        self._execution_halt_reason,
                    )
                    return False
                
                # Apply initial SL/TP
                await self._apply_sltp(result['ticket'], signal, scored.symbol)
                
                return True
            else:
                logger.error(f"❌ Order failed for {scored.symbol}: {result.get('error')}")
                self.components.trade_manager.record_failed_order(scored.symbol)
                return False
                
        except Exception as e:
            logger.error(f"Execution error for {scored.symbol}: {e}")
            return False
    
    async def _apply_sltp(self, ticket: int, signal: Dict[str, Any], symbol: str):
        """Apply initial SL/TP to a new position."""
        try:
            manager = self.components.dynamic_sltp_manager
            if not manager:
                return
            positions = self.components.position_manager.monitor_positions()
            position = next((p for p in positions if p.ticket == ticket), None)
            if not position:
                logger.warning("Cannot apply initial SL/TP: position %s was not found", ticket)
                return
            atr = await self._position_atr(position)
            if atr is None:
                logger.warning("Cannot apply initial SL/TP: ATR unavailable for %s", ticket)
                return
            account = self.components.connector.get_account_info() or {}
            balance = float(account.get('balance') or 0.0)
            equity = float(account.get('equity') or balance)
            state = manager.positions_managed
            initial_balance = float(state.setdefault('initial_balance', balance) or balance)
            peak_balance = max(balance, float(state.get('peak_balance', balance) or balance))
            state['peak_balance'] = peak_balance
            drawdown_pct = ((peak_balance - balance) / peak_balance * 100) if peak_balance else 0.0
            result = manager.calculate_initial_sltp(
                ticket=ticket,
                direction=signal['direction'],
                entry_price=position.open_price,
                atr=atr,
                balance=balance,
                equity=equity,
                drawdown_pct=drawdown_pct,
                initial_balance=initial_balance,
                symbol_info=self.components.connector.get_symbol_info(symbol),
            )
            sl = position.stop_loss or result['sl']
            tp = position.take_profit or result['tp']
            if (not position.stop_loss or not position.take_profit) and self.components.position_lifecycle.modify_position(ticket, sl=sl, tp=tp):
                logger.info("Initial dynamic SL/TP applied to %s", ticket)
        except Exception as e:
            logger.error(f"SLTP application error: {e}")
    
    async def _manage_all_positions(self):
        """Manage every broker position, including positions not opened by Cthulu."""
        manager = self.components.dynamic_sltp_manager
        if not manager:
            return
        positions = self.components.position_manager.monitor_positions()
        account = self.components.connector.get_account_info() or {}
        balance = float(account.get('balance') or 0.0)
        equity = float(account.get('equity') or balance)
        state = manager.positions_managed
        initial_balance = float(state.setdefault('initial_balance', balance) or balance)
        peak_balance = max(balance, float(state.get('peak_balance', balance) or balance))
        state['peak_balance'] = peak_balance
        drawdown_pct = ((peak_balance - balance) / peak_balance * 100) if peak_balance else 0.0

        for position in positions:
            try:
                atr = await self._position_atr(position)
                if atr is None:
                    logger.debug("Dynamic SL/TP skipped for %s: ATR unavailable", position.ticket)
                    continue
                current_price = float(position.current_price or 0.0)
                if current_price <= 0:
                    continue
                symbol_info = self.components.connector.get_symbol_info(position.symbol)
                if not symbol_info:
                    logger.warning("Dynamic SL/TP skipped for %s: symbol info unavailable", position.ticket)
                    continue
                side = position.side.upper()
                current_sl = position.stop_loss or None
                current_tp = position.take_profit or None
                if current_sl is None or current_tp is None:
                    initial = manager.calculate_initial_sltp(
                        ticket=position.ticket,
                        direction=side,
                        entry_price=position.open_price,
                        atr=atr,
                        balance=balance,
                        equity=equity,
                        drawdown_pct=drawdown_pct,
                        initial_balance=initial_balance,
                        symbol_info=symbol_info,
                    )
                    point = float(symbol_info.get('point') or 0.0)
                    min_distance = max(
                        point,
                        point * float(symbol_info.get('trade_stops_level') or 0),
                    )
                    new_sl, new_tp = current_sl, current_tp
                    if current_sl is None:
                        candidate = float(initial['sl'])
                        valid = (
                            candidate < current_price - min_distance
                            if side == 'BUY'
                            else candidate > current_price + min_distance
                        )
                        if valid:
                            new_sl = candidate
                    if current_tp is None:
                        candidate = float(initial['tp'])
                        valid = (
                            candidate > current_price + min_distance
                            if side == 'BUY'
                            else candidate < current_price - min_distance
                        )
                        if valid:
                            new_tp = candidate
                    if new_sl != current_sl or new_tp != current_tp:
                        self.components.position_lifecycle.modify_position(
                            position.ticket, sl=new_sl, tp=new_tp
                        )
                        continue
                    if current_sl is None:
                        logger.warning("Dynamic SL/TP could not find a valid initial stop for %s", position.ticket)
                        continue

                update = manager.update_position_sltp(
                    ticket=position.ticket,
                    entry_price=position.open_price,
                    current_price=current_price,
                    side=side,
                    current_sl=current_sl,
                    current_tp=current_tp,
                    atr=atr,
                    balance=balance,
                    equity=equity,
                    drawdown_pct=drawdown_pct,
                    initial_balance=initial_balance,
                    symbol_info=symbol_info,
                )
                if not update.get('update_sl') or update.get('new_sl') is None:
                    continue
                new_sl = float(update['new_sl'])
                improves = current_sl is None or (
                    new_sl > current_sl if side == 'BUY' else new_sl < current_sl
                )
                min_distance = max(
                    float(symbol_info.get('point') or 0.0),
                    float(symbol_info.get('point') or 0.0) * float(symbol_info.get('trade_stops_level') or 0),
                )
                valid = new_sl < current_price - min_distance if side == 'BUY' else new_sl > current_price + min_distance
                if improves and valid:
                    self.components.position_lifecycle.modify_position(
                        position.ticket, sl=new_sl, tp=current_tp
                    )
            except Exception as e:
                logger.exception("Dynamic SL/TP failed for position %s: %s", position.ticket, e)

    async def _position_atr(self, position) -> Optional[float]:
        ctx = self._get_symbol_context(position.symbol)
        if ctx and ctx.indicators:
            try:
                atr = float(ctx.indicators.get('ATR') or ctx.indicators.get('atr') or 0.0)
                if atr > 0:
                    return atr
            except (TypeError, ValueError):
                pass

        timeframe = _resolve_mt5_timeframe(self.timeframe)
        rates = self.components.connector.get_rates(position.symbol, timeframe, 200)
        if not rates:
            return None
        data = self.components.data_layer.normalize_rates(rates, symbol=position.symbol)
        from cthulu.indicators.atr import calculate_atr

        try:
            atr = float(calculate_atr(data, period=14).iloc[-1])
        except (TypeError, ValueError):
            return None
        return atr if atr > 0 else None
    
    async def _evaluate_all_exits(self):
        """Evaluate exit conditions for ALL positions."""
        try:
            positions = self.components.trade_manager.get_all_positions()
            exit_coordinator = getattr(self.components, "exit_coordinator", None)
            if exit_coordinator is None:
                logger.error("Exit coordinator is unavailable; skipping strategy exits")
                return
            
            for position in positions:
                ctx = self._get_symbol_context(position.symbol)
                if ctx and ctx.market_data is not None:
                    current_price = ctx.market_data['close'].iloc[-1]
                    indicators = ctx.indicators
                else:
                    current_price = (
                        getattr(position, "current_price", None)
                        or getattr(position, "open_price", None)
                        or getattr(position, "price_open", 0.0)
                    )
                    indicators = {}
                
                exit_signal = exit_coordinator.evaluate(
                    position=position,
                    current_price=current_price,
                    indicators=indicators
                )
                
                if exit_signal is None:
                    continue
                if exit_signal.should_exit:
                    logger.info(f"🚪 Exit signal for {position.symbol} #{position.ticket}: {exit_signal.reason}")
                    closed = self.components.execution_engine.close_position(
                        ticket=position.ticket, reason=exit_signal.reason
                    )
                    if not closed:
                        continue
                    dynamic_sltp_manager = getattr(self.components, "dynamic_sltp_manager", None)
                    if dynamic_sltp_manager:
                        dynamic_sltp_manager.cleanup_position(position.ticket)
                    
                    # Update consecutive loss tracking
                    sym_ctx = self._get_symbol_context(position.symbol)
                    profit = self._position_profit(position)
                    if sym_ctx:
                        if profit < 0:
                            sym_ctx.consecutive_losses += 1
                        else:
                            sym_ctx.consecutive_losses = 0
                    
                    # Record trade result for intelligent sizing (Phase 4)
                    if self._sizer:
                        self._sizer.record_trade_result(position.symbol, profit)
                    
        except Exception as e:
            logger.error(f"Exit evaluation error: {e}")

    @staticmethod
    def _position_profit(position) -> float:
        profit = getattr(position, "profit", None)
        if profit is None:
            profit = getattr(position, "unrealized_pnl", None)
        if profit is None:
            calculate_profit = getattr(position, "calculate_unrealized_pnl", None)
            if callable(calculate_profit):
                profit = calculate_profit()
        try:
            value = float(profit or 0.0)
            return value if math.isfinite(value) else 0.0
        except (TypeError, ValueError):
            return 0.0
    
    async def _scan_adoptions(self):
        """Scan for and adopt external trades."""
        try:
            adoptions = self.components.lifecycle_manager.scan_and_adopt()
            if adoptions > 0:
                logger.info(f"Adopted {adoptions} external trade(s)")
        except Exception as e:
            logger.debug(f"Adoption scan error: {e}")
    
    async def _log_portfolio_status(self):
        """Log portfolio status periodically."""
        try:
            acct = self.components.mt5_connector.get_account_info()
            positions = self.components.trade_manager.get_all_positions()
            
            total_pnl = sum(self._position_profit(position) for position in positions)
            symbols_traded = set(p.symbol for p in positions)
            
            daily_pnl = 0
            if self._daily_start_equity > 0:
                daily_pnl = acct.get('equity', 0) - self._daily_start_equity
            
            macro_str = ""
            if self._current_macro_snapshot:
                m = self._current_macro_snapshot
                macro_str = (f" | Macro={m.regime}(conf={m.confidence:.2f}) "
                           f"VIX={m.vix:.1f}({m.vix_trend}) "
                           f"Bias: G={m.gold_bias:+.1f} O={m.oil_bias:+.1f} "
                           f"C={m.crypto_bias:+.1f} E={m.forex_eur_bias:+.1f}")
            
            logger.info(f"📊 PORTFOLIO [Cycle {self._loop_count}]: "
                       f"Balance=${acct.get('balance', 0):.2f} | "
                       f"Equity=${acct.get('equity', 0):.2f} | "
                       f"Positions={len(positions)} {list(symbols_traded)} | "
                       f"Unrealized={total_pnl:+.2f} | "
                       f"Daily={daily_pnl:+.2f}{macro_str}")
        except Exception as e:
            logger.debug(f"Portfolio status error: {e}")
