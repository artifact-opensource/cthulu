"""
ML Data Exporter

Exports structured training data from Hektor vector database.
Prepares data for machine learning model training.
"""

import logging
import pandas as pd
import numpy as np
import json
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class TrainingExample:
    """Single training example"""
    # Features
    features: Dict[str, float]
    
    # Labels
    outcome: str  # WIN, LOSS, BREAKEVEN
    pnl: float
    pnl_pct: float
    duration_bars: int
    profit_tier: int  # 0=loss, 1=small_win, 2=medium_win, 3=large_win
    
    # Metadata
    timestamp: datetime
    symbol: str
    strategy: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            **self.features,
            'outcome': self.outcome,
            'pnl': self.pnl,
            'pnl_pct': self.pnl_pct,
            'duration_bars': self.duration_bars,
            'profit_tier': self.profit_tier,
            'timestamp': self.timestamp.isoformat(),
            'symbol': self.symbol,
            'strategy': self.strategy
        }


class MLDataExporter:
    """
    Exports structured training data from Hektor vector database.
    
    Prepares data for supervised learning, reinforcement learning,
    and pattern recognition models.
    """
    
    def __init__(self, vector_adapter=None, output_dir: str = "./training_data"):
        """
        Initialize ML data exporter.
        
        Args:
            vector_adapter: VectorStudioAdapter instance
            output_dir: Directory to save exported data
        """
        self.vector_adapter = vector_adapter
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        
    def export_training_data(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        symbols: Optional[List[str]] = None,
        min_samples: int = 100,
        test_split: float = 0.2,
        validation_split: float = 0.1
    ) -> Dict[str, Path]:
        """
        Export training data from Hektor.
        
        Args:
            start_date: Start date for data export
            end_date: End date for data export
            symbols: List of symbols to include (None = all)
            min_samples: Minimum samples required
            test_split: Fraction for test set
            validation_split: Fraction for validation set
            
        Returns:
            Dictionary with paths to exported files
        """
        self.logger.info("Starting ML data export...")
        
        try:
            # Query all trade data from Hektor
            trade_data = self._query_trade_data(start_date, end_date, symbols)
            
            if len(trade_data) < min_samples:
                self.logger.warning(
                    f"Insufficient samples: {len(trade_data)} < {min_samples}"
                )
                return {}
                
            self.logger.info(f"Retrieved {len(trade_data)} trade records")
            
            # Convert to training examples
            examples = self._convert_to_training_examples(trade_data)
            
            # Split data
            train, val, test = self._split_data(
                examples, test_split, validation_split
            )
            
            # Export in multiple formats
            output_files = {}
            
            # CSV format
            output_files['train_csv'] = self._export_csv(train, 'train.csv')
            output_files['val_csv'] = self._export_csv(val, 'validation.csv')
            output_files['test_csv'] = self._export_csv(test, 'test.csv')
            
            # Parquet format (for large datasets)
            output_files['train_parquet'] = self._export_parquet(train, 'train.parquet')
            output_files['val_parquet'] = self._export_parquet(val, 'validation.parquet')
            output_files['test_parquet'] = self._export_parquet(test, 'test.parquet')
            
            # JSON format (for metadata)
            output_files['metadata'] = self._export_metadata(
                train, val, test, 'metadata.json'
            )
            
            self.logger.info(f"Exported {len(output_files)} files to {self.output_dir}")
            
            return output_files
            
        except Exception as e:
            self.logger.error(f"Error exporting training data: {e}", exc_info=True)
            return {}
    
    def export_feature_vectors(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        output_file: str = "feature_vectors.npy"
    ) -> Optional[Path]:
        """
        Export raw feature vectors from Hektor embeddings.
        
        Args:
            start_date: Start date
            end_date: End date
            output_file: Output filename
            
        Returns:
            Path to exported file
        """
        try:
            # Query embeddings from Hektor
            # This would require additional Hektor API support
            self.logger.warning("Feature vector export requires Hektor embedding API")
            return None
            
        except Exception as e:
            self.logger.error(f"Error exporting feature vectors: {e}")
            return None
    
    def export_successful_patterns(
        self,
        min_win_rate: float = 0.6,
        min_samples: int = 10,
        output_file: str = "successful_patterns.json"
    ) -> Optional[Path]:
        """
        Export patterns with high success rates.
        
        Args:
            min_win_rate: Minimum win rate threshold
            min_samples: Minimum number of samples
            output_file: Output filename
            
        Returns:
            Path to exported file
        """
        try:
            # Query all trades
            trade_data = self._query_trade_data()
            
            # Group by pattern/strategy
            patterns = self._group_by_pattern(trade_data)
            
            # Filter successful patterns
            successful = []
            for pattern_name, trades in patterns.items():
                if len(trades) < min_samples:
                    continue
                    
                wins = sum(1 for t in trades if t.get('outcome') == 'WIN')
                win_rate = wins / len(trades)
                
                if win_rate >= min_win_rate:
                    successful.append({
                        'pattern': pattern_name,
                        'total_trades': len(trades),
                        'win_rate': win_rate,
                        'avg_pnl': np.mean([t.get('pnl', 0) for t in trades]),
                        'trades': trades
                    })
                    
            # Export
            output_path = self.output_dir / output_file
            with open(output_path, 'w') as f:
                json.dump(successful, f, indent=2, default=str)
                
            self.logger.info(
                f"Exported {len(successful)} successful patterns to {output_path}"
            )
            
            return output_path
            
        except Exception as e:
            self.logger.error(f"Error exporting successful patterns: {e}")
            return None
    
    # Private methods
    
    def _query_trade_data(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        symbols: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Query trade data from Hektor"""
        if not self.vector_adapter:
            self.logger.error("No vector adapter available")
            return []
            
        try:
            # Build filters
            filters = {}
            if start_date:
                filters['start_date'] = start_date.isoformat()
            if end_date:
                filters['end_date'] = end_date.isoformat()
            if symbols:
                filters['symbols'] = symbols
                
            # Query all trades (this is a simplified approach)
            # In practice, you'd need pagination for large datasets
            query = "[Trade] outcome: WIN or LOSS"
            
            contexts = self.vector_adapter.find_similar_contexts(
                query=query,
                k=10000,  # Large number to get all trades
                min_score=0.0,
                filters=filters
            )
            
            # Extract trade data from contexts
            trades = []
            for ctx in contexts:
                trade_data = self._parse_trade_context(ctx)
                if trade_data:
                    trades.append(trade_data)
                    
            return trades
            
        except Exception as e:
            self.logger.error(f"Error querying trade data: {e}")
            return []
    
    def _parse_trade_context(self, context: Any) -> Optional[Dict[str, Any]]:
        """Parse trade data from context"""
        try:
            metadata = context.metadata
            
            return {
                'timestamp': datetime.fromisoformat(metadata.get('timestamp', '')),
                'symbol': metadata.get('symbol', ''),
                'strategy': metadata.get('strategy', ''),
                'outcome': metadata.get('outcome', ''),
                'pnl': metadata.get('pnl', 0.0),
                'entry_price': metadata.get('entry_price', 0.0),
                'exit_price': metadata.get('exit_price', 0.0),
                'duration_bars': metadata.get('duration_bars', 0),
                'indicators': metadata.get('indicators', {}),
                'regime': metadata.get('regime', ''),
                'confidence': metadata.get('confidence', 0.0),
            }
        except Exception as e:
            self.logger.error(f"Error parsing trade context: {e}")
            return None
    
    def _convert_to_training_examples(
        self,
        trade_data: List[Dict[str, Any]]
    ) -> List[TrainingExample]:
        """Convert trade data to training examples"""
        examples = []
        
        for trade in trade_data:
            try:
                # Extract features
                features = self._extract_features(trade)
                
                # Calculate labels
                pnl = trade.get('pnl', 0.0)
                entry_price = trade.get('entry_price', 1.0)
                pnl_pct = (pnl / entry_price) * 100 if entry_price > 0 else 0.0
                
                outcome = trade.get('outcome', 'UNKNOWN')
                duration_bars = trade.get('duration_bars', 0)
                
                # Categorize profit tier
                profit_tier = self._categorize_profit_tier(pnl_pct)
                
                example = TrainingExample(
                    features=features,
                    outcome=outcome,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    duration_bars=duration_bars,
                    profit_tier=profit_tier,
                    timestamp=trade.get('timestamp', datetime.now()),
                    symbol=trade.get('symbol', ''),
                    strategy=trade.get('strategy', '')
                )
                
                examples.append(example)
                
            except Exception as e:
                self.logger.error(f"Error converting trade to example: {e}")
                continue
                
        return examples
    
    def _extract_features(self, trade: Dict[str, Any]) -> Dict[str, float]:
        """Extract features from trade data"""
        features = {}
        
        # Price features
        features['entry_price'] = trade.get('entry_price', 0.0)
        features['exit_price'] = trade.get('exit_price', 0.0)
        
        # Indicator features
        indicators = trade.get('indicators', {})
        for name, value in indicators.items():
            if isinstance(value, (int, float)):
                features[f'ind_{name}'] = float(value)
                
        # Regime features (one-hot encoding)
        regime = trade.get('regime', 'UNKNOWN')
        features['regime_trending'] = 1.0 if 'TREND' in regime else 0.0
        features['regime_ranging'] = 1.0 if 'RANG' in regime else 0.0
        features['regime_volatile'] = 1.0 if 'VOLAT' in regime else 0.0
        
        # Confidence
        features['confidence'] = trade.get('confidence', 0.0)
        
        # Time features
        timestamp = trade.get('timestamp', datetime.now())
        features['hour_of_day'] = timestamp.hour
        features['day_of_week'] = timestamp.weekday()
        
        return features
    
    def _categorize_profit_tier(self, pnl_pct: float) -> int:
        """Categorize profit into tiers"""
        if pnl_pct < 0:
            return 0  # Loss
        elif pnl_pct < 0.5:
            return 1  # Small win
        elif pnl_pct < 1.5:
            return 2  # Medium win
        else:
            return 3  # Large win
    
    def _split_data(
        self,
        examples: List[TrainingExample],
        test_split: float,
        validation_split: float
    ) -> Tuple[List[TrainingExample], List[TrainingExample], List[TrainingExample]]:
        """Split data into train/validation/test sets with temporal awareness"""
        # Sort by timestamp
        sorted_examples = sorted(examples, key=lambda x: x.timestamp)
        
        total = len(sorted_examples)
        test_size = int(total * test_split)
        val_size = int(total * validation_split)
        train_size = total - test_size - val_size
        
        # Use temporal split (most recent for test)
        train = sorted_examples[:train_size]
        val = sorted_examples[train_size:train_size + val_size]
        test = sorted_examples[train_size + val_size:]
        
        self.logger.info(
            f"Data split: train={len(train)}, val={len(val)}, test={len(test)}"
        )
        
        return train, val, test
    
    def _export_csv(
        self,
        examples: List[TrainingExample],
        filename: str
    ) -> Path:
        """Export to CSV format"""
        output_path = self.output_dir / filename
        
        # Convert to DataFrame
        data = [ex.to_dict() for ex in examples]
        df = pd.DataFrame(data)
        
        # Save
        df.to_csv(output_path, index=False)
        
        self.logger.info(f"Exported {len(examples)} examples to {output_path}")
        
        return output_path
    
    def _export_parquet(
        self,
        examples: List[TrainingExample],
        filename: str
    ) -> Path:
        """Export to Parquet format"""
        output_path = self.output_dir / filename
        
        # Convert to DataFrame
        data = [ex.to_dict() for ex in examples]
        df = pd.DataFrame(data)
        
        # Save
        df.to_parquet(output_path, index=False, compression='snappy')
        
        self.logger.info(f"Exported {len(examples)} examples to {output_path}")
        
        return output_path
    
    def _export_metadata(
        self,
        train: List[TrainingExample],
        val: List[TrainingExample],
        test: List[TrainingExample],
        filename: str
    ) -> Path:
        """Export metadata about the dataset"""
        output_path = self.output_dir / filename
        
        metadata = {
            'export_timestamp': datetime.now().isoformat(),
            'total_examples': len(train) + len(val) + len(test),
            'train_size': len(train),
            'validation_size': len(val),
            'test_size': len(test),
            'date_range': {
                'start': min(ex.timestamp for ex in train + val + test).isoformat(),
                'end': max(ex.timestamp for ex in train + val + test).isoformat()
            },
            'symbols': list(set(ex.symbol for ex in train + val + test)),
            'strategies': list(set(ex.strategy for ex in train + val + test)),
            'outcome_distribution': {
                'train': self._get_outcome_distribution(train),
                'val': self._get_outcome_distribution(val),
                'test': self._get_outcome_distribution(test)
            },
            'feature_names': list(train[0].features.keys()) if train else []
        }
        
        with open(output_path, 'w') as f:
            json.dump(metadata, f, indent=2)
            
        self.logger.info(f"Exported metadata to {output_path}")
        
        return output_path
    
    def _get_outcome_distribution(
        self,
        examples: List[TrainingExample]
    ) -> Dict[str, int]:
        """Get distribution of outcomes"""
        distribution = {}
        for ex in examples:
            outcome = ex.outcome
            distribution[outcome] = distribution.get(outcome, 0) + 1
        return distribution
    
    def _group_by_pattern(
        self,
        trade_data: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group trades by pattern/strategy"""
        patterns = {}
        
        for trade in trade_data:
            pattern = trade.get('strategy', 'UNKNOWN')
            if pattern not in patterns:
                patterns[pattern] = []
            patterns[pattern].append(trade)
            
        return patterns
