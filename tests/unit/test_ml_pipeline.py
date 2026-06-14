"""
Tests for ML Pipeline Components.

Part of Cthulu ML Pipeline v6.0.0
"""

import pytest
import numpy as np
import pandas as pd
import os
import tempfile

from ML_RL.feature_pipeline import FeaturePipeline, FeatureSet
from ML_RL.rl_position_sizer import RLPositionSizer, RLState, SizeAction
from ML_RL.llm_analysis import LLMAnalyzer, MarketContext, TradeContext, AnalysisType
from ML_RL.mlops import ModelRegistry, DriftDetector, ModelStatus, DriftType


@pytest.fixture
def sample_ohlcv_data():
    """Generate sample OHLCV data for testing."""
    np.random.seed(42)
    n = 100
    
    returns = np.random.normal(0, 0.002, n)
    price = 100 * np.exp(np.cumsum(returns))
    
    return pd.DataFrame({
        'time': pd.date_range(start='2025-01-01', periods=n, freq='30min'),
        'open': price,
        'high': price * (1 + np.abs(np.random.normal(0, 0.001, n))),
        'low': price * (1 - np.abs(np.random.normal(0, 0.001, n))),
        'close': price * (1 + np.random.normal(0, 0.0005, n)),
        'volume': np.random.exponential(1000, n)
    })


class TestFeaturePipeline:
    """Tests for feature pipeline."""
    
    def test_feature_extraction(self, sample_ohlcv_data):
        """Test basic feature extraction."""
        pipeline = FeaturePipeline()
        features = pipeline.extract(sample_ohlcv_data)
        
        assert features.valid
        assert features.features.shape[0] == 31  # 31 features
        assert len(features.feature_names) == 31
        assert not np.isnan(features.features).any()
    
    def test_feature_extraction_insufficient_data(self):
        """Test feature extraction with insufficient data."""
        pipeline = FeaturePipeline()
        small_df = pd.DataFrame({
            'time': pd.date_range(start='2025-01-01', periods=10, freq='30min'),
            'open': [100] * 10,
            'high': [101] * 10,
            'low': [99] * 10,
            'close': [100.5] * 10,
            'volume': [1000] * 10
        })
        
        features = pipeline.extract(small_df)
        assert not features.valid
        assert len(features.errors) > 0
    
    def test_training_data_preparation(self, sample_ohlcv_data):
        """Test training data preparation."""
        pipeline = FeaturePipeline()
        X, y, names = pipeline.prepare_training_data(sample_ohlcv_data)
        
        assert X.shape[1] == 31  # 31 features
        assert y.shape[1] == 3   # 3 classes (LONG, SHORT, NEUTRAL)
        assert len(names) == 31
        assert np.sum(y) == len(y)  # Each row sums to 1 (one-hot)
    
    def test_pipeline_save_load(self, sample_ohlcv_data):
        """Test pipeline save and load."""
        pipeline = FeaturePipeline()
        X, y, _ = pipeline.prepare_training_data(sample_ohlcv_data)
        
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = f.name
        
        try:
            pipeline.save(path)
            
            pipeline2 = FeaturePipeline()
            pipeline2.load(path)
            
            assert pipeline2._fitted
            assert np.allclose(pipeline._means, pipeline2._means)
            assert np.allclose(pipeline._stds, pipeline2._stds)
        finally:
            os.unlink(path)


class TestRLPositionSizer:
    """Tests for RL position sizer."""
    
    def test_action_selection(self):
        """Test action selection."""
        sizer = RLPositionSizer()
        
        state = RLState(
            trend_strength=0.7,
            volatility_regime=0.5,
            momentum_score=0.3,
            signal_confidence=0.8,
            entry_quality=0.75,
            risk_reward_ratio=2.0,
            current_exposure_pct=0.05,
            win_rate_recent=0.55,
            drawdown_pct=0.03,
            max_position_pct=0.1,
            remaining_daily_risk=0.8
        )
        
        action, mult = sizer.select_action(state, explore=False)
        
        assert isinstance(action, SizeAction)
        assert 0 <= mult <= 2
    
    def test_reward_calculation(self):
        """Test reward calculation."""
        sizer = RLPositionSizer()
        
        # Profitable trade
        reward_profit = sizer.calculate_reward(
            action=SizeAction.STANDARD,
            multiplier=1.0,
            pnl=100,
            risk_taken=2.0,
            max_risk=5.0,
            trade_duration_bars=10
        )
        
        # Losing trade
        reward_loss = sizer.calculate_reward(
            action=SizeAction.STANDARD,
            multiplier=1.0,
            pnl=-50,
            risk_taken=2.0,
            max_risk=5.0,
            trade_duration_bars=10
        )
        
        assert reward_profit > 0
        assert reward_loss < 0
        assert reward_profit > reward_loss
    
    def test_experience_storage(self):
        """Test experience storage and training."""
        sizer = RLPositionSizer()
        
        state = RLState(
            trend_strength=0.7, volatility_regime=0.5, momentum_score=0.3,
            signal_confidence=0.8, entry_quality=0.75, risk_reward_ratio=2.0,
            current_exposure_pct=0.05, win_rate_recent=0.55, drawdown_pct=0.03,
            max_position_pct=0.1, remaining_daily_risk=0.8
        )
        
        # Store multiple experiences
        for _ in range(100):
            sizer.store_experience(state, SizeAction.STANDARD, 10.0, state, done=True)
        
        assert len(sizer.replay_buffer) == 100
        
        # Training should work
        loss = sizer.train_step()
        assert loss is not None
        assert loss >= 0
    
    def test_sizing_recommendation(self):
        """Test sizing recommendation interface."""
        sizer = RLPositionSizer()
        
        action, mult, details = sizer.get_sizing_recommendation(
            trend_strength=0.7,
            volatility=0.5,
            momentum=0.3,
            signal_confidence=0.8,
            entry_quality=0.75,
            risk_reward=2.0,
            current_exposure=0.05,
            recent_win_rate=0.55,
            current_drawdown=0.03,
            max_position_pct=0.1,
            remaining_risk=0.8
        )
        
        assert 'action' in details
        assert 'multiplier' in details
        assert 'q_values' in details
        assert 'confidence' in details


