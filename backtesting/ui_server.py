"""
Backtesting UI Server

Flask/FastAPI server for backtesting UI communication.
Provides REST API endpoints and WebSocket support for real-time updates.
"""

import logging
import json
import asyncio
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, asdict
import uuid

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# Cthulu imports - use try/except for graceful degradation
try:
    from backtesting.engine import BacktestEngine, BacktestConfig, SpeedMode
    from backtesting.optimizer import ParameterOptimizer
    from backtesting.reporter import BacktestReporter
    from strategy.base import Strategy
    from config.loader import load_config
    CTHULU_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Some Cthulu modules not available: {e}")
    print("Server will run in limited mode")
    CTHULU_AVAILABLE = False
    # Create dummy classes for type hints
    class BacktestEngine: pass
    class BacktestConfig: pass
    class SpeedMode: pass
    class ParameterOptimizer: pass
    class BacktestReporter: pass
    class Strategy: pass

logger = logging.getLogger(__name__)


@dataclass
class BacktestJob:
    """Backtest job tracking"""
    job_id: str
    status: str  # QUEUED, RUNNING, COMPLETED, FAILED
    config: Dict[str, Any]
    progress: float
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'job_id': self.job_id,
            'status': self.status,
            'config': self.config,
            'progress': self.progress,
            'result': self.result,
            'error': self.error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }


class BacktestServer:
    """
    Flask server for backtesting UI.
    
    Provides REST API and WebSocket endpoints for:
    - Running backtests
    - Monitoring progress
    - Retrieving results
    - Configuration management
    - Optimization
    """
    
    def __init__(self, host: str = '127.0.0.1', port: int = 5000):
        """
        Initialize backtest server.
        
        Args:
            host: Server host
            port: Server port
        """
        self.app = Flask(__name__)
        CORS(self.app)  # Enable CORS for Angular frontend
        self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode='threading')
        
        self.host = host
        self.port = port
        
        # Job tracking
        self.jobs: Dict[str, BacktestJob] = {}
        
        # Configuration storage
        self.config_dir = Path("./backtesting/configs")
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Results storage
        self.results_dir = Path("./backtesting/results")
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup routes
        self._setup_routes()
        self._setup_socketio()
        
        self.logger = logging.getLogger(__name__)
        
    def _setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/api/health', methods=['GET'])
        def health():
            """Health check endpoint"""
            return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})
        
        @self.app.route('/api/backtest/run', methods=['POST'])
        def run_backtest():
            """Start a backtest"""
            try:
                data = request.json
                
                # Create job
                job_id = str(uuid.uuid4())
                job = BacktestJob(
                    job_id=job_id,
                    status='QUEUED',
                    config=data,
                    progress=0.0,
                    created_at=datetime.now()
                )
                
                self.jobs[job_id] = job
                
                # Start backtest asynchronously
                self.socketio.start_background_task(self._run_backtest_async, job_id)
                
                return jsonify({
                    'job_id': job_id,
                    'status': 'QUEUED',
                    'message': 'Backtest queued successfully'
                })
                
            except Exception as e:
                self.logger.error(f"Error starting backtest: {e}", exc_info=True)
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/backtest/status/<job_id>', methods=['GET'])
        def get_status(job_id):
            """Get backtest status"""
            job = self.jobs.get(job_id)
            
            if not job:
                return jsonify({'error': 'Job not found'}), 404
                
            return jsonify(job.to_dict())
        
        @self.app.route('/api/backtest/results/<job_id>', methods=['GET'])
        def get_results(job_id):
            """Get backtest results"""
            job = self.jobs.get(job_id)
            
            if not job:
                return jsonify({'error': 'Job not found'}), 404
                
            if job.status != 'COMPLETED':
                return jsonify({'error': 'Backtest not completed'}), 400
                
            return jsonify(job.result)
        
        @self.app.route('/api/backtest/jobs', methods=['GET'])
        def list_jobs():
            """List all backtest jobs"""
            jobs = [job.to_dict() for job in self.jobs.values()]
            jobs.sort(key=lambda x: x['created_at'], reverse=True)
            return jsonify(jobs)
        
        @self.app.route('/api/configs', methods=['GET'])
        def list_configs():
            """List saved configurations"""
            configs = []
            
            for config_file in self.config_dir.glob('*.json'):
                try:
                    with open(config_file, 'r') as f:
                        config = json.load(f)
                        configs.append({
                            'name': config_file.stem,
                            'config': config,
                            'modified_at': datetime.fromtimestamp(
                                config_file.stat().st_mtime
                            ).isoformat()
                        })
                except Exception as e:
                    self.logger.error(f"Error loading config {config_file}: {e}")
                    
            return jsonify(configs)
        
        @self.app.route('/api/configs', methods=['POST'])
        def save_config():
            """Save a configuration"""
            try:
                data = request.json
                name = data.get('name', f'config_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
                config = data.get('config', {})
                
                config_file = self.config_dir / f"{name}.json"
                
                with open(config_file, 'w') as f:
                    json.dump(config, f, indent=2)
                    
                return jsonify({
                    'message': 'Configuration saved',
                    'name': name,
                    'path': str(config_file)
                })
                
            except Exception as e:
                self.logger.error(f"Error saving config: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/configs/<name>', methods=['DELETE'])
        def delete_config(name):
            """Delete a configuration"""
            try:
                config_file = self.config_dir / f"{name}.json"
                
                if not config_file.exists():
                    return jsonify({'error': 'Configuration not found'}), 404
                    
                config_file.unlink()
                
                return jsonify({'message': 'Configuration deleted'})
                
            except Exception as e:
                self.logger.error(f"Error deleting config: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/optimize', methods=['POST'])
        def run_optimization():
            """Run parameter optimization"""
            try:
                data = request.json
                
                # Create optimization job
                job_id = str(uuid.uuid4())
                job = BacktestJob(
                    job_id=job_id,
                    status='QUEUED',
                    config=data,
                    progress=0.0,
                    created_at=datetime.now()
                )
                
                self.jobs[job_id] = job
                
                # Start optimization asynchronously
                self.socketio.start_background_task(self._run_optimization_async, job_id)
                
                return jsonify({
                    'job_id': job_id,
                    'status': 'QUEUED',
                    'message': 'Optimization queued successfully'
                })
                
            except Exception as e:
                self.logger.error(f"Error starting optimization: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/', methods=['GET'])
        def serve_index():
            """Serve UI index page"""
            ui_dir = Path(__file__).parent / 'ui' / 'dist'
            if not ui_dir.exists():
                ui_dir = Path(__file__).parent / 'ui'
            return send_from_directory(ui_dir, 'index.html')
        
        @self.app.route('/api/ui/<path:filename>', methods=['GET'])
        def serve_ui(filename):
            """Serve UI files"""
            ui_dir = Path(__file__).parent / 'ui' / 'dist'
            if not ui_dir.exists():
                ui_dir = Path(__file__).parent / 'ui'
            return send_from_directory(ui_dir, filename)
        
        @self.app.route('/<path:filename>', methods=['GET'])
        def serve_ui_files(filename):
            """Serve any UI file"""
            ui_dir = Path(__file__).parent / 'ui' / 'dist'
            if not ui_dir.exists():
                ui_dir = Path(__file__).parent / 'ui'
            try:
                return send_from_directory(ui_dir, filename)
            except:
                # If file not found, return index.html for SPA routing
                return send_from_directory(ui_dir, 'index.html')
    
    def _setup_socketio(self):
        """Setup SocketIO event handlers"""
        
        @self.socketio.on('connect')
        def handle_connect():
            """Handle client connection"""
            self.logger.info("Client connected")
            emit('connected', {'message': 'Connected to backtest server'})
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            """Handle client disconnection"""
            self.logger.info("Client disconnected")
        
        @self.socketio.on('subscribe')
        def handle_subscribe(data):
            """Subscribe to job updates"""
            job_id = data.get('job_id')
            self.logger.info(f"Client subscribed to job {job_id}")
            emit('subscribed', {'job_id': job_id})
    
    def _run_backtest_async(self, job_id: str):
        """Run backtest asynchronously"""
        job = self.jobs[job_id]
        
        try:
            job.status = 'RUNNING'
            job.started_at = datetime.now()
            
            self._emit_progress(job_id, 0.0, 'Initializing backtest...')
            
            # Parse configuration
            config_data = job.config
            
            # Load data
            self._emit_progress(job_id, 0.1, 'Loading market data...')
            data = self._load_market_data(config_data.get('data_source'))
            
            # Create strategies
            self._emit_progress(job_id, 0.2, 'Initializing strategies...')
            strategies = self._create_strategies(config_data.get('strategies', []))
            
            # Create backtest config
            backtest_config = self._create_backtest_config(config_data)
            
            # Create engine
            engine = BacktestEngine(strategies, backtest_config)
            
            # Run backtest with progress callback
            def progress_callback(progress: float):
                self._emit_progress(
                    job_id,
                    0.2 + (progress * 0.7),
                    f'Running backtest... {progress:.1%}'
                )
            
            self._emit_progress(job_id, 0.2, 'Running backtest...')
            
            result = engine.run(data, progress_callback=progress_callback)
            
            # Generate report
            self._emit_progress(job_id, 0.9, 'Generating report...')
            
            reporter = BacktestReporter()
            report = reporter.generate_report(result)
            
            # Save results
            result_file = self.results_dir / f"{job_id}.json"
            with open(result_file, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            # Update job
            job.status = 'COMPLETED'
            job.result = report
            job.progress = 1.0
            job.completed_at = datetime.now()
            
            self._emit_progress(job_id, 1.0, 'Backtest completed!')
            self._emit_complete(job_id, report)
            
        except Exception as e:
            self.logger.error(f"Backtest error: {e}", exc_info=True)
            job.status = 'FAILED'
            job.error = str(e)
            job.completed_at = datetime.now()
            
            self._emit_error(job_id, str(e))
    
    def _run_optimization_async(self, job_id: str):
        """Run optimization asynchronously"""
        job = self.jobs[job_id]
        
        try:
            job.status = 'RUNNING'
            job.started_at = datetime.now()
            
            self._emit_progress(job_id, 0.0, 'Starting optimization...')
            
            # Parse configuration
            config_data = job.config
            
            # Load data
            data = self._load_market_data(config_data.get('data_source'))
            
            # Create optimizer
            optimizer = ParameterOptimizer()
            
            # Run optimization with progress callback
            def progress_callback(iteration: int, total: int, best_result: Dict[str, Any]):
                progress = iteration / total
                self._emit_progress(
                    job_id,
                    progress,
                    f'Optimization: {iteration}/{total} iterations'
                )
                
                # Emit intermediate results
                self.socketio.emit('optimization_update', {
                    'job_id': job_id,
                    'iteration': iteration,
                    'total': total,
                    'best_result': best_result
                })
            
            # Run optimization
            results = optimizer.optimize(
                data=data,
                param_ranges=config_data.get('param_ranges', {}),
                objective=config_data.get('objective', 'sharpe_ratio'),
                progress_callback=progress_callback
            )
            
            # Update job
            job.status = 'COMPLETED'
            job.result = results
            job.progress = 1.0
            job.completed_at = datetime.now()
            
            self._emit_complete(job_id, results)
            
        except Exception as e:
            self.logger.error(f"Optimization error: {e}", exc_info=True)
            job.status = 'FAILED'
            job.error = str(e)
            job.completed_at = datetime.now()
            
            self._emit_error(job_id, str(e))
    
    def _emit_progress(self, job_id: str, progress: float, message: str):
        """Emit progress update via WebSocket"""
        self.socketio.emit('progress', {
            'job_id': job_id,
            'progress': progress,
            'message': message
        })
    
    def _emit_complete(self, job_id: str, result: Dict[str, Any]):
        """Emit completion event"""
        self.socketio.emit('complete', {
            'job_id': job_id,
            'result': result
        })
    
    def _emit_error(self, job_id: str, error: str):
        """Emit error event"""
        self.socketio.emit('error', {
            'job_id': job_id,
            'error': error
        })
    
    def _load_market_data(self, data_source: Optional[Dict[str, Any]]):
        """Load market data from source"""
        import pandas as pd
        
        # 1. Try CSV path if provided
        if data_source and 'csv_path' in data_source:
            path = Path(data_source['csv_path'])
            if path.exists():
                return pd.read_csv(path, parse_dates=['Date'], index_col='Date')
        
        # 2. Try default project data path
        default_data = Path(__file__).parent.parent / "test_pattern_data.csv"
        if default_data.exists():
            df = pd.read_csv(default_data)
            # Normalize column names for SMA/EMA indicators
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'])
                df.set_index('Date', inplace=True)
            return df
        
        # 3. Create dummy data as last resort
        import numpy as np
        dates = pd.date_range(start='2023-01-01', periods=1000, freq='H')
        prices = 1.1000 + np.cumsum(np.random.normal(0, 0.001, 1000))
        df = pd.DataFrame({
            'open': prices,
            'high': prices + 0.0005,
            'low': prices - 0.0005,
            'close': prices,
            'volume': np.random.randint(100, 1000, 1000)
        }, index=dates)
        
        # Add required indicators if missing
        df['ema_9'] = df['close'].ewm(span=9).mean()
        df['ema_12'] = df['close'].ewm(span=12).mean()
        df['ema_21'] = df['close'].ewm(span=21).mean()
        df['ema_26'] = df['close'].ewm(span=26).mean()
        df['atr'] = 0.0010 # Constant ATR for dummy
        
        return df
    
    def _create_strategies(self, strategy_configs: List[Dict[str, Any]]) -> List[Strategy]:
        """Create strategy instances from configurations"""
        from strategy import (
            SmaCrossover, EmaCrossover, MomentumBreakout, 
            ScalpingStrategy, MeanReversionStrategy, 
            TrendFollowingStrategy, RsiReversalStrategy
        )
        
        STRATEGY_MAP = {
            'sma_crossover': SmaCrossover,
            'ema_crossover': EmaCrossover,
            'momentum_breakout': MomentumBreakout,
            'scalping': ScalpingStrategy,
            'mean_reversion': MeanReversionStrategy,
            'trend_following': TrendFollowingStrategy,
            'rsi_reversal': RsiReversalStrategy
        }
        
        strategies = []
        
        for config in strategy_configs:
            strategy_type = config.get('type')
            if strategy_type in STRATEGY_MAP:
                strategy_cls = STRATEGY_MAP[strategy_type]
                strategies.append(strategy_cls(config))
            else:
                self.logger.warning(f"Unknown strategy type: {strategy_type}")
        
        return strategies
    
    def _create_backtest_config(self, config_data: Dict[str, Any]) -> BacktestConfig:
        """Create backtest configuration"""
        return BacktestConfig(
            initial_capital=config_data.get('initial_capital', 10000.0),
            commission=config_data.get('commission', 0.0001),
            slippage_pct=config_data.get('slippage_pct', 0.0002),
            speed_mode=SpeedMode(config_data.get('speed_mode', 'fast'))
        )
    
    def run(self):
        """Start the server"""
        self.logger.info(f"Starting backtest server on {self.host}:{self.port}")
        self.socketio.run(
            self.app, 
            host=self.host, 
            port=self.port, 
            debug=True,
            allow_unsafe_werkzeug=True  # Allow development mode
        )


def main():
    """Main entry point"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    server = BacktestServer(host='127.0.0.1', port=5000)
    server.run()


if __name__ == '__main__':
    main()
