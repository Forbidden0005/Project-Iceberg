"""
startup_manager.py — Windows startup items manager plugin.

Covers all three startup entry points Windows uses:
  1. Registry Run keys  (HKCU + HKLM, both 32 and 64-bit views)
  2. Startup folders    (per-user and All Users)
  3. Task Scheduler     (tasks set to run at logon)

Tools provided:
  list_startup_items     — All startup entries across all sources
  disable_startup_item   — Prevent an item from running at startup
  enable_startup_item    — Re-enable a disabled startup item
  delete_startup_item    — Permanently remove a registry startup entry
  add_startup_item       — Add a new registry startup entry

Tier 2 dependency for Task Scheduler enumeration: pip install pywin32
Registry + folder tools use winreg (stdlib) — they work without pywin32.
"""

from __future__ import annotations

import os
import winreg
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Dependency guard for pywin32 (Task Scheduler COM access)
# ---------------------------------------------------------------------------

_WIN32_AVAILABLE = False
try:
    import win32com.client as _win32com  # noqa: F401

    _WIN32_AVAILABLE = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Registry paths that contain startup entries
# ---------------------------------------------------------------------------

_REG_RUN_KEYS: list[tuple[Any, str, str]] = [
    # (hive, key_path, friendly_label)
    (
        winreg.HKEY_CURRENT_USER,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
        "HKCU\\Run",
    ),
    (
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
        "HKLM\\Run",
    ),
    (
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run",
        "HKLM\\Run (32-bit)",
    ),
    (
        winreg.HKEY_CURRENT_USER,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",
        "HKCU\\RunOnce",
    ),
    (
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",
        "HKLM\\RunOnce",
    ),
]

# Disabled items are moved here (same structure as Run, prefixed with '!')
_REG_DISABLED_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
_REG_DISABLED_HKCU = winreg.HKEY_CURRENT_USER
_REG_DISABLED_HKLM = winreg.HKEY_LOCAL_MACHINE

# Per-user startup folder
_STARTUP_FOLDER_USER = (
    Path(os.environ.get("APPDATA", ""))
    / "Microsoft"
    / "Windows"
    / "Start Menu"
    / "Programs"
    / "Startup"
)
# All-users startup folder
_STARTUP_FOLDER_ALL = (
    Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData"))
    / "Microsoft"
    / "Windows"
    / "Start Menu"
    / "Programs"
    / "Startup"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_reg_key(hive, key_path: str) -> dict[str, str]:
    """Return {name: command} for all values in a registry key."""
    entries: dict[str, str] = {}
    try:
        with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            i = 0
            while True:
                try:
                    name, data, _ = winreg.EnumValue(key, i)
                    entries[name] = str(data)
                    i += 1
                except OSError:
                    break
    except FileNotFoundError:
        pass
    except PermissionError:
        pass
    return entries


def _read_disabled_flags(hive) -> set[str]:
    """
    StartupApproved\\Run stores binary flags; if the first byte is 03 the item
    is disabled. Return set of disabled entry names.
    """
    disabled: set[str] = {}
    key_path = _REG_DISABLED_KEY
    try:
        with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ) as key:
            i = 0
            while True:
                try:
                    name, data, vtype = winreg.EnumValue(key, i)
                    # data is bytes; byte[0] == 3 → disabled, 2 → enabled
                    if isinstance(data, bytes) and len(data) > 0 and data[0] in (3, 0x03):
                        disabled[name] = True
                    i += 1
                except OSError:
                    break
    except (FileNotFoundError, PermissionError):
        pass
    return set(disabled.keys())


def _list_startup_folder(folder: Path, source_label: str) -> list[dict]:
    """Return startup entries from a Windows startup folder."""
    items: list[dict] = []
    if not folder.exists():
        return items
    for entry in folder.iterdir():
        if entry.suffix.lower() in (".lnk", ".url", ".bat", ".cmd", ".exe", ".vbs", ".ps1"):
            items.append(
                {
                    "name": entry.stem,
                    "command": str(entry),
                    "source": source_label,
                    "enabled": True,
                    "type": "folder",
                    "path": str(entry),
                }
            )
    return items


