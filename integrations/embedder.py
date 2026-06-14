"""
Trade Embedder

Converts trading data (signals, trades, market snapshots) to natural 
language text suitable for embedding in Vector Studio.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime


class TradeEmbedder:
    """
    Converts trading data to embeddable text.
    
    Transforms structured trading data into natural language
    representations for semantic similarity search.
    """
    
    def __init__(self):
        self.logger = logging.getLogger("cthulu.integrations.embedder")
    
    def signal_to_text(
        self,
        signal: Any,
        indicators: Dict[str, Any],
        regime: str
    ) -> str:
        """
        Convert a signal to natural language text.
        
        Args:
            signal: Trading signal (dataclass or dict)
            indicators: Current indicator values
            regime: Market regime classification
        
        Returns:
            Natural language text representation
        """
        # Extract signal attributes
        if hasattr(signal, "__dict__"):
            sig = signal.__dict__
        elif isinstance(signal, dict):
            sig = signal
        else:
            sig = {"raw": str(signal)}
        
        symbol = sig.get("symbol", "UNKNOWN")
        side = sig.get("side", sig.get("direction", "UNKNOWN")).upper()
        confidence = sig.get("confidence", 0.0)
        price = sig.get("price", sig.get("entry_price", 0.0))
        stop_loss = sig.get("stop_loss", sig.get("sl", 0.0))
        take_profit = sig.get("take_profit", sig.get("tp", 0.0))
        strategy = sig.get("strategy_name", sig.get("strategy", "unknown"))
        timeframe = sig.get("timeframe", "M15")
        reason = sig.get("reason", "")
        
        # Build indicator summary
        ind_parts = []
        for key, value in indicators.items():
            if isinstance(value, float):
                ind_parts.append(f"{key}: {value:.2f}")
            else:
                ind_parts.append(f"{key}: {value}")
        ind_summary = ", ".join(ind_parts) if ind_parts else "N/A"
        
        # Compose natural language text
        text = f"""[TradeSignal] Symbol: {symbol} | Direction: {side} | Confidence: {confidence:.2f}
Regime: {regime} | {ind_summary}
Entry Price: {price:.5f} | Stop Loss: {stop_loss:.5f} | Take Profit: {take_profit:.5f}
Strategy: {strategy} | Timeframe: {timeframe}
Reason: {reason if reason else 'Signal conditions met'}"""
        
        return text.strip()
    
    def trade_to_text(self, trade: Any, outcome: Dict[str, Any]) -> str:
        """
        Convert a completed trade to natural language text.
        
        Args:
            trade: Completed trade record
            outcome: Trade outcome details
        
        Returns:
            Natural language text representation
        """
        # Extract trade attributes
        if hasattr(trade, "__dict__"):
            tr = trade.__dict__
        elif isinstance(trade, dict):
            tr = trade
        else:
            tr = {"raw": str(trade)}
        
        symbol = tr.get("symbol", outcome.get("symbol", "UNKNOWN"))
        side = tr.get("side", tr.get("direction", "UNKNOWN")).upper()
        entry_price = tr.get("entry_price", 0.0)
        exit_price = outcome.get("exit_price", tr.get("exit_price", 0.0))
        entry_time = tr.get("entry_time", "")
        exit_time = outcome.get("exit_time", tr.get("exit_time", ""))
        
        pnl = outcome.get("pnl", outcome.get("profit", tr.get("profit", 0.0)))
        exit_reason = outcome.get("exit_reason", tr.get("exit_reason", ""))
        
        # Determine result
        if pnl > 0:
            result = "WIN"
        elif pnl < 0:
            result = "LOSS"
        else:
            result = "BREAKEVEN"
        
        # Calculate duration if possible
        duration = outcome.get("duration", "unknown")
        if duration == "unknown" and entry_time and exit_time:
            try:
                if isinstance(entry_time, str):
                    entry_dt = datetime.fromisoformat(entry_time.replace("Z", ""))
                else:
                    entry_dt = entry_time
                if isinstance(exit_time, str):
                    exit_dt = datetime.fromisoformat(exit_time.replace("Z", ""))
                else:
                    exit_dt = exit_time
                delta = exit_dt - entry_dt
                hours = delta.total_seconds() / 3600
                duration = f"{hours:.2f} hours"
            except Exception:
                pass
        
        # Calculate risk/reward if available
        rr = outcome.get("risk_reward", "N/A")
        
        text = f"""[ExecutedTrade] Symbol: {symbol} | Direction: {side} | Result: {result}
