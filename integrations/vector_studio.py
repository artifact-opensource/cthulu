"""
Vector Studio Adapter

Manages connection to Vector Studio (Hecktor) vector database.
Provides graceful fallback to SQLite when Vector Studio is unavailable.
"""

import logging
import json
import threading
import queue
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime


@dataclass
class VectorStudioConfig:
    """Configuration for Vector Studio integration."""
    
    enabled: bool = True
    database_path: str = "./vectors/cthulu_memory"
    dimension: int = 512
    
    # HNSW parameters
    hnsw_m: int = 16
    hnsw_ef_construction: int = 200
    hnsw_ef_search: int = 50
    
    # Retrieval parameters
    default_k: int = 10
    min_similarity_score: float = 0.7
    max_context_age_days: int = 90
    
    # Performance
    batch_size: int = 100
    async_writes: bool = True
    cache_embeddings: bool = True
    
    # Resilience
    connection_timeout_ms: int = 5000
    retry_attempts: int = 3
    fallback_on_failure: bool = True


class VectorStudioError(Exception):
    """Exception raised when Vector Studio operations fail."""
    pass


class VectorStudioAdapter:
    """
    Manages connection to Vector Studio database.
    
    Provides automatic fallback to SQLite-based storage when
    Vector Studio is unavailable, ensuring Cthulu can always operate.
    """
    
    def __init__(self, config: VectorStudioConfig):
        """
        Initialize adapter with configuration.
        
        Args:
            config: Vector Studio configuration
        """
        self.config = config
        self.logger = logging.getLogger("cthulu.integrations.vector_studio")
        self._connected = False
        self._db = None
        self._using_fallback = False
        self._write_queue: queue.Queue = queue.Queue()
        self._writer_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        
        # Fallback SQLite connection
        self._fallback_db = None
        
    def connect(self) -> bool:
        """
        Establish connection to Vector Studio.
        
        Returns:
            True if connected successfully (to Vector Studio or fallback)
        """
        if not self.config.enabled:
            self.logger.info("Vector Studio integration disabled by config")
            return self._init_fallback()
        
        try:
            # Attempt to import and connect to Vector Studio
            self._db = self._connect_vector_studio()
            self._connected = True
            self._using_fallback = False
            self.logger.info(f"Connected to Vector Studio: {self.config.database_path}")
            
            # Start async writer thread if enabled
            if self.config.async_writes:
                self._start_writer_thread()
            
            return True
            
        except Exception as e:
            self.logger.warning(f"Vector Studio connection failed: {e}")
            
            if self.config.fallback_on_failure:
                self.logger.info("Falling back to SQLite storage")
                return self._init_fallback()
            
            return False
    
    def _connect_vector_studio(self):
        """
        Attempt to connect to Vector Studio.
        
        Returns:
            Vector Studio database instance
        
        Raises:
            VectorStudioError: If connection fails
        """
        try:
            import pyvdb
            
            db_path = Path(self.config.database_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if database already exists
            db_index_file = db_path / "index.bin"  # pyvdb creates this file
            
            if db_path.exists() and (db_index_file.exists() or any(db_path.glob("*.bin"))):
                # Open existing database
                db = pyvdb.open_database(str(db_path))
                self.logger.info(f"Opened existing Vector Studio database at {db_path}")
            else:
                # Create new database (uses optimized defaults)
                db_path.mkdir(parents=True, exist_ok=True)
                db = pyvdb.create_gold_standard_db(str(db_path))
                db.init()
                self.logger.info(f"Created new Vector Studio database at {db_path}")
            
            if not db.is_ready():
                db.init()
            
            return db
            
        except ImportError:
            raise VectorStudioError("pyvdb module not installed. Install with: pip install pyvdb")
        except Exception as e:
            raise VectorStudioError(f"Failed to connect to Vector Studio: {e}")
    
    def _init_fallback(self) -> bool:
        """
        Initialize SQLite fallback storage.
        
        Returns:
            True if fallback initialized successfully
        """
        try:
            import sqlite3
            
            fallback_path = Path("./data/vector_fallback.db")
            fallback_path.parent.mkdir(parents=True, exist_ok=True)
            
            self._fallback_db = sqlite3.connect(
                str(fallback_path),
                check_same_thread=False,
                timeout=30.0
            )
            self._fallback_db.row_factory = sqlite3.Row
            self._fallback_db.execute("PRAGMA journal_mode=WAL")
            
            # Create fallback tables
            self._fallback_db.execute("""
                CREATE TABLE IF NOT EXISTS vector_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    synced BOOLEAN DEFAULT FALSE
                )
            """)
            
            self._fallback_db.execute("""
                CREATE TABLE IF NOT EXISTS semantic_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_hash TEXT UNIQUE NOT NULL,
                    query_text TEXT NOT NULL,
                    results TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP
                )
            """)
            
            self._fallback_db.execute("""
                CREATE INDEX IF NOT EXISTS idx_queue_synced 
                ON vector_queue(synced)
            """)
            
            self._fallback_db.commit()
            
            self._using_fallback = True
            self._connected = True
            self.logger.info("SQLite fallback storage initialized")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize SQLite fallback: {e}")
            return False
    
    def _start_writer_thread(self):
        """Start background thread for async writes."""
        if self._writer_thread is not None and self._writer_thread.is_alive():
            return
        
        self._shutdown_event.clear()
        self._writer_thread = threading.Thread(
            target=self._writer_loop,
            name="VectorStudioWriter",
            daemon=True
        )
        self._writer_thread.start()
        self.logger.debug("Async writer thread started")
    
    def _writer_loop(self):
        """Background writer loop for async writes."""
        batch = []
        
        while not self._shutdown_event.is_set():
            try:
                # Wait for item with timeout
                item = self._write_queue.get(timeout=1.0)
                batch.append(item)
                
                # Batch up writes
                while len(batch) < self.config.batch_size:
                    try:
                        item = self._write_queue.get_nowait()
                        batch.append(item)
                    except queue.Empty:
                        break
                
                # Write batch
                if batch:
                    self._write_batch(batch)
                    batch.clear()
                    
            except queue.Empty:
                # Flush any pending items
                if batch:
                    self._write_batch(batch)
                    batch.clear()
            except Exception as e:
                self.logger.error(f"Writer loop error: {e}")
        
        # Flush remaining items on shutdown
        if batch:
            self._write_batch(batch)
    
    def _write_batch(self, batch: List[Dict[str, Any]]):
        """
        Write a batch of items to storage.
        
        Args:
            batch: List of items to write
        """
        for item in batch:
            try:
                if self._using_fallback:
                    self._write_to_fallback(item)
                else:
                    self._write_to_vector_studio(item)
            except Exception as e:
                self.logger.error(f"Failed to write item: {e}")
    
    def _write_to_vector_studio(self, item: Dict[str, Any]):
        """Write item to Vector Studio."""
        if self._db is None:
            raise VectorStudioError("Not connected to Vector Studio")
        
        doc_type = item.get("doc_type", "text")
        content = item.get("content", "")
        metadata = item.get("metadata", {})
        
        self._db.add_text(content, metadata=metadata)
    
    def _write_to_fallback(self, item: Dict[str, Any]):
        """Write item to SQLite fallback."""
        if self._fallback_db is None:
            return
        
        self._fallback_db.execute("""
            INSERT INTO vector_queue (doc_type, content, metadata)
            VALUES (?, ?, ?)
        """, (
            item.get("doc_type", "text"),
            item.get("content", ""),
            json.dumps(item.get("metadata", {}))
        ))
        self._fallback_db.commit()
    
    def is_healthy(self) -> bool:
        """
        Check database health.
        
        Returns:
            True if database is healthy
        """
        if not self._connected:
            return False
        
        try:
            if self._using_fallback:
                self._fallback_db.execute("SELECT 1")
                return True
            else:
                # Ping Vector Studio
                return self._db is not None
        except Exception:
            return False
    
    def is_using_fallback(self) -> bool:
        """Check if using SQLite fallback."""
        return self._using_fallback
    
    def store_signal(self, signal: Any, context: Dict[str, Any]) -> Optional[int]:
        """
        Store a trading signal with context.
        
        Args:
            signal: Trading signal dataclass
            context: Additional context (indicators, regime, etc.)
        
        Returns:
            Vector ID if successful, None otherwise
        """
        try:
            from .embedder import TradeEmbedder
            
            embedder = TradeEmbedder()
            text = embedder.signal_to_text(
                signal,
                context.get("indicators", {}),
                context.get("regime", "UNKNOWN")
            )
            
            metadata = {
                "doc_type": "signal",
                "signal_id": getattr(signal, "signal_id", str(signal)),
                "symbol": getattr(signal, "symbol", context.get("symbol", "")),
                "side": getattr(signal, "side", ""),
                "confidence": getattr(signal, "confidence", 0.0),
                "regime": context.get("regime", ""),
                "timestamp": datetime.now().isoformat(),
            }
            
            item = {
                "doc_type": "signal",
                "content": text,
                "metadata": metadata
            }
            
            if self.config.async_writes:
                self._write_queue.put(item)
                return 0  # Async - no immediate ID
            else:
                if self._using_fallback:
                    self._write_to_fallback(item)
                    return 0
                else:
                    self._write_to_vector_studio(item)
                    return 0
                    
        except Exception as e:
            self.logger.error(f"Failed to store signal: {e}")
            return None
    
    def store_trade(self, trade: Any, outcome: Dict[str, Any]) -> Optional[int]:
        """
        Store a completed trade with outcome.
        
        Args:
            trade: Completed trade record
            outcome: Trade outcome (P&L, duration, exit reason)
        
        Returns:
            Vector ID if successful, None otherwise
        """
        try:
            from .embedder import TradeEmbedder
            
            embedder = TradeEmbedder()
            text = embedder.trade_to_text(trade, outcome)
            
            metadata = {
                "doc_type": "trade",
                "trade_id": getattr(trade, "id", str(trade)),
                "symbol": getattr(trade, "symbol", outcome.get("symbol", "")),
                "side": getattr(trade, "side", ""),
                "pnl": outcome.get("pnl", 0.0),
                "result": outcome.get("result", ""),
                "exit_reason": outcome.get("exit_reason", ""),
                "timestamp": datetime.now().isoformat(),
            }
            
            item = {
                "doc_type": "trade",
                "content": text,
                "metadata": metadata
            }
            
            if self.config.async_writes:
                self._write_queue.put(item)
                return 0
            else:
                if self._using_fallback:
                    self._write_to_fallback(item)
                    return 0
                else:
                    self._write_to_vector_studio(item)
                    return 0
                    
        except Exception as e:
            self.logger.error(f"Failed to store trade: {e}")
            return None
    
    def find_similar_contexts(
        self,
        query: str,
        k: int = 10,
        min_score: float = 0.7,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Find similar historical contexts.
        
        Args:
            query: Current context as text
            k: Number of results
            min_score: Minimum similarity score
            filters: Metadata filters (symbol, date range, etc.)
        
        Returns:
            List of similar contexts with scores
        """
        if self._using_fallback:
            # Fallback: return empty - no semantic search available
            self.logger.debug("Semantic search unavailable in fallback mode")
            return []
        
        if self._db is None:
            return []
        
        try:
            results = self._db.search(query, k=k)
            
            # Filter by score and metadata
            filtered = []
            for result in results:
                if result.get("score", 0) >= min_score:
                    if filters:
                        # Apply metadata filters
                        metadata = result.get("metadata", {})
                        match = all(
                            metadata.get(key) == value
                            for key, value in filters.items()
                        )
                        if not match:
                            continue
                    filtered.append(result)
            
            return filtered
            
        except Exception as e:
            self.logger.error(f"Search failed: {e}")
            return []
    
    def sync_fallback_to_vector_studio(self) -> int:
        """
        Sync queued fallback items to Vector Studio.
        
        Call this when Vector Studio becomes available after using fallback.
        
        Returns:
            Number of items synced
        """
        if self._using_fallback or self._db is None:
            return 0
        
        if self._fallback_db is None:
            return 0
        
        try:
            cursor = self._fallback_db.execute("""
                SELECT id, doc_type, content, metadata
                FROM vector_queue
                WHERE synced = FALSE
                LIMIT 1000
            """)
            
            synced = 0
            for row in cursor.fetchall():
                try:
                    metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                    self._db.add_text(row["content"], metadata=metadata)
                    
                    self._fallback_db.execute(
                        "UPDATE vector_queue SET synced = TRUE WHERE id = ?",
                        (row["id"],)
                    )
                    synced += 1
                    
                except Exception as e:
                    self.logger.warning(f"Failed to sync item {row['id']}: {e}")
            
            self._fallback_db.commit()
            
            if synced > 0:
                self.logger.info(f"Synced {synced} items from fallback to Vector Studio")
            
            return synced
            
        except Exception as e:
            self.logger.error(f"Fallback sync failed: {e}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics.
        
        Returns:
            Dictionary with storage stats
        """
        stats = {
            "connected": self._connected,
            "using_fallback": self._using_fallback,
            "async_writes_enabled": self.config.async_writes,
            "queue_size": self._write_queue.qsize(),
        }
        
        if self._using_fallback and self._fallback_db:
            try:
                cursor = self._fallback_db.execute(
                    "SELECT COUNT(*) FROM vector_queue WHERE synced = FALSE"
                )
                stats["pending_sync"] = cursor.fetchone()[0]
            except Exception:
                pass
        
        return stats
    
    def close(self):
        """Close connection gracefully."""
        # Signal writer thread to stop
        self._shutdown_event.set()
        
        if self._writer_thread and self._writer_thread.is_alive():
            self._writer_thread.join(timeout=5.0)
        
        # Close connections
        if self._db is not None:
            try:
                self._db.close()
            except Exception:
                pass
            self._db = None
        
        if self._fallback_db is not None:
            try:
                self._fallback_db.close()
            except Exception:
                pass
            self._fallback_db = None
        
        self._connected = False
        self.logger.info("Vector Studio adapter closed")