def _list_task_scheduler_logon_tasks() -> list[dict]:
    """Return Task Scheduler tasks that trigger at logon."""
    if not _WIN32_AVAILABLE:
        return []
    items: list[dict] = []
    try:
        import win32com.client

        scheduler = win32com.client.Dispatch("Schedule.Service")
        scheduler.Connect()
        root = scheduler.GetFolder("\\")

        def _walk_folder(folder):
            # Tasks
            tasks = folder.GetTasks(0)
            for i in range(tasks.Count):
                task = tasks.Item(i + 1)
                defn = task.Definition
                enabled = task.Enabled
                # Check if any trigger is logon type (6 = TASK_TRIGGER_LOGON)
                triggers = defn.Triggers
                for j in range(triggers.Count):
                    trg = triggers.Item(j + 1)
                    if trg.Type == 9 or trg.Type == 6:  # 9=SESSION_STATE_CHANGE, 6=LOGON
                        actions = defn.Actions
                        cmd = ""
                        if actions.Count > 0:
                            try:
                                cmd = actions.Item(1).Path + " " + actions.Item(1).Arguments
                            except Exception:
                                cmd = "<COM action>"
                        items.append(
                            {
                                "name": task.Name,
                                "command": cmd.strip(),
                                "source": "Task Scheduler",
                                "enabled": enabled,
                                "type": "task",
                                "path": task.Path,
                            }
                        )
                        break
            # Sub-folders
            subfolders = folder.GetFolders(0)
            for k in range(subfolders.Count):
                _walk_folder(subfolders.Item(k + 1))

        _walk_folder(root)
    except Exception:
        pass
    return items


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def list_startup_items(include_tasks: bool = True) -> str:
    """
    List all programs that run at Windows startup.

    Shows registry Run keys (HKCU + HKLM), startup folders (user + all-users),
    and optionally logon-triggered Task Scheduler tasks.

    Args:
        include_tasks: Include Task Scheduler logon tasks (default True,
                       requires pywin32).
    """
    all_items: list[dict] = []

    # 1. Registry Run keys
    for hive, key_path, label in _REG_RUN_KEYS:
        hive_disabled = _read_disabled_flags(hive)
        entries = _read_reg_key(hive, key_path)
        for name, cmd in entries.items():
            all_items.append(
                {
                    "name": name,
                    "command": cmd,
                    "source": label,
                    "enabled": name not in hive_disabled,
                    "type": "registry",
                    "path": f"{label}\\{name}",
                }
            )

    # 2. Startup folders
    all_items.extend(_list_startup_folder(_STARTUP_FOLDER_USER, "Startup Folder (User)"))
    all_items.extend(_list_startup_folder(_STARTUP_FOLDER_ALL, "Startup Folder (All Users)"))

    # 3. Task Scheduler
    if include_tasks:
        all_items.extend(_list_task_scheduler_logon_tasks())

    if not all_items:
        return "No startup items found."

    lines = [f"{'Name':<35} {'Enabled':<9} {'Source':<28} Command"]
    lines.append("-" * 110)

    for item in sorted(all_items, key=lambda x: x["name"].lower()):
        status = "✅ Yes" if item["enabled"] else "⛔ No "
        cmd_short = item["command"][:55] + "…" if len(item["command"]) > 55 else item["command"]
        lines.append(f"{item['name'][:34]:<35} {status:<9} {item['source'][:27]:<28} {cmd_short}")

    lines.append(f"\nTotal: {len(all_items)} startup item(s)")
    if not _WIN32_AVAILABLE and include_tasks:
        lines.append("(Task Scheduler tasks skipped — pip install pywin32 to include them)")
    return "\n".join(lines)


