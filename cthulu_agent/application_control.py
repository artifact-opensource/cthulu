"""Narrow, graceful controls for the configured MetaTrader 5 terminal."""
from __future__ import annotations

import ctypes
import os
import subprocess
import time
from ctypes import wintypes
from pathlib import Path
from typing import List


class ApplicationControlError(RuntimeError):
    pass


class _ProcessEntry32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


def configured_mt5_path() -> Path:
    raw = os.environ.get("MT5_PATH", "").strip()
    if not raw:
        raise ApplicationControlError("MT5_PATH is not configured.")
    path = Path(raw).expanduser().resolve()
    if path.name.casefold() not in {"terminal64.exe", "terminal.exe"}:
        raise ApplicationControlError("MT5_PATH must point to terminal64.exe or terminal.exe.")
    if not path.is_file():
        raise ApplicationControlError(f"Configured MT5 terminal does not exist: {path}")
    return path


def _process_ids_for_path(path: Path) -> List[int]:
    if os.name != "nt":
        raise ApplicationControlError("MT5 application control is supported on Windows only.")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry32W)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry32W)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ApplicationControlError(f"Could not enumerate Windows processes (error {ctypes.get_last_error()}).")

    wanted = os.path.normcase(str(path))
    found: List[int] = []
    try:
        entry = _ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(entry)
        more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            if entry.szExeFile.casefold() == path.name.casefold():
                process = kernel32.OpenProcess(0x1000, False, entry.th32ProcessID)
                if process:
                    try:
                        buffer = ctypes.create_unicode_buffer(32768)
                        size = wintypes.DWORD(len(buffer))
                        if kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
                            if os.path.normcase(buffer.value) == wanted:
                                found.append(int(entry.th32ProcessID))
                    finally:
                        kernel32.CloseHandle(process)
            more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return found


def status_mt5() -> str:
    path = configured_mt5_path()
    pids = _process_ids_for_path(path)
    if not pids:
        return "Configured MT5 terminal is not running."
    return "Configured MT5 terminal is running (PID " + ", ".join(map(str, pids)) + ")."


def launch_mt5() -> str:
    path = configured_mt5_path()
    pids = _process_ids_for_path(path)
    if pids:
        return "Configured MT5 terminal is already running (PID " + ", ".join(map(str, pids)) + ")."
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(
        [str(path)],
        cwd=str(path.parent),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=flags,
        shell=False,
    )
    return "Launched the configured MT5 terminal."


def close_mt5(timeout: float = 15.0) -> str:
    path = configured_mt5_path()
    pids = _process_ids_for_path(path)
    if not pids:
        return "Configured MT5 terminal is already closed."
    if os.name != "nt":
        raise ApplicationControlError("MT5 application control is supported on Windows only.")

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    enum_windows = user32.EnumWindows
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    targets = set(pids)
    windows: List[int] = []

    @callback_type
    def collect(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in targets:
            windows.append(hwnd)
        return True

    enum_windows.argtypes = [callback_type, wintypes.LPARAM]
    enum_windows.restype = wintypes.BOOL
    if not enum_windows(collect, 0):
        raise ApplicationControlError(f"Could not enumerate MT5 windows (error {ctypes.get_last_error()}).")
    if not windows:
        raise ApplicationControlError("MT5 has no visible window to close gracefully; no process was terminated.")
    for hwnd in windows:
        if not user32.PostMessageW(hwnd, 0x0010, 0, 0):  # WM_CLOSE
            raise ApplicationControlError(f"Could not request graceful MT5 shutdown (error {ctypes.get_last_error()}).")

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = _process_ids_for_path(path)
        if not remaining:
            return "Closed the configured MT5 terminal gracefully."
        time.sleep(0.25)
    raise ApplicationControlError("MT5 did not close in time; it was not force-terminated.")
