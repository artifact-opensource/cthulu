"""
Price Predictor - The Foresight of Cognition

Multi-bar ahead price direction forecasting using softmax/argmax.
Trainable neural predictor with gradient descent optimization.

Part of Cthulu Cognition Engine v6.0.0
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import json
import os
import logging

logger = logging.getLogger("cthulu.cognition.predictor")


class PredictionDirection(Enum):
    """Prediction direction classifications."""
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


@dataclass
class PricePrediction:
    """Price prediction result."""
    direction: PredictionDirection
    confidence: float
    probabilities: Dict[str, float]
    expected_move_pct: float
    horizon_bars: int
    features_used: int
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def is_actionable(self) -> bool:
        """Whether prediction meets minimum confidence threshold."""
        return self.confidence >= 0.55 and self.direction != PredictionDirection.NEUTRAL
    
    @property
    def signal_strength(self) -> str:
        """Qualitative signal strength."""
        if self.confidence >= 0.80:
            return "VERY_STRONG"
        elif self.confidence >= 0.70:
            return "STRONG"
        elif self.confidence >= 0.60:
            return "MODERATE"
        elif self.confidence >= 0.50:
            return "WEAK"
        else:
            return "VERY_WEAK"


@dataclass
class TrainingResult:
    """Training result metrics."""
    epochs_trained: int
    final_loss: float
    accuracy: float
    samples_used: int
    training_time_seconds: float


class PricePredictor:
    """
    Softmax-based price direction predictor.
    
    Features extracted (12 total):
    - Momentum (3 timeframes)
    - ATR ratio (volatility)
    - RSI normalized
    - Volume ratio
    - Range position
    - Recent returns (5)
    
    Training:
    - Cross-entropy loss
    - Gradient descent with momentum
    - Configurable epochs and learning rate
    
    Output:
    - Direction: LONG/SHORT/NEUTRAL
    - Probability distribution
    - Expected move percentage
    """
    
    DIRECTIONS = [PredictionDirection.LONG, PredictionDirection.SHORT, PredictionDirection.NEUTRAL]
    
    def __init__(
        self,
        lookback_bars: int = 60,
        prediction_horizon: int = 5,
        confidence_threshold: float = 0.55,
        feature_count: int = 12,
        hidden_size: int = 32,
        learning_rate: float = 0.01,
        momentum: float = 0.9,
        model_path: Optional[str] = None
    ):
        self.lookback_bars = lookback_bars
        self.prediction_horizon = prediction_horizon
        self.confidence_threshold = confidence_threshold
        self.feature_count = feature_count
        self.hidden_size = hidden_size
        self.learning_rate = learning_rate
        self.momentum = momentum
        
        # Model weights (simple 2-layer network)
        self._init_weights()
        
        # Momentum buffers for gradient descent
        self._velocity_w1 = np.zeros_like(self.W1)
        self._velocity_b1 = np.zeros_like(self.b1)
        self._velocity_w2 = np.zeros_like(self.W2)
        self._velocity_b2 = np.zeros_like(self.b2)
        
        # Feature normalization
        self._feature_means = np.zeros(feature_count)
        self._feature_stds = np.ones(feature_count)
        self._fitted = False
        
        # Training history
        self._loss_history: List[float] = []
        self._accuracy_history: List[float] = []
        
        # Load model if path provided
        if model_path and os.path.exists(model_path):
            self.load(model_path)
        
        logger.info(f"PricePredictor initialized: lookback={lookback_bars}, horizon={prediction_horizon}")
    
    def _init_weights(self):
        """Initialize network weights (Xavier initialization)."""
        np.random.seed(42)
        
        # Input -> Hidden
        scale1 = np.sqrt(2.0 / (self.feature_count + self.hidden_size))
        self.W1 = np.random.randn(self.feature_count, self.hidden_size) * scale1
        self.b1 = np.zeros(self.hidden_size)
        
        # Hidden -> Output (3 classes)
        scale2 = np.sqrt(2.0 / (self.hidden_size + 3))
        self.W2 = np.random.randn(self.hidden_size, 3) * scale2
        self.b2 = np.zeros(3)
    
    def extract_features(self, df: pd.DataFrame) -> np.ndarray:
        """
        Extract features from OHLCV data.
        
        Returns: Array of shape (n_samples, feature_count)
        """
        if len(df) < self.lookback_bars:
            raise ValueError(f"Need at least {self.lookback_bars} bars, got {len(df)}")
        
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        open_price = df['open'].values
        volume = df['volume'].values if 'volume' in df.columns else np.ones(len(close))
        
        features = []
        
        # 1-3. Multi-timeframe momentum
        mom_5 = (close[-1] - close[-5]) / (close[-5] + 1e-10) if len(close) >= 5 else 0
        mom_10 = (close[-1] - close[-10]) / (close[-10] + 1e-10) if len(close) >= 10 else 0
        mom_20 = (close[-1] - close[-20]) / (close[-20] + 1e-10) if len(close) >= 20 else 0
        features.extend([mom_5 * 100, mom_10 * 100, mom_20 * 100])
        
        # 4. ATR ratio (volatility)
        if len(close) >= 15:
            # True Range calculation with aligned arrays
            high_slice = high[-14:]
            low_slice = low[-14:]
            prev_close = close[-15:-1]
            tr = np.maximum(
                high_slice - low_slice,
                np.maximum(
                    np.abs(high_slice - prev_close),
                    np.abs(low_slice - prev_close)
                )
            )
            atr = np.mean(tr)
        else:
            atr = np.mean(high - low) if len(high) > 0 else 0
        atr_ratio = (atr / close[-1]) * 100 if close[-1] > 0 else 0
        features.append(atr_ratio)
        
        # 5. RSI normalized (0-100 -> -1 to 1)
        rsi = self._calculate_rsi(close, 14)
        rsi_norm = (rsi - 50) / 50  # Center at 0
        features.append(rsi_norm)
        
        # 6. Volume ratio
        vol_sma_5 = np.mean(volume[-5:]) if len(volume) >= 5 else volume[-1]
        vol_sma_20 = np.mean(volume[-20:]) if len(volume) >= 20 else volume[-1]
        vol_ratio = (vol_sma_5 / (vol_sma_20 + 1e-10)) - 1
        features.append(np.clip(vol_ratio, -2, 2))
        
        # 7. Range position (where price is in recent range)
        high_20 = np.max(high[-20:]) if len(high) >= 20 else high[-1]
        low_20 = np.min(low[-20:]) if len(low) >= 20 else low[-1]
        range_pos = (close[-1] - low_20) / (high_20 - low_20 + 1e-10)
        range_pos = (range_pos - 0.5) * 2  # Center at 0
        features.append(range_pos)
        
        # 8-12. Recent returns (last 5 bars)
        for i in range(1, 6):
            if len(close) > i:
                ret = (close[-i] - close[-(i+1)]) / (close[-(i+1)] + 1e-10) * 100
            else:
                ret = 0
            features.append(np.clip(ret, -5, 5))
        
        return np.array(features)
    
    def _calculate_rsi(self, close: np.ndarray, period: int = 14) -> float:
        """Calculate RSI."""
        if len(close) < period + 1:
            return 50.0
        
        deltas = np.diff(close[-(period+1):])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return float(rsi)
    
    def _normalize_features(self, features: np.ndarray) -> np.ndarray:
        """Normalize features using stored means/stds."""
        if not self._fitted:
            return features
        return (features - self._feature_means) / (self._feature_stds + 1e-10)
    
    def _fit_normalizer(self, features: np.ndarray):
        """Fit feature normalizer on training data."""
        self._feature_means = np.mean(features, axis=0)
        self._feature_stds = np.std(features, axis=0)
        self._feature_stds[self._feature_stds < 1e-10] = 1.0
        self._fitted = True
    
    def _relu(self, x: np.ndarray) -> np.ndarray:
        """ReLU activation."""
        return np.maximum(0, x)
    
    def _relu_derivative(self, x: np.ndarray) -> np.ndarray:
        """ReLU derivative."""
        return (x > 0).astype(float)
    
    def _softmax(self, x: np.ndarray) -> np.ndarray:
        """Softmax activation."""
        exp_x = np.exp(x - np.max(x, axis=-1, keepdims=True))
        return exp_x / np.sum(exp_x, axis=-1, keepdims=True)
    
    def _forward(self, x: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Forward pass through network."""
        # Hidden layer
        z1 = np.dot(x, self.W1) + self.b1
        a1 = self._relu(z1)
        
        # Output layer
        z2 = np.dot(a1, self.W2) + self.b2
        a2 = self._softmax(z2)
        
        return z1, a1, a2
    
    def _cross_entropy_loss(self, y_pred: np.ndarray, y_true: np.ndarray) -> float:
        """Calculate cross-entropy loss."""
        eps = 1e-10
        return -np.mean(np.sum(y_true * np.log(y_pred + eps), axis=-1))
    
    def predict(self, df: pd.DataFrame) -> PricePrediction:
        """
        Predict price direction.
        
        Args:
            df: DataFrame with OHLCV columns
            
        Returns:
            PricePrediction with direction, confidence, and probabilities
        """
        try:
            features = self.extract_features(df)
            features_norm = self._normalize_features(features)
            
            # Forward pass
            _, _, probs = self._forward(features_norm.reshape(1, -1))
            probs = probs[0]
            
            # Determine direction (argmax)
            direction_idx = np.argmax(probs)
            direction = self.DIRECTIONS[direction_idx]
            confidence = float(probs[direction_idx])
            
            # Calculate expected move
            expected_move = self._estimate_expected_move(df, direction, confidence)
            
            return PricePrediction(
                direction=direction,
                confidence=confidence,
                probabilities={d.value: float(probs[i]) for i, d in enumerate(self.DIRECTIONS)},
                expected_move_pct=expected_move,
                horizon_bars=self.prediction_horizon,
                features_used=self.feature_count
            )
            
        except Exception as e:
            logger.error(f"Prediction error: {e}")
            return PricePrediction(
                direction=PredictionDirection.NEUTRAL,
                confidence=0.33,
                probabilities={d.value: 0.33 for d in self.DIRECTIONS},
                expected_move_pct=0.0,
                horizon_bars=self.prediction_horizon,
                features_used=0
            )
    
    def _estimate_expected_move(self, df: pd.DataFrame, direction: PredictionDirection, confidence: float) -> float:
        """Estimate expected price move based on recent volatility."""
        if len(df) < 21:
            return 0.0
        
        close = df['close'].values
        
        # Average bar size (as percentage)
        # Use aligned slices: diff of last 20 gives 19 values, divide by previous 19 closes
        recent_close = close[-20:]
        price_changes = np.abs(np.diff(recent_close))
        prev_closes = recent_close[:-1]  # 19 elements to match diff output
        bar_sizes = price_changes / (prev_closes + 1e-10) * 100
        avg_bar_size = np.mean(bar_sizes)
        
        # Expected move = avg_bar_size * horizon * confidence factor
        base_move = avg_bar_size * self.prediction_horizon * 0.5
        
        # Scale by confidence
        expected_move = base_move * (0.5 + confidence * 0.5)
        
        # Direction
        if direction == PredictionDirection.SHORT:
            expected_move = -expected_move
        elif direction == PredictionDirection.NEUTRAL:
            expected_move = 0.0
        
        return float(expected_move)
    
    def train(
        self,
        df: pd.DataFrame,
        epochs: int = 100,
        batch_size: int = 32,
        validation_split: float = 0.2,
        move_threshold_pct: float = 0.1
    ) -> TrainingResult:
        """
        Train the predictor on historical data.
        
        Args:
            df: DataFrame with OHLCV columns
            epochs: Training epochs
            batch_size: Mini-batch size
            validation_split: Fraction for validation
            move_threshold_pct: % move to classify as LONG/SHORT (vs NEUTRAL)
            
        Returns:
            TrainingResult with metrics
        """
        import time
        start_time = time.time()
        
        logger.info(f"Starting training: {len(df)} bars, {epochs} epochs")
        
        # Prepare training data
        X, y = self._prepare_training_data(df, move_threshold_pct)
        
        if len(X) < 100:
            logger.warning(f"Insufficient training data: {len(X)} samples")
            return TrainingResult(0, float('inf'), 0.0, len(X), 0.0)
        
        # Fit normalizer
        self._fit_normalizer(X)
        X = self._normalize_features(X)
        
        # Train/val split
        split_idx = int(len(X) * (1 - validation_split))
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]
        
        # Training loop
        for epoch in range(epochs):
            # Shuffle training data
            indices = np.random.permutation(len(X_train))
            X_shuffled = X_train[indices]
            y_shuffled = y_train[indices]
            
            # Mini-batch training
            epoch_loss = 0.0
            n_batches = max(1, len(X_train) // batch_size)
            
            for i in range(n_batches):
                start_idx = i * batch_size
                end_idx = min(start_idx + batch_size, len(X_train))
                
                X_batch = X_shuffled[start_idx:end_idx]
                y_batch = y_shuffled[start_idx:end_idx]
                
                # Forward pass
                z1, a1, a2 = self._forward(X_batch)
                
                # Loss
                batch_loss = self._cross_entropy_loss(a2, y_batch)
                epoch_loss += batch_loss
                
                # Backward pass
                self._backward(X_batch, y_batch, z1, a1, a2)
            
            epoch_loss /= n_batches
            self._loss_history.append(epoch_loss)
            
            # Validation accuracy
            if len(X_val) > 0:
                _, _, val_probs = self._forward(X_val)
                val_preds = np.argmax(val_probs, axis=1)
                val_true = np.argmax(y_val, axis=1)
                accuracy = np.mean(val_preds == val_true)
                self._accuracy_history.append(accuracy)
            else:
                accuracy = 0.0
            
            if epoch % 20 == 0:
                logger.debug(f"Epoch {epoch}: loss={epoch_loss:.4f}, acc={accuracy:.4f}")
        
        training_time = time.time() - start_time
        final_loss = self._loss_history[-1] if self._loss_history else float('inf')
        final_acc = self._accuracy_history[-1] if self._accuracy_history else 0.0
        
        logger.info(f"Training complete: loss={final_loss:.4f}, acc={final_acc:.4f}, time={training_time:.1f}s")
        
        return TrainingResult(
            epochs_trained=epochs,
            final_loss=final_loss,
            accuracy=final_acc,
            samples_used=len(X_train),
            training_time_seconds=training_time
        )
    
    def _prepare_training_data(
        self,
        df: pd.DataFrame,
        move_threshold_pct: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare training samples and labels."""
        X_list = []
        y_list = []
        
        close = df['close'].values
        
        for i in range(self.lookback_bars, len(df) - self.prediction_horizon):
            # Extract features for this sample
            sample_df = df.iloc[i - self.lookback_bars:i + 1]
            
            try:
                features = self.extract_features(sample_df)
                
                # Calculate label (future move)
                current_price = close[i]
                future_price = close[i + self.prediction_horizon]
                pct_move = (future_price - current_price) / current_price * 100
                
                # Classify
                if pct_move > move_threshold_pct:
                    label = [1, 0, 0]  # LONG
                elif pct_move < -move_threshold_pct:
                    label = [0, 1, 0]  # SHORT
                else:
                    label = [0, 0, 1]  # NEUTRAL
                
                X_list.append(features)
                y_list.append(label)
                
            except Exception:
                continue
        
        return np.array(X_list), np.array(y_list)
    
    def _backward(
        self,
        X: np.ndarray,
        y: np.ndarray,
        z1: np.ndarray,
        a1: np.ndarray,
        a2: np.ndarray
    ):
        """Backward pass with gradient descent + momentum."""
        m = len(X)
        
        # Output layer gradients
        dz2 = a2 - y
        dW2 = np.dot(a1.T, dz2) / m
        db2 = np.mean(dz2, axis=0)
        
        # Hidden layer gradients
        da1 = np.dot(dz2, self.W2.T)
        dz1 = da1 * self._relu_derivative(z1)
        dW1 = np.dot(X.T, dz1) / m
        db1 = np.mean(dz1, axis=0)
        
        # Update with momentum
        self._velocity_w2 = self.momentum * self._velocity_w2 - self.learning_rate * dW2
        self._velocity_b2 = self.momentum * self._velocity_b2 - self.learning_rate * db2
        self._velocity_w1 = self.momentum * self._velocity_w1 - self.learning_rate * dW1
        self._velocity_b1 = self.momentum * self._velocity_b1 - self.learning_rate * db1
        
        self.W2 += self._velocity_w2
        self.b2 += self._velocity_b2
        self.W1 += self._velocity_w1
        self.b1 += self._velocity_b1
    
    def save(self, path: str):
        """Save model to file."""
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
        
        state = {
            'W1': self.W1.tolist(),
            'b1': self.b1.tolist(),
            'W2': self.W2.tolist(),
            'b2': self.b2.tolist(),
            'feature_means': self._feature_means.tolist(),
            'feature_stds': self._feature_stds.tolist(),
            'fitted': self._fitted,
            'lookback_bars': self.lookback_bars,
            'prediction_horizon': self.prediction_horizon,
            'confidence_threshold': self.confidence_threshold
        }
        
        with open(path, 'w') as f:
            json.dump(state, f)
        
        logger.info(f"Model saved to {path}")
    
    def load(self, path: str):
        """Load model from file."""
        with open(path, 'r') as f:
            state = json.load(f)
        
        self.W1 = np.array(state['W1'])
        self.b1 = np.array(state['b1'])
        self.W2 = np.array(state['W2'])
        self.b2 = np.array(state['b2'])
        self._feature_means = np.array(state['feature_means'])
        self._feature_stds = np.array(state['feature_stds'])
        self._fitted = state['fitted']
        self.lookback_bars = state['lookback_bars']
        self.prediction_horizon = state['prediction_horizon']
        self.confidence_threshold = state['confidence_threshold']
        
        logger.info(f"Model loaded from {path}")
    
    def get_training_history(self) -> Dict[str, List[float]]:
        """Get training history."""
        return {
            'loss': self._loss_history,
            'accuracy': self._accuracy_history
        }
    
    def to_dict(self) -> Dict:
        """Export current state as dictionary."""
        return {
            'lookback_bars': self.lookback_bars,
            'prediction_horizon': self.prediction_horizon,
            'confidence_threshold': self.confidence_threshold,
            'fitted': self._fitted,
            'epochs_trained': len(self._loss_history),
            'final_loss': self._loss_history[-1] if self._loss_history else None,
            'final_accuracy': self._accuracy_history[-1] if self._accuracy_history else None
        }


# Module-level singleton
_predictor: Optional[PricePredictor] = None


def get_price_predictor(**kwargs) -> PricePredictor:
    """Get or create the price predictor singleton."""
    global _predictor
    if _predictor is None:
        _predictor = PricePredictor(**kwargs)
    return _predictor


def predict_direction(df: pd.DataFrame) -> PricePrediction:
    """Convenience function to predict direction."""
    return get_price_predictor().predict(df)
