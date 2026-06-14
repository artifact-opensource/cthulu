"""
Cthulu Cognition - The Soul of the System

AI/ML integration layer for intelligent trading decisions.

Modules:
- regime_classifier: Market state detection (Bull/Bear/Sideways/Volatile/Choppy)
- price_predictor: Direction forecasting with softmax/argmax
- sentiment_analyzer: News and calendar integration
- exit_oracle: High-confluence exit signals
- engine: Central orchestration layer

Usage:
    from cthulu.cognition import CognitionEngine, get_cognition_engine
    
    engine = get_cognition_engine()
    state = engine.analyze('BTCUSD', market_data)
    
    # Enhance signals
    enhancement = engine.enhance_signal('long', 0.75, 'BTCUSD', market_data)
    
    # Get exit signals
    exits = engine.get_exit_signals(positions, market_data, indicators)

Part of Cthulu v6.0.0
"""

# Regime Classifier
from .regime_classifier import (
    MarketRegimeClassifier,
    RegimeState,
    MarketRegime,
    RegimeTransition,
    get_regime_classifier,
    classify_regime,
)

# Price Predictor
from .price_predictor import (
    PricePredictor,
    PricePrediction,
    PredictionDirection,
    TrainingResult,
    get_price_predictor,
    predict_direction,
)

# Sentiment Analyzer
from .sentiment_analyzer import (
    SentimentAnalyzer,
    SentimentScore,
    SentimentDirection,
    EventImpact,
    NewsItem,
    EconomicEvent,
    get_sentiment_analyzer,
    get_sentiment,
)

# Exit Oracle
from .exit_oracle import (
    ExitOracle,
    ExitSignal,
    ExitUrgency,
    ExitReason,
    PositionContext,
    ReversalDetector,
    get_exit_oracle,
    evaluate_exits,
)

# Main Engine
from .engine import (
    CognitionEngine,
    CognitionState,
    SignalEnhancement,
    get_cognition_engine,
    analyze_market,
    enhance_signal,
)

# Tier Optimizer (existing)
from .tier_optimizer import (
    get_tier_optimizer,
    run_tier_optimization,
)

# ML Instrumentation (existing)
from .instrumentation import MLDataCollector

# Training Data Logger
from .training_logger import (
    TrainingDataLogger,
    TradeDecision,
    get_training_logger,
    log_trade_decision,
    log_trade_outcome,
)

# Order Blocks (ICT methodology)
from .order_blocks import (
    OrderBlockDetector,
    OrderBlock,
    OrderBlockType,
    StructureBreak,
    SwingPoint,
)

# Session ORB (Opening Range Breakout)
from .session_orb import (
    SessionORBDetector,
    SessionConfig,
    SessionType,
    OpeningRange,
)

# Chart Manager (Visual Reasoning Layer)
from .chart_manager import (
    ChartManager,
    ChartState,
    PriceZone,
    TrendLine,
    Channel,
    ZoneType,
    ZoneState,
    ZoneEvent,
    TrendDirection,
    get_chart_manager,
    shutdown_chart_manager,
)

__all__ = [
    # Regime
    'MarketRegimeClassifier',
    'RegimeState',
    'MarketRegime',
    'RegimeTransition',
    'get_regime_classifier',
    'classify_regime',
    
    # Predictor
    'PricePredictor',
    'PricePrediction',
    'PredictionDirection',
    'TrainingResult',
    'get_price_predictor',
    'predict_direction',
    
    # Sentiment
    'SentimentAnalyzer',
    'SentimentScore',
    'SentimentDirection',
    'EventImpact',
    'NewsItem',
    'EconomicEvent',
    'get_sentiment_analyzer',
    'get_sentiment',
    
    # Exit Oracle
    'ExitOracle',
    'ExitSignal',
    'ExitUrgency',
    'ExitReason',
    'PositionContext',
    'ReversalDetector',
    'get_exit_oracle',
    'evaluate_exits',
    
    # Engine
    'CognitionEngine',
    'CognitionState',
    'SignalEnhancement',
    'get_cognition_engine',
    'analyze_market',
    'enhance_signal',
    
    # Existing
    'get_tier_optimizer',
    'run_tier_optimization',
    'MLDataCollector',
    
    # Training Logger
    'TrainingDataLogger',
    'TradeDecision',
    'get_training_logger',
    'log_trade_decision',
    'log_trade_outcome',
    
    # Order Blocks (ICT)
    'OrderBlockDetector',
    'OrderBlock',
    'OrderBlockType',
    'StructureBreak',
    'SwingPoint',
    
    # Session ORB
    'SessionORBDetector',
    'SessionConfig',
    'SessionType',
    'OpeningRange',
    
    # Chart Manager (Visual Reasoning)
    'ChartManager',
    'ChartState',
    'PriceZone',
    'TrendLine',
    'Channel',
    'ZoneType',
    'ZoneState',
    'ZoneEvent',
    'TrendDirection',
    'get_chart_manager',
    'shutdown_chart_manager',
]
