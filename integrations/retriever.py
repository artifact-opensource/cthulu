"""
Context Retriever

Retrieves relevant historical contexts from Vector Studio for 
decision-making enhancement in the cognition engine.
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class SimilarContext:
    """A retrieved similar historical context."""
    vector_id: int
    score: float
    content: str
    metadata: Dict[str, Any]
    trade_outcome: Optional[str] = None  # WIN, LOSS, BREAKEVEN
    pnl: Optional[float] = None


class ContextRetriever:
    """
    Retrieves relevant historical contexts for decision-making.
    
    Queries Vector Studio to find similar historical signals,
    trades, and market conditions to enhance trading decisions.
    """
    
    def __init__(self, adapter, embedder=None):
        """
        Initialize retriever.
        
        Args:
            adapter: VectorStudioAdapter instance
            embedder: TradeEmbedder instance (optional, will create if None)
        """
        self.adapter = adapter
        self.logger = logging.getLogger("cthulu.integrations.retriever")
        
        if embedder is None:
            from .embedder import TradeEmbedder
            embedder = TradeEmbedder()
        self.embedder = embedder
    
    def get_similar_signals(
        self,
        current_signal: Any,
        indicators: Dict[str, Any],
        regime: str,
        k: int = 5,
        min_score: float = 0.7
    ) -> List[SimilarContext]:
        """
        Find similar historical signals and their outcomes.
        
        Args:
            current_signal: Current trading signal
            indicators: Current indicator values
            regime: Market regime
            k: Number of results to return
            min_score: Minimum similarity score
        
        Returns:
            List of similar historical signals with outcomes
        """
        if not self.adapter.is_healthy():
            return []
        
        try:
            # Build query from current signal
            query = self.embedder.signal_to_text(current_signal, indicators, regime)
            
            # Search Vector Studio
            results = self.adapter.find_similar_contexts(
                query=query,
                k=k * 2,  # Get more to filter
                min_score=min_score,
                filters={"doc_type": "signal"}
            )
            
            # Convert to SimilarContext
            contexts = []
            for result in results[:k]:
                metadata = result.get("metadata", {})
                contexts.append(SimilarContext(
                    vector_id=result.get("id", 0),
                    score=result.get("score", 0.0),
                    content=result.get("content", result.get("text", "")),
                    metadata=metadata,
                    trade_outcome=metadata.get("result"),
                    pnl=metadata.get("pnl")
                ))
            
            return contexts
            
        except Exception as e:
            self.logger.warning(f"Failed to get similar signals: {e}")
            return []
    
    def get_regime_contexts(
        self,
        regime: str,
        symbol: str,
        k: int = 10,
        min_score: float = 0.6
    ) -> List[SimilarContext]:
        """
        Find contexts from similar market regimes.
        
        Args:
            regime: Market regime to search for
            symbol: Trading symbol
            k: Number of results
            min_score: Minimum similarity score
        
        Returns:
            List of contexts from similar regimes
        """
        if not self.adapter.is_healthy():
            return []
        
        try:
            query = f"Market regime {regime} for {symbol}. Historical trade outcomes and patterns."
            
            results = self.adapter.find_similar_contexts(
                query=query,
                k=k,
                min_score=min_score,
                filters={"symbol": symbol}
            )
            
            contexts = []
            for result in results:
                metadata = result.get("metadata", {})
                contexts.append(SimilarContext(
                    vector_id=result.get("id", 0),
                    score=result.get("score", 0.0),
                    content=result.get("content", result.get("text", "")),
                    metadata=metadata,
                    trade_outcome=metadata.get("result"),
                    pnl=metadata.get("pnl")
                ))
            
            return contexts
            
        except Exception as e:
            self.logger.warning(f"Failed to get regime contexts: {e}")
            return []
    
    def get_pattern_matches(
        self,
        pattern_description: str,
        timeframe: str,
        k: int = 5,
        min_score: float = 0.7
    ) -> List[SimilarContext]:
        """
        Find trades with similar chart patterns.
        
        Args:
            pattern_description: Description of the pattern
            timeframe: Timeframe to filter by
            k: Number of results
            min_score: Minimum similarity score
        
        Returns:
            List of trades with similar patterns
        """
        if not self.adapter.is_healthy():
            return []
        
        try:
            query = f"Chart pattern: {pattern_description}. Timeframe: {timeframe}. Historical outcomes."
            
            results = self.adapter.find_similar_contexts(
                query=query,
                k=k,
                min_score=min_score
            )
            
            contexts = []
            for result in results:
                metadata = result.get("metadata", {})
                contexts.append(SimilarContext(
                    vector_id=result.get("id", 0),
                    score=result.get("score", 0.0),
                    content=result.get("content", result.get("text", "")),
                    metadata=metadata,
                    trade_outcome=metadata.get("result"),
                    pnl=metadata.get("pnl")
                ))
            
            return contexts
            
        except Exception as e:
            self.logger.warning(f"Failed to get pattern matches: {e}")
            return []
    
    def get_winning_contexts(
        self,
        symbol: str,
        regime: str,
        k: int = 5
    ) -> List[SimilarContext]:
        """
        Get historical winning trade contexts for given conditions.
        
        Args:
            symbol: Trading symbol
            regime: Current market regime
            k: Number of results
        
        Returns:
            List of winning trade contexts
        """
        if not self.adapter.is_healthy():
            return []
        
        try:
            query = f"Winning trades for {symbol} in {regime} regime. Profitable outcomes."
            
            results = self.adapter.find_similar_contexts(
                query=query,
                k=k * 2,
                min_score=0.5,
                filters={"symbol": symbol, "result": "WIN"}
            )
            
            contexts = []
            for result in results[:k]:
                metadata = result.get("metadata", {})
                if metadata.get("result") == "WIN":
                    contexts.append(SimilarContext(
                        vector_id=result.get("id", 0),
                        score=result.get("score", 0.0),
                        content=result.get("content", result.get("text", "")),
                        metadata=metadata,
                        trade_outcome="WIN",
                        pnl=metadata.get("pnl")
                    ))
            
            return contexts
            
        except Exception as e:
            self.logger.warning(f"Failed to get winning contexts: {e}")
            return []
    
    def format_context_window(
        self,
        contexts: List[SimilarContext],
        max_chars: int = 4000
    ) -> str:
        """
        Format contexts into a context window for cognition.
        
        Args:
            contexts: List of similar contexts
            max_chars: Maximum characters in output
        
        Returns:
            Formatted context window string
        """
        if not contexts:
            return "No similar historical contexts found."
        
        lines = ["--- Historical Context ---"]
        current_length = len(lines[0])
        
        for i, ctx in enumerate(contexts, 1):
            outcome_str = ""
            if ctx.trade_outcome:
                outcome_str = f" | Outcome: {ctx.trade_outcome}"
                if ctx.pnl is not None:
                    outcome_str += f" ({ctx.pnl:+.2f})"
            
            header = f"\n[{i}] Score: {ctx.score:.2f}{outcome_str}"
            content = ctx.content[:500]  # Truncate long content
            
            entry = f"{header}\n{content}\n"
            
            if current_length + len(entry) > max_chars:
                break
            
            lines.append(entry)
            current_length += len(entry)
        
        lines.append("--- End Context ---")
        
        return "\n".join(lines)
    
    def analyze_historical_performance(
        self,
        current_state: Dict[str, Any],
        k: int = 20
    ) -> Dict[str, Any]:
        """
        Analyze historical performance for similar conditions.
        
        Args:
            current_state: Current market state
            k: Number of contexts to analyze
        
        Returns:
            Performance analysis dictionary
        """
        if not self.adapter.is_healthy():
            return {"available": False, "reason": "Vector Studio unavailable"}
        
        try:
            query = self.embedder.build_query(current_state)
            
            results = self.adapter.find_similar_contexts(
                query=query,
                k=k,
                min_score=0.5
            )
            
            if not results:
                return {"available": True, "sample_size": 0}
            
            # Analyze outcomes
            wins = 0
            losses = 0
            breakeven = 0
            total_pnl = 0.0
            
            for result in results:
                metadata = result.get("metadata", {})
                outcome = metadata.get("result", "")
                pnl = metadata.get("pnl", 0)
                
                if outcome == "WIN":
                    wins += 1
                elif outcome == "LOSS":
                    losses += 1
                else:
                    breakeven += 1
                
                if isinstance(pnl, (int, float)):
                    total_pnl += pnl
            
            total = wins + losses + breakeven
            win_rate = (wins / total * 100) if total > 0 else 0
            avg_pnl = total_pnl / total if total > 0 else 0
            
            return {
                "available": True,
                "sample_size": total,
                "wins": wins,
                "losses": losses,
                "breakeven": breakeven,
                "win_rate": win_rate,
                "total_pnl": total_pnl,
                "avg_pnl": avg_pnl,
                "recommendation": "FAVORABLE" if win_rate >= 55 else "CAUTION" if win_rate >= 45 else "UNFAVORABLE"
            }
            
        except Exception as e:
            self.logger.warning(f"Failed to analyze historical performance: {e}")
            return {"available": False, "reason": str(e)}
