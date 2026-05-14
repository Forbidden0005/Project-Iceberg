"""
Process monitor and task killer for Project Iceberg.

Provides deep process inspection, anomaly detection, and forceful termination.
Requires: pip install psutil

All tools work on Windows, macOS, and Linux.  Windows-specific enrichment
(publisher, signature path checks) degrades gracefully on other platforms.
"""

import platform
from datetime import datetime
from pathlib import Path

try:
    import psutil

    _PSUTIL = True
except ImportError:
    _PSUTIL = False

_IS_WINDOWS = platform.system() == "Windows"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WINDOWS_SYSTEM_DIRS = {
    "c:\\windows\\system32",
    "c:\\windows\\syswow64",
    "c:\\windows",
    "c:\\program files",
    "c:\\program files (x86)",
}

_SUSPICIOUS_EXTENSIONS = {".tmp", ".dat", ".bin"}  # exes with these names are red flags

_KNOWN_SAFE_NAMES = {
    # Common system processes — not exhaustive, just reduces noise
    "system",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "services.exe",
    "lsass.exe",
    "svchost.exe",
    "explorer.exe",
    "taskhostw.exe",
    "dwm.exe",
    "conhost.exe",
    "fontdrvhost.exe",
    "winlogon.exe",
    "spoolsv.exe",
    "SearchIndexer.exe",
    "audiodg.exe",
}


def _proc_info(proc: "psutil.Process") -> dict:
    """Collect safe process info; skip fields that raise AccessDenied."""
    info: dict = {"pid": proc.pid}
    try:
        info["name"] = proc.name()
    except Exception:
        info["name"] = "?"
    try:
        info["exe"] = proc.exe()
    except Exception:
        info["exe"] = ""
    try:
        info["status"] = proc.status()
    except Exception:
        info["status"] = "?"
    try:
        info["cpu_pct"] = proc.cpu_percent(interval=0.1)
    except Exception:
        info["cpu_pct"] = 0.0
    try:
        mem = proc.memory_info()
        info["mem_mb"] = round(mem.rss / 1024 / 1024, 1)
    except Exception:
        info["mem_mb"] = 0.0
    try:
        info["username"] = proc.username()
    except Exception:
        info["username"] = "?"
    try:
        info["cmdline"] = " ".join(proc.cmdline())[:200]
    except Exception:
        info["cmdline"] = ""
    try:
        ct = proc.create_time()
        info["started"] = datetime.fromtimestamp(ct).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        info["started"] = "?"
    return info


def _format_proc(info: dict, idx: int = 0) -> str:
    tag = f"[{idx}] " if idx else ""
    return (
        f"{tag}{info['name']} (PID {info['pid']})\n"
        f"    CPU: {info['cpu_pct']:.1f}%  |  RAM: {info['mem_mb']} MB  |  "
        f"Status: {info['status']}  |  User: {info['username']}\n"
        f"    Started: {info['started']}\n"
        f"    Path: {info['exe'] or '(unknown)'}"
    )


def _anomaly_flags(info: dict) -> list[str]:
    """Return a list of human-readable suspicion reasons for a process."""
    flags: list[str] = []
    exe = (info.get("exe") or "").lower()
    name = (info.get("name") or "").lower()

    # High resource usage
    if info.get("cpu_pct", 0) > 80:
        flags.append(f"Very high CPU ({info['cpu_pct']:.0f}%)")
    if info.get("mem_mb", 0) > 1500:
        flags.append(f"Very high RAM ({info['mem_mb']:.0f} MB)")

    # Running from temp or user-writable directories
    if exe:
        suspicious_paths = [
            "\\temp\\",
            "\\tmp\\",
            "\\appdata\\local\\temp\\",
            "\\downloads\\",
            "\\desktop\\",
            "\\users\\public\\",
        ]
        for sp in suspicious_paths:
            if sp in exe:
                sp_clean = sp.strip("\\")
                flags.append(f"Running from writable dir: {sp_clean}")
                break

    # Executable name looks like a random hash or has suspicious extension
    stem = Path(exe).stem.lower() if exe else ""
    if len(stem) > 20 and stem.isalnum() and stem not in _KNOWN_SAFE_NAMES:
        flags.append("Name looks like random hash")

    # Masquerading as system process but not in system dir
    if name in {n.lower() for n in _KNOWN_SAFE_NAMES} and exe:
        in_system = any(exe.startswith(d) for d in _WINDOWS_SYSTEM_DIRS)
        if not in_system and _IS_WINDOWS:
            flags.append("Name matches system process but runs from non-system path")

    # No exe path at all (process hiding itself)
    if not exe and info.get("pid", 0) > 4:
        flags.append("No executable path (possible hiding)")

    return flags


