"""
Observability Suite - Unified Command to Run All Services

Launches all three observability and monitoring services:
1. Observability Service (trading metrics)
2. Indicator Monitoring Service (signal analysis + scoring)
3. System Health Service (system performance)

Usage:
    python -m observability.suit [--csv] [--prom] [--8181]
    
Examples:
    # Run all services with CSV only
    python -m observability.suit --csv
    
    # Run all with CSV + Prometheus on port 8181
    python -m observability.suit --csv --8181
"""

import sys
import time
import signal
import logging
import argparse
import multiprocessing
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from observability.integration import start_observability_service
try:
    from monitoring.service import start_indicator_process, start_system_health_process
    MONITORING_AVAILABLE = True
except ImportError as e:
    MONITORING_AVAILABLE = False
    MONITORING_ERROR = str(e)
    
from observability.logger import setup_logger


class ObservabilitySuite:
    """
    Manages all three observability/monitoring services as a unified suite.
    """
    
    def __init__(self):
        self.logger = setup_logger("cthulu.observability_suite", level=logging.INFO)
        self.processes = []
        self.running = False
        
    def start_all(self, enable_csv: bool = True, enable_prometheus: bool = False, 
                  http_port: int = None):
        """
        Start all three services.
        
        Args:
            enable_csv: Enable CSV export (default: True)
            enable_prometheus: Enable Prometheus export (default: False, or True if http_port set)
            http_port: HTTP metrics port (8181, 8182, 8183, etc.)
        """
        self.logger.info("=" * 60)
        self.logger.info("CTHULU OBSERVABILITY SUITE")
        self.logger.info("=" * 60)
        self.logger.info("")
        
        if not MONITORING_AVAILABLE:
            self.logger.warning("Monitoring services unavailable: {}".format(MONITORING_ERROR))
            self.logger.info("Starting observability service only...")
            self.logger.info("To enable monitoring, install dependencies: pip install psutil")
            self.logger.info("")
        else:
            self.logger.info("Starting 3 independent services:")
            self.logger.info("  1. Observability Service (Trading Metrics)")
            self.logger.info("  2. Indicator Monitoring Service (Signal Analysis)")
            self.logger.info("  3. System Health Service (Performance Monitoring)")
            self.logger.info("")
        
        # Determine if Prometheus should be enabled
        if http_port and not enable_prometheus:
            enable_prometheus = True
        
        try:
            # 1. Start Observability Service (trading metrics)
            self.logger.info("[1/3] Starting Observability Service...")
            obs_process = start_observability_service(
                enable_prometheus=enable_prometheus,
                http_port=http_port
            )
            if obs_process:
                self.processes.append(("Observability", obs_process))
                self.logger.info("  ✓ Observability Service started (PID: {})".format(obs_process.pid))
                self.logger.info("    Output: metrics/comprehensive_metrics.csv")
            else:
                self.logger.warning("  ✗ Failed to start Observability Service")
            
            time.sleep(0.5)
            
            # 2. Start Indicator Monitoring Service (if available)
            if MONITORING_AVAILABLE:
                self.logger.info("[2/3] Starting Indicator Monitoring Service...")
                ind_process = start_indicator_process()
                if ind_process:
                    self.processes.append(("Indicator", ind_process))
                    self.logger.info("  ✓ Indicator Service started (PID: {})".format(ind_process.pid))
                    self.logger.info("    Output: metrics/indicator_metrics.csv")
                else:
                    self.logger.warning("  ✗ Failed to start Indicator Service")
                
                time.sleep(0.5)
                
                # 3. Start System Health Service
                self.logger.info("[3/3] Starting System Health Service...")
                sys_process = start_system_health_process()
                if sys_process:
                    self.processes.append(("System Health", sys_process))
                    self.logger.info("  ✓ System Health Service started (PID: {})".format(sys_process.pid))
                    self.logger.info("    Output: metrics/system_health.csv")
                else:
                    self.logger.warning("  ✗ Failed to start System Health Service")
            else:
                self.logger.info("[2-3] Monitoring services skipped (dependencies not available)")
                self.logger.info("      Install with: pip install psutil")
            
            self.logger.info("")
            self.logger.info("=" * 60)
            if MONITORING_AVAILABLE:
                self.logger.info("ALL SERVICES RUNNING")
            else:
                self.logger.info("OBSERVABILITY SERVICE RUNNING")
            self.logger.info("=" * 60)
            self.logger.info("")
            self.logger.info("Canonical Output Files (centralized in metrics/):")
            self.logger.info("  1. metrics/comprehensive_metrics.csv (173 fields)")
            if MONITORING_AVAILABLE:
                self.logger.info("  2. metrics/indicator_metrics.csv (78 fields + scoring)")
                self.logger.info("  3. metrics/system_health.csv (80+ fields)")
            self.logger.info("")
            
            if enable_prometheus and http_port:
                self.logger.info("Prometheus endpoint: http://localhost:{}".format(http_port))
                self.logger.info("")
            
            self.logger.info("Press Ctrl+C to stop all services")
            self.logger.info("")
            
            self.running = True
            return True
            
        except Exception as e:
            self.logger.error("Error starting services: {}".format(e))
            self.stop_all()
            return False
    
    def stop_all(self):
        """Stop all running services"""
        if not self.processes:
            return
        
        self.logger.info("")
        self.logger.info("=" * 60)
        self.logger.info("SHUTTING DOWN ALL SERVICES")
        self.logger.info("=" * 60)
        
        for name, process in self.processes:
            try:
                if process and process.is_alive():
                    self.logger.info("Stopping {} Service (PID: {})...".format(name, process.pid))
                    process.terminate()
                    process.join(timeout=5)
                    
                    if process.is_alive():
                        self.logger.warning("  Force killing {}...".format(name))
                        process.kill()
                        process.join()
                    
                    self.logger.info("  ✓ {} Service stopped".format(name))
            except Exception as e:
                self.logger.error("Error stopping {}: {}".format(name, e))
        
        self.processes = []
        self.running = False
        self.logger.info("")
        self.logger.info("All services stopped")
    
    def monitor_processes(self):
        """Monitor all processes and restart if any crash"""
        while self.running:
            try:
                time.sleep(5)
                
                # Check if any process died
                for name, process in self.processes:
                    if not process.is_alive():
                        self.logger.error("{} Service crashed! (PID: {})".format(name, process.pid))
                        self.running = False
                        break
                        
            except KeyboardInterrupt:
                break
    
    def run(self, enable_csv: bool = True, enable_prometheus: bool = False,
            http_port: int = None):
        """
        Main run loop - start and monitor all services.
        """
        # Set up signal handlers
        def signal_handler(signum, frame):
            self.logger.info("\nReceived signal, shutting down...")
            self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start all services
        if not self.start_all(enable_csv, enable_prometheus, http_port):
            return 1
        
        # Monitor until stopped
        try:
            self.monitor_processes()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop_all()
        
        return 0


