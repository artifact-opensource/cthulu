"""
ML-Based Profit Tier Optimizer

Uses historical scaling data to dynamically optimize profit-taking tiers.
Learns from past performance to adjust:
- Optimal profit thresholds for each tier
- Optimal close percentages
- Account-size specific adjustments
- Volatility-based adaptations

Architecture:
1. Collects scaling events from profit_scaler
2. Analyzes outcomes (profit vs giveback)
3. Uses gradient-free optimization to find better tiers
4. Applies learned tiers in real-time

Philosophy:
- Start with battle-tested defaults
- Gradually adapt to market behavior
- Never compromise capital protection
- Conservative updates (small incremental changes)
"""

import os
import json
import math
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from collections import defaultdict
import threading

logger = logging.getLogger('cthulu.ml.tier_optimizer')

# Data directory for persistence
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data', 'tier_optimizer')
os.makedirs(DATA_DIR, exist_ok=True)


@dataclass
class ScalingOutcome:
    """Record of a scaling action and its outcome"""
    timestamp: str
    ticket: int
    tier: str
    profit_threshold_triggered: float  # Profit % when tier triggered
    close_pct: float                   # % of position closed
    profit_captured: float             # USD profit from this scale
    remaining_profit: float            # Profit from remaining position (if closed later)
    account_balance: float             # Balance at time of scaling
    volatility_atr: Optional[float] = None
    momentum_adx: Optional[float] = None
    symbol: str = ""
    outcome_score: float = 0.0        # Computed efficiency score


@dataclass  
class TierConfig:
    """Learned configuration for a profit tier"""
    tier_name: str
    profit_threshold_pct: float
    close_pct: float
    confidence: float = 0.5  # 0-1, how confident we are in this config
    sample_count: int = 0
    avg_outcome_score: float = 0.0
    last_updated: str = ""


@dataclass
class OptimizerState:
    """Persistent state for the optimizer"""
    micro_tiers: List[TierConfig] = field(default_factory=list)
    small_tiers: List[TierConfig] = field(default_factory=list)
    standard_tiers: List[TierConfig] = field(default_factory=list)
    outcomes: List[Dict[str, Any]] = field(default_factory=list)
    total_optimizations: int = 0
    last_optimization: str = ""
    version: str = "1.0.0"


