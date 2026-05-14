"""
service_manager.py — Windows service management plugin.

Tools provided:
  list_services        — List all services with status/start-type filter
  service_details      — Full details on a single service
  start_service        — Start a stopped service
  stop_service         — Stop a running service
  restart_service      — Stop then start a service
  enable_service       — Set start type to Automatic
  disable_service      — Set start type to Disabled

Tier 2 dependency: pip install wmi pywin32
Gracefully degrades: if wmi/win32service not available, returns a clear
install instruction instead of crashing.
"""

from __future__ import annotations

import subprocess

# ---------------------------------------------------------------------------
# Dependency guard — Tier 2 requires wmi + pywin32
# ---------------------------------------------------------------------------

_WMI_AVAILABLE = False
_WIN32_AVAILABLE = False

try:
    import wmi as _wmi_mod  # noqa: F401

    _WMI_AVAILABLE = True
except ImportError:
    pass

try:
    import win32con as _w32con  # noqa: F401
    import win32service as _w32svc  # noqa: F401

    _WIN32_AVAILABLE = True
except ImportError:
    pass

_TIER2_MSG = (
    "Service manager requires Tier 2 dependencies.\n"
    "Install with:  pip install wmi pywin32\n"
    "Then restart the assistant."
)

# ---------------------------------------------------------------------------
# Start-type constants (SC_START_TYPE values from WMI Win32_Service)
# ---------------------------------------------------------------------------

_START_TYPE_MAP = {
    "Auto": "Automatic",
    "Manual": "Manual",
    "Disabled": "Disabled",
    "Boot": "Boot",
    "System": "System",
}

_STATUS_LABELS = {
    "Running": "✅ Running",
    "Stopped": "⛔ Stopped",
    "Paused": "⏸ Paused",
    "StartPending": "🔄 Starting",
    "StopPending": "🔄 Stopping",
    "PausePending": "🔄 Pausing",
    "ContinuePending": "🔄 Resuming",
    "Unknown": "❓ Unknown",
}


def _wmi_conn():
    """Return a live WMI connection (or raise with a helpful message)."""
    if not _WMI_AVAILABLE:
        raise RuntimeError(_TIER2_MSG)
    import wmi

    return wmi.WMI()


def _sc(args: list[str]) -> tuple[int, str]:
    """
    Run sc.exe (Windows Service Control) and return (returncode, output).
    sc.exe ships with every Windows version — no extra deps needed for
    start/stop/config actions.
    """
    result = subprocess.run(
        ["sc"] + args,
        capture_output=True,
        text=True,
        timeout=15,
    )
    output = (result.stdout + result.stderr).strip()
    return result.returncode, output


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def list_services(
    status_filter: str = "all",
    start_type_filter: str = "all",
    max_results: int = 100,
) -> str:
    """
    List Windows services filtered by status and/or start type.

    Args:
        status_filter:     'all' | 'running' | 'stopped' | 'paused'
        start_type_filter: 'all' | 'auto' | 'manual' | 'disabled'
        max_results:       Cap on services returned (default 100).
    """
    try:
        c = _wmi_conn()
    except RuntimeError as e:
        return str(e)

    status_filter = status_filter.lower()
    start_type_filter = start_type_filter.lower()

    try:
        services = c.Win32_Service()
    except Exception as e:
        return f"[WMI error] {e}"

    rows: list[dict] = []
    for svc in services:
        state = (svc.State or "Unknown").strip()
        start = (svc.StartMode or "Unknown").strip()

        # Apply filters
        if status_filter != "all" and state.lower() != status_filter:
            continue
        if start_type_filter != "all" and start.lower() != start_type_filter:
            continue

        rows.append(
            {
                "name": svc.Name or "",
                "display": svc.DisplayName or "",
                "state": state,
                "start_mode": start,
                "pid": svc.ProcessId or 0,
            }
        )

    rows.sort(key=lambda r: r["display"].lower())
    rows = rows[:max_results]

    if not rows:
        return f"No services matched (status={status_filter}, start_type={start_type_filter})."

    lines = [
        f"{'Display Name':<45} {'State':<12} {'Start':<10} {'PID'}",
        "-" * 80,
    ]
    for r in rows:
        status_label = _STATUS_LABELS.get(r["state"], r["state"])
        lines.append(
            f"{r['display'][:44]:<45} {status_label:<12} {r['start_mode']:<10} {r['pid'] or '-'}"
        )

    lines.append(f"\nTotal: {len(rows)} service(s) shown")
    if len(rows) == max_results:
        lines.append(f"(limited to {max_results} — increase max_results to see more)")
    return "\n".join(lines)


