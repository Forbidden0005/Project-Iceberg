"""
System resource monitor for Project Iceberg.

CPU, memory, disk, temperature, and top resource hog reporting.

Requires: pip install psutil
Temperature readings on Windows also benefit from: pip install wmi
"""

import platform
import time
from datetime import datetime, timedelta

try:
    import psutil

    _PSUTIL = True
except ImportError:
    _PSUTIL = False

_IS_WINDOWS = platform.system() == "Windows"


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _uptime() -> str:
    try:
        boot = psutil.boot_time()
        delta = timedelta(seconds=time.time() - boot)
        days = delta.days
        hours, rem = divmod(delta.seconds, 3600)
        mins = rem // 60
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        parts.append(f"{mins}m")
        return " ".join(parts)
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Public tools
# ---------------------------------------------------------------------------


def system_stats() -> str:
    """
    Full system snapshot: CPU, RAM, swap, disk, network throughput, uptime.

    Returns a single formatted report covering all major resources at a glance.
    No arguments needed.
    """
    if not _PSUTIL:
        return "[error] psutil not installed — run: pip install psutil"

    lines = [
        f"System snapshot — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Uptime: {_uptime()}",
        "",
    ]

    # CPU
    cpu_pct = psutil.cpu_percent(interval=1)
    cpu_count_phys = psutil.cpu_count(logical=False)
    cpu_count_logi = psutil.cpu_count(logical=True)
    try:
        freq = psutil.cpu_freq()
        freq_str = f"  |  {freq.current:.0f} MHz (max {freq.max:.0f} MHz)" if freq else ""
    except Exception:
        freq_str = ""
    lines.append(
        f"CPU:    {cpu_pct:.1f}%  |  {cpu_count_phys} cores / {cpu_count_logi} threads{freq_str}"
    )

    # Per-core (compact)
    try:
        per_core = psutil.cpu_percent(percpu=True)
        core_str = "  ".join(f"C{i}:{p:.0f}%" for i, p in enumerate(per_core))
        lines.append(f"        {core_str}")
    except Exception:
        pass

    # Memory
    mem = psutil.virtual_memory()
    lines.append(
        f"\nRAM:    {_fmt_bytes(mem.used)} / {_fmt_bytes(mem.total)}  "
        f"({mem.percent:.1f}% used)  |  Available: {_fmt_bytes(mem.available)}"
    )
    try:
        swap = psutil.swap_memory()
        if swap.total > 0:
            lines.append(
                f"Swap:   {_fmt_bytes(swap.used)} / {_fmt_bytes(swap.total)}  "
                f"({swap.percent:.1f}% used)"
            )
    except Exception:
        pass

    # Disk
    lines.append("")
    try:
        partitions = psutil.disk_partitions()
        for p in partitions:
            if not p.mountpoint:
                continue
            try:
                usage = psutil.disk_usage(p.mountpoint)
                bar_pct = usage.percent
                bar = "█" * int(bar_pct / 5) + "░" * (20 - int(bar_pct / 5))
                lines.append(
                    f"Disk [{p.device}] {p.mountpoint}\n"
                    f"       {bar} {bar_pct:.1f}%  "
                    f"{_fmt_bytes(usage.used)} / {_fmt_bytes(usage.total)}  "
                    f"Free: {_fmt_bytes(usage.free)}"
                )
            except PermissionError:
                lines.append(f"Disk [{p.device}] {p.mountpoint}  (access denied)")
    except Exception as e:
        lines.append(f"Disk: error — {e}")

    # Network I/O (1-second delta)
    lines.append("")
    try:
        net1 = psutil.net_io_counters()
        time.sleep(1)
        net2 = psutil.net_io_counters()
        sent_ps = net2.bytes_sent - net1.bytes_sent
        recv_ps = net2.bytes_recv - net1.bytes_recv
        lines.append(
            f"Network: ↑ {_fmt_bytes(sent_ps)}/s  ↓ {_fmt_bytes(recv_ps)}/s  "
            f"(total sent: {_fmt_bytes(net2.bytes_sent)}  recv: {_fmt_bytes(net2.bytes_recv)})"
        )
    except Exception:
        pass

    # Temperatures (optional, platform-dependent)
    temp_lines = _get_temps()
    if temp_lines:
        lines.append("")
        lines.extend(temp_lines)

    return "\n".join(lines)


