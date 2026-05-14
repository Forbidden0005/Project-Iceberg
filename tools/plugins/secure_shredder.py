"""
secure_shredder.py — Secure file deletion plugin.

Standard file deletion leaves data recoverable because the OS only removes
the directory entry — the actual bytes remain on disk until overwritten.
This plugin overwrites file content with random data before deletion.

NOTE: Effective only on spinning HDDs. SSDs/NVMe drives use wear-leveling
that makes byte-level overwrite unreliable — full-disk encryption (BitLocker)
is the correct approach for SSDs. This is disclosed in each tool's output.

Tools provided:
  shred_file          — Overwrite + delete a single file
  shred_directory     — Shred all files in a directory
  wipe_free_space     — Wipe free space via Windows cipher /w (HDD only)
  secure_delete_temp  — Shred the Windows Temp folder contents

No pip dependencies — uses stdlib: os, sys, random, struct, pathlib.
"""

from __future__ import annotations

import os
import random
import subprocess
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SSD_WARNING = (
    "⚠️  SSD/NVMe note: Overwrite-based shredding is NOT guaranteed effective on "
    "SSDs due to wear-leveling. Use BitLocker full-disk encryption instead."
)

_DEFAULT_PASSES = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _overwrite_file(path: Path, passes: int) -> tuple[bool, str]:
    """
    Overwrite a file with multiple passes of random/pattern data, then delete.

    Pass 1: all zeros
    Pass 2: all ones (0xFF)
    Pass 3+: cryptographically random bytes

    Returns (success, message).
    """
    try:
        file_size = path.stat().st_size
    except OSError as e:
        return False, f"Cannot stat '{path}': {e}"

    if file_size == 0:
        # Zero-byte file — just delete
        try:
            path.unlink()
            return True, "Deleted (zero-byte file, no overwrite needed)."
        except OSError as e:
            return False, f"Cannot delete: {e}"

    try:
        with open(path, "r+b") as f:
            for pass_num in range(passes):
                f.seek(0)
                remaining = file_size

                if pass_num == 0:
                    # Pass 1: zeros
                    chunk = b"\x00" * min(65536, remaining)
                    while remaining > 0:
                        write_size = min(65536, remaining)
                        f.write(b"\x00" * write_size)
                        remaining -= write_size
                elif pass_num == 1:
                    # Pass 2: ones
                    while remaining > 0:
                        write_size = min(65536, remaining)
                        f.write(b"\xff" * write_size)
                        remaining -= write_size
                else:
                    # Subsequent passes: random
                    while remaining > 0:
                        write_size = min(65536, remaining)
                        f.write(os.urandom(write_size))
                        remaining -= write_size

                f.flush()
                os.fsync(f.fileno())

    except PermissionError:
        return False, f"Permission denied writing to '{path}' (file may be in use)."
    except OSError as e:
        return False, f"I/O error overwriting '{path}': {e}"

    # Rename before delete (obscures original filename from recovery)
    try:
        temp_name = path.parent / f"_shredded_{random.randint(100000, 999999)}"
        path.rename(temp_name)
        temp_name.unlink()
        return (
            True,
            f"Shredded and deleted ({_fmt_bytes(file_size)}, {passes} pass{'es' if passes > 1 else ''}).",
        )
    except OSError as e:
        # Try direct delete if rename failed
        try:
            path.unlink()
            return (
                True,
                f"Shredded ({_fmt_bytes(file_size)}, {passes} passes) — renamed failed but file deleted.",
            )
        except OSError as e2:
            return False, f"Overwritten but could not delete: {e2}"


# ---------------------------------------------------------------------------
# Tool: shred_file
# ---------------------------------------------------------------------------


