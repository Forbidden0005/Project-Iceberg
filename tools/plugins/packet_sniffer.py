"""
packet_sniffer.py — Live packet capture and traffic analysis plugin.

Tier 4 dependencies:
  pip install scapy
  Npcap driver: https://npcap.com/#download  (free, Windows packet capture driver)

Both are required. scapy alone won't capture on Windows without Npcap installed.
This plugin gracefully explains the install steps if either is missing.

Tools provided:
  list_interfaces          — Show available network interfaces for capture
  capture_packets          — Live capture for N seconds, show protocol summary
  analyze_traffic          — Top talkers, protocols, ports from a live capture
  detect_suspicious_traffic — Flag unusual patterns: port scans, DNS tunneling,
                              beaconing, large uploads, cleartext credentials
  capture_to_file          — Write packets to a .pcap file for Wireshark
  read_pcap                — Analyze an existing .pcap file
"""

from __future__ import annotations

import collections
import ipaddress
import os
import time
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Dependency guard
# ---------------------------------------------------------------------------

_SCAPY_AVAILABLE = False
_NPCAP_AVAILABLE = False

try:
    # Suppress scapy's verbose startup warnings
    import logging

    logging.getLogger("scapy").setLevel(logging.ERROR)
    import scapy.all as sc

    _SCAPY_AVAILABLE = True

    # Test if Npcap/WinPcap driver is available
    try:
        ifaces = sc.get_if_list()
        _NPCAP_AVAILABLE = len(ifaces) > 0
    except Exception:
        _NPCAP_AVAILABLE = False

except ImportError:
    pass

_INSTALL_MSG = """Packet sniffer requires Tier 4 dependencies:

  1. Install scapy:
       pip install scapy

  2. Install Npcap driver (Windows packet capture):
       Download from: https://npcap.com/#download
       Run the installer — choose "WinPcap API-compatible Mode" during install.
       Restart may be required.

After both are installed, restart Project Iceberg and try again.
"""

_NPCAP_ONLY_MSG = """scapy is installed but Npcap driver is not detected.

Install Npcap:
  Download: https://npcap.com/#download
  Run installer → enable "WinPcap API-compatible Mode"
  Restart your computer if prompted.
"""


