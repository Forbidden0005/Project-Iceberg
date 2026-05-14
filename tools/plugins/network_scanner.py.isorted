"""
network_scanner.py — Network port scanner and device discovery plugin.

Tools provided:
  scan_ports      — TCP port scan a host (common ports or custom range)
  ping_host       — ICMP ping a single host, return latency
  scan_network    — Sweep a subnet for live hosts (ping + ARP)
  trace_route     — Traceroute to a host
  dns_lookup      — Resolve hostname → IPs, or reverse IP → hostname
  arp_table       — Show local ARP cache (known devices on LAN)

Zero extra pip dependencies — uses stdlib: socket, subprocess, ipaddress,
concurrent.futures for parallel scanning.
"""

from __future__ import annotations

import concurrent.futures
import ipaddress
import socket
import subprocess
import sys
import time
from typing import Optional

# ---------------------------------------------------------------------------
# Well-known port names (common services)
# ---------------------------------------------------------------------------

_WELL_KNOWN: dict[int, str] = {
    21: "FTP",
    22: "SSH",
    23: "Telnet",
    25: "SMTP",
    53: "DNS",
    80: "HTTP",
    110: "POP3",
    135: "RPC",
    139: "NetBIOS",
    143: "IMAP",
    443: "HTTPS",
    445: "SMB",
    993: "IMAPS",
    995: "POP3S",
    1433: "MSSQL",
    1723: "PPTP",
    3306: "MySQL",
    3389: "RDP",
    5432: "PostgreSQL",
    5900: "VNC",
    6379: "Redis",
    8080: "HTTP-Alt",
    8443: "HTTPS-Alt",
    27017: "MongoDB",
}

