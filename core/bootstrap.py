"""
Bootstrap Module

Handles system initialization including:
- Configuration loading and validation
- Component initialization (connectors, managers, databases)
- Dependency injection setup
- Logging and monitoring setup

Extracted from __main__.py for better modularity and testability.
"""

import logging
import tempfile
from pathlib import Path
import os
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

from cthulu.connector.mt5_connector import MT5Connector, ConnectionConfig
from cthulu.data.layer import DataLayer
from cthulu.risk.evaluator import RiskEvaluator, RiskLimits
from cthulu.execution.engine import ExecutionEngine
from cthulu.position.tracker import PositionTracker
from cthulu.position.lifecycle import PositionLifecycle
from cthulu.position.adoption import TradeAdoptionManager, TradeAdoptionPolicy
from cthulu.persistence.database import Database
from cthulu.observability.metrics import MetricsCollector
from config_schema import Config
from config.mindsets import apply_mindset


@dataclass
class SystemComponents:
    """Container for all initialized system components."""
    
    # Core components
    config: Dict[str, Any]
    connector: MT5Connector
    data_layer: DataLayer
    risk_manager: RiskEvaluator
    execution_engine: ExecutionEngine
    position_tracker: PositionTracker
    position_manager: Optional[Any]
    position_lifecycle: PositionLifecycle
    trade_adoption_manager: TradeAdoptionManager
    exit_coordinator: PositionLifecycle
    database: Database
    metrics: MetricsCollector
    
    # Strategy and indicators (loaded separately)
    strategy: Any = None
    indicators: list = None
    exit_strategies: list = None
    trade_adoption_policy: Optional[Any] = None
    
    # Optional components
    ml_collector: Any = None
    advisory_manager: Any = None
    monitor: Any = None
    exporter: Any = None
    
    # Dynamic SL/TP and Adaptive Drawdown (cutting-edge risk management)
    dynamic_sltp_manager: Any = None
    adaptive_drawdown_manager: Any = None
    profit_scaler: Any = None  # Profit scaling for partial profit taking
    
    # In-process observability collectors
    indicator_collector: Any = None
    system_health_collector: Any = None
    comprehensive_collector: Any = None
    
    # Hektor (Vector Studio) integration
    hektor_adapter: Any = None
    hektor_retriever: Any = None
    
    # ML Enhancement Manager (auto-initialized with trading loop)
    ml_enhancement_manager: Any = None


