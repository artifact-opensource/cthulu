"""Resolve safe dashboard bind addresses for loopback, LAN, and Tailscale access."""
from __future__ import annotations

import ipaddress
import os
import shutil
import socket
import subprocess
from dataclasses import dataclass
from typing import List


ACCESS_MODES = ("loopback", "lan", "tailscale")


class NetworkAccessError(RuntimeError):
    pass


@dataclass(frozen=True)
class BindTarget:
    host: str
    urls: List[str]
    allowed_hosts: set[str]


def get_access_mode() -> str:
    mode = os.environ.get("DASHBOARD_ACCESS_MODE", "loopback").strip().lower()
    if mode not in ACCESS_MODES:
        raise NetworkAccessError(f"DASHBOARD_ACCESS_MODE must be one of: {', '.join(ACCESS_MODES)}")
    return mode


def _lan_ipv4_addresses() -> List[str]:
    addresses = set()
    try:
        for result in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM):
            address = result[4][0]
            parsed = ipaddress.ip_address(address)
            if parsed.is_private and not parsed.is_loopback and not parsed.is_link_local:
                addresses.add(address)
    except OSError as exc:
        raise NetworkAccessError(f"Could not discover LAN addresses: {exc}") from exc
    if not addresses:
        raise NetworkAccessError("No private LAN IPv4 address found; connect to a LAN and try again.")
    return sorted(addresses)


def _tailscale_ipv4_address() -> str:
    executable = shutil.which("tailscale")
    if not executable and os.name == "nt":
        default_path = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Tailscale", "tailscale.exe")
        if os.path.isfile(default_path):
            executable = default_path
    if not executable:
        raise NetworkAccessError("Tailscale CLI not found. Install/start Tailscale, then select Tailscale mode again.")
    try:
        result = subprocess.run(
            [executable, "ip", "-4"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise NetworkAccessError(f"Could not query the Tailscale address: {exc}") from exc
    for line in result.stdout.splitlines():
        try:
            address = ipaddress.ip_address(line.strip())
        except ValueError:
            continue
        if address.version == 4 and not address.is_loopback:
            return str(address)
    raise NetworkAccessError("Tailscale did not report a usable IPv4 address.")


def resolve_bind_target(mode: str, port: int) -> BindTarget:
    if mode not in ACCESS_MODES:
        raise NetworkAccessError(f"mode must be one of: {', '.join(ACCESS_MODES)}")
    if mode == "loopback":
        return BindTarget("127.0.0.1", [f"http://127.0.0.1:{port}/"], set())
    if mode == "lan":
        addresses = _lan_ipv4_addresses()
        return BindTarget(
            "0.0.0.0",
            [f"http://{address}:{port}/" for address in addresses],
            set(addresses),
        )
    address = _tailscale_ipv4_address()
    return BindTarget(address, [f"http://{address}:{port}/"], {address})
