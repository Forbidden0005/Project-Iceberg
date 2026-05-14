"""
Network connection tracker for Project Iceberg.

Shows what processes are talking to the network, where they're connecting,
and flags anything phoning home unexpectedly.

Requires: pip install psutil
"""

import ipaddress
import socket
from typing import Optional

try:
    import psutil

    _PSUTIL = True
except ImportError:
    _PSUTIL = False

# ---------------------------------------------------------------------------
# Private IP ranges — connections to these are local/internal
# ---------------------------------------------------------------------------

_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 ULA
]


def _is_private(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in _PRIVATE_NETS)
    except ValueError:
        return False


def _resolve_hostname(ip: str, timeout: float = 0.5) -> str:
    """Try a reverse DNS lookup; return the IP if it fails."""
    try:
        socket.setdefaulttimeout(timeout)
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ip


def _proc_name(pid: Optional[int]) -> str:
    if pid is None:
        return "(system)"
    try:
        return psutil.Process(pid).name()
    except Exception:
        return f"PID {pid}"


def _format_conn(c, resolve: bool = False) -> str:
    laddr = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "*"
    if c.raddr:
        rip = c.raddr.ip
        rhost = _resolve_hostname(rip) if resolve else rip
        raddr = f"{rhost}:{c.raddr.port}"
        external_tag = "" if _is_private(rip) else "  [EXTERNAL]"
    else:
        raddr = "*"
        external_tag = ""
    proc = _proc_name(c.pid)
    return f"  {proc:<25} {laddr:<25} -> {raddr}{external_tag}  [{c.status or 'n/a'}]"


# ---------------------------------------------------------------------------
# Public tools
# ---------------------------------------------------------------------------


def list_connections(
    state: str = "all",
    process_name: str = "",
    resolve_dns: bool = False,
) -> str:
    """
    List all active network connections on this machine.

    Args:
        state:        Filter by connection state: "all" (default), "established",
                      "listen", "time_wait", "close_wait".
        process_name: Only show connections from processes matching this name.
        resolve_dns:  Try reverse-DNS lookup on remote IPs (slower, default False).

    Returns:
        Table of connections: process name, local addr, remote addr, state.
        External (internet) connections are labelled [EXTERNAL].
    """
    if not _PSUTIL:
        return "[error] psutil not installed — run: pip install psutil"

    try:
        conns = psutil.net_connections(kind="inet")
    except psutil.AccessDenied:
        return "[error] Access denied — run as administrator to see all connections"

    state_lower = state.lower()
    filtered = []
    for c in conns:
        if state_lower != "all" and (c.status or "").lower() != state_lower:
            continue
        if process_name:
            pname = _proc_name(c.pid).lower()
            if process_name.lower() not in pname:
                continue
        filtered.append(c)

    if not filtered:
        return f"No connections found (state={state}, process={process_name or 'any'})"

    lines = [
        f"Network connections — {len(filtered)} found  "
        f"(filter: state={state}, process={process_name or 'any'})\n",
        f"  {'Process':<25} {'Local':<25}   {'Remote':<35} State",
        f"  {'-'*24} {'-'*24}   {'-'*34} -----",
    ]
    for c in sorted(filtered, key=lambda x: (_proc_name(x.pid), x.status or "")):
        lines.append(_format_conn(c, resolve=resolve_dns))

    return "\n".join(lines)


def find_external_connections(resolve_dns: bool = True) -> str:
    """
    Show only connections that reach outside your local network (internet-bound).

    This is the "what's phoning home?" tool — it shows every process with an
    active connection to an external (non-private) IP address.

    Args:
        resolve_dns: Try to resolve remote IPs to hostnames (default True).

    Returns:
        List of processes with external connections, grouped by process.
        Flags any process that has no associated executable path.
    """
    if not _PSUTIL:
        return "[error] psutil not installed — run: pip install psutil"

    try:
        conns = psutil.net_connections(kind="inet")
    except psutil.AccessDenied:
        return "[error] Access denied — run as administrator"

    external: dict[str, list] = {}
    for c in conns:
        if not c.raddr:
            continue
        rip = c.raddr.ip
        if _is_private(rip):
            continue
        pname = _proc_name(c.pid)
        external.setdefault(pname, []).append(c)

    if not external:
        return "✓ No external (internet-bound) connections found."

    lines = [f"⚠  External connections detected — {len(external)} process(es)\n"]
    for pname, pconns in sorted(external.items()):
        # Try to get exe path for trust assessment
        exe = ""
        if pconns[0].pid:
            try:
                exe = psutil.Process(pconns[0].pid).exe()
            except Exception:
                pass
        trust = "" if exe else "  ⚠ NO EXE PATH"
        lines.append(f"  {pname} (PID {pconns[0].pid}){trust}")
        if exe:
            lines.append(f"    Exe: {exe}")
        for c in pconns[:6]:
            rip = c.raddr.ip
            rhost = _resolve_hostname(rip) if resolve_dns else rip
            lines.append(f"    → {rhost}:{c.raddr.port}  [{c.status or 'n/a'}]")
        if len(pconns) > 6:
            lines.append(f"    ... and {len(pconns)-6} more connections")
        lines.append("")

    return "\n".join(lines)


