"""
ML-Enhanced Decision Making

Softmax/Argmax signal selection and price prediction for backtesting.
Provides probabilistic framework for strategy selection and forecasting.
"""

import numpy as np
import pandas as pd
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

from cthulu.strategy.base import Signal, SignalType


class SelectionMethod(Enum):
    """Signal selection methods"""
    ARGMAX = "argmax"           # Select single highest-confidence signal
    SOFTMAX = "softmax"         # Probabilistic selection weighted by confidence
    TOP_K = "top_k"             # Select top K strategies
    THRESHOLD = "threshold"      # All signals above threshold


@dataclass
class PredictionResult:
    """Result from price prediction model"""
    direction: SignalType       # Predicted direction (LONG/SHORT)
    probability: float          # Confidence in prediction
    expected_move_pct: float    # Expected price move percentage
    horizon_bars: int           # Prediction horizon
    features_used: List[str] = field(default_factory=list)
    
    
class SoftmaxSelector:
    """
    Softmax-based signal selection.
    
    Converts raw confidence scores to probability distribution,
    allowing for controlled exploration vs exploitation.
    """
    
    def __init__(self, temperature: float = 1.0, min_probability: float = 0.05):
        """
        Initialize softmax selector.
        
        Args:
            temperature: Controls distribution sharpness (lower = more greedy)
                        - T=0.1: Nearly argmax (very greedy)
                        - T=1.0: Standard softmax
                        - T=10.0: Near-uniform (high exploration)
            min_probability: Minimum probability floor for any strategy
        """
        self.logger = logging.getLogger("cthulu.backtesting.ml.softmax")
        self.temperature = temperature
        self.min_probability = min_probability
        
    def softmax(self, scores: np.ndarray) -> np.ndarray:
        """
        Compute softmax probabilities with temperature scaling.
        
        Args:
            scores: Raw confidence/quality scores
            
        Returns:
            Probability distribution summing to 1.0
        """
        if len(scores) == 0:
            return np.array([])
            
        # Temperature scaling
        scaled = scores / self.temperature
        
        # Numerical stability: subtract max
        scaled = scaled - np.max(scaled)
        
        # Compute softmax
        exp_scores = np.exp(scaled)
        probabilities = exp_scores / np.sum(exp_scores)
        
        # Apply minimum probability floor
        if self.min_probability > 0:
            n = len(probabilities)
            floor_total = self.min_probability * n
            if floor_total < 1.0:
                # Redistribute to meet floor while preserving relative ordering
                probabilities = probabilities * (1 - floor_total) + self.min_probability
                probabilities = probabilities / probabilities.sum()  # Renormalize
                
        return probabilities
        
    def select_signal(
        self,
        signals: List[Tuple[str, Signal]],
        method: SelectionMethod = SelectionMethod.SOFTMAX,
        k: int = 1,
        threshold: float = 0.5
    ) -> List[Tuple[str, Signal, float]]:
        """
        Select signals using specified method.
        
        Args:
            signals: List of (strategy_name, signal) tuples
            method: Selection method to use
            k: Number of signals to select (for TOP_K)
            threshold: Confidence threshold (for THRESHOLD method)
            
        Returns:
            List of (strategy_name, signal, selection_probability) tuples
        """
        if not signals:
            return []
            
        # Extract confidence scores
        scores = np.array([s[1].confidence for s in signals])
        names = [s[0] for s in signals]
        
        if method == SelectionMethod.ARGMAX:
            # Select single highest confidence
            idx = np.argmax(scores)
            return [(names[idx], signals[idx][1], 1.0)]
            
        elif method == SelectionMethod.SOFTMAX:
            # Probabilistic selection
            probabilities = self.softmax(scores)
            # Sample one signal based on probabilities
            idx = np.random.choice(len(signals), p=probabilities)
            return [(names[idx], signals[idx][1], probabilities[idx])]
            
        elif method == SelectionMethod.TOP_K:
            # Select top K by confidence
            indices = np.argsort(scores)[-k:][::-1]  # Descending order
            probabilities = self.softmax(scores[indices])
            return [
                (names[i], signals[i][1], probabilities[j])
                for j, i in enumerate(indices)
            ]
            
        elif method == SelectionMethod.THRESHOLD:
            # All signals above threshold
            mask = scores >= threshold
            if not mask.any():
                return []
            filtered_scores = scores[mask]
            probabilities = self.softmax(filtered_scores)
            result = []
            prob_idx = 0
            for i, (name, signal) in enumerate(signals):
                if mask[i]:
                    result.append((name, signal, probabilities[prob_idx]))
                    prob_idx += 1
            return result
            
        else:
            raise ValueError(f"Unknown selection method: {method}")
            
    def blend_signals(
        self,
        signals: List[Tuple[str, Signal]],
        weights: Optional[Dict[str, float]] = None
    ) -> Optional[Signal]:
        """
        Blend multiple signals into single ensemble signal.
        
        Args:
            signals: List of (strategy_name, signal) tuples
            weights: Optional strategy weights (uses softmax if not provided)
            
        Returns:
            Blended signal or None if no valid signals
        """
        if not signals:
            return None
            
        # Get confidence scores
        scores = np.array([s[1].confidence for s in signals])
        
        # Compute weights
        if weights:
            w = np.array([weights.get(s[0], 1.0) for s in signals])
            w = w / w.sum()  # Normalize
        else:
            w = self.softmax(scores)
            
        # Separate by direction
        long_weight = 0.0
        short_weight = 0.0
        
        for i, (name, signal) in enumerate(signals):
            if signal.side == SignalType.LONG:
                long_weight += w[i]
            elif signal.side == SignalType.SHORT:
                short_weight += w[i]
                
        # Determine direction
        if long_weight > short_weight:
            direction = SignalType.LONG
            direction_confidence = long_weight
            direction_signals = [(s, w[i]) for i, (n, s) in enumerate(signals) if s.side == SignalType.LONG]
        elif short_weight > long_weight:
            direction = SignalType.SHORT
            direction_confidence = short_weight
            direction_signals = [(s, w[i]) for i, (n, s) in enumerate(signals) if s.side == SignalType.SHORT]
        else:
            # Tie - no clear direction
            return None
            
        # Weighted average of stop loss and take profit
        stop_losses = [(s.stop_loss, wt) for s, wt in direction_signals if s.stop_loss is not None]
        take_profits = [(s.take_profit, wt) for s, wt in direction_signals if s.take_profit is not None]
        
        avg_sl = None
        avg_tp = None
        
        if stop_losses:
            values, weights_sl = zip(*stop_losses)
            avg_sl = np.average(values, weights=weights_sl)
            
        if take_profits:
            values, weights_tp = zip(*take_profits)
            avg_tp = np.average(values, weights=weights_tp)
            
        # Create blended signal
        base_signal = direction_signals[0][0]
        blended = Signal(
            id=f"blended_{base_signal.id}",
            timestamp=base_signal.timestamp,
            symbol=base_signal.symbol,
            timeframe=base_signal.timeframe,
            side=direction,
            action="blend",
            price=base_signal.price,
            stop_loss=avg_sl,
            take_profit=avg_tp,
            confidence=direction_confidence,
            reason=f"Blended from {len(direction_signals)} signals (softmax T={self.temperature})",
            metadata={
                'blend_method': 'softmax',
                'temperature': self.temperature,
                'num_signals': len(direction_signals),
                'direction_weight': direction_confidence,
            }
        )
        
        return blended


