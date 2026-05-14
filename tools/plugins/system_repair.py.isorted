"""
system_repair.py — Windows system repair and maintenance tools plugin.

Wraps Windows built-in repair and maintenance utilities:
  - SFC (System File Checker)
  - DISM (Deployment Image Servicing and Management)
  - CHKDSK (Check Disk)
  - DNS flush
  - Temp file cleanup
  - Windows Update reset
  - Memory diagnostic scheduler

No pip dependencies — pure subprocess calling Windows built-in tools.
Most tools require Administrator privileges.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(
    args: list[str],
    timeout: int = 300,
    shell: bool = False,
) -> tuple[int, str]:
    """Run a command and return (returncode, combined output)."""
    try:
        r = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=shell,
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return -1, f"[timed out after {timeout}s]"
    except FileNotFoundError:
        return -1, f"[command not found: {args[0]}]"
    except Exception as e:
        return -1, f"[error: {e}]"


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ---------------------------------------------------------------------------
# Tool: run_sfc
# ---------------------------------------------------------------------------


def run_sfc(scan_only: bool = False) -> str:
    """
    Run System File Checker (SFC) to scan for and repair corrupted Windows files.

    SFC scans protected system files and replaces corrupted files with a cached copy.
    Requires Administrator privileges.

    Args:
        scan_only: If True, runs /verifyonly (scan without repair). Default False = full scan+repair.
    """
    flag = "/verifyonly" if scan_only else "/scannow"
    action = "Verifying" if scan_only else "Scanning and repairing"

    lines = [
        f"Running SFC ({action} system files)...",
        "This may take several minutes. Please wait.",
        "",
    ]

    rc, out = _run(["sfc", flag], timeout=600)

    lines.append(out)

    # Parse result
    if rc == 0:
        if "did not find any integrity violations" in out.lower():
            lines.append("\n✅ SFC: No integrity violations found. System files are healthy.")
        elif "successfully repaired" in out.lower():
            lines.append("\n✅ SFC: Corrupted files found and repaired successfully.")
        elif "unable to fix" in out.lower():
            lines.append(
                "\n⚠️  SFC: Some corrupted files could not be repaired.\n"
                "   Run DISM first (run_dism) then re-run SFC."
            )
        else:
            lines.append("\n✅ SFC completed (exit code 0).")
    elif rc == -1:
        lines.append(f"\n⏱️  {out}")
    else:
        lines.append(
            f"\n❌ SFC failed (exit code {rc}).\n" "   Make sure you're running as Administrator."
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: run_dism
# ---------------------------------------------------------------------------


def run_dism(operation: str = "restorehealth") -> str:
    """
    Run DISM to repair the Windows image (often run before SFC).

    DISM can fix issues that SFC alone cannot repair by downloading
    replacement files from Windows Update.

    Args:
        operation: Which DISM operation to run:
                   'checkhealth'   — Quick check of image health flag (fast)
                   'scanhealth'    — Full scan for image corruption (slow)
                   'restorehealth' — Scan and repair from Windows Update (default, slow)
    """
    op_map = {
        "checkhealth": "/CheckHealth",
        "scanhealth": "/ScanHealth",
        "restorehealth": "/RestoreHealth",
    }

    dism_flag = op_map.get(operation.lower())
    if not dism_flag:
        return (
            f"Unknown operation '{operation}'. "
            "Use: 'checkhealth', 'scanhealth', or 'restorehealth'."
        )

    lines = [
        f"Running DISM /Online /Cleanup-Image {dism_flag}...",
    ]
    if operation == "restorehealth":
        lines.append("This may take 15-30+ minutes and requires internet access.")
    lines.append("")

    rc, out = _run(
        ["dism", "/Online", "/Cleanup-Image", dism_flag],
        timeout=1800,  # 30 minutes
    )

    lines.append(out)

    if rc == 0:
        lines.append(f"\n✅ DISM {operation} completed successfully.")
    elif rc == -1:
        lines.append(f"\n⏱️  {out}")
    else:
        lines.append(
            f"\n❌ DISM failed (exit {rc}).\n"
            "   Check you have Administrator rights and internet access."
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: check_disk
# ---------------------------------------------------------------------------


def check_disk(drive: str = "C:", fix: bool = False) -> str:
    """
    Run CHKDSK to check a disk volume for errors.

    Scanning the system drive requires a reboot to run at next startup.
    Non-system drives can be checked/fixed immediately.

    Args:
        drive: Drive letter to check (e.g. 'C:', 'D:'). Default 'C:'.
        fix:   If True, schedule fix of errors (/f flag). Default False = scan only.
    """
    drive = drive.rstrip("\\").upper()
    if not drive.endswith(":"):
        drive += ":"

    args = ["chkdsk", drive]
    if fix:
        args += ["/f", "/r"]  # /f=fix, /r=recover bad sectors

    note = ""
    if fix and drive == "C:":
        note = (
            "\n⚠️  Fixing the system drive (C:) requires a reboot.\n"
            "CHKDSK will run automatically on the next restart."
        )

    rc, out = _run(args, timeout=600)
    result = f"CHKDSK {drive}:\n{out}"
    if note:
        result += note
    return result


# ---------------------------------------------------------------------------
# Tool: flush_dns
# ---------------------------------------------------------------------------


def flush_dns() -> str:
    """
    Flush the Windows DNS resolver cache.

    Useful when websites show stale IPs or after changing DNS settings.
    No administrator rights required.
    """
    rc, out = _run(["ipconfig", "/flushdns"])
    if rc == 0:
        return f"✅ DNS cache flushed.\n{out}"
    return f"❌ DNS flush failed (exit {rc}):\n{out}"


# ---------------------------------------------------------------------------
# Tool: clear_temp_files
# ---------------------------------------------------------------------------


def clear_temp_files(dry_run: bool = True) -> str:
    """
    Delete temporary files from the Windows Temp folder and user Temp folder.

    Args:
        dry_run: Show what would be deleted without deleting (default True).
    """
    temp_dirs: list[Path] = []

    # System temp
    sys_temp = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "Temp"
    if sys_temp.exists():
        temp_dirs.append(sys_temp)

    # User temp
    user_temp = Path(tempfile.gettempdir())
    if user_temp.exists() and user_temp != sys_temp:
        temp_dirs.append(user_temp)

    total_size = 0
    total_files = 0
    total_dirs = 0
    skipped = 0
    deletable: list[Path] = []

    for temp_dir in temp_dirs:
        try:
            for item in temp_dir.rglob("*"):
                try:
                    if item.is_file():
                        sz = item.stat().st_size
                        total_size += sz
                        total_files += 1
                        deletable.append(item)
                    elif item.is_dir():
                        total_dirs += 1
                except (PermissionError, OSError):
                    skipped += 1
        except (PermissionError, OSError):
            pass

    lines = [
        "Temp files scan:",
        f"  Directories scanned: {', '.join(str(d) for d in temp_dirs)}",
        f"  Files found:         {total_files}",
        f"  Total size:          {_fmt_bytes(total_size)}",
        f"  Skipped (in use):    {skipped}",
        "",
    ]

    if dry_run:
        lines.append(
            f"[DRY RUN] Would delete {total_files} temp files ({_fmt_bytes(total_size)}).\n"
            "Run with dry_run=False to actually delete."
        )
        return "\n".join(lines)

    # Actually delete
    deleted_files = 0
    deleted_size = 0
    failed = 0

    for f in deletable:
        try:
            sz = f.stat().st_size
            f.unlink(missing_ok=True)
            deleted_files += 1
            deleted_size += sz
        except (PermissionError, OSError):
            failed += 1

    # Remove empty temp dirs
    for temp_dir in temp_dirs:
        try:
            for sub in sorted(temp_dir.rglob("*"), reverse=True):
                if sub.is_dir():
                    try:
                        sub.rmdir()
                    except OSError:
                        pass
        except Exception:
            pass

    lines += [
        f"✅ Deleted {deleted_files} file(s) — {_fmt_bytes(deleted_size)} freed.",
        f"   Could not delete {failed} file(s) (in use by other processes).",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: repair_windows_update
# ---------------------------------------------------------------------------


def repair_windows_update(dry_run: bool = True) -> str:
    """
    Reset Windows Update components to fix stuck or broken updates.

    Stops Windows Update services, renames the SoftwareDistribution and
    Catroot2 folders, then restarts the services.

    Requires Administrator privileges.

    Args:
        dry_run: Show the steps without executing (default True).
    """
    steps = [
        ("net", ["net", "stop", "wuauserv"]),
        ("net", ["net", "stop", "cryptSvc"]),
        ("net", ["net", "stop", "bits"]),
        ("net", ["net", "stop", "msiserver"]),
        (
            "rename SoftwareDistribution",
            ["cmd", "/c", r"ren C:\Windows\SoftwareDistribution SoftwareDistribution.bak"],
        ),
        ("rename Catroot2", ["cmd", "/c", r"ren C:\Windows\System32\catroot2 Catroot2.bak"]),
        ("net", ["net", "start", "wuauserv"]),
        ("net", ["net", "start", "cryptSvc"]),
        ("net", ["net", "start", "bits"]),
        ("net", ["net", "start", "msiserver"]),
    ]

    if dry_run:
        lines = ["[DRY RUN] Windows Update reset would run these steps:"]
        for label, cmd in steps:
            lines.append(f"  → {' '.join(cmd)}")
        lines.append("\nRun with dry_run=False to execute (requires Administrator).")
        return "\n".join(lines)

    lines = ["Resetting Windows Update components...", ""]
    for label, cmd in steps:
        rc, out = _run(cmd, timeout=30)
        status = "✅" if rc == 0 else "⚠️"
        lines.append(f"{status} {' '.join(cmd[:3])}")
        if out:
            lines.append(f"   {out[:120]}")
        time.sleep(1)

    lines.append(
        "\nWindows Update reset complete.\n"
        "Try running Windows Update again. You may need to restart first."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: system_repair_report
# ---------------------------------------------------------------------------


def system_repair_report() -> str:
    """
    Run a quick system health check without making any changes.

    Checks:
    - Disk space on all volumes
    - Windows activation status
    - Pending reboot state
    - Temp folder size
    - Recent critical events (if event log accessible)
    """
    lines = ["System Health Report", "=" * 50, ""]

    # 1. Disk space
    lines.append("Disk Space:")
    try:
        import psutil

        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                pct = usage.percent
                warn = " ⚠️  LOW" if pct > 90 else ""
                lines.append(
                    f"  {part.device}  {_fmt_bytes(usage.used)} / {_fmt_bytes(usage.total)} "
                    f"({pct:.0f}% used){warn}"
                )
            except Exception:
                pass
    except ImportError:
        rc, out = _run(["wmic", "logicaldisk", "get", "size,freespace,caption"])
        lines.append(f"  {out[:300]}")
    lines.append("")

    # 2. Windows activation
    lines.append("Windows Activation:")
    rc, out = _run(["slmgr", "/dli"], timeout=20, shell=True)
    if rc == 0 and out:
        for l in out.splitlines()[:5]:
            lines.append(f"  {l.strip()}")
    else:
        rc2, out2 = _run(
            [
                "powershell",
                "-Command",
                "(Get-WmiObject SoftwareLicensingProduct | Where-Object {$_.PartialProductKey}).LicenseStatus",
            ],
            timeout=15,
        )
        lines.append(f"  License status: {out2[:100] if out2 else 'unknown'}")
    lines.append("")

    # 3. Pending reboot
    lines.append("Pending Reboot:")
    reboot_keys = [
        r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager",
        r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
    ]
    rc, out = _run(
        [
            "reg",
            "query",
            r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager",
            "/v",
            "PendingFileRenameOperations",
        ],
        timeout=5,
    )
    if rc == 0:
        lines.append("  ⚠️  Pending file rename operations found — reboot may be required.")
    else:
        rc2, _ = _run(
            [
                "reg",
                "query",
                r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
            ],
            timeout=5,
        )
        if rc2 == 0:
            lines.append("  ⚠️  Windows Update is waiting for a reboot.")
        else:
            lines.append("  ✅ No pending reboot detected.")
    lines.append("")

    # 4. Temp folder size
    lines.append("Temp Folder Size:")
    temp = Path(tempfile.gettempdir())
    total = sum(
        f.stat().st_size
        for f in temp.rglob("*")
        if f.is_file() and not f.is_symlink()
        for _ in [None]
        if True
    )
    # Simpler version:
    total_sz = 0
    total_ct = 0
    try:
        for f in temp.rglob("*"):
            try:
                if f.is_file():
                    total_sz += f.stat().st_size
                    total_ct += 1
            except (PermissionError, OSError):
                pass
    except Exception:
        pass
    lines.append(f"  {temp}: {_fmt_bytes(total_sz)} in {total_ct} files")
    if total_sz > 500 * 1024 * 1024:
        lines.append("  ℹ️  Large temp folder — consider running clear_temp_files()")
    lines.append("")

    lines.append("Run run_sfc() or run_dism() for deeper system file integrity checks.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(registry) -> None:
    registry.register(
        "run_sfc",
        run_sfc,
        description=(
            "Run Windows System File Checker (SFC /scannow) to find and repair "
            "corrupted system files. Requires Administrator. May take several minutes."
        ),
        category="system",
        args=[
            {
                "name": "scan_only",
                "required": False,
                "description": "If True, scan without repair (/verifyonly). Default False = full scan+repair.",
            },
        ],
    )

    registry.register(
        "run_dism",
        run_dism,
        description=(
            "Run DISM to repair the Windows system image. "
            "Use 'restorehealth' (default) to download and apply repairs. "
            "Run this before SFC when SFC alone can't fix issues."
        ),
        category="system",
        args=[
            {
                "name": "operation",
                "required": False,
                "description": "'checkhealth' (fast), 'scanhealth' (slow), 'restorehealth' (repairs, default)",
            },
        ],
    )

    registry.register(
        "check_disk",
        check_disk,
        description=(
            "Run CHKDSK on a drive to check for file system errors. "
            "fix=True schedules error repair (requires reboot for system drive)."
        ),
        category="system",
        args=[
            {
                "name": "drive",
                "required": False,
                "description": "Drive letter (e.g. 'C:', 'D:'). Default 'C:'.",
            },
            {
                "name": "fix",
                "required": False,
                "description": "Schedule error fix (default False = scan only)",
            },
        ],
    )

    registry.register(
        "flush_dns",
        flush_dns,
        description=(
            "Flush the Windows DNS resolver cache. "
            "Fixes stale DNS entries and website-not-found errors after DNS changes."
        ),
        category="system",
        args=[],
    )

    registry.register(
        "clear_temp_files",
        clear_temp_files,
        description=(
            "Delete Windows temporary files from system and user Temp folders. "
            "dry_run=True (default) shows what would be deleted. "
            "Set dry_run=False to actually free the space."
        ),
        category="system",
        args=[
            {
                "name": "dry_run",
                "required": False,
                "description": "Preview without deleting (default True — set False to delete)",
            },
        ],
    )

    registry.register(
        "repair_windows_update",
        repair_windows_update,
        description=(
            "Reset Windows Update components to fix stuck or broken updates. "
            "Stops services, renames SoftwareDistribution + Catroot2, restarts services. "
            "dry_run=True by default. Requires Administrator."
        ),
        category="system",
        args=[
            {
                "name": "dry_run",
                "required": False,
                "description": "Preview steps without executing (default True)",
            },
        ],
    )

    registry.register(
        "system_repair_report",
        system_repair_report,
        description=(
            "Quick system health snapshot: disk space, Windows activation status, "
            "pending reboot flags, and temp folder size. Read-only — no changes made."
        ),
        category="system",
        args=[],
    )