# ---------------------------------------------------------------------------
# Public tool functions
# ---------------------------------------------------------------------------


def list_processes(
    sort_by: str = "cpu",
    top_n: int = 20,
    filter_user: str = "",
) -> str:
    """
    List running processes sorted by CPU or memory usage.

    Args:
        sort_by:      "cpu" (default), "memory", "name", or "pid".
        top_n:        How many to show (default 20, max 100).
        filter_user:  Only show processes owned by this username (optional).

    Returns:
        Formatted table of running processes with PID, CPU%, RAM, status, path.
    """
    if not _PSUTIL:
        return "[error] psutil not installed — run: pip install psutil"

    top_n = max(1, min(top_n, 100))
    procs: list[dict] = []

    for proc in psutil.process_iter():
        try:
            info = _proc_info(proc)
            if filter_user and filter_user.lower() not in info.get("username", "").lower():
                continue
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Sort
    key_map = {
        "cpu": lambda p: p.get("cpu_pct", 0),
        "memory": lambda p: p.get("mem_mb", 0),
        "name": lambda p: p.get("name", "").lower(),
        "pid": lambda p: p.get("pid", 0),
    }
    sort_key = key_map.get(sort_by.lower(), key_map["cpu"])
    reverse = sort_by.lower() not in ("name", "pid")
    procs.sort(key=sort_key, reverse=reverse)

    shown = procs[:top_n]
    lines = [
        f"Running processes — sorted by {sort_by} (showing {len(shown)} of {len(procs)} total)\n"
    ]
    for i, p in enumerate(shown, 1):
        lines.append(_format_proc(p, i))

    return "\n\n".join(lines)


