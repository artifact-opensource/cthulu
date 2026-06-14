"""Sentinel GUI Module"""
# Import happens at runtime to avoid circular imports
__all__ = ['SentinelDashboard']

def get_dashboard():
    from .dashboard import SentinelDashboard
    return SentinelDashboard
