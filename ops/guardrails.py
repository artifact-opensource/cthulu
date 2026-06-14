import os
import shutil
import psutil


def allow_auto_apply():
    """Return True only if AUTO_APPLY_RECOMMENDATIONS=='true' and LIVE_RUN_CONFIRM=='1'.
    This makes auto-apply an explicit opt-in.
    """
    auto_apply = os.environ.get('AUTO_APPLY_RECOMMENDATIONS', 'false').lower()
    live_confirm = os.environ.get('LIVE_RUN_CONFIRM', '0')
    return auto_apply == 'true' and live_confirm == '1'


def check_disk(min_gb: float) -> bool:
    total, used, free = shutil.disk_usage(os.getcwd())
    free_gb = free / (1024**3)
    return free_gb >= min_gb


def check_ram(min_gb: float) -> bool:
    mem = psutil.virtual_memory()
    free_gb = (mem.available) / (1024**3)
    return free_gb >= min_gb


def check_model_size(path: str, max_gb: float) -> bool:
    """Return True if total size at `path` is <= max_gb. If path absent, return True.
    """
    if not os.path.exists(path):
        return True
    total = 0
    if os.path.isfile(path):
        total = os.path.getsize(path)
    else:
        for root, dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    return (total / (1024**3)) <= max_gb
