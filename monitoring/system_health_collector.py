"""
System Health Monitoring Collector

Tracks system-level metrics: processes, workloads, resources, performance.
Does NOT track trading metrics - purely system operations.

Output: metrics/system_health.csv
"""

import os
import csv
import time
try:
    import psutil
except Exception:
    psutil = None
import logging
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, asdict


@dataclass
class SystemHealthSnapshot:
    """Single snapshot of system health metrics"""
    
    # Timestamp
    timestamp: str = ""
    
    # Process Info
    process_pid: int = 0
    process_name: str = ""
    process_status: str = ""  # running, sleeping, zombie, etc.
    process_threads: int = 0
    process_cpu_percent: float = 0.0
    process_memory_mb: float = 0.0
    process_memory_percent: float = 0.0
    
    # Child Processes
    child_process_count: int = 0
    child_cpu_total: float = 0.0
    child_memory_total_mb: float = 0.0
    
    # System CPU
    system_cpu_percent: float = 0.0
    system_cpu_count_logical: int = 0
    system_cpu_count_physical: int = 0
    system_cpu_freq_current: float = 0.0
    system_cpu_freq_max: float = 0.0
    
    # System Memory
    system_memory_total_gb: float = 0.0
    system_memory_available_gb: float = 0.0
    system_memory_used_gb: float = 0.0
    system_memory_percent: float = 0.0
    system_memory_cached_gb: float = 0.0
    
    # System Disk
    disk_total_gb: float = 0.0
    disk_used_gb: float = 0.0
    disk_free_gb: float = 0.0
    disk_percent: float = 0.0
    disk_read_mb: float = 0.0
    disk_write_mb: float = 0.0
    
    # Network
    network_sent_mb: float = 0.0
    network_recv_mb: float = 0.0
    network_connections: int = 0
    network_connections_established: int = 0
    
    # System Load
    load_avg_1min: float = 0.0
    load_avg_5min: float = 0.0
    load_avg_15min: float = 0.0
    
    # Process Workload
    workload_tasks_pending: int = 0
    workload_tasks_running: int = 0
    workload_tasks_completed: int = 0
    workload_queue_size: int = 0
    
    # Thread Pool
    threadpool_size: int = 0
    threadpool_active: int = 0
    threadpool_idle: int = 0
    
    # Performance Metrics
    perf_loop_rate_hz: float = 0.0  # Main loop frequency
    perf_avg_loop_time_ms: float = 0.0
    perf_max_loop_time_ms: float = 0.0
    perf_gc_collections: int = 0
    perf_gc_time_ms: float = 0.0
    
    # File Handles
    files_open: int = 0
    files_max: int = 0
    files_percent: float = 0.0
    
    # Database Connections (if applicable)
    db_connections_active: int = 0
    db_connections_idle: int = 0
    db_pool_size: int = 0
    
    # API/External Connections
    api_mt5_connected: bool = False
    api_mt5_latency_ms: float = 0.0
    api_rate_limit_remaining: int = 0
    
    # Error Tracking
    errors_total: int = 0
    errors_last_hour: int = 0
    warnings_total: int = 0
    warnings_last_hour: int = 0
    exceptions_total: int = 0
    exceptions_last_hour: int = 0
    
    # System Uptime
    system_uptime_seconds: float = 0.0
    process_uptime_seconds: float = 0.0
    
    # Temperature (if available)
    cpu_temp_celsius: float = 0.0
    gpu_temp_celsius: float = 0.0