def service_details(service_name: str) -> str:
    """
    Show full details for a single service.

    Args:
        service_name: The short service name (e.g. 'Spooler', 'wuauserv').
    """
    try:
        c = _wmi_conn()
    except RuntimeError as e:
        return str(e)

    try:
        matches = c.Win32_Service(Name=service_name)
    except Exception as e:
        return f"[WMI error] {e}"

    if not matches:
        # Try case-insensitive search
        try:
            all_svcs = c.Win32_Service()
            matches = [s for s in all_svcs if (s.Name or "").lower() == service_name.lower()]
        except Exception:
            matches = []

    if not matches:
        return f"Service '{service_name}' not found. Use list_services to see available services."

    svc = matches[0]
    state = svc.State or "Unknown"
    status_icon = _STATUS_LABELS.get(state, state)

    lines = [
        f"Service: {svc.DisplayName}",
        f"  Short name:   {svc.Name}",
        f"  Status:       {status_icon}",
        f"  Start type:   {svc.StartMode}",
        f"  PID:          {svc.ProcessId or 'N/A (not running)'}",
        f"  Path:         {svc.PathName or 'N/A'}",
        f"  Account:      {svc.StartName or 'N/A'}",
        f"  Description:  {(svc.Description or 'N/A')[:200]}",
        f"  Accepts stop: {svc.AcceptStop}",
        f"  Error control:{svc.ErrorControl}",
        f"  Caption:      {svc.Caption or 'N/A'}",
    ]

    # Dependencies
    try:
        deps = c.Win32_DependentService(Antecedent=svc.path_())
        dep_names = [d.Dependent.Name for d in deps if d.Dependent]
        if dep_names:
            lines.append(f"  Dependents:   {', '.join(dep_names)}")
    except Exception:
        pass

    return "\n".join(lines)


def start_service(service_name: str) -> str:
    """
    Start a Windows service.

    Args:
        service_name: Short service name (e.g. 'Spooler').
    """
    rc, out = _sc(["start", service_name])
    if rc == 0 or "START_PENDING" in out or "RUNNING" in out:
        return f"✅ Service '{service_name}' started successfully.\n{out}"
    if "1056" in out or "already running" in out.lower():
        return f"ℹ️  Service '{service_name}' is already running."
    return f"❌ Failed to start '{service_name}' (exit {rc}):\n{out}"


def stop_service(service_name: str, force: bool = False) -> str:
    """
    Stop a Windows service.

    Args:
        service_name: Short service name (e.g. 'Spooler').
        force:        If True, also stop dependent services first.
    """
    args = ["stop"]
    if force:
        args.append("/f")
    args.append(service_name)

    rc, out = _sc(args)
    if rc == 0 or "STOP_PENDING" in out or "STOPPED" in out:
        return f"✅ Service '{service_name}' stopped.\n{out}"
    if "1062" in out or "not started" in out.lower():
        return f"ℹ️  Service '{service_name}' is already stopped."
    if "1051" in out or "dependent" in out.lower():
        return (
            f"⚠️  '{service_name}' has dependent services still running.\n"
            f"Use stop_service(service_name, force=True) to stop dependents first.\n{out}"
        )
    return f"❌ Failed to stop '{service_name}' (exit {rc}):\n{out}"