class TestLLMAnalyzer:
    """Tests for LLM analyzer."""
    
    def test_market_narrative(self):
        """Test market narrative generation."""
        analyzer = LLMAnalyzer()
        
        context = MarketContext(
            symbol="BTCUSD",
            timeframe="M30",
            current_price=95000.0,
            price_change_pct=1.5,
            trend_direction="up",
            trend_strength=0.7,
            volatility="medium",
            key_levels={"support": 93000, "resistance": 97000},
            indicators={"rsi": 65, "macd": 0.002, "adx": 35},
            recent_patterns=["higher_high"]
        )
        
        result = analyzer.generate_market_narrative(context)
        
        assert result.analysis_type == AnalysisType.MARKET_NARRATIVE
        assert len(result.content) > 0
        assert result.success
    
    def test_trade_rationale(self):
        """Test trade rationale generation."""
        analyzer = LLMAnalyzer()
        
        context = TradeContext(
            symbol="BTCUSD",
            direction="long",
            entry_price=95000.0,
            stop_loss=94000.0,
            take_profit=97000.0,
            position_size=0.1,
            signal_confidence=0.8,
            entry_quality="GOOD",
            risk_reward_ratio=2.0,
            strategy_name="momentum_breakout",
            supporting_factors=["trend_aligned", "volume_confirmed"],
            warning_factors=[]
        )
        
        result = analyzer.generate_trade_rationale(context)
        
        assert result.analysis_type == AnalysisType.TRADE_RATIONALE
        assert len(result.content) > 0
        assert result.success
    
    def test_risk_assessment(self):
        """Test risk assessment generation."""
        analyzer = LLMAnalyzer()
        
        result = analyzer.generate_risk_assessment(
            symbol="BTCUSD",
            position_size=0.1,
            stop_loss_pct=1.0,
            account_exposure_pct=5.0,
            drawdown_pct=3.0,
            win_rate=0.55,
            recent_trades=20
        )
        
        assert result.analysis_type == AnalysisType.RISK_ASSESSMENT
        assert "LOW" in result.content or "MODERATE" in result.content or "HIGH" in result.content
    
    def test_performance_summary(self):
        """Test performance summary generation."""
        analyzer = LLMAnalyzer()
        
        result = analyzer.generate_performance_summary(
            trades_count=50,
            win_rate=0.6,
            profit_factor=1.8,
            total_pnl=1500.0,
            max_drawdown=8.0,
            best_trade=500.0,
            worst_trade=-200.0,
            avg_hold_time_bars=15.0
        )
        
        assert result.analysis_type == AnalysisType.PERFORMANCE_SUMMARY
        assert "Grade:" in result.content


class TestMLOps:
    """Tests for MLOps components."""
    
    def test_model_registry(self):
        """Test model registry operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(registry_dir=tmpdir)
            
            # Register model
            model_id = registry.register(
                model_type="test_model",
                version="1.0.0",
                metrics={"accuracy": 0.75},
                hyperparameters={"epochs": 100},
                feature_names=["f1", "f2", "f3"],
                training_samples=1000,
                validation_accuracy=0.75
            )
            
            assert model_id is not None
            
            # Retrieve model
            model = registry.get_model(model_id)
            assert model is not None
            assert model.status == ModelStatus.TRAINING
            
            # Update status
            registry.update_status(model_id, ModelStatus.STAGING)
            model = registry.get_model(model_id)
            assert model.status == ModelStatus.STAGING
            
            # Promote to production
            registry.promote_to_production(model_id)
            model = registry.get_model(model_id)
            assert model.status == ModelStatus.PRODUCTION
    
    def test_drift_detector_baseline(self):
        """Test drift detector baseline setting."""
        detector = DriftDetector()
        
        feature_stats = {"f1": (0.0, 1.0), "f2": (0.5, 0.5)}
        prediction_dist = {"long": 0.4, "short": 0.3, "neutral": 0.3}
        
        detector.set_baseline(feature_stats, prediction_dist, accuracy=0.7)
        
        # No drift initially
        report = detector.detect_drift("test_model")
        assert report.drift_type == DriftType.NONE
    
    def test_drift_detection(self):
        """Test drift detection with observations."""
        detector = DriftDetector(window_size=100)
        
        # Set baseline
        detector.set_baseline(
            feature_stats={"f0": (0.0, 1.0)},
            prediction_dist={"long": 0.5, "short": 0.5},
            accuracy=0.7
        )
        
        # Record observations with drift
        for _ in range(100):
            features = np.array([5.0])  # Significantly different from baseline
            detector.record_observation(features, "long", "long")
        
        report = detector.detect_drift("test_model")
        
        # Should detect feature drift
        assert 'feature' in report.details or report.drift_type != DriftType.NONE
