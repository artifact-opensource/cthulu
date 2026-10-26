#!/usr/bin/env python3
"""
MQL5 Handbook Vectorization Script

Ingests all MQL5 handbook articles into Hektor (Vector Studio) for semantic retrieval.
This enables Cthulu to query trading knowledge during decision-making.
"""

import os
import sys
import logging
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import re

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("HandbookVectorizer")


class HandbookVectorizer:
    """
    Vectorizes MQL5 handbook articles into Hektor for semantic retrieval.
    
    Features:
    - Chunks articles intelligently (by section headers)
    - Preserves metadata (title, phase, url, date)
    - Deduplicates content by hash
    - Tracks vectorization state for incremental updates
    """
    
    def __init__(
        self,
        handbook_path: str,
        vector_db_path: str = "./vectors/mql5_handbook",
        chunk_size: int = 1500,
        chunk_overlap: int = 200
    ):
        """
        Initialize vectorizer.
        
        Args:
            handbook_path: Path to MQL5 handbook directory
            vector_db_path: Path to vector database
            chunk_size: Maximum chunk size in characters
            chunk_overlap: Overlap between chunks
        """
        self.handbook_path = Path(handbook_path)
        self.vector_db_path = Path(vector_db_path)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        self.db = None
        self.state_file = self.vector_db_path / "vectorization_state.json"
        self.state: Dict[str, Any] = {}
        
    def connect(self) -> bool:
        """
        Connect to Vector Studio database.
        
        Returns:
            True if connected successfully
        """
        try:
            import pyvdb
            
            self.vector_db_path.mkdir(parents=True, exist_ok=True)
            
            self.db = pyvdb.Database(
                str(self.vector_db_path / "handbook.vdb"),
                dimension=384,  # all-MiniLM-L6-v2 dimension
                index_type="hnsw",
                hnsw_m=16,
                hnsw_ef_construction=200
            )
            
            logger.info(f"Connected to Vector Studio: {self.vector_db_path}")
            self._load_state()
            return True
            
        except ImportError:
            logger.error("pyvdb not installed. Attempting fallback mode...")
            return self._init_fallback()
        except Exception as e:
            logger.error(f"Failed to connect to Vector Studio: {e}")
            return self._init_fallback()
    
    def _init_fallback(self) -> bool:
        """Initialize SQLite fallback for article storage."""
        try:
            import sqlite3
            
            fallback_path = self.vector_db_path / "handbook_fallback.db"
            fallback_path.parent.mkdir(parents=True, exist_ok=True)
            
            self.db = sqlite3.connect(str(fallback_path))
            self.db.row_factory = sqlite3.Row
            
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_hash TEXT UNIQUE NOT NULL,
                    phase TEXT NOT NULL,
                    title TEXT NOT NULL,
                    original_url TEXT,
                    content TEXT NOT NULL,
                    chunk_index INTEGER,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            self.db.execute("""
                CREATE INDEX IF NOT EXISTS idx_phase ON articles(phase)
            """)
            
            self.db.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
                    title, content, content='articles', content_rowid='id'
                )
            """)
            
            self.db.commit()
            logger.info("Using SQLite fallback for handbook storage")
            self._load_state()
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize fallback: {e}")
            return False
    
    def _load_state(self):
        """Load vectorization state from disk."""
        try:
            if self.state_file.exists():
                with open(self.state_file, "r") as f:
                    self.state = json.load(f)
                logger.info(f"Loaded state: {len(self.state.get('processed', {}))} articles processed")
        except Exception as e:
            logger.warning(f"Could not load state: {e}")
            self.state = {"processed": {}, "last_run": None}
    
    def _save_state(self):
        """Save vectorization state to disk."""
        try:
            self.state["last_run"] = datetime.now().isoformat()
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, "w") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save state: {e}")
    
    def discover_articles(self) -> List[Path]:
        """
        Discover all markdown articles in the handbook.
        
        Returns:
            List of article file paths
        """
        articles = []
        
        for phase_dir in ["phase1", "phase2", "phase3"]:
            phase_path = self.handbook_path / phase_dir / "articles"
            if phase_path.exists():
                for md_file in phase_path.glob("*.md"):
                    articles.append(md_file)
        
        logger.info(f"Discovered {len(articles)} articles")
        return articles
    
    def parse_article(self, file_path: Path) -> Dict[str, Any]:
        """
        Parse a markdown article.
        
        Args:
            file_path: Path to markdown file
            
        Returns:
            Parsed article with metadata and content
        """
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Extract YAML frontmatter
        metadata = {}
        body = content
        
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1].strip()
                body = parts[2].strip()
                
                for line in frontmatter.split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        metadata[key.strip()] = value.strip().strip('"\'')
        
        # Determine phase from path
        phase = "unknown"
        for p in ["phase1", "phase2", "phase3"]:
            if p in str(file_path):
                phase = p
                break
        
        # Clean markdown (remove images, links, etc.)
        body = self._clean_markdown(body)
        
        # Generate content hash
        content_hash = hashlib.md5(body.encode()).hexdigest()
        
        return {
            "file_path": str(file_path),
            "phase": phase,
            "title": metadata.get("title", file_path.stem),
            "original_url": metadata.get("original_url", ""),
            "date": metadata.get("date", ""),
            "content": body,
            "content_hash": content_hash
        }
    
    def _clean_markdown(self, content: str) -> str:
        """
        Clean markdown content for vectorization.
        
        Args:
            content: Raw markdown content
            
        Returns:
            Cleaned text
        """
        # Remove image references
        content = re.sub(r"!\[.*?\]\(.*?\)", "", content)
        
        # Remove link references but keep text
        content = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", content)
        
        # Remove HTML tags
        content = re.sub(r"<[^>]+>", "", content)
        
        # Remove code blocks (keep inline code)
        content = re.sub(r"```[\s\S]*?```", "[CODE BLOCK]", content)
        
        # Normalize whitespace
        content = re.sub(r"\n{3,}", "\n\n", content)
        content = re.sub(r" {2,}", " ", content)
        
        return content.strip()
    
    def chunk_article(self, article: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Split article into chunks for vectorization.
        
        Args:
            article: Parsed article
            
        Returns:
            List of chunks with metadata
        """
        content = article["content"]
        chunks = []
        
        # Split by section headers first
        sections = re.split(r"\n(#{1,3} .+)\n", content)
        
        current_section = ""
        current_text = ""
        
        for i, part in enumerate(sections):
            if part.startswith("#"):
                # This is a header
                if current_text.strip():
                    chunks.extend(self._split_text(
                        current_text,
                        article,
                        current_section,
                        len(chunks)
                    ))
                current_section = part.strip("#").strip()
                current_text = ""
            else:
                current_text += part
        
        # Handle remaining text
        if current_text.strip():
            chunks.extend(self._split_text(
                current_text,
                article,
                current_section,
                len(chunks)
            ))
        
        # If no chunks created, treat entire content as one chunk
        if not chunks:
            chunks.append({
                "text": content[:self.chunk_size],
                "metadata": {
                    "phase": article["phase"],
                    "title": article["title"],
                    "section": "",
                    "chunk_index": 0,
                    "original_url": article["original_url"],
                    "content_hash": article["content_hash"]
                }
            })
        
        return chunks
    
    def _split_text(
        self,
        text: str,
        article: Dict[str, Any],
        section: str,
        start_index: int
    ) -> List[Dict[str, Any]]:
        """
        Split text into chunks with overlap.
        
        Args:
            text: Text to split
            article: Parent article
            section: Current section name
            start_index: Starting chunk index
            
        Returns:
            List of chunks
        """
        chunks = []
        text = text.strip()
        
        if len(text) <= self.chunk_size:
            if text:
                chunks.append({
                    "text": text,
                    "metadata": {
                        "phase": article["phase"],
                        "title": article["title"],
                        "section": section,
                        "chunk_index": start_index,
                        "original_url": article["original_url"],
                        "content_hash": article["content_hash"]
                    }
                })
            return chunks
        
        # Split into overlapping chunks
        start = 0
        idx = start_index
        
        while start < len(text):
            end = start + self.chunk_size
            
            # Try to break at sentence boundary
            if end < len(text):
                last_period = text.rfind(".", start, end)
                if last_period > start + self.chunk_size // 2:
                    end = last_period + 1
            
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append({
                    "text": chunk_text,
                    "metadata": {
                        "phase": article["phase"],
                        "title": article["title"],
                        "section": section,
                        "chunk_index": idx,
                        "original_url": article["original_url"],
                        "content_hash": article["content_hash"]
                    }
                })
                idx += 1
            
            start = end - self.chunk_overlap
        
        return chunks
    
    def vectorize_chunk(self, chunk: Dict[str, Any]) -> bool:
        """
        Add a chunk to the vector database.
        
        Args:
            chunk: Chunk with text and metadata
            
        Returns:
            True if successful
        """
        try:
            if hasattr(self.db, "add_text"):
                # Vector Studio
                self.db.add_text(chunk["text"], metadata=chunk["metadata"])
            else:
                # SQLite fallback
                doc_hash = hashlib.md5(
                    f"{chunk['metadata']['content_hash']}_{chunk['metadata']['chunk_index']}".encode()
                ).hexdigest()
                
                self.db.execute("""
                    INSERT OR REPLACE INTO articles 
                    (doc_hash, phase, title, original_url, content, chunk_index, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    doc_hash,
                    chunk["metadata"]["phase"],
                    chunk["metadata"]["title"],
                    chunk["metadata"]["original_url"],
                    chunk["text"],
                    chunk["metadata"]["chunk_index"],
                    json.dumps(chunk["metadata"])
                ))
                self.db.commit()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to vectorize chunk: {e}")
            return False
    
    def run(self, force: bool = False) -> Dict[str, int]:
        """
        Run vectorization on all articles.
        
        Args:
            force: If True, reprocess all articles even if already processed
            
        Returns:
            Statistics dictionary
        """
        if not self.connect():
            return {"error": "Failed to connect to database"}
        
        articles = self.discover_articles()
        
        stats = {
            "total_articles": len(articles),
            "processed": 0,
            "skipped": 0,
            "chunks_created": 0,
            "errors": 0
        }
        
        processed = self.state.get("processed", {})
        
        for article_path in articles:
            try:
                article = self.parse_article(article_path)
                
                # Check if already processed
                if not force and article["content_hash"] in processed:
                    logger.debug(f"Skipping (already processed): {article['title']}")
                    stats["skipped"] += 1
                    continue
                
                # Chunk and vectorize
                chunks = self.chunk_article(article)
                
                for chunk in chunks:
                    if self.vectorize_chunk(chunk):
                        stats["chunks_created"] += 1
                    else:
                        stats["errors"] += 1
                
                # Mark as processed
                processed[article["content_hash"]] = {
                    "title": article["title"],
                    "file": str(article_path),
                    "chunks": len(chunks),
                    "processed_at": datetime.now().isoformat()
                }
                
                stats["processed"] += 1
                logger.info(f"Processed: {article['title']} ({len(chunks)} chunks)")
                
            except Exception as e:
                logger.error(f"Failed to process {article_path}: {e}")
                stats["errors"] += 1
        
        # Save state
        self.state["processed"] = processed
        self._save_state()
        
        logger.info(f"Vectorization complete: {stats}")
        return stats
    
    def search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """
        Search the vectorized handbook.
        
        Args:
            query: Search query
            k: Number of results
            
        Returns:
            List of matching chunks
        """
        try:
            if hasattr(self.db, "search"):
                # Vector Studio
                return self.db.search(query, k=k)
            else:
                # SQLite FTS fallback
                cursor = self.db.execute("""
                    SELECT a.title, a.content, a.phase, a.metadata
                    FROM articles a
                    JOIN articles_fts ON articles_fts.rowid = a.id
                    WHERE articles_fts MATCH ?
                    LIMIT ?
                """, (query, k))
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        "title": row["title"],
                        "content": row["content"],
                        "phase": row["phase"],
                        "metadata": json.loads(row["metadata"]) if row["metadata"] else {}
                    })
                return results
                
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    def close(self):
        """Close database connection."""
        if self.db:
            try:
                if hasattr(self.db, "close"):
                    self.db.close()
            except Exception:
                pass


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Vectorize MQL5 Handbook for Hektor")
    parser.add_argument(
        "--handbook-path",
        default=r"C:\workspace\_gladius\_dev\mql5_handbook",
        help="Path to MQL5 handbook directory"
    )
    parser.add_argument(
        "--vector-db-path",
        default=r"C:\workspace\cthulu\vectors\mql5_handbook",
        help="Path to vector database"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reprocessing of all articles"
    )
    parser.add_argument(
        "--test-query",
        type=str,
        help="Test query after vectorization"
    )
    
    args = parser.parse_args()
    
    vectorizer = HandbookVectorizer(
        handbook_path=args.handbook_path,
        vector_db_path=args.vector_db_path
    )
    
    try:
        stats = vectorizer.run(force=args.force)
        print(f"\nVectorization Results:")
        print(f"  Total Articles: {stats.get('total_articles', 0)}")
        print(f"  Processed: {stats.get('processed', 0)}")
        print(f"  Skipped: {stats.get('skipped', 0)}")
        print(f"  Chunks Created: {stats.get('chunks_created', 0)}")
        print(f"  Errors: {stats.get('errors', 0)}")
        
        if args.test_query:
            print(f"\nTest Query: '{args.test_query}'")
            results = vectorizer.search(args.test_query)
            for i, r in enumerate(results, 1):
                print(f"\n  {i}. {r.get('title', 'Unknown')}")
                print(f"     Phase: {r.get('phase', 'unknown')}")
                print(f"     Content: {r.get('content', '')[:200]}...")
                
    finally:
        vectorizer.close()


if __name__ == "__main__":
    main()
