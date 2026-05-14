"""
drive_manager.py — Drive health, partitions, and USB device manager plugin.

Tools provided:
  locate_smartctl      — Find smartctl.exe on this machine (diagnostic)
  list_drives          — All physical drives with size, type, interface
  drive_health         — Full SMART health data via smartctl (falls back to WMI)
  smartctl_report      — Raw full smartctl -a output for a drive
  disk_partitions      — Partitions/volumes with usage stats
  usb_devices          — List connected USB storage and devices
  usb_health           — Health details on a specific USB drive
  disk_io_stats        — Real-time disk read/write throughput

SMART setup (one-time):
  Download the Windows installer from https://www.smartmontools.org/wiki/Download
  Default install path: C:\\Program Files\\smartmontools\\bin\\smartctl.exe
  Run Iceberg as Administrator for full SMART attribute access.

Optional pip deps:
  pip install wmi pywin32   (for WMI fallback and USB enumeration)
  pip install psutil        (for partition + IO stats)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Optional

# ---------------------------------------------------------------------------
# Dependency guards
# ---------------------------------------------------------------------------

_PSUTIL_AVAILABLE = False
_WMI_AVAILABLE = False

try:
    _PSUTIL_AVAILABLE = True
except ImportError:
    pass

try:
    import wmi as _wmi_mod

    _WMI_AVAILABLE = True
except ImportError:
    pass

_PSUTIL_MSG = "Drive tools require psutil.\n" "Install with:  pip install psutil"

# ---------------------------------------------------------------------------
# smartctl discovery
# ---------------------------------------------------------------------------

# Candidate paths — ordered by likelihood.
_SMARTCTL_CANDIDATES = [
    r"C:\Program Files\smartmontools\bin\smartctl.exe",
    r"C:\Program Files (x86)\smartmontools\bin\smartctl.exe",
    # User's Desktop copy (built or extracted there)
    r"C:\Users\tyler\Desktop\smartmontools-main\bin\Release\smartctl.exe",
    r"C:\Users\tyler\Desktop\smartmontools-main\bin\smartctl.exe",
    r"C:\Users\tyler\Desktop\smartmontools-main\smartctl.exe",
    r"C:\Users\tyler\Desktop\smartmontools-main\windows\smartctl.exe",
    # Any other common spots
    r"C:\smartmontools\bin\smartctl.exe",
    r"C:\tools\smartmontools\bin\smartctl.exe",
]

_SMARTCTL_SETUP = """\

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  SMARTCTL NOT FOUND — Quick Setup
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The smartmontools-main folder on your Desktop is the source code —
it needs to be compiled, or you can just download the pre-built
Windows binary instead (much easier):

  1. Download the installer (.exe) from:
     https://www.smartmontools.org/wiki/Download
     (look for "For Windows" → smartmontools-X.X-X.win32-setup.exe)

  2. Run the installer — default path:
     C:\\Program Files\\smartmontools\\bin\\smartctl.exe

  3. Restart Iceberg (or reload the plugin).

For full SMART attributes, run Iceberg (or server.py) as Administrator.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


def _find_smartctl() -> Optional[str]:
    """Return the path to smartctl.exe, or None if not found."""
    # Check PATH first (covers system-wide install / env var)
    in_path = shutil.which("smartctl") or shutil.which("smartctl.exe")
    if in_path:
        return in_path

    # Check candidate paths
    for candidate in _SMARTCTL_CANDIDATES:
        if os.path.isfile(candidate):
            return candidate

    return None


