"""
LLM Market Analysis - Local LLM for Market Narrative Generation

Uses local LLM (llama-cpp) to generate:
1. Market narratives and context
2. Trade rationale explanations
3. Risk assessment summaries
4. Pattern recognition descriptions

Part of Cthulu ML Pipeline v6.0.0
"""

from __future__ import annotations
import os
import json
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import threading

logger = logging.getLogger("cthulu.ml.llm_analysis")

# Check for local LLM availability
try:
    from cthulu.llm.local_llm import available as llm_available, generate as llm_generate
    HAS_LOCAL_LLM = True
except ImportError:
    HAS_LOCAL_LLM = False
    llm_available = lambda: False
    llm_generate = lambda x: ""


class AnalysisType(Enum):
    """Types of LLM analysis."""
    MARKET_NARRATIVE = "market_narrative"
    TRADE_RATIONALE = "trade_rationale"
    RISK_ASSESSMENT = "risk_assessment"
    PATTERN_DESCRIPTION = "pattern_description"
    PERFORMANCE_SUMMARY = "performance_summary"


@dataclass
class MarketContext:
    """Context for market narrative generation."""
    symbol: str
    timeframe: str
    current_price: float
    price_change_pct: float
    trend_direction: str  # "up", "down", "sideways"
    trend_strength: float  # 0-1
    volatility: str  # "low", "medium", "high"
    key_levels: Dict[str, float]  # support, resistance
    indicators: Dict[str, float]  # rsi, macd, adx, etc.
    recent_patterns: List[str]
    news_sentiment: Optional[str] = None


@dataclass
class TradeContext:
    """Context for trade rationale generation."""
    symbol: str
    direction: str  # "long", "short"
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size: float
    signal_confidence: float
    entry_quality: str
    risk_reward_ratio: float
    strategy_name: str
    supporting_factors: List[str]
    warning_factors: List[str]


@dataclass
class AnalysisResult:
    """Result of LLM analysis."""
    analysis_type: AnalysisType
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    model_used: str = "local_llm"
    tokens_used: int = 0
    success: bool = True
    error: Optional[str] = None