def disable_startup_item(item_name: str, hive: str = "hkcu") -> str:
    """
    Disable a startup registry entry so it won't run at startup.

    This uses the StartupApproved\\Run mechanism (same as Task Manager),
    so the entry is preserved and can be re-enabled later.

    Args:
        item_name: Name of the startup entry (as shown in list_startup_items).
        hive:      Registry hive: 'hkcu' (user, default) or 'hklm' (system-wide).
    """
    hive_const = winreg.HKEY_CURRENT_USER if hive.lower() == "hkcu" else winreg.HKEY_LOCAL_MACHINE
    key_path = _REG_DISABLED_KEY

    # Disabled flag: 8 bytes, first byte = 0x03
    disabled_flag = bytes([0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])

    try:
        with winreg.OpenKey(
            hive_const, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY
        ) as key:
            winreg.SetValueEx(key, item_name, 0, winreg.REG_BINARY, disabled_flag)
        return f"✅ '{item_name}' disabled at startup ({hive.upper()}\\StartupApproved)."
    except FileNotFoundError:
        # Key doesn't exist yet — create it
        try:
            with winreg.CreateKey(hive_const, key_path) as key:
                winreg.SetValueEx(key, item_name, 0, winreg.REG_BINARY, disabled_flag)
            return f"✅ '{item_name}' disabled at startup (key created)."
        except PermissionError:
            return (
                f"❌ Permission denied writing to {hive.upper()}\\{key_path}.\n"
                "Run the assistant as Administrator to modify HKLM entries."
            )
    except PermissionError:
        return (
            f"❌ Permission denied. Run as Administrator to modify {hive.upper()} startup entries."
        )
    except Exception as e:
        return f"❌ Error disabling '{item_name}': {e}"


def enable_startup_item(item_name: str, hive: str = "hkcu") -> str:
    """
    Re-enable a previously disabled startup registry entry.

    Args:
        item_name: Name of the startup entry to re-enable.
        hive:      'hkcu' (default) or 'hklm'.
    """
    hive_const = winreg.HKEY_CURRENT_USER if hive.lower() == "hkcu" else winreg.HKEY_LOCAL_MACHINE
    key_path = _REG_DISABLED_KEY

    # Enabled flag: 8 bytes, first byte = 0x02
    enabled_flag = bytes([0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])

    try:
        with winreg.OpenKey(
            hive_const, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY
        ) as key:
            winreg.SetValueEx(key, item_name, 0, winreg.REG_BINARY, enabled_flag)
        return f"✅ '{item_name}' re-enabled at startup."
    except FileNotFoundError:
        return f"ℹ️  No disable record found for '{item_name}' — it may already be enabled."
    except PermissionError:
        return f"❌ Permission denied. Run as Administrator to modify {hive.upper()} entries."
    except Exception as e:
        return f"❌ Error enabling '{item_name}': {e}"


def delete_startup_item(item_name: str, hive: str = "hkcu") -> str:
    """
    Permanently delete a startup registry entry.

    WARNING: This removes the entry from the Run key entirely. Use
    disable_startup_item if you want to keep the entry but prevent it
    from launching.

    Args:
        item_name: Name of the startup entry to delete.
        hive:      'hkcu' (default) or 'hklm'.
    """
    hive_const = winreg.HKEY_CURRENT_USER if hive.lower() == "hkcu" else winreg.HKEY_LOCAL_MACHINE
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"

    deleted = False
    errors: list[str] = []

    try:
        with winreg.OpenKey(
            hive_const, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY
        ) as key:
            winreg.DeleteValue(key, item_name)
        deleted = True
    except FileNotFoundError:
        errors.append(f"'{item_name}' not found in {hive.upper()}\\Run")
    except PermissionError:
        errors.append(f"Permission denied modifying {hive.upper()}\\Run (need Administrator)")
    except Exception as e:
        errors.append(f"Error: {e}")

    # Also clean up the StartupApproved flag
    if deleted:
        try:
            with winreg.OpenKey(hive_const, _REG_DISABLED_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, item_name)
        except Exception:
            pass  # Non-fatal — entry may not have a flag

    if deleted:
        return f"✅ Startup entry '{item_name}' permanently deleted from {hive.upper()}\\Run."
    return "❌ Could not delete:\n" + "\n".join(errors)