def connections_by_process(pid_or_name: str, resolve_dns: bool = False) -> str:
    """
    Show all network connections for a specific process.

    Args:
        pid_or_name: PID number or process name (e.g. "chrome.exe").
        resolve_dns: Resolve remote IPs to hostnames (default False).

    Returns:
        All connections for that process with local/remote addresses and state.
    """
    if not _PSUTIL:
        return "[error] psutil not installed — run: pip install psutil"

    pid_or_name = str(pid_or_name).strip()
    targets: list[int] = []

    if pid_or_name.isdigit():
        targets = [int(pid_or_name)]
    else:
        for proc in psutil.process_iter():
            try:
                if pid_or_name.lower() in proc.name().lower():
                    targets.append(proc.pid)
            except Exception:
                continue

    if not targets:
        return f"No process found matching: {pid_or_name}"

    try:
        all_conns = psutil.net_connections(kind="inet")
    except psutil.AccessDenied:
        return "[error] Access denied — run as administrator"

    relevant = [c for c in all_conns if c.pid in targets]
    if not relevant:
        return f"No network connections found for: {pid_or_name}"

    lines = [f"Connections for {pid_or_name} — {len(relevant)} found\n"]
    for c in relevant:
        laddr = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "*"
        if c.raddr:
            rip = c.raddr.ip
            rhost = _resolve_hostname(rip) if resolve_dns else rip
            raddr = f"{rhost}:{c.raddr.port}"
            ext = "  [EXTERNAL]" if not _is_private(rip) else ""
        else:
            raddr = "(listening)"
            ext = ""
        lines.append(f"  {laddr:<25} -> {raddr}{ext}  [{c.status or 'n/a'}]")

    return "\n".join(lines)


def network_interface_stats() -> str:
    """
    Show all network interfaces with their current throughput and addresses.

    Returns:
        Per-interface stats: bytes sent/received, packets, errors, IP addresses.
    """
    if not _PSUTIL:
        return "[error] psutil not installed — run: pip install psutil"

    io = psutil.net_io_counters(pernic=True)
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    lines = ["Network interfaces:\n"]
    for name in sorted(io.keys()):
        counters = io[name]
        iface_stats = stats.get(name)
        is_up = iface_stats.isup if iface_stats else False
        speed = (
            f"{iface_stats.speed} Mbps" if iface_stats and iface_stats.speed else "unknown speed"
        )

        lines.append(f"  {name}  ({'UP' if is_up else 'DOWN'}  {speed})")
        # Addresses
        for addr in addrs.get(name, []):
            if addr.family.name in ("AF_INET", "AF_INET6"):
                lines.append(f"    IP: {addr.address}")

        sent_mb = round(counters.bytes_sent / 1024 / 1024, 1)
        recv_mb = round(counters.bytes_recv / 1024 / 1024, 1)
        lines.append(
            f"    Sent: {sent_mb} MB  |  Recv: {recv_mb} MB  |  "
            f"Errors: {counters.errin + counters.errout}  |  "
            f"Drops: {counters.dropin + counters.dropout}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------


def register(registry) -> None:
    registry.register(
        "list_connections",
        list_connections,
        description="List all active network connections. Filter by state (established/listen) or process name. Flags external (internet) connections.",
        category="system",
        args=[
            {
                "name": "state",
                "required": False,
                "description": "'all', 'established', 'listen', 'time_wait' (default: all)",
            },
            {
                "name": "process_name",
                "required": False,
                "description": "Filter to a specific process",
            },
            {
                "name": "resolve_dns",
                "required": False,
                "description": "Reverse-lookup remote IPs (slower, default False)",
            },
        ],
    )
    registry.register(
        "find_external_connections",
        find_external_connections,
        description="Show what processes are connecting to the internet (phoning home). Groups by process, flags missing exe paths.",
        category="system",
        args=[
            {
                "name": "resolve_dns",
                "required": False,
                "description": "Resolve remote IPs to hostnames (default True)",
            },
        ],
    )
    registry.register(
        "connections_by_process",
        connections_by_process,
        description="Show all network connections for a specific process by PID or name.",
        category="system",
        args=[
            {
                "name": "pid_or_name",
                "required": True,
                "description": "PID or process name (e.g. 'firefox.exe')",
            },
            {
                "name": "resolve_dns",
                "required": False,
                "description": "Resolve remote IPs (default False)",
            },
        ],
    )
    registry.register(
        "network_interface_stats",
        network_interface_stats,
        description="Show all network interfaces with IP addresses, throughput (bytes sent/received), errors, and whether each is up or down.",
        category="system",
        args=[],
    )
