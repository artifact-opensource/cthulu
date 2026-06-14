"""
Performance Analyzer

Semantic search across performance metrics to identify what works
in specific market conditions.
"""

import logging
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class PerformanceInsight:
    """Performance insight from semantic analysis"""
    condition: str
    metric: str
    value: float
    sample_size: int
    confidence: float
    recommendation: str
    supporting_data: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'condition': self.condition,
            'metric': self.metric,
            'value': self.value,
            'sample_size': self.sample_size,
            'confidence': self.confidence,
            'recommendation': self.recommendation,
            'supporting_data_count': len(self.supporting_data)
        }


class PerformanceAnalyzer:
    """
    Analyzes trading performance using semantic search.
    
    Identifies patterns in what works under specific market conditions,
    times, regimes, and other contextual factors.
    """
    
    def __init__(self, vector_adapter=None, retriever=None):
        """
        Initialize performance analyzer.
        
        Args:
            vector_adapter: VectorStudioAdapter instance
            retriever: ContextRetriever instance
        """
        self.vector_adapter = vector_adapter
        self.retriever = retriever
        self.logger = logging.getLogger(__name__)
        
    def analyze_regime_performance(
        self,
        symbol: str,
        lookback_days: int = 90
    ) -> Dict[str, PerformanceInsight]:
        """
        Analyze performance by market regime.
        
        Args:
            symbol: Trading symbol
            lookback_days: Days to look back
            
        Returns:
            Dictionary of regime -> performance insight
        """
        insights = {}
        
        regimes = [
            'TRENDING_BULLISH',
            'TRENDING_BEARISH',
            'RANGING',
            'VOLATILE',
            'BREAKOUT'
        ]
        
        for regime in regimes:
            try:
                # Query performance in this regime
                contexts = self.retriever.get_regime_contexts(
                    regime=regime,
                    symbol=symbol,
                    k=50,
                    min_score=0.6
                )
                
                if not contexts:
                    continue
                    
                # Analyze outcomes
                wins = sum(1 for c in contexts if c.trade_outcome == 'WIN')
                total = len(contexts)
                win_rate = wins / total if total > 0 else 0.0
                
                avg_pnl = np.mean([c.pnl for c in contexts if c.pnl is not None])
                
                # Calculate confidence
                confidence = self._calculate_confidence(total, win_rate)
                
                # Generate recommendation
                recommendation = self._generate_regime_recommendation(
                    regime, win_rate, avg_pnl
                )
                
                insight = PerformanceInsight(
                    condition=f"Regime: {regime}",
                    metric="win_rate",
                    value=win_rate,
                    sample_size=total,
                    confidence=confidence,
                    recommendation=recommendation,
                    supporting_data=[
                        {'outcome': c.trade_outcome, 'pnl': c.pnl}
                        for c in contexts[:10]  # Top 10 examples
                    ]
                )
                
                insights[regime] = insight
                
                self.logger.info(
                    f"{regime}: {win_rate:.1%} win rate, "
                    f"${avg_pnl:.2f} avg P&L ({total} trades)"
                )
                
            except Exception as e:
                self.logger.error(f"Error analyzing regime {regime}: {e}")
                continue
                
        return insights
    
    def analyze_time_of_day_performance(
        self,
        symbol: str,
        lookback_days: int = 90
    ) -> Dict[int, PerformanceInsight]:
        """
        Analyze performance by hour of day.
        
        Args:
            symbol: Trading symbol
            lookback_days: Days to look back
            
        Returns:
            Dictionary of hour -> performance insight
        """
        insights = {}
        
        # Get all recent trades
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days)
        
        # Query trades (simplified - would need proper filtering)
        query = f"[Trade] Symbol: {symbol}"
        contexts = self.vector_adapter.find_similar_contexts(
            query=query,
            k=1000,
            min_score=0.0
        ) if self.vector_adapter else []
        
        # Group by hour
        hourly_trades = defaultdict(list)
        for ctx in contexts:
            try:
                timestamp = datetime.fromisoformat(ctx.metadata.get('timestamp', ''))
                hour = timestamp.hour
                hourly_trades[hour].append(ctx)
            except:
                continue
                
        # Analyze each hour
        for hour in range(24):
            trades = hourly_trades.get(hour, [])
            
            if len(trades) < 5:  # Minimum sample size
                continue
                
            wins = sum(1 for t in trades if t.trade_outcome == 'WIN')
            total = len(trades)
            win_rate = wins / total if total > 0 else 0.0
            
            avg_pnl = np.mean([t.pnl for t in trades if t.pnl is not None])
            
            confidence = self._calculate_confidence(total, win_rate)
            
            recommendation = self._generate_time_recommendation(
                hour, win_rate, avg_pnl
            )
            
            insight = PerformanceInsight(
                condition=f"Hour: {hour:02d}:00",
                metric="win_rate",
                value=win_rate,
                sample_size=total,
                confidence=confidence,
                recommendation=recommendation
            )
            
            insights[hour] = insight
            
        return insights
    
    def analyze_strategy_effectiveness(
        self,
        symbol: str,
        regime: Optional[str] = None,
        lookback_days: int = 90
    ) -> Dict[str, PerformanceInsight]:
        """
        Analyze which strategies work best in given conditions.
        
        Args:
            symbol: Trading symbol
            regime: Market regime (optional filter)
            lookback_days: Days to look back
            
        Returns:
            Dictionary of strategy -> performance insight
        """
        insights = {}
        
        strategies = [
            'ema_crossover',
            'sma_crossover',
            'momentum_breakout',
            'scalping',
            'mean_reversion',
            'trend_following',
            'rsi_reversal'
        ]
        
        for strategy in strategies:
            try:
                # Build query
                query = f"[Trade] Strategy: {strategy}, Symbol: {symbol}"
                if regime:
                    query += f", Regime: {regime}"
                    
                contexts = self.vector_adapter.find_similar_contexts(
                    query=query,
                    k=100,
                    min_score=0.6
                ) if self.vector_adapter else []
                
                if not contexts:
                    continue
                    
                # Analyze performance
                wins = sum(1 for c in contexts if c.trade_outcome == 'WIN')
                total = len(contexts)
                win_rate = wins / total if total > 0 else 0.0
                
                avg_pnl = np.mean([c.pnl for c in contexts if c.pnl is not None])
                
                confidence = self._calculate_confidence(total, win_rate)
                
                recommendation = self._generate_strategy_recommendation(
                    strategy, win_rate, avg_pnl, regime
                )
                
                condition_desc = f"Strategy: {strategy}"
                if regime:
                    condition_desc += f" in {regime}"
                    
                insight = PerformanceInsight(
                    condition=condition_desc,
                    metric="win_rate",
                    value=win_rate,
                    sample_size=total,
                    confidence=confidence,
                    recommendation=recommendation
                )
                
                insights[strategy] = insight
                
                self.logger.info(
                    f"{strategy}: {win_rate:.1%} win rate, "
                    f"${avg_pnl:.2f} avg P&L ({total} trades)"
                )
                
            except Exception as e:
                self.logger.error(f"Error analyzing strategy {strategy}: {e}")
                continue
                
        return insights
    
    def find_optimal_conditions(
        self,
        symbol: str,
        min_win_rate: float = 0.6,
        min_samples: int = 10
    ) -> List[PerformanceInsight]:
        """
        Find market conditions with best performance.
        
        Args:
            symbol: Trading symbol
            min_win_rate: Minimum win rate threshold
            min_samples: Minimum sample size
            
        Returns:
            List of optimal conditions sorted by performance
        """
        optimal_conditions = []
        
        # Analyze different dimensions
        regime_insights = self.analyze_regime_performance(symbol)
        time_insights = self.analyze_time_of_day_performance(symbol)
        strategy_insights = self.analyze_strategy_effectiveness(symbol)
        
        # Collect all insights
        all_insights = []
        all_insights.extend(regime_insights.values())
        all_insights.extend(time_insights.values())
        all_insights.extend(strategy_insights.values())
        
        # Filter by criteria
        for insight in all_insights:
            if (insight.value >= min_win_rate and 
                insight.sample_size >= min_samples):
                optimal_conditions.append(insight)
                
        # Sort by win rate * confidence
        optimal_conditions.sort(
            key=lambda x: x.value * x.confidence,
            reverse=True
        )
        
        self.logger.info(
            f"Found {len(optimal_conditions)} optimal conditions "
            f"(min_win_rate={min_win_rate:.1%}, min_samples={min_samples})"
        )
        
        return optimal_conditions
    
    def analyze_drawdown_patterns(
        self,
        symbol: str,
        lookback_days: int = 90
    ) -> Dict[str, Any]:
        """
        Analyze patterns in drawdown periods.
        
        Args:
            symbol: Trading symbol
            lookback_days: Days to look back
            
        Returns:
            Dictionary with drawdown analysis
        """
        try:
            # Query losing trades
            query = f"[Trade] Symbol: {symbol}, Outcome: LOSS"
            
            contexts = self.vector_adapter.find_similar_contexts(
                query=query,
                k=200,
                min_score=0.0
            ) if self.vector_adapter else []
            
            if not contexts:
                return {}
                
            # Analyze common factors in losses
            regimes = defaultdict(int)
            strategies = defaultdict(int)
            hours = defaultdict(int)
            
            for ctx in contexts:
                metadata = ctx.metadata
                regimes[metadata.get('regime', 'UNKNOWN')] += 1
                strategies[metadata.get('strategy', 'UNKNOWN')] += 1
                
                try:
                    timestamp = datetime.fromisoformat(metadata.get('timestamp', ''))
                    hours[timestamp.hour] += 1
                except:
                    pass
                    
            # Find most common factors
            analysis = {
                'total_losses': len(contexts),
                'most_common_regime': max(regimes.items(), key=lambda x: x[1])[0] if regimes else None,
                'most_common_strategy': max(strategies.items(), key=lambda x: x[1])[0] if strategies else None,
                'worst_hours': sorted(hours.items(), key=lambda x: x[1], reverse=True)[:3],
                'regime_distribution': dict(regimes),
                'strategy_distribution': dict(strategies)
            }
            
            self.logger.info(
                f"Drawdown analysis: {len(contexts)} losses, "
                f"most common in {analysis['most_common_regime']} regime"
            )
            
            return analysis
            
        except Exception as e:
            self.logger.error(f"Error analyzing drawdown patterns: {e}")
            return {}
    
    def generate_performance_report(
        self,
        symbol: str,
        lookback_days: int = 90
    ) -> Dict[str, Any]:
        """
        Generate comprehensive performance report.
        
        Args:
            symbol: Trading symbol
            lookback_days: Days to look back
            
        Returns:
            Dictionary with complete performance analysis
        """
        self.logger.info(f"Generating performance report for {symbol}...")
        
        report = {
            'symbol': symbol,
            'lookback_days': lookback_days,
            'generated_at': datetime.now().isoformat(),
            'regime_performance': {},
            'time_of_day_performance': {},
            'strategy_effectiveness': {},
            'optimal_conditions': [],
            'drawdown_analysis': {}
        }
        
        try:
            # Regime analysis
            regime_insights = self.analyze_regime_performance(symbol, lookback_days)
            report['regime_performance'] = {
                k: v.to_dict() for k, v in regime_insights.items()
            }
            
            # Time analysis
            time_insights = self.analyze_time_of_day_performance(symbol, lookback_days)
            report['time_of_day_performance'] = {
                k: v.to_dict() for k, v in time_insights.items()
            }
            
            # Strategy analysis
            strategy_insights = self.analyze_strategy_effectiveness(symbol, lookback_days=lookback_days)
            report['strategy_effectiveness'] = {
                k: v.to_dict() for k, v in strategy_insights.items()
            }
            
            # Optimal conditions
            optimal = self.find_optimal_conditions(symbol)
            report['optimal_conditions'] = [o.to_dict() for o in optimal]
            
            # Drawdown analysis
            report['drawdown_analysis'] = self.analyze_drawdown_patterns(symbol, lookback_days)
            
            self.logger.info("Performance report generated successfully")
            
        except Exception as e:
            self.logger.error(f"Error generating performance report: {e}")
            
        return report
    
    # Helper methods
    
    def _calculate_confidence(
        self,
        sample_size: int,
        win_rate: float
    ) -> float:
        """Calculate confidence score based on sample size and win rate"""
        # Base confidence on sample size
        sample_confidence = min(1.0, sample_size / 30)
        
        # Adjust for win rate deviation from 50%
        win_rate_confidence = 1.0 - abs(0.5 - win_rate)
        
        # Combined confidence
        confidence = (sample_confidence * 0.7 + win_rate_confidence * 0.3)
        
        return np.clip(confidence, 0.0, 1.0)
    
    def _generate_regime_recommendation(
        self,
        regime: str,
        win_rate: float,
        avg_pnl: float
    ) -> str:
        """Generate recommendation for regime"""
        if win_rate > 0.6 and avg_pnl > 0:
            return f"FAVORABLE - Trade actively in {regime} conditions"
        elif win_rate < 0.4 or avg_pnl < 0:
            return f"UNFAVORABLE - Avoid or reduce exposure in {regime} conditions"
        else:
            return f"NEUTRAL - Standard approach in {regime} conditions"
    
    def _generate_time_recommendation(
        self,
        hour: int,
        win_rate: float,
        avg_pnl: float
    ) -> str:
        """Generate recommendation for time of day"""
        if win_rate > 0.6 and avg_pnl > 0:
            return f"FAVORABLE - {hour:02d}:00 is a strong trading hour"
        elif win_rate < 0.4 or avg_pnl < 0:
            return f"UNFAVORABLE - Avoid trading at {hour:02d}:00"
        else:
            return f"NEUTRAL - Standard performance at {hour:02d}:00"
    
    def _generate_strategy_recommendation(
        self,
        strategy: str,
        win_rate: float,
        avg_pnl: float,
        regime: Optional[str] = None
    ) -> str:
        """Generate recommendation for strategy"""
        context = f" in {regime}" if regime else ""
        
        if win_rate > 0.6 and avg_pnl > 0:
            return f"RECOMMENDED - {strategy} performs well{context}"
        elif win_rate < 0.4 or avg_pnl < 0:
            return f"NOT RECOMMENDED - {strategy} underperforms{context}"
        else:
            return f"NEUTRAL - {strategy} shows average performance{context}"