def main():
    """Main entry point for observability suite"""
    parser = argparse.ArgumentParser(
        description="Cthulu Observability Suite - Run all monitoring services",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all services with CSV only
  python -m observability.suit --csv
  
  # Run all with CSV + Prometheus on port 8181
  python -m observability.suit --csv --8181
  
  # Run all with CSV + Prometheus + custom port
  python -m observability.suit --csv --prom --9090

Output Files (3 Canonical CSVs - centralized in metrics/):
  1. metrics/comprehensive_metrics.csv (173 trading metrics)
  2. metrics/indicator_metrics.csv (78 indicator/signal fields + scoring)
  3. metrics/system_health.csv (80+ system health/performance fields)
        """
    )
    
    parser.add_argument(
        '--csv',
        action='store_true',
        help='Enable CSV export (always recommended)'
    )
    
    parser.add_argument(
        '--prom',
        action='store_true',
        help='Enable Prometheus export (requires port flag)'
    )
    
    parser.add_argument(
        '--8181',
        action='store_const',
        const=8181,
        dest='port',
        help='Enable Prometheus on port 8181'
    )
    
    parser.add_argument(
        '--8182',
        action='store_const',
        const=8182,
        dest='port',
        help='Enable Prometheus on port 8182'
    )
    
    parser.add_argument(
        '--8183',
        action='store_const',
        const=8183,
        dest='port',
        help='Enable Prometheus on port 8183'
    )
    
    args = parser.parse_args()
    
    # Determine settings
    enable_prometheus = args.prom or args.port is not None
    http_port = args.port
    
    # Default to CSV if nothing specified
    if not args.csv and not enable_prometheus:
        args.csv = True
    
    # Create and run suite
    suite = ObservabilitySuite()
    return suite.run(
        enable_csv=args.csv,
        enable_prometheus=enable_prometheus,
        http_port=http_port
    )


if __name__ == '__main__':
    # Required for Windows multiprocessing
    multiprocessing.freeze_support()
    sys.exit(main())
