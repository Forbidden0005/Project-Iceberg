"""
uninstaller.py — Powerful Windows application uninstaller plugin.

Reads the installed-apps list directly from the registry (fast, unlike
Win32_Product WMI which triggers a repair/reinstall on every query).

Tools provided:
  list_installed_apps    — All installed software from registry (fast)
  uninstall_app          — Run an app's uninstall command
  find_ghost_installs    — Registry entries with no matching exe/dir
  find_app_leftovers     — Orphaned dirs/files after an app is removed
  app_install_details    — Full registry record for a single app

No Tier 2 deps required for listing/ghost detection (pure winreg stdlib).
Optional: wmi + pywin32 for richer publisher/version info.
"""

from __future__ import annotations

import os
import re
import subprocess
import winreg
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Registry paths for installed software
# ---------------------------------------------------------------------------

_UNINSTALL_KEYS: list[tuple] = [
    # (hive, key_path, arch_label)
    (
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        "HKLM 64-bit",
    ),
    (
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        "HKLM 32-bit",
    ),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "HKCU"),
]

# Common leftover directories to scan
_LEFTOVER_SEARCH_DIRS: list[Path] = [
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")),
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")),
    Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")),
    Path(os.environ.get("APPDATA", "")) / "Roaming",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Local",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Roaming",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _read_app_entry(key_handle, subkey_name: str) -> Optional[dict]:
    """Read one uninstall subkey into a dict, return None if it's a system update."""
    try:
        with winreg.OpenKey(key_handle, subkey_name, 0, winreg.KEY_READ) as sk:

            def _val(name: str, default: str = "") -> str:
                try:
                    v, _ = winreg.QueryValueEx(sk, name)
                    return str(v).strip()
                except FileNotFoundError:
                    return default

            display_name = _val("DisplayName")
            if not display_name:
                return None  # Skip anonymous entries (language packs, etc.)

            # Skip Windows system updates (KB######)
            if re.match(r"^(KB|Hotfix|Security Update|Update for)", display_name, re.IGNORECASE):
                return None

            return {
                "name": display_name,
                "version": _val("DisplayVersion"),
                "publisher": _val("Publisher"),
                "install_date": _val("InstallDate"),
                "install_dir": _val("InstallLocation"),
                "uninstall_cmd": _val("UninstallString"),
                "quiet_cmd": _val("QuietUninstallString"),
                "size_kb": _val("EstimatedSize", "0"),
                "system_comp": _val("SystemComponent", "0"),
                "no_remove": _val("NoRemove", "0"),
                "subkey": subkey_name,
            }
    except Exception:
        return None


def _all_apps(include_system: bool = False) -> list[dict]:
    """Return all installed apps from the registry (deduplicated by name)."""
    seen: set[str] = set()
    apps: list[dict] = []

    for hive, key_path, label in _UNINSTALL_KEYS:
        try:
            with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        i += 1
                    except OSError:
                        break
                    entry = _read_app_entry(key, subkey_name)
                    if entry is None:
                        continue
                    if not include_system and entry["system_comp"] == "1":
                        continue
                    entry["source"] = label
                    # Deduplicate by name (same app in 32+64 bit keys)
                    key_id = entry["name"].lower()
                    if key_id not in seen:
                        seen.add(key_id)
                        apps.append(entry)
        except (FileNotFoundError, PermissionError):
            pass

    return sorted(apps, key=lambda a: a["name"].lower())


# ---------------------------------------------------------------------------
# Tool: list_installed_apps
# ---------------------------------------------------------------------------


def list_installed_apps(
    search: str = "",
    publisher_filter: str = "",
    max_results: int = 200,
) -> str:
    """
    List installed Windows applications from the registry.

    Reads directly from registry (fast — does NOT trigger repair like
    Win32_Product WMI does).

    Args:
        search:           Filter by app name (case-insensitive substring).
        publisher_filter: Filter by publisher name substring.
        max_results:      Maximum results to return (default 200).
    """
    apps = _all_apps(include_system=False)

    if search:
        apps = [a for a in apps if search.lower() in a["name"].lower()]
    if publisher_filter:
        apps = [a for a in apps if publisher_filter.lower() in a["publisher"].lower()]

    apps = apps[:max_results]

    if not apps:
        hint = f" matching '{search}'" if search else ""
        return f"No installed apps found{hint}."

    lines = [
        f"{'Application':<50} {'Version':<16} {'Publisher':<30} {'Install Date':<13} {'Size'}",
        "-" * 125,
    ]
    total_kb = 0
    for a in apps:
        sz_kb = int(a["size_kb"]) if a["size_kb"].isdigit() else 0
        total_kb += sz_kb
        sz_str = _fmt_bytes(sz_kb * 1024) if sz_kb else "N/A"
        lines.append(
            f"{a['name'][:49]:<50} {a['version'][:15]:<16} {a['publisher'][:29]:<30} "
            f"{a['install_date']:<13} {sz_str}"
        )

    lines.append(f"\nTotal: {len(apps)} application(s)")
    if total_kb:
        lines.append(f"Estimated total size: {_fmt_bytes(total_kb * 1024)}")
    if len(apps) == max_results:
        lines.append(f"(results capped at {max_results} — use search= to narrow down)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: app_install_details
# ---------------------------------------------------------------------------


def app_install_details(app_name: str) -> str:
    """
    Show full registry details for a single installed application.

    Args:
        app_name: Full or partial app name (case-insensitive).
    """
    apps = _all_apps(include_system=True)
    matches = [a for a in apps if app_name.lower() in a["name"].lower()]

    if not matches:
        return f"No app found matching '{app_name}'. Try list_installed_apps to browse."

    lines = []
    for a in matches[:5]:  # Show up to 5 matches
        sz_kb = int(a["size_kb"]) if a["size_kb"].isdigit() else 0
        lines += [
            f"App:             {a['name']}",
            f"  Version:       {a['version'] or 'N/A'}",
            f"  Publisher:     {a['publisher'] or 'N/A'}",
            f"  Install date:  {a['install_date'] or 'N/A'}",
            f"  Install dir:   {a['install_dir'] or 'N/A'}",
            f"  Est. size:     {_fmt_bytes(sz_kb * 1024) if sz_kb else 'N/A'}",
            f"  Uninstall:     {a['uninstall_cmd'] or 'N/A'}",
            f"  Quiet uninst:  {a['quiet_cmd'] or 'N/A'}",
            f"  Can remove:    {'No' if a['no_remove'] == '1' else 'Yes'}",
            f"  Registry src:  {a['source']}  [{a['subkey'][:60]}]",
            "",
        ]
    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# Tool: uninstall_app
# ---------------------------------------------------------------------------


def uninstall_app(app_name: str, quiet: bool = False, dry_run: bool = True) -> str:
    """
    Run the uninstaller for an installed application.

    SAFETY: dry_run=True by default — shows what would run without executing.
    Set dry_run=False to actually uninstall.

    Args:
        app_name: Full or partial app name to uninstall.
        quiet:    Use quiet/silent uninstall command if available (default False).
        dry_run:  Show the uninstall command without running it (default True).
    """
    apps = _all_apps(include_system=False)
    matches = [a for a in apps if app_name.lower() in a["name"].lower()]

    if not matches:
        return f"No app matching '{app_name}'. Use list_installed_apps to browse."

    if len(matches) > 1:
        names = "\n".join(f"  - {a['name']}" for a in matches[:10])
        return (
            f"{len(matches)} apps matched '{app_name}'. Be more specific:\n{names}\n"
            f"{'…and more' if len(matches) > 10 else ''}"
        )

    app = matches[0]

    if app["no_remove"] == "1":
        return f"❌ '{app['name']}' is marked as non-removable by Windows."

    cmd = (app["quiet_cmd"] if quiet and app["quiet_cmd"] else app["uninstall_cmd"]).strip()
    if not cmd:
        return (
            f"❌ No uninstall command found for '{app['name']}'.\n"
            f"   Install dir: {app['install_dir'] or 'unknown'}\n"
            "   Try uninstalling via Settings → Apps or the app's own uninstaller."
        )

    if dry_run:
        return (
            f"[DRY RUN] Would uninstall '{app['name']}':\n"
            f"  Command: {cmd}\n"
            f"  Version: {app['version']}\n"
            f"  Publisher: {app['publisher']}\n\n"
            f"Re-run with dry_run=False to actually uninstall."
        )

    # Execute
    try:
        # Many uninstallers need to run in their own console
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            return (
                f"✅ Uninstall command completed for '{app['name']}'.\n"
                f"   Exit code: 0\n"
                f"   Note: Some uninstallers require a reboot to complete removal.\n"
                f"{result.stdout[:500] if result.stdout else ''}"
            )
        else:
            return (
                f"⚠️  Uninstaller exited with code {result.returncode} for '{app['name']}'.\n"
                f"   stdout: {result.stdout[:300]}\n"
                f"   stderr: {result.stderr[:300]}\n"
                "   This may still have succeeded — check Apps & Features in Settings."
            )
    except subprocess.TimeoutExpired:
        return (
            f"⏱️  Uninstaller timed out for '{app['name']}' (120s limit).\n"
            "   The uninstaller may be waiting for user input — check your desktop."
        )
    except Exception as e:
        return f"❌ Error running uninstaller for '{app['name']}': {e}\n   Command was: {cmd}"


# ---------------------------------------------------------------------------
# Tool: find_ghost_installs
# ---------------------------------------------------------------------------


def find_ghost_installs() -> str:
    """
    Find registry uninstall entries where the install directory no longer exists.

    These 'ghost installs' are apps that were deleted manually (not via
    uninstaller) and left orphaned registry entries behind.
    """
    apps = _all_apps(include_system=False)
    ghosts: list[dict] = []

    for a in apps:
        install_dir = a["install_dir"].strip()
        if not install_dir:
            continue  # Can't verify without a path

        # Expand environment variables like %ProgramFiles%
        install_dir = os.path.expandvars(install_dir).strip('"')
        p = Path(install_dir)

        if not p.exists():
            ghosts.append(
                {
                    "name": a["name"],
                    "version": a["version"],
                    "install_dir": install_dir,
                    "uninstall": a["uninstall_cmd"],
                }
            )

    if not ghosts:
        return "✅ No ghost installs found — all registry entries have valid install directories."

    lines = [
        f"Found {len(ghosts)} ghost install(s) — registry entries pointing to missing directories:",
        "-" * 80,
    ]
    for g in ghosts:
        lines += [
            f"  App:         {g['name']}  ({g['version']})",
            f"  Missing dir: {g['install_dir']}",
            f"  Uninstall:   {g['uninstall'][:80] if g['uninstall'] else 'None'}",
            "",
        ]

    lines.append(
        "To clean up: run uninstall_app('<name>', dry_run=False) if an uninstaller exists,\n"
        "or the registry entry can be removed manually via regedit."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: find_app_leftovers
# ---------------------------------------------------------------------------


def find_app_leftovers(app_name: str, min_size_mb: float = 0.0) -> str:
    """
    Search common directories for leftover files/folders from an uninstalled app.

    Useful after uninstalling to reclaim disk space from orphaned data.

    Args:
        app_name:    Name (or partial name) of the app to search for.
        min_size_mb: Only report directories larger than this (default 0 = all).
    """
    if not app_name.strip():
        return "Provide an app name to search for leftover directories."

    search_term = app_name.lower()
    found: list[dict] = []

    for base_dir in _LEFTOVER_SEARCH_DIRS:
        if not base_dir.exists():
            continue
        try:
            for child in base_dir.iterdir():
                if search_term in child.name.lower():
                    size_bytes = 0
                    file_count = 0
                    try:
                        for f in child.rglob("*"):
                            if f.is_file():
                                size_bytes += f.stat().st_size
                                file_count += 1
                    except (PermissionError, OSError):
                        pass

                    size_mb = size_bytes / (1024 * 1024)
                    if size_mb >= min_size_mb:
                        found.append(
                            {
                                "path": str(child),
                                "size_bytes": size_bytes,
                                "size_mb": size_mb,
                                "files": file_count,
                                "is_dir": child.is_dir(),
                            }
                        )
        except (PermissionError, OSError):
            continue

    if not found:
        return (
            f"No leftover directories found for '{app_name}'.\n"
            f"Searched: {', '.join(str(d) for d in _LEFTOVER_SEARCH_DIRS if d.exists())}"
        )

    found.sort(key=lambda x: x["size_bytes"], reverse=True)

    lines = [
        f"Leftover items for '{app_name}' ({len(found)} found):",
        "-" * 70,
    ]
    total_bytes = 0
    for item in found:
        total_bytes += item["size_bytes"]
        type_label = "📁 Dir " if item["is_dir"] else "📄 File"
        lines.append(
            f"  {type_label} {_fmt_bytes(item['size_bytes']):>10}  ({item['files']} files)  {item['path']}"
        )

    lines.append(f"\nTotal reclaimable: {_fmt_bytes(total_bytes)}")
    lines.append(
        "\n⚠️  Verify these are safe to delete before removing.\n"
        "   Use Python's shutil.rmtree() or the file manager to clean them up."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(registry) -> None:
    registry.register(
        "list_installed_apps",
        list_installed_apps,
        description=(
            "List all installed Windows applications from the registry. "
            "Fast (reads registry directly, not WMI Win32_Product). "
            "Supports name and publisher filters."
        ),
        category="system",
        args=[
            {
                "name": "search",
                "required": False,
                "description": "Filter by app name (case-insensitive substring)",
            },
            {
                "name": "publisher_filter",
                "required": False,
                "description": "Filter by publisher name substring",
            },
            {
                "name": "max_results",
                "required": False,
                "description": "Maximum number of results (default 200)",
            },
        ],
    )

    registry.register(
        "app_install_details",
        app_install_details,
        description="Show full registry details for a single installed application including uninstall command.",
        category="system",
        args=[
            {
                "name": "app_name",
                "required": True,
                "description": "Full or partial app name to look up",
            },
        ],
    )

    registry.register(
        "uninstall_app",
        uninstall_app,
        description=(
            "Run the uninstaller for an installed application. "
            "dry_run=True by default — shows the command without executing. "
            "Set dry_run=False to actually uninstall."
        ),
        category="system",
        args=[
            {
                "name": "app_name",
                "required": True,
                "description": "Full or partial name of app to uninstall",
            },
            {
                "name": "quiet",
                "required": False,
                "description": "Use silent/quiet uninstall switch if available (default False)",
            },
            {
                "name": "dry_run",
                "required": False,
                "description": "Show command without running (default True — set False to uninstall)",
            },
        ],
    )

    registry.register(
        "find_ghost_installs",
        find_ghost_installs,
        description=(
            "Find registry uninstall entries where the install directory no longer exists. "
            "These are apps deleted manually that left orphaned registry entries."
        ),
        category="system",
        args=[],
    )

    registry.register(
        "find_app_leftovers",
        find_app_leftovers,
        description=(
            "Search AppData, ProgramData, and Program Files for leftover directories "
            "from an uninstalled app — helps reclaim disk space after removal."
        ),
        category="system",
        args=[
            {
                "name": "app_name",
                "required": True,
                "description": "App name (or partial) to search for leftover files/directories",
            },
            {
                "name": "min_size_mb",
                "required": False,
                "description": "Only show directories larger than this many MB (default 0 = all)",
            },
        ],
    )
