"""Sentinel Core Module"""
# Import happens at runtime to avoid path issues
__all__ = ['SentinelGuardian', 'RecoveryConfig']

def get_guardian():
    from .guardian import SentinelGuardian, RecoveryConfig
    return SentinelGuardian, RecoveryConfig
