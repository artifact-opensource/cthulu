"""
Observability Integration

Provides integration hooks for starting/stopping the observability service
as part of the Cthulu bootstrap process.

SIMPLIFIED FLOW:
Trading System → ComprehensiveCollector → CSV Export
                                       → Prometheus Export (OPTIONAL)
"""

import logging
import multiprocessing
from pathlib import Path
from typing import Optional


def start_observability_service(
    csv_path: Optional[str] = None,
    update_interval: float = 1.0,
    enable_prometheus: bool = False,
    prom_path: Optional[str] = None,
    http_port: Optional[int] = None
) -> Optional[multiprocessing.Process]:
    """
    Start observability service as separate process during bootstrap.
    
    This starts comprehensive metrics collection in a separate process
    that won't block the main trading loop.
    
    CORE FEATURE: Real-time CSV export to comprehensive_metrics.csv
    OPTIONAL: Prometheus export (only if enable_prometheus=True)
    
    Args:
        csv_path: Path to CSV metrics file (default: observability/comprehensive_metrics.csv)
        update_interval: Seconds between metric updates (default: 1.0)
        enable_prometheus: Enable Prometheus export (default: False)
        prom_path: Path to Prometheus metrics file (only if enable_prometheus=True)
        http_port: Optional HTTP port for metrics endpoint
        
    Returns:
        Process object if started successfully, None otherwise
    """
    logger = logging.getLogger("cthulu.observability_integration")
    
    try:
        from observability.service import start_observability_process
        
        # Set defaults with centralized metrics/ directory
        if csv_path is None:
            # Auto-path: metrics/ (centralized)
            metrics_dir = Path(__file__).parent.parent / "metrics"
            metrics_dir.mkdir(exist_ok=True)
            csv_path = str(metrics_dir / "comprehensive_metrics.csv")
        
        if prom_path is None and enable_prometheus:
            # Auto-path: prometheus/tmp/ (only if Prometheus enabled)
            prom_dir = Path(__file__).parent.parent / "prometheus" / "tmp"
            prom_dir.mkdir(parents=True, exist_ok=True)
            prom_path = str(prom_dir / "cthulu_metrics.prom")
        
        logger.info("Starting observability service...")
        logger.info(f"  CSV: {csv_path}")
        if enable_prometheus:
            logger.info(f"  Prometheus: ENABLED → {prom_path}")
        else:
            logger.info(f"  Prometheus: DISABLED (use enable_prometheus=True to enable)")
        if http_port:
            logger.info(f"  HTTP: port {http_port}")
        
        # Start as subprocess
        process = start_observability_process(
            csv_path=csv_path,
            prom_path=prom_path,
            update_interval=update_interval,
            http_port=http_port,
            enable_prometheus=enable_prometheus
        )
        
        logger.info(f"Observability service started (PID: {process.pid})")
        return process
        
    except Exception as e:
        logger.error(f"Failed to start observability service: {e}")
        logger.error("Continuing without observability service")
        return None


def stop_observability_service(process: Optional[multiprocessing.Process]):
    """
    Stop observability service process.
    
    Args:
        process: Process object from start_observability_service
    """
    if process is None:
        return
    
    logger = logging.getLogger("cthulu.observability_integration")
    
    try:
        if process.is_alive():
            logger.info("Stopping observability service...")
            process.terminate()
            process.join(timeout=5.0)
            
            if process.is_alive():
                logger.warning("Observability service did not stop gracefully, killing...")
                process.kill()
                process.join(timeout=2.0)
            
            logger.info("Observability service stopped")
    except Exception as e:
        logger.error(f"Error stopping observability service: {e}")


def get_comprehensive_collector():
    """
    Get the comprehensive metrics collector for manual updates.
    
    Returns:
        ComprehensiveMetricsCollector instance
    """
    from observability.comprehensive_collector import ComprehensiveMetricsCollector
    return ComprehensiveMetricsCollector()
