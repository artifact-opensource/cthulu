"""
Indicator & Signal Monitoring Collector

Real-time collection of all indicator values, signals, and calculated scores.
Creates comprehensive CSV output for signal optimization and analysis.

Output: metrics/indicator_metrics.csv
"""

import os
import csv
import json
import time
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class IndicatorSnapshot:
    """Single snapshot of all indicator values and scores"""
    
    # Timestamp
    timestamp: str = ""
    
    # RSI
    rsi_value: float = 0.0
    rsi_overbought: bool = False
    rsi_oversold: bool = False
    
    # MACD
    macd_value: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0
    macd_crossover: str = "none"  # bullish, bearish, none
    
    # Bollinger Bands
    bb_upper: float = 0.0
    bb_middle: float = 0.0
    bb_lower: float = 0.0
    bb_width: float = 0.0
    bb_position: float = 0.0  # Price position within bands (0-1)
    
    # Stochastic
    stoch_k: float = 0.0
    stoch_d: float = 0.0
    stoch_overbought: bool = False
    stoch_oversold: bool = False
    
    # ADX
    adx_value: float = 0.0
    adx_plus_di: float = 0.0
    adx_minus_di: float = 0.0
    adx_trend_strength: str = "weak"  # weak, moderate, strong
    
    # Supertrend
    supertrend_value: float = 0.0
    supertrend_direction: str = "neutral"  # bullish, bearish, neutral
    supertrend_signal: str = "none"  # buy, sell, none
    
    # VWAP
    vwap_value: float = 0.0
    vwap_deviation: float = 0.0
    
    # ATR
    atr_value: float = 0.0
    
    # Volume
    volume_current: float = 0.0
    volume_avg: float = 0.0
    volume_relative: float = 0.0  # Current / Average
    
    # Price Action
    price_current: float = 0.0
    price_change_pct: float = 0.0
    
    # Strategy Signals
    signal_sma_crossover: str = "none"  # buy, sell, none
    signal_sma_strength: float = 0.0
    signal_ema_crossover: str = "none"
    signal_ema_strength: float = 0.0
    signal_trend_following: str = "none"
    signal_trend_strength: float = 0.0
    signal_mean_reversion: str = "none"
    signal_mean_deviation: float = 0.0
    signal_momentum: str = "none"
    signal_momentum_score: float = 0.0
    signal_scalping: str = "none"
    signal_scalping_score: float = 0.0
    
    # Calculated Scores (frozen columns)
    score_confidence: float = 0.0  # 0-1
    score_confluence: float = 0.0  # 0-1
    score_trend_alignment: float = 0.0  # 0-1
    score_volume_confirmation: float = 0.0  # 0-1
    score_volatility_filter: float = 0.0  # 0-1
    score_overall: float = 0.0  # 0-1 (weighted combination)
    
    # Signal Summary
    signal_count_bullish: int = 0
    signal_count_bearish: int = 0
    signal_count_neutral: int = 0
    signal_agreement_pct: float = 0.0  # % of indicators agreeing
    
    # Additional Metadata
    symbol: str = ""
    timeframe: str = ""
    session: str = ""  # asian, european, us


