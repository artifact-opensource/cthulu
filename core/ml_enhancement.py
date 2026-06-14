"""
ML Enhancement Manager - Automatic ML/RL Integration for Trading

This module ensures ML enhancements are automatically initialized and active
whenever the trading loop starts. No manual setup required.

Components Integrated:
- RL Position Sizer: Learns optimal position sizing from trade outcomes
- Feature Pipeline: Extracts ML features from market data
- Cognition Engine: AI-driven signal enhancement
- Drift Detection: Monitors for model/market drift
- Online Learning: Continuous model improvement from trade outcomes

Part of Cthulu ML Pipeline v6.0.0
"""

from __future__ import annotations
import logging
import threading
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
import numpy as np
import pandas as pd

logger = logging.getLogger("cthulu.core.ml_enhancement")


@dataclass
class MLEnhancementConfig:
    """Configuration for ML enhancement manager."""
    # RL Position Sizing
    enable_rl_sizing: bool = True
    rl_learning_rate: float = 0.001
    rl_explore_rate: float = 0.1  # Reduced exploration in production
    
    # Feature Pipeline
    enable_features: bool = True
    feature_lookback: int = 50
    
    # Cognition Engine
    enable_cognition: bool = True
    enable_regime: bool = True
    enable_prediction: bool = True
    enable_sentiment: bool = True
    
    # Drift Detection
    enable_drift_detection: bool = True
    drift_check_interval: int = 100  # Every N trades
    
    # Online Learning
    enable_online_learning: bool = True
    learning_batch_size: int = 32
    min_samples_before_learning: int = 50


@dataclass
class MLEnhancementState:
    """Current state of ML enhancement system."""
    initialized: bool = False
    rl_sizer_active: bool = False
    feature_pipeline_active: bool = False
    cognition_active: bool = False
    drift_detector_active: bool = False
    
    trades_processed: int = 0
    learning_iterations: int = 0
    last_drift_check: Optional[datetime] = None
    drift_detected: bool = False
    
    # Performance tracking
    rl_sizing_decisions: int = 0
    feature_extractions: int = 0
    cognition_enhancements: int = 0