def process_details(pid_or_name: str) -> str:
    """
    Show detailed information about a specific process.

    Args:
        pid_or_name: Process ID (number) or process name (e.g. "chrome.exe").
                     If a name matches multiple processes, all are shown.

    Returns:
        Detailed process info including open files, network connections, threads,
        parent process, environment variables (truncated), and memory breakdown.
    """
    if not _PSUTIL:
        return "[error] psutil not installed — run: pip install psutil"

    targets: list[psutil.Process] = []
    pid_or_name = pid_or_name.strip()

    # Try PID first
    if pid_or_name.isdigit():
        try:
            targets = [psutil.Process(int(pid_or_name))]
        except psutil.NoSuchProcess:
            return f"No process with PID {pid_or_name}"
    else:
        name_lower = pid_or_name.lower()
        for proc in psutil.process_iter():
            try:
                if name_lower in proc.name().lower():
                    targets.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    if not targets:
        return f"No process found matching: {pid_or_name}"

    sections: list[str] = []
    for proc in targets[:5]:  # Cap at 5 matches
        info = _proc_info(proc)
        lines = [f"=== {info['name']} (PID {info['pid']}) ==="]
        lines.append(f"Status:    {info['status']}")
        lines.append(f"User:      {info['username']}")
        lines.append(f"CPU:       {info['cpu_pct']:.1f}%")
        lines.append(f"RAM:       {info['mem_mb']} MB")
        lines.append(f"Started:   {info['started']}")
        lines.append(f"Exe:       {info['exe'] or '(unknown)'}")
        if info["cmdline"]:
            lines.append(f"CmdLine:   {info['cmdline']}")

        # Parent
        try:
            parent = proc.parent()
            if parent:
                lines.append(f"Parent:    {parent.name()} (PID {parent.pid})")
        except Exception:
            pass

        # Children
        try:
            children = proc.children()
            if children:
                child_strs = [f"{c.name()} ({c.pid})" for c in children[:10]]
                lines.append(f"Children:  {', '.join(child_strs)}")
        except Exception:
            pass

        # Memory breakdown
        try:
            mem = (
                proc.memory_full_info() if hasattr(proc, "memory_full_info") else proc.memory_info()
            )
            lines.append(f"RSS:       {round(mem.rss/1024/1024, 1)} MB (physical)")
            lines.append(f"VMS:       {round(mem.vms/1024/1024, 1)} MB (virtual)")
        except Exception:
            pass

        # Network connections
        try:
            conns = proc.net_connections()
            if conns:
                lines.append(f"\nNetwork connections ({len(conns)}):")
                for c in conns[:8]:
                    laddr = f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "-"
                    raddr = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "-"
                    lines.append(f"  {laddr} -> {raddr}  [{c.status}]")
        except Exception:
            pass

        # Open files (capped)
        try:
            files = proc.open_files()
            if files:
                lines.append(f"\nOpen files ({min(len(files), 8)} shown):")
                for f in files[:8]:
                    lines.append(f"  {f.path}")
        except Exception:
            pass

        # Threads
        try:
            n_threads = proc.num_threads()
            lines.append(f"\nThreads:   {n_threads}")
        except Exception:
            pass

        # Anomaly flags
        flags = _anomaly_flags(info)
        if flags:
            lines.append("\n⚠  Suspicion flags:")
            for f in flags:
                lines.append(f"   • {f}")

        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def find_suspicious_processes(
    cpu_threshold: float = 70.0,
    mem_threshold_mb: float = 800.0,
) -> str:
    """
    Scan all running processes and flag anything suspicious or anomalous.

    Checks for: high CPU/RAM usage, processes running from temp/download dirs,
    names that mimic system processes but run from wrong paths, no executable
    path (possible rootkit hiding), and unusually long random-looking names.

    Args:
        cpu_threshold:    Flag processes using more than this % CPU (default 70).
        mem_threshold_mb: Flag processes using more than this MB RAM (default 800).

    Returns:
        Report of suspicious processes with specific reasons, or a clean-bill
        if nothing looks off.
    """
    if not _PSUTIL:
        return "[error] psutil not installed — run: pip install psutil"

    findings: list[tuple[dict, list[str]]] = []

    for proc in psutil.process_iter():
        try:
            info = _proc_info(proc)
            # Override thresholds with caller's values
            if info.get("cpu_pct", 0) > cpu_threshold:
                pass  # will be caught by _anomaly_flags with default thresholds
            flags = _anomaly_flags(info)
            # Also check caller thresholds
            if info.get("cpu_pct", 0) > cpu_threshold and "Very high CPU" not in " ".join(flags):
                flags.append(f"High CPU ({info['cpu_pct']:.0f}% > {cpu_threshold:.0f}% threshold)")
            if info.get("mem_mb", 0) > mem_threshold_mb and "Very high RAM" not in " ".join(flags):
                flags.append(
                    f"High RAM ({info['mem_mb']:.0f} MB > {mem_threshold_mb:.0f} MB threshold)"
                )
            if flags:
                findings.append((info, flags))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not findings:
        return (
            "✓ No suspicious processes detected.\n"
            f"  Scanned {sum(1 for _ in psutil.process_iter())} running processes.\n"
            f"  CPU threshold: {cpu_threshold}%  |  RAM threshold: {mem_threshold_mb} MB"
        )

    lines = [
        f"⚠  Suspicious process scan — {len(findings)} finding(s)\n"
        f"   CPU threshold: {cpu_threshold}%  |  RAM threshold: {mem_threshold_mb} MB\n"
    ]
    for info, flags in sorted(findings, key=lambda x: x[0].get("cpu_pct", 0), reverse=True):
        lines.append(_format_proc(info))
        for f in flags:
            lines.append(f"   ⚠  {f}")

    return "\n\n".join(lines)


def kill_process(
    pid_or_name: str,
    force: bool = False,
    kill_children: bool = False,
) -> str:
    """
    Kill a process by PID or name.

    Tries graceful termination first (SIGTERM / TerminateProcess), waits 3
    seconds, then force-kills if the process is still alive or force=True.

    Args:
        pid_or_name:   Process ID number or process name (e.g. "notepad.exe").
                       If a name matches multiple processes, ALL are killed.
        force:         Skip graceful attempt and force-kill immediately.
        kill_children: Also kill all child processes first (default False).

    Returns:
        Summary of which processes were killed or any errors encountered.
    """
    if not _PSUTIL:
        return "[error] psutil not installed — run: pip install psutil"

    targets: list[psutil.Process] = []
    pid_or_name = str(pid_or_name).strip()

    if pid_or_name.isdigit():
        try:
            targets = [psutil.Process(int(pid_or_name))]
        except psutil.NoSuchProcess:
            return f"No process with PID {pid_or_name}"
    else:
        name_lower = pid_or_name.lower()
        for proc in psutil.process_iter():
            try:
                if name_lower in proc.name().lower():
                    targets.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    if not targets:
        return f"No process found matching: {pid_or_name}"

    results: list[str] = []
    for proc in targets:
        name = "?"
        pid = proc.pid
        try:
            name = proc.name()
        except Exception:
            pass

        try:
            # Collect children before killing parent
            children: list[psutil.Process] = []
            if kill_children:
                try:
                    children = proc.children(recursive=True)
                except Exception:
                    pass

            if force:
                proc.kill()
                results.append(f"✓ Force-killed {name} (PID {pid})")
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                    results.append(f"✓ Terminated {name} (PID {pid})")
                except psutil.TimeoutExpired:
                    proc.kill()
                    results.append(f"✓ Force-killed {name} (PID {pid}) — graceful timeout")

            # Kill children
            for child in children:
                try:
                    c_name = child.name()
                    child.kill()
                    results.append(f"  ✓ Killed child {c_name} (PID {child.pid})")
                except Exception as e:
                    results.append(f"  ✗ Child PID {child.pid}: {e}")

        except psutil.AccessDenied:
            results.append(f"✗ Access denied killing {name} (PID {pid}) — try running as admin")
        except psutil.NoSuchProcess:
            results.append(f"✗ {name} (PID {pid}) already gone")
        except Exception as e:
            results.append(f"✗ Error killing {name} (PID {pid}): {e}")

    return "\n".join(results)