_COMMON_PORTS = sorted(_WELL_KNOWN.keys())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tcp_probe(host: str, port: int, timeout: float = 0.5) -> bool:
    """Return True if host:port accepts a TCP connection."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def _resolve(host: str) -> str:
    """Resolve hostname to IP, return original if already an IP."""
    try:
        return socket.gethostbyname(host)
    except socket.gaierror:
        return host


def _run(args: list[str], timeout: int = 10) -> tuple[int, str]:
    try:
        r = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return -1, "[timed out]"
    except FileNotFoundError:
        return -1, f"[command not found: {args[0]}]"


# ---------------------------------------------------------------------------
# Tool: scan_ports
# ---------------------------------------------------------------------------


def scan_ports(
    host: str,
    ports: str = "common",
    timeout: float = 0.5,
    max_workers: int = 50,
) -> str:
    """
    TCP port scan a host to find open services.

    Args:
        host:        Hostname or IP to scan (e.g. '192.168.1.1', 'example.com').
        ports:       Which ports to scan:
                     'common' (default) — well-known service ports
                     'all'             — 1–65535 (slow!)
                     '1-1024'          — a range
                     '80,443,8080'     — specific ports
        timeout:     Per-port connection timeout in seconds (default 0.5).
        max_workers: Parallel threads for scanning (default 50).
    """
    ip = _resolve(host)
    if ip != host:
        host_display = f"{host} ({ip})"
    else:
        host_display = host

    # Parse ports argument
    port_list: list[int] = []
    if ports == "common":
        port_list = _COMMON_PORTS
    elif ports == "all":
        port_list = list(range(1, 65536))
    elif "-" in ports and "," not in ports:
        try:
            lo, hi = ports.split("-")
            port_list = list(range(int(lo), int(hi) + 1))
        except ValueError:
            return f"Invalid port range '{ports}'. Use '80-443', 'common', 'all', or '80,443,8080'."
    else:
        try:
            port_list = [int(p.strip()) for p in ports.split(",")]
        except ValueError:
            return f"Invalid port spec '{ports}'."

    if not port_list:
        return "No ports to scan."

    open_ports: list[tuple[int, str]] = []
    start = time.time()

    def _probe(port: int) -> Optional[tuple[int, str]]:
        if _tcp_probe(ip, port, timeout):
            svc = _WELL_KNOWN.get(port, "unknown")
            return (port, svc)
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_probe, p): p for p in port_list}
        for fut in concurrent.futures.as_completed(futures):
            result = fut.result()
            if result:
                open_ports.append(result)

    elapsed = time.time() - start
    open_ports.sort()

    lines = [
        f"Port scan: {host_display}",
        f"Scanned {len(port_list)} port(s) in {elapsed:.1f}s",
        "",
    ]

    if not open_ports:
        lines.append(f"No open ports found (timeout={timeout}s).")
        lines.append("Host may be offline, firewalled, or blocking TCP.")
    else:
        lines.append(f"{'Port':<8} {'Service':<16} {'Status'}")
        lines.append("-" * 36)
        for port, svc in open_ports:
            lines.append(f"{port:<8} {svc:<16} ✅ OPEN")
        lines.append(f"\n{len(open_ports)} open port(s) found.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: ping_host
# ---------------------------------------------------------------------------


def ping_host(host: str, count: int = 4) -> str:
    """
    Ping a host and report latency and packet loss.

    Args:
        host:  Hostname or IP address.
        count: Number of ping packets to send (default 4).
    """
    count = max(1, min(20, count))
    is_windows = sys.platform == "win32"

    if is_windows:
        args = ["ping", "-n", str(count), host]
    else:
        args = ["ping", "-c", str(count), host]

    rc, out = _run(args, timeout=count * 3 + 5)

    if rc == 0:
        icon = "✅"
    elif rc == 1:
        icon = "⛔"
    else:
        icon = "❓"

    return f"{icon} ping {host} (×{count}):\n{out}"


# ---------------------------------------------------------------------------
# Tool: scan_network
# ---------------------------------------------------------------------------


def scan_network(
    subnet: str = "",
    timeout: float = 0.5,
    max_workers: int = 50,
) -> str:
    """
    Sweep a subnet for live hosts using ICMP ping and reverse DNS.

    Args:
        subnet:      CIDR notation (e.g. '192.168.1.0/24').
                     If omitted, attempts to detect the local subnet.
        timeout:     Ping timeout per host in seconds (default 0.5).
        max_workers: Parallel threads (default 50).
    """
    # Auto-detect local subnet if not provided
    if not subnet:
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
            # Assume /24
            parts = local_ip.rsplit(".", 1)
            subnet = parts[0] + ".0/24"
        except Exception:
            return (
                "Could not auto-detect local subnet. "
                "Provide a subnet explicitly: scan_network('192.168.1.0/24')"
            )

    try:
        net = ipaddress.IPv4Network(subnet, strict=False)
    except ValueError as e:
        return f"Invalid subnet '{subnet}': {e}"

    hosts = list(net.hosts())
    if len(hosts) > 512:
        return (
            f"Subnet {subnet} has {len(hosts)} hosts — too large for a quick sweep.\n"
            "Use a /24 or smaller subnet (e.g. '10.0.0.0/24')."
        )

    is_windows = sys.platform == "win32"
    live: list[dict] = []

    def _ping_one(ip: ipaddress.IPv4Address) -> Optional[dict]:
        ip_str = str(ip)
        if is_windows:
            args = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), ip_str]
        else:
            args = ["ping", "-c", "1", "-W", str(max(1, int(timeout))), ip_str]
        rc, _ = _run(args, timeout=int(timeout) + 2)
        if rc == 0:
            # Reverse DNS
            try:
                hostname = socket.gethostbyaddr(ip_str)[0]
            except Exception:
                hostname = ""
            return {"ip": ip_str, "hostname": hostname}
        return None

    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_ping_one, ip) for ip in hosts]
        for fut in concurrent.futures.as_completed(futures):
            result = fut.result()
            if result:
                live.append(result)

    elapsed = time.time() - start
    live.sort(key=lambda x: ipaddress.IPv4Address(x["ip"]))

    lines = [
        f"Network scan: {subnet}",
        f"Scanned {len(hosts)} host(s) in {elapsed:.1f}s",
        f"Live hosts: {len(live)}",
        "",
    ]

    if not live:
        lines.append("No hosts responded to ping.")
        lines.append("(Some hosts block ICMP — they may still be online.)")
    else:
        lines.append(f"{'IP Address':<18} {'Hostname'}")
        lines.append("-" * 55)
        for h in live:
            lines.append(f"{h['ip']:<18} {h['hostname'] or '(no hostname)'}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: trace_route
# ---------------------------------------------------------------------------


def trace_route(host: str, max_hops: int = 15) -> str:
    """
    Run a traceroute to a host and show each network hop.

    Args:
        host:     Hostname or IP to trace.
        max_hops: Maximum number of hops to trace (default 15).
    """
    max_hops = max(1, min(30, max_hops))
    is_windows = sys.platform == "win32"

    if is_windows:
        args = ["tracert", "-d", "-h", str(max_hops), host]
    else:
        args = ["traceroute", "-m", str(max_hops), "-n", host]

    rc, out = _run(args, timeout=max_hops * 5 + 10)

    icon = "✅" if rc == 0 else "⚠️"
    return f"{icon} traceroute to {host} (max {max_hops} hops):\n{out}"


# ---------------------------------------------------------------------------
# Tool: dns_lookup
# ---------------------------------------------------------------------------


def dns_lookup(host: str, reverse: bool = False) -> str:
    """
    DNS lookup — resolve a hostname to IPs, or reverse-lookup an IP to hostname.

    Args:
        host:    Hostname or IP address.
        reverse: If True, do a reverse PTR lookup (IP → hostname).
    """
    lines = [f"DNS lookup: {host}"]

    if reverse:
        try:
            hostname, aliases, _ = socket.gethostbyaddr(host)
            lines.append(f"  PTR → {hostname}")
            if aliases:
                lines.append(f"  Aliases: {', '.join(aliases)}")
        except socket.herror as e:
            lines.append(f"  No PTR record: {e}")
    else:
        try:
            infos = socket.getaddrinfo(host, None)
            ips = sorted(set(info[4][0] for info in infos))
            for ip in ips:
                family = "IPv6" if ":" in ip else "IPv4"
                lines.append(f"  {family}: {ip}")
        except socket.gaierror as e:
            lines.append(f"  Resolution failed: {e}")

    # Try to get canonical name
    try:
        canon = socket.getfqdn(host)
        if canon != host:
            lines.append(f"  FQDN: {canon}")
    except Exception:
        pass

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: arp_table
# ---------------------------------------------------------------------------


def arp_table() -> str:
    """
    Show the local ARP cache — known devices on the LAN with their MAC addresses.
    """
    is_windows = sys.platform == "win32"
    args = ["arp", "-a"] if is_windows else ["arp", "-n"]
    rc, out = _run(args, timeout=5)

    if rc != 0:
        return f"[arp error] {out}"

    lines = ["Local ARP cache (known LAN devices):", ""]
    for line in out.splitlines():
        line = line.strip()
        if line:
            lines.append(f"  {line}")

    lines.append("\n(ARP cache shows recently communicated devices only.)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(registry) -> None:
    registry.register(
        "scan_ports",
        scan_ports,
        description=(
            "TCP port scan a host to find open services. "
            "ports='common' scans well-known ports; 'all' scans 1-65535; "
            "or specify a range like '1-1024' or specific ports like '80,443,8080'."
        ),
        category="web",
        args=[
            {"name": "host", "required": True, "description": "Hostname or IP to scan"},
            {
                "name": "ports",
                "required": False,
                "description": "'common' (default), 'all', '1-1024', or '80,443,8080'",
            },
            {
                "name": "timeout",
                "required": False,
                "description": "Per-port timeout in seconds (default 0.5)",
            },
            {
                "name": "max_workers",
                "required": False,
                "description": "Parallel scan threads (default 50)",
            },
        ],
    )

    registry.register(
        "ping_host",
        ping_host,
        description="Ping a hostname or IP and report latency and packet loss.",
        category="web",
        args=[
            {"name": "host", "required": True, "description": "Hostname or IP address to ping"},
            {
                "name": "count",
                "required": False,
                "description": "Number of ping packets (default 4)",
            },
        ],
    )

    registry.register(
        "scan_network",
        scan_network,
        description=(
            "Sweep a subnet for live hosts using ICMP ping. "
            "Auto-detects local /24 if no subnet given. "
            "Example: scan_network('192.168.1.0/24')"
        ),
        category="web",
        args=[
            {
                "name": "subnet",
                "required": False,
                "description": "CIDR subnet to scan (e.g. '192.168.1.0/24'). Auto-detects local subnet if omitted.",
            },
            {
                "name": "timeout",
                "required": False,
                "description": "Ping timeout per host (default 0.5s)",
            },
            {
                "name": "max_workers",
                "required": False,
                "description": "Parallel threads (default 50)",
            },
        ],
    )

    registry.register(
        "trace_route",
        trace_route,
        description="Trace the network path (hops) to a host or IP address.",
        category="web",
        args=[
            {"name": "host", "required": True, "description": "Hostname or IP to trace"},
            {
                "name": "max_hops",
                "required": False,
                "description": "Maximum hops to trace (default 15)",
            },
        ],
    )

    registry.register(
        "dns_lookup",
        dns_lookup,
        description=(
            "DNS lookup — resolve a hostname to its IP addresses, "
            "or reverse-lookup an IP to its hostname."
        ),
        category="web",
        args=[
            {"name": "host", "required": True, "description": "Hostname or IP to look up"},
            {
                "name": "reverse",
                "required": False,
                "description": "True for reverse PTR lookup (IP → hostname)",
            },
        ],
    )

    registry.register(
        "arp_table",
        arp_table,
        description="Show the local ARP cache — IP and MAC addresses of recently communicated LAN devices.",
        category="web",
        args=[],
    )