class SystemHealthCollector:
    """
    Collects comprehensive system health metrics.
    
    Monitors:
    - Process and thread metrics
    - CPU, memory, disk, network
    - System load and performance
    - Error tracking
    - Resource utilization
    """
    
    def __init__(self, csv_path: str = None, update_interval: float = 5.0):
        """
        Initialize collector.
        
        Args:
            csv_path: Path to output CSV (default: metrics/system_health.csv)
            update_interval: Seconds between CSV writes (default: 5.0)
        """
        self.logger = logging.getLogger("cthulu.system_health_collector")

        # If psutil is not available, disable this collector gracefully
        if psutil is None:
            self.disabled = True
            self.logger.warning("psutil not available; system health collector disabled")
            # Set minimal attributes so other code can inspect CSV path if needed
            if csv_path is None:
                cthulu_root = Path(__file__).parent.parent
                metrics_dir = cthulu_root / "metrics"
                try:
                    metrics_dir.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    self.logger.debug("Failed to create metrics directory for system health collector: %s", e, exc_info=True)
                csv_path = str(metrics_dir / "system_health.csv")
            self.csv_path = csv_path
            self.update_interval = update_interval
            self._running = False
            self._writer_thread = None
            return

        # Else: full initialization
        self.disabled = False
        # Set path - CSV goes to centralized metrics/ directory
        if csv_path is None:
            cthulu_root = Path(__file__).parent.parent
            metrics_dir = cthulu_root / "metrics"
            metrics_dir.mkdir(parents=True, exist_ok=True)
            csv_path = str(metrics_dir / "system_health.csv")

        self.csv_path = csv_path
        self.update_interval = update_interval

        # Get current process
        self.process = psutil.Process()
        self.process_start_time = time.time()

        # Tracking
        self.disk_io_start = psutil.disk_io_counters()
        self.net_io_start = psutil.net_io_counters()

        # Current snapshot
        self.current_snapshot = SystemHealthSnapshot()
        self._lock = threading.Lock()

        # CSV writer thread
        self._running = False
        self._writer_thread = None

        # Initialize CSV
        self._initialize_csv()

        self.logger.info(f"System health collector initialized")
        self.logger.info(f"  CSV: {self.csv_path}")
        self.logger.info(f"  PID: {self.process.pid}")
        self.logger.info(f"  Update Interval: {self.update_interval}s")
    
    def _initialize_csv(self):
        """Initialize CSV file with headers - always ensures header row exists"""
        try:
            # Create directory if needed
            Path(self.csv_path).parent.mkdir(parents=True, exist_ok=True)
            
            fieldnames = list(asdict(SystemHealthSnapshot()).keys())
            
            # Check if file exists and has valid header
            needs_header = True
            if os.path.exists(self.csv_path):
                try:
                    with open(self.csv_path, 'r', newline='') as f:
                        reader = csv.reader(f)
                        first_row = next(reader, None)
                        # Check if first row is our expected header (must match exactly)
                        if first_row and len(first_row) == len(fieldnames) and first_row[0] == 'timestamp':
                            # Verify it's actually a header (not data starting with ISO timestamp)
                            if first_row == fieldnames:
                                needs_header = False
                            else:
                                self.logger.warning(f"CSV header mismatch, resetting file")
                                needs_header = True
                        else:
                            # Invalid header detected - file needs reset
                            self.logger.warning(f"Invalid CSV header detected (first={first_row[0] if first_row else 'None'}, cols={len(first_row) if first_row else 0}), resetting file")
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
    
    def start(self):
        """Start background collection and CSV writer thread"""
        if getattr(self, 'disabled', False):
            self.logger.info("System health collector is disabled (psutil unavailable); skipping start")
            return

        if self._running:
            return

        self._running = True
        self._writer_thread = threading.Thread(target=self._collection_loop, daemon=True)
        self._writer_thread.start()
        self.logger.info("System health collector started")
    
    def stop(self):
        """Stop collector"""
        if not self._running:
            return
        
        self.logger.info("Stopping system health collector...")
        self._running = False
        
        if self._writer_thread:
            self._writer_thread.join(timeout=5.0)
        
        # Final write
        self._collect_metrics()
        self._write_snapshot()
        self.logger.info("System health collector stopped")
    
    def _collection_loop(self):
        """Background thread that collects metrics and writes to CSV"""
        while self._running:
            try:
                self._collect_metrics()
                self._write_snapshot()
                time.sleep(self.update_interval)
            except Exception as e:
                self.logger.error(f"Error in collection loop: {e}")
    
    def _collect_metrics(self):
        """Collect all system health metrics"""
        try:
            with self._lock:
                snapshot = self.current_snapshot
                
                # Timestamp (using timezone-aware UTC)
                snapshot.timestamp = datetime.now(timezone.utc).isoformat()
                
                # Process info
                snapshot.process_pid = self.process.pid
                snapshot.process_name = self.process.name()
                snapshot.process_status = self.process.status()
                snapshot.process_threads = self.process.num_threads()
                snapshot.process_cpu_percent = self.process.cpu_percent()
                
                mem_info = self.process.memory_info()
                snapshot.process_memory_mb = mem_info.rss / (1024 * 1024)
                snapshot.process_memory_percent = self.process.memory_percent()
                
                # Child processes
                try:
                    children = self.process.children(recursive=True)
                    snapshot.child_process_count = len(children)
                    snapshot.child_cpu_total = sum(c.cpu_percent() for c in children)
                    snapshot.child_memory_total_mb = sum(c.memory_info().rss for c in children) / (1024 * 1024)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                
                # System CPU
                snapshot.system_cpu_percent = psutil.cpu_percent(interval=0.1)
                snapshot.system_cpu_count_logical = psutil.cpu_count(logical=True)
                snapshot.system_cpu_count_physical = psutil.cpu_count(logical=False)
                
                try:
                    cpu_freq = psutil.cpu_freq()
                    if cpu_freq:
                        snapshot.system_cpu_freq_current = cpu_freq.current
                        snapshot.system_cpu_freq_max = cpu_freq.max
                except Exception as e:
                    self.logger.debug("Failed to read CPU frequency: %s", e, exc_info=True)
                
                # System Memory
                mem = psutil.virtual_memory()
                snapshot.system_memory_total_gb = mem.total / (1024 ** 3)
                snapshot.system_memory_available_gb = mem.available / (1024 ** 3)
                snapshot.system_memory_used_gb = mem.used / (1024 ** 3)
                snapshot.system_memory_percent = mem.percent
                
                try:
                    snapshot.system_memory_cached_gb = mem.cached / (1024 ** 3)
                except AttributeError as e:
                    self.logger.debug("Memory object missing 'cached' attribute: %s", e)
                
                # System Disk
                try:
                    disk = psutil.disk_usage('/')
                    snapshot.disk_total_gb = disk.total / (1024 ** 3)
                    snapshot.disk_used_gb = disk.used / (1024 ** 3)
                    snapshot.disk_free_gb = disk.free / (1024 ** 3)
                    snapshot.disk_percent = disk.percent
                    
                    # Disk I/O
                    disk_io = psutil.disk_io_counters()
                    if disk_io and self.disk_io_start:
                        snapshot.disk_read_mb = (disk_io.read_bytes - self.disk_io_start.read_bytes) / (1024 * 1024)
                        snapshot.disk_write_mb = (disk_io.write_bytes - self.disk_io_start.write_bytes) / (1024 * 1024)
                except Exception as e:
                    self.logger.debug("Failed to collect disk metrics: %s", e, exc_info=True)
                
                # Network
                try:
                    net_io = psutil.net_io_counters()
                    if net_io and self.net_io_start:
                        snapshot.network_sent_mb = (net_io.bytes_sent - self.net_io_start.bytes_sent) / (1024 * 1024)
                        snapshot.network_recv_mb = (net_io.bytes_recv - self.net_io_start.bytes_recv) / (1024 * 1024)
                    
                    connections = psutil.net_connections(kind='inet')
                    snapshot.network_connections = len(connections)
                    snapshot.network_connections_established = len([c for c in connections if c.status == 'ESTABLISHED'])
                except (psutil.AccessDenied, AttributeError) as e:
                    self.logger.debug("Failed to collect network metrics: %s", e, exc_info=True)
                
                # System Load
                try:
                    load_avg = psutil.getloadavg()
                    snapshot.load_avg_1min = load_avg[0]
                    snapshot.load_avg_5min = load_avg[1]
                    snapshot.load_avg_15min = load_avg[2]
                except (AttributeError, OSError) as e:
                    self.logger.debug("getloadavg not available on this platform: %s", e)
                
                # File Handles
                try:
                    snapshot.files_open = self.process.num_fds() if hasattr(self.process, 'num_fds') else len(self.process.open_files())
                except (psutil.AccessDenied, AttributeError) as e:
                    self.logger.debug("Failed to read file handle counts: %s", e, exc_info=True)
                
                # Uptime
                try:
                    snapshot.system_uptime_seconds = time.time() - psutil.boot_time()
                except Exception as e:
                    self.logger.debug("Failed to compute system uptime: %s", e, exc_info=True)
                
                snapshot.process_uptime_seconds = time.time() - self.process_start_time
                
                # Temperature (if available)
                try:
                    temps = psutil.sensors_temperatures()
                    if temps and 'coretemp' in temps:
                        snapshot.cpu_temp_celsius = temps['coretemp'][0].current
                except (AttributeError, KeyError) as e:
                    self.logger.debug("Failed to read temperature sensors: %s", e, exc_info=True)
                
        except Exception as e:
            self.logger.error(f"Error collecting metrics: {e}")
    
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
    
    def get_current_snapshot(self) -> SystemHealthSnapshot:
        """Get current snapshot (thread-safe)"""
        with self._lock:
            return SystemHealthSnapshot(**asdict(self.current_snapshot))
    
    # Manual update methods
    
    def update_workload(self, pending: int = 0, running: int = 0, completed: int = 0, queue_size: int = 0):
        """Update workload metrics"""
        with self._lock:
            self.current_snapshot.workload_tasks_pending = pending
            self.current_snapshot.workload_tasks_running = running
            self.current_snapshot.workload_tasks_completed = completed
            self.current_snapshot.workload_queue_size = queue_size
    
    def update_threadpool(self, size: int = 0, active: int = 0, idle: int = 0):
        """Update thread pool metrics"""
        with self._lock:
            self.current_snapshot.threadpool_size = size
            self.current_snapshot.threadpool_active = active
            self.current_snapshot.threadpool_idle = idle
    
    def update_performance(self, loop_rate_hz: float = 0.0, avg_loop_ms: float = 0.0, 
                          max_loop_ms: float = 0.0):
        """Update performance metrics"""
        with self._lock:
            self.current_snapshot.perf_loop_rate_hz = loop_rate_hz
            self.current_snapshot.perf_avg_loop_time_ms = avg_loop_ms
            self.current_snapshot.perf_max_loop_time_ms = max_loop_ms
    
    def update_database(self, active: int = 0, idle: int = 0, pool_size: int = 0):
        """Update database connection metrics"""
        with self._lock:
            self.current_snapshot.db_connections_active = active
            self.current_snapshot.db_connections_idle = idle
            self.current_snapshot.db_pool_size = pool_size
    
    def update_api(self, mt5_connected: bool = False, latency_ms: float = 0.0, 
                   rate_limit: int = 0):
        """Update API connection metrics"""
        with self._lock:
            self.current_snapshot.api_mt5_connected = mt5_connected
            self.current_snapshot.api_mt5_latency_ms = latency_ms
            self.current_snapshot.api_rate_limit_remaining = rate_limit
    
    def increment_error(self):
        """Increment error counter"""
        with self._lock:
            self.current_snapshot.errors_total += 1
            self.current_snapshot.errors_last_hour += 1
    
    def increment_warning(self):
        """Increment warning counter"""
        with self._lock:
            self.current_snapshot.warnings_total += 1
            self.current_snapshot.warnings_last_hour += 1
    
    def increment_exception(self):
        """Increment exception counter"""
        with self._lock:
            self.current_snapshot.exceptions_total += 1
            self.current_snapshot.exceptions_last_hour += 1
