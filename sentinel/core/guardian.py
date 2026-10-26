"""
SENTINEL GUARDIAN - Core Watchdog System
=========================================
Independent process that monitors Cthulu and MT5 for:
- Crashes and automatic recovery
- Disconnections and reconnection attempts
- Algo trading state monitoring and auto-re-enable
- System health metrics collection
- Emergency shutdown protocols

This runs OUTSIDE of Cthulu to ensure it survives any Cthulu crash.
SENTINEL IS NOT PART OF CTHULU - IT IS A COMPLETELY SEPARATE SYSTEM.
"""

import os
import sys
import time
import json
import signal
import logging
import subprocess
import threading
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Dict, Any, List, Callable
import psutil

# Configure logging
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Configure file handler with UTF-8 encoding
file_handler = logging.FileHandler(
    LOG_DIR / f"sentinel_{datetime.now().strftime('%Y%m%d')}.log",
    encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter("%(asctime)s [SENTINEL] %(levelname)s: %(message)s"))

# Configure stream handler with UTF-8 encoding for Windows
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(logging.Formatter("%(asctime)s [SENTINEL] %(levelname)s: %(message)s"))

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, stream_handler]
)
logger = logging.getLogger("SENTINEL")


class SystemState(Enum):
    """Overall system state"""
    HEALTHY = auto()
    DEGRADED = auto()
    CRITICAL = auto()
    RECOVERING = auto()
    OFFLINE = auto()


class CthhuluState(Enum):
    """Cthulu process state"""
    RUNNING = auto()
    STARTING = auto()
    STOPPED = auto()
    CRASHED = auto()
    UNRESPONSIVE = auto()


class MT5State(Enum):
    """MetaTrader 5 state"""
    CONNECTED = auto()
    DISCONNECTED = auto()
    ALGO_ENABLED = auto()
    ALGO_DISABLED = auto()
    NOT_RUNNING = auto()


@dataclass
class HealthMetrics:
    """System health snapshot"""
    timestamp: datetime = field(default_factory=datetime.now)
    cthulu_state: CthhuluState = CthhuluState.STOPPED
    mt5_state: MT5State = MT5State.NOT_RUNNING
    system_state: SystemState = SystemState.OFFLINE
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    cthulu_pid: Optional[int] = None
    mt5_pid: Optional[int] = None
    uptime_seconds: float = 0.0
    crash_count: int = 0
    last_crash: Optional[datetime] = None
    recovery_attempts: int = 0
    last_heartbeat: Optional[datetime] = None
    error_log: List[str] = field(default_factory=list)


@dataclass
class RecoveryConfig:
    """Recovery behavior configuration"""
    max_crash_recovery_attempts: int = 5
    recovery_cooldown_seconds: int = 30
    heartbeat_timeout_seconds: int = 120
    auto_restart_cthulu: bool = True
    auto_enable_algo: bool = True
    emergency_stop_on_repeated_crashes: bool = True
    crash_threshold_for_emergency: int = 5
    crash_window_minutes: int = 10
    mt5_path: str = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    cthulu_path: str = r"C:\workspace\cthulu"
    cthulu_config: str = "config.json"
    last_known_config: str = "config.json"  # Track last successful config


