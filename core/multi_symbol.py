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
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


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
        self.timeframe = config.get('timeframe', 'M5')
        self.loop_interval = config.get('loop_interval', 15)
        
        # Portfolio-level limits
        portfolio_config = config.get('portfolio', {})
        self.max_total_positions = portfolio_config.get('max_total_positions', 5)
        self.max_positions_per_symbol = portfolio_config.get('max_positions_per_symbol', 2)
        self.max_correlated_positions = portfolio_config.get('max_correlated_positions', 3)
        self.max_daily_loss_pct = portfolio_config.get('max_daily_loss_pct', 5.0)
        self.signal_cooldown_seconds = portfolio_config.get('signal_cooldown_seconds', 300)
        
        # Track daily P&L
        self._daily_start_balance = 0.0
        self._daily_date = None
        self._daily_loss_halt = False
        
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
            'gold': ['GOLDm#', 'GOLD#', 'XAUUSD'],
            'oil': ['OILCash#', 'USOIL', 'BRENT'],
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
        from strategy.selector import StrategySelector
        
        strategy_config = self.config.get('strategy_selector', {})
        
        for sym, ctx in self.symbols.items():
            # Merge per-symbol strategy overrides
            sym_strategy_config = {**strategy_config, **ctx.strategy_overrides}
            selector = StrategySelector(config=sym_strategy_config, symbol=sym)
            self._strategy_selectors[sym] = selector
            logger.info(f"  Strategy selector for {sym}: {len(selector.strategies)} strategies")
    
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
        try:
            acct = self.components.mt5_connector.get_account_info()
            self._daily_start_balance = acct.get('balance', 0)
            self._daily_date = datetime.now(timezone.utc).date()
            self._daily_loss_halt = False
            logger.info(f"Daily tracking initialized: start_balance=${self._daily_start_balance:.2f}")
        except Exception as e:
            logger.warning(f"Failed to init daily tracking: {e}")
    
    async def _check_daily_limits(self) -> bool:
        """Check if daily loss limit has been hit. Returns True if trading is OK."""
        today = datetime.now(timezone.utc).date()
        
        # Reset on new day
        if today != self._daily_date:
            await self._init_daily_tracking()
            return True
        
        if self._daily_loss_halt:
            return False
        
        try:
            acct = self.components.mt5_connector.get_account_info()
            current_balance = acct.get('equity', acct.get('balance', 0))
            
            if self._daily_start_balance > 0:
                daily_pnl_pct = ((current_balance - self._daily_start_balance) 
                                / self._daily_start_balance * 100)
                
                if daily_pnl_pct <= -self.max_daily_loss_pct:
                    self._daily_loss_halt = True
                    logger.warning(f"🛑 DAILY LOSS LIMIT HIT: {daily_pnl_pct:.1f}% "
                                  f"(limit: -{self.max_daily_loss_pct}%). "
                                  f"No new trades until tomorrow.")
                    return False
            
            return True
        except Exception as e:
            logger.warning(f"Daily limit check failed: {e}")
            return True  # Fail open (allow trading if check fails)
    
    async def _execute_cycle(self):
        """Execute one full multi-symbol analysis + trade cycle."""
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
            data = self.components.data_layer.get_ohlcv(
                symbol=sym, timeframe=ctx.timeframe, count=200
            )
        except Exception as e:
            logger.debug(f"No data for {sym}: {e}")
            return None
        
        if data is None or len(data) < 50:
            return None
        
        # Check data freshness via bar timestamps
        # If the latest bar time hasn't changed across cycles, market is closed
        try:
            if 'time' in data.columns and len(data) >= 2:
                last_bar_time = data['time'].iloc[-1]
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
        
        # Calculate indicators
        indicators = await self._calculate_indicators(data)
        ctx.indicators = indicators
        
        # Update regime (every 5 min per symbol)
        now = time.time()
        if now - ctx.last_regime_update > 300:
            ctx.last_regime_update = now
            try:
                ctx.regime = self.components.regime_classifier.classify(
                    indicators=indicators, market_data=data
                )
            except Exception:
                ctx.regime = 'unknown'
        
        # Generate signal via this symbol's strategy selector
        selector = self._strategy_selectors.get(sym)
        if not selector:
            return None
        
        signal = selector.generate_signal(
            data=data, indicators=indicators, regime=ctx.regime
        )
        
        if signal is None:
            return None
        
        # Ensure symbol is set correctly
        signal['symbol'] = sym
        
        # Apply confluence filter
        if self.components.entry_confluence:
            try:
                confluence = self.components.entry_confluence.analyze(
                    signal=signal, data=data, indicators=indicators
                )
                
                if confluence['should_reject']:
                    logger.debug(f"{sym}: Signal rejected by confluence: {confluence['reason']}")
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
                return None
        
        combined_score = (
            strategy_score * 0.25 + 
            confidence * 0.25 + 
            confluence_score * 0.35 +
            max(0, macro_multiplier - 0.7) * 0.15  # Macro contributes 15%
        ) * loss_penalty * macro_multiplier * session_multiplier
        
        return ScoredSignal(
            signal=signal,
            symbol=sym,
            score=combined_score,
            regime=ctx.regime,
            strategy=signal.get('strategy', 'unknown'),
            timestamp=time.time()
        )
    
    async def _calculate_indicators(self, data) -> Dict[str, Any]:
        """Calculate indicators for a given dataset."""
        indicators = {}
        
        try:
            from indicators.rsi import calculate_rsi
            from indicators.adx import calculate_adx
            from indicators.atr import calculate_atr
            from indicators.macd import calculate_macd
            from indicators.bollinger import calculate_bollinger
            
            close = data['close'].values
            high = data['high'].values
            low = data['low'].values
            
            indicators['RSI'] = calculate_rsi(close, period=14)
            indicators['ADX'] = calculate_adx(high, low, close, period=14)
            indicators['ATR'] = calculate_atr(high, low, close, period=14)
            indicators['MACD'] = calculate_macd(close)
            indicators['BB'] = calculate_bollinger(close, period=20, std_dev=2.0)
            
            indicators['SMA_10'] = close[-10:].mean() if len(close) >= 10 else close[-1]
            indicators['SMA_30'] = close[-30:].mean() if len(close) >= 30 else close[-1]
            
            multiplier_12 = 2 / 13
            ema_12 = close[:12].mean()
            for p in close[12:]:
                ema_12 = (p - ema_12) * multiplier_12 + ema_12
            indicators['EMA_12'] = ema_12
            
            multiplier_26 = 2 / 27
            ema_26 = close[:26].mean()
            for p in close[26:]:
                ema_26 = (p - ema_26) * multiplier_26 + ema_26
            indicators['EMA_26'] = ema_26
            
        except Exception as e:
            logger.error(f"Indicator calculation error: {e}")
        
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
            sym_positions = sum(1 for p in positions if p.symbol == symbol)
            sym_ctx = self.symbols.get(symbol)
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
        for group_name, symbols in self._correlation_groups.items():
            if symbol in symbols:
                return group_name
        return None
    
    def _get_macro_bias_for_symbol(self, symbol: str, macro) -> float:
        """Map a trading symbol to its macro directional bias."""
        # Gold group
        if symbol in ('GOLDm#', 'GOLD#', 'XAUUSD'):
            return macro.gold_bias
        # Oil group
        elif symbol in ('OILCash#', 'USOIL', 'BRENT'):
            return macro.oil_bias
        # Crypto group
        elif symbol in ('BTCUSD#', 'BTCUSD', 'ETHUSD#', 'ETHUSD'):
            return macro.crypto_bias
        # EUR group
        elif symbol in ('EURUSD', 'EURGBP', 'EURJPY'):
            return macro.forex_eur_bias
        # Unknown — no bias
        return 0.0
    
    async def _execute_signal(self, scored: ScoredSignal) -> bool:
        """Execute a scored signal with portfolio-aware risk sizing."""
        signal = scored.signal
        
        try:
            # Risk evaluation
            risk_result = self.components.risk_evaluator.evaluate(signal)
            
            if not risk_result['approved']:
                logger.info(f"{scored.symbol}: Risk rejected: {risk_result['reason']}")
                return False
            
            lot_size = risk_result['lot_size']
            
            # Intelligent sizing (Phase 4) — replaces simple lot_size_override
            if self._sizer:
                try:
                    acct = self.components.mt5_connector.get_account_info()
                    sym_ctx = self.symbols.get(scored.symbol)
                    atr = sym_ctx.indicators.get('ATR', 0) if sym_ctx else 0
                    macro_conf = (self._current_macro_snapshot.confidence 
                                 if self._current_macro_snapshot else 0.5)
                    session_mult = signal.get('session_multiplier', 1.0)
                    
                    lot_size = self._sizer.calculate_lot_size(
                        symbol=scored.symbol,
                        account_balance=acct.get('balance', 0),
                        atr=atr,
                        signal_confidence=signal.get('confidence', 0.5),
                        session_multiplier=session_mult,
                        macro_confidence=macro_conf,
                        leverage=acct.get('leverage', 1000),
                    )
                except Exception as e:
                    logger.debug(f"Intelligent sizing failed, using risk evaluator size: {e}")
                    # Fall back to per-symbol override
                    sym_ctx = self.symbols.get(scored.symbol)
                    if sym_ctx and sym_ctx.lot_size_override:
                        lot_size = sym_ctx.lot_size_override
            else:
                # Fallback: per-symbol lot size override
                sym_ctx = self.symbols.get(scored.symbol)
                if sym_ctx and sym_ctx.lot_size_override:
                    lot_size = sym_ctx.lot_size_override
                
                # Session-based size adjustment (Phase 3 fallback)
                session_mult = signal.get('session_multiplier', 1.0)
                if session_mult < 1.0:
                    lot_size = max(0.01, lot_size * session_mult)
            
            # Adaptive drawdown adjustment (always applies as final safety)
            if self.components.adaptive_drawdown_manager:
                try:
                    acct = self.components.mt5_connector.get_account_info()
                    balance = acct.get('balance', 0) or acct.get('equity', 0)
                    if balance > 0:
                        dd_state = self.components.adaptive_drawdown_manager.update(balance)
                        if dd_state.get('recommendation') == 'REDUCE_RISK':
                            lot_size = self.components.adaptive_drawdown_manager.get_adjusted_lot_size(
                                lot_size, balance
                            )
                except Exception:
                    pass
            
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
                self.components.trade_manager.register_trade(
                    ticket=result['ticket'], signal=signal, result=result
                )
                
                # Apply initial SL/TP
                await self._apply_sltp(result['ticket'], signal, scored.symbol)
                
                return True
            else:
                logger.error(f"❌ Order failed for {scored.symbol}: {result.get('error')}")
                return False
                
        except Exception as e:
            logger.error(f"Execution error for {scored.symbol}: {e}")
            return False
    
    async def _apply_sltp(self, ticket: int, signal: Dict[str, Any], symbol: str):
        """Apply initial SL/TP to a new position."""
        try:
            ctx = self.symbols.get(symbol)
            atr = ctx.indicators.get('ATR', 10.0) if ctx else 10.0
            
            result = self.components.dynamic_sltp_manager.calculate_initial_sltp(
                ticket=ticket,
                direction=signal['direction'],
                entry_price=signal.get('entry_price', 0),
                atr=atr
            )
            
            if result['sl'] and result['tp']:
                success = self.components.mt5_connector.modify_position(
                    ticket=ticket, sl=result['sl'], tp=result['tp']
                )
                if success:
                    logger.info(f"SL/TP applied to {ticket}: SL={result['sl']:.2f}, TP={result['tp']:.2f}")
                    self.components.trade_manager.update_position_sltp(
                        ticket=ticket, sl=result['sl'], tp=result['tp']
                    )
        except Exception as e:
            logger.error(f"SLTP application error: {e}")
    
    async def _manage_all_positions(self):
        """Manage SL/TP for ALL open positions across ALL symbols."""
        positions = self.components.trade_manager.get_all_positions()
        
        for position in positions:
            try:
                # Get the right indicators for this position's symbol
                ctx = self.symbols.get(position.symbol)
                if ctx and ctx.indicators:
                    atr = ctx.indicators.get('ATR', 10.0)
                    current_price = (ctx.market_data['close'].iloc[-1] 
                                   if ctx.market_data is not None else position.price_open)
                else:
                    atr = 10.0
                    current_price = position.price_open  # Fallback to open price
                
                result = self.components.dynamic_sltp_manager.update_position_sltp(
                    position=position, current_price=current_price, atr=atr
                )
                
                if result['update_sl'] or result['update_tp']:
                    self.components.mt5_connector.modify_position(
                        ticket=position.ticket,
                        sl=result['new_sl'] if result['update_sl'] else position.sl,
                        tp=result['new_tp'] if result['update_tp'] else position.tp
                    )
            except Exception as e:
                logger.debug(f"Position mgmt error {position.ticket}: {e}")
    
    async def _evaluate_all_exits(self):
        """Evaluate exit conditions for ALL positions."""
        try:
            positions = self.components.trade_manager.get_all_positions()
            
            for position in positions:
                ctx = self.symbols.get(position.symbol)
                if ctx and ctx.market_data is not None:
                    current_price = ctx.market_data['close'].iloc[-1]
                    indicators = ctx.indicators
                else:
                    current_price = position.price_open  # Fallback
                    indicators = {}
                
                exit_signal = self.components.exit_coordinator.evaluate(
                    position=position,
                    current_price=current_price,
                    indicators=indicators
                )
                
                if exit_signal.should_exit:
                    logger.info(f"🚪 Exit signal for {position.symbol} #{position.ticket}: {exit_signal.reason}")
                    self.components.execution_engine.close_position(
                        ticket=position.ticket, reason=exit_signal.reason
                    )
                    self.components.dynamic_sltp_manager.cleanup_position(position.ticket)
                    
                    # Update consecutive loss tracking
                    sym_ctx = self.symbols.get(position.symbol)
                    if sym_ctx:
                        if position.profit < 0:
                            sym_ctx.consecutive_losses += 1
                        else:
                            sym_ctx.consecutive_losses = 0
                    
                    # Record trade result for intelligent sizing (Phase 4)
                    if self._sizer:
                        self._sizer.record_trade_result(position.symbol, position.profit)
                    
        except Exception as e:
            logger.error(f"Exit evaluation error: {e}")
    
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
            
            total_pnl = sum(p.profit for p in positions)
            symbols_traded = set(p.symbol for p in positions)
            
            daily_pnl = 0
            if self._daily_start_balance > 0:
                daily_pnl = acct.get('equity', 0) - self._daily_start_balance
            
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
