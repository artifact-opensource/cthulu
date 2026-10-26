"""
ML Training Pipeline - Orchestrates Model Training and Optimization

This script provides:
1. Price predictor training
2. Tier optimizer enhancement
3. RL position sizer training
4. Feature pipeline fitting
5. Model evaluation and promotion

Part of Cthulu ML Pipeline v6.0.0

Usage:
    python -m training.train_models --mode all
    python -m training.train_models --mode predictor --data-path path/to/data.csv
    python -m training.train_models --mode tier_optimizer
    python -m training.train_models --mode rl_sizer
"""

from __future__ import annotations
import os
import sys
import json
import gzip
import glob
import argparse
import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
import numpy as np
import pandas as pd

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ML_RL.feature_pipeline import FeaturePipeline, get_feature_pipeline
from ML_RL.mlops import ModelRegistry, DriftDetector, get_model_registry, get_drift_detector
from ML_RL.rl_position_sizer import RLPositionSizer, get_rl_position_sizer, RLState, SizeAction
from ML_RL.llm_analysis import LLMAnalyzer, get_llm_analyzer, MarketContext

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("cthulu.ml.train")

# Data directory
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
COGNITION_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cognition', 'data')
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cthulu.db')
os.makedirs(DATA_DIR, exist_ok=True)