def _run_smartctl(*args: str) -> tuple[int, str, str]:
    """
    Run smartctl with the given args. Returns (returncode, stdout, stderr).
    Raises FileNotFoundError if smartctl is not found.
    """
    exe = _find_smartctl()
    if not exe:
        raise FileNotFoundError("smartctl.exe not found")

    result = subprocess.run(
        [exe] + list(args),
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.returncode, result.stdout, result.stderr


def _smartctl_dev(drive_index: int) -> str:
    """Map drive index to smartctl device string (Windows uses /dev/pdN)."""
    return f"/dev/pd{drive_index}"


# ---------------------------------------------------------------------------
# WMI helper
# ---------------------------------------------------------------------------


def _wmi_conn():
    if not _WMI_AVAILABLE:
        return None
    try:
        import wmi

        return wmi.WMI()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _fmt_bytes(n: int) -> str:
    """Human-readable byte size."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _health_bar(pct: float, width: int = 20) -> str:
    filled = int(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


# ---------------------------------------------------------------------------
# Tool: locate_smartctl
# ---------------------------------------------------------------------------


def locate_smartctl() -> str:
    """
    Find smartctl.exe on this machine and show where it is (or how to get it).
    """
    exe = _find_smartctl()
    if exe:
        # Try version check
        try:
            _, out, _ = _run_smartctl("--version")
            ver_line = out.splitlines()[0] if out else "(version unknown)"
        except Exception as e:
            ver_line = f"(could not get version: {e})"

        lines = [
            "✅ smartctl found!",
            f"  Path:     {exe}",
            f"  Version:  {ver_line}",
            "",
            "Drive health tools are fully operational.",
            "Run Iceberg as Administrator for full SMART attribute access.",
        ]
        return "\n".join(lines)

    # Not found — show all checked locations
    lines = [
        "❌ smartctl.exe not found.",
        "",
        "Locations checked:",
    ]
    in_path = shutil.which("smartctl") or shutil.which("smartctl.exe")
    lines.append(f"  PATH:  {'found → ' + in_path if in_path else 'not in PATH'}")
    for candidate in _SMARTCTL_CANDIDATES:
        exists = "✓ EXISTS" if os.path.isfile(candidate) else "✗ missing"
        lines.append(f"  {exists}  {candidate}")

    lines.append(_SMARTCTL_SETUP)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: list_drives
# ---------------------------------------------------------------------------


def list_drives() -> str:
    """
    List all physical disk drives with size, media type, and interface.
    """
    # Try smartctl scan first (most reliable)
    try:
        rc, out, err = _run_smartctl("--scan")
        if rc == 0 and out.strip():
            lines = ["Physical drives (smartctl --scan):", ""]
            for i, line in enumerate(out.strip().splitlines()):
                dev = line.split()[0] if line.split() else line
                # Get basic info for each drive
                try:
                    _, info_out, _ = _run_smartctl("-i", dev)
                    model = "(unknown)"
                    serial = ""
                    size = ""
                    for il in info_out.splitlines():
                        if "Device Model" in il or "Model Family" in il:
                            model = il.split(":", 1)[1].strip() if ":" in il else model
                        elif "Serial Number" in il:
                            serial = il.split(":", 1)[1].strip() if ":" in il else ""
                        elif "User Capacity" in il:
                            # e.g. "500,107,862,016 bytes [500 GB]"
                            bracket = il.split("[")
                            size = bracket[1].rstrip("]").strip() if len(bracket) > 1 else ""
                except Exception:
                    model, serial, size = "(error reading info)", "", ""

                lines.append(f"  Disk {i}: {dev}")
                lines.append(f"    Model:   {model}")
                if serial:
                    lines.append(f"    Serial:  {serial}")
                if size:
                    lines.append(f"    Size:    {size}")
                lines.append("")
            return "\n".join(lines).rstrip()
    except FileNotFoundError:
        pass  # fall through to WMI / psutil

    # WMI fallback
    c = _wmi_conn()
    if c:
        try:
            disks = c.Win32_DiskDrive()
            lines = [
                f"{'Drive':<8} {'Model':<42} {'Size':>10} {'Interface':<12} {'Partitions'}",
                "-" * 90,
            ]
            for disk in sorted(disks, key=lambda d: d.Index or 0):
                size = int(disk.Size or 0)
                name = (disk.Caption or disk.Model or "Unknown")[:41]
                iface = disk.InterfaceType or "Unknown"
                parts = disk.Partitions or 0
                lines.append(
                    f"Disk {disk.Index:<3} {name:<42} {_fmt_bytes(size):>10} {iface:<12} {parts}"
                )
            if not disks:
                lines.append("No physical drives detected via WMI.")
            return "\n".join(lines)
        except Exception as e:
            pass

    # psutil fallback
    if not _PSUTIL_AVAILABLE:
        return "Drive listing requires psutil. Run: pip install psutil"

    import psutil

    try:
        parts = psutil.disk_partitions(all=False)
        lines = [
            f"{'Device':<12} {'Mount':<20} {'FS':<8} {'Total':>10} {'Used':>10} {'Free':>10} {'Use%'}",
            "-" * 85,
        ]
        for p in parts:
            try:
                usage = psutil.disk_usage(p.mountpoint)
                lines.append(
                    f"{p.device[:11]:<12} {p.mountpoint[:19]:<20} {p.fstype[:7]:<8} "
                    f"{_fmt_bytes(usage.total):>10} {_fmt_bytes(usage.used):>10} "
                    f"{_fmt_bytes(usage.free):>10} {usage.percent:.1f}%"
                )
            except PermissionError:
                lines.append(f"{p.device[:11]:<12} {p.mountpoint[:19]:<20} [no access]")
        return "\n".join(lines)
    except Exception as e:
        return f"[Error listing drives] {e}"


# ---------------------------------------------------------------------------
# Tool: drive_health
# ---------------------------------------------------------------------------


def drive_health(drive_index: int = 0) -> str:
    """
    Show SMART health data for a physical drive.

    Args:
        drive_index: Which disk to inspect (0 = first/primary, 1 = second, etc.)
    """
    # ── Primary: smartctl ───────────────────────────────────────────────────
    exe = _find_smartctl()
    if exe:
        dev = _smartctl_dev(drive_index)
        try:
            rc, out, err = _run_smartctl("-H", "-i", "-A", "-l", "error", dev)
            if not out.strip():
                return (
                    f"smartctl returned no output for {dev}.\nTry running Iceberg as Administrator."
                )

            # Parse overall health assessment
            health_line = "Unknown"
            for line in out.splitlines():
                if "SMART overall-health" in line or "SMART Health Status" in line:
                    health_line = line.split(":", 1)[1].strip() if ":" in line else line
                    break

            emoji = "✅" if "PASSED" in health_line.upper() or "OK" in health_line.upper() else "⚠️"

            lines = [
                f"Drive {drive_index} ({dev}) — SMART Report",
                f"  Overall Health: {emoji} {health_line}",
                "",
                "─── Full smartctl output ───────────────────────────────",
                out.strip(),
            ]

            if rc == 64:
                lines.append(
                    "\n⚠️  smartctl exit code 64 — some SMART attributes may be unavailable."
                )
                lines.append("   Run Iceberg as Administrator for full attribute access.")

            return "\n".join(lines)

        except subprocess.TimeoutExpired:
            return f"smartctl timed out reading drive {drive_index}."
        except Exception as e:
            # Fall through to WMI
            pass

    # ── Fallback: WMI ──────────────────────────────────────────────────────
    c = _wmi_conn()
    if c:
        try:
            disks = c.Win32_DiskDrive(Index=drive_index)
            if not disks:
                return f"No drive at index {drive_index}. Use list_drives to see available drives."

            disk = disks[0]
            size = int(disk.Size or 0)
            lines = [
                f"Drive {drive_index}: {disk.Caption or disk.Model}  (WMI — no smartctl)",
                f"  Serial:     {disk.SerialNumber or 'N/A'}",
                f"  Size:       {_fmt_bytes(size)}",
                f"  Interface:  {disk.InterfaceType or 'N/A'}",
                f"  Firmware:   {disk.FirmwareRevision or 'N/A'}",
                f"  Partitions: {disk.Partitions or 0}",
            ]

            # Try WMI SMART status
            try:
                ns_wmi = _wmi_mod.WMI(namespace="root\\wmi")
                smart_items = ns_wmi.MSStorageDriver_FailurePredictStatus()
                for s in smart_items:
                    if str(drive_index) in (s.InstanceName or ""):
                        predict = s.PredictFailure
                        reason = s.Reason or 0
                        status = "⚠️  FAILURE PREDICTED" if predict else "✅ No failure predicted"
                        lines.append(f"\n  SMART Status:  {status}")
                        if predict and reason:
                            lines.append(f"  Reason code:   {reason}")
                        break
                else:
                    lines.append(
                        "\n  SMART Status:  (could not read — try running as Administrator)"
                    )
            except Exception:
                lines.append("\n  SMART Status:  (WMI root\\wmi not accessible)")

            lines.append(_SMARTCTL_SETUP)
            return "\n".join(lines)

        except Exception as e:
            return f"[drive_health error] {e}"

    return f"Drive health requires either smartctl or WMI+pywin32.\n" f"{_SMARTCTL_SETUP}"


# ---------------------------------------------------------------------------
# Tool: smartctl_report
# ---------------------------------------------------------------------------


def smartctl_report(drive_index: int = 0, all_attributes: bool = True) -> str:
    """
    Run a full smartctl report on a physical drive and return raw output.

    Args:
        drive_index:    Physical drive number (0 = primary, 1 = second, etc.)
        all_attributes: Include all SMART attributes table (default True)
    """
    exe = _find_smartctl()
    if not exe:
        return f"smartctl not found.\n{_SMARTCTL_SETUP}"

    dev = _smartctl_dev(drive_index)
    args = ["-x", dev] if all_attributes else ["-a", dev]

    try:
        rc, out, err = _run_smartctl(*args)
        header = f"smartctl {'--xall' if all_attributes else '-a'} {dev}\n" + "=" * 60 + "\n"
        result = header + (out or err or "(no output)")
        if rc not in (0, 64):
            result += f"\n\n[smartctl exit code {rc} — may need Administrator rights]"
        return result
    except FileNotFoundError:
        return f"smartctl not found.\n{_SMARTCTL_SETUP}"
    except subprocess.TimeoutExpired:
        return f"smartctl timed out on {dev}."
    except Exception as e:
        return f"[smartctl_report error] {e}"


# ---------------------------------------------------------------------------
# Tool: disk_partitions
# ---------------------------------------------------------------------------


def disk_partitions(show_all: bool = False) -> str:
    """
    List all disk partitions with total/used/free space and a visual bar.

    Args:
        show_all: Include unmounted/special partitions (default False)
    """
    if not _PSUTIL_AVAILABLE:
        return _PSUTIL_MSG

    import psutil

    lines = [
        f"{'Mount':<20} {'Device':<14} {'FS':<8} {'Total':>10} {'Used':>10} {'Free':>10} {'Use%':>6}  Bar",
        "-" * 95,
    ]

    warnings = []

    try:
        partitions = psutil.disk_partitions(all=show_all)
        if not partitions:
            return "No disk partitions found."

        for p in partitions:
            try:
                usage = psutil.disk_usage(p.mountpoint)
                pct = usage.percent
                bar = _health_bar(pct, 10)
                warn = " ⚠️" if pct >= 90 else ""
                lines.append(
                    f"{p.mountpoint[:19]:<20} {p.device[:13]:<14} {p.fstype[:7]:<8} "
                    f"{_fmt_bytes(usage.total):>10} {_fmt_bytes(usage.used):>10} "
                    f"{_fmt_bytes(usage.free):>10} {pct:>5.1f}%  {bar}{warn}"
                )
                if pct >= 90:
                    warnings.append(f"  ⚠️  {p.mountpoint} is {pct:.1f}% full!")
            except (PermissionError, OSError):
                lines.append(f"{p.mountpoint[:19]:<20} {p.device[:13]:<14} [access denied]")
            except Exception as e:
                lines.append(f"{p.mountpoint[:19]:<20} {p.device[:13]:<14} [error: {e}]")

        if warnings:
            lines.append("\nWarnings:")
            lines.extend(warnings)

        return "\n".join(lines).rstrip()

    except Exception as e:
        return f"[disk_partitions error] {e}"


# ---------------------------------------------------------------------------
# Tool: usb_devices
# ---------------------------------------------------------------------------


def usb_devices() -> str:
    """
    List connected USB storage devices and other USB peripherals.
    """
    c = _wmi_conn()
    if not c:
        return (
            "USB device enumeration requires WMI.\n"
            "Install with:  pip install wmi pywin32\n\n"
            "Showing mounted USB volumes via psutil instead:\n\n" + _usb_via_psutil()
        )

    try:
        usb_disks = c.Win32_DiskDrive(InterfaceType="USB")
        lines = ["USB Storage Devices:", ""]
        if not usb_disks:
            lines.append("  No USB storage devices currently connected.")
        else:
            for disk in usb_disks:
                size = int(disk.Size or 0)
                lines.append(f"  {disk.Caption or disk.Model}")
                lines.append(f"    Serial:     {disk.SerialNumber or 'N/A'}")
                lines.append(f"    Size:       {_fmt_bytes(size)}")
                lines.append(f"    Interface:  {disk.InterfaceType}")
                lines.append(f"    Status:     {disk.Status or 'N/A'}")
                lines.append("")

        # Also list USB controllers / hubs
        try:
            controllers = c.Win32_USBController()
            lines.append(f"\nUSB Controllers ({len(controllers)} found):")
            for ctrl in controllers:
                lines.append(f"  {ctrl.Name or ctrl.Caption}")
        except Exception:
            pass

        return "\n".join(lines).rstrip()

    except Exception as e:
        return f"[usb_devices error] {e}"


def _usb_via_psutil() -> str:
    if not _PSUTIL_AVAILABLE:
        return "(psutil not installed)"
    import psutil

    removable = [p for p in psutil.disk_partitions() if "removable" in (p.opts or "").lower()]
    if not removable:
        return "  No removable volumes mounted."
    lines = []
    for p in removable:
        try:
            usage = psutil.disk_usage(p.mountpoint)
            lines.append(
                f"  {p.mountpoint} ({p.device})  {_fmt_bytes(usage.total)}  {usage.percent:.1f}% used"
            )
        except Exception:
            lines.append(f"  {p.mountpoint} ({p.device})  [no access]")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: usb_health
# ---------------------------------------------------------------------------


def usb_health(drive_letter: str = "") -> str:
    """
    Show health/capacity details for a specific USB drive.

    Args:
        drive_letter: Drive letter to inspect, e.g. 'E' or 'E:' (optional)
    """
    if not _PSUTIL_AVAILABLE:
        return _PSUTIL_MSG

    import psutil

    letter = (drive_letter.rstrip(":\\").upper() + ":\\") if drive_letter else ""

    try:
        parts = psutil.disk_partitions(all=False)
        usb_parts = [p for p in parts if "removable" in (p.opts or "").lower()]

        if not usb_parts:
            return "No removable USB drives mounted."

        if letter:
            target = [p for p in usb_parts if p.mountpoint.upper().startswith(letter)]
            if not target:
                return (
                    f"Drive {letter} not found among removable drives.\n"
                    f"Available: {', '.join(p.mountpoint for p in usb_parts)}"
                )
            usb_parts = target

        lines = []
        for p in usb_parts:
            try:
                usage = psutil.disk_usage(p.mountpoint)
                pct = usage.percent
                bar = _health_bar(pct, 25)
                lines += [
                    f"USB Drive: {p.mountpoint}",
                    f"  Device:     {p.device}",
                    f"  Filesystem: {p.fstype}",
                    f"  Total:      {_fmt_bytes(usage.total)}",
                    f"  Used:       {_fmt_bytes(usage.used)} ({pct:.1f}%)",
                    f"  Free:       {_fmt_bytes(usage.free)}",
                    f"  Usage:      [{bar}] {pct:.1f}%",
                    "",
                ]
            except Exception as e:
                lines.append(f"  {p.mountpoint}: [error: {e}]")

        return "\n".join(lines).rstrip()

    except Exception as e:
        return f"[usb_health error] {e}"


# ---------------------------------------------------------------------------
# Tool: disk_io_stats
# ---------------------------------------------------------------------------


def disk_io_stats(interval_seconds: int = 1) -> str:
    """
    Show real-time disk I/O throughput (reads/writes per second).

    Args:
        interval_seconds: Measurement window in seconds (1–5, default 1).
    """
    if not _PSUTIL_AVAILABLE:
        return _PSUTIL_MSG

    import psutil

    interval = max(1, min(5, interval_seconds))

    try:
        before = psutil.disk_io_counters(perdisk=True)
        time.sleep(interval)
        after = psutil.disk_io_counters(perdisk=True)
    except Exception as e:
        return f"[disk_io_stats error] {e}"

    lines = [
        f"Disk I/O over {interval}s:",
        f"{'Drive':<14} {'Read/s':>12} {'Write/s':>12} {'Read ops/s':>12} {'Write ops/s':>13}",
        "-" * 65,
    ]

    for drive, after_stats in sorted(after.items()):
        if drive not in before:
            continue
        b = before[drive]
        a = after_stats
        read_bps = (a.read_bytes - b.read_bytes) / interval
        write_bps = (a.write_bytes - b.write_bytes) / interval
        read_ops = (a.read_count - b.read_count) / interval
        write_ops = (a.write_count - b.write_count) / interval
        lines.append(
            f"{drive[:13]:<14} {_fmt_bytes(read_bps):>11}/s {_fmt_bytes(write_bps):>11}/s "
            f"{read_ops:>11.0f}/s {write_ops:>12.0f}/s"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(registry) -> None:
    registry.register(
        "locate_smartctl",
        locate_smartctl,
        description=(
            "Find smartctl.exe on this machine and show its version/path. "
            "Also shows setup instructions if smartctl is not installed."
        ),
        category="system",
        args=[],
    )

    registry.register(
        "list_drives",
        list_drives,
        description=(
            "List all physical disk drives with model, size, interface (SATA/NVMe/USB), "
            "and partition count. Uses smartctl → WMI → psutil in priority order."
        ),
        category="system",
        args=[],
    )

    registry.register(
        "drive_health",
        drive_health,
        description=(
            "Show SMART health data for a specific drive. Uses smartctl for full attribute "
            "data (recommended), falls back to WMI. drive_index=0 is the primary drive."
        ),
        category="system",
        args=[
            {
                "name": "drive_index",
                "required": False,
                "description": "Physical drive number (0 = primary, 1 = second, etc.)",
            },
        ],
    )

    registry.register(
        "smartctl_report",
        smartctl_report,
        description=(
            "Run a full smartctl -xall report on a physical drive and return the complete raw output. "
            "Requires smartctl.exe. Run Iceberg as Administrator for all attributes."
        ),
        category="system",
        args=[
            {
                "name": "drive_index",
                "required": False,
                "description": "Physical drive number (0 = primary)",
            },
            {
                "name": "all_attributes",
                "required": False,
                "description": "Include complete SMART attributes table (default True)",
            },
        ],
    )

    registry.register(
        "disk_partitions",
        disk_partitions,
        description=(
            "List all disk partitions and volumes with total/used/free space "
            "and a visual usage bar. Warns when any volume exceeds 90% usage."
        ),
        category="system",
        args=[
            {
                "name": "show_all",
                "required": False,
                "description": "Include unmounted and special partitions (default False)",
            },
        ],
    )

    registry.register(
        "usb_devices",
        usb_devices,
        description=(
            "List connected USB storage devices and USB controllers. "
            "Uses WMI if available, psutil removable-drive fallback otherwise."
        ),
        category="system",
        args=[],
    )

    registry.register(
        "usb_health",
        usb_health,
        description=(
            "Show capacity and usage health for a specific USB drive by drive letter. "
            "Leave drive_letter empty to show all removable drives."
        ),
        category="system",
        args=[
            {
                "name": "drive_letter",
                "required": False,
                "description": "Drive letter, e.g. 'E' or 'E:' (optional — shows all if empty)",
            },
        ],
    )

    registry.register(
        "disk_io_stats",
        disk_io_stats,
        description=(
            "Measure real-time disk read/write throughput over a short interval. "
            "Shows per-drive MB/s and operations per second."
        ),
        category="system",
        args=[
            {
                "name": "interval_seconds",
                "required": False,
                "description": "Measurement window in seconds, 1–5 (default 1)",
            },
        ],
    )