def cpu_usage(interval: float = 1.0, per_core: bool = True) -> str:
    """
    Show current CPU usage, optionally per-core.

    Args:
        interval:  Measurement window in seconds (default 1.0).
        per_core:  Show per-core breakdown (default True).

    Returns:
        Overall CPU % and per-core breakdown with load averages if available.
    """
    if not _PSUTIL:
        return "[error] psutil not installed — run: pip install psutil"

    overall = psutil.cpu_percent(interval=interval)
    lines = [f"CPU usage (over {interval}s):  {overall:.1f}% overall"]

    if per_core:
        cores = psutil.cpu_percent(percpu=True)
        for i, pct in enumerate(cores):
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            lines.append(f"  Core {i:>2}: {bar} {pct:.1f}%")

    # Load average (Linux/Mac only)
    try:
        la = psutil.getloadavg()
        lines.append(f"\nLoad avg (1m / 5m / 15m): {la[0]:.2f} / {la[1]:.2f} / {la[2]:.2f}")
    except AttributeError:
        pass  # Windows doesn't have load average

    try:
        freq = psutil.cpu_freq()
        if freq:
            lines.append(
                f"Frequency: {freq.current:.0f} MHz  (min {freq.min:.0f}  max {freq.max:.0f})"
            )
    except Exception:
        pass

    return "\n".join(lines)


def memory_details() -> str:
    """
    Detailed breakdown of RAM and swap usage.

    Returns physical and virtual memory stats plus the top 10 memory-hungry
    processes at the time of the call.
    """
    if not _PSUTIL:
        return "[error] psutil not installed — run: pip install psutil"

    mem = psutil.virtual_memory()
    lines = [
        "RAM breakdown:",
        f"  Total:     {_fmt_bytes(mem.total)}",
        f"  Used:      {_fmt_bytes(mem.used)}  ({mem.percent:.1f}%)",
        f"  Available: {_fmt_bytes(mem.available)}",
        f"  Free:      {_fmt_bytes(mem.free)}",
        f"  Cached:    {_fmt_bytes(getattr(mem, 'cached', 0))}",
        f"  Buffers:   {_fmt_bytes(getattr(mem, 'buffers', 0))}",
    ]

    try:
        swap = psutil.swap_memory()
        lines += [
            "",
            "Swap:",
            f"  Total: {_fmt_bytes(swap.total)}",
            f"  Used:  {_fmt_bytes(swap.used)}  ({swap.percent:.1f}%)",
            f"  Free:  {_fmt_bytes(swap.free)}",
        ]
    except Exception:
        pass

    # Top memory consumers
    lines += ["", "Top 10 RAM consumers:"]
    procs = []
    for proc in psutil.process_iter():
        try:
            m = proc.memory_info().rss
            procs.append((proc.name(), proc.pid, m))
        except Exception:
            continue
    procs.sort(key=lambda x: x[2], reverse=True)
    for name, pid, rss in procs[:10]:
        bar = "█" * min(int(rss / mem.total * 40), 40)
        lines.append(f"  {name:<30} PID {pid:<7} {_fmt_bytes(rss):>10}  {bar}")

    return "\n".join(lines)


def disk_usage(path: str = "/") -> str:
    """
    Show disk space usage for a specific path or drive.

    Args:
        path: Directory or drive letter to check (default '/'). On Windows
              use drive letters like 'C:\\' or 'D:\\'.

    Returns:
        Usage stats plus read/write throughput over the last second.
    """
    if not _PSUTIL:
        return "[error] psutil not installed — run: pip install psutil"

    # On Windows default to C:\
    if path == "/" and _IS_WINDOWS:
        path = "C:\\"

    try:
        usage = psutil.disk_usage(path)
    except Exception as e:
        return f"[error] Cannot read disk usage for {path}: {e}"

    bar_pct = usage.percent
    bar = "█" * int(bar_pct / 5) + "░" * (20 - int(bar_pct / 5))

    lines = [
        f"Disk usage: {path}",
        f"  {bar} {bar_pct:.1f}%",
        f"  Used:  {_fmt_bytes(usage.used)}",
        f"  Free:  {_fmt_bytes(usage.free)}",
        f"  Total: {_fmt_bytes(usage.total)}",
    ]

    # I/O throughput
    try:
        io1 = psutil.disk_io_counters()
        time.sleep(1)
        io2 = psutil.disk_io_counters()
        read_ps = io2.read_bytes - io1.read_bytes
        write_ps = io2.write_bytes - io1.write_bytes
        lines.append(
            f"\n  Current I/O:  Read {_fmt_bytes(read_ps)}/s  |  Write {_fmt_bytes(write_ps)}/s"
        )
        lines.append(
            f"  Lifetime:     Read {_fmt_bytes(io2.read_bytes)}  |  Write {_fmt_bytes(io2.write_bytes)}"
        )
    except Exception:
        pass

    return "\n".join(lines)