class MLEnhancementManager:
    """
    Central manager for all ML enhancements in the trading system.
    
    Automatically initializes and coordinates:
    - RL Position Sizer for dynamic position sizing
    - Feature Pipeline for ML feature extraction
    - Cognition Engine for signal enhancement
    - Drift Detection for model monitoring
    - Online Learning for continuous improvement
    
    Usage:
        # Auto-created during bootstrap
        ml_manager = get_ml_enhancement_manager(config)
        
        # In trading loop - enhance position sizing
        size_mult, details = ml_manager.get_position_size_recommendation(
            signal, market_data, account_state
        )
        
        # After trade closes - learn from outcome
        ml_manager.record_trade_outcome(trade_result)
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize ML Enhancement Manager.
        
        Args:
            config: Configuration dictionary (uses defaults if not provided)
        """
        self._lock = threading.RLock()
        
        # Parse config
        ml_config = (config or {}).get('ml_enhancement', {})
        self.config = MLEnhancementConfig(
            enable_rl_sizing=ml_config.get('enable_rl_sizing', True),
            rl_learning_rate=ml_config.get('rl_learning_rate', 0.001),
            rl_explore_rate=ml_config.get('rl_explore_rate', 0.1),
            enable_features=ml_config.get('enable_features', True),
            feature_lookback=ml_config.get('feature_lookback', 50),
            enable_cognition=ml_config.get('enable_cognition', True),
            enable_regime=ml_config.get('enable_regime', True),
            enable_prediction=ml_config.get('enable_prediction', True),
            enable_sentiment=ml_config.get('enable_sentiment', True),
            enable_drift_detection=ml_config.get('enable_drift_detection', True),
            drift_check_interval=ml_config.get('drift_check_interval', 100),
            enable_online_learning=ml_config.get('enable_online_learning', True),
            learning_batch_size=ml_config.get('learning_batch_size', 32),
            min_samples_before_learning=ml_config.get('min_samples_before_learning', 50)
        )
        
        # State tracking
        self.state = MLEnhancementState()
        
        # Component references (lazy initialized)
        self._rl_sizer = None
        self._feature_pipeline = None
        self._cognition_engine = None
        self._drift_detector = None
        self._model_registry = None
        
        # Experience buffer for online learning
        self._experience_buffer: List[Dict[str, Any]] = []
        
        # Pending trade contexts (for learning when trade closes)
        self._pending_trades: Dict[int, Dict[str, Any]] = {}  # ticket -> context
        
        logger.info(f"MLEnhancementManager created with config: rl={self.config.enable_rl_sizing}, "
                   f"features={self.config.enable_features}, cognition={self.config.enable_cognition}")
    
    def initialize(self, hektor_adapter=None, hektor_retriever=None) -> bool:
        """
        Initialize all ML components.
        
        Called automatically when trading loop starts.
        
        Args:
            hektor_adapter: Optional Vector Studio adapter for semantic memory
            hektor_retriever: Optional context retriever
            
        Returns:
            True if initialization successful
        """
        with self._lock:
            if self.state.initialized:
                logger.debug("ML Enhancement already initialized")
                return True
            
            logger.info("Initializing ML Enhancement components...")
            
            # Initialize RL Position Sizer
            if self.config.enable_rl_sizing:
                try:
                    from ML_RL.rl_position_sizer import get_rl_position_sizer
                    self._rl_sizer = get_rl_position_sizer()
                    # Reduce exploration in production
                    self._rl_sizer.epsilon = self.config.rl_explore_rate
                    self.state.rl_sizer_active = True
                    logger.info("RL Position Sizer initialized")
                except Exception as e:
                    logger.warning(f"Failed to initialize RL Position Sizer: {e}")
            
            # Initialize Feature Pipeline
            if self.config.enable_features:
                try:
                    from ML_RL.feature_pipeline import get_feature_pipeline
                    self._feature_pipeline = get_feature_pipeline()
                    self.state.feature_pipeline_active = True
                    logger.info("Feature Pipeline initialized")
                except Exception as e:
                    logger.warning(f"Failed to initialize Feature Pipeline: {e}")
            
            # Initialize Cognition Engine
            if self.config.enable_cognition:
                try:
                    from cognition.engine import create_cognition_engine
                    self._cognition_engine = create_cognition_engine(
                        config={
                            'cognition': {
                                'enable_regime': self.config.enable_regime,
                                'enable_prediction': self.config.enable_prediction,
                                'enable_sentiment': self.config.enable_sentiment
                            }
                        },
                        hektor_adapter=hektor_adapter,
                        hektor_retriever=hektor_retriever
                    )
                    self.state.cognition_active = True
                    logger.info("Cognition Engine initialized")
                except Exception as e:
                    logger.warning(f"Failed to initialize Cognition Engine: {e}")
            
            # Initialize Drift Detector
            if self.config.enable_drift_detection:
                try:
                    from ML_RL.mlops import get_drift_detector
                    self._drift_detector = get_drift_detector()
                    self.state.drift_detector_active = True
                    logger.info("Drift Detector initialized")
                except Exception as e:
                    logger.warning(f"Failed to initialize Drift Detector: {e}")
            
            # Initialize Model Registry
            try:
                from ML_RL.mlops import get_model_registry
                self._model_registry = get_model_registry()
                logger.info("Model Registry initialized")
            except Exception as e:
                logger.debug(f"Model Registry not available: {e}")
            
            self.state.initialized = True
            logger.info(f"ML Enhancement initialization complete: "
                       f"rl={self.state.rl_sizer_active}, "
                       f"features={self.state.feature_pipeline_active}, "
                       f"cognition={self.state.cognition_active}, "
                       f"drift={self.state.drift_detector_active}")
            
            return True
    
    def get_position_size_recommendation(
        self,
        signal: Any,
        market_data: pd.DataFrame,
        account_state: Dict[str, Any],
        base_size: float = 1.0
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Get ML-enhanced position size recommendation.
        
        Args:
            signal: Trading signal
            market_data: OHLCV DataFrame
            account_state: Account info (balance, equity, drawdown, etc.)
            base_size: Base position size from risk manager
            
        Returns:
            (size_multiplier, details_dict)
        """
        with self._lock:
            if not self.state.initialized:
                self.initialize()
            
            details = {
                'ml_enhanced': False,
                'rl_action': None,
                'rl_mult': 1.0,
                'feature_quality': 0.0,
                'cognition_mult': 1.0,
                'final_mult': 1.0,
                'reasons': []
            }
            
            final_mult = 1.0
            
            # Extract features
            if self._feature_pipeline and len(market_data) >= self.config.feature_lookback:
                try:
                    feature_set = self._feature_pipeline.extract(market_data)
                    if feature_set.valid:
                        self.state.feature_extractions += 1
                        details['feature_quality'] = 1.0 - len(feature_set.errors) / max(len(feature_set.feature_names), 1)
                        details['features'] = feature_set.to_dict()
                except Exception as e:
                    logger.debug(f"Feature extraction failed: {e}")
            
            # RL Position Sizing
            if self._rl_sizer:
                try:
                    # Build state for RL
                    signal_conf = getattr(signal, 'confidence', 0.5)
                    entry_quality = details.get('feature_quality', 0.5)
                    
                    # Get risk/reward from signal
                    entry_price = getattr(signal, 'price', 0) or getattr(signal, 'entry_price', 0)
                    stop_loss = getattr(signal, 'stop_loss', 0)
                    take_profit = getattr(signal, 'take_profit', 0)
                    
                    if entry_price > 0 and stop_loss > 0 and take_profit > 0:
                        risk = abs(entry_price - stop_loss)
                        reward = abs(take_profit - entry_price)
                        risk_reward = reward / risk if risk > 0 else 1.5
                    else:
                        risk_reward = 1.5
                    
                    # Market regime features
                    trend_strength = 0.5
                    volatility = 0.5
                    momentum = 0.0
                    
                    if self._cognition_engine:
                        try:
                            state = self._cognition_engine.get_state()
                            if state:
                                trend_strength = state.regime.confidence if state.regime else 0.5
                                volatility = 0.5  # Could derive from regime
                                # Map prediction to momentum
                                if state.prediction:
                                    if state.prediction.direction.value == 'long':
                                        momentum = state.prediction.confidence
                                    elif state.prediction.direction.value == 'short':
                                        momentum = -state.prediction.confidence
                        except Exception:
                            pass
                    
                    # Account state
                    balance = account_state.get('balance', 10000)
                    equity = account_state.get('equity', balance)
                    current_exposure = account_state.get('exposure_pct', 0.0)
                    drawdown_pct = account_state.get('drawdown_pct', 0.0)
                    win_rate = account_state.get('recent_win_rate', 0.5)
                    max_position_pct = account_state.get('max_position_pct', 0.02)
                    remaining_risk = account_state.get('remaining_daily_risk', 1.0)
                    
                    action, rl_mult, rl_details = self._rl_sizer.get_sizing_recommendation(
                        trend_strength=trend_strength,
                        volatility=volatility,
                        momentum=momentum,
                        signal_confidence=signal_conf,
                        entry_quality=entry_quality,
                        risk_reward=risk_reward,
                        current_exposure=current_exposure,
                        recent_win_rate=win_rate,
                        current_drawdown=drawdown_pct,
                        max_position_pct=max_position_pct,
                        remaining_risk=remaining_risk
                    )
                    
                    details['rl_action'] = action.name
                    details['rl_mult'] = rl_mult
                    details['rl_q_values'] = rl_details.get('q_values', {})
                    details['rl_confidence'] = rl_details.get('confidence', 0.0)
                    
                    final_mult *= rl_mult
                    self.state.rl_sizing_decisions += 1
                    
                    if rl_mult != 1.0:
                        details['reasons'].append(f"RL: {action.name} ({rl_mult:.2f}x)")
                    
                    # Store context for later learning
                    ticket = getattr(signal, 'id', None) or id(signal)
                    self._pending_trades[ticket] = {
                        'signal': signal,
                        'rl_action': action,
                        'rl_mult': rl_mult,
                        'state': {
                            'trend_strength': trend_strength,
                            'volatility': volatility,
                            'momentum': momentum,
                            'signal_confidence': signal_conf,
                            'entry_quality': entry_quality,
                            'risk_reward': risk_reward,
                            'exposure': current_exposure,
                            'win_rate': win_rate,
                            'drawdown': drawdown_pct,
                            'max_position': max_position_pct,
                            'remaining_risk': remaining_risk
                        },
                        'timestamp': datetime.now(timezone.utc)
                    }
                    
                except Exception as e:
                    logger.warning(f"RL sizing failed: {e}")
            
            # Cognition enhancement
            if self._cognition_engine:
                try:
                    signal_dir = 'long' if str(getattr(signal, 'side', '')).upper() in ('LONG', 'BUY') else 'short'
                    symbol = getattr(signal, 'symbol', 'UNKNOWN')
                    
                    enhancement = self._cognition_engine.enhance_signal(
                        signal_direction=signal_dir,
                        signal_confidence=getattr(signal, 'confidence', 0.5),
                        symbol=symbol,
                        market_data=market_data,
                        signal=signal
                    )
                    
                    details['cognition_mult'] = enhancement.size_multiplier
                    details['cognition_conf_mult'] = enhancement.confidence_multiplier
                    details['cognition_reasons'] = enhancement.reasons
                    details['cognition_warnings'] = enhancement.warnings
                    
                    final_mult *= enhancement.size_multiplier
                    self.state.cognition_enhancements += 1
                    
                    if enhancement.size_multiplier != 1.0:
                        details['reasons'].append(f"Cognition: {enhancement.size_multiplier:.2f}x")
                    
                except Exception as e:
                    logger.debug(f"Cognition enhancement failed: {e}")
            
            # Apply bounds
            final_mult = max(0.1, min(2.0, final_mult))
            details['final_mult'] = final_mult
            details['ml_enhanced'] = True
            
            return final_mult, details
    
    def record_trade_outcome(
        self,
        ticket: int,
        pnl: float,
        exit_price: float,
        duration_bars: int = 0,
        exit_reason: str = ""
    ):
        """
        Record trade outcome for RL learning.
        
        Args:
            ticket: Trade ticket/ID
            pnl: Profit/Loss
            exit_price: Exit price
            duration_bars: How long trade was held
            exit_reason: Why trade was closed
        """
        with self._lock:
            self.state.trades_processed += 1
            
            # Get pending context
            context = self._pending_trades.pop(ticket, None)
            if not context:
                logger.debug(f"No pending context for trade {ticket}")
                return
            
            # Calculate reward and store experience for RL
            if self._rl_sizer and context.get('rl_action'):
                try:
                    from ML_RL.rl_position_sizer import RLState, SizeAction
                    
                    state_dict = context['state']
                    rl_state = RLState(
                        trend_strength=state_dict['trend_strength'],
                        volatility_regime=state_dict['volatility'],
                        momentum_score=state_dict['momentum'],
                        signal_confidence=state_dict['signal_confidence'],
                        entry_quality=state_dict['entry_quality'],
                        risk_reward_ratio=state_dict['risk_reward'],
                        current_exposure_pct=state_dict['exposure'],
                        win_rate_recent=state_dict['win_rate'],
                        drawdown_pct=state_dict['drawdown'],
                        max_position_pct=state_dict['max_position'],
                        remaining_daily_risk=state_dict['remaining_risk']
                    )
                    
                    # Calculate reward
                    action = context['rl_action']
                    mult = context['rl_mult']
                    risk_taken = state_dict['exposure']
                    max_risk = state_dict['max_position']
                    
                    reward = self._rl_sizer.calculate_reward(
                        action=action,
                        multiplier=mult,
                        pnl=pnl,
                        risk_taken=risk_taken,
                        max_risk=max_risk,
                        trade_duration_bars=duration_bars
                    )
                    
                    # Store experience
                    self._experience_buffer.append({
                        'state': rl_state,
                        'action': action,
                        'reward': reward,
                        'pnl': pnl,
                        'timestamp': datetime.now(timezone.utc)
                    })
                    
                    logger.debug(f"Trade {ticket} outcome recorded: pnl={pnl:.2f}, reward={reward:.4f}")
                    
                    # Trigger online learning if enough samples
                    if self.config.enable_online_learning and \
                       len(self._experience_buffer) >= self.config.min_samples_before_learning:
                        self._run_online_learning()
                    
                except Exception as e:
                    logger.warning(f"Failed to record RL experience: {e}")
            
            # Check for drift
            if self.config.enable_drift_detection and \
               self.state.trades_processed % self.config.drift_check_interval == 0:
                self._check_drift()
    
    def _run_online_learning(self):
        """Run online learning iteration with buffered experiences."""
        if not self._rl_sizer:
            return
        
        try:
            # Sample batch from buffer
            batch_size = min(self.config.learning_batch_size, len(self._experience_buffer))
            indices = np.random.choice(len(self._experience_buffer), batch_size, replace=False)
            
            for idx in indices:
                exp = self._experience_buffer[idx]
                # Create a dummy next state (in real online RL this would be actual next state)
                next_state = exp['state']  # Simplified - same state
                done = True  # Trade completed
                
                self._rl_sizer.store_experience(
                    state=exp['state'],
                    action=exp['action'],
                    reward=exp['reward'],
                    next_state=next_state,
                    done=done
                )
            
            # Train step
            loss = self._rl_sizer.train_step()
            if loss is not None:
                self.state.learning_iterations += 1
                logger.info(f"Online learning step {self.state.learning_iterations}: loss={loss:.6f}")
            
            # Trim buffer
            if len(self._experience_buffer) > 1000:
                self._experience_buffer = self._experience_buffer[-500:]
            
        except Exception as e:
            logger.warning(f"Online learning failed: {e}")
    
    def _check_drift(self):
        """Check for model/market drift."""
        if not self._drift_detector:
            return
        
        try:
            self.state.last_drift_check = datetime.now(timezone.utc)
            
            # Get recent feature distributions
            if self._feature_pipeline and self._experience_buffer:
                # This would compare recent feature distributions to training distributions
                # Simplified check here
                recent_rewards = [e['reward'] for e in self._experience_buffer[-50:]]
                avg_reward = np.mean(recent_rewards) if recent_rewards else 0
                
                # Simple drift detection: significant reward drop
                if avg_reward < -0.5:
                    self.state.drift_detected = True
                    logger.warning(f"Potential model drift detected: avg_reward={avg_reward:.4f}")
                else:
                    self.state.drift_detected = False
            
        except Exception as e:
            logger.debug(f"Drift check failed: {e}")
    
    def get_cognition_engine(self):
        """Get the cognition engine for external use."""
        return self._cognition_engine
    
    def get_state(self) -> Dict[str, Any]:
        """Get current ML enhancement state."""
        return {
            'initialized': self.state.initialized,
            'components': {
                'rl_sizer': self.state.rl_sizer_active,
                'features': self.state.feature_pipeline_active,
                'cognition': self.state.cognition_active,
                'drift': self.state.drift_detector_active
            },
            'stats': {
                'trades_processed': self.state.trades_processed,
                'learning_iterations': self.state.learning_iterations,
                'rl_decisions': self.state.rl_sizing_decisions,
                'feature_extractions': self.state.feature_extractions,
                'cognition_enhancements': self.state.cognition_enhancements
            },
            'drift': {
                'detected': self.state.drift_detected,
                'last_check': self.state.last_drift_check.isoformat() if self.state.last_drift_check else None
            },
            'buffer_size': len(self._experience_buffer),
            'pending_trades': len(self._pending_trades)
        }
    
    def save_models(self):
        """Save all ML models to disk."""
        if self._rl_sizer:
            try:
                self._rl_sizer.save()
                logger.info("RL Position Sizer saved")
            except Exception as e:
                logger.warning(f"Failed to save RL sizer: {e}")
        
        if self._feature_pipeline:
            try:
                import os
                path = os.path.join(os.path.dirname(__file__), '..', 'ML_RL', 'models', 'feature_pipeline.json')
                os.makedirs(os.path.dirname(path), exist_ok=True)
                self._feature_pipeline.save(path)
                logger.info("Feature Pipeline saved")
            except Exception as e:
                logger.debug(f"Failed to save feature pipeline: {e}")
    
    def shutdown(self):
        """Graceful shutdown - save models and cleanup."""
        logger.info("ML Enhancement Manager shutting down...")
        self.save_models()
        self._experience_buffer.clear()
        self._pending_trades.clear()
        logger.info("ML Enhancement Manager shutdown complete")


# Singleton instance
_ml_enhancement_manager: Optional[MLEnhancementManager] = None


def get_ml_enhancement_manager(config: Optional[Dict[str, Any]] = None) -> MLEnhancementManager:
    """
    Get or create the ML Enhancement Manager singleton.
    
    Args:
        config: Configuration dictionary (only used on first call)
        
    Returns:
        MLEnhancementManager instance
    """
    global _ml_enhancement_manager
    if _ml_enhancement_manager is None:
        _ml_enhancement_manager = MLEnhancementManager(config)
    return _ml_enhancement_manager


def initialize_ml_enhancements(config: Dict[str, Any], hektor_adapter=None, hektor_retriever=None) -> MLEnhancementManager:
    """
    Initialize ML enhancements for the trading system.
    
    This should be called during system bootstrap.
    
    Args:
        config: System configuration
        hektor_adapter: Optional Vector Studio adapter
        hektor_retriever: Optional context retriever
        
    Returns:
        Initialized MLEnhancementManager
    """
    manager = get_ml_enhancement_manager(config)
    manager.initialize(hektor_adapter=hektor_adapter, hektor_retriever=hektor_retriever)
    return manager