class IndicatorMetricsCollector:
    """
    Collects comprehensive indicator and signal metrics in real-time.
    
    Features:
    - JSON-based configuration (extensible)
    - Real-time indicator value tracking
    - Automatic confidence/confluence scoring
    - Single CSV output with all data
    """
    
    def __init__(self, csv_path: str = None, config_path: str = None, 
                 update_interval: float = 1.0):
        """
        Initialize collector.
        
        Args:
            csv_path: Path to output CSV (default: metrics/indicator_metrics.csv)
            config_path: Path to JSON config (default: monitoring/indicator_config.json)
            update_interval: Seconds between CSV writes
        """
        self.logger = logging.getLogger("cthulu.indicator_collector")
        
        # Set paths - CSV goes to centralized metrics/ directory
        if csv_path is None:
            cthulu_root = Path(__file__).parent.parent
            metrics_dir = cthulu_root / "metrics"
            metrics_dir.mkdir(parents=True, exist_ok=True)
            csv_path = str(metrics_dir / "indicator_metrics.csv")
        if config_path is None:
            monitoring_dir = Path(__file__).parent
            config_path = str(monitoring_dir / "indicator_config.json")
        
        self.csv_path = csv_path
        self.config_path = config_path
        self.update_interval = update_interval
        
        # Load configuration
        self.config = self._load_config()
        
        # Current snapshot
        self.current_snapshot = IndicatorSnapshot()
        self._lock = threading.Lock()
        
        # CSV writer thread
        self._running = False
        self._writer_thread = None
        
        # Initialize CSV file with headers
        self._initialize_csv()
        
        self.logger.info(f"Indicator collector initialized")
        self.logger.info(f"  CSV: {self.csv_path}")
        self.logger.info(f"  Config: {self.config_path}")
        self.logger.info(f"  Indicators: {len([i for i in self.config['indicators'] if i['enabled']])}")
        self.logger.info(f"  Strategies: {len([s for s in self.config['strategies'] if s['enabled']])}")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load JSON configuration"""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.warning(f"Failed to load config: {e}, using defaults")
            return {
                "indicators": [],
                "strategies": [],
                "scoring": {
                    "confidence_weights": {
                        "indicator_agreement": 0.4,
                        "trend_strength": 0.3,
                        "volume_confirmation": 0.2,
                        "volatility_filter": 0.1
                    }
                }
            }
    
    def _initialize_csv(self):
        """Initialize CSV file with headers - always ensures header row exists"""
        try:
            # Create directory if needed
            Path(self.csv_path).parent.mkdir(parents=True, exist_ok=True)
            
            fieldnames = list(asdict(IndicatorSnapshot()).keys())
            
            # Check if file exists and has valid header
            needs_header = True
            if os.path.exists(self.csv_path):
                try:
                    with open(self.csv_path, 'r', newline='') as f:
                        reader = csv.reader(f)
                        first_row = next(reader, None)
                        # Check if first row is our expected header (must have 'timestamp' as first column
                        # and match expected column count)
                        if first_row and len(first_row) == len(fieldnames) and first_row[0] == 'timestamp':
                            # Verify it's actually a header (not data starting with ISO timestamp)
                            if first_row == fieldnames:
                                needs_header = False
                            else:
                                self.logger.warning(f"CSV header mismatch, resetting file")
                                needs_header = True
                        else:
                            # Invalid header detected - file needs reset
                            self.logger.warning(f"Invalid CSV header detected, resetting file")
                            needs_header = True
                except Exception as e:
                    self.logger.warning(f"Error reading CSV header: {e}")
                    needs_header = True
            
            if needs_header:
                # Write fresh file with headers
                with open(self.csv_path, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                self.logger.info(f"Created/reset CSV file with headers: {self.csv_path}")
            else:
                self.logger.info(f"CSV file exists with valid headers: {self.csv_path}")
                
        except Exception as e:
            self.logger.error(f"Failed to initialize CSV: {e}")
            try:
                fallback_base = Path(os.getenv('LOCALAPPDATA') or Path.home()) / 'cthulu' / 'metrics'
                fallback_base.mkdir(parents=True, exist_ok=True)
                fallback_path = fallback_base / Path(self.csv_path).name
                with open(fallback_path, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=list(asdict(IndicatorSnapshot()).keys()))
                    writer.writeheader()
                self.csv_path = str(fallback_path)
                self.logger.info(f"Switched indicator CSV to user-local path: {self.csv_path}")
            except Exception as e2:
                self.logger.error(f"Fallback indicator CSV init failed: {e2}")
    
    def start(self):
        """Start background CSV writer thread"""
        if self._running:
            return
        
        self._running = True
        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._writer_thread.start()
        self.logger.info("Indicator collector started")
    
    def stop(self):
        """Stop collector"""
        if not self._running:
            return
        
        self.logger.info("Stopping indicator collector...")
        self._running = False
        
        if self._writer_thread:
            self._writer_thread.join(timeout=5.0)
        
        # Final write
        self._write_snapshot()
        self.logger.info("Indicator collector stopped")
    
    def _writer_loop(self):
        """Background thread that writes snapshots to CSV"""
        while self._running:
            try:
                self._write_snapshot()
                time.sleep(self.update_interval)
            except Exception as e:
                self.logger.error(f"Error in writer loop: {e}")
    
    def _write_snapshot(self):
        """Write current snapshot to CSV"""
        try:
            with self._lock:
                snapshot_dict = asdict(self.current_snapshot)
            
            # Append to CSV
            with open(self.csv_path, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=list(snapshot_dict.keys()))
                writer.writerow(snapshot_dict)
                
        except Exception as e:
            self.logger.error(f"Failed to write snapshot: {e}")
            # Attempt write to user-local fallback directory
            try:
                fallback_base = Path(os.getenv('LOCALAPPDATA') or Path.home()) / 'cthulu' / 'metrics'
                fallback_base.mkdir(parents=True, exist_ok=True)
                fallback_path = fallback_base / Path(self.csv_path).name
                with open(fallback_path, 'a', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=list(snapshot_dict.keys()))
                    writer.writerow(snapshot_dict)
                self.logger.info(f"Wrote indicator snapshot to fallback CSV: {fallback_path}")
                self.csv_path = str(fallback_path)
            except Exception as e2:
                self.logger.error(f"Failed to write to fallback indicator CSV: {e2}")
    
    def update_snapshot(self, **kwargs):
        """
        Update current snapshot with new values.
        
        Args:
            **kwargs: Field names and values to update
        """
        with self._lock:
            # Update timestamp
            self.current_snapshot.timestamp = datetime.utcnow().isoformat()
            
            # Update provided fields
            for key, value in kwargs.items():
                if hasattr(self.current_snapshot, key):
                    setattr(self.current_snapshot, key, value)
            
            # Recalculate scores
            self._calculate_scores()
    
    def _calculate_scores(self):
        """Calculate confidence, confluence, and overall scores"""
        snapshot = self.current_snapshot
        weights = self.config['scoring']['confidence_weights']
        
        # 1. Signal agreement score
        total_signals = snapshot.signal_count_bullish + snapshot.signal_count_bearish + snapshot.signal_count_neutral
        if total_signals > 0:
            max_direction = max(snapshot.signal_count_bullish, snapshot.signal_count_bearish)
            snapshot.signal_agreement_pct = (max_direction / total_signals) * 100
            agreement_score = max_direction / total_signals
        else:
            agreement_score = 0.0
            snapshot.signal_agreement_pct = 0.0
        
        # 2. Trend strength score
        if snapshot.adx_value > 25:
            trend_score = min(snapshot.adx_value / 50.0, 1.0)
        else:
            trend_score = 0.0
        
        # 3. Volume confirmation score
        if snapshot.volume_relative > 1.0:
            volume_score = min(snapshot.volume_relative / 2.0, 1.0)
        else:
            volume_score = snapshot.volume_relative
        
        # 4. Volatility filter score (lower ATR relative to price = higher score)
        if snapshot.price_current > 0 and snapshot.atr_value > 0:
            atr_pct = (snapshot.atr_value / snapshot.price_current) * 100
            volatility_score = max(0.0, 1.0 - (atr_pct / 5.0))  # Normalize to 5% ATR
        else:
            volatility_score = 0.5
        
        # Store individual scores
        snapshot.score_trend_alignment = trend_score
        snapshot.score_volume_confirmation = volume_score
        snapshot.score_volatility_filter = volatility_score
        
        # Calculate confidence (weighted)
        snapshot.score_confidence = (
            agreement_score * weights['indicator_agreement'] +
            trend_score * weights['trend_strength'] +
            volume_score * weights['volume_confirmation'] +
            volatility_score * weights['volatility_filter']
        )
        
        # Calculate confluence (number of agreeing indicators)
        agreeing_indicators = max(snapshot.signal_count_bullish, snapshot.signal_count_bearish)
        min_indicators = self.config['scoring'].get('confluence_min_indicators', 3)
        if agreeing_indicators >= min_indicators:
            snapshot.score_confluence = min(agreeing_indicators / 6.0, 1.0)  # Normalize to 6 indicators
        else:
            snapshot.score_confluence = 0.0
        
        # Overall score (average of confidence and confluence)
        snapshot.score_overall = (snapshot.score_confidence + snapshot.score_confluence) / 2.0
    
    def get_current_snapshot(self) -> IndicatorSnapshot:
        """Get current snapshot (thread-safe)"""
        with self._lock:
            # Return a copy
            return IndicatorSnapshot(**asdict(self.current_snapshot))
    
    # Convenience methods for updating specific indicators
    
    def update_rsi(self, value: float, overbought: bool = False, oversold: bool = False):
        """Update RSI values"""
        self.update_snapshot(rsi_value=value, rsi_overbought=overbought, rsi_oversold=oversold)
    
    def update_macd(self, macd: float, signal: float, histogram: float):
        """Update MACD values"""
        crossover = "none"
        if histogram > 0 and macd > signal:
            crossover = "bullish"
        elif histogram < 0 and macd < signal:
            crossover = "bearish"
        
        self.update_snapshot(
            macd_value=macd,
            macd_signal=signal,
            macd_histogram=histogram,
            macd_crossover=crossover
        )
    
    def update_bollinger(self, upper: float, middle: float, lower: float, price: float):
        """Update Bollinger Bands values"""
        width = upper - lower
        position = 0.5
        if width > 0:
            position = (price - lower) / width
        
        self.update_snapshot(
            bb_upper=upper,
            bb_middle=middle,
            bb_lower=lower,
            bb_width=width,
            bb_position=position
        )
    
    def update_strategy_signal(self, strategy_name: str, signal: str, score: float = 0.0):
        """
        Update strategy signal.
        
        Args:
            strategy_name: Name of strategy (e.g., "sma_crossover")
            signal: Signal type ("buy", "sell", "none")
            score: Signal strength (0-1)
        """
        field_signal = f"signal_{strategy_name}"
        field_score = f"signal_{strategy_name}_strength"
        
        # Update signal counts
        current_snapshot = self.current_snapshot
        if signal == "buy":
            current_snapshot.signal_count_bullish += 1
        elif signal == "sell":
            current_snapshot.signal_count_bearish += 1
        else:
            current_snapshot.signal_count_neutral += 1
        
        self.update_snapshot(**{field_signal: signal, field_score: score})