def _check_deps() -> Optional[str]:
    """Return error message if deps missing, None if all good."""
    if not _SCAPY_AVAILABLE:
        return _INSTALL_MSG
    if not _NPCAP_AVAILABLE:
        return _NPCAP_ONLY_MSG
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _is_private(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return False


def _protocol_name(pkt) -> str:
    """Identify the highest-layer protocol name."""
    if not _SCAPY_AVAILABLE:
        return "unknown"
    if pkt.haslayer(sc.DNS):
        return "DNS"
    if pkt.haslayer(sc.DNSQR):
        return "DNS"
    if pkt.haslayer(sc.HTTP):
        return "HTTP"
    if pkt.haslayer(sc.TCP):
        dport = pkt[sc.TCP].dport
        sport = pkt[sc.TCP].sport
        port = min(dport, sport)
        known = {
            80: "HTTP",
            443: "HTTPS",
            22: "SSH",
            21: "FTP",
            25: "SMTP",
            110: "POP3",
            143: "IMAP",
            3389: "RDP",
            445: "SMB",
            139: "NetBIOS",
            3306: "MySQL",
            5432: "PostgreSQL",
            6379: "Redis",
            27017: "MongoDB",
        }
        return known.get(port, f"TCP:{port}")
    if pkt.haslayer(sc.UDP):
        dport = pkt[sc.UDP].dport
        sport = pkt[sc.UDP].sport
        port = min(dport, sport)
        known = {53: "DNS", 67: "DHCP", 68: "DHCP", 123: "NTP", 161: "SNMP"}
        return known.get(port, f"UDP:{port}")
    if pkt.haslayer(sc.ICMP):
        return "ICMP"
    if pkt.haslayer(sc.ARP):
        return "ARP"
    return "Other"


# ---------------------------------------------------------------------------
# Tool: list_interfaces
# ---------------------------------------------------------------------------


def list_interfaces() -> str:
    """
    List available network interfaces for packet capture.
    """
    err = _check_deps()
    if err:
        return err

    try:
        ifaces = sc.get_if_list()
        iface_details = []

        for iface in ifaces:
            try:
                ip = sc.get_if_addr(iface)
            except Exception:
                ip = "N/A"
            iface_details.append((iface, ip))

        if not iface_details:
            return "No network interfaces found."

        lines = [
            f"Available capture interfaces ({len(iface_details)}):",
            f"{'Interface':<45} {'IP Address'}",
            "-" * 70,
        ]
        for iface, ip in iface_details:
            lines.append(f"{iface[:44]:<45} {ip}")

        lines.append("\nUse the interface name with capture_packets() or capture_to_file().")
        return "\n".join(lines)
    except Exception as e:
        return f"[list_interfaces error] {e}"


# ---------------------------------------------------------------------------
# Tool: capture_packets
# ---------------------------------------------------------------------------


def capture_packets(
    interface: str = "",
    duration: int = 10,
    packet_filter: str = "",
    max_packets: int = 500,
    show_raw: bool = False,
) -> str:
    """
    Live packet capture — sniff traffic and display a protocol summary.

    Args:
        interface:     Network interface to capture on (use list_interfaces to find name).
                       Omit to use the default interface.
        duration:      Capture duration in seconds (default 10, max 60).
        packet_filter: BPF filter string (e.g. 'tcp port 80', 'host 1.2.3.4', 'udp').
                       Leave empty to capture all traffic.
        max_packets:   Stop after this many packets even if duration not reached (default 500).
        show_raw:      Show individual packet summaries (default False = stats only).
    """
    err = _check_deps()
    if err:
        return err

    duration = max(1, min(60, duration))
    max_packets = max(1, min(2000, max_packets))

    kwargs: dict[str, Any] = {
        "timeout": duration,
        "count": max_packets,
        "store": True,
    }
    if interface:
        kwargs["iface"] = interface
    if packet_filter:
        kwargs["filter"] = packet_filter

    try:
        start = time.time()
        packets = sc.sniff(**kwargs)
        elapsed = time.time() - start
    except PermissionError:
        return "❌ Permission denied. Run Project Iceberg as Administrator to capture packets."
    except Exception as e:
        return f"[capture error] {e}"

    if not packets:
        return (
            f"No packets captured in {elapsed:.1f}s on "
            f"{'default interface' if not interface else interface}.\n"
            "Check the interface name (list_interfaces) and filter string."
        )

    # Aggregate stats
    proto_counts: dict[str, int] = collections.defaultdict(int)
    src_counts: dict[str, int] = collections.defaultdict(int)
    dst_counts: dict[str, int] = collections.defaultdict(int)
    total_bytes = 0
    raw_lines: list[str] = []

    for pkt in packets:
        proto = _protocol_name(pkt)
        proto_counts[proto] += 1
        pkt_len = len(pkt)
        total_bytes += pkt_len

        # IP layer stats
        if pkt.haslayer(sc.IP):
            src_counts[pkt[sc.IP].src] += 1
            dst_counts[pkt[sc.IP].dst] += 1

        if show_raw:
            raw_lines.append(f"  {pkt.summary()[:100]}")

    lines = [
        f"Capture summary: {len(packets)} packets in {elapsed:.1f}s  "
        f"({_fmt_bytes(total_bytes)} total)",
        f"Interface: {interface or 'default'}",
        f"Filter:    {packet_filter or 'none'}",
        "",
        "Protocol breakdown:",
    ]
    for proto, count in sorted(proto_counts.items(), key=lambda x: -x[1]):
        pct = count / len(packets) * 100
        bar = "█" * int(pct / 5)
        lines.append(f"  {proto:<15} {count:>5} pkts  ({pct:5.1f}%)  {bar}")

    lines.append("\nTop source IPs:")
    for ip, count in sorted(src_counts.items(), key=lambda x: -x[1])[:8]:
        ext = "" if _is_private(ip) else "  [EXTERNAL]"
        lines.append(f"  {ip:<18} {count:>5} pkts{ext}")

    lines.append("\nTop destination IPs:")
    for ip, count in sorted(dst_counts.items(), key=lambda x: -x[1])[:8]:
        ext = "" if _is_private(ip) else "  [EXTERNAL]"
        lines.append(f"  {ip:<18} {count:>5} pkts{ext}")

    if show_raw and raw_lines:
        lines.append("\nPacket list (first 50):")
        lines.extend(raw_lines[:50])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: analyze_traffic
# ---------------------------------------------------------------------------


def analyze_traffic(
    interface: str = "",
    duration: int = 15,
    packet_filter: str = "",
) -> str:
    """
    Capture traffic and produce a detailed analysis: top talkers, ports,
    protocols, external connections, and data volume per host.

    Args:
        interface:     Network interface (use list_interfaces). Default = auto.
        duration:      Capture duration in seconds (default 15, max 60).
        packet_filter: BPF filter (e.g. 'tcp', 'not arp'). Default = all.
    """
    err = _check_deps()
    if err:
        return err

    duration = max(1, min(60, duration))
    kwargs: dict[str, Any] = {"timeout": duration, "count": 2000, "store": True}
    if interface:
        kwargs["iface"] = interface
    if packet_filter:
        kwargs["filter"] = packet_filter

    try:
        packets = sc.sniff(**kwargs)
    except Exception as e:
        return f"[analyze_traffic error] {e}"

    if not packets:
        return "No packets captured. Check interface and filter."

    # Per-host stats
    host_stats: dict[str, dict] = collections.defaultdict(
        lambda: {"sent": 0, "recv": 0, "bytes_out": 0, "bytes_in": 0, "protocols": set()}
    )
    port_counts: dict[int, int] = collections.defaultdict(int)
    external_conns: list[str] = []
    total_bytes = 0

    local_ip = ""
    try:
        if interface:
            local_ip = sc.get_if_addr(interface)
    except Exception:
        pass

    for pkt in packets:
        size = len(pkt)
        total_bytes += size

        if not pkt.haslayer(sc.IP):
            continue

        src = pkt[sc.IP].src
        dst = pkt[sc.IP].dst
        proto = _protocol_name(pkt)

        host_stats[src]["sent"] += 1
        host_stats[src]["bytes_out"] += size
        host_stats[src]["protocols"].add(proto)
        host_stats[dst]["recv"] += 1
        host_stats[dst]["bytes_in"] += size

        # Port tallying
        for layer in [sc.TCP, sc.UDP]:
            if pkt.haslayer(layer):
                port_counts[pkt[layer].dport] += 1
                break

        # External connection detection
        if not _is_private(dst) and _is_private(src):
            external_conns.append(f"{src} → {dst}  [{proto}]")
        elif not _is_private(src) and _is_private(dst):
            external_conns.append(f"{src} [EXTERNAL] → {dst}  [{proto}]")

    lines = [
        f"Traffic analysis: {len(packets)} packets, {_fmt_bytes(total_bytes)}, {duration}s",
        "=" * 65,
        "",
        "Top Talkers (by packets sent):",
        f"  {'IP Address':<18} {'Sent':>7} {'Recv':>7} {'Out':>10} {'In':>10}  Protocols",
        "  " + "-" * 75,
    ]
    for ip, stats in sorted(host_stats.items(), key=lambda x: -x[1]["sent"])[:12]:
        ext = " [EXT]" if not _is_private(ip) else ""
        protos = ", ".join(sorted(stats["protocols"]))[:30]
        lines.append(
            f"  {ip+ext:<24} {stats['sent']:>7} {stats['recv']:>7} "
            f"{_fmt_bytes(stats['bytes_out']):>10} {_fmt_bytes(stats['bytes_in']):>10}  {protos}"
        )

    lines.append("\nTop Destination Ports:")
    for port, count in sorted(port_counts.items(), key=lambda x: -x[1])[:15]:
        from tools.plugins.network_scanner import _WELL_KNOWN  # noqa

        svc = _WELL_KNOWN.get(port, "")
        lines.append(f"  {port:<6} {svc:<14} {count} packets")

    lines.append(f"\nExternal Connections ({len(set(external_conns))} unique):")
    for conn in sorted(set(external_conns))[:20]:
        lines.append(f"  {conn}")
    if len(external_conns) > 20:
        lines.append(f"  … and {len(external_conns)-20} more")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: detect_suspicious_traffic
# ---------------------------------------------------------------------------


def detect_suspicious_traffic(
    interface: str = "",
    duration: int = 30,
) -> str:
    """
    Monitor traffic for suspicious patterns:
      - Port scan behavior (one src hitting many ports)
      - Beaconing (regular timed connections to the same external host)
      - DNS tunneling (unusually large DNS queries)
      - Cleartext credential patterns (FTP, Telnet, HTTP Basic Auth)
      - Large outbound data transfers to external IPs
      - Connections to known bad ports (RAT common ports)

    Args:
        interface: Network interface (use list_interfaces). Default = auto.
        duration:  Monitoring duration in seconds (default 30, max 120).
    """
    err = _check_deps()
    if err:
        return err

    duration = max(5, min(120, duration))
    kwargs: dict[str, Any] = {"timeout": duration, "count": 5000, "store": True}
    if interface:
        kwargs["iface"] = interface

    # Known suspicious ports (common RAT/C2 ports)
    _SUSPICIOUS_PORTS = {
        1080: "SOCKS proxy",
        4444: "Metasploit default",
        5555: "Android ADB",
        6666: "Common malware",
        6667: "IRC (C2)",
        6668: "IRC",
        6669: "IRC",
        7777: "Common RAT",
        8888: "Jupyter/alt-HTTP",
        9001: "Tor",
        9050: "Tor SOCKS",
        31337: "Elite backdoor",
    }

    try:
        packets = sc.sniff(**kwargs)
    except Exception as e:
        return f"[detect_suspicious_traffic error] {e}"

    if not packets:
        return "No packets captured for analysis."

    findings: list[str] = []

    # --- Port scan detection ---
    # src IP → set of destination ports
    src_ports: dict[str, set] = collections.defaultdict(set)
    for pkt in packets:
        if pkt.haslayer(sc.IP) and pkt.haslayer(sc.TCP):
            if pkt[sc.TCP].flags == 2:  # SYN flag only
                src_ports[pkt[sc.IP].src].add(pkt[sc.TCP].dport)

    for src, ports in src_ports.items():
        if len(ports) > 20:
            findings.append(
                f"🔴 PORT SCAN: {src} probed {len(ports)} ports " f"(e.g. {sorted(ports)[:8]}…)"
            )

    # --- Suspicious port connections ---
    susp_connections: list[str] = []
    for pkt in packets:
        if pkt.haslayer(sc.IP) and (pkt.haslayer(sc.TCP) or pkt.haslayer(sc.UDP)):
            layer = sc.TCP if pkt.haslayer(sc.TCP) else sc.UDP
            dport = pkt[layer].dport
            if dport in _SUSPICIOUS_PORTS:
                conn = f"{pkt[sc.IP].src} → {pkt[sc.IP].dst}:{dport} ({_SUSPICIOUS_PORTS[dport]})"
                susp_connections.append(conn)

    if susp_connections:
        for conn in set(susp_connections[:10]):
            findings.append(f"⚠️  SUSPICIOUS PORT: {conn}")

    # --- DNS tunneling detection ---
    # Large DNS query names (> 50 chars) suggest data encoding in hostnames
    for pkt in packets:
        if pkt.haslayer(sc.DNSQR):
            qname = str(pkt[sc.DNSQR].qname)
            if len(qname) > 50:
                findings.append(
                    f"⚠️  DNS TUNNEL SUSPECT: Long DNS query ({len(qname)} chars): "
                    f"{qname[:80]}…"
                )

    # --- Cleartext credential protocols ---
    cleartext_protos: set[str] = set()
    for pkt in packets:
        if pkt.haslayer(sc.IP) and pkt.haslayer(sc.TCP):
            dport = pkt[sc.TCP].dport
            src = pkt[sc.IP].src
            if dport == 21:
                cleartext_protos.add(f"FTP (port 21) from {src}")
            elif dport == 23:
                cleartext_protos.add(f"Telnet (port 23) from {src}")
            # HTTP Basic Auth detection (look for 'Authorization: Basic')
            if pkt.haslayer(sc.Raw):
                payload = bytes(pkt[sc.Raw]).decode("utf-8", errors="ignore")
                if "Authorization: Basic" in payload:
                    cleartext_protos.add(f"HTTP Basic Auth from {src}")
                if "PASS " in payload[:10] and dport == 21:
                    cleartext_protos.add(f"FTP password in cleartext from {src}")

    for proto_event in cleartext_protos:
        findings.append(f"🔴 CLEARTEXT CREDENTIALS: {proto_event}")

    # --- Large outbound transfers ---
    outbound_bytes: dict[str, int] = collections.defaultdict(int)
    for pkt in packets:
        if pkt.haslayer(sc.IP):
            src = pkt[sc.IP].src
            dst = pkt[sc.IP].dst
            if _is_private(src) and not _is_private(dst):
                outbound_bytes[f"{src}→{dst}"] += len(pkt)

    for flow, size in outbound_bytes.items():
        if size > 5 * 1024 * 1024:  # > 5 MB to a single external host
            findings.append(f"⚠️  LARGE OUTBOUND: {flow}  {_fmt_bytes(size)} sent to external host")

    # --- Beaconing detection ---
    # Same src→dst pair appearing at regular intervals
    conn_times: dict[str, list[float]] = collections.defaultdict(list)
    for pkt in packets:
        if pkt.haslayer(sc.IP) and pkt.haslayer(sc.TCP):
            src = pkt[sc.IP].src
            dst = pkt[sc.IP].dst
            if _is_private(src) and not _is_private(dst):
                conn_times[f"{src}→{dst}"].append(float(pkt.time))

    for flow, times in conn_times.items():
        if len(times) >= 5:
            times.sort()
            intervals = [times[i + 1] - times[i] for i in range(len(times) - 1)]
            avg = sum(intervals) / len(intervals)
            variance = sum((x - avg) ** 2 for x in intervals) / len(intervals)
            if avg > 1.0 and variance < (avg * 0.2) ** 2:
                findings.append(
                    f"⚠️  BEACONING SUSPECT: {flow}  "
                    f"~every {avg:.1f}s ({len(times)} connections, low variance)"
                )

    # --- Report ---
    lines = [
        f"Suspicious traffic analysis: {len(packets)} packets over {duration}s",
        "=" * 60,
    ]

    if not findings:
        lines.append(
            "\n✅ No suspicious patterns detected.\n"
            "   Traffic appears normal for the monitoring period."
        )
    else:
        lines.append(f"\n🚨 {len(findings)} suspicious pattern(s) found:\n")
        for f in findings:
            lines.append(f"  {f}")

    lines.append(
        "\nNote: These are heuristic detections — verify before taking action.\n"
        "False positives are possible, especially in high-traffic environments."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: capture_to_file
# ---------------------------------------------------------------------------


def capture_to_file(
    output_path: str,
    interface: str = "",
    duration: int = 30,
    packet_filter: str = "",
    max_packets: int = 10000,
) -> str:
    """
    Capture packets and write them to a .pcap file for analysis in Wireshark.

    Args:
        output_path:   Where to save the .pcap file (e.g. 'C:\\\\capture.pcap').
        interface:     Network interface (use list_interfaces). Default = auto.
        duration:      Capture duration in seconds (default 30, max 300).
        packet_filter: BPF filter (e.g. 'tcp port 443'). Default = all.
        max_packets:   Stop after this many packets (default 10000).
    """
    err = _check_deps()
    if err:
        return err

    duration = max(1, min(300, duration))
    kwargs: dict[str, Any] = {
        "timeout": duration,
        "count": max_packets,
        "store": True,
    }
    if interface:
        kwargs["iface"] = interface
    if packet_filter:
        kwargs["filter"] = packet_filter

    try:
        start = time.time()
        packets = sc.sniff(**kwargs)
        elapsed = time.time() - start
    except PermissionError:
        return "❌ Run as Administrator to capture packets."
    except Exception as e:
        return f"[capture_to_file error] {e}"

    if not packets:
        return f"No packets captured in {elapsed:.1f}s."

    try:
        sc.wrpcap(output_path, packets)
    except Exception as e:
        return f"❌ Failed to write pcap to '{output_path}': {e}"

    size = os.path.getsize(output_path)
    return (
        f"✅ Captured {len(packets)} packets in {elapsed:.1f}s\n"
        f"   Saved to: {output_path}  ({_fmt_bytes(size)})\n"
        f"   Open with Wireshark for detailed analysis.\n"
        f"   Or use read_pcap('{output_path}') to analyze here."
    )


# ---------------------------------------------------------------------------
# Tool: read_pcap
# ---------------------------------------------------------------------------


def read_pcap(pcap_path: str) -> str:
    """
    Read and analyze an existing .pcap file.

    Args:
        pcap_path: Path to the .pcap file to analyze.
    """
    err = _check_deps()
    if err:
        return err

    if not os.path.exists(pcap_path):
        return f"File not found: '{pcap_path}'"

    try:
        packets = sc.rdpcap(pcap_path)
    except Exception as e:
        return f"[read_pcap error] {e}"

    if not packets:
        return f"No packets found in '{pcap_path}'."

    proto_counts: dict[str, int] = collections.defaultdict(int)
    src_counts: dict[str, int] = collections.defaultdict(int)
    total_bytes = 0

    for pkt in packets:
        proto_counts[_protocol_name(pkt)] += 1
        total_bytes += len(pkt)
        if pkt.haslayer(sc.IP):
            src_counts[pkt[sc.IP].src] += 1

    file_size = os.path.getsize(pcap_path)
    lines = [
        f"pcap analysis: {pcap_path}",
        f"  File size:   {_fmt_bytes(file_size)}",
        f"  Packets:     {len(packets)}",
        f"  Data volume: {_fmt_bytes(total_bytes)}",
        "",
        "Protocol breakdown:",
    ]
    for proto, count in sorted(proto_counts.items(), key=lambda x: -x[1]):
        pct = count / len(packets) * 100
        lines.append(f"  {proto:<15} {count:>6} pkts  ({pct:5.1f}%)")

    lines.append("\nTop source IPs:")
    for ip, count in sorted(src_counts.items(), key=lambda x: -x[1])[:10]:
        ext = "  [EXTERNAL]" if not _is_private(ip) else ""
        lines.append(f"  {ip:<18} {count:>6} pkts{ext}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(registry) -> None:
    registry.register(
        "list_interfaces",
        list_interfaces,
        description=(
            "List available network interfaces for packet capture. "
            "Requires scapy + Npcap. Use the interface name with capture_packets()."
        ),
        category="web",
        args=[],
    )

    registry.register(
        "capture_packets",
        capture_packets,
        description=(
            "Live packet capture — sniff network traffic and show protocol breakdown, "
            "top talkers, and connection summary. Requires scapy + Npcap + admin rights."
        ),
        category="web",
        args=[
            {
                "name": "interface",
                "required": False,
                "description": "Interface name from list_interfaces. Default = auto.",
            },
            {
                "name": "duration",
                "required": False,
                "description": "Capture duration in seconds (default 10, max 60)",
            },
            {
                "name": "packet_filter",
                "required": False,
                "description": "BPF filter string (e.g. 'tcp port 80', 'host 1.2.3.4')",
            },
            {
                "name": "max_packets",
                "required": False,
                "description": "Stop after N packets (default 500)",
            },
            {
                "name": "show_raw",
                "required": False,
                "description": "Show individual packet summaries (default False)",
            },
        ],
    )

    registry.register(
        "analyze_traffic",
        analyze_traffic,
        description=(
            "Deep traffic analysis: top talkers, port distribution, external connections, "
            "and per-host byte counts. Requires scapy + Npcap + admin rights."
        ),
        category="web",
        args=[
            {
                "name": "interface",
                "required": False,
                "description": "Interface name from list_interfaces",
            },
            {
                "name": "duration",
                "required": False,
                "description": "Capture duration in seconds (default 15)",
            },
            {"name": "packet_filter", "required": False, "description": "BPF filter string"},
        ],
    )

    registry.register(
        "detect_suspicious_traffic",
        detect_suspicious_traffic,
        description=(
            "Monitor network traffic for suspicious patterns: port scans, beaconing, "
            "DNS tunneling, cleartext credentials, large outbound transfers, and "
            "connections to known RAT/C2 ports."
        ),
        category="web",
        args=[
            {
                "name": "interface",
                "required": False,
                "description": "Interface name from list_interfaces",
            },
            {
                "name": "duration",
                "required": False,
                "description": "Monitoring duration in seconds (default 30, max 120)",
            },
        ],
    )

    registry.register(
        "capture_to_file",
        capture_to_file,
        description=(
            "Capture packets and save to a .pcap file for analysis in Wireshark. "
            "Use read_pcap() to analyze .pcap files in the assistant."
        ),
        category="web",
        args=[
            {
                "name": "output_path",
                "required": True,
                "description": "Path to save .pcap file (e.g. 'C:\\\\capture.pcap')",
            },
            {
                "name": "interface",
                "required": False,
                "description": "Interface name from list_interfaces",
            },
            {
                "name": "duration",
                "required": False,
                "description": "Capture duration in seconds (default 30, max 300)",
            },
            {"name": "packet_filter", "required": False, "description": "BPF filter string"},
            {
                "name": "max_packets",
                "required": False,
                "description": "Stop after N packets (default 10000)",
            },
        ],
    )

    registry.register(
        "read_pcap",
        read_pcap,
        description="Read and analyze an existing .pcap file. Shows protocol breakdown and top talkers.",
        category="web",
        args=[
            {
                "name": "pcap_path",
                "required": True,
                "description": "Path to the .pcap file to analyze",
            },
        ],
    )
