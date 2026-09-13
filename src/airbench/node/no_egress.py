"""First-scope no-egress observation.

The first scope records explicit local no-egress checks; independently attested,
continuous machine-state observation is deferred (``P0-2``).  This module lists
established TCP connections the host currently holds and reports any whose
remote address is not loopback.  It is observation only: enforcement lives in
the absence of network paths, not in this check.
"""

from __future__ import annotations

import ipaddress
import platform
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable, Sequence


class NoEgressError(RuntimeError):
    """The no-egress observation could not be completed."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class NoEgressReport:
    backend: str
    checked: int
    external_connections: tuple[str, ...]
    observed_at: str

    @property
    def clean(self) -> bool:
        return not self.external_connections

    def to_dict(self) -> dict:
        return {
            "backend": self.backend,
            "checked": self.checked,
            "clean": self.clean,
            "external_connections": list(self.external_connections),
            "observed_at": self.observed_at,
        }


def _host(address: str) -> str:
    if address.startswith("["):
        return address[1:address.index("]")]
    return address.rsplit(":", 1)[0]


def is_loopback(address: str) -> bool:
    try:
        return ipaddress.ip_address(_host(address)).is_loopback
    except ValueError:
        return False


def external(connections: Iterable[tuple[str, str]]) -> tuple[str, ...]:
    """Return the remote endpoints whose host is not loopback."""
    return tuple(
        remote for _local, remote in connections
        if remote and not is_loopback(remote)
    )


def _list_windows() -> tuple[tuple[str, str], ...]:
    command = ["powershell", "-NoProfile", "-Command",
               "Get-NetTCPConnection -State Established | ForEach-Object { \"$($_.LocalAddress):$($_.LocalPort) $($_.RemoteAddress):$($_.RemotePort)\" }"]
    output = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False).stdout
    pairs = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) == 2:
            pairs.append((parts[0], parts[1]))
    return tuple(pairs)


def _list_linux() -> tuple[tuple[str, str], ...]:
    output = subprocess.run(["ss", "-tn", "state", "established"], capture_output=True, text=True, timeout=30, check=False).stdout
    pairs = []
    for line in output.splitlines()[1:]:
        parts = re.split(r"\s+", line.strip())
        if len(parts) >= 5:
            pairs.append((parts[3], parts[4]))
    return tuple(pairs)


def list_tcp_connections() -> tuple[tuple[str, str], ...]:
    system = platform.system()
    if system == "Windows":
        return _list_windows()
    return _list_linux()


def observe_no_egress(
    *,
    lister: Callable[[], Sequence[tuple[str, str]]] | None = None,
) -> NoEgressReport:
    active = lister or list_tcp_connections
    try:
        connections = tuple(active())
    except (OSError, subprocess.SubprocessError) as exc:
        raise NoEgressError("observation_failed", "the no-egress observation could not list connections") from exc
    return NoEgressReport(
        backend="windows-netstat" if platform.system() == "Windows" else "linux-ss",
        checked=len(connections),
        external_connections=external(connections),
        observed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


__all__ = ["NoEgressError", "NoEgressReport", "external", "is_loopback", "list_tcp_connections", "observe_no_egress"]
