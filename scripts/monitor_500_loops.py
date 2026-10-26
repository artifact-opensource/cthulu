"""
Monitor Cthulu logs and count Loop entries until 500 loops are observed.
Reports counts of errors, SL/TP modifications, and 'Failed to save position' occurrences.
"""
import time
from pathlib import Path
import re

LOG_DIR = Path('logs')
LOOP_RE = re.compile(r"Loop #(?P<num>\d+):")
ERROR_RE = re.compile(r"\[ERROR\].*")
SL_RE = re.compile(r"SL modified for #(?P<ticket>\d+):")
TP_RE = re.compile(r"TP modified for #(?P<ticket>\d+):")
SAVE_FAIL_RE = re.compile(r"Failed to save position")


def tail_file(path: Path):
    with path.open('r', encoding='utf-8', errors='replace') as f:
        # Go to end
        f.seek(0, 2)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.5)
                continue
            yield line


def find_latest_log():
    if not LOG_DIR.exists():
        raise SystemExit('Logs directory not found')
    files = sorted(LOG_DIR.glob('**/*.log'), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        # fallback to any file
        files = sorted(LOG_DIR.rglob('*.*'), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0]


def main():
    latest = find_latest_log()
    print('Monitoring log:', latest)

    loops = 0
    errors = 0
    sl_mods = 0
    tp_mods = 0
    save_fails = 0

    for line in tail_file(latest):
        if LOOP_RE.search(line):
            loops += 1
            if loops % 10 == 0:
                print(f'Loops observed: {loops}')
        if ERROR_RE.search(line):
            errors += 1
        if SL_RE.search(line):
            sl_mods += 1
        if TP_RE.search(line):
            tp_mods += 1
        if SAVE_FAIL_RE.search(line):
            save_fails += 1
        if loops >= 500:
            print('\n--- Monitoring complete ---')
            print(f'Loops: {loops}\nErrors: {errors}\nSL modifications: {sl_mods}\nTP modifications: {tp_mods}\nSave failures: {save_fails}')
            break


if __name__ == '__main__':
    main()