def restart_service(service_name: str) -> str:
    """
    Restart a Windows service (stop then start).

    Args:
        service_name: Short service name (e.g. 'Spooler').
    """
    stop_result = stop_service(service_name)
    if "❌" in stop_result:
        return f"Restart aborted — could not stop service:\n{stop_result}"

    start_result = start_service(service_name)
    return f"Restart result for '{service_name}':\n{stop_result}\n{start_result}"


def enable_service(service_name: str, start_type: str = "auto") -> str:
    """
    Set a service's start type to Automatic (or Manual).

    Args:
        service_name: Short service name.
        start_type:   'auto' (default) | 'manual'
    """
    start_map = {"auto": "auto", "automatic": "auto", "manual": "demand"}
    sc_start = start_map.get(start_type.lower(), "auto")

    rc, out = _sc(["config", service_name, f"start={sc_start}"])
    if rc == 0 or "SUCCESS" in out:
        friendly = "Automatic" if sc_start == "auto" else "Manual"
        return f"✅ Service '{service_name}' set to {friendly} start.\n{out}"
    return f"❌ Failed to configure '{service_name}' (exit {rc}):\n{out}"


def disable_service(service_name: str) -> str:
    """
    Set a service's start type to Disabled (prevents it from starting).

    Args:
        service_name: Short service name.
    """
    # Stop it first if running
    stop_result = stop_service(service_name)

    rc, out = _sc(["config", service_name, "start=disabled"])
    if rc == 0 or "SUCCESS" in out:
        return f"✅ Service '{service_name}' disabled.\n{stop_result}\n{out}"
    return f"❌ Failed to disable '{service_name}' (exit {rc}):\n{out}"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(registry) -> None:
    registry.register(
        "list_services",
        list_services,
        description=(
            "List Windows services filtered by status (running/stopped/all) "
            "and start type (auto/manual/disabled/all)."
        ),
        category="system",
        args=[
            {
                "name": "status_filter",
                "required": False,
                "description": "Filter by status: 'all' (default), 'running', 'stopped', 'paused'",
            },
            {
                "name": "start_type_filter",
                "required": False,
                "description": "Filter by start type: 'all' (default), 'auto', 'manual', 'disabled'",
            },
            {
                "name": "max_results",
                "required": False,
                "description": "Maximum number of services to return (default 100)",
            },
        ],
    )

    registry.register(
        "service_details",
        service_details,
        description="Get full details about a specific Windows service by its short name.",
        category="system",
        args=[
            {
                "name": "service_name",
                "required": True,
                "description": "Short service name (e.g. 'Spooler', 'wuauserv', 'bits')",
            },
        ],
    )

    registry.register(
        "start_service",
        start_service,
        description="Start a Windows service.",
        category="system",
        args=[
            {
                "name": "service_name",
                "required": True,
                "description": "Short service name to start",
            },
        ],
    )

    registry.register(
        "stop_service",
        stop_service,
        description="Stop a Windows service. Use force=True to also stop dependent services.",
        category="system",
        args=[
            {
                "name": "service_name",
                "required": True,
                "description": "Short service name to stop",
            },
            {
                "name": "force",
                "required": False,
                "description": "If True, stop dependent services first (default False)",
            },
        ],
    )

    registry.register(
        "restart_service",
        restart_service,
        description="Stop then start a Windows service.",
        category="system",
        args=[
            {
                "name": "service_name",
                "required": True,
                "description": "Short service name to restart",
            },
        ],
    )

    registry.register(
        "enable_service",
        enable_service,
        description="Set a Windows service start type to Automatic or Manual.",
        category="system",
        args=[
            {
                "name": "service_name",
                "required": True,
                "description": "Short service name",
            },
            {
                "name": "start_type",
                "required": False,
                "description": "'auto' (default) or 'manual'",
            },
        ],
    )

    registry.register(
        "disable_service",
        disable_service,
        description=(
            "Disable a Windows service — stops it and sets start type to Disabled "
            "so it won't start automatically or manually."
        ),
        category="system",
        args=[
            {
                "name": "service_name",
                "required": True,
                "description": "Short service name to disable",
            },
        ],
    )
