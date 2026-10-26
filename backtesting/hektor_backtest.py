"""
Hektor-Enhanced Backtesting

Stores backtest results in Hektor for semantic search and comparison.
"""

import logging
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class HektorBacktest:
    """
    Hektor-enhanced backtesting module.
    
    Stores backtest results in vector database for:
    - Semantic search across backtest configurations
    - Finding similar backtest results
    - Configuration optimization history
    - Pattern matching between live and backtest performance
    """
    
    def __init__(self, vector_adapter=None, embedder=None):
        """
        Initialize Hektor backtest integration.
        
        Args:
            vector_adapter: VectorStudioAdapter instance
            embedder: TradeEmbedder instance
        """
        self.vector_adapter = vector_adapter
        self.embedder = embedder
        self.logger = logging.getLogger(__name__)
        
    def store_backtest_result(
        self,
        config: Dict[str, Any],
        result: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[int]:
        """
        Store backtest result in Hektor.
        
        Args:
            config: Backtest configuration
            result: Backtest results
            metadata: Additional metadata
            
        Returns:
            Vector ID if successful
        """
        if not self.vector_adapter:
            self.logger.warning("No vector adapter available")
            return None
            
        try:
            # Build text representation
            text = self._build_backtest_text(config, result)
            
            # Prepare metadata
            full_metadata = {
                'type': 'backtest_result',
                'timestamp': datetime.now().isoformat(),
                'config': config,
                'sharpe_ratio': result.get('sharpe_ratio', 0.0),
                'total_return': result.get('total_return', 0.0),
                'max_drawdown': result.get('max_drawdown', 0.0),
                'win_rate': result.get('win_rate', 0.0),
                'total_trades': result.get('total_trades', 0),
                **(metadata or {})
            }
            
            # Store in Hektor
            vector_id = self.vector_adapter.store_signal(
                signal=None,  # Not a real signal
                context={'text': text, 'metadata': full_metadata}
            )
            
            if vector_id:
                self.logger.info(f"Stored backtest result with vector ID: {vector_id}")
            
            return vector_id
            
        except Exception as e:
            self.logger.error(f"Error storing backtest result: {e}", exc_info=True)
            return None
    
    def find_similar_backtests(
        self,
        config: Dict[str, Any],
        k: int = 10,
        min_score: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Find similar backtest configurations.
        
        Args:
            config: Current configuration
            k: Number of results
            min_score: Minimum similarity score
            
        Returns:
            List of similar backtest results
        """
        if not self.vector_adapter:
            return []
            
        try:
            # Build query from config
            query = self._build_config_query(config)
            
            # Search Hektor
            contexts = self.vector_adapter.find_similar_contexts(
                query=query,
                k=k,
                min_score=min_score,
                filters={'type': 'backtest_result'}
            )
            
            # Parse results
            results = []
            for ctx in contexts:
                result = {
                    'similarity_score': ctx.score,
                    'config': ctx.metadata.get('config', {}),
                    'sharpe_ratio': ctx.metadata.get('sharpe_ratio', 0.0),
                    'total_return': ctx.metadata.get('total_return', 0.0),
                    'max_drawdown': ctx.metadata.get('max_drawdown', 0.0),
                    'win_rate': ctx.metadata.get('win_rate', 0.0),
                    'total_trades': ctx.metadata.get('total_trades', 0),
                    'timestamp': ctx.metadata.get('timestamp', '')
                }
                results.append(result)
                
            self.logger.info(f"Found {len(results)} similar backtests")
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error finding similar backtests: {e}")
            return []
    
    def get_best_configurations(
        self,
        metric: str = 'sharpe_ratio',
        k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get best performing configurations from history.
        
        Args:
            metric: Metric to optimize (sharpe_ratio, total_return, etc.)
            k: Number of results
            
        Returns:
            List of best configurations
        """
        if not self.vector_adapter:
            return []
            
        try:
            # Query all backtest results
            query = "[Backtest] High performance configuration"
            
            contexts = self.vector_adapter.find_similar_contexts(
                query=query,
                k=100,  # Get more to sort
                min_score=0.0,
                filters={'type': 'backtest_result'}
            )
            
            # Parse and sort by metric
            results = []
            for ctx in contexts:
                result = {
                    'config': ctx.metadata.get('config', {}),
                    'sharpe_ratio': ctx.metadata.get('sharpe_ratio', 0.0),
                    'total_return': ctx.metadata.get('total_return', 0.0),
                    'max_drawdown': ctx.metadata.get('max_drawdown', 0.0),
                    'win_rate': ctx.metadata.get('win_rate', 0.0),
                    'total_trades': ctx.metadata.get('total_trades', 0),
                    'timestamp': ctx.metadata.get('timestamp', '')
                }
                results.append(result)
                
            # Sort by metric
            results.sort(key=lambda x: x.get(metric, 0.0), reverse=True)
            
            # Return top k
            best = results[:k]
            
            self.logger.info(
                f"Retrieved {len(best)} best configurations by {metric}"
            )
            
            return best
            
        except Exception as e:
            self.logger.error(f"Error getting best configurations: {e}")
            return []
    
    def compare_live_vs_backtest(
        self,
        live_performance: Dict[str, Any],
        backtest_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Compare live trading performance with backtest results.
        
        Args:
            live_performance: Live trading metrics
            backtest_id: Specific backtest to compare (None = find similar)
            
        Returns:
            Comparison analysis
        """
        try:
            if backtest_id:
                # Compare with specific backtest
                # TODO: Retrieve specific backtest by ID
                backtest_result = {}
            else:
                # Find similar backtest configuration
                similar = self.find_similar_backtests(
                    config=live_performance.get('config', {}),
                    k=1
                )
                
                if not similar:
                    return {'error': 'No similar backtests found'}
                    
                backtest_result = similar[0]
                
            # Calculate differences
            comparison = {
                'live': live_performance,
                'backtest': backtest_result,
                'differences': {
                    'sharpe_ratio_diff': (
                        live_performance.get('sharpe_ratio', 0) -
                        backtest_result.get('sharpe_ratio', 0)
                    ),
                    'return_diff': (
                        live_performance.get('total_return', 0) -
                        backtest_result.get('total_return', 0)
                    ),
                    'drawdown_diff': (
                        live_performance.get('max_drawdown', 0) -
                        backtest_result.get('max_drawdown', 0)
                    ),
                    'win_rate_diff': (
                        live_performance.get('win_rate', 0) -
                        backtest_result.get('win_rate', 0)
                    )
                },
                'analysis': self._analyze_differences(live_performance, backtest_result)
            }
            
            return comparison
            
        except Exception as e:
            self.logger.error(f"Error comparing live vs backtest: {e}")
            return {'error': str(e)}
    
    # Private methods
    
    def _build_backtest_text(
        self,
        config: Dict[str, Any],
        result: Dict[str, Any]
    ) -> str:
        """Build text representation of backtest for embedding"""
        text = "[Backtest Result]\n"
        
        # Configuration summary
        text += f"Initial Capital: ${config.get('initial_capital', 0):.2f}\n"
        text += f"Commission: {config.get('commission', 0):.4f}\n"
        text += f"Slippage: {config.get('slippage_pct', 0):.4f}\n"
        
        # Strategy info
        strategies = config.get('strategies', [])
        if strategies:
            text += f"Strategies: {', '.join(s.get('type', 'unknown') for s in strategies)}\n"
            
        # Results
        text += f"\nPerformance:\n"
        text += f"Sharpe Ratio: {result.get('sharpe_ratio', 0):.2f}\n"
        text += f"Total Return: {result.get('total_return', 0):.2%}\n"
        text += f"Max Drawdown: {result.get('max_drawdown', 0):.2%}\n"
        text += f"Win Rate: {result.get('win_rate', 0):.2%}\n"
        text += f"Total Trades: {result.get('total_trades', 0)}\n"
        
        return text
    
    def _build_config_query(self, config: Dict[str, Any]) -> str:
        """Build query from configuration"""
        query = "[Backtest] Configuration:\n"
        
        query += f"Capital: ${config.get('initial_capital', 0):.0f}\n"
        
        strategies = config.get('strategies', [])
        if strategies:
            query += f"Strategies: {', '.join(s.get('type', 'unknown') for s in strategies)}\n"
            
        return query
    
    def _analyze_differences(
        self,
        live: Dict[str, Any],
        backtest: Dict[str, Any]
    ) -> str:
        """Analyze differences between live and backtest"""
        analysis = []
        
        # Sharpe ratio
        sharpe_diff = live.get('sharpe_ratio', 0) - backtest.get('sharpe_ratio', 0)
        if abs(sharpe_diff) > 0.5:
            if sharpe_diff > 0:
                analysis.append("Live Sharpe ratio significantly better than backtest")
            else:
                analysis.append("Live Sharpe ratio significantly worse than backtest")
                
        # Return
        return_diff = live.get('total_return', 0) - backtest.get('total_return', 0)
        if abs(return_diff) > 0.1:  # 10% difference
            if return_diff > 0:
                analysis.append("Live returns outperforming backtest")
            else:
                analysis.append("Live returns underperforming backtest")
                
        # Drawdown
        dd_diff = live.get('max_drawdown', 0) - backtest.get('max_drawdown', 0)
        if abs(dd_diff) > 0.05:  # 5% difference
            if dd_diff > 0:
                analysis.append("Live drawdown worse than backtest - review risk management")
            else:
                analysis.append("Live drawdown better than backtest")
                
        # Win rate
        wr_diff = live.get('win_rate', 0) - backtest.get('win_rate', 0)
        if abs(wr_diff) > 0.1:  # 10% difference
            if wr_diff > 0:
                analysis.append("Live win rate better than backtest")
            else:
                analysis.append("Live win rate worse than backtest - review entry logic")
                
        if not analysis:
            analysis.append("Live performance closely matches backtest expectations")
            
        return "; ".join(analysis)