def kill_process_tree(pid: str) -> str:
    """
    Kill a process AND all of its descendant child processes.

    Args:
        pid: Process ID of the root process to kill.

    Returns:
        Summary of all processes killed.
    """
    return kill_process(pid, force=True, kill_children=True)


def kill_by_port(port: int) -> str:
    """
    Find and kill the process listening on a specific TCP/UDP port.

    Args:
        port: Port number (e.g. 8080, 3000, 5432).

    Returns:
        Which process was killed, or a message if no process owns that port.
    """
    if not _PSUTIL:
        return "[error] psutil not installed — run: pip install psutil"

    for conn in psutil.net_connections():
        if conn.laddr and conn.laddr.port == int(port) and conn.pid:
            try:
                proc = psutil.Process(conn.pid)
                name = proc.name()
                return kill_process(str(conn.pid), force=True)
            except Exception as e:
                return f"Found PID {conn.pid} on port {port} but could not kill: {e}"

    return f"No process found listening on port {port}"


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------


def register(registry) -> None:
    registry.register(
        "list_processes",
        list_processes,
        description="List all running processes sorted by CPU or memory. Shows PID, CPU%, RAM, status, path.",
        category="system",
        args=[
            {
                "name": "sort_by",
                "required": False,
                "description": "'cpu' (default), 'memory', 'name', or 'pid'",
            },
            {"name": "top_n", "required": False, "description": "How many to show (default 20)"},
            {"name": "filter_user", "required": False, "description": "Filter by username"},
        ],
    )
    registry.register(
        "process_details",
        process_details,
        description="Show deep details about a process: memory breakdown, open files, network connections, children, parent, suspicion flags.",
        category="system",
        args=[
            {
                "name": "pid_or_name",
                "required": True,
                "description": "PID number or process name (e.g. 'chrome.exe')",
            },
        ],
    )
    registry.register(
        "find_suspicious_processes",
        find_suspicious_processes,
        description="Scan all processes for anomalies: high CPU/RAM, running from temp dirs, masquerading as system processes, hidden executables.",
        category="system",
        args=[
            {
                "name": "cpu_threshold",
                "required": False,
                "description": "Flag above this CPU % (default 70)",
            },
            {
                "name": "mem_threshold_mb",
                "required": False,
                "description": "Flag above this MB RAM (default 800)",
            },
        ],
    )
    registry.register(
        "kill_process",
        kill_process,
        description="Kill a process by PID or name. Tries graceful termination first, then force-kills. Can kill all matching processes by name.",
        category="system",
        args=[
            {
                "name": "pid_or_name",
                "required": True,
                "description": "PID number or name like 'notepad.exe'",
            },
            {
                "name": "force",
                "required": False,
                "description": "Skip graceful and force-kill immediately (default False)",
            },
            {
                "name": "kill_children",
                "required": False,
                "description": "Also kill all child processes (default False)",
            },
        ],
    )
    registry.register(
        "kill_process_tree",
        kill_process_tree,
        description="Kill a process and ALL of its child processes by PID. Use when a parent has spawned workers you also need to stop.",
        category="system",
        args=[
            {"name": "pid", "required": True, "description": "PID of the root process"},
        ],
    )
    registry.register(
        "kill_by_port",
        kill_by_port,
        description="Find and kill whatever process is listening on a specific TCP/UDP port.",
        category="system",
        args=[
            {"name": "port", "required": True, "description": "Port number (e.g. 8080)"},
        ],
    )