def shred_file(
    file_path: str,
    passes: int = 3,
    dry_run: bool = True,
) -> str:
    """
    Securely delete a file by overwriting its contents before deletion.

    Overwrites with zeros, then ones, then random data (per pass), then deletes.

    Args:
        file_path: Full path to the file to shred.
        passes:    Number of overwrite passes (default 3). More = slower but more thorough.
        dry_run:   Preview without shredding (default True — set False to actually shred).
    """
    path = Path(file_path)

    if not path.exists():
        return f"File not found: '{file_path}'"
    if not path.is_file():
        return f"'{file_path}' is not a file. Use shred_directory for directories."

    try:
        size = path.stat().st_size
    except OSError as e:
        return f"Cannot read file info: {e}"

    if dry_run:
        return (
            f"[DRY RUN] Would shred: {file_path}\n"
            f"  Size:   {_fmt_bytes(size)}\n"
            f"  Passes: {passes}\n\n"
            f"Run with dry_run=False to actually shred and delete.\n"
            f"{_SSD_WARNING}"
        )

    ok, msg = _overwrite_file(path, passes)
    icon = "✅" if ok else "❌"
    return f"{icon} {path.name}: {msg}\n{_SSD_WARNING}"


# ---------------------------------------------------------------------------
# Tool: shred_directory
# ---------------------------------------------------------------------------