class CthuluBootstrap:
    """Handles Cthulu system initialization."""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize bootstrap handler.
        
        Args:
            logger: Logger instance (will be created if not provided)
        """
        self.logger = logger or logging.getLogger(__name__)
        self.components = None
    
    def load_configuration(self, config_path: str, mindset: Optional[str] = None,
                          symbol_override: Optional[str] = None) -> Dict[str, Any]:
        """Load and validate configuration.
        
        Args:
            config_path: Path to configuration file
            mindset: Optional mindset to apply (aggressive, balanced, conservative, ultra_aggressive)
            symbol_override: Optional symbol to override configuration
            
        Returns:
            Validated configuration dictionary
            
        Raises:
            Exception: If configuration loading or validation fails
        """
        try:
            cfg = Config.load(config_path)
            self.logger.info(f"Configuration loaded from {config_path}")
            
            # Convert to dict (Pydantic v2 compatibility)
            config = cfg.model_dump() if hasattr(cfg, 'model_dump') else cfg.dict()
            
            # Apply mindset if specified
            if mindset:
                config = apply_mindset(config, mindset)
                self.logger.info(f"Applied '{mindset}' trading mindset")
                self.logger.info(
                    f"  Risk: position_size_pct={config['risk'].get('position_size_pct', 2.0)}%, "
                    f"max_daily_loss=${config['risk'].get('max_daily_loss', 50)}"
                )
            
            # Symbol override from CLI
            if symbol_override:
                config['trading']['symbol'] = symbol_override
                self.logger.info(f"Overriding trading symbol: {symbol_override}")
            
            return config
            
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            raise
    
    def initialize_connector(self, config: Dict[str, Any]) -> MT5Connector:
        """Initialize MT5 connector.
        
        Args:
            config: System configuration
            
        Returns:
            Initialized MT5Connector instance
        """
        self.logger.info("Initializing MT5 connector...")
        connection_config = ConnectionConfig(**config['mt5'])
        connector = MT5Connector(connection_config)
        return connector
    
    def initialize_data_layer(self, config: Dict[str, Any]) -> DataLayer:
        """Initialize data layer.
        
        Args:
            config: System configuration
            
        Returns:
            Initialized DataLayer instance
        """
        self.logger.info("Initializing data layer...")
        cache_enabled = config.get('cache_enabled', True)
        data_layer = DataLayer(cache_enabled=cache_enabled)
        return data_layer
    
    def initialize_risk_manager(self, config: Dict[str, Any]) -> RiskEvaluator:
        """Initialize risk evaluator.
        
        Args:
            config: System configuration
            
        Returns:
            RiskLimits configuration object
        """
        self.logger.info("Initializing risk evaluator...")
        risk_config = config.get('risk', {})
        
        # Log the min_balance_threshold being used
        min_bal = risk_config.get('min_balance_threshold', 10.0)
        self.logger.info(f"Risk config min_balance_threshold: {min_bal}")
        
        # Build RiskLimits with defaults
        risk_limits = RiskLimits(
            max_position_size_percent=risk_config.get('max_position_size_percent', 2.0),
            max_total_exposure_percent=risk_config.get('max_total_exposure_percent', 10.0),
            max_daily_loss=risk_config.get('max_daily_loss', 500.0),
            max_positions_per_symbol=risk_config.get('max_positions_per_symbol', 3),
            min_risk_reward_ratio=risk_config.get('min_risk_reward_ratio', 1.5),
            max_spread_points=risk_config.get('max_spread_points', 5000.0),
            max_spread_pct=risk_config.get('max_spread_pct', 0.05),
            min_confidence=risk_config.get('min_confidence', 0.0),
            emergency_shutdown_enabled=risk_config.get('emergency_shutdown_enabled', True),
            min_balance_threshold=risk_config.get('min_balance_threshold', 10.0),
            negative_balance_action=risk_config.get('negative_balance_action', 'halt')
        )
        
        return risk_limits
    
    def initialize_execution_engine(self, connector: MT5Connector, config: Dict[str, Any],
                                   ml_collector: Any = None) -> ExecutionEngine:
        """Initialize execution engine.
        
        Args:
            connector: MT5 connector instance
            config: System configuration
            ml_collector: Optional ML data collector
            
        Returns:
            Initialized ExecutionEngine instance
        """
        self.logger.info("Initializing execution engine...")
        risk_config = config.get('risk', {})
        execution_engine = ExecutionEngine(
            connector,
            risk_config=risk_config,
            ml_collector=ml_collector
        )
        return execution_engine
    
    def initialize_position_tracker(self, connector: MT5Connector) -> PositionTracker:
        """Initialize position tracker.
        
        Args:
            connector: MT5 connector instance
            
        Returns:
            Initialized PositionTracker instance
        """
        self.logger.info("Initializing position tracker...")
        position_tracker = PositionTracker()
        return position_tracker

    def initialize_position_manager(self, connector: MT5Connector, execution_engine: ExecutionEngine, context_symbol: str = None) -> 'PositionManager':
        """Initialize a lightweight PositionManager for higher-level monitoring.
        
        This manager is separate from the low-level PositionTracker and provides
        additional monitoring and convenience APIs used by the trading loop.
        
        Args:
            connector: MT5 connector instance
            execution_engine: Execution engine instance
            context_symbol: Symbol being traded (used as fallback for UNKNOWN symbols)
        """
        try:
            from cthulu.position.manager import PositionManager
            self.logger.info("Initializing position manager...")
            pm = PositionManager(connector=connector, execution_engine=execution_engine, context_symbol=context_symbol)
            self.logger.info('PositionManager initialized')
            return pm
        except Exception as e:
            self.logger.exception('PositionManager initialization failed; continuing without it')
            return None

    def initialize_strategy(self, config: Dict[str, Any]) -> Optional[Any]:
        """Initialize trading strategy from configuration."""
        self.logger.info("Initializing strategy...")
        try:
            from core.strategy_factory import load_strategy
            strat_cfg = config.get('strategy', {}) if isinstance(config, dict) else {}
            
            # Ensure trading symbol is available to strategy for signal generation
            trading_symbol = config.get('trading', {}).get('symbol')
            if trading_symbol:
                # Inject symbol into strategy params
                if 'params' not in strat_cfg:
                    strat_cfg['params'] = {}
                if 'symbol' not in strat_cfg['params']:
                    strat_cfg['params']['symbol'] = trading_symbol
            
            strategy = load_strategy(strat_cfg)
            self.logger.info(f"Strategy initialized: {strategy.__class__.__name__}")
            return strategy
        except Exception as e:
            self.logger.exception(f"Failed to initialize strategy: {e}")
            return None
    
    def initialize_position_lifecycle(self, connector: MT5Connector,
                                      execution_engine: ExecutionEngine,
                                      position_tracker: PositionTracker,
                                      database: Database) -> PositionLifecycle:
        """Initialize position lifecycle manager.
        
        Args:
            connector: MT5 connector instance
            execution_engine: Execution engine instance
            position_tracker: PositionTracker instance
            database: Database instance
            
        Returns:
            Initialized PositionLifecycle instance
        """
        self.logger.info("Initializing position lifecycle...")
        position_lifecycle = PositionLifecycle(connector, execution_engine, position_tracker, database)
        return position_lifecycle
    
    def initialize_trade_adoption_manager(self, connector: MT5Connector, position_tracker: PositionTracker,
                                          position_lifecycle: PositionLifecycle,
                                          config: Dict[str, Any]) -> TradeAdoptionManager:
        """Initialize trade adoption manager for external trade adoption.
        
        Args:
            position_tracker: Position tracker instance
            position_lifecycle: Position lifecycle instance
            config: System configuration
            
        Returns:
            Initialized TradeAdoptionManager instance
        """
        trade_adoption_config = config.get('orphan_trades', {})
        trade_adoption_policy = TradeAdoptionPolicy(
            enabled=trade_adoption_config.get('enabled', False),
            allowed_symbols=trade_adoption_config.get('adopt_symbols') or None,
            blocked_symbols=trade_adoption_config.get('ignore_symbols', []),
            max_age_hours=trade_adoption_config.get('max_adoption_age_hours'),
            min_age_seconds=trade_adoption_config.get('min_age_seconds', 60),
            min_volume=trade_adoption_config.get('min_volume'),
            max_volume=trade_adoption_config.get('max_volume'),
            excluded_magic_numbers=set(trade_adoption_config.get('excluded_magic_numbers', [])),
            apply_emergency_sl=trade_adoption_config.get('apply_emergency_sl', True),
            emergency_sl_points=trade_adoption_config.get('emergency_sl_points', 100),
            apply_emergency_tp=trade_adoption_config.get('apply_emergency_tp', False),
            emergency_tp_points=trade_adoption_config.get('emergency_tp_points', 100),
            log_only=trade_adoption_config.get('log_only', False)
        )
        
        trade_adoption_manager = TradeAdoptionManager(
            connector,
            position_tracker,
            position_lifecycle,
            trade_adoption_policy
        )
        
        if trade_adoption_policy.enabled:
            self.logger.info(
                f"External trade adoption ENABLED (log_only: {trade_adoption_policy.log_only})"
            )
        else:
            self.logger.info("External trade adoption disabled")
        
        return trade_adoption_manager
    
    def initialize_database(self, config: Dict[str, Any]) -> Database:
        """Initialize database.
        
        Args:
            config: System configuration
            
        Returns:
            Initialized Database instance
        """
        self.logger.info("Initializing database...")
        db_path = config.get('database', {}).get('path', 'cthulu.db')
        database = Database(db_path)
        # Fail fast if the database is not writable: deployment must ensure ACLs
        try:
            database.check_writable()
        except PermissionError as e:
            self.logger.error(
                "Database path '%s' is not writable. Ensure file permissions and ACLs are correct. %s",
                db_path, e
            )
            raise
        return database
    
    def initialize_metrics(self, database: Database) -> MetricsCollector:
        """Initialize metrics collector.
        
        Args:
            database: Database instance
            
        Returns:
            Initialized MetricsCollector instance
        """
        self.logger.info("Initializing metrics collector...")
        metrics = MetricsCollector(database=database)
        return metrics
    
    def initialize_ml_collector(self, config: Dict[str, Any], args: Any) -> Optional[Any]:
        """Initialize ML data collector (optional).
        
        Args:
            config: System configuration
            args: Command-line arguments
            
        Returns:
            MLDataCollector instance or None if disabled
        """
        ml_collector = None
        try:
            ml_config = config.get('ml', {}) if isinstance(config, dict) else {}
            ml_enabled = ml_config.get('enabled', True)
            
            # CLI overrides config when provided
            if hasattr(args, 'enable_ml') and args.enable_ml is not None:
                ml_enabled = args.enable_ml
            
            if ml_enabled:
                from cthulu.ML_RL.instrumentation import MLDataCollector
                ml_prefix = ml_config.get('prefix', 'events')
                ml_collector = MLDataCollector(prefix=ml_prefix)
                self.logger.info('MLDataCollector initialized')
            else:
                self.logger.info('ML instrumentation disabled via config/CLI')
        except Exception:
            self.logger.exception('Failed to initialize MLDataCollector; continuing without it')
        
        return ml_collector
    
    def initialize_advisory_manager(self, config: Dict[str, Any],
                                    execution_engine: ExecutionEngine,
                                    ml_collector: Any) -> Optional[Any]:
        """Initialize advisory manager (optional).
        
        Args:
            config: System configuration
            execution_engine: Execution engine instance
            ml_collector: ML data collector instance
            
        Returns:
            AdvisoryManager instance or None if disabled
        """
        advisory_manager = None
        try:
            from cthulu.advisory.manager import AdvisoryManager
            advisory_cfg = config.get('advisory', {}) if isinstance(config, dict) else {}
            advisory_manager = AdvisoryManager(advisory_cfg, execution_engine, ml_collector)
            if advisory_manager.enabled:
                self.logger.info(f"AdvisoryManager enabled (mode={advisory_manager.mode})")
        except Exception:
            self.logger.exception('Failed to initialize AdvisoryManager; continuing without it')
        
        return advisory_manager
    
    def initialize_prometheus_exporter(self, config: Dict[str, Any]) -> Optional[Any]:
        """Initialize Prometheus exporter (optional).
        
        Args:
            config: System configuration
            
        Returns:
            PrometheusExporter instance or None if disabled
        """
        exporter = None
        try:
            prom_cfg = config.get('observability', {}).get('prometheus', {})
            try:
                from cthulu.observability.prometheus import PrometheusExporter
                exporter = PrometheusExporter(prefix=prom_cfg.get('prefix', 'Cthulu'))
                # configure textfile path if provided
                textfile_path = prom_cfg.get('textfile_path')
                if textfile_path:
                    exporter._file_path = textfile_path
                else:
                    # Use platform-appropriate default paths
                    if os.name == 'nt':
                        # Windows: Use user's temp directory
                        temp_dir = tempfile.gettempdir()
                        exporter._file_path = os.path.join(temp_dir, "cthulu_metrics", "Cthulu_metrics.prom")
                    else:
                        # Unix/Linux: Prefer XDG_RUNTIME_DIR, fall back to /tmp
                        runtime_dir = os.getenv('XDG_RUNTIME_DIR')
                        if runtime_dir and os.path.exists(runtime_dir):
                            exporter._file_path = os.path.join(runtime_dir, "cthulu", "metrics", "Cthulu_metrics.prom")
                        else:
                            exporter._file_path = "/tmp/cthulu_metrics/Cthulu_metrics.prom"
                    
                    # Ensure directory exists
                    try:
                        os.makedirs(os.path.dirname(exporter._file_path), exist_ok=True)
                    except Exception as e:
                        logger.warning(f"Failed to create metrics directory: {e}")
                # Start a simple HTTP metrics server if requested or default to 8181
                http_port = prom_cfg.get('http_port', 8181)
                try:
                    import threading
                    from http.server import BaseHTTPRequestHandler, HTTPServer
                    class _MetricsHandler(BaseHTTPRequestHandler):
                        def do_GET(self):
                            if self.path != '/metrics':
                                self.send_response(404)
                                self.end_headers()
                                return
                            try:
                                body = exporter.export_text().encode('utf-8')
                                self.send_response(200)
                                self.send_header('Content-Type', 'text/plain; version=0.0.4')
                                self.send_header('Content-Length', str(len(body)))
                                self.end_headers()
                                self.wfile.write(body)
                            except Exception:
                                self.send_response(500)
                                self.end_headers()
                    def _serve():
                        server = HTTPServer(('0.0.0.0', int(http_port)), _MetricsHandler)
                        exporter.logger.info(f"Starting metrics HTTP server on port {http_port}")
                        try:
                            server.serve_forever()
                        except Exception:
                            exporter.logger.exception('Metrics HTTP server stopped')
                    t = threading.Thread(target=_serve, daemon=True)
                    t.start()
                except Exception:
                    self.logger.exception('Failed to start HTTP metrics server')
                self.logger.info('Prometheus exporter initialized')
            except Exception:
                self.logger.exception('Failed to initialize Prometheus exporter')
        except Exception:
            self.logger.exception('Failed to initialize Prometheus exporter; continuing without it')
        
        return exporter
    
    def initialize_trade_monitor(self, position_tracker: PositionTracker,
                                 position_lifecycle: PositionLifecycle,
                                 trade_adoption_manager: TradeAdoptionManager,
                                 config: Dict[str, Any],
                                 ml_collector: Any) -> Optional[Any]:
        """Initialize trade monitor (optional).
        
        Args:
            position_tracker: Position tracker instance
            position_lifecycle: Position lifecycle instance
            trade_adoption_manager: Trade adoption manager instance
            config: System configuration
            ml_collector: ML data collector instance
            
        Returns:
            TradeMonitor instance or None if initialization fails
        """
        monitor = None
        try:
            from cthulu.monitoring.trade_monitor import TradeMonitor
            poll_interval = config.get('monitor_poll_interval', 5.0)
            monitor = TradeMonitor(
                position_tracker,
                position_lifecycle,
                poll_interval=poll_interval,
                ml_collector=ml_collector
            )
            monitor.start()
            self.logger.info(f"TradeMonitor started (poll_interval={poll_interval}s)")
        except Exception:
            self.logger.exception('Failed to start TradeMonitor; continuing without it')
        
        return monitor
    
    def initialize_dynamic_sltp_manager(self, config: Dict[str, Any]) -> Optional[Any]:
        """Initialize dynamic SL/TP manager for cutting-edge position management.
        
        Args:
            config: System configuration
            
        Returns:
            DynamicSLTPManager instance or None if disabled
        """
        try:
            sltp_config = config.get('dynamic_sltp', {})
            if not sltp_config.get('enabled', False):
                self.logger.info("Dynamic SL/TP management disabled")
                return None
            
            from cthulu.risk.dynamic_sltp import DynamicSLTPManager
            manager = DynamicSLTPManager(sltp_config)
            self.logger.info(
                f"DynamicSLTPManager initialized: "
                f"base_sl_atr={sltp_config.get('base_sl_atr_mult', 2.0)}, "
                f"base_tp_atr={sltp_config.get('base_tp_atr_mult', 4.0)}"
            )
            return manager
        except Exception:
            self.logger.exception("Failed to initialize DynamicSLTPManager")
            return None
    
    def initialize_adaptive_drawdown_manager(self, config: Dict[str, Any]) -> Optional[Any]:
        """Initialize adaptive drawdown manager for dynamic risk management.
        
        Args:
            config: System configuration
            
        Returns:
            AdaptiveDrawdownManager instance or None if disabled
        """
        try:
            dd_config = config.get('adaptive_drawdown', {})
            if not dd_config.get('enabled', False):
                self.logger.info("Adaptive drawdown management disabled")
                return None
            
            from cthulu.risk.adaptive_drawdown import AdaptiveDrawdownManager
            manager = AdaptiveDrawdownManager(dd_config)
            self.logger.info(
                f"AdaptiveDrawdownManager initialized: "
                f"trailing_lock={dd_config.get('trailing_lock_pct', 0.5)}, "
                f"survival_threshold={dd_config.get('survival_threshold_pct', 50.0)}%"
            )
            return manager
        except Exception:
            self.logger.exception("Failed to initialize AdaptiveDrawdownManager")
            return None
    
    def initialize_profit_scaler(self, config: Dict[str, Any], connector, execution_engine) -> Optional[Any]:
        """Initialize profit scaler for partial profit taking.
        
        Args:
            config: System configuration
            connector: MT5Connector instance
            execution_engine: ExecutionEngine instance
            
        Returns:
            ProfitScaler instance or None if disabled
        """
        try:
            scaler_config = config.get('profit_scaling', {})
            if not scaler_config.get('enabled', True):  # Enabled by default
                self.logger.info("Profit scaling disabled")
                return None
            
            from cthulu.position.profit_scaler import create_profit_scaler
            scaler = create_profit_scaler(connector, execution_engine, scaler_config)
            self.logger.info(
                f"ProfitScaler initialized: "
                f"micro_threshold=${scaler_config.get('micro_account_threshold', 100)}, "
                f"emergency_lock={scaler_config.get('emergency_lock_threshold_pct', 0.10)*100}%"
            )
            return scaler
        except Exception:
            self.logger.exception("Failed to initialize ProfitScaler")
            return None
    
    def initialize_hektor(self, config: Dict[str, Any]) -> Tuple[Any, Any]:
        """Initialize Hektor (Vector Studio) integration.
        
        Args:
            config: System configuration
            
        Returns:
            Tuple of (VectorStudioAdapter, ContextRetriever) or (None, None) if disabled
        """
        adapter = None
        retriever = None
        
        try:
            hektor_config = config.get('hektor', {})
            if not hektor_config.get('enabled', False):
                self.logger.info("Hektor (Vector Studio) integration disabled")
                return None, None
            
            from integrations.vector_studio import VectorStudioAdapter, VectorStudioConfig
            from integrations.retriever import ContextRetriever
            from integrations.embedder import TradeEmbedder
            
            # Build config from settings
            vs_config = VectorStudioConfig(
                enabled=hektor_config.get('enabled', True),
                database_path=hektor_config.get('database_path', './vectors/cthulu_memory'),
                dimension=hektor_config.get('dimension', 512),
                hnsw_m=hektor_config.get('hnsw_m', 16),
                hnsw_ef_construction=hektor_config.get('hnsw_ef_construction', 200),
                hnsw_ef_search=hektor_config.get('hnsw_ef_search', 50),
                default_k=hektor_config.get('default_k', 10),
                min_similarity_score=hektor_config.get('min_similarity_score', 0.7),
                max_context_age_days=hektor_config.get('max_context_age_days', 90),
                batch_size=hektor_config.get('batch_size', 100),
                async_writes=hektor_config.get('async_writes', True),
                cache_embeddings=hektor_config.get('cache_embeddings', True),
                connection_timeout_ms=hektor_config.get('connection_timeout_ms', 5000),
                retry_attempts=hektor_config.get('retry_attempts', 3),
                fallback_on_failure=hektor_config.get('fallback_to_sqlite', True)
            )
            
            adapter = VectorStudioAdapter(vs_config)
            connected = adapter.connect()
            
            if connected:
                if adapter.is_using_fallback():
                    self.logger.info("Hektor connected (using SQLite fallback)")
                else:
                    self.logger.info("Hektor connected to Vector Studio")
                
                # Initialize retriever
                embedder = TradeEmbedder()
                retriever = ContextRetriever(adapter, embedder)
                self.logger.info("Hektor retriever initialized")
            else:
                self.logger.warning("Hektor connection failed; semantic memory unavailable")
                adapter = None
            
            return adapter, retriever
            
        except ImportError as e:
            self.logger.warning(f"Hektor integration unavailable (missing module): {e}")
            return None, None
        except Exception:
            self.logger.exception("Failed to initialize Hektor integration")
            return None, None
    
    def initialize_exit_strategies(self, config: Dict[str, Any]) -> list:
        """Initialize exit strategies from configuration.
        
        Args:
            config: System configuration
            
        Returns:
            List of exit strategy instances
        """
        try:
            exit_configs = config.get('exit_strategies', [])
            if not exit_configs:
                self.logger.info("No exit strategies configured")
                return []
            
            from cthulu.core.exit_loader import load_exit_strategies
            exit_strategies = load_exit_strategies(exit_configs)
            self.logger.info(f"Loaded {len(exit_strategies)} exit strategies")
            return exit_strategies
        except Exception:
            self.logger.exception("Failed to initialize exit strategies")
            return []
    
    def bootstrap(self, config_path: str, args: Any) -> SystemComponents:
        """Bootstrap the entire Cthulu system.
        
        Args:
            config_path: Path to configuration file
            args: Command-line arguments
            
        Returns:
            SystemComponents with all initialized components
            
        Raises:
            Exception: If critical initialization fails
        """
        # Load configuration
        config = self.load_configuration(
            config_path,
            mindset=getattr(args, 'mindset', None),
            symbol_override=getattr(args, 'symbol', None)
        )
        
        # Initialize core components
        connector = self.initialize_connector(config)
        data_layer = self.initialize_data_layer(config)
        # Compute risk limits configuration (create RiskEvaluator later when position tracker is available)
        risk_limits = self.initialize_risk_manager(config)
        
        # Initialize ML collector before execution engine
        ml_collector = self.initialize_ml_collector(config, args)
        
        # Initialize execution components
        execution_engine = self.initialize_execution_engine(connector, config, ml_collector)
        
        # Initialize persistence first (needed by lifecycle)
        database = self.initialize_database(config)
        # Wire telemetry helper to execution engine so provenance is persisted
        try:
            from cthulu.observability.telemetry import Telemetry
            telemetry = Telemetry(database)
            execution_engine.telemetry = telemetry
        except Exception:
            telemetry = None
            self.logger.debug('Telemetry helper unavailable; provenance will still be logged to file')
        
        # Initialize position management components
        position_tracker = self.initialize_position_tracker(connector)
        # Get trading symbol from config for position manager fallback
        trading_symbol = config.get('trading', {}).get('symbol', None)
        # Initialize higher-level position manager used by trading loop monitoring
        position_manager = self.initialize_position_manager(connector, execution_engine, context_symbol=trading_symbol)
        # Now we can construct the risk evaluator with the connector and position tracker
        risk_manager = RiskEvaluator(connector, position_tracker, limits=risk_limits)
        self.logger.info('RiskEvaluator initialized with runtime dependencies')
        
        position_lifecycle = self.initialize_position_lifecycle(connector, execution_engine, position_tracker, database)
        trade_adoption_manager = self.initialize_trade_adoption_manager(connector, position_tracker, position_lifecycle, config)
        
        # Initialize strategy
        strategy = self.initialize_strategy(config)
        
        # Initialize metrics
        metrics = self.initialize_metrics(database)
        
        # Attach metrics to execution engine
        try:
            execution_engine.metrics = metrics
        except Exception:
            self.logger.debug('Failed to attach metrics to execution engine')        
        # Initialize optional components
        advisory_manager = self.initialize_advisory_manager(config, execution_engine, ml_collector)
        exporter = self.initialize_prometheus_exporter(config)
        monitor = self.initialize_trade_monitor(position_tracker, position_lifecycle, trade_adoption_manager, config, ml_collector)
        
        # Initialize cutting-edge risk management components
        dynamic_sltp_manager = self.initialize_dynamic_sltp_manager(config)
        adaptive_drawdown_manager = self.initialize_adaptive_drawdown_manager(config)
        profit_scaler = self.initialize_profit_scaler(config, connector, execution_engine)
        
        # Initialize Hektor (Vector Studio) semantic memory integration
        hektor_adapter, hektor_retriever = self.initialize_hektor(config)
        
        # Initialize exit strategies
        exit_strategies = self.initialize_exit_strategies(config)
        
        # ==========================================================
        # INITIALIZE ML ENHANCEMENT MANAGER (Auto-ML Integration)
        # This ensures ML enhancements are ALWAYS active with trading
        # ==========================================================
        ml_enhancement_manager = None
        try:
            ml_config = config.get('ml', {}) if isinstance(config, dict) else {}
            ml_enabled = ml_config.get('enabled', True)  # ML enabled by default
            
            if ml_enabled:
                from core.ml_enhancement import initialize_ml_enhancements
                ml_enhancement_manager = initialize_ml_enhancements(
                    config=config,
                    hektor_adapter=hektor_adapter,
                    hektor_retriever=hektor_retriever
                )
                self.logger.info(f"ML Enhancement Manager initialized: {ml_enhancement_manager.get_state()['components']}")
            else:
                self.logger.info("ML Enhancement Manager disabled via config (ml.enabled=false)")
        except Exception as e:
            self.logger.warning(f"Failed to initialize ML Enhancement Manager: {e}")
            self.logger.info("Continuing without ML enhancements - system will operate with rule-based logic only")
        
        # Create components container
        components = SystemComponents(
            config=config,
            connector=connector,
            data_layer=data_layer,
            risk_manager=risk_manager,
            execution_engine=execution_engine,
            position_tracker=position_tracker,
            position_manager=position_manager,
            position_lifecycle=position_lifecycle,
            trade_adoption_manager=trade_adoption_manager,
            exit_coordinator=position_lifecycle,
            database=database,
            metrics=metrics,
            ml_collector=ml_collector,
            advisory_manager=advisory_manager,
            monitor=monitor,
            exporter=exporter,
            strategy=strategy,
            dynamic_sltp_manager=dynamic_sltp_manager,
            adaptive_drawdown_manager=adaptive_drawdown_manager,
            profit_scaler=profit_scaler,
            exit_strategies=exit_strategies,
            hektor_adapter=hektor_adapter,
            hektor_retriever=hektor_retriever,
            ml_enhancement_manager=ml_enhancement_manager
        )
        # Expose trade_adoption_policy for convenience
        try:
            components.trade_adoption_policy = trade_adoption_manager.policy
        except Exception:
            components.trade_adoption_policy = None
        
        # Start RPC server if configured (allows runtime manual trades via HTTP)
        try:
            rpc_cfg = config.get('rpc', {}) if isinstance(config, dict) else {}
            if rpc_cfg.get('enabled', False):
                try:
                    from cthulu.rpc.server import run_rpc_server
                    host = rpc_cfg.get('host', '127.0.0.1')
                    port = int(rpc_cfg.get('port', 8278))
                    token = rpc_cfg.get('token', None)
                    t, server = run_rpc_server(host, port, token, execution_engine, risk_manager, position_manager, database)
                    components.rpc_server = server
                    components.rpc_thread = t
                    self.logger.info(f"RPC server started on http://{host}:{port}")
                except Exception:
                    self.logger.exception('Failed to start RPC server; continuing without it')
        except Exception:
            self.logger.debug('RPC configuration parsing failed; skipping RPC startup')

        # Start observability suite (decoupled monitoring/metrics collection)
        try:
            obs_cfg = config.get('observability', {}) if isinstance(config, dict) else {}
            # By default, start observability unless explicitly disabled
            if obs_cfg.get('enabled', True):
                try:
                    # NOTE: We use IN-PROCESS collectors instead of separate processes
                    # This allows the trading loop to feed real-time data to the collectors
                    
                    # Create in-process comprehensive collector for real-time trading data
                    try:
                        from observability.comprehensive_collector import ComprehensiveMetricsCollector
                        comprehensive_collector = ComprehensiveMetricsCollector(
                            update_interval=1.0,
                            enable_prometheus=obs_cfg.get('prometheus', {}).get('enabled', False)
                        )
                        comprehensive_collector.start()
                        components.comprehensive_collector = comprehensive_collector
                        self.logger.info(f"In-process comprehensive collector started for real-time data (obj={comprehensive_collector is not None})")
                    except Exception as e:
                        self.logger.warning(f"Failed to start in-process comprehensive collector: {e}")
                    
                    # Create in-process indicator collector for real-time data feeding
                    try:
                        from monitoring.indicator_collector import IndicatorMetricsCollector
                        indicator_collector = IndicatorMetricsCollector(update_interval=1.0)
                        indicator_collector.start()
                        components.indicator_collector = indicator_collector
                        self.logger.info("In-process indicator collector started for real-time data")
                    except Exception as e:
                        self.logger.warning(f"Failed to start in-process indicator collector: {e}")
                    
                    # Create in-process system health collector for real-time data feeding
                    try:
                        from monitoring.system_health_collector import SystemHealthCollector
                        system_health_collector = SystemHealthCollector(update_interval=5.0)
                        system_health_collector.start()
                        components.system_health_collector = system_health_collector
                        self.logger.info("In-process system health collector started for real-time data")
                    except Exception as e:
                        self.logger.warning(f"Failed to start in-process system health collector: {e}")
                    
                    # ==========================================================
                    # INITIALIZE TRADE EVENT BUS (Non-blocking metrics collection)
                    # ==========================================================
                    try:
                        from observability.trade_event_bus import initialize_event_bus
                        
                        # Get training logger if ML is enabled
                        training_logger = None
                        try:
                            if config.get('ml', {}).get('training_data', {}).get('enabled', False):
                                from cognition.training_logger import get_training_logger
                                training_logger = get_training_logger()
                        except Exception:
                            pass
                        
                        event_bus = initialize_event_bus(
                            metrics_collector=metrics,
                            comprehensive_collector=components.comprehensive_collector,
                            training_logger=training_logger,
                            database=database,
                            ml_collector=ml_collector
                        )
                        self.logger.info(f"Trade Event Bus initialized: {event_bus.get_stats()['subscribers']}")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize Trade Event Bus: {e}")
                    
                    # ==========================================================
                    # INITIALIZE DISCORD NOTIFIER (Non-blocking alerts)
                    # ==========================================================
                    try:
                        discord_cfg = config.get('discord', {}) if isinstance(config, dict) else {}
                        if discord_cfg.get('enabled', True):  # Enabled by default if webhooks exist
                            from integrations.discord_notifier import initialize_discord_notifier
                            import os
                            
                            discord_notifier = initialize_discord_notifier(
                                alerts_webhook=discord_cfg.get('webhook_alerts') or os.getenv('DISCORD_WEBHOOK_ALERTS', ''),
                                health_webhook=discord_cfg.get('webhook_health') or os.getenv('DISCORD_WEBHOOK_HEALTH', ''),
                                signals_webhook=discord_cfg.get('webhook_signals') or os.getenv('DISCORD_WEBHOOK_SIGNALS', ''),
                                config={
                                    'notify_trades': discord_cfg.get('notify_trades', True),
                                    'notify_adoptions': discord_cfg.get('notify_adoptions', True),
                                    'notify_risk': discord_cfg.get('notify_risk', True),
                                    'min_pnl_notify': discord_cfg.get('min_pnl_notify', 0)
                                }
                            )
                            if discord_notifier.enabled:
                                self.logger.info("Discord notifier initialized and connected to event bus")
                            else:
                                self.logger.info("Discord notifier disabled (no webhooks configured)")
                    except Exception as e:
                        self.logger.warning(f"Failed to initialize Discord notifier: {e}")
                        
                except Exception as e:
                    self.logger.warning(f'Failed to start observability suite: {e}')
                    self.logger.info('Continuing without observability suite')
            else:
                self.logger.info('Observability suite disabled via config')
        except Exception:
            self.logger.debug('Observability configuration parsing failed; skipping observability startup')

        self.components = components
        self.logger.info("System bootstrap complete")
        
        return components


def bootstrap_system(config_path: str, args: Any, logger: logging.Logger) -> SystemComponents:
    """Convenience function for bootstrapping the system.
    
    Args:
        config_path: Path to configuration file
        args: Command-line arguments
        logger: Logger instance
        
    Returns:
        SystemComponents with all initialized components
    """
    bootstrapper = CthuluBootstrap(logger=logger)
    return bootstrapper.bootstrap(config_path, args)