def add_startup_item(item_name: str, command: str, hive: str = "hkcu") -> str:
    """
    Add a new program to run at Windows startup (registry Run key).

    Args:
        item_name: Name for the startup entry (e.g. 'MyApp').
        command:   Full path to executable, optionally with arguments
                   (e.g. 'C:\\\\MyApp\\\\app.exe --silent').
        hive:      'hkcu' (user, default) or 'hklm' (all users, needs admin).
    """
    hive_const = winreg.HKEY_CURRENT_USER if hive.lower() == "hkcu" else winreg.HKEY_LOCAL_MACHINE
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"

    try:
        with winreg.OpenKey(
            hive_const, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY
        ) as key:
            winreg.SetValueEx(key, item_name, 0, winreg.REG_SZ, command)
        return (
            f"✅ Added startup entry '{item_name}':\n"
            f"   Command: {command}\n"
            f"   Registry: {hive.upper()}\\Run\n"
            f"   Will launch on next Windows login."
        )
    except PermissionError:
        return (
            f"❌ Permission denied writing to {hive.upper()}\\Run.\n"
            "For system-wide entries (hive='hklm'), run as Administrator.\n"
            "For user entries, use hive='hkcu' (default)."
        )
    except Exception as e:
        return f"❌ Error adding startup entry '{item_name}': {e}"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(registry) -> None:
    registry.register(
        "list_startup_items",
        list_startup_items,
        description=(
            "List all programs that run at Windows startup — registry Run keys "
            "(HKCU + HKLM), startup folders, and Task Scheduler logon tasks. "
            "Shows whether each item is enabled or disabled."
        ),
        category="system",
        args=[
            {
                "name": "include_tasks",
                "required": False,
                "description": "Include Task Scheduler logon tasks (default True, requires pywin32)",
            },
        ],
    )

    registry.register(
        "disable_startup_item",
        disable_startup_item,
        description=(
            "Disable a startup registry entry so it won't run at login. "
            "Uses the StartupApproved mechanism — entry is preserved and can be re-enabled."
        ),
        category="system",
        args=[
            {
                "name": "item_name",
                "required": True,
                "description": "Name of startup entry (as shown in list_startup_items)",
            },
            {
                "name": "hive",
                "required": False,
                "description": "'hkcu' for current user (default) or 'hklm' for all users (needs admin)",
            },
        ],
    )

    registry.register(
        "enable_startup_item",
        enable_startup_item,
        description="Re-enable a previously disabled startup registry entry.",
        category="system",
        args=[
            {
                "name": "item_name",
                "required": True,
                "description": "Name of startup entry to re-enable",
            },
            {
                "name": "hive",
                "required": False,
                "description": "'hkcu' (default) or 'hklm'",
            },
        ],
    )

    registry.register(
        "delete_startup_item",
        delete_startup_item,
        description=(
            "Permanently delete a startup registry entry from the Run key. "
            "Use disable_startup_item instead if you want to keep but deactivate it."
        ),
        category="system",
        args=[
            {
                "name": "item_name",
                "required": True,
                "description": "Name of startup entry to permanently remove",
            },
            {
                "name": "hive",
                "required": False,
                "description": "'hkcu' (default) or 'hklm'",
            },
        ],
    )

    registry.register(
        "add_startup_item",
        add_startup_item,
        description=(
            "Add a new program to run at Windows startup via the registry Run key. "
            "Use hive='hkcu' for current user (no admin needed) or 'hklm' for all users."
        ),
        category="system",
        args=[
            {
                "name": "item_name",
                "required": True,
                "description": "Name for the startup entry (e.g. 'MyBackupApp')",
            },
            {
                "name": "command",
                "required": True,
                "description": "Full path + arguments (e.g. 'C:\\\\Apps\\\\backup.exe --quiet')",
            },
            {
                "name": "hive",
                "required": False,
                "description": "'hkcu' for current user (default) or 'hklm' for all users",
            },
        ],
    )