class SentinelGuardian:
    """
    The Sentinel Guardian - Watches over Cthulu and MT5
    
    Runs as an independent process, completely separate from Cthulu.
    Survives Cthulu crashes and orchestrates recovery.
    
    SENTINEL DOES NOT START CTHULU - IT ONLY RECOVERS FROM CRASHES.
    Starting Cthulu is the user's responsibility.
    Sentinel only watches and recovers when things go wrong.
    """
    
    def __init__(self, config: Optional[RecoveryConfig] = None):
        self.config = config or RecoveryConfig()
        self.metrics = HealthMetrics()
        self.running = False
        self.start_time: Optional[datetime] = None
        self._crash_timestamps: List[datetime] = []
        self._callbacks: Dict[str, List[Callable]] = {
            "on_crash": [],
            "on_recovery": [],
            "on_state_change": [],
            "on_emergency": []
        }
        self._lock = threading.Lock()
        
        # Auto-restart property (can be toggled by GUI)
        self._auto_restart = True
        
        # Track last known good config
        self._last_known_config = self._find_last_config()
        
        # MT5 Python integration
        self._mt5_module = None
        self._load_mt5_module()
        
        logger.info("SENTINEL Guardian initialized")
        logger.info(f"Cthulu path: {self.config.cthulu_path}")
        logger.info(f"Last known config: {self._last_known_config}")
    
    def _find_last_config(self) -> str:
        """Find the last known good config file"""
        cthulu_dir = Path(self.config.cthulu_path)
        
        # Priority order for configs
        config_priority = [
            "config.json",
            "config_battle_test.json",
            "config_backup.json"
        ]
        
        for cfg in config_priority:
            cfg_path = cthulu_dir / cfg
            if cfg_path.exists():
                logger.info(f"Found config: {cfg}")
                return cfg
        
        return "config.json"  # Default fallback
    
    @property
    def auto_restart(self) -> bool:
        """Get auto-restart state"""
        return self._auto_restart
    
    @auto_restart.setter
    def auto_restart(self, value: bool):
        """Set auto-restart state - can be toggled by GUI"""
        self._auto_restart = value
        self.config.auto_restart_cthulu = value
        logger.info(f"🔄 Auto-restart {'ENABLED' if value else 'DISABLED'}")
    
    def _load_mt5_module(self):
        """Attempt to load MT5 Python module"""
        try:
            import MetaTrader5 as mt5
            self._mt5_module = mt5
            logger.info("✅ MT5 Python module loaded")
        except ImportError:
            logger.warning("⚠️ MT5 Python module not available - limited MT5 control")
    
    def register_callback(self, event: str, callback: Callable):
        """Register callback for events: on_crash, on_recovery, on_state_change, on_emergency"""
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    def _emit_event(self, event: str, *args, **kwargs):
        """Emit event to all registered callbacks"""
        for callback in self._callbacks.get(event, []):
            try:
                callback(*args, **kwargs)
            except Exception as e:
                logger.error(f"Callback error for {event}: {e}")
    
    # ==================== Process Detection ====================
    
    def find_cthulu_process(self) -> Optional[psutil.Process]:
        """Find running Cthulu process"""
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline', []) or []
                cmdline_str = ' '.join(cmdline).lower()
                if 'python' in proc.info['name'].lower():
                    if 'cthulu' in cmdline_str or ('__main__.py' in cmdline_str and 'cthulu' in cmdline_str):
                        return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None
    
    def find_mt5_process(self) -> Optional[psutil.Process]:
        """Find running MetaTrader 5 process"""
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if 'terminal64' in proc.info['name'].lower() or 'metatrader' in proc.info['name'].lower():
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None
    
    # ==================== Health Checks ====================
    
    def check_cthulu_health(self) -> CthhuluState:
        """Check Cthulu process health"""
        proc = self.find_cthulu_process()
        
        if proc is None:
            self.metrics.cthulu_pid = None
            if self.metrics.cthulu_state == CthhuluState.RUNNING:
                # Was running, now not - potential crash
                return CthhuluState.CRASHED
            return CthhuluState.STOPPED
        
        try:
            # Check if process is responding
            cpu = proc.cpu_percent(interval=0.1)
            status = proc.status()
            
            if status == psutil.STATUS_ZOMBIE:
                return CthhuluState.CRASHED
            elif status == psutil.STATUS_STOPPED:
                return CthhuluState.UNRESPONSIVE
            
            self.metrics.cthulu_pid = proc.pid
            return CthhuluState.RUNNING
            
        except psutil.NoSuchProcess:
            self.metrics.cthulu_pid = None
            return CthhuluState.CRASHED
        except Exception as e:
            logger.error(f"Error checking Cthulu health: {e}")
            return CthhuluState.UNRESPONSIVE
    
    def check_mt5_health(self) -> MT5State:
        """Check MT5 process and connection health"""
        proc = self.find_mt5_process()
        
        if proc is None:
            self.metrics.mt5_pid = None
            return MT5State.NOT_RUNNING
        
        self.metrics.mt5_pid = proc.pid
        
        # Try to check connection via MT5 Python API
        if self._mt5_module:
            try:
                if not self._mt5_module.initialize():
                    return MT5State.DISCONNECTED
                
                info = self._mt5_module.terminal_info()
                if info is None:
                    return MT5State.DISCONNECTED
                
                # Check algo trading state
                if hasattr(info, 'trade_allowed') and info.trade_allowed:
                    return MT5State.ALGO_ENABLED
                else:
                    return MT5State.ALGO_DISABLED
                    
            except Exception as e:
                logger.warning(f"MT5 API check failed: {e}")
                return MT5State.DISCONNECTED
        
        # Without API, assume connected if process exists
        return MT5State.CONNECTED
    
    def check_system_health(self) -> SystemState:
        """Determine overall system state"""
        cthulu = self.metrics.cthulu_state
        mt5 = self.metrics.mt5_state
        
        # Both healthy
        if cthulu == CthhuluState.RUNNING and mt5 == MT5State.ALGO_ENABLED:
            return SystemState.HEALTHY
        
        # Recovery in progress
        if self.metrics.recovery_attempts > 0:
            return SystemState.RECOVERING
        
        # Critical states
        if cthulu == CthhuluState.CRASHED:
            return SystemState.CRITICAL
        
        # Degraded states
        if cthulu == CthhuluState.UNRESPONSIVE or mt5 == MT5State.ALGO_DISABLED:
            return SystemState.DEGRADED
        
        # Everything offline
        if cthulu == CthhuluState.STOPPED and mt5 == MT5State.NOT_RUNNING:
            return SystemState.OFFLINE
        
        return SystemState.DEGRADED
    
    # ==================== Recovery Actions ====================
    
    def start_mt5(self) -> bool:
        """Start MetaTrader 5"""
        logger.info("Starting MetaTrader 5...")
        try:
            if self._mt5_module:
                if self._mt5_module.initialize():
                    logger.info("MT5 initialized via Python API")
                    return True
            
            # Fallback: Start via subprocess
            if os.path.exists(self.config.mt5_path):
                subprocess.Popen([self.config.mt5_path], 
                               creationflags=subprocess.DETACHED_PROCESS)
                time.sleep(5)  # Wait for MT5 to start
                logger.info("MT5 started via subprocess")
                return True
            else:
                logger.error(f"MT5 not found at: {self.config.mt5_path}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to start MT5: {e}")
            return False
    
    def enable_algo_trading(self) -> bool:
        """Enable algo trading in MT5"""
        logger.info("Enabling algo trading...")
        
        if not self._mt5_module:
            logger.warning("Cannot enable algo - MT5 module not loaded")
            return False
        
        try:
            # Re-initialize to refresh state
            if not self._mt5_module.initialize():
                logger.error("Failed to initialize MT5 for algo enable")
                return False
            
            # The Python API cannot directly toggle algo trading
            # We can only check the state
            info = self._mt5_module.terminal_info()
            if info and hasattr(info, 'trade_allowed') and info.trade_allowed:
                logger.info("✅ Algo trading is enabled")
                return True
            else:
                logger.warning("⚠️ Algo trading is disabled - requires manual enable or AutoHotkey")
                # Could integrate AutoHotkey here for GUI automation
                return False
                
        except Exception as e:
            logger.error(f"Error enabling algo: {e}")
            return False
    
    def start_cthulu(self, config_file: Optional[str] = None) -> bool:
        """
        Start Cthulu trading system with last known config.
        Used ONLY for crash recovery - not for initial start.
        """
        config = config_file or self._last_known_config
        logger.info(f"🐙 Starting Cthulu with config: {config}")
        
        cthulu_dir = Path(self.config.cthulu_path)
        
        if not cthulu_dir.exists():
            logger.error(f"Cthulu directory not found: {cthulu_dir}")
            return False
        
        # Verify config file exists
        config_path = cthulu_dir / config
        if not config_path.exists():
            logger.error(f"Config file not found: {config_path}")
            # Try to find any valid config
            for fallback in ["config.json", "config_battle_test.json"]:
                fallback_path = cthulu_dir / fallback
                if fallback_path.exists():
                    config = fallback
                    logger.info(f"Using fallback config: {config}")
                    break
            else:
                logger.error("No valid config file found!")
                return False
        
        try:
            # Start Cthulu as detached process with last known config
            # --skip-setup skips wizard for automated recovery
            # No --live flag needed - live is default when --dry-run is absent
            
            # The cthulu package structure: cthulu_dir/cthulu/__main__.py
            # We need to run: python -m cthulu from cthulu_dir with PYTHONPATH=cthulu_dir/cthulu
            cmd = [sys.executable, "-m", "cthulu", "--config", config, "--skip-setup"]
            
            logger.info(f"Running command: {' '.join(cmd)}")
            logger.info(f"Working directory: {cthulu_dir}")
            
            # Set PYTHONPATH to include cthulu/cthulu directory for proper imports
            # The package structure is: cthulu_dir/cthulu/__main__.py
            env = os.environ.copy()
            cthulu_package_dir = str(cthulu_dir / "cthulu")
            env['PYTHONPATH'] = cthulu_package_dir + os.pathsep + env.get('PYTHONPATH', '')
            
            # First try with visible output to capture errors
            proc = subprocess.Popen(
                cmd,
                cwd=str(cthulu_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                env=env
            )
            
            time.sleep(5)  # Wait for startup - increased for bootstrap time
            
            # Check if process is still running
            if proc.poll() is not None:
                # Process exited - get error output
                stdout, stderr = proc.communicate(timeout=5)
                logger.error(f"Cthulu exited with code: {proc.returncode}")
                if stderr:
                    logger.error(f"STDERR: {stderr.decode('utf-8', errors='ignore')[:500]}")
                if stdout:
                    logger.info(f"STDOUT: {stdout.decode('utf-8', errors='ignore')[:500]}")
                return False
            
            # Verify it started by checking process
            cthulu_proc = self.find_cthulu_process()
            if cthulu_proc:
                logger.info(f"✅ Cthulu started (PID: {cthulu_proc.pid}) with config: {config}")
                self.metrics.cthulu_pid = cthulu_proc.pid
                self._last_known_config = config  # Update last known good config
                return True
            else:
                logger.error("Cthulu process not found after start")
                # Check for error output
                try:
                    stdout, stderr = proc.communicate(timeout=2)
                    if stderr:
                        logger.error(f"STDERR: {stderr.decode('utf-8', errors='ignore')[:500]}")
                except:
                    pass
                return False
                
        except Exception as e:
            logger.error(f"Failed to start Cthulu: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def stop_cthulu(self) -> bool:
        """
        Emergency stop Cthulu - for user intervention only.
        This is the ONLY way to stop Cthulu from Sentinel.
        """
        logger.warning("🛑 EMERGENCY STOP - Stopping Cthulu...")
        proc = self.find_cthulu_process()
        
        if proc is None:
            logger.info("Cthulu not running")
            return True
        
        try:
            # Send SIGTERM for graceful shutdown
            proc.terminate()
            proc.wait(timeout=10)
            logger.info("✅ Cthulu stopped gracefully")
            return True
        except psutil.TimeoutExpired:
            logger.warning("Cthulu not responding, forcing kill...")
            proc.kill()
            return True
        except Exception as e:
            logger.error(f"Error stopping Cthulu: {e}")
            return False
    
    def force_recovery(self) -> bool:
        """
        Force recovery - used by GUI Force Recovery button.
        Always starts Cthulu with last known config.
        """
        logger.warning("🔄 FORCE RECOVERY - Restarting Cthulu with last known config")
        
        # First stop any zombie Cthulu processes
        self.stop_cthulu()
        time.sleep(2)
        
        # Start with last known good config
        return self.recover_from_crash()
    
    def recover_from_crash(self) -> bool:
        """Execute crash recovery procedure"""
        logger.warning("CRASH RECOVERY INITIATED")
        
        with self._lock:
            self._crash_timestamps.append(datetime.now())
            self.metrics.crash_count += 1
            self.metrics.last_crash = datetime.now()
            self.metrics.recovery_attempts += 1
        
        # Check for repeated crashes (emergency condition)
        recent_crashes = [
            t for t in self._crash_timestamps 
            if datetime.now() - t < timedelta(minutes=self.config.crash_window_minutes)
        ]
        
        if len(recent_crashes) >= self.config.crash_threshold_for_emergency:
            logger.critical("🚨 EMERGENCY: Too many crashes in short window!")
            self._emit_event("on_emergency", "repeated_crashes", recent_crashes)
            
            if self.config.emergency_stop_on_repeated_crashes:
                logger.critical("⛔ Emergency stop - manual intervention required")
                self.metrics.error_log.append(
                    f"{datetime.now()}: EMERGENCY STOP - {len(recent_crashes)} crashes in "
                    f"{self.config.crash_window_minutes} minutes"
                )
                return False
        
        # Cooldown before recovery
        logger.info(f"⏳ Cooldown: {self.config.recovery_cooldown_seconds}s")
        time.sleep(self.config.recovery_cooldown_seconds)
        
        self._emit_event("on_crash", self.metrics)
        
        # Recovery sequence
        success = True
        
        # Step 1: Ensure MT5 is running
        if self.check_mt5_health() == MT5State.NOT_RUNNING:
            success = self.start_mt5() and success
            time.sleep(5)
        
        # Step 2: Enable algo if needed
        if self.config.auto_enable_algo:
            mt5_state = self.check_mt5_health()
            if mt5_state == MT5State.ALGO_DISABLED:
                self.enable_algo_trading()
        
        # Step 3: Restart Cthulu with LAST KNOWN CONFIG
        if self.config.auto_restart_cthulu and self._auto_restart:
            success = self.start_cthulu(self._last_known_config) and success
        
        if success:
            logger.info("✅ Recovery completed successfully")
            self.metrics.recovery_attempts = 0
            self._emit_event("on_recovery", self.metrics)
        else:
            logger.error("❌ Recovery failed")
        
        return success
    
    # ==================== Main Loop ====================
    
    def update_metrics(self):
        """Update all health metrics"""
        old_state = self.metrics.system_state
        
        self.metrics.timestamp = datetime.now()
        self.metrics.cthulu_state = self.check_cthulu_health()
        self.metrics.mt5_state = self.check_mt5_health()
        self.metrics.system_state = self.check_system_health()
        self.metrics.cpu_percent = psutil.cpu_percent()
        self.metrics.memory_percent = psutil.virtual_memory().percent
        
        if self.start_time:
            self.metrics.uptime_seconds = (datetime.now() - self.start_time).total_seconds()
        
        # Emit state change event
        if old_state != self.metrics.system_state:
            logger.info(f"State change: {old_state.name} -> {self.metrics.system_state.name}")
            self._emit_event("on_state_change", old_state, self.metrics.system_state, self.metrics)
    
    def run(self, poll_interval: float = 5.0, setup_signals: bool = True):
        """Main guardian loop"""
        self.running = True
        self.start_time = datetime.now()
        
        logger.info("=" * 60)
        logger.info("🛡️  SENTINEL GUARDIAN ACTIVE")
        logger.info("=" * 60)
        logger.info(f"Poll interval: {poll_interval}s")
        logger.info(f"Auto restart: {self.config.auto_restart_cthulu}")
        logger.info(f"Auto algo enable: {self.config.auto_enable_algo}")
        logger.info(f"Last known config: {self._last_known_config}")
        logger.info("=" * 60)
        
        # Setup signal handlers for graceful shutdown (only in main thread)
        if setup_signals:
            try:
                def shutdown_handler(signum, frame):
                    logger.info("🛑 Shutdown signal received")
                    self.running = False
                
                signal.signal(signal.SIGINT, shutdown_handler)
                signal.signal(signal.SIGTERM, shutdown_handler)
            except ValueError:
                # Not in main thread - signals already handled elsewhere
                pass
        
        while self.running:
            try:
                self.update_metrics()
                
                # Log status periodically
                logger.debug(
                    f"Status: Cthulu={self.metrics.cthulu_state.name}, "
                    f"MT5={self.metrics.mt5_state.name}, "
                    f"System={self.metrics.system_state.name}"
                )
                
                # Handle crash detection - ONLY if auto_restart is enabled
                if self.metrics.cthulu_state == CthhuluState.CRASHED and self._auto_restart:
                    if self.metrics.recovery_attempts < self.config.max_crash_recovery_attempts:
                        self.recover_from_crash()
                    else:
                        logger.critical("⛔ Max recovery attempts exceeded - stopping guardian")
                        self.running = False
                        break
                
                # Handle MT5 algo disabled
                if (self.config.auto_enable_algo and 
                    self.metrics.mt5_state == MT5State.ALGO_DISABLED):
                    logger.warning("⚠️ Algo trading disabled - attempting re-enable")
                    self.enable_algo_trading()
                
                time.sleep(poll_interval)
                
            except Exception as e:
                logger.error(f"Guardian loop error: {e}")
                time.sleep(poll_interval)
        
        logger.info("🛡️ SENTINEL Guardian shutting down")
    
    def get_status_dict(self) -> Dict[str, Any]:
        """Get current status as dictionary (for GUI)"""
        return {
            "timestamp": self.metrics.timestamp.isoformat(),
            "system_state": self.metrics.system_state.name,
            "cthulu_state": self.metrics.cthulu_state.name,
            "cthulu_pid": self.metrics.cthulu_pid,
            "mt5_state": self.metrics.mt5_state.name,
            "mt5_pid": self.metrics.mt5_pid,
            "cpu_percent": self.metrics.cpu_percent,
            "memory_percent": self.metrics.memory_percent,
            "uptime_seconds": self.metrics.uptime_seconds,
            "crash_count": self.metrics.crash_count,
            "last_crash": self.metrics.last_crash.isoformat() if self.metrics.last_crash else None,
            "recovery_attempts": self.metrics.recovery_attempts,
            "error_log": self.metrics.error_log[-10:],  # Last 10 errors
            "last_known_config": self._last_known_config,
            "auto_restart_enabled": self._auto_restart
        }


# ==================== CLI Entry Point ====================

def main():
    """CLI entry point for Sentinel"""
    import argparse
    
    parser = argparse.ArgumentParser(description="SENTINEL - Cthulu Guardian System")
    parser.add_argument("--interval", type=float, default=5.0, help="Poll interval in seconds")
    parser.add_argument("--no-auto-restart", action="store_true", help="Disable auto-restart of Cthulu")
    parser.add_argument("--no-auto-algo", action="store_true", help="Disable auto-enable of algo trading")
    parser.add_argument("--config", type=str, help="Cthulu config file to use")
    parser.add_argument("--gui", action="store_true", help="Start GUI dashboard")
    parser.add_argument("--headless", action="store_true", help="Run without GUI (CLI only)")
    
    args = parser.parse_args()
    
    config = RecoveryConfig(
        auto_restart_cthulu=not args.no_auto_restart,
        auto_enable_algo=not args.no_auto_algo,
        cthulu_config=args.config or "config.json"
    )
    
    guardian = SentinelGuardian(config)
    
    if args.gui or not args.headless:
        # Start GUI dashboard
        from sentinel.gui.dashboard import SentinelDashboard
        
        # Run guardian in background thread (no signal handling - main thread will handle)
        guardian_thread = threading.Thread(
            target=guardian.run,
            kwargs={'poll_interval': args.interval, 'setup_signals': False},
            daemon=True
        )
        guardian_thread.start()
        logger.info("Starting GUI Dashboard...")
        
        # Run GUI on main thread
        dashboard = SentinelDashboard(guardian)
        dashboard.run()
        guardian.running = False  # Stop guardian when GUI closes
        return
    
    guardian.run(poll_interval=args.interval)


if __name__ == "__main__":
    main()