def top_resource_hogs(resource: str = "cpu", top_n: int = 10) -> str:
    """
    Find the processes consuming the most CPU or memory right now.

    Args:
        resource: "cpu" (default) or "memory".
        top_n:    How many to list (default 10).

    Returns:
        Ranked list of processes with usage bars.
    """
    if not _PSUTIL:
        return "[error] psutil not installed — run: pip install psutil"

    resource = resource.lower()
    top_n = max(1, min(top_n, 50))
    procs = []

    for proc in psutil.process_iter():
        try:
            cpu = proc.cpu_percent(interval=0.05)
            mem = proc.memory_info().rss
            procs.append((proc.name(), proc.pid, cpu, mem))
        except Exception:
            continue

    if resource == "memory":
        procs.sort(key=lambda x: x[3], reverse=True)
        total_mem = psutil.virtual_memory().total
        lines = [f"Top {top_n} by MEMORY:\n"]
        for name, pid, cpu, mem in procs[:top_n]:
            pct = mem / total_mem * 100
            bar = "█" * int(pct * 2) + "░" * max(0, 20 - int(pct * 2))
            lines.append(f"  {name:<30} PID {pid:<7} {_fmt_bytes(mem):>10}  {pct:.1f}%  {bar}")
    else:
        procs.sort(key=lambda x: x[2], reverse=True)
        lines = [f"Top {top_n} by CPU:\n"]
        for name, pid, cpu, mem in procs[:top_n]:
            bar = "█" * int(cpu / 5) + "░" * max(0, 20 - int(cpu / 5))
            lines.append(f"  {name:<30} PID {pid:<7} {cpu:>6.1f}%  {bar}")

    return "\n".join(lines)


def _get_temps() -> list[str]:
    """Return temperature lines if psutil can read them."""
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            return []
        lines = ["Temperatures:"]
        for chip, entries in temps.items():
            for e in entries:
                label = e.label or chip
                current = f"{e.current:.0f}°C"
                high = f"  (high: {e.high:.0f}°C)" if e.high else ""
                crit = (
                    f"  ⚠ CRITICAL: {e.critical:.0f}°C"
                    if e.critical and e.current >= e.critical
                    else ""
                )
                lines.append(f"  {label}: {current}{high}{crit}")
        return lines
    except (AttributeError, Exception):
        return []  # Windows often returns empty here without WMI


def hardware_temps() -> str:
    """
    Read hardware temperatures (CPU, GPU, drives) where available.

    On Windows this may require admin rights or additional WMI support.
    On Linux/Mac it reads directly from hardware sensors.

    Returns:
        Temperature readings per sensor, with high/critical thresholds flagged.
    """
    if not _PSUTIL:
        return "[error] psutil not installed — run: pip install psutil"

    lines = _get_temps()
    if not lines:
        if _IS_WINDOWS:
            return (
                "Temperature sensors not available via psutil on this Windows setup.\n"
                "Install WMI for richer hardware data:  pip install wmi\n"
                "Or use HWiNFO64 / HWMonitor for visual temp monitoring."
            )
        return "No temperature sensors found."
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------


def register(registry) -> None:
    registry.register(
        "system_stats",
        system_stats,
        description="Full system snapshot: CPU%, per-core usage, RAM, swap, disk space for all drives, network throughput, uptime, and temperatures.",
        category="system",
        args=[],
    )
    registry.register(
        "cpu_usage",
        cpu_usage,
        description="Show current CPU usage overall and per-core with a bar chart. Optionally adjust measurement interval.",
        category="system",
        args=[
            {
                "name": "interval",
                "required": False,
                "description": "Measurement window in seconds (default 1.0)",
            },
            {
                "name": "per_core",
                "required": False,
                "description": "Show per-core breakdown (default True)",
            },
        ],
    )
    registry.register(
        "memory_details",
        memory_details,
        description="Detailed RAM and swap breakdown plus top 10 memory-consuming processes.",
        category="system",
        args=[],
    )
    registry.register(
        "disk_usage",
        disk_usage,
        description="Disk space usage for a drive or path with real-time read/write throughput.",
        category="system",
        args=[
            {
                "name": "path",
                "required": False,
                "description": "Drive or path to check (e.g. 'C:\\\\' on Windows)",
            },
        ],
    )
    registry.register(
        "top_resource_hogs",
        top_resource_hogs,
        description="Rank processes by CPU or memory consumption with visual usage bars.",
        category="system",
        args=[
            {"name": "resource", "required": False, "description": "'cpu' (default) or 'memory'"},
            {"name": "top_n", "required": False, "description": "How many to show (default 10)"},
        ],
    )
    registry.register(
        "hardware_temps",
        hardware_temps,
        description="Read CPU, GPU, and drive temperatures from hardware sensors. Flags readings near high/critical thresholds.",
        category="system",
        args=[],
    )