class PricePredictor:
    """
    Multi-bar price direction predictor using softmax classification.
    
    Predicts probability distribution over price movements
    (up/down/neutral) for N bars ahead.
    """
    
    def __init__(
        self,
        lookback_bars: int = 20,
        prediction_horizon: int = 5,
        num_classes: int = 3,  # Up, Down, Neutral
        neutral_threshold: float = 0.001  # 0.1% move considered neutral
    ):
        """
        Initialize price predictor.
        
        Args:
            lookback_bars: Number of historical bars for features
            prediction_horizon: Bars ahead to predict
            num_classes: Number of prediction classes (3 = up/down/neutral)
            neutral_threshold: Price change threshold for neutral classification
        """
        self.logger = logging.getLogger("cthulu.backtesting.ml.predictor")
        self.lookback_bars = lookback_bars
        self.prediction_horizon = prediction_horizon
        self.num_classes = num_classes
        self.neutral_threshold = neutral_threshold
        
        # Feature history
        self.history = deque(maxlen=lookback_bars + prediction_horizon)
        
        # Simple learned weights (can be replaced with neural network)
        self.weights: Optional[np.ndarray] = None
        self.feature_names: List[str] = []
        
    def extract_features(self, data: pd.DataFrame) -> np.ndarray:
        """
        Extract features from OHLCV data.
        
        Args:
            data: DataFrame with OHLCV columns
            
        Returns:
            Feature vector
        """
        features = []
        self.feature_names = []
        
        close = data['close'].values
        high = data['high'].values
        low = data['low'].values
        volume = data['volume'].values if 'volume' in data.columns else np.ones_like(close)
        
        # Price momentum features
        for period in [5, 10, 20]:
            if len(close) >= period:
                momentum = (close[-1] - close[-period]) / close[-period]
                features.append(momentum)
                self.feature_names.append(f'momentum_{period}')
            else:
                features.append(0.0)
                self.feature_names.append(f'momentum_{period}')
                
        # Volatility (ATR-like)
        if len(close) >= 14:
            # True Range = max(high-low, |high-prev_close|, |low-prev_close|)
            tr = high[-14:] - low[-14:]  # Simplified: just use high-low range
            atr = np.mean(tr) / close[-1] if close[-1] > 0 else 0.0
            features.append(atr)
            self.feature_names.append('atr_ratio')
        else:
            features.append(0.0)
            self.feature_names.append('atr_ratio')
            
        # RSI-like
        if len(close) >= 14:
            changes = np.diff(close[-15:])
            gains = np.mean(np.maximum(changes, 0))
            losses = np.mean(np.abs(np.minimum(changes, 0)))
            if losses > 0:
                rs = gains / losses
                rsi = 100 - (100 / (1 + rs))
            else:
                rsi = 100
            features.append((rsi - 50) / 50)  # Normalize to [-1, 1]
            self.feature_names.append('rsi_normalized')
        else:
            features.append(0.0)
            self.feature_names.append('rsi_normalized')
            
        # Volume trend
        if len(volume) >= 10:
            vol_ma = np.mean(volume[-10:])
            vol_ratio = volume[-1] / vol_ma if vol_ma > 0 else 1.0
            features.append(np.log(vol_ratio))  # Log scale
            self.feature_names.append('volume_ratio')
        else:
            features.append(0.0)
            self.feature_names.append('volume_ratio')
            
        # Price position in range
        if len(close) >= 20:
            high_20 = np.max(high[-20:])
            low_20 = np.min(low[-20:])
            range_pos = (close[-1] - low_20) / (high_20 - low_20) if high_20 > low_20 else 0.5
            features.append(range_pos * 2 - 1)  # Normalize to [-1, 1]
            self.feature_names.append('range_position')
        else:
            features.append(0.0)
            self.feature_names.append('range_position')
            
        # Recent returns sequence (last 5 bars)
        if len(close) >= 6:
            recent_returns = np.diff(close[-6:]) / close[-6:-1]
            features.extend(recent_returns)
            for i in range(5):
                self.feature_names.append(f'return_t-{5-i}')
        else:
            features.extend([0.0] * 5)
            for i in range(5):
                self.feature_names.append(f'return_t-{5-i}')
                
        return np.array(features)
        
    def predict_softmax(self, features: np.ndarray) -> np.ndarray:
        """
        Predict class probabilities using softmax.
        
        Args:
            features: Feature vector
            
        Returns:
            Probability distribution over classes [down, neutral, up]
        """
        if self.weights is None:
            # Initialize with simple heuristic weights
            self._initialize_weights(len(features))
            
        # Linear combination
        logits = self.weights @ features
        
        # Softmax
        logits = logits - np.max(logits)  # Numerical stability
        exp_logits = np.exp(logits)
        probabilities = exp_logits / np.sum(exp_logits)
        
        return probabilities
        
    def _initialize_weights(self, num_features: int):
        """Initialize weights with sensible defaults."""
        self.weights = np.zeros((self.num_classes, num_features))
        
        # Down class: negative momentum, high RSI (overbought)
        self.weights[0, 0] = -0.5   # momentum_5
        self.weights[0, 1] = -0.3   # momentum_10
        self.weights[0, 2] = -0.2   # momentum_20
        self.weights[0, 3] = 0.3    # atr_ratio (high vol = potential reversal)
        self.weights[0, 4] = 0.3    # rsi_normalized (high RSI = sell)
        
        # Up class: positive momentum, low RSI (oversold)
        self.weights[2, 0] = 0.5    # momentum_5
        self.weights[2, 1] = 0.3    # momentum_10
        self.weights[2, 2] = 0.2    # momentum_20
        self.weights[2, 3] = 0.3    # atr_ratio
        self.weights[2, 4] = -0.3   # rsi_normalized (low RSI = buy)
        
        # Neutral class: low volatility, RSI near 50
        self.weights[1, 3] = -0.5   # Low ATR = neutral
        self.weights[1, 4] = -0.5   # RSI near 0 (normalized) = neutral
        
    def predict(self, data: pd.DataFrame) -> PredictionResult:
        """
        Generate price prediction.
        
        Args:
            data: DataFrame with recent OHLCV data
            
        Returns:
            PredictionResult with direction and probability
        """
        features = self.extract_features(data)
        probabilities = self.predict_softmax(features)
        
        # Classes: [down, neutral, up]
        class_idx = np.argmax(probabilities)
        confidence = probabilities[class_idx]
        
        if class_idx == 0:
            direction = SignalType.SHORT
            expected_move = -np.abs(features[0])  # Use momentum as estimate
        elif class_idx == 2:
            direction = SignalType.LONG
            expected_move = np.abs(features[0])
        else:
            # Neutral - default to most likely non-neutral
            if probabilities[2] > probabilities[0]:
                direction = SignalType.LONG
                expected_move = np.abs(features[0]) * 0.5  # Halved for low confidence
            else:
                direction = SignalType.SHORT
                expected_move = -np.abs(features[0]) * 0.5
            confidence = max(probabilities[0], probabilities[2])
            
        return PredictionResult(
            direction=direction,
            probability=confidence,
            expected_move_pct=expected_move * 100,
            horizon_bars=self.prediction_horizon,
            features_used=self.feature_names
        )
        
    def train(
        self,
        data: pd.DataFrame,
        learning_rate: float = 0.01,
        epochs: int = 100
    ) -> Dict[str, float]:
        """
        Train the predictor on historical data.
        
        Simple gradient descent on cross-entropy loss.
        
        Args:
            data: Historical OHLCV data
            learning_rate: Learning rate for gradient descent
            epochs: Number of training epochs
            
        Returns:
            Training metrics
        """
        if len(data) < self.lookback_bars + self.prediction_horizon + 10:
            self.logger.warning("Insufficient data for training")
            return {'accuracy': 0.0, 'loss': float('inf')}
            
        # Prepare training samples
        X = []
        y = []
        
        for i in range(self.lookback_bars, len(data) - self.prediction_horizon):
            window = data.iloc[i-self.lookback_bars:i+1]
            features = self.extract_features(window)
            
            # Calculate actual future return
            current_close = data.iloc[i]['close']
            future_close = data.iloc[i + self.prediction_horizon]['close']
            future_return = (future_close - current_close) / current_close
            
            # Classify
            if future_return > self.neutral_threshold:
                label = 2  # Up
            elif future_return < -self.neutral_threshold:
                label = 0  # Down
            else:
                label = 1  # Neutral
                
            X.append(features)
            y.append(label)
            
        X = np.array(X)
        y = np.array(y)
        
        # Initialize weights
        if self.weights is None:
            self._initialize_weights(X.shape[1])
            
        # Training loop
        best_accuracy = 0.0
        
        for epoch in range(epochs):
            # Forward pass
            logits = X @ self.weights.T
            
            # Softmax
            exp_logits = np.exp(logits - np.max(logits, axis=1, keepdims=True))
            probs = exp_logits / np.sum(exp_logits, axis=1, keepdims=True)
            
            # Cross-entropy loss
            n_samples = len(y)
            loss = -np.mean(np.log(probs[np.arange(n_samples), y] + 1e-8))
            
            # Accuracy
            predictions = np.argmax(probs, axis=1)
            accuracy = np.mean(predictions == y)
            
            if accuracy > best_accuracy:
                best_accuracy = accuracy
                
            # Gradient computation
            # d_loss/d_logits = probs - one_hot(y)
            d_logits = probs.copy()
            d_logits[np.arange(n_samples), y] -= 1
            d_logits /= n_samples
            
            # d_loss/d_weights = d_logits.T @ X
            d_weights = d_logits.T @ X
            
            # Update weights
            self.weights -= learning_rate * d_weights
            
            if epoch % 20 == 0:
                self.logger.debug(f"Epoch {epoch}: loss={loss:.4f}, accuracy={accuracy:.3f}")
                
        self.logger.info(f"Training complete. Best accuracy: {best_accuracy:.3f}")
        
        return {
            'accuracy': best_accuracy,
            'loss': loss,
            'samples': len(y),
            'class_distribution': {
                'down': np.sum(y == 0),
                'neutral': np.sum(y == 1),
                'up': np.sum(y == 2)
            }
        }


