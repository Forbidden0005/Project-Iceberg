"""
event_log_reader.py — Windows Event Log reader plugin.

Tools provided:
  list_event_logs    — Show available event log channels
  read_event_log     — Read recent entries from a log (System, Application, Security)
  search_event_log   — Search logs by keyword, event ID, or source
  recent_errors      — Quick summary of recent errors and warnings across all logs
  clear_event_log    — Clear a specific event log (requires admin)

Primary path: win32evtlog from pywin32 (Tier 2, already installed).
Fallback path: wevtutil.exe (built into Windows — always available).
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# Dependency detection
# ---------------------------------------------------------------------------

_WIN32EVTLOG_AVAILABLE = False
try:
    import win32evtlog
    import win32evtlogutil

    _WIN32EVTLOG_AVAILABLE = True
except ImportError:
    pass

_LEVEL_LABELS = {
    1: "🔴 Critical",
    2: "❌ Error",
    3: "⚠️  Warning",
    4: "ℹ️  Info",
    5: "🔍 Verbose",
}

_COMMON_LOGS = ["System", "Application", "Security"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_wevtutil(args: list[str], timeout: int = 15) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["wevtutil"] + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return -1, "[wevtutil timed out]"
    except FileNotFoundError:
        return -1, "[wevtutil.exe not found — this tool requires Windows]"


def _fmt_time(t: Any) -> str:
    """Format a pywintypes.datetime or datetime object."""
    try:
        return t.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(t)


# ---------------------------------------------------------------------------
# Tool: list_event_logs
# ---------------------------------------------------------------------------


def list_event_logs() -> str:
    """
    List available Windows Event Log channels.
    """
    rc, out = _run_wevtutil(["el"])
    if rc != 0:
        return f"[wevtutil error] {out}"

    channels = [line.strip() for line in out.splitlines() if line.strip()]
    common = [c for c in channels if c in _COMMON_LOGS]
    apps = [c for c in channels if "/" not in c and c not in _COMMON_LOGS]
    others = [c for c in channels if "/" in c]

    lines = [
        f"Available event logs: {len(channels)} total",
        "",
        "Core logs:",
    ]
    for c in common:
        lines.append(f"  {c}")

    lines.append(f"\nApplication logs ({len(apps)}):")
    for c in apps[:20]:
        lines.append(f"  {c}")
    if len(apps) > 20:
        lines.append(f"  … and {len(apps)-20} more")

    lines.append(f"\nService/component logs ({len(others)}) — use read_event_log('<name>')")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: read_event_log (win32evtlog path)
# ---------------------------------------------------------------------------


def _read_via_win32(
    log_name: str,
    max_entries: int,
    level: str,
    hours_back: int,
) -> str:
    """Read event log via pywin32 (faster, richer data than wevtutil)."""
    level_map = {
        "all": None,
        "critical": 1,
        "error": 2,
        "warning": 3,
        "info": 4,
    }
    target_level = level_map.get(level.lower())
    cutoff = datetime.now() - timedelta(hours=hours_back) if hours_back > 0 else None

    try:
        handle = win32evtlog.OpenEventLog(None, log_name)
    except Exception as e:
        return f"[Cannot open log '{log_name}'] {e}"

    flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
    entries: list[str] = []

    try:
        while len(entries) < max_entries:
            events = win32evtlog.ReadEventLog(handle, flags, 0)
            if not events:
                break
            for evt in events:
                if len(entries) >= max_entries:
                    break

                # Time filter
                evt_time = evt.TimeGenerated
                if cutoff:
                    try:
                        evt_dt = datetime(
                            evt_time.year,
                            evt_time.month,
                            evt_time.day,
                            evt_time.hour,
                            evt_time.minute,
                            evt_time.second,
                        )
                        if evt_dt < cutoff:
                            # Events are newest-first; stop when we go past cutoff
                            return _format_entries(entries, log_name, max_entries)
                    except Exception:
                        pass

                # Level filter
                evt_level = getattr(evt, "EventType", 4)
                # EventType: 1=Error, 2=Warning, 4=Info, 8=Audit Success, 16=Audit Failure
                # Normalise to our 1-4 scale
                if evt_level == 1:
                    lvl = 2  # Error
                elif evt_level == 2:
                    lvl = 3  # Warning
                elif evt_level in (8, 16):
                    lvl = 4  # Audit
                else:
                    lvl = 4  # Info
                if target_level and lvl > target_level:
                    continue

                try:
                    msg = win32evtlogutil.SafeFormatMessage(evt, log_name)
                    msg = (msg or "").strip().replace("\r\n", " ").replace("\n", " ")[:200]
                except Exception:
                    msg = "(message unavailable)"

                label = _LEVEL_LABELS.get(lvl, "ℹ️  Info")
                entries.append(
                    f"[{_fmt_time(evt_time)}] {label:<14} "
                    f"Source: {evt.SourceName or '?':<30} ID: {evt.EventID & 0xFFFF:<6} {msg}"
                )
    finally:
        win32evtlog.CloseEventLog(handle)

    return _format_entries(entries, log_name, max_entries)


def _format_entries(entries: list[str], log_name: str, max_entries: int) -> str:
    if not entries:
        return f"No entries found in '{log_name}' matching the filter."
    lines = [f"Event log: {log_name}  ({len(entries)} entries)", "-" * 80]
    lines.extend(entries)
    if len(entries) == max_entries:
        lines.append(f"\n(showing first {max_entries} — increase max_entries to see more)")
    return "\n".join(lines)


def _read_via_wevtutil(
    log_name: str,
    max_entries: int,
    level: str,
    hours_back: int,
) -> str:
    """Fallback: read event log via wevtutil.exe query."""
    # Build XPath query
    level_xp = {
        "critical": "Level=1",
        "error": "Level=2",
        "warning": "Level=3",
        "info": "Level=4",
        "all": "",
    }.get(level.lower(), "")

    if hours_back > 0:
        ms_back = hours_back * 3600 * 1000
        time_xp = f"TimeCreated[timediff(@SystemTime) <= {ms_back}]"
    else:
        time_xp = ""

    conditions = [x for x in [level_xp, time_xp] if x]
    if conditions:
        xpath = f"*[System[{' and '.join(conditions)}]]"
    else:
        xpath = "*"

    args = [
        "qe",
        log_name,
        "/q:" + xpath,
        "/f:text",
        "/c:" + str(max_entries),
        "/rd:true",  # Read direction = newest first
    ]
    rc, out = _run_wevtutil(args, timeout=20)
    if rc != 0:
        return f"[wevtutil error reading '{log_name}'] {out}"

    return f"Event log: {log_name}\n{'-'*60}\n{out}"


def read_event_log(
    log_name: str = "System",
    max_entries: int = 50,
    level: str = "all",
    hours_back: int = 24,
) -> str:
    """
    Read recent entries from a Windows Event Log.

    Args:
        log_name:    Log to read: 'System', 'Application', 'Security', or any channel.
        max_entries: Number of entries to return (default 50).
        level:       Filter by level: 'all', 'critical', 'error', 'warning', 'info'.
        hours_back:  Only show events from last N hours (0 = no time filter, default 24).
    """
    if _WIN32EVTLOG_AVAILABLE:
        return _read_via_win32(log_name, max_entries, level, hours_back)
    return _read_via_wevtutil(log_name, max_entries, level, hours_back)


# ---------------------------------------------------------------------------
# Tool: search_event_log
# ---------------------------------------------------------------------------


def search_event_log(
    keyword: str,
    log_name: str = "all",
    hours_back: int = 48,
    max_results: int = 30,
) -> str:
    """
    Search event logs for a keyword, event ID, or source name.

    Args:
        keyword:   Text to search for in event messages or source names.
        log_name:  Which log to search: 'all', 'System', 'Application', 'Security'.
        hours_back: Search events from last N hours (default 48).
        max_results: Maximum matches to return (default 30).
    """
    if log_name == "all":
        logs_to_search = _COMMON_LOGS
    else:
        logs_to_search = [log_name]

    all_results: list[str] = []
    kw_lower = keyword.lower()

    for log in logs_to_search:
        if len(all_results) >= max_results:
            break

        if _WIN32EVTLOG_AVAILABLE:
            # Read last N hours and filter by keyword in memory
            raw = _read_via_win32(log, 1000, "all", hours_back)
        else:
            raw = _read_via_wevtutil(log, 1000, "all", hours_back)

        for line in raw.splitlines():
            if kw_lower in line.lower():
                all_results.append(f"[{log}] {line}")
                if len(all_results) >= max_results:
                    break

    if not all_results:
        return f"No events found matching '{keyword}' in {log_name} " f"(last {hours_back}h)."

    lines = [
        f"Search results for '{keyword}' in {log_name} (last {hours_back}h):",
        f"Found {len(all_results)} match(es):",
        "-" * 80,
    ]
    lines.extend(all_results)
    if len(all_results) == max_results:
        lines.append(f"\n(capped at {max_results} — reduce hours_back or be more specific)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: recent_errors
# ---------------------------------------------------------------------------


def recent_errors(hours_back: int = 24, max_per_log: int = 20) -> str:
    """
    Show recent errors and critical events across System, Application, and Security logs.

    Args:
        hours_back:  How many hours to look back (default 24).
        max_per_log: Maximum errors per log (default 20).
    """
    lines = [
        f"Recent errors and critical events (last {hours_back}h):",
        "=" * 70,
    ]

    for log in _COMMON_LOGS:
        if _WIN32EVTLOG_AVAILABLE:
            section = _read_via_win32(log, max_per_log, "error", hours_back)
        else:
            section = _read_via_wevtutil(log, max_per_log, "error", hours_back)

        lines.append(f"\n{log} log:")
        lines.append("-" * 40)
        lines.append(section)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: clear_event_log
# ---------------------------------------------------------------------------


def clear_event_log(log_name: str, dry_run: bool = True) -> str:
    """
    Clear all entries from a Windows Event Log.

    Requires Administrator privileges.

    Args:
        log_name: Log to clear: 'System', 'Application', 'Security', etc.
        dry_run:  Show what would be cleared without doing it (default True).
    """
    if dry_run:
        return (
            f"[DRY RUN] Would clear all entries from '{log_name}' event log.\n"
            f"Run with dry_run=False to actually clear it.\n"
            f"⚠️  This is irreversible. Cleared events cannot be recovered."
        )

    rc, out = _run_wevtutil(["cl", log_name], timeout=15)
    if rc == 0:
        return f"✅ Event log '{log_name}' cleared successfully."
    return (
        f"❌ Failed to clear '{log_name}' (exit {rc}):\n{out}\n(May require Administrator rights.)"
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(registry) -> None:
    registry.register(
        "list_event_logs",
        list_event_logs,
        description="List all available Windows Event Log channels (System, Application, Security, etc.).",
        category="system",
        args=[],
    )

    registry.register(
        "read_event_log",
        read_event_log,
        description=(
            "Read recent entries from a Windows Event Log. "
            "Specify log_name ('System', 'Application', 'Security'), "
            "level filter ('all', 'error', 'warning', 'critical'), "
            "and how many hours back to look."
        ),
        category="system",
        args=[
            {
                "name": "log_name",
                "required": False,
                "description": "Log name: 'System' (default), 'Application', 'Security', or any channel",
            },
            {
                "name": "max_entries",
                "required": False,
                "description": "Max entries to return (default 50)",
            },
            {
                "name": "level",
                "required": False,
                "description": "Level filter: 'all' (default), 'critical', 'error', 'warning', 'info'",
            },
            {
                "name": "hours_back",
                "required": False,
                "description": "Hours to look back (default 24, 0 = no limit)",
            },
        ],
    )

    registry.register(
        "search_event_log",
        search_event_log,
        description=(
            "Search Windows Event Logs for a keyword, error message, event ID, or source name. "
            "Searches System, Application, and Security logs by default."
        ),
        category="system",
        args=[
            {
                "name": "keyword",
                "required": True,
                "description": "Text to search for in event messages",
            },
            {
                "name": "log_name",
                "required": False,
                "description": "'all' (default), 'System', 'Application', 'Security'",
            },
            {
                "name": "hours_back",
                "required": False,
                "description": "Hours to search back (default 48)",
            },
            {
                "name": "max_results",
                "required": False,
                "description": "Maximum matches to return (default 30)",
            },
        ],
    )

    registry.register(
        "recent_errors",
        recent_errors,
        description=(
            "Quick summary of recent errors and critical events across all core Windows logs "
            "(System, Application, Security). Good first step when troubleshooting."
        ),
        category="system",
        args=[
            {
                "name": "hours_back",
                "required": False,
                "description": "Hours to look back (default 24)",
            },
            {
                "name": "max_per_log",
                "required": False,
                "description": "Max errors per log (default 20)",
            },
        ],
    )

    registry.register(
        "clear_event_log",
        clear_event_log,
        description=(
            "Clear all entries from a Windows Event Log. "
            "dry_run=True by default — set False to actually clear. "
            "Requires Administrator privileges."
        ),
        category="system",
        args=[
            {
                "name": "log_name",
                "required": True,
                "description": "Log to clear: 'System', 'Application', 'Security', etc.",
            },
            {
                "name": "dry_run",
                "required": False,
                "description": "Preview without clearing (default True — set False to clear)",
            },
        ],
    )