class ModelTrainer:
    """
    Orchestrates training of all ML models.
    
    Handles:
    - Data loading and preprocessing
    - Feature extraction
    - Model training
    - Evaluation
    - Model registration and promotion
    """
    
    def __init__(self):
        self.feature_pipeline = get_feature_pipeline()
        self.model_registry = get_model_registry()
        self.drift_detector = get_drift_detector()
        self.rl_sizer = get_rl_position_sizer()
        self.llm_analyzer = get_llm_analyzer()
        
        logger.info("ModelTrainer initialized")
    
    def load_jsonl_events(self, data_dir: str) -> List[Dict[str, Any]]:
        """
        Load events from compressed JSONL files.
        
        Args:
            data_dir: Directory containing .jsonl.gz files
            
        Returns:
            List of event dictionaries
        """
        events = []
        pattern = os.path.join(data_dir, '*.jsonl.gz')
        files = sorted(glob.glob(pattern))
        
        logger.info(f"Loading events from {len(files)} JSONL files in {data_dir}")
        
        for filepath in files:
            try:
                with gzip.open(filepath, 'rt', encoding='utf-8') as f:
                    for line in f:
                        try:
                            event = json.loads(line.strip())
                            events.append(event)
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                logger.debug(f"Could not read {filepath}: {e}")
                
        logger.info(f"Loaded {len(events)} events from JSONL files")
        return events
    
    def load_trades_from_db(self) -> List[Dict[str, Any]]:
        """Load trades from SQLite database."""
        trades = []
        
        if not os.path.exists(DB_PATH):
            logger.warning(f"Database not found: {DB_PATH}")
            return trades
            
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Load trades
            cursor.execute('SELECT * FROM trades ORDER BY id')
            for row in cursor.fetchall():
                trades.append(dict(row))
                
            conn.close()
            logger.info(f"Loaded {len(trades)} trades from database")
            
        except Exception as e:
            logger.warning(f"Could not load trades from database: {e}")
            
        return trades
    
    def load_signals_from_db(self) -> List[Dict[str, Any]]:
        """Load signals from SQLite database."""
        signals = []
        
        if not os.path.exists(DB_PATH):
            return signals
            
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM signals ORDER BY id')
            for row in cursor.fetchall():
                signals.append(dict(row))
                
            conn.close()
            logger.info(f"Loaded {len(signals)} signals from database")
            
        except Exception as e:
            logger.warning(f"Could not load signals from database: {e}")
            
        return signals
    
    def load_data(self, path: Optional[str] = None, symbol: str = "GOLD#") -> pd.DataFrame:
        """
        Load training data from multiple sources.
        
        Priority:
        1. Explicit CSV path
        2. MT5 via HistoricalDataManager
        3. Backtesting cache files
        4. Synthetic data (fallback)
        
        Args:
            path: Path to CSV file, or None to use default
            symbol: Symbol to load data for
            
        Returns:
            DataFrame with OHLCV data
        """
        # 1. Explicit CSV path
        if path and os.path.exists(path):
            df = pd.read_csv(path, parse_dates=['time'] if 'time' in pd.read_csv(path, nrows=1).columns else False)
            logger.info(f"Loaded {len(df)} rows from {path}")
            return df
        
        # 2. Try MT5 via backtesting data manager
        try:
            from backtesting.data_manager import HistoricalDataManager, DataSource
            dm = HistoricalDataManager()
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=90)
            
            df, metadata = dm.fetch_data(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                timeframe='M30',
                source=DataSource.MT5,
                use_cache=True
            )
            
            # Reset index to get 'time' as column
            df = df.reset_index()
            df.rename(columns={'index': 'time'}, inplace=True)
            
            logger.info(f"Loaded {len(df)} rows from MT5/HistoricalDataManager (quality={metadata.data_quality_score:.2f})")
            return df
            
        except Exception as e:
            logger.warning(f"Could not load from MT5: {e}")
        
        # 3. Try to find cached pickle files in backtesting cache
        try:
            from backtesting import BACKTEST_CACHE_DIR
            cache_files = glob.glob(os.path.join(BACKTEST_CACHE_DIR, f"{symbol}*.pkl"))
            if cache_files:
                import pickle
                with open(cache_files[0], 'rb') as f:
                    df, metadata = pickle.load(f)
                df = df.reset_index()
                df.rename(columns={'index': 'time'}, inplace=True)
                logger.info(f"Loaded {len(df)} rows from cache: {cache_files[0]}")
                return df
        except Exception as e:
            logger.debug(f"Could not load from cache: {e}")
        
        # 4. Fallback to synthetic data
        logger.warning("Using synthetic data for training - consider fetching real data")
        return self._generate_synthetic_data(5000)
    
    def _generate_synthetic_data(self, n_bars: int) -> pd.DataFrame:
        """Generate synthetic OHLCV data for testing."""
        np.random.seed(42)
        
        # Random walk price
        returns = np.random.normal(0, 0.002, n_bars)
        price = 100 * np.exp(np.cumsum(returns))
        
        # Generate OHLCV
        data = {
            'time': pd.date_range(start='2025-01-01', periods=n_bars, freq='30min'),
            'open': price,
            'high': price * (1 + np.abs(np.random.normal(0, 0.001, n_bars))),
            'low': price * (1 - np.abs(np.random.normal(0, 0.001, n_bars))),
            'close': price * (1 + np.random.normal(0, 0.0005, n_bars)),
            'volume': np.random.exponential(1000, n_bars)
        }
        
        return pd.DataFrame(data)
    
    def train_price_predictor(
        self,
        df: pd.DataFrame,
        epochs: int = 100,
        batch_size: int = 32,
        validation_split: float = 0.2,
        target_horizon: int = 5,
        target_threshold: float = 0.1
    ) -> Dict[str, Any]:
        """
        Train the price predictor model.
        
        Args:
            df: Training data
            epochs: Training epochs
            batch_size: Mini-batch size
            validation_split: Validation data fraction
            target_horizon: Bars ahead to predict
            target_threshold: % move threshold for classification
            
        Returns:
            Training results dictionary
        """
        logger.info(f"Training price predictor: {len(df)} bars, {epochs} epochs")
        
        try:
            from cthulu.cognition.price_predictor import PricePredictor
            predictor = PricePredictor()
        except ImportError:
            logger.error("Could not import PricePredictor")
            return {"error": "Import failed"}
        
        # Train
        import time
        start_time = time.time()
        
        result = predictor.train(
            df,
            epochs=epochs,
            batch_size=batch_size,
            validation_split=validation_split,
            move_threshold_pct=target_threshold
        )
        
        training_time = time.time() - start_time
        
        # Save model
        model_path = os.path.join(DATA_DIR, 'models', 'price_predictor.json')
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        predictor.save(model_path)
        
        # Register model
        model_id = self.model_registry.register(
            model_type="cthulu-predictor",
            version="v5.3.0",
            metrics={
                "accuracy": result.accuracy,
                "final_loss": result.final_loss,
                "epochs": result.epochs_trained
            },
            hyperparameters={
                "epochs": epochs,
                "batch_size": batch_size,
                "target_horizon": target_horizon,
                "target_threshold": target_threshold
            },
            feature_names=self.feature_pipeline.feature_names,
            training_samples=result.samples_used,
            validation_accuracy=result.accuracy,
            description=f"Price predictor trained on {len(df)} bars"
        )
        
        logger.info(f"Price predictor training complete: accuracy={result.accuracy:.2%}, loss={result.final_loss:.4f}")
        
        return {
            "model_id": model_id,
            "accuracy": result.accuracy,
            "final_loss": result.final_loss,
            "epochs_trained": result.epochs_trained,
            "samples_used": result.samples_used,
            "training_time": training_time
        }
    
    def enhance_tier_optimizer(
        self,
        trades_data: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Enhance the tier optimizer with historical trade data.
        
        Args:
            trades_data: List of historical trade dictionaries
            
        Returns:
            Optimization results
        """
        logger.info("Enhancing tier optimizer")
        
        try:
            from ML_RL.tier_optimizer import TierOptimizer
            optimizer = TierOptimizer()
        except ImportError:
            try:
                from cognition.tier_optimizer import TierOptimizer
                optimizer = TierOptimizer()
            except ImportError:
                logger.error("Could not import TierOptimizer")
                return {"error": "Import failed"}
        
        # If no trades provided, load from database
        if not trades_data:
            trades_data = self.load_trades_from_db()
        
        # Also load from JSONL events for additional data
        ml_events = self.load_jsonl_events(os.path.join(DATA_DIR, 'raw'))
        cog_events = self.load_jsonl_events(os.path.join(COGNITION_DATA_DIR, 'raw'))
        
        # Process trades from database
        outcomes_added = 0
        for trade in trades_data:
            try:
                # Synthesize scaling outcome from trade data
                pnl = trade.get('pnl', 0) or trade.get('profit', 0) or 0
                if pnl != 0:
                    # Create synthetic tier outcome
                    optimizer.record_outcome(
                        ticket=trade.get('ticket', trade.get('id', 0)),
                        tier='tier_1',
                        profit_threshold_triggered=abs(pnl) / max(trade.get('volume', 0.01) * 100, 1),
                        close_pct=0.25,
                        profit_captured=pnl if pnl > 0 else 0,
                        remaining_profit=0,
                        account_balance=1000,
                        volatility_atr=None,
                        momentum_adx=None,
                        symbol=trade.get('symbol', 'GOLD#')
                    )
                    outcomes_added += 1
            except Exception as e:
                logger.debug(f"Could not process trade: {e}")
        
        # Process JSONL events for execution data
        for event in ml_events + cog_events:
            try:
                if event.get('event_type') in ['execution', 'trade_closed', 'position_closed']:
                    payload = event.get('payload', {})
                    pnl = payload.get('pnl', 0) or payload.get('profit', 0)
                    if pnl != 0:
                        optimizer.record_outcome(
                            ticket=payload.get('ticket', 0),
                            tier='tier_1',
                            profit_threshold_triggered=abs(pnl) / 100,
                            close_pct=0.25,
                            profit_captured=pnl if pnl > 0 else 0,
                            remaining_profit=0,
                            account_balance=1000,
                            symbol=payload.get('symbol', '')
                        )
                        outcomes_added += 1
            except Exception as e:
                logger.debug(f"Could not process event: {e}")
        
        # Run optimization
        if outcomes_added >= 10:
            optimization_result = optimizer.optimize()
            optimizer.save()
            
            logger.info(f"Tier optimizer enhanced: {outcomes_added} outcomes, improvement={optimization_result.get('improvement', 0):.2%}")
            
            return {
                "outcomes_processed": outcomes_added,
                "optimization_result": optimization_result
            }
        else:
            logger.info(f"Insufficient data for optimization: {outcomes_added} outcomes")
            return {
                "outcomes_processed": outcomes_added,
                "message": "Insufficient data for optimization"
            }
    
    def train_rl_sizer(
        self,
        episodes: int = 1000,
        trades_data: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Train the RL position sizer.
        
        Args:
            episodes: Training episodes
            trades_data: Historical trades for offline training
            
        Returns:
            Training results
        """
        logger.info(f"Training RL position sizer: {episodes} episodes")
        
        # Load trades from database if not provided
        if not trades_data:
            trades_data = self.load_trades_from_db()
            
        # Also load signals for additional context
        signals = self.load_signals_from_db()
        
        # Load ML events for market snapshots
        ml_events = self.load_jsonl_events(os.path.join(DATA_DIR, 'raw'))
        
        # If we have real data, train on it first
        if trades_data:
            logger.info(f"Training RL on {len(trades_data)} historical trades")
            result = self._train_rl_from_trades(trades_data, signals, ml_events)
        else:
            result = {"historical_episodes": 0, "historical_reward": 0}
            
        # Then run additional simulated episodes
        sim_episodes = max(episodes - len(trades_data) * 5, 100)
        logger.info(f"Running {sim_episodes} simulated episodes for exploration")
        sim_result = self._train_rl_simulated(sim_episodes)
        
        # Combine results
        return {
            "historical_episodes": result.get("historical_episodes", 0),
            "simulated_episodes": sim_result["episodes"],
            "total_reward": result.get("historical_reward", 0) + sim_result["total_reward"],
            "avg_loss": sim_result["avg_loss"],
            "epsilon": sim_result["epsilon"]
        }
    
    def _train_rl_from_trades(
        self,
        trades: List[Dict[str, Any]],
        signals: List[Dict[str, Any]],
        events: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Train RL from historical trade data."""
        total_reward = 0
        losses = []
        episodes = 0
        
        # Build signal lookup by timestamp for context
        signal_lookup = {}
        for sig in signals:
            ts = sig.get('timestamp') or sig.get('created_at')
            if ts:
                signal_lookup[ts] = sig
        
        for trade in trades:
            try:
                # Build state from trade data
                state = RLState(
                    trend_strength=trade.get('trend_strength', 0.5),
                    volatility_regime=trade.get('volatility', 0.5),
                    momentum_score=trade.get('momentum', 0),
                    signal_confidence=trade.get('confidence', 0.5),
                    entry_quality=trade.get('entry_quality', 0.5),
                    risk_reward_ratio=trade.get('risk_reward', 1.5),
                    current_exposure_pct=trade.get('exposure', 0),
                    win_rate_recent=trade.get('win_rate', 0.5),
                    drawdown_pct=trade.get('drawdown', 0),
                    max_position_pct=0.1,
                    remaining_daily_risk=1.0
                )
                
                # Determine what action was taken
                size_mult = trade.get('position_size_mult', 1.0)
                if size_mult == 0:
                    action = SizeAction.SKIP
                elif size_mult <= 0.3:
                    action = SizeAction.MICRO
                elif size_mult <= 0.6:
                    action = SizeAction.SMALL
                elif size_mult <= 1.1:
                    action = SizeAction.STANDARD
                elif size_mult <= 1.3:
                    action = SizeAction.MODERATE
                else:
                    action = SizeAction.AGGRESSIVE
                
                # Calculate reward from actual outcome
                pnl = trade.get('pnl', 0)
                risk_taken = trade.get('risk_pct', 1)
                duration = trade.get('duration_bars', 10)
                
                reward = self.rl_sizer.calculate_reward(
                    action=action,
                    multiplier=size_mult,
                    pnl=pnl,
                    risk_taken=risk_taken,
                    max_risk=5.0,
                    trade_duration_bars=duration
                )
                
                total_reward += reward
                
                # Create next state (simplified)
                next_state = RLState(
                    trend_strength=state.trend_strength,
                    volatility_regime=state.volatility_regime,
                    momentum_score=state.momentum_score,
                    signal_confidence=state.signal_confidence,
                    entry_quality=state.entry_quality,
                    risk_reward_ratio=state.risk_reward_ratio,
                    current_exposure_pct=0,  # Trade closed
                    win_rate_recent=state.win_rate_recent * 0.9 + (0.1 if pnl > 0 else 0),
                    drawdown_pct=max(0, state.drawdown_pct - pnl / 100),
                    max_position_pct=state.max_position_pct,
                    remaining_daily_risk=state.remaining_daily_risk
                )
                
                # Store experience
                self.rl_sizer.store_experience(state, action, reward, next_state, done=True)
                
                # Train step
                loss = self.rl_sizer.train_step()
                if loss is not None:
                    losses.append(loss)
                
                episodes += 1
                
            except Exception as e:
                logger.debug(f"Could not process trade for RL: {e}")
        
        # Save model
        self.rl_sizer.save()
        
        avg_loss = np.mean(losses) if losses else 0
        logger.info(f"RL historical training: {episodes} episodes, reward={total_reward:.2f}, avg_loss={avg_loss:.4f}")
        
        return {
            "historical_episodes": episodes,
            "historical_reward": total_reward,
            "avg_loss": avg_loss
        }
    
    def _train_rl_simulated(self, episodes: int) -> Dict[str, Any]:
        """Train RL sizer with simulated episodes."""
        total_reward = 0
        losses = []
        
        for ep in range(episodes):
            # Generate random state
            state = RLState(
                trend_strength=np.random.uniform(0, 1),
                volatility_regime=np.random.uniform(0, 1),
                momentum_score=np.random.uniform(-1, 1),
                signal_confidence=np.random.uniform(0.3, 0.9),
                entry_quality=np.random.uniform(0.3, 1.0),
                risk_reward_ratio=np.random.uniform(1.0, 3.0),
                current_exposure_pct=np.random.uniform(0, 0.1),
                win_rate_recent=np.random.uniform(0.4, 0.7),
                drawdown_pct=np.random.uniform(0, 0.1),
                max_position_pct=0.1,
                remaining_daily_risk=np.random.uniform(0.5, 1.0)
            )
            
            # Select action
            action, multiplier = self.rl_sizer.select_action(state, explore=True)
            
            # Simulate outcome
            # Higher quality setups have higher expected returns
            expected_win_prob = (state.signal_confidence + state.entry_quality) / 2
            won = np.random.random() < expected_win_prob
            
            if won:
                pnl = multiplier * state.risk_reward_ratio * np.random.uniform(0.5, 1.5)
            else:
                pnl = -multiplier * np.random.uniform(0.5, 1.0)
            
            if action == SizeAction.SKIP:
                pnl = 0  # No trade
            
            # Calculate reward
            reward = self.rl_sizer.calculate_reward(
                action=action,
                multiplier=multiplier,
                pnl=pnl,
                risk_taken=multiplier * 2,  # Rough estimate
                max_risk=5.0,
                trade_duration_bars=np.random.randint(5, 50)
            )
            
            total_reward += reward
            
            # Create next state
            next_state = RLState(
                trend_strength=np.random.uniform(0, 1),
                volatility_regime=np.random.uniform(0, 1),
                momentum_score=np.random.uniform(-1, 1),
                signal_confidence=np.random.uniform(0.3, 0.9),
                entry_quality=np.random.uniform(0.3, 1.0),
                risk_reward_ratio=np.random.uniform(1.0, 3.0),
                current_exposure_pct=0,
                win_rate_recent=state.win_rate_recent * 0.9 + (0.1 if pnl > 0 else 0),
                drawdown_pct=max(0, state.drawdown_pct - pnl / 100),
                max_position_pct=0.1,
                remaining_daily_risk=state.remaining_daily_risk
            )
            
            # Store and train
            self.rl_sizer.store_experience(state, action, reward, next_state, done=True)
            loss = self.rl_sizer.train_step()
            if loss is not None:
                losses.append(loss)
            
            if (ep + 1) % 100 == 0:
                avg_loss = np.mean(losses[-100:]) if losses else 0
                logger.info(f"Episode {ep+1}/{episodes}: avg_loss={avg_loss:.4f}, epsilon={self.rl_sizer.epsilon:.3f}")
        
        # Save model
        self.rl_sizer.save()
        
        avg_loss = np.mean(losses) if losses else 0
        logger.info(f"RL sizer training complete: total_reward={total_reward:.2f}, avg_loss={avg_loss:.4f}")
        
        return {
            "episodes": episodes,
            "total_reward": total_reward,
            "avg_loss": avg_loss,
            "epsilon": self.rl_sizer.epsilon
        }
    
    def fit_feature_pipeline(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Fit the feature pipeline normalization on data.
        
        Args:
            df: Training data
            
        Returns:
            Pipeline statistics
        """
        logger.info(f"Fitting feature pipeline on {len(df)} bars")
        
        X, y, feature_names = self.feature_pipeline.prepare_training_data(df)
        
        # Save pipeline
        pipeline_path = os.path.join(DATA_DIR, 'models', 'feature_pipeline.json')
        os.makedirs(os.path.dirname(pipeline_path), exist_ok=True)
        self.feature_pipeline.save(pipeline_path)
        
        logger.info(f"Feature pipeline fitted: {len(feature_names)} features, {len(X)} samples")
        
        return {
            "feature_count": len(feature_names),
            "samples": len(X),
            "label_distribution": {
                "long": int(np.sum(y[:, 0])),
                "short": int(np.sum(y[:, 1])),
                "neutral": int(np.sum(y[:, 2]))
            }
        }
    
    def run_full_training(self, data_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Run full training pipeline.
        
        Args:
            data_path: Optional path to training data
            
        Returns:
            Combined results from all training
        """
        logger.info("=" * 60)
        logger.info("STARTING FULL ML TRAINING PIPELINE")
        logger.info("=" * 60)
        
        results = {}
        
        # Load data
        df = self.load_data(data_path)
        
        # 1. Fit feature pipeline
        logger.info("\n[1/4] Fitting Feature Pipeline...")
        results['feature_pipeline'] = self.fit_feature_pipeline(df)
        
        # 2. Train price predictor
        logger.info("\n[2/4] Training Price Predictor...")
        results['price_predictor'] = self.train_price_predictor(df)
        
        # 3. Enhance tier optimizer
        logger.info("\n[3/4] Enhancing Tier Optimizer...")
        results['tier_optimizer'] = self.enhance_tier_optimizer()
        
        # 4. Train RL sizer
        logger.info("\n[4/4] Training RL Position Sizer...")
        results['rl_sizer'] = self.train_rl_sizer(episodes=500)
        
        logger.info("\n" + "=" * 60)
        logger.info("TRAINING COMPLETE")
        logger.info("=" * 60)
        
        # Save results
        results_path = os.path.join(DATA_DIR, 'training_results.json')
        with open(results_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"Results saved to {results_path}")
        
        return results


def main():
    """Main entry point for training script."""
    parser = argparse.ArgumentParser(description="Cthulu ML Training Pipeline")
    parser.add_argument('--mode', choices=['all', 'predictor', 'tier_optimizer', 'rl_sizer', 'features'],
                       default='all', help='Training mode')
    parser.add_argument('--data-path', type=str, default=None, help='Path to training data CSV')
    parser.add_argument('--epochs', type=int, default=100, help='Training epochs')
    parser.add_argument('--episodes', type=int, default=500, help='RL training episodes')
    
    args = parser.parse_args()
    
    trainer = ModelTrainer()
    
    if args.mode == 'all':
        results = trainer.run_full_training(args.data_path)
    elif args.mode == 'predictor':
        df = trainer.load_data(args.data_path)
        results = trainer.train_price_predictor(df, epochs=args.epochs)
    elif args.mode == 'tier_optimizer':
        results = trainer.enhance_tier_optimizer()
    elif args.mode == 'rl_sizer':
        results = trainer.train_rl_sizer(episodes=args.episodes)
    elif args.mode == 'features':
        df = trainer.load_data(args.data_path)
        results = trainer.fit_feature_pipeline(df)
    
    print("\nTraining Results:")
    print(json.dumps(results, indent=2, default=str))


if __name__ == '__main__':
    main()
