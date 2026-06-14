"""
Configuration loader and validation.

This module centralizes config loading and schema validation. It maps common legacy keys
to canonical names, applies defaults, and returns typed config objects for the application.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import json
import os
import logging

try:
    from dotenv import load_dotenv
    _dotenv_available = True
except ImportError:
    _dotenv_available = False

try:
    from pydantic import BaseModel, Field, ValidationError
except Exception:
    # If pydantic is not available, provide a very small fallback validator
    BaseModel = object
    Field = lambda *a, **k: None
    ValidationError = Exception


class MT5Config(BaseModel):
    login: int
    password: str
    server: str
    timeout: int = 60000
    path: Optional[str] = None


class RiskConfig(BaseModel):
    max_position_size_pct: float = 0.02
    max_total_exposure_pct: float = 0.10
    max_daily_loss_pct: float = 0.05
    # Allow a legacy absolute dollar daily loss value to be stored by the wizard
    max_daily_loss: float = 0.0
    max_positions_per_symbol: int = 1
    max_total_positions: int = 3
    min_risk_reward_ratio: float = 1.0
    max_spread_pips: float = 50.0  # Legacy field for FX
    max_spread_points: float = 5000.0  # Absolute spread threshold in points
    max_spread_pct: float = 0.05  # Relative spread threshold as fraction of price
    volatility_scaling: bool = True
    # SL/TP adaptive knobs
    emergency_stop_loss_pct: float = 8.0  # default emergency stop when adopting external trades (percent)
    sl_balance_thresholds: Dict[str, float] = Field(default_factory=lambda: {
        "tiny": 0.01,   # <= $1k
        "small": 0.02,  # <= $5k
        "medium": 0.05, # <= $20k
        "large": 0.25   # > $20k
    })
    sl_balance_breakpoints: list = Field(default_factory=lambda: [1000.0, 5000.0, 20000.0])
    # Balance protection
    min_balance_threshold: float = 10.0  # Minimum balance to allow trading
    negative_balance_action: str = "halt"  # "halt", "close_all", "reduce"


class TradingConfig(BaseModel):
    symbol: str = "EURUSD"
    timeframe: str = "TIMEFRAME_H1"
    poll_interval: int = 60
    lookback_bars: int = 500


class StrategyConfig(BaseModel):
    type: str = "sma_crossover"
    params: Dict[str, Any] = Field(default_factory=dict)
    # Dynamic selection config (if type=='dynamic')
    dynamic_selection: Optional[Dict[str, Any]] = Field(default_factory=dict)
    # Child strategies for dynamic selection
    strategies: Optional[list] = Field(default_factory=list)


class OrphanConfig(BaseModel):
    """Configuration for orphan trade adoption."""
    enabled: bool = False
    adopt_symbols: list = Field(default_factory=list)  # Empty = all symbols
    ignore_symbols: list = Field(default_factory=list)
    apply_exit_strategies: bool = True
    max_adoption_age_hours: float = 0.0  # 0 = no limit
    log_only: bool = False  # If True, only log orphans without adopting


class AdvisoryConfig(BaseModel):
    """Configuration for advisory and ghost modes."""
    enabled: bool = False
    mode: str = 'advisory'  # 'advisory' | 'ghost' | 'production'
    ghost_lot_size: float = 0.01
    ghost_max_trades: int = 5
    ghost_max_duration: int = 3600  # seconds
    log_only: bool = False  # If True, do not actually place ghost trades; only log/record


class Config(BaseModel):
    mt5: MT5Config
    risk: RiskConfig
    trading: TradingConfig
    strategy: StrategyConfig
    providers: Dict[str, Any] = Field(default_factory=lambda: {
        'alpha_vantage_key': None,
        'binance_api_key': None,
        'binance_api_secret': None
    })
    runtime: Dict[str, Any] = Field(default_factory=lambda: {
        'dry_run': True
    })
    indicators: Optional[list] = Field(default_factory=list)
    exit_strategies: Optional[list] = Field(default_factory=list)
    orphan_trades: OrphanConfig = Field(default_factory=OrphanConfig)
    advisory: AdvisoryConfig = Field(default_factory=AdvisoryConfig)
    database: Dict[str, Any] = Field(default_factory=lambda: {"path": "cthulu.db"})
    cache_enabled: bool = True
    logging: Dict[str, Any] = Field(default_factory=dict)
    # RPC configuration (optional runtime HTTP control) with security hardening
    rpc: Dict[str, Any] = Field(default_factory=lambda: {
        "enabled": False,
        "host": "127.0.0.1",
        "port": 8080,
        "token": None,
        "security": {
            "rate_limit": {
                "requests_per_minute": 60,
                "trades_per_minute": 10,
                "burst_limit": 10,
                "adaptive_enabled": True
            },
            "ip_whitelist": ["127.0.0.1", "::1"],
            "audit_enabled": True
        }
    })
    # Dynamic SL/TP management (cutting-edge position management)
    dynamic_sltp: Dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    # Adaptive drawdown management (dynamic risk management)
    adaptive_drawdown: Dict[str, Any] = Field(default_factory=lambda: {"enabled": False})
    # Features configuration
    features: Dict[str, Any] = Field(default_factory=dict)
    # Hektor (Vector Studio) integration defaults
    hektor: Dict[str, Any] = Field(default_factory=lambda: {
        'enabled': False,
        'fallback_to_sqlite': True,
        'database_path': './vectors/cthulu_memory',
        'dimension': 512,
        'hnsw_m': 16,
        'hnsw_ef_construction': 200,
        'hnsw_ef_search': 50,
        'default_k': 10,
        'min_similarity_score': 0.7,
        'max_context_age_days': 90,
        'batch_size': 100,
        'async_writes': True,
        'cache_embeddings': True,
        'connection_timeout_ms': 5000,
        'retry_attempts': 3
    })
    # Confidence threshold for signal filtering
    confidence_threshold: float = 0.5

    @staticmethod
    def _map_legacy_keys(raw: Dict[str, Any]) -> Dict[str, Any]:
        """Map legacy or alternate key names to canonical keys used by this app.

        This helps support configs that use alternate names (e.g., 'fast_period' vs 'short_window').
        """
        # Map top-level risk keys
        r = raw.copy()
        risk = r.get('risk', {})
        if 'max_position_size' in risk:
            risk['max_position_size_pct'] = risk.pop('max_position_size')
        # Wizard historically used 'position_size_pct' as a percentage (e.g. 2.0 for 2%).
        # Normalize to the canonical 'max_position_size_pct' as a decimal (0.02).
        if 'position_size_pct' in risk and 'max_position_size_pct' not in risk:
            try:
                val = float(risk.pop('position_size_pct'))
                # If user provided percent-style value (>1), convert to decimal
                if val > 1:
                    val = val / 100.0
                risk['max_position_size_pct'] = val
            except Exception:
                # Fallback: silently ignore conversion errors and leave value as-is
                risk['max_position_size_pct'] = risk.get('position_size_pct')
        # Map risk keys that could exist in older configs
        if 'max_daily_loss' in risk and 'max_daily_loss_pct' not in risk:
            # The wizard historically stored a dollar-denominated 'max_daily_loss'.
            # Preserve the original value and do not assume it's a percent; also
            # keep a pct field if present elsewhere. Store the raw dollar value
            # under 'max_daily_loss' (new in schema) while leaving pct untouched.
            try:
                # If the value seems fractional (<1), treat it as a pct and copy
                v = float(risk.get('max_daily_loss'))
                if v <= 1.0:
                    risk['max_daily_loss_pct'] = v
                else:
                    # store raw dollar value for backwards compatibility
                    risk['max_daily_loss'] = v
            except Exception:
                risk['max_daily_loss'] = risk.get('max_daily_loss')
        r['risk'] = risk

        # Map strategy param keys
        strategy = r.get('strategy', {})
        params = strategy.get('params', {}) if isinstance(strategy, dict) else {}
        # common naming alternatives
        if 'fast_period' in params and 'short_window' not in params:
            params['short_window'] = params.pop('fast_period')
        if 'slow_period' in params and 'long_window' not in params:
            params['long_window'] = params.pop('slow_period')
        strategy['params'] = params
        r['strategy'] = strategy

        # Indicators: sometimes passed as dict; ensure list of dicts
        inds = r.get('indicators', [])
        if isinstance(inds, dict):
            # convert to list
            r['indicators'] = [ { 'type': k, 'params': v or {} } for k,v in inds.items() ]

        # Exit strategies: ensure list-of-dicts
        if isinstance(r.get('exit_strategies', []), dict):
            r['exit_strategies'] = [ { 'type': k, **v } for k, v in r['exit_strategies'].items() ]

        return r

    @classmethod
    def load(cls, path: str) -> 'Config':
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        # Load .env file if available
        env_path = p.parent / '.env'
        if env_path.exists():
            try:
                with open(env_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            if '=' in line:
                                key, value = line.split('=', 1)
                                os.environ[key.strip()] = value.strip()
            except Exception:
                pass  # Ignore errors loading .env

        text = p.read_text()
        raw = json.loads(text)
        
        # Substitute environment variables in the form ${VAR_NAME}
        def substitute_env_vars(obj):
            if isinstance(obj, dict):
                return {k: substitute_env_vars(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [substitute_env_vars(item) for item in obj]
            elif isinstance(obj, str) and obj.startswith('${') and obj.endswith('}'):
                var_name = obj[2:-1]
                env_value = os.getenv(var_name)
                if env_value is not None:
                    # Try to convert to int if it looks like a number
                    if env_value.isdigit():
                        return int(env_value)
                    return env_value
                else:
                    raise ValueError(f"Environment variable {var_name} not set")
            else:
                return obj
        
        raw = substitute_env_vars(raw)
        raw = cls._map_legacy_keys(raw)

        # Process environment variable overrides before validation
        if 'mt5' in raw:
            mt5_cfg = raw['mt5']
            # No FROM_ENV placeholders needed - env overrides below

        try:
            # Pydantic v2 uses model_validate, v1 uses parse_obj
            if hasattr(cls, 'model_validate'):
                cfg = cls.model_validate(raw)
            else:
                cfg = cls.parse_obj(raw)
        except Exception as e:
            # Try a simple validation fallback if pydantic isn't available
            # This approach will still yield a reasonable config for the app
            raise

        # Allow environment variable overrides for sensitive fields (takes priority over config values)
        mt5_login = os.getenv('MT5_LOGIN')
        mt5_password = os.getenv('MT5_PASSWORD')
        mt5_server = os.getenv('MT5_SERVER')
        if mt5_login:
            cfg.mt5.login = int(mt5_login)
        if mt5_password:
            cfg.mt5.password = mt5_password
        if mt5_server:
            cfg.mt5.server = mt5_server

        return cfg




