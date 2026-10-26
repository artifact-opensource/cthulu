"""
Unified Data Layer

Provides a single interface for all data persistence in Cthulu.
Manages both SQLite (primary/fallback) and Vector Studio (semantic memory).
Ensures graceful degradation when Vector Studio is unavailable.
"""

import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .vector_studio import VectorStudioAdapter, VectorStudioConfig, VectorStudioError
from .embedder import TradeEmbedder
from .retriever import ContextRetriever, SimilarContext


@dataclass
class DataLayerConfig:
    """Configuration for the unified data layer."""
    
    # SQLite config
    sqlite_path: str = "cthulu.db"
    
    # Vector Studio config
    vector_studio_enabled: bool = True
    vector_studio_path: str = "./vectors/cthulu_memory"
    vector_studio_fallback: bool = True
    
    # Performance settings
    async_vector_writes: bool = True
    cache_embeddings: bool = True
    
    # Semantic search settings
    default_search_k: int = 10
    min_similarity_score: float = 0.7


class UnifiedDataLayer:
    """
    Unified data persistence layer for Cthulu.
    
    Manages:
    - SQLite: Primary persistence for trades, signals, positions
    - Vector Studio: Semantic memory for context retrieval
    - Fallback: Graceful degradation when Vector Studio unavailable
    
    The system ALWAYS works - Vector Studio is an enhancement,
    not a requirement.
    """
    
    def __init__(self, config: Optional[DataLayerConfig] = None):
        """
        Initialize the unified data layer.
        
        Args:
            config: Data layer configuration
        """
        self.config = config or DataLayerConfig()
        self.logger = logging.getLogger("cthulu.data.unified")
        
        self._sqlite_db = None
        self._vector_adapter: Optional[VectorStudioAdapter] = None
        self._embedder: Optional[TradeEmbedder] = None
        self._retriever: Optional[ContextRetriever] = None
        
        self._initialized = False
        self._vector_available = False
    
    def initialize(self) -> bool:
        """
        Initialize all data stores.
        
        Returns:
            True if SQLite initialized (Vector Studio is optional)
        """
        success = True
        
        # Initialize SQLite (REQUIRED)
        try:
            from persistence.database import Database
            self._sqlite_db = Database(self.config.sqlite_path)
            self.logger.info(f"SQLite initialized: {self.config.sqlite_path}")
        except Exception as e:
            self.logger.error(f"SQLite initialization failed: {e}")
            success = False
        
        # Initialize Vector Studio (OPTIONAL)
        if self.config.vector_studio_enabled:
            try:
                vs_config = VectorStudioConfig(
                    enabled=True,
                    database_path=self.config.vector_studio_path,
                    fallback_on_failure=self.config.vector_studio_fallback,
                    async_writes=self.config.async_vector_writes,
                    cache_embeddings=self.config.cache_embeddings,
                )
                
                self._vector_adapter = VectorStudioAdapter(vs_config)
                self._vector_available = self._vector_adapter.connect()
                
                if self._vector_available:
                    self._embedder = TradeEmbedder()
                    self._retriever = ContextRetriever(
                        self._vector_adapter,
                        self._embedder
                    )
                    
                    if self._vector_adapter.is_using_fallback():
                        self.logger.warning("Vector Studio using SQLite fallback")
                    else:
                        self.logger.info("Vector Studio connected successfully")
                else:
                    self.logger.warning("Vector Studio unavailable - semantic features disabled")
                    
            except Exception as e:
                self.logger.warning(f"Vector Studio initialization failed: {e}")
                self._vector_available = False
        
        self._initialized = success
        return success
    
    # ========== SQLite Operations (Always Available) ==========
    
    def record_signal(self, signal) -> int:
        """
        Record a trading signal.
        
        Args:
            signal: SignalRecord instance
        
        Returns:
            Database row ID
        """
        if self._sqlite_db is None:
            return -1
        
        row_id = self._sqlite_db.record_signal(signal)
        
        # Also store in Vector Studio for semantic search
        if self._vector_available and self._vector_adapter:
            try:
                context = {
                    "symbol": signal.symbol,
                    "regime": getattr(signal, "regime", "UNKNOWN"),
                    "indicators": {},
                }
                self._vector_adapter.store_signal(signal, context)
            except Exception as e:
                self.logger.debug(f"Vector signal storage failed: {e}")
        
        return row_id
    
    def record_trade(self, trade) -> int:
        """
        Record a trade entry.
        
        Args:
            trade: TradeRecord instance
        
        Returns:
            Database row ID
        """
        if self._sqlite_db is None:
            return -1
        
        return self._sqlite_db.record_trade(trade)
    
    def record_trade_completion(self, trade, outcome: Dict[str, Any]) -> bool:
        """
        Record a completed trade with outcome.
        
        Args:
            trade: Trade record
            outcome: Trade outcome (pnl, exit_reason, etc.)
        
        Returns:
            True if recorded successfully
        """
        # Update SQLite
        if self._sqlite_db:
            self._sqlite_db.update_trade_exit(
                order_id=getattr(trade, "order_id", 0),
                exit_price=outcome.get("exit_price", 0),
                exit_time=outcome.get("exit_time", datetime.now()),
                profit=outcome.get("pnl", 0),
                exit_reason=outcome.get("exit_reason", "")
            )
        
        # Store in Vector Studio for learning
        if self._vector_available and self._vector_adapter:
            try:
                self._vector_adapter.store_trade(trade, outcome)
            except Exception as e:
                self.logger.debug(f"Vector trade storage failed: {e}")
        
        return True
    
    def save_position(self, **kwargs) -> bool:
        """Save or update a position."""
        if self._sqlite_db is None:
            return False
        return self._sqlite_db.save_position(**kwargs)
    
    def update_position_price(self, ticket: int, current_price: float, profit: float) -> bool:
        """Update position current price and profit."""
        if self._sqlite_db is None:
            return False
        return self._sqlite_db.update_position_price(ticket, current_price, profit)
    
    def remove_position(self, ticket: int) -> bool:
        """Remove a closed position."""
        if self._sqlite_db is None:
            return False
        return self._sqlite_db.remove_position(ticket)
    
    def get_positions(self, status: str = "open") -> List[Dict[str, Any]]:
        """Get positions by status."""
        if self._sqlite_db is None:
            return []
        return self._sqlite_db.get_positions(status)
    
    def get_open_trades(self):
        """Get all open trades."""
        if self._sqlite_db is None:
            return []
        return self._sqlite_db.get_open_trades()
    
    def get_all_trades(self, limit: int = 100):
        """Get all trades."""
        if self._sqlite_db is None:
            return []
        return self._sqlite_db.get_all_trades(limit)
    
    def record_metric(self, name: str, value: float, metadata: str = "") -> bool:
        """Record a performance metric."""
        if self._sqlite_db is None:
            return False
        return self._sqlite_db.record_metric(name, value, metadata)
    
    def record_provenance(self, provenance: Dict[str, Any]) -> int:
        """Record order provenance."""
        if self._sqlite_db is None:
            return -1
        return self._sqlite_db.record_provenance(provenance)
    
    # ========== Semantic Memory Operations (Vector Studio) ==========
    
    def is_semantic_available(self) -> bool:
        """Check if semantic memory features are available."""
        return self._vector_available and self._vector_adapter is not None
    
    def find_similar_signals(
        self,
        current_signal,
        indicators: Dict[str, Any],
        regime: str,
        k: int = 5
    ) -> List[SimilarContext]:
        """
        Find similar historical signals.
        
        Falls back to empty list if Vector Studio unavailable.
        """
        if not self._retriever:
            return []
        
        return self._retriever.get_similar_signals(
            current_signal, indicators, regime, k
        )
    
    def find_regime_contexts(
        self,
        regime: str,
        symbol: str,
        k: int = 10
    ) -> List[SimilarContext]:
        """
        Find contexts from similar market regimes.
        
        Falls back to empty list if Vector Studio unavailable.
        """
        if not self._retriever:
            return []
        
        return self._retriever.get_regime_contexts(regime, symbol, k)
    
    def find_winning_patterns(
        self,
        symbol: str,
        regime: str,
        k: int = 5
    ) -> List[SimilarContext]:
        """
        Find historical winning trade patterns.
        
        Falls back to empty list if Vector Studio unavailable.
        """
        if not self._retriever:
            return []
        
        return self._retriever.get_winning_contexts(symbol, regime, k)
    
    def analyze_historical_performance(
        self,
        current_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze historical performance for similar conditions.
        
        Falls back to unavailable status if Vector Studio unavailable.
        """
        if not self._retriever:
            return {"available": False, "reason": "Semantic memory not available"}
        
        return self._retriever.analyze_historical_performance(current_state)
    
    def get_context_window(
        self,
        current_signal,
        indicators: Dict[str, Any],
        regime: str,
        max_chars: int = 4000
    ) -> str:
        """
        Get formatted context window for cognition enhancement.
        
        Falls back to empty context if Vector Studio unavailable.
        """
        if not self._retriever:
            return "Semantic memory unavailable - using default cognition."
        
        contexts = self._retriever.get_similar_signals(
            current_signal, indicators, regime, k=5
        )
        
        return self._retriever.format_context_window(contexts, max_chars)
    
    # ========== Health & Status ==========
    
    def get_status(self) -> Dict[str, Any]:
        """Get status of all data stores."""
        status = {
            "initialized": self._initialized,
            "sqlite": {
                "available": self._sqlite_db is not None,
                "path": self.config.sqlite_path
            },
            "vector_studio": {
                "enabled": self.config.vector_studio_enabled,
                "available": self._vector_available,
                "using_fallback": False,
                "path": self.config.vector_studio_path
            },
            "semantic_features": self.is_semantic_available()
        }
        
        if self._vector_adapter:
            status["vector_studio"]["using_fallback"] = self._vector_adapter.is_using_fallback()
            status["vector_studio"]["stats"] = self._vector_adapter.get_stats()
        
        return status
    
    def is_healthy(self) -> bool:
        """
        Check if data layer is healthy.
        
        SQLite must be healthy. Vector Studio is optional.
        """
        return self._sqlite_db is not None
    
    def sync_fallback(self) -> int:
        """
        Sync fallback data to Vector Studio if available.
        
        Returns:
            Number of items synced
        """
        if self._vector_adapter:
            return self._vector_adapter.sync_fallback_to_vector_studio()
        return 0
    
    # ========== Cleanup ==========
    
    def close(self):
        """Close all data stores."""
        if self._sqlite_db:
            self._sqlite_db.close()
            self._sqlite_db = None
        
        if self._vector_adapter:
            self._vector_adapter.close()
            self._vector_adapter = None
        
        self._initialized = False
        self._vector_available = False
        
        self.logger.info("Data layer closed")


# Convenience function for creating configured data layer
def create_data_layer(
    sqlite_path: str = "cthulu.db",
    enable_vector_studio: bool = True,
    vector_path: str = "./vectors/cthulu_memory"
) -> UnifiedDataLayer:
    """
    Create and initialize a data layer.
    
    Args:
        sqlite_path: Path to SQLite database
        enable_vector_studio: Whether to enable Vector Studio
        vector_path: Path to Vector Studio storage
    
    Returns:
        Initialized UnifiedDataLayer
    """
    config = DataLayerConfig(
        sqlite_path=sqlite_path,
        vector_studio_enabled=enable_vector_studio,
        vector_studio_path=vector_path
    )
    
    layer = UnifiedDataLayer(config)
    layer.initialize()
    
    return layer