Entry: {entry_price:.5f} @ {entry_time}
Exit: {exit_price:.5f} @ {exit_time} | Duration: {duration}
P&L: {pnl:+.2f} | Risk/Reward: {rr} | Exit Reason: {exit_reason}"""
        
        return text.strip()
    
    def market_snapshot_to_text(
        self,
        df: Any,
        symbol: str,
        indicators: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Convert market data to natural language text.
        
        Args:
            df: DataFrame with OHLCV data
            symbol: Trading symbol
            indicators: Optional indicator values
        
        Returns:
            Natural language text representation
        """
        if df is None or len(df) == 0:
            return f"[MarketSnapshot] Symbol: {symbol} | No data available"
        
        # Get latest bar
        try:
            latest = df.iloc[-1]
            open_p = latest.get("open", 0)
            high_p = latest.get("high", 0)
            low_p = latest.get("low", 0)
            close_p = latest.get("close", 0)
            volume = latest.get("volume", 0)
            
            # Calculate basic stats
            change = ((close_p - open_p) / open_p * 100) if open_p > 0 else 0
            range_pct = ((high_p - low_p) / low_p * 100) if low_p > 0 else 0
            
            # Build indicator summary
            ind_text = ""
            if indicators:
                ind_parts = []
                for key, value in indicators.items():
                    if isinstance(value, float):
                        ind_parts.append(f"{key}: {value:.2f}")
                    else:
                        ind_parts.append(f"{key}: {value}")
                ind_text = f"\nIndicators: {', '.join(ind_parts)}"
            
            text = f"""[MarketSnapshot] Symbol: {symbol}
Open: {open_p:.5f} | High: {high_p:.5f} | Low: {low_p:.5f} | Close: {close_p:.5f}
Volume: {volume} | Change: {change:+.2f}% | Range: {range_pct:.2f}%{ind_text}"""
            
            return text.strip()
            
        except Exception as e:
            self.logger.warning(f"Failed to convert market snapshot: {e}")
            return f"[MarketSnapshot] Symbol: {symbol} | Conversion error"
    
    def build_query(self, current_state: Dict[str, Any]) -> str:
        """
        Build a query from current market state.
        
        Args:
            current_state: Dictionary with current market conditions
        
        Returns:
            Query text for similarity search
        """
        symbol = current_state.get("symbol", "")
        regime = current_state.get("regime", "UNKNOWN")
        indicators = current_state.get("indicators", {})
        price = current_state.get("price", 0)
        
        # Build indicator summary
        ind_parts = []
        for key, value in indicators.items():
            if isinstance(value, float):
                ind_parts.append(f"{key}: {value:.2f}")
            else:
                ind_parts.append(f"{key}: {value}")
        ind_summary = ", ".join(ind_parts) if ind_parts else ""
        
        query = f"""Market conditions for {symbol}
Regime: {regime}
Current Price: {price:.5f}
{ind_summary}
Looking for similar historical contexts and trade outcomes."""
        
        return query.strip()
    
    def cognition_to_text(self, cognition: Dict[str, Any]) -> str:
        """
        Convert cognition engine insight to text.
        
        Args:
            cognition: Cognition engine output
        
        Returns:
            Natural language text representation
        """
        regime = cognition.get("regime", "UNKNOWN")
        prediction = cognition.get("prediction", {})
        sentiment = cognition.get("sentiment", "neutral")
        confidence = cognition.get("confidence", 0.0)
        
        pred_direction = prediction.get("direction", "")
        pred_strength = prediction.get("strength", 0.0)
        
        text = f"""[CognitionInsight] Regime: {regime} | Sentiment: {sentiment}
Prediction: {pred_direction} (strength: {pred_strength:.2f})
Overall Confidence: {confidence:.2f}"""
        
        return text.strip()
