"""
ML Training Data Logger - Decision Recording for Model Training

Records trading decisions, outcomes, and market conditions for 
supervised learning model training.

Part of Cthulu Cognition Engine v6.0.0
"""
from __future__ import annotations
import os
import json
import gzip
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any
import pandas as pd
import numpy as np
from pathlib import Path

logger = logging.getLogger("cthulu.cognition.training")


@dataclass
class TradeDecision:
    """Record of a trade decision for ML training."""
    timestamp: str
    symbol: str
    timeframe: str
    
    # Market state at decision time
    price: float
    atr: float
    rsi: float
    adx: float
    macd: float
    macd_signal: float
    bb_upper: float
    bb_lower: float
    volume_ratio: float
    
    # Cognition state
    regime: str
    regime_confidence: float
    prediction_direction: str
    prediction_confidence: float
    sentiment_direction: str
    sentiment_score: float
    
    # Decision made
    action: str  # BUY, SELL, HOLD
    confidence: float
    strategy_used: str
    position_size: float
    
    # Entry conditions
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    
    # Outcome (filled in later)
    outcome: Optional[str] = None  # WIN, LOSS, BREAKEVEN
    pnl: Optional[float] = None
    exit_price: Optional[float] = None
    exit_time: Optional[str] = None
    hold_duration_minutes: Optional[float] = None
    max_favorable: Optional[float] = None  # Max favorable excursion
    max_adverse: Optional[float] = None    # Max adverse excursion