class ArgmaxStrategySelector:
    """
    Argmax-based strategy selection with performance tracking.
    
    Selects the single best strategy based on recent performance
    rather than ensemble voting.
    """
    
    def __init__(
        self,
        lookback_trades: int = 20,
        performance_metric: str = 'sharpe',
        exploration_rate: float = 0.1
    ):
        """
        Initialize argmax selector.
        
        Args:
            lookback_trades: Number of recent trades for performance calculation
            performance_metric: Metric for ranking ('sharpe', 'profit_factor', 'win_rate')
            exploration_rate: Probability of random selection (epsilon-greedy)
        """
        self.logger = logging.getLogger("cthulu.backtesting.ml.argmax")
        self.lookback_trades = lookback_trades
        self.performance_metric = performance_metric
        self.exploration_rate = exploration_rate
        
        # Performance tracking
        self.strategy_returns: Dict[str, deque] = {}
        self.strategy_scores: Dict[str, float] = {}
        
    def update_performance(self, strategy_name: str, pnl: float):
        """Record trade result for strategy."""
        if strategy_name not in self.strategy_returns:
            self.strategy_returns[strategy_name] = deque(maxlen=self.lookback_trades)
        self.strategy_returns[strategy_name].append(pnl)
        
        # Recalculate score
        self._update_score(strategy_name)
        
    def _update_score(self, strategy_name: str):
        """Update performance score for strategy."""
        returns = list(self.strategy_returns[strategy_name])
        
        if len(returns) < 3:
            self.strategy_scores[strategy_name] = 0.0
            return
            
        returns_arr = np.array(returns)
        
        if self.performance_metric == 'sharpe':
            mean_return = np.mean(returns_arr)
            std_return = np.std(returns_arr)
            self.strategy_scores[strategy_name] = mean_return / std_return if std_return > 0 else 0.0
            
        elif self.performance_metric == 'profit_factor':
            gains = np.sum(returns_arr[returns_arr > 0])
            losses = np.abs(np.sum(returns_arr[returns_arr < 0]))
            self.strategy_scores[strategy_name] = gains / losses if losses > 0 else gains
            
        elif self.performance_metric == 'win_rate':
            self.strategy_scores[strategy_name] = np.mean(returns_arr > 0)
            
        else:
            self.strategy_scores[strategy_name] = np.sum(returns_arr)
            
    def select_strategy(self, available_strategies: List[str]) -> str:
        """
        Select best strategy using argmax with epsilon-greedy exploration.
        
        Args:
            available_strategies: List of strategy names to choose from
            
        Returns:
            Selected strategy name
        """
        if not available_strategies:
            raise ValueError("No strategies available")
            
        # Epsilon-greedy exploration
        if np.random.random() < self.exploration_rate:
            selected = np.random.choice(available_strategies)
            self.logger.debug(f"Exploration: randomly selected {selected}")
            return selected
            
        # Argmax selection
        scores = [self.strategy_scores.get(s, 0.0) for s in available_strategies]
        
        if max(scores) == min(scores):  # All equal (or unknown)
            selected = np.random.choice(available_strategies)
        else:
            idx = np.argmax(scores)
            selected = available_strategies[idx]
            
        self.logger.debug(f"Argmax selected {selected} (score={self.strategy_scores.get(selected, 0):.3f})")
        return selected
        
    def get_rankings(self) -> List[Tuple[str, float]]:
        """Get strategies ranked by score."""
        sorted_strategies = sorted(
            self.strategy_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_strategies