def shred_directory(
    dir_path: str,
    passes: int = 3,
    dry_run: bool = True,
    recursive: bool = True,
) -> str:
    """
    Securely delete all files in a directory.

    Args:
        dir_path:  Full path to the directory to shred.
        passes:    Overwrite passes per file (default 3).
        dry_run:   Preview without shredding (default True).
        recursive: Also shred files in subdirectories (default True).
    """
    base = Path(dir_path)

    if not base.exists():
        return f"Directory not found: '{dir_path}'"
    if not base.is_dir():
        return f"'{dir_path}' is not a directory. Use shred_file for single files."

    # Collect files
    glob_pattern = "**/*" if recursive else "*"
    files = [f for f in base.glob(glob_pattern) if f.is_file()]

    if not files:
        return f"No files found in '{dir_path}'."

    total_size = sum(f.stat().st_size for f in files if f.exists())

    if dry_run:
        return (
            f"[DRY RUN] Would shred {len(files)} file(s) in '{dir_path}':\n"
            f"  Total size: {_fmt_bytes(total_size)}\n"
            f"  Passes:     {passes}\n"
            f"  Recursive:  {recursive}\n\n"
            f"Run with dry_run=False to actually shred all files.\n"
            f"{_SSD_WARNING}"
        )

    shredded = 0
    shredded_size = 0
    failed: list[str] = []

    for f in files:
        ok, msg = _overwrite_file(f, passes)
        if ok:
            shredded += 1
            shredded_size += 0  # already deleted, can't stat
        else:
            failed.append(f"  {f.name}: {msg}")

    # Remove empty directories (bottom-up)
    if recursive:
        for sub in sorted(base.rglob("*"), reverse=True):
            if sub.is_dir():
                try:
                    sub.rmdir()
                except OSError:
                    pass
    try:
        base.rmdir()
    except OSError:
        pass

    lines = [
        f"✅ Shredded {shredded}/{len(files)} file(s) in '{dir_path}'",
        f"   (~{_fmt_bytes(total_size)} data overwritten with {passes} passes)",
    ]
    if failed:
        lines.append(f"\n❌ {len(failed)} file(s) could not be shredded:")
        lines.extend(failed[:10])
    lines.append(f"\n{_SSD_WARNING}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: wipe_free_space
# ---------------------------------------------------------------------------


def wipe_free_space(drive: str = "C:", dry_run: bool = True) -> str:
    """
    Wipe free space on a drive using Windows' built-in cipher /w command.

    cipher /w writes zeros, then ones, then random data to all free space,
    making deleted file recovery much harder.

    This can take a very long time (hours on large/full drives).

    Args:
        drive:   Drive letter to wipe free space on (e.g. 'C:', 'D:'). Default 'C:'.
        dry_run: Preview without running (default True).
    """
    drive = drive.rstrip("\\/:").upper() + ":\\"

    if dry_run:
        return (
            f"[DRY RUN] Would run: cipher /w:{drive}\n\n"
            f"This overwrites all free space on {drive} with zeros, ones, and random data.\n"
            f"⚠️  This can take hours on large drives.\n"
            f"Run with dry_run=False to start.\n"
            f"{_SSD_WARNING}"
        )

    lines = [
        f"Wiping free space on {drive} with cipher /w...",
        "This may take a very long time. The process runs in the background.",
        "",
    ]

    try:
        # Launch detached so it doesn't block the assistant
        proc = subprocess.Popen(
            ["cipher", f"/w:{drive}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        # Read a few seconds of output then report PID
        time.sleep(3)
        if proc.poll() is None:
            lines += [
                f"✅ cipher /w is running (PID {proc.pid}).",
                "   It will continue in the background until complete.",
                "   You can monitor progress via Task Manager → cipher.exe",
                f"\n{_SSD_WARNING}",
            ]
        else:
            out, err = proc.communicate()
            lines += [
                f"cipher /w completed (exit {proc.returncode}).",
                out[:300] if out else "",
                err[:200] if err else "",
            ]
    except FileNotFoundError:
        lines.append("❌ cipher.exe not found — this requires Windows.")
    except Exception as e:
        lines.append(f"❌ Error starting cipher /w: {e}")

    return "\n".join(l for l in lines if l is not None)


# ---------------------------------------------------------------------------
# Tool: secure_delete_temp
# ---------------------------------------------------------------------------


def secure_delete_temp(passes: int = 1, dry_run: bool = True) -> str:
    """
    Securely shred the contents of the Windows Temp folder.

    Uses 1 pass by default (faster) since temp files are usually low-sensitivity.
    Increase passes for more thorough wiping.

    Args:
        passes:  Overwrite passes (default 1 for temp files).
        dry_run: Preview without shredding (default True).
    """
    import tempfile

    temp_dir = tempfile.gettempdir()
    return shred_directory(temp_dir, passes=passes, dry_run=dry_run, recursive=True)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(registry) -> None:
    registry.register(
        "shred_file",
        shred_file,
        description=(
            "Securely delete a file by overwriting its contents before deletion. "
            "Overwrites with zeros, ones, then random data. "
            "dry_run=True by default — set False to actually shred. "
            "Note: Most effective on HDDs; SSDs use BitLocker instead."
        ),
        category="file",
        args=[
            {
                "name": "file_path",
                "required": True,
                "description": "Full path to file to securely delete",
            },
            {"name": "passes", "required": False, "description": "Overwrite passes (default 3)"},
            {
                "name": "dry_run",
                "required": False,
                "description": "Preview without shredding (default True)",
            },
        ],
    )

    registry.register(
        "shred_directory",
        shred_directory,
        description=(
            "Securely delete all files in a directory by overwriting before deletion. "
            "dry_run=True by default. Removes empty directories after shredding."
        ),
        category="file",
        args=[
            {
                "name": "dir_path",
                "required": True,
                "description": "Full path to directory to shred",
            },
            {
                "name": "passes",
                "required": False,
                "description": "Overwrite passes per file (default 3)",
            },
            {
                "name": "dry_run",
                "required": False,
                "description": "Preview without shredding (default True)",
            },
            {
                "name": "recursive",
                "required": False,
                "description": "Also shred subdirectory files (default True)",
            },
        ],
    )

    registry.register(
        "wipe_free_space",
        wipe_free_space,
        description=(
            "Wipe free disk space using Windows cipher /w to make deleted files unrecoverable. "
            "Can take hours on large drives. dry_run=True by default."
        ),
        category="system",
        args=[
            {
                "name": "drive",
                "required": False,
                "description": "Drive letter (e.g. 'C:', 'D:'). Default 'C:'.",
            },
            {
                "name": "dry_run",
                "required": False,
                "description": "Preview without running (default True)",
            },
        ],
    )

    registry.register(
        "secure_delete_temp",
        secure_delete_temp,
        description=(
            "Securely shred the Windows Temp folder contents with overwrite passes. "
            "Safer than regular temp cleanup for sensitive temporary data. "
            "dry_run=True by default."
        ),
        category="file",
        args=[
            {
                "name": "passes",
                "required": False,
                "description": "Overwrite passes (default 1 for temp files)",
            },
            {
                "name": "dry_run",
                "required": False,
                "description": "Preview without shredding (default True)",
            },
        ],
    )
