"""
Cthulu Cognition Engine - The Soul of the System

Central AI/ML integration layer that coordinates:
- Market Regime Classification
- Price Direction Prediction
- Sentiment Analysis
- Enhanced Exit Signals

Part of Cthulu v6.0.0
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import logging
import json
import os
from datetime import datetime

from .regime_classifier import (
    MarketRegimeClassifier, RegimeState, MarketRegime,
    get_regime_classifier, classify_regime
)
from .price_predictor import (
    PricePredictor, PricePrediction, PredictionDirection,
    get_price_predictor, predict_direction
)
from .sentiment_analyzer import (
    SentimentAnalyzer, SentimentScore, SentimentDirection,
    get_sentiment_analyzer, get_sentiment
)
from .exit_oracle import (
    ExitOracle, ExitSignal, ExitUrgency, PositionContext,
    get_exit_oracle, evaluate_exits
)
from .order_blocks import OrderBlockDetector, OrderBlock, OrderBlockType
from .session_orb import SessionORBDetector, SessionType, OpeningRange

logger = logging.getLogger("cthulu.cognition")


@dataclass
class CognitionState:
    """Combined state of all cognition modules."""
    regime: RegimeState
    prediction: PricePrediction
    sentiment: SentimentScore
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def combined_confidence(self) -> float:
        """Overall confidence from all modules."""
        weights = {'regime': 0.35, 'prediction': 0.40, 'sentiment': 0.25}
        return (
            self.regime.confidence * weights['regime'] +
            self.prediction.confidence * weights['prediction'] +
            self.sentiment.confidence * weights['sentiment']
        )
    
    @property
    def directional_consensus(self) -> str:
        """Check if modules agree on direction."""
        bullish_count = 0
        bearish_count = 0
        
        # Regime
        if self.regime.regime in (MarketRegime.BULL,):
            bullish_count += 1
        elif self.regime.regime in (MarketRegime.BEAR,):
            bearish_count += 1
        
        # Prediction
        if self.prediction.direction == PredictionDirection.LONG:
            bullish_count += 1
        elif self.prediction.direction == PredictionDirection.SHORT:
            bearish_count += 1
        
        # Sentiment
        if self.sentiment.direction == SentimentDirection.BULLISH:
            bullish_count += 1
        elif self.sentiment.direction == SentimentDirection.BEARISH:
            bearish_count += 1
        
        if bullish_count >= 2:
            return "BULLISH"
        elif bearish_count >= 2:
            return "BEARISH"
        else:
            return "MIXED"
    
    @property
    def trade_allowed(self) -> bool:
        """Check if conditions are favorable for trading.
        
        NOTE: This is advisory, not restrictive. The rule-based system
        should remain the primary decision maker. Cognition provides
        enhancements, not gates.
        """
        # Only block in extreme conditions with very high confidence
        if self.regime.regime == MarketRegime.CHOPPY:
            # Only block if prediction is also strongly against AND low confidence
            if self.prediction.confidence < 0.4 and self.regime.confidence > 0.8:
                return False
        
        # Only block on extreme sentiment with critical events
        if self.sentiment.suggests_caution:
            # Check if there are actually critical upcoming events
            critical_events = [e for e in self.sentiment.events 
                             if e.get('impact') == 'critical' and e.get('is_upcoming')]
            if critical_events:
                return False
        
        # Default: ALLOW trading - let rule-based system decide
        return True


@dataclass
class SignalEnhancement:
    """Enhancement/adjustment for trading signals."""
    confidence_multiplier: float  # Multiply signal confidence
    size_multiplier: float  # Multiply position size
    reasons: List[str]
    warnings: List[str]
    
    @property
    def is_favorable(self) -> bool:
        return self.confidence_multiplier >= 1.0 and not self.warnings


class CognitionEngine:
    """
    Central AI/ML integration layer for Cthulu.
    
    Coordinates all cognition modules:
    - Market Regime Classifier: Bull/Bear/Sideways/Volatile/Choppy
    - Price Predictor: Direction probabilities for next N bars
    - Sentiment Analyzer: News/calendar/fear-greed integration
    - Exit Oracle: High-confluence exit signals
    
    Provides:
    - Signal enhancement (boost/reduce confidence)
    - Exit signal generation
    - Risk adjustment recommendations
    - Market condition awareness
    """
    
    def __init__(
        self,
        enable_regime: bool = True,
        enable_prediction: bool = True,
        enable_sentiment: bool = True,
        enable_exit_oracle: bool = True,
        enable_order_blocks: bool = True,
        enable_session_orb: bool = True,
        model_dir: Optional[str] = None,
        hektor_adapter: Optional[Any] = None,
        hektor_retriever: Optional[Any] = None
    ):
        self.enable_regime = enable_regime
        self.enable_prediction = enable_prediction
        self.enable_sentiment = enable_sentiment
        self.enable_exit_oracle = enable_exit_oracle
        self.enable_order_blocks = enable_order_blocks
        self.enable_session_orb = enable_session_orb
        
        # Hektor (Vector Studio) integration for semantic memory
        self.hektor_adapter = hektor_adapter
        self.hektor_retriever = hektor_retriever
        self.enable_hektor = hektor_adapter is not None
        
        self.model_dir = model_dir or os.path.join(
            os.path.dirname(__file__), 'data', 'models'
        )
        os.makedirs(self.model_dir, exist_ok=True)
        
        # Initialize modules
        self._regime_classifier: Optional[MarketRegimeClassifier] = None
        self._price_predictor: Optional[PricePredictor] = None
        self._sentiment_analyzer: Optional[SentimentAnalyzer] = None
        self._exit_oracle: Optional[ExitOracle] = None
        self._order_block_detector: Optional[OrderBlockDetector] = None
        self._session_orb_detector: Optional[SessionORBDetector] = None
        
        # State tracking
        self._last_state: Optional[CognitionState] = None
        self._state_history: List[CognitionState] = []
        
        # Initialize enabled modules
        self._initialize_modules()
        
        logger.info(f"CognitionEngine initialized: regime={enable_regime}, "
                   f"prediction={enable_prediction}, sentiment={enable_sentiment}, "
                   f"exit_oracle={enable_exit_oracle}, order_blocks={enable_order_blocks}, "
                   f"session_orb={enable_session_orb}, hektor={self.enable_hektor}")
    
    def _get_semantic_context(self, signal: Any, market_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Retrieve semantic context from Hektor for signal enhancement.
        
        Args:
            signal: Trading signal to enhance
            market_data: Current market data
            
        Returns:
            Dictionary with semantic context and similar historical patterns
        """
        if not self.enable_hektor or not self.hektor_retriever:
            return {}
        
        try:
            # Get current market context
            current_context = {
                'symbol': getattr(signal, 'symbol', 'UNKNOWN'),
                'side': getattr(signal, 'side', 'UNKNOWN'),
                'confidence': getattr(signal, 'confidence', 0.0),
                'regime': self._last_state.regime.regime.name if self._last_state else 'UNKNOWN',
                'price': market_data['close'].iloc[-1] if len(market_data) > 0 else 0.0
            }
            
            # Find similar historical contexts
            similar_contexts = self.hektor_retriever.get_similar_signals(
                signal, 
                indicators={}, # Will be populated by retriever
                regime=current_context['regime'],
                k=5
            )
            
            return {
                'similar_count': len(similar_contexts),
                'contexts': similar_contexts[:3],  # Top 3 most similar
                'has_semantic_data': len(similar_contexts) > 0
            }
            
        except Exception as e:
            logger.debug(f"Semantic context retrieval failed: {e}")
            return {}
    
    def _store_signal_context(self, signal: Any, enhancement: SignalEnhancement, market_data: pd.DataFrame):
        """
        Store signal and context in Hektor for future semantic retrieval.
        
        Args:
            signal: Trading signal
            enhancement: Signal enhancement applied
            market_data: Current market data
        """
        if not self.enable_hektor or not self.hektor_adapter:
            return
            
        try:
            # Build context for storage
            context = {
                'indicators': {
                    'rsi': market_data.get('rsi', pd.Series()).iloc[-1] if 'rsi' in market_data.columns and len(market_data) > 0 else None,
                    'atr': market_data.get('atr', pd.Series()).iloc[-1] if 'atr' in market_data.columns and len(market_data) > 0 else None,
                    'adx': market_data.get('adx', pd.Series()).iloc[-1] if 'adx' in market_data.columns and len(market_data) > 0 else None
                },
                'regime': self._last_state.regime.regime.name if self._last_state else 'UNKNOWN',
                'enhancement': {
                    'confidence_mult': enhancement.confidence_multiplier,
                    'size_mult': enhancement.size_multiplier,
                    'favorable': enhancement.is_favorable
                },
                'symbol': getattr(signal, 'symbol', 'UNKNOWN'),
                'timestamp': datetime.now().isoformat()
            }
            
            # Remove None values
            context['indicators'] = {k: v for k, v in context['indicators'].items() if v is not None}
            
            # Store asynchronously
            self.hektor_adapter.store_signal(signal, context)
            
        except Exception as e:
            logger.debug(f"Failed to store signal context: {e}")

    def _initialize_modules(self):
        """Initialize enabled cognition modules."""
        if self.enable_regime:
            self._regime_classifier = get_regime_classifier()
        
        if self.enable_prediction:
            model_path = os.path.join(self.model_dir, 'price_predictor.json')
            self._price_predictor = get_price_predictor(
                model_path=model_path if os.path.exists(model_path) else None
            )
        
        if self.enable_sentiment:
            self._sentiment_analyzer = get_sentiment_analyzer()
        
        if self.enable_exit_oracle:
            self._exit_oracle = get_exit_oracle()
            # Integrate cognition into exit oracle
            self._exit_oracle.integrate_cognition(
                regime_classifier=self._regime_classifier,
                price_predictor=self._price_predictor,
                sentiment_analyzer=self._sentiment_analyzer
            )
        
        if self.enable_order_blocks:
            self._order_block_detector = OrderBlockDetector(
                swing_lookback=5,
                min_move_atr=1.5,
                max_age_bars=100,
                use_body_only=True
            )
        
        if self.enable_session_orb:
            self._session_orb_detector = SessionORBDetector(
                sessions=[SessionType.LONDON, SessionType.NEW_YORK],
                range_duration_minutes=30,
                confirm_bars=1
            )
    
    def analyze(self, symbol: str, market_data: pd.DataFrame) -> CognitionState:
        """
        Perform full cognition analysis.
        
        Args:
            symbol: Trading symbol
            market_data: OHLCV DataFrame
            
        Returns:
            CognitionState with all module outputs
        """
        # Regime classification
        if self._regime_classifier and len(market_data) >= 50:
            regime = self._regime_classifier.classify(market_data)
        else:
            regime = RegimeState(
                regime=MarketRegime.UNKNOWN,
                confidence=0.0,
                probabilities={},
                features={}
            )
        
        # Price prediction
        if self._price_predictor and len(market_data) >= self._price_predictor.lookback_bars:
            prediction = self._price_predictor.predict(market_data)
        else:
            prediction = PricePrediction(
                direction=PredictionDirection.NEUTRAL,
                confidence=0.33,
                probabilities={},
                expected_move_pct=0.0,
                horizon_bars=5,
                features_used=0
            )
        
        # Sentiment
        if self._sentiment_analyzer:
            sentiment = self._sentiment_analyzer.get_sentiment(symbol)
        else:
            sentiment = SentimentScore(
                score=0.0,
                direction=SentimentDirection.NEUTRAL,
                confidence=0.5,
                components={},
                events=[]
            )
        
        state = CognitionState(
            regime=regime,
            prediction=prediction,
            sentiment=sentiment
        )
        
        self._last_state = state
        self._state_history.append(state)
        
        # Trim history
        if len(self._state_history) > 100:
            self._state_history = self._state_history[-50:]
        
        logger.debug(f"Cognition analysis: regime={regime.regime.value}, "
                    f"prediction={prediction.direction.value}, "
                    f"sentiment={sentiment.direction.value}")
        
        return state
    
    def enhance_signal(
        self,
        signal_direction: str,  # 'long' or 'short'
        signal_confidence: float,
        symbol: str,
        market_data: pd.DataFrame,
        signal: Any = None  # Actual signal object for semantic analysis
    ) -> SignalEnhancement:
        """
        Enhance or adjust a trading signal based on cognition.
        
        Args:
            signal_direction: Signal direction ('long' or 'short')
            signal_confidence: Original signal confidence
            symbol: Trading symbol
            market_data: OHLCV DataFrame
            signal: Actual signal object for semantic analysis (optional)
            
        Returns:
            SignalEnhancement with multipliers and reasons
        """
        # Get or refresh state
        state = self.analyze(symbol, market_data)
        
        # Get semantic context from Hektor if available
        semantic_context = self._get_semantic_context(signal, market_data) if signal else {}
        
        confidence_mult = 1.0
        size_mult = 1.0
        reasons = []
        warnings = []
        
        # Semantic enhancement from historical patterns
        if semantic_context.get('has_semantic_data', False):
            similar_count = semantic_context.get('similar_count', 0)
            if similar_count >= 3:
                confidence_mult *= 1.10  # +10% boost for strong historical patterns
                reasons.append(f"Strong historical patterns (+10% conf, {similar_count} similar)")
            elif similar_count >= 1:
                confidence_mult *= 1.05  # +5% boost for some patterns
                reasons.append(f"Historical patterns (+5% conf, {similar_count} similar)")
                
        # Continue with existing logic...
        if self._last_state is None or (datetime.utcnow() - self._last_state.timestamp).seconds > 60:
            self.analyze(symbol, market_data)
        
        state = self._last_state
        if state is None:
            return SignalEnhancement(1.0, 1.0, [], [])
        
        confidence_mult = 1.0
        size_mult = 1.0
        reasons = []
        warnings = []
        
        # Regime alignment - BOOST MORE, PENALIZE LESS
        # Philosophy: Rule-based signals are already good, cognition should enhance
        if state.regime.regime != MarketRegime.UNKNOWN:
            regime_val = state.regime.regime.value
            
            if signal_direction == 'long':
                if regime_val == 'bull':
                    confidence_mult *= 1.20  # +20% boost
                    reasons.append(f"Bullish regime (+20% conf)")
                elif regime_val == 'bear':
                    # Only penalize if regime confidence is high
                    if state.regime.confidence > 0.7:
                        confidence_mult *= 0.90  # Reduced penalty: -10% instead of -25%
                        warnings.append(f"Bearish regime (minor -10% conf)")
                elif regime_val == 'sideways':
                    # No penalty for sideways - mean reversion can work here
                    reasons.append(f"Sideways regime (neutral)")
                elif regime_val in ('choppy', 'volatile'):
                    # Volatile can be good for momentum strategies
                    if regime_val == 'volatile':
                        confidence_mult *= 1.05  # Slight boost
                        reasons.append(f"Volatile market (+5% conf)")
                    else:
                        confidence_mult *= 0.95  # Minimal penalty
                        warnings.append(f"Choppy market (-5% conf)")
            
            elif signal_direction == 'short':
                if regime_val == 'bear':
                    confidence_mult *= 1.20  # +20% boost
                    reasons.append(f"Bearish regime (+20% conf)")
                elif regime_val == 'bull':
                    if state.regime.confidence > 0.7:
                        confidence_mult *= 0.90  # Reduced penalty
                        warnings.append(f"Bullish regime (minor -10% conf)")
        
        # Prediction alignment - ONLY BOOST, MINIMAL PENALTY
        if state.prediction.direction != PredictionDirection.NEUTRAL:
            pred_dir = state.prediction.direction.value
            pred_conf = state.prediction.confidence
            
            if (signal_direction == 'long' and pred_dir == 'long') or \
               (signal_direction == 'short' and pred_dir == 'short'):
                boost = 1 + (pred_conf - 0.5) * 0.4  # Up to +20% at 100% conf
                confidence_mult *= boost
                reasons.append(f"Prediction aligned ({pred_conf:.0%} conf)")
            elif pred_conf > 0.75:  # Only penalize on VERY strong contrary prediction
                confidence_mult *= 0.95  # Minimal penalty
                warnings.append(f"Prediction contrary ({pred_conf:.0%})")
        
        # Sentiment alignment - BOOST ONLY
        if state.sentiment.direction != SentimentDirection.NEUTRAL:
            sent_dir = state.sentiment.direction.value
            sent_conf = state.sentiment.confidence
            
            if (signal_direction == 'long' and sent_dir == 'bullish') or \
               (signal_direction == 'short' and sent_dir == 'bearish'):
                boost = 1 + (sent_conf - 0.5) * 0.25
                confidence_mult *= boost
                reasons.append(f"Sentiment aligned ({sent_dir})")
            # NO PENALTY for contrary sentiment - it's too unreliable
        
        # Caution flag - ONLY SIZE, NOT CONFIDENCE
        if state.sentiment.suggests_caution:
            # Check for actual critical events
            critical_events = [e for e in state.sentiment.events 
                             if e.get('impact') == 'critical']
            if critical_events:
                size_mult *= 0.7  # Reduced from 0.5
                warnings.append("Critical event nearby (-30% size)")
        
        # Consensus bonus - BIGGER BOOST
        if state.directional_consensus == signal_direction.upper():
            confidence_mult *= 1.15  # Increased from 1.10
            reasons.append("Full consensus (+15% conf)")
        
        # FLOOR: Never reduce confidence below 85% of original
        confidence_mult = max(confidence_mult, 0.85)
        size_mult = max(size_mult, 0.7)
        
        enhancement = SignalEnhancement(
            confidence_multiplier=confidence_mult,
            size_multiplier=size_mult,
            reasons=reasons,
            warnings=warnings
        )
        
        # Store signal context in Hektor for future learning (asynchronous)
        if signal:
            self._store_signal_context(signal, enhancement, market_data)
        
        return enhancement
    
    def get_exit_signals(
        self,
        positions: List[Dict[str, Any]],
        market_data: pd.DataFrame,
        indicators: Dict[str, float]
    ) -> List[ExitSignal]:
        """
        Get exit signals for active positions.
        
        Args:
            positions: List of position dictionaries
            market_data: OHLCV DataFrame
            indicators: Current indicator values
            
        Returns:
            List of exit signals
        """
        if not self._exit_oracle:
            return []
        
        # Convert to PositionContext
        contexts = []
        for pos in positions:
            try:
                ctx = PositionContext(
                    ticket=pos.get('ticket', 0),
                    symbol=pos.get('symbol', ''),
                    direction='long' if pos.get('type', 0) == 0 else 'short',
                    entry_price=pos.get('price_open', 0),
                    current_price=pos.get('price_current', 0),
                    volume=pos.get('volume', 0),
                    unrealized_pnl=pos.get('profit', 0),
                    entry_time=pos.get('time', datetime.utcnow())
                )
                contexts.append(ctx)
            except Exception as e:
                logger.warning(f"Error creating PositionContext: {e}")
        
        return self._exit_oracle.evaluate_exits(contexts, market_data, indicators)
    
    def get_order_block_signal(
        self,
        market_data: pd.DataFrame,
        current_price: float,
        atr: float,
        timestamp: datetime = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get entry signal from Order Block detector.
        
        Uses ICT methodology to detect institutional order blocks
        and generate signals when price revisits these zones.
        
        Args:
            market_data: OHLCV DataFrame
            current_price: Current market price
            atr: Current ATR value
            timestamp: Current timestamp
            
        Returns:
            Signal dict with direction, entry, SL, TP, confidence, reason
            or None if no signal
        """
        if not self._order_block_detector:
            return None
        
        try:
            return self._order_block_detector.update(
                df=market_data,
                current_price=current_price,
                atr=atr,
                timestamp=timestamp
            )
        except Exception as e:
            logger.warning(f"Order block detection error: {e}")
            return None
    
    def get_session_orb_signal(
        self,
        market_data: pd.DataFrame,
        current_price: float,
        atr: float,
        timestamp: datetime = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get entry signal from Session ORB detector.
        
        Detects opening range breakouts for London and New York sessions.
        
        Args:
            market_data: OHLCV DataFrame
            current_price: Current market price
            atr: Current ATR value
            timestamp: Current timestamp
            
        Returns:
            Signal dict with direction, entry, SL, TP, confidence, reason
            or None if no signal
        """
        if not self._session_orb_detector:
            return None
        
        try:
            return self._session_orb_detector.update(
                df=market_data,
                current_price=current_price,
                atr=atr,
                timestamp=timestamp
            )
        except Exception as e:
            logger.warning(f"Session ORB detection error: {e}")
            return None
    
    def get_structure_signals(
        self,
        market_data: pd.DataFrame,
        current_price: float,
        atr: float,
        timestamp: datetime = None
    ) -> List[Dict[str, Any]]:
        """
        Get all structure-based signals (Order Blocks + Session ORB).
        
        Combines ICT order block signals with session-based ORB signals.
        
        Args:
            market_data: OHLCV DataFrame
            current_price: Current market price
            atr: Current ATR value
            timestamp: Current timestamp
            
        Returns:
            List of signal dicts from both detectors
        """
        signals = []
        
        ob_signal = self.get_order_block_signal(market_data, current_price, atr, timestamp)
        if ob_signal:
            ob_signal['source'] = 'order_block'
            signals.append(ob_signal)
        
        orb_signal = self.get_session_orb_signal(market_data, current_price, atr, timestamp)
        if orb_signal:
            orb_signal['source'] = 'session_orb'
            signals.append(orb_signal)
        
        return signals
    
    def get_active_order_blocks(self) -> List[OrderBlock]:
        """Get currently active (unmitigated) order blocks."""
        if not self._order_block_detector:
            return []
        return self._order_block_detector.get_active_order_blocks()
    
    def get_active_session_ranges(self) -> Dict[str, OpeningRange]:
        """Get currently active session opening ranges."""
        if not self._session_orb_detector:
            return {}
        return self._session_orb_detector.get_active_ranges()
    
    def get_strategy_affinity(self, strategy_name: str) -> float:
        """
        Get affinity score for a strategy based on current regime.
        
        Args:
            strategy_name: Name of strategy
            
        Returns:
            Affinity score 0-1
        """
        if self._regime_classifier:
            return self._regime_classifier.get_regime_affinity(strategy_name)
        return 0.5
    
    def should_trade(self, symbol: str, market_data: pd.DataFrame) -> Tuple[bool, str]:
        """
        Check if trading is advisable.
        
        NOTE: This is ADVISORY only. The rule-based system should remain
        primary decision maker. Only block in extreme conditions.
        
        Args:
            symbol: Trading symbol
            market_data: OHLCV DataFrame
            
        Returns:
            (should_trade, reason)
        """
        if self._last_state is None or (datetime.utcnow() - self._last_state.timestamp).seconds > 60:
            self.analyze(symbol, market_data)
        
        state = self._last_state
        if state is None:
            return True, "No cognition data - proceeding"
        
        # Check trade allowed - but only block in EXTREME conditions
        if not state.trade_allowed:
            # Log but DON'T block unless critical
            if state.regime.regime == MarketRegime.CHOPPY and state.regime.confidence > 0.85:
                # Only block if VERY confident it's choppy
                logger.info(f"Cognition advisory: Choppy market detected (conf={state.regime.confidence:.2f})")
                # Don't return False - let rule-based system decide
            if state.sentiment.suggests_caution:
                logger.info(f"Cognition advisory: Sentiment caution")
                # Don't return False
        
        # Only block for CRITICAL upcoming events with high-impact
        if self._sentiment_analyzer:
            try:
                avoid, reason = self._sentiment_analyzer.should_avoid_trading(symbol)
                if avoid:
                    # Check if this is truly critical
                    if 'critical' in reason.lower() or 'nfp' in reason.lower() or 'fomc' in reason.lower():
                        return False, f"Critical event: {reason}"
                    # For other events, just log advisory
                    logger.info(f"Cognition advisory: {reason}")
            except Exception as e:
                logger.debug(f"Sentiment check error: {e}")
        
        return True, "Trading conditions acceptable"
    
    def train_predictor(
        self,
        market_data: pd.DataFrame,
        epochs: int = 100,
        **kwargs
    ):
        """Train the price predictor on historical data."""
        if not self._price_predictor:
            logger.warning("Price predictor not enabled")
            return None
        
        result = self._price_predictor.train(market_data, epochs=epochs, **kwargs)
        
        # Save model
        model_path = os.path.join(self.model_dir, 'price_predictor.json')
        self._price_predictor.save(model_path)
        
        return result
    
    def add_news(self, headline: str, source: str, symbols: List[str]):
        """Add news item to sentiment analyzer."""
        if self._sentiment_analyzer:
            self._sentiment_analyzer.add_news(headline, source, symbols)
    
    def add_economic_event(self, **kwargs):
        """Add economic event to sentiment analyzer."""
        if self._sentiment_analyzer:
            self._sentiment_analyzer.add_event(**kwargs)
    
    def get_state(self) -> Optional[CognitionState]:
        """Get last cognition state."""
        return self._last_state
    
    def to_dict(self) -> Dict[str, Any]:
        """Export current state as dictionary."""
        result = {
            'enabled_modules': {
                'regime': self.enable_regime,
                'prediction': self.enable_prediction,
                'sentiment': self.enable_sentiment,
                'exit_oracle': self.enable_exit_oracle,
                'order_blocks': self.enable_order_blocks,
                'session_orb': self.enable_session_orb
            },
            'state_history_length': len(self._state_history)
        }
        
        if self._last_state:
            result['last_state'] = {
                'regime': self._last_state.regime.regime.value,
                'regime_confidence': self._last_state.regime.confidence,
                'prediction': self._last_state.prediction.direction.value,
                'prediction_confidence': self._last_state.prediction.confidence,
                'sentiment': self._last_state.sentiment.direction.value,
                'sentiment_score': self._last_state.sentiment.score,
                'consensus': self._last_state.directional_consensus,
                'combined_confidence': self._last_state.combined_confidence,
                'trade_allowed': self._last_state.trade_allowed
            }
        
        if self._regime_classifier:
            result['regime_classifier'] = self._regime_classifier.to_dict()
        
        if self._price_predictor:
            result['price_predictor'] = self._price_predictor.to_dict()
        
        if self._sentiment_analyzer:
            result['sentiment_analyzer'] = self._sentiment_analyzer.to_dict()
        
        if self._exit_oracle:
            result['exit_oracle'] = self._exit_oracle.to_dict()
        
        # Order Blocks state
        if self._order_block_detector:
            active_obs = self.get_active_order_blocks()
            result['order_blocks'] = {
                'active_count': len(active_obs),
                'blocks': [
                    {
                        'type': ob.block_type.value,
                        'high': ob.high,
                        'low': ob.low,
                        'touches': ob.touches,
                        'structure_break': ob.structure_break.value
                    }
                    for ob in active_obs[:5]  # Top 5 most recent
                ]
            }
        
        # Session ORB state
        if self._session_orb_detector:
            active_ranges = self.get_active_session_ranges()
            result['session_orb'] = {
                'active_sessions': list(active_ranges.keys()),
                'ranges': {
                    name: {
                        'high': r.high,
                        'low': r.low,
                        'is_complete': r.is_complete,
                        'breakout_direction': r.breakout_direction
                    }
                    for name, r in active_ranges.items()
                }
            }
        
        return result


# Module-level singleton
_engine: Optional[CognitionEngine] = None


def create_cognition_engine(
    config: Dict[str, Any] = None,
    hektor_adapter: Any = None,
    hektor_retriever: Any = None
) -> CognitionEngine:
    """
    Factory function to create a CognitionEngine with proper configuration.
    
    Args:
        config: Configuration dictionary
        hektor_adapter: Vector Studio adapter for semantic memory
        hektor_retriever: Context retriever for semantic search
        
    Returns:
        Configured CognitionEngine instance
    """
    if config is None:
        config = {}
    
    cognition_config = config.get('cognition', {})
    
    return CognitionEngine(
        enable_regime=cognition_config.get('enable_regime', True),
        enable_prediction=cognition_config.get('enable_prediction', True),
        enable_sentiment=cognition_config.get('enable_sentiment', True),
        enable_exit_oracle=cognition_config.get('enable_exit_oracle', True),
        enable_order_blocks=cognition_config.get('enable_order_blocks', True),
        enable_session_orb=cognition_config.get('enable_session_orb', True),
        model_dir=cognition_config.get('model_dir'),
        hektor_adapter=hektor_adapter,
        hektor_retriever=hektor_retriever
    )


def get_cognition_engine(**kwargs) -> CognitionEngine:
    """Get or create the cognition engine singleton."""
    global _engine
    if _engine is None:
        _engine = CognitionEngine(**kwargs)
    return _engine


def analyze_market(symbol: str, market_data: pd.DataFrame) -> CognitionState:
    """Convenience function to analyze market."""
    return get_cognition_engine().analyze(symbol, market_data)


def enhance_signal(
    signal_direction: str,
    signal_confidence: float,
    symbol: str,
    market_data: pd.DataFrame
) -> SignalEnhancement:
    """Convenience function to enhance signal."""
    return get_cognition_engine().enhance_signal(
        signal_direction, signal_confidence, symbol, market_data
    )