class LLMAnalyzer:
    """
    Local LLM-based market analyzer.
    
    Provides:
    - Market narrative generation
    - Trade rationale explanations
    - Risk assessment summaries
    - Pattern descriptions
    
    Uses deterministic fallback when LLM unavailable.
    """
    
    def __init__(self, max_tokens: int = 500, temperature: float = 0.7):
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._cache: Dict[str, AnalysisResult] = {}
        self._cache_ttl_seconds = 300  # 5 minutes
        self._lock = threading.Lock()
        
        if HAS_LOCAL_LLM and llm_available():
            logger.info("LLMAnalyzer initialized with local LLM")
        else:
            logger.info("LLMAnalyzer initialized with deterministic fallback")
    
    def _get_cache_key(self, analysis_type: AnalysisType, context_hash: str) -> str:
        """Generate cache key."""
        return f"{analysis_type.value}_{context_hash}"
    
    def _is_cached(self, key: str) -> bool:
        """Check if result is cached and not expired."""
        if key not in self._cache:
            return False
        result = self._cache[key]
        age = (datetime.now(timezone.utc) - result.timestamp).total_seconds()
        return age < self._cache_ttl_seconds
    
    def generate_market_narrative(self, context: MarketContext) -> AnalysisResult:
        """
        Generate market narrative describing current conditions.
        
        Returns:
            AnalysisResult with narrative text
        """
        context_hash = f"{context.symbol}_{context.current_price:.2f}_{context.trend_direction}"
        cache_key = self._get_cache_key(AnalysisType.MARKET_NARRATIVE, context_hash)
        
        with self._lock:
            if self._is_cached(cache_key):
                return self._cache[cache_key]
        
        # Build prompt
        prompt = self._build_market_narrative_prompt(context)
        
        # Generate
        if HAS_LOCAL_LLM and llm_available():
            try:
                content = llm_generate(prompt)
                result = AnalysisResult(
                    analysis_type=AnalysisType.MARKET_NARRATIVE,
                    content=content,
                    model_used="local_llm"
                )
            except Exception as e:
                logger.warning(f"LLM generation failed: {e}")
                result = self._fallback_market_narrative(context)
        else:
            result = self._fallback_market_narrative(context)
        
        with self._lock:
            self._cache[cache_key] = result
        
        return result
    
    def generate_trade_rationale(self, context: TradeContext) -> AnalysisResult:
        """
        Generate explanation for a trade decision.
        
        Returns:
            AnalysisResult with rationale text
        """
        context_hash = f"{context.symbol}_{context.direction}_{context.entry_price:.2f}"
        cache_key = self._get_cache_key(AnalysisType.TRADE_RATIONALE, context_hash)
        
        with self._lock:
            if self._is_cached(cache_key):
                return self._cache[cache_key]
        
        prompt = self._build_trade_rationale_prompt(context)
        
        if HAS_LOCAL_LLM and llm_available():
            try:
                content = llm_generate(prompt)
                result = AnalysisResult(
                    analysis_type=AnalysisType.TRADE_RATIONALE,
                    content=content,
                    model_used="local_llm"
                )
            except Exception as e:
                logger.warning(f"LLM generation failed: {e}")
                result = self._fallback_trade_rationale(context)
        else:
            result = self._fallback_trade_rationale(context)
        
        with self._lock:
            self._cache[cache_key] = result
        
        return result
    
    def generate_risk_assessment(
        self,
        symbol: str,
        position_size: float,
        stop_loss_pct: float,
        account_exposure_pct: float,
        drawdown_pct: float,
        win_rate: float,
        recent_trades: int
    ) -> AnalysisResult:
        """
        Generate risk assessment summary.
        
        Returns:
            AnalysisResult with risk assessment text
        """
        # Build deterministic assessment (LLM optional for this)
        risk_level = "LOW"
        concerns = []
        
        if account_exposure_pct > 15:
            risk_level = "HIGH"
            concerns.append(f"High account exposure ({account_exposure_pct:.1f}%)")
        elif account_exposure_pct > 10:
            risk_level = "MODERATE"
            concerns.append(f"Moderate account exposure ({account_exposure_pct:.1f}%)")
        
        if drawdown_pct > 10:
            risk_level = "HIGH"
            concerns.append(f"Elevated drawdown ({drawdown_pct:.1f}%)")
        elif drawdown_pct > 5:
            if risk_level != "HIGH":
                risk_level = "MODERATE"
            concerns.append(f"Notable drawdown ({drawdown_pct:.1f}%)")
        
        if win_rate < 0.4 and recent_trades >= 10:
            concerns.append(f"Below-average win rate ({win_rate:.0%})")
        
        if stop_loss_pct > 3:
            concerns.append(f"Wide stop loss ({stop_loss_pct:.1f}%)")
        
        # Build narrative
        if risk_level == "LOW":
            narrative = f"Risk assessment for {symbol}: LOW RISK. "
            narrative += "Current position sizing and exposure are within conservative limits. "
        elif risk_level == "MODERATE":
            narrative = f"Risk assessment for {symbol}: MODERATE RISK. "
            narrative += "Some caution advised. "
        else:
            narrative = f"Risk assessment for {symbol}: HIGH RISK. "
            narrative += "Consider reducing exposure. "
        
        if concerns:
            narrative += "Concerns: " + "; ".join(concerns) + "."
        else:
            narrative += "No significant concerns identified."
        
        return AnalysisResult(
            analysis_type=AnalysisType.RISK_ASSESSMENT,
            content=narrative,
            model_used="deterministic"
        )
    
    def generate_performance_summary(
        self,
        trades_count: int,
        win_rate: float,
        profit_factor: float,
        total_pnl: float,
        max_drawdown: float,
        best_trade: float,
        worst_trade: float,
        avg_hold_time_bars: float
    ) -> AnalysisResult:
        """
        Generate performance summary.
        
        Returns:
            AnalysisResult with performance summary text
        """
        # Evaluate performance
        performance_grade = "A"
        if win_rate < 0.4 or profit_factor < 1.0 or max_drawdown > 20:
            performance_grade = "C"
        elif win_rate < 0.5 or profit_factor < 1.5 or max_drawdown > 10:
            performance_grade = "B"
        
        narrative = f"Performance Summary (Grade: {performance_grade})\n\n"
        narrative += f"• Trades: {trades_count}\n"
        narrative += f"• Win Rate: {win_rate:.1%}\n"
        narrative += f"• Profit Factor: {profit_factor:.2f}\n"
        narrative += f"• Total P&L: ${total_pnl:+.2f}\n"
        narrative += f"• Max Drawdown: {max_drawdown:.1f}%\n"
        narrative += f"• Best Trade: ${best_trade:+.2f}\n"
        narrative += f"• Worst Trade: ${worst_trade:+.2f}\n"
        narrative += f"• Avg Hold Time: {avg_hold_time_bars:.1f} bars\n\n"
        
        # Analysis
        if performance_grade == "A":
            narrative += "Excellent performance. System is executing well with strong risk-adjusted returns."
        elif performance_grade == "B":
            narrative += "Good performance with room for improvement. Consider reviewing losing trades for patterns."
        else:
            narrative += "Performance needs attention. Review strategy parameters and risk management."
        
        return AnalysisResult(
            analysis_type=AnalysisType.PERFORMANCE_SUMMARY,
            content=narrative,
            model_used="deterministic"
        )
    
    # === PROMPT BUILDERS ===
    
    def _build_market_narrative_prompt(self, context: MarketContext) -> str:
        """Build prompt for market narrative generation."""
        prompt = f"""Analyze the current market conditions for {context.symbol} on {context.timeframe} timeframe.

Current State:
- Price: {context.current_price:.2f} ({context.price_change_pct:+.2f}%)
- Trend: {context.trend_direction} (strength: {context.trend_strength:.0%})
- Volatility: {context.volatility}
- Key Levels: Support {context.key_levels.get('support', 'N/A')}, Resistance {context.key_levels.get('resistance', 'N/A')}

Indicators:
- RSI: {context.indicators.get('rsi', 50):.1f}
- MACD: {context.indicators.get('macd', 0):.4f}
- ADX: {context.indicators.get('adx', 25):.1f}

Recent Patterns: {', '.join(context.recent_patterns) if context.recent_patterns else 'None identified'}

Provide a concise 2-3 sentence market narrative describing current conditions and potential implications."""
        
        return prompt
    
    def _build_trade_rationale_prompt(self, context: TradeContext) -> str:
        """Build prompt for trade rationale generation."""
        prompt = f"""Explain the rationale for this trade setup:

Trade Details:
- Symbol: {context.symbol}
- Direction: {context.direction.upper()}
- Entry: {context.entry_price:.2f}
- Stop Loss: {context.stop_loss:.2f}
- Take Profit: {context.take_profit:.2f}
- Size: {context.position_size:.2f} lots
- Risk:Reward: {context.risk_reward_ratio:.2f}
- Strategy: {context.strategy_name}
- Signal Confidence: {context.signal_confidence:.0%}
- Entry Quality: {context.entry_quality}

Supporting Factors: {', '.join(context.supporting_factors)}
Warning Factors: {', '.join(context.warning_factors) if context.warning_factors else 'None'}

Provide a concise 2-3 sentence explanation of why this trade was taken."""
        
        return prompt
    
    # === FALLBACK GENERATORS ===
    
    def _fallback_market_narrative(self, context: MarketContext) -> AnalysisResult:
        """Generate deterministic market narrative."""
        trend_desc = {
            "up": "bullish momentum",
            "down": "bearish pressure",
            "sideways": "consolidation"
        }.get(context.trend_direction, "mixed conditions")
        
        vol_desc = {
            "low": "quiet trading with limited volatility",
            "medium": "normal market activity",
            "high": "elevated volatility and increased activity"
        }.get(context.volatility, "normal conditions")
        
        rsi = context.indicators.get('rsi', 50)
        rsi_condition = ""
        if rsi > 70:
            rsi_condition = "RSI in overbought territory suggests caution for longs. "
        elif rsi < 30:
            rsi_condition = "RSI in oversold territory may present buying opportunities. "
        
        narrative = f"{context.symbol} on {context.timeframe} showing {trend_desc} with {vol_desc}. "
        narrative += f"Price at {context.current_price:.2f} ({context.price_change_pct:+.2f}% change). "
        narrative += rsi_condition
        
        if context.trend_strength > 0.7:
            narrative += "Strong trend - consider trend-following strategies."
        elif context.trend_strength < 0.3:
            narrative += "Weak trend - mean reversion or range strategies may be appropriate."
        
        return AnalysisResult(
            analysis_type=AnalysisType.MARKET_NARRATIVE,
            content=narrative,
            model_used="deterministic"
        )
    
    def _fallback_trade_rationale(self, context: TradeContext) -> AnalysisResult:
        """Generate deterministic trade rationale."""
        direction_desc = "long (bullish)" if context.direction == "long" else "short (bearish)"
        
        rationale = f"{context.direction.upper()} trade on {context.symbol} via {context.strategy_name} strategy. "
        rationale += f"Entry at {context.entry_price:.2f} with {context.risk_reward_ratio:.1f}:1 risk-reward. "
        
        if context.signal_confidence >= 0.8:
            rationale += "High confidence signal. "
        elif context.signal_confidence >= 0.6:
            rationale += "Moderate confidence signal. "
        else:
            rationale += "Lower confidence - reduced position size. "
        
        rationale += f"Entry quality: {context.entry_quality}. "
        
        if context.supporting_factors:
            rationale += f"Key factors: {', '.join(context.supporting_factors[:3])}."
        
        return AnalysisResult(
            analysis_type=AnalysisType.TRADE_RATIONALE,
            content=rationale,
            model_used="deterministic"
        )


# Singleton instance
_llm_analyzer: Optional[LLMAnalyzer] = None


def get_llm_analyzer() -> LLMAnalyzer:
    """Get singleton LLM analyzer."""
    global _llm_analyzer
    if _llm_analyzer is None:
        _llm_analyzer = LLMAnalyzer()
    return _llm_analyzer