class TrainingDataLogger:
    """
    Logs trading decisions and outcomes for ML model training.
    
    Stores data in JSONL format (one JSON per line) with optional gzip compression.
    Designed for efficient batch training data collection.
    """
    
    def __init__(
        self,
        data_dir: Optional[str] = None,
        compress: bool = True,
        batch_size: int = 100
    ):
        self.data_dir = Path(data_dir or os.path.join(
            os.path.dirname(__file__), 'data', 'training'
        ))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.compress = compress
        self.batch_size = batch_size
        
        # Pending decisions (not yet written)
        self._pending: List[Dict[str, Any]] = []
        
        # Active decisions awaiting outcome
        self._active_decisions: Dict[int, TradeDecision] = {}
        
        # Session file
        session_id = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        ext = ".jsonl.gz" if compress else ".jsonl"
        self._session_file = self.data_dir / f"decisions_{session_id}{ext}"
        
        logger.info(f"TrainingDataLogger initialized: {self._session_file}")
    
    def log_decision(
        self,
        symbol: str,
        timeframe: str,
        market_data: pd.DataFrame,
        indicators: Dict[str, float],
        cognition_state: Optional[Dict[str, Any]],
        action: str,
        confidence: float,
        strategy: str,
        position_size: float,
        entry_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        ticket: Optional[int] = None
    ) -> None:
        """
        Log a trading decision.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe string
            market_data: OHLCV DataFrame
            indicators: Current indicator values
            cognition_state: CognitionState as dict
            action: BUY, SELL, or HOLD
            confidence: Decision confidence
            strategy: Strategy that generated signal
            position_size: Position size in lots
            entry_price: Entry price if trade executed
            stop_loss: Stop loss price
            take_profit: Take profit price
            ticket: MT5 ticket number if trade executed
        """
        try:
            # Extract market state
            latest = market_data.iloc[-1] if len(market_data) > 0 else {}
            
            decision = TradeDecision(
                timestamp=datetime.utcnow().isoformat(),
                symbol=symbol,
                timeframe=timeframe,
                
                # Market state
                price=float(latest.get('close', 0)) if isinstance(latest, dict) else float(latest['close']) if 'close' in latest.index else 0,
                atr=float(indicators.get('atr', 0)),
                rsi=float(indicators.get('rsi', indicators.get('rsi_14', 50))),
                adx=float(indicators.get('adx', indicators.get('adx_14', 20))),
                macd=float(indicators.get('macd', 0)),
                macd_signal=float(indicators.get('macd_signal', 0)),
                bb_upper=float(indicators.get('bb_upper', 0)),
                bb_lower=float(indicators.get('bb_lower', 0)),
                volume_ratio=float(indicators.get('volume_ratio', 1.0)),
                
                # Cognition state
                regime=cognition_state.get('regime', 'unknown') if cognition_state else 'unknown',
                regime_confidence=float(cognition_state.get('regime_confidence', 0)) if cognition_state else 0,
                prediction_direction=cognition_state.get('prediction', 'neutral') if cognition_state else 'neutral',
                prediction_confidence=float(cognition_state.get('prediction_confidence', 0.33)) if cognition_state else 0.33,
                sentiment_direction=cognition_state.get('sentiment', 'neutral') if cognition_state else 'neutral',
                sentiment_score=float(cognition_state.get('sentiment_score', 0)) if cognition_state else 0,
                
                # Decision
                action=action,
                confidence=confidence,
                strategy_used=strategy,
                position_size=position_size,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            
            # If trade was executed, track for outcome
            if ticket and action in ('BUY', 'SELL'):
                self._active_decisions[ticket] = decision
            
            # Add to pending
            self._pending.append(asdict(decision))
            
            # Flush if batch full
            if len(self._pending) >= self.batch_size:
                self._flush()
                
        except Exception as e:
            logger.error(f"Error logging decision: {e}")
    
    def log_outcome(
        self,
        ticket: int,
        outcome: str,
        pnl: float,
        exit_price: float,
        max_favorable: float = 0,
        max_adverse: float = 0
    ) -> None:
        """
        Log the outcome of a trade.
        
        Args:
            ticket: MT5 ticket number
            outcome: WIN, LOSS, or BREAKEVEN
            pnl: Profit/loss in account currency
            exit_price: Exit price
            max_favorable: Maximum favorable excursion (pips)
            max_adverse: Maximum adverse excursion (pips)
        """
        try:
            if ticket in self._active_decisions:
                decision = self._active_decisions.pop(ticket)
                
                decision.outcome = outcome
                decision.pnl = pnl
                decision.exit_price = exit_price
                decision.exit_time = datetime.utcnow().isoformat()
                decision.max_favorable = max_favorable
                decision.max_adverse = max_adverse
                
                # Calculate hold duration
                if decision.timestamp:
                    entry_time = datetime.fromisoformat(decision.timestamp)
                    exit_time = datetime.utcnow()
                    decision.hold_duration_minutes = (exit_time - entry_time).total_seconds() / 60
                
                # Write completed decision
                self._pending.append(asdict(decision))
                
                if len(self._pending) >= self.batch_size:
                    self._flush()
                    
        except Exception as e:
            logger.error(f"Error logging outcome: {e}")
    
    def _flush(self) -> None:
        """Write pending decisions to file."""
        if not self._pending:
            return
        
        try:
            if self.compress:
                with gzip.open(self._session_file, 'at', encoding='utf-8') as f:
                    for decision in self._pending:
                        f.write(json.dumps(decision) + '\n')
            else:
                with open(self._session_file, 'a', encoding='utf-8') as f:
                    for decision in self._pending:
                        f.write(json.dumps(decision) + '\n')
            
            logger.debug(f"Flushed {len(self._pending)} decisions to {self._session_file}")
            self._pending.clear()
            
        except Exception as e:
            logger.error(f"Error flushing decisions: {e}")
    
    def close(self) -> None:
        """Flush remaining decisions and close."""
        self._flush()
        
        # Write incomplete decisions (no outcome yet)
        incomplete = []
        for ticket, decision in self._active_decisions.items():
            decision.outcome = 'INCOMPLETE'
            incomplete.append(asdict(decision))
        
        if incomplete:
            self._pending = incomplete
            self._flush()
        
        logger.info(f"TrainingDataLogger closed: {len(self._active_decisions)} incomplete trades")
    
    @staticmethod
    def load_training_data(data_dir: str, min_date: Optional[str] = None) -> pd.DataFrame:
        """
        Load training data from files.
        
        Args:
            data_dir: Directory containing training data files
            min_date: Minimum date to include (YYYYMMDD format)
            
        Returns:
            DataFrame with all training data
        """
        data_path = Path(data_dir)
        records = []
        
        for file in data_path.glob("decisions_*.jsonl*"):
            # Check date filter
            if min_date:
                file_date = file.stem.split('_')[1][:8]
                if file_date < min_date:
                    continue
            
            try:
                if file.suffix == '.gz':
                    with gzip.open(file, 'rt', encoding='utf-8') as f:
                        for line in f:
                            records.append(json.loads(line))
                else:
                    with open(file, 'r', encoding='utf-8') as f:
                        for line in f:
                            records.append(json.loads(line))
            except Exception as e:
                logger.warning(f"Error loading {file}: {e}")
        
        if not records:
            return pd.DataFrame()
        
        return pd.DataFrame(records)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get logging statistics."""
        return {
            'session_file': str(self._session_file),
            'pending_decisions': len(self._pending),
            'active_trades': len(self._active_decisions),
            'compress': self.compress,
            'batch_size': self.batch_size
        }


# Module-level singleton
_logger: Optional[TrainingDataLogger] = None


def get_training_logger(**kwargs) -> TrainingDataLogger:
    """Get or create training data logger singleton."""
    global _logger
    if _logger is None:
        _logger = TrainingDataLogger(**kwargs)
    return _logger


def log_trade_decision(**kwargs) -> None:
    """Convenience function to log a trade decision."""
    get_training_logger().log_decision(**kwargs)


def log_trade_outcome(**kwargs) -> None:
    """Convenience function to log a trade outcome."""
    get_training_logger().log_outcome(**kwargs)
