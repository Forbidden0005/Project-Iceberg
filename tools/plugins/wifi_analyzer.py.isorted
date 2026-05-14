"""
wifi_analyzer.py — WiFi network scanner and analyzer plugin.

Primary path: netsh wlan (built into Windows — always available, no pip needed).
Enhanced path: scapy for raw 802.11 beacon frame analysis (requires Npcap + scapy).

Tools provided:
  scan_wifi_networks   — All visible WiFi SSIDs with signal, security, channel
  wifi_connection_info — Details on the current WiFi connection
  wifi_password_list   — Saved WiFi profile passwords (requires admin)
  wifi_diagnostics     — Run Windows WiFi diagnostics
  wifi_signal_history  — Poll signal strength over time (live graph)
  wifi_disconnect      — Disconnect from current network
  wifi_connect         — Connect to a saved WiFi profile
  forget_wifi_network  — Delete a saved WiFi profile
"""

from __future__ import annotations

import re
import subprocess
import time

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _netsh(*args: str, timeout: int = 15) -> tuple[int, str]:
    """Run netsh and return (returncode, combined output)."""
    try:
        r = subprocess.run(
            ["netsh"] + list(args),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return -1, "[netsh timed out]"
    except FileNotFoundError:
        return -1, "[netsh not found — this tool requires Windows]"


def _signal_bar(pct: int, width: int = 20) -> str:
    """Visual bar for signal strength."""
    filled = int(pct / 100 * width)
    bar = "█" * filled + "░" * (width - filled)
    if pct >= 80:
        quality = "Excellent"
    elif pct >= 60:
        quality = "Good"
    elif pct >= 40:
        quality = "Fair"
    elif pct >= 20:
        quality = "Poor"
    else:
        quality = "Very Poor"
    return f"{bar} {pct}%  {quality}"


def _parse_network_block(block: str) -> dict:
    """Parse one SSID block from netsh wlan show networks mode=bssid output."""
    result: dict = {}
    for line in block.splitlines():
        line = line.strip()
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip().lower()
            val = val.strip()
            if "ssid" in key and "bssid" not in key:
                result["ssid"] = val
            elif "bssid" in key:
                result.setdefault("bssids", []).append(val)
            elif "signal" in key:
                # "Signal : 78%" → 78
                m = re.search(r"(\d+)", val)
                result["signal"] = int(m.group(1)) if m else 0
            elif "radio type" in key or "type" in key:
                result.setdefault("radio", val)
            elif "channel" in key:
                result.setdefault("channel", val)
            elif "authentication" in key:
                result["auth"] = val
            elif "cipher" in key:
                result["cipher"] = val
            elif "network type" in key:
                result["network_type"] = val
            elif "band" in key:
                result["band"] = val
    return result


# ---------------------------------------------------------------------------
# Tool: scan_wifi_networks
# ---------------------------------------------------------------------------


def scan_wifi_networks(show_bssids: bool = False) -> str:
    """
    Scan for visible WiFi networks and display SSID, signal strength,
    security type, channel, and frequency band.

    Args:
        show_bssids: Include BSSID (MAC address) for each access point (default False).
    """
    rc, out = _netsh("wlan", "show", "networks", "mode=bssid")
    if rc != 0:
        return f"[scan_wifi_networks error]\n{out}\n\nMake sure WiFi is enabled."

    # Split output into per-SSID blocks
    blocks = re.split(r"\nSSID \d+ :", "\n" + out)
    networks: list[dict] = []

    for block in blocks[1:]:  # skip header
        net = _parse_network_block(block)
        if net.get("ssid"):
            networks.append(net)

    if not networks:
        return (
            "No WiFi networks found.\n"
            "Make sure WiFi is turned on and you're not in airplane mode."
        )

    # Sort by signal strength descending
    networks.sort(key=lambda n: n.get("signal", 0), reverse=True)

    lines = [
        f"WiFi networks visible: {len(networks)}",
        "",
        f"{'SSID':<35} {'Signal':<10} {'Auth':<20} {'Channel':<9} {'Band'}",
        "-" * 90,
    ]

    for net in networks:
        ssid = net.get("ssid", "?")[:34]
        sig = net.get("signal", 0)
        auth = net.get("auth", "?")[:19]
        chan = net.get("channel", "?")
        band = net.get("band", net.get("radio", "?"))

        # Signal icon
        if sig >= 75:
            icon = "▂▄▆█"
        elif sig >= 50:
            icon = "▂▄▆░"
        elif sig >= 25:
            icon = "▂▄░░"
        else:
            icon = "▂░░░"

        lines.append(f"{ssid:<35} {icon} {sig:>2}%   {auth:<20} {chan:<9} {band}")
        if show_bssids:
            for bssid in net.get("bssids", []):
                lines.append(f"  {'':35} BSSID: {bssid}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: wifi_connection_info
# ---------------------------------------------------------------------------


def wifi_connection_info() -> str:
    """
    Show detailed information about the current WiFi connection:
    SSID, BSSID, channel, signal strength, speed, security, and radio type.
    """
    rc, out = _netsh("wlan", "show", "interfaces")
    if rc != 0:
        return f"[wifi_connection_info error]\n{out}"

    if "There is no wireless interface" in out:
        return "No wireless adapter found on this machine."

    lines = ["Current WiFi Connection:", ""]

    # Parse key-value pairs
    interface_blocks = re.split(r"\n\s*Name\s+:", out)
    for block in interface_blocks[1:]:
        block = "Name : " + block
        kv: dict[str, str] = {}
        for line in block.splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                kv[key.strip().lower()] = val.strip()

        state = kv.get("state", "unknown")
        ssid = kv.get("ssid", "(not connected)")

        if "connected" not in state.lower():
            lines.append(f"  Interface: {kv.get('name', '?')}")
            lines.append(f"  State:     ⛔ {state}")
            lines.append("")
            continue

        signal_str = kv.get("signal", "0%").replace("%", "")
        try:
            signal = int(signal_str)
        except ValueError:
            signal = 0

        lines += [
            f"  Interface:    {kv.get('name', '?')}",
            f"  State:        ✅ {state}",
            f"  SSID:         {ssid}",
            f"  BSSID:        {kv.get('bssid', '?')}",
            f"  Radio type:   {kv.get('radio type', kv.get('radio_type', '?'))}",
            f"  Channel:      {kv.get('channel', '?')}",
            f"  Receive rate: {kv.get('receive rate (mbps)', kv.get('receive rate', '?'))} Mbps",
            f"  Transmit:     {kv.get('transmit rate (mbps)', kv.get('transmit rate', '?'))} Mbps",
            f"  Signal:       {_signal_bar(signal)}",
            f"  Auth:         {kv.get('authentication', '?')}",
            f"  Cipher:       {kv.get('cipher', '?')}",
            f"  Profile:      {kv.get('profile', '?')}",
            "",
        ]

    if not lines[2:]:
        return out  # Fallback: return raw output

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: wifi_password_list
# ---------------------------------------------------------------------------


def wifi_password_list(ssid: str = "") -> str:
    """
    Show saved WiFi passwords for all profiles or a specific network.

    Requires Administrator privileges to reveal passwords.

    Args:
        ssid: Specific network name to show password for.
              Leave empty to list all saved profiles and their passwords.
    """
    # Get list of profiles
    rc, profile_out = _netsh("wlan", "show", "profiles")
    if rc != 0:
        return f"[wifi_password_list error]\n{profile_out}"

    # Parse profile names
    profiles = re.findall(r"All User Profile\s*:\s*(.+)", profile_out)
    if not profiles:
        profiles = re.findall(r"User Profile\s*:\s*(.+)", profile_out)

    if ssid:
        profiles = [p for p in profiles if ssid.lower() in p.strip().lower()]

    if not profiles:
        if ssid:
            return f"No saved WiFi profile found for '{ssid}'."
        return "No saved WiFi profiles found."

    lines = [f"Saved WiFi profiles: {len(profiles)}", ""]

    for profile in profiles:
        profile = profile.strip()
        rc2, detail = _netsh("wlan", "show", "profile", f"name={profile}", "key=clear")

        password = ""
        if rc2 == 0:
            m = re.search(r"Key Content\s*:\s*(.+)", detail)
            if m:
                password = m.group(1).strip()
            auth_m = re.search(r"Authentication\s*:\s*(.+)", detail)
            auth = auth_m.group(1).strip() if auth_m else "?"
        else:
            auth = "?"
            if "requires elevation" in detail.lower() or "access is denied" in detail.lower():
                password = "(requires Administrator to reveal)"
            else:
                password = "(unavailable)"

        pw_display = password if password else "(open network / no password)"
        lines += [
            f"  Network:  {profile}",
            f"  Auth:     {auth}",
            f"  Password: {pw_display}",
            "",
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: wifi_signal_history
# ---------------------------------------------------------------------------


def wifi_signal_history(
    samples: int = 10,
    interval_seconds: float = 2.0,
) -> str:
    """
    Poll WiFi signal strength over time and display a live trend chart.

    Args:
        samples:          Number of signal samples to take (default 10).
        interval_seconds: Seconds between samples (default 2.0, min 0.5).
    """
    samples = max(2, min(60, samples))
    interval = max(0.5, min(10.0, interval_seconds))

    readings: list[int] = []

    for i in range(samples):
        rc, out = _netsh("wlan", "show", "interfaces")
        m = re.search(r"Signal\s*:\s*(\d+)%", out)
        if m:
            readings.append(int(m.group(1)))
        else:
            readings.append(0)

        if i < samples - 1:
            time.sleep(interval)

    if not readings:
        return "Could not read signal strength. Check WiFi is connected."

    avg = sum(readings) / len(readings)
    min_sig = min(readings)
    max_sig = max(readings)

    lines = [
        f"WiFi Signal History ({samples} samples, {interval}s interval):",
        f"  Average: {avg:.0f}%   Min: {min_sig}%   Max: {max_sig}%",
        "",
        "  Time  Signal  Chart",
        "  " + "-" * 55,
    ]

    for i, sig in enumerate(readings):
        timestamp = f"T+{i * interval:.0f}s"
        bar_width = int(sig / 5)
        bar = "█" * bar_width
        warn = " ⚠️" if sig < 30 else ""
        lines.append(f"  {timestamp:<6} {sig:>3}%    {bar}{warn}")

    # Trend
    if len(readings) >= 3:
        trend_start = sum(readings[:3]) / 3
        trend_end = sum(readings[-3:]) / 3
        delta = trend_end - trend_start
        if delta > 5:
            trend = "📈 Improving"
        elif delta < -5:
            trend = "📉 Degrading"
        else:
            trend = "➡️  Stable"
        lines.append(f"\n  Trend: {trend}  (Δ {delta:+.0f}%)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: wifi_diagnostics
# ---------------------------------------------------------------------------


def wifi_diagnostics() -> str:
    """
    Run Windows built-in WiFi diagnostics and show adapter information.

    Shows adapter capabilities, driver info, and radio state.
    """
    lines = ["WiFi Diagnostics", "=" * 50, ""]

    # Interface details
    rc, out = _netsh("wlan", "show", "interfaces")
    lines.append("Interface Status:")
    lines.append(out[:800] if out else "(no output)")
    lines.append("")

    # Driver details
    rc2, driver_out = _netsh("wlan", "show", "drivers")
    lines.append("Driver Information:")
    lines.append(driver_out[:600] if driver_out else "(no output)")
    lines.append("")

    # Capabilities
    rc3, cap_out = _netsh("wlan", "show", "capabilities")
    lines.append("Adapter Capabilities:")
    lines.append(cap_out[:600] if cap_out else "(no output)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: wifi_connect / wifi_disconnect
# ---------------------------------------------------------------------------


def wifi_disconnect() -> str:
    """Disconnect from the current WiFi network."""
    rc, out = _netsh("wlan", "disconnect")
    if rc == 0:
        return f"✅ Disconnected from WiFi.\n{out}"
    return f"❌ Disconnect failed (exit {rc}):\n{out}"


def wifi_connect(profile_name: str) -> str:
    """
    Connect to a saved WiFi profile by name.

    Args:
        profile_name: Name of the saved WiFi profile to connect to.
                      Use wifi_password_list to see saved profiles.
    """
    rc, out = _netsh("wlan", "connect", f"name={profile_name}")
    if rc == 0:
        # Wait a moment and check connection
        time.sleep(3)
        rc2, status = _netsh("wlan", "show", "interfaces")
        m = re.search(r"Signal\s*:\s*(\d+)%", status)
        sig = m.group(1) if m else "?"
        return f"✅ Connected to '{profile_name}'  Signal: {sig}%\n{out}"
    return f"❌ Failed to connect to '{profile_name}' (exit {rc}):\n{out}"


# ---------------------------------------------------------------------------
# Tool: forget_wifi_network
# ---------------------------------------------------------------------------


def forget_wifi_network(profile_name: str, dry_run: bool = True) -> str:
    """
    Delete a saved WiFi profile (forget the network).

    Args:
        profile_name: Name of the WiFi profile to delete.
        dry_run:      Preview without deleting (default True).
    """
    if dry_run:
        return (
            f"[DRY RUN] Would delete saved WiFi profile '{profile_name}'.\n"
            "Run with dry_run=False to actually remove it."
        )

    rc, out = _netsh("wlan", "delete", "profile", f"name={profile_name}")
    if rc == 0 or "deleted" in out.lower():
        return f"✅ WiFi profile '{profile_name}' deleted.\n{out}"
    return f"❌ Failed to delete profile '{profile_name}' (exit {rc}):\n{out}"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(registry) -> None:
    registry.register(
        "scan_wifi_networks",
        scan_wifi_networks,
        description=(
            "Scan for all visible WiFi networks. Shows SSID, signal strength, "
            "security type, channel, and band. Works without any extra dependencies."
        ),
        category="web",
        args=[
            {
                "name": "show_bssids",
                "required": False,
                "description": "Include BSSID (MAC) for each access point (default False)",
            },
        ],
    )

    registry.register(
        "wifi_connection_info",
        wifi_connection_info,
        description=(
            "Show current WiFi connection details: SSID, BSSID, signal strength, "
            "channel, receive/transmit rate, and security settings."
        ),
        category="web",
        args=[],
    )

    registry.register(
        "wifi_password_list",
        wifi_password_list,
        description=(
            "Show saved WiFi passwords for all stored networks or a specific SSID. "
            "Requires Administrator to reveal passwords."
        ),
        category="web",
        args=[
            {
                "name": "ssid",
                "required": False,
                "description": "Specific network name, or leave empty for all saved profiles",
            },
        ],
    )

    registry.register(
        "wifi_signal_history",
        wifi_signal_history,
        description=(
            "Poll WiFi signal strength repeatedly and display a trend chart. "
            "Useful for testing signal strength in different locations."
        ),
        category="web",
        args=[
            {
                "name": "samples",
                "required": False,
                "description": "Number of samples to take (default 10)",
            },
            {
                "name": "interval_seconds",
                "required": False,
                "description": "Seconds between samples (default 2.0)",
            },
        ],
    )

    registry.register(
        "wifi_diagnostics",
        wifi_diagnostics,
        description=(
            "Run Windows WiFi diagnostics — shows interface status, driver info, "
            "and adapter capabilities."
        ),
        category="web",
        args=[],
    )

    registry.register(
        "wifi_disconnect",
        wifi_disconnect,
        description="Disconnect from the current WiFi network.",
        category="web",
        args=[],
    )

    registry.register(
        "wifi_connect",
        wifi_connect,
        description="Connect to a saved WiFi profile by name. Use wifi_password_list to see saved profiles.",
        category="web",
        args=[
            {
                "name": "profile_name",
                "required": True,
                "description": "Name of the saved WiFi profile to connect to",
            },
        ],
    )

    registry.register(
        "forget_wifi_network",
        forget_wifi_network,
        description=(
            "Delete a saved WiFi network profile (forget the network). " "dry_run=True by default."
        ),
        category="web",
        args=[
            {
                "name": "profile_name",
                "required": True,
                "description": "WiFi profile name to forget",
            },
            {
                "name": "dry_run",
                "required": False,
                "description": "Preview without deleting (default True)",
            },
        ],
    )