class TierOptimizer:
    """
    ML-powered profit tier optimizer.
    
    Learns optimal scaling configurations from historical trades.
    Uses a simple but effective approach:
    1. Track all scaling outcomes
    2. Compute efficiency scores (captured profit vs potential)
    3. Use gradient-free search to find better thresholds
    4. Apply conservative updates (max 10% change per optimization)
    """
    
    # Default tier configurations (starting points)
    DEFAULT_MICRO_TIERS = [
        TierConfig("tier_1", 0.15, 30.0, 0.5, 0, 0.0, ""),
        TierConfig("tier_2", 0.30, 40.0, 0.5, 0, 0.0, ""),
        TierConfig("tier_3", 0.50, 50.0, 0.5, 0, 0.0, ""),
    ]
    
    DEFAULT_SMALL_TIERS = [
        TierConfig("tier_1", 0.20, 30.0, 0.5, 0, 0.0, ""),
        TierConfig("tier_2", 0.40, 35.0, 0.5, 0, 0.0, ""),
        TierConfig("tier_3", 0.70, 50.0, 0.5, 0, 0.0, ""),
    ]
    
    DEFAULT_STANDARD_TIERS = [
        TierConfig("tier_1", 0.30, 25.0, 0.5, 0, 0.0, ""),
        TierConfig("tier_2", 0.60, 35.0, 0.5, 0, 0.0, ""),
        TierConfig("tier_3", 1.00, 50.0, 0.5, 0, 0.0, ""),
    ]
    
    # Optimization constraints
    MIN_PROFIT_THRESHOLD = 0.05    # Minimum 0.05% profit threshold
    MAX_PROFIT_THRESHOLD = 3.0     # Maximum 3% profit threshold
    MIN_CLOSE_PCT = 15.0           # Minimum 15% close
    MAX_CLOSE_PCT = 70.0           # Maximum 70% close
    MAX_ADJUSTMENT_PER_OPT = 0.10  # Max 10% change per optimization
    MIN_SAMPLES_FOR_OPT = 10       # Need at least 10 samples to optimize
    
    def __init__(self, state_file: str = "optimizer_state.json"):
        self.state_file = os.path.join(DATA_DIR, state_file)
        self.state: OptimizerState = self._load_state()
        self._lock = threading.Lock()
        
        # Initialize defaults if empty
        if not self.state.micro_tiers:
            self.state.micro_tiers = [TierConfig(**asdict(t)) for t in self.DEFAULT_MICRO_TIERS]
        if not self.state.small_tiers:
            self.state.small_tiers = [TierConfig(**asdict(t)) for t in self.DEFAULT_SMALL_TIERS]
        if not self.state.standard_tiers:
            self.state.standard_tiers = [TierConfig(**asdict(t)) for t in self.DEFAULT_STANDARD_TIERS]
            
        logger.info(f"TierOptimizer initialized. Outcomes tracked: {len(self.state.outcomes)}")
        
    def _load_state(self) -> OptimizerState:
        """Load optimizer state from disk"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    
                # Reconstruct TierConfig objects
                state = OptimizerState()
                state.micro_tiers = [TierConfig(**t) for t in data.get('micro_tiers', [])]
                state.small_tiers = [TierConfig(**t) for t in data.get('small_tiers', [])]
                state.standard_tiers = [TierConfig(**t) for t in data.get('standard_tiers', [])]
                state.outcomes = data.get('outcomes', [])
                state.total_optimizations = data.get('total_optimizations', 0)
                state.last_optimization = data.get('last_optimization', '')
                state.version = data.get('version', '1.0.0')
                
                return state
        except Exception as e:
            logger.warning(f"Failed to load optimizer state: {e}, starting fresh")
            
        return OptimizerState()
        
    def _save_state(self) -> None:
        """Persist optimizer state to disk"""
        try:
            data = {
                'micro_tiers': [asdict(t) for t in self.state.micro_tiers],
                'small_tiers': [asdict(t) for t in self.state.small_tiers],
                'standard_tiers': [asdict(t) for t in self.state.standard_tiers],
                'outcomes': self.state.outcomes[-1000:],  # Keep last 1000 outcomes
                'total_optimizations': self.state.total_optimizations,
                'last_optimization': self.state.last_optimization,
                'version': self.state.version,
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
                
        except Exception as e:
            logger.error(f"Failed to save optimizer state: {e}")
            
    def record_scaling_outcome(
        self,
        ticket: int,
        tier: str,
        profit_threshold_triggered: float,
        close_pct: float,
        profit_captured: float,
        remaining_profit: float,
        account_balance: float,
        symbol: str = "",
        volatility_atr: Optional[float] = None,
        momentum_adx: Optional[float] = None
    ) -> None:
        """
        Record a scaling action outcome for learning.
        
        Args:
            ticket: Position ticket
            tier: Tier name (tier_1, tier_2, tier_3)
            profit_threshold_triggered: Profit % when tier triggered
            close_pct: Percentage of position closed
            profit_captured: USD profit from this scale
            remaining_profit: Profit from remaining position after full close
            account_balance: Account balance at scaling time
            symbol: Trading symbol
            volatility_atr: ATR at time of scaling
            momentum_adx: ADX at time of scaling
        """
        with self._lock:
            # Compute efficiency score
            total_potential = profit_captured + remaining_profit
            if total_potential > 0:
                # Higher score if we captured good profit without leaving too much on table
                capture_ratio = profit_captured / total_potential if total_potential > 0 else 0
                # Ideal is capturing 40-60% (taking some off, letting rest run)
                ideal_ratio = 0.50
                deviation = abs(capture_ratio - ideal_ratio)
                score = 1.0 - deviation
            else:
                score = 0.5  # Neutral if no profit
                
            outcome = ScalingOutcome(
                timestamp=datetime.now(timezone.utc).isoformat(),
                ticket=ticket,
                tier=tier,
                profit_threshold_triggered=profit_threshold_triggered,
                close_pct=close_pct,
                profit_captured=profit_captured,
                remaining_profit=remaining_profit,
                account_balance=account_balance,
                symbol=symbol,
                volatility_atr=volatility_atr,
                momentum_adx=momentum_adx,
                outcome_score=score
            )
            
            self.state.outcomes.append(asdict(outcome))
            
            # Keep outcomes bounded
            if len(self.state.outcomes) > 2000:
                self.state.outcomes = self.state.outcomes[-1000:]
                
            self._save_state()
            
            logger.debug(f"Recorded scaling outcome: {tier} score={score:.2f}")
            
    def get_optimized_tiers(self, account_balance: float) -> List[Dict[str, float]]:
        """
        Get the current optimized tier configuration.
        
        Args:
            account_balance: Current account balance
            
        Returns:
            List of tier configs: [{profit_threshold_pct, close_pct}, ...]
        """
        if account_balance < 100:
            tiers = self.state.micro_tiers
        elif account_balance < 500:
            tiers = self.state.small_tiers
        else:
            tiers = self.state.standard_tiers
            
        return [
            {
                'profit_threshold_pct': t.profit_threshold_pct,
                'close_pct': t.close_pct,
                'confidence': t.confidence,
            }
            for t in tiers
        ]
        
    def run_optimization(self, account_category: str = "all") -> Dict[str, Any]:
        """
        Run optimization to improve tier configurations.
        
        Uses gradient-free optimization (evolution strategy) to find
        better threshold and close percentage combinations.
        
        Args:
            account_category: "micro", "small", "standard", or "all"
            
        Returns:
            Optimization results summary
        """
        with self._lock:
            results = {'optimized': [], 'skipped': [], 'errors': []}
            
            categories = ['micro', 'small', 'standard'] if account_category == 'all' else [account_category]
            
            for category in categories:
                try:
                    # Get relevant outcomes
                    outcomes = self._filter_outcomes_by_balance(category)
                    
                    if len(outcomes) < self.MIN_SAMPLES_FOR_OPT:
                        results['skipped'].append({
                            'category': category,
                            'reason': f'Insufficient samples ({len(outcomes)}/{self.MIN_SAMPLES_FOR_OPT})'
                        })
                        continue
                        
                    # Get current tiers for this category
                    if category == 'micro':
                        current_tiers = self.state.micro_tiers
                    elif category == 'small':
                        current_tiers = self.state.small_tiers
                    else:
                        current_tiers = self.state.standard_tiers
                        
                    # Optimize each tier
                    for i, tier in enumerate(current_tiers):
                        tier_outcomes = [o for o in outcomes if o.get('tier') == tier.tier_name]
                        
                        if len(tier_outcomes) < 3:
                            continue
                            
                        # Compute optimal adjustments
                        new_threshold, new_close_pct, new_confidence = self._optimize_tier(
                            tier, tier_outcomes
                        )
                        
                        # Apply conservative update
                        old_threshold = tier.profit_threshold_pct
                        old_close_pct = tier.close_pct
                        
                        tier.profit_threshold_pct = self._bounded_update(
                            old_threshold, new_threshold,
                            self.MIN_PROFIT_THRESHOLD, self.MAX_PROFIT_THRESHOLD
                        )
                        tier.close_pct = self._bounded_update(
                            old_close_pct, new_close_pct,
                            self.MIN_CLOSE_PCT, self.MAX_CLOSE_PCT
                        )
                        tier.confidence = new_confidence
                        tier.sample_count = len(tier_outcomes)
                        tier.avg_outcome_score = sum(o.get('outcome_score', 0) for o in tier_outcomes) / len(tier_outcomes)
                        tier.last_updated = datetime.now(timezone.utc).isoformat()
                        
                        results['optimized'].append({
                            'category': category,
                            'tier': tier.tier_name,
                            'threshold': f'{old_threshold:.2f} -> {tier.profit_threshold_pct:.2f}',
                            'close_pct': f'{old_close_pct:.1f} -> {tier.close_pct:.1f}',
                            'samples': len(tier_outcomes),
                            'confidence': tier.confidence
                        })
                        
                except Exception as e:
                    logger.exception(f"Optimization error for {category}")
                    results['errors'].append({'category': category, 'error': str(e)})
                    
            # Update state
            self.state.total_optimizations += 1
            self.state.last_optimization = datetime.now(timezone.utc).isoformat()
            self._save_state()
            
            logger.info(f"Optimization complete: {len(results['optimized'])} tiers updated")
            return results
            
    def _filter_outcomes_by_balance(self, category: str) -> List[Dict[str, Any]]:
        """Filter outcomes by account balance category"""
        if category == 'micro':
            return [o for o in self.state.outcomes if o.get('account_balance', 0) < 100]
        elif category == 'small':
            return [o for o in self.state.outcomes if 100 <= o.get('account_balance', 0) < 500]
        else:
            return [o for o in self.state.outcomes if o.get('account_balance', 0) >= 500]
            
    def _optimize_tier(
        self,
        tier: TierConfig,
        outcomes: List[Dict[str, Any]]
    ) -> Tuple[float, float, float]:
        """
        Optimize a single tier configuration.
        
        Uses a simple evolutionary approach:
        1. Analyze outcome scores by threshold/close_pct buckets
        2. Find direction of improvement
        3. Propose small adjustment in that direction
        
        Returns:
            (new_threshold, new_close_pct, confidence)
        """
        if not outcomes:
            return tier.profit_threshold_pct, tier.close_pct, tier.confidence
            
        # Compute average scores and triggering conditions
        avg_score = sum(o.get('outcome_score', 0) for o in outcomes) / len(outcomes)
        avg_trigger = sum(o.get('profit_threshold_triggered', 0) for o in outcomes) / len(outcomes)
        avg_captured = sum(o.get('profit_captured', 0) for o in outcomes) / len(outcomes)
        avg_remaining = sum(o.get('remaining_profit', 0) for o in outcomes) / len(outcomes)
        
        # Analyze: if remaining profit >> captured, we're closing too early
        # If captured >> remaining, we might be holding too long before scaling
        
        new_threshold = tier.profit_threshold_pct
        new_close_pct = tier.close_pct
        
        if len(outcomes) >= 5:
            # Direction analysis
            if avg_remaining > avg_captured * 1.5:
                # We're leaving too much on the table - let it run more
                new_threshold = tier.profit_threshold_pct * 1.05  # 5% higher threshold
                new_close_pct = tier.close_pct * 0.95  # Close less
            elif avg_captured > avg_remaining * 2:
                # We're taking too much too early
                new_threshold = tier.profit_threshold_pct * 0.97  # 3% lower threshold
                new_close_pct = tier.close_pct * 1.03  # Close more
                
        # Confidence based on sample size and score variance
        score_variance = self._compute_variance([o.get('outcome_score', 0) for o in outcomes])
        confidence = min(0.95, max(0.3, (1.0 - score_variance) * (len(outcomes) / 50)))
        
        return new_threshold, new_close_pct, confidence
        
    def _bounded_update(
        self,
        old_value: float,
        new_value: float,
        min_val: float,
        max_val: float
    ) -> float:
        """Apply bounded conservative update"""
        # Maximum change is MAX_ADJUSTMENT_PER_OPT of current value
        max_change = old_value * self.MAX_ADJUSTMENT_PER_OPT
        
        delta = new_value - old_value
        delta = max(-max_change, min(max_change, delta))
        
        result = old_value + delta
        return max(min_val, min(max_val, result))
        
    def _compute_variance(self, values: List[float]) -> float:
        """Compute variance of values"""
        if len(values) < 2:
            return 0.5
            
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return min(1.0, math.sqrt(variance))
        
    def get_stats(self) -> Dict[str, Any]:
        """Get optimizer statistics"""
        with self._lock:
            recent_outcomes = [
                o for o in self.state.outcomes
                if datetime.fromisoformat(o['timestamp'].replace('Z', '+00:00')) > 
                   datetime.now(timezone.utc) - timedelta(hours=24)
            ]
            
            return {
                'total_outcomes': len(self.state.outcomes),
                'recent_outcomes_24h': len(recent_outcomes),
                'total_optimizations': self.state.total_optimizations,
                'last_optimization': self.state.last_optimization,
                'micro_tiers': [asdict(t) for t in self.state.micro_tiers],
                'small_tiers': [asdict(t) for t in self.state.small_tiers],
                'standard_tiers': [asdict(t) for t in self.state.standard_tiers],
                'avg_score': sum(o.get('outcome_score', 0) for o in self.state.outcomes) / max(1, len(self.state.outcomes)),
            }
            
    def reset(self) -> None:
        """Reset to default configurations"""
        with self._lock:
            self.state.micro_tiers = [TierConfig(**asdict(t)) for t in self.DEFAULT_MICRO_TIERS]
            self.state.small_tiers = [TierConfig(**asdict(t)) for t in self.DEFAULT_SMALL_TIERS]
            self.state.standard_tiers = [TierConfig(**asdict(t)) for t in self.DEFAULT_STANDARD_TIERS]
            self.state.outcomes = []
            self.state.total_optimizations = 0
            self._save_state()
            logger.info("TierOptimizer reset to defaults")


# Singleton instance for global access
_optimizer_instance: Optional[TierOptimizer] = None


def get_tier_optimizer() -> TierOptimizer:
    """Get or create the global TierOptimizer instance"""
    global _optimizer_instance
    if _optimizer_instance is None:
        _optimizer_instance = TierOptimizer()
    return _optimizer_instance


def record_scaling_outcome(**kwargs) -> None:
    """Convenience function to record a scaling outcome"""
    get_tier_optimizer().record_scaling_outcome(**kwargs)


def get_optimized_tiers(account_balance: float) -> List[Dict[str, float]]:
    """Convenience function to get optimized tiers"""
    return get_tier_optimizer().get_optimized_tiers(account_balance)


def run_tier_optimization(account_category: str = "all") -> Dict[str, Any]:
    """Convenience function to run optimization"""
    return get_tier_optimizer().run_optimization(account_category)
