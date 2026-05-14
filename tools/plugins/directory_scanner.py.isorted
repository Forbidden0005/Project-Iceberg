"""
Directory scanner for Project Iceberg.

Deep filesystem analysis: health checks, duplicate detection, junk cleanup,
large file hunting, malicious file indicators, and structural organisation.

No external dependencies — pure stdlib + psutil (optional for disk stats).
"""

import hashlib
import os
import re
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_JUNK_PATTERNS = [
    r"\.tmp$",
    r"\.temp$",
    r"~$",
    r"thumbs\.db$",
    r"desktop\.ini$",
    r"\.DS_Store$",
    r"\.bak$",
    r"\.old$",
    r"\.orig$",
    r"\.log$",
    r"Thumbs\.db$",
    r"ehthumbs\.db$",
    r"\.crdownload$",
    r"\.part$",
    r"\.download$",
]
_JUNK_RE = re.compile("|".join(_JUNK_PATTERNS), re.IGNORECASE)

# Extensions that are executable / potentially dangerous in wrong locations
_RISKY_EXTENSIONS = {
    ".exe",
    ".dll",
    ".scr",
    ".bat",
    ".cmd",
    ".vbs",
    ".js",
    ".wsf",
    ".ps1",
    ".pif",
    ".com",
    ".hta",
    ".reg",
    ".msi",
    ".jar",
}

# Directory names that are unusual in a user's home folder
_SUSPICIOUS_DIR_NAMES = {
    "system32",
    "syswow64",
    "windows",
    "drivers",
    "inf",
    "temp0",
    "tmp0",
    ".hidden",
    "...",
    "system",
}

_FMT_SIZE_UNITS = ("B", "KB", "MB", "GB", "TB")


def _fmt_size(n: int) -> str:
    for unit in _FMT_SIZE_UNITS:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _file_hash(path: str, algo: str = "md5") -> Optional[str]:
    """Return hex digest of a file, or None on error."""
    try:
        h = hashlib.new(algo)
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _walk(root: str, max_depth: int = 999) -> "list[tuple[str, os.stat_result]]":
    """Walk a directory tree, yielding (path, stat) tuples."""
    root_depth = root.count(os.sep)
    results = []
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
        cur_depth = dirpath.count(os.sep) - root_depth
        if cur_depth >= max_depth:
            dirnames.clear()
            continue
        for fname in filenames:
            fpath = os.path.join(dirpath, fname)
            try:
                st = os.stat(fpath)
                results.append((fpath, st))
            except Exception:
                continue
    return results


# ---------------------------------------------------------------------------
# Public tools
# ---------------------------------------------------------------------------


def scan_directory(
    path: str = ".",
    max_depth: int = 5,
) -> str:
    """
    Scan a directory and produce a health + organisation report.

    Shows: total file count, size breakdown by type, largest subdirectories,
    age distribution, and any structural issues found.

    Args:
        path:      Directory to scan (default: current directory).
        max_depth: How deep to recurse (default 5).

    Returns:
        Full directory health report.
    """
    root = os.path.expandvars(os.path.expanduser(path))
    if not os.path.isdir(root):
        return f"[error] Not a directory: {path}"

    files = _walk(root, max_depth)
    if not files:
        return f"Directory is empty or inaccessible: {root}"

    total_size = sum(st.st_size for _, st in files)
    now = time.time()

    # Extension breakdown
    ext_sizes: dict[str, int] = defaultdict(int)
    ext_counts: dict[str, int] = defaultdict(int)
    age_buckets = {"<1 day": 0, "1-7 days": 0, "7-30 days": 0, "1-12 months": 0, ">1 year": 0}

    for fpath, st in files:
        ext = Path(fpath).suffix.lower() or "(no ext)"
        ext_sizes[ext] += st.st_size
        ext_counts[ext] += 1
        age = now - st.st_mtime
        if age < 86400:
            age_buckets["<1 day"] += 1
        elif age < 604800:
            age_buckets["1-7 days"] += 1
        elif age < 2592000:
            age_buckets["7-30 days"] += 1
        elif age < 31536000:
            age_buckets["1-12 months"] += 1
        else:
            age_buckets[">1 year"] += 1

    # Largest subdirectories
    subdir_sizes: dict[str, int] = defaultdict(int)
    for fpath, st in files:
        rel = os.path.relpath(fpath, root)
        parts = rel.split(os.sep)
        top = parts[0] if len(parts) > 1 else "(root)"
        subdir_sizes[top] += st.st_size

    top_subdirs = sorted(subdir_sizes.items(), key=lambda x: x[1], reverse=True)[:8]

    lines = [
        f"Directory scan: {root}",
        f"Files: {len(files):,}  |  Total size: {_fmt_size(total_size)}  |  Max depth: {max_depth}",
        "",
        "Top file types by size:",
    ]
    for ext, sz in sorted(ext_sizes.items(), key=lambda x: x[1], reverse=True)[:12]:
        pct = sz / total_size * 100 if total_size else 0
        lines.append(f"  {ext:<15} {ext_counts[ext]:>5} files  {_fmt_size(sz):>10}  ({pct:.1f}%)")

    lines += ["", "Largest subdirectories:"]
    for name, sz in top_subdirs:
        pct = sz / total_size * 100 if total_size else 0
        lines.append(f"  {name:<35} {_fmt_size(sz):>10}  ({pct:.1f}%)")

    lines += ["", "File age distribution:"]
    for bucket, count in age_buckets.items():
        lines.append(f"  {bucket:<15} {count:>6,} files")

    return "\n".join(lines)


def find_duplicates(
    path: str = ".",
    min_size_kb: int = 1,
    max_depth: int = 10,
) -> str:
    """
    Find duplicate files in a directory tree by content hash.

    Groups files with identical content together regardless of filename.
    Only compares files above a minimum size to skip tiny stub files.

    Args:
        path:        Directory to scan.
        min_size_kb: Minimum file size to consider in KB (default 1).
        max_depth:   Recursion depth (default 10).

    Returns:
        Groups of duplicate files with total wasted space.
    """
    root = os.path.expandvars(os.path.expanduser(path))
    if not os.path.isdir(root):
        return f"[error] Not a directory: {path}"

    min_bytes = min_size_kb * 1024
    files = [(p, st) for p, st in _walk(root, max_depth) if st.st_size >= min_bytes]

    # First pass: group by size (cheap)
    by_size: dict[int, list[str]] = defaultdict(list)
    for fpath, st in files:
        by_size[st.st_size].append(fpath)

    candidates = {sz: paths for sz, paths in by_size.items() if len(paths) > 1}

    # Second pass: hash candidates
    by_hash: dict[str, list[str]] = defaultdict(list)
    for paths in candidates.values():
        for fpath in paths:
            h = _file_hash(fpath)
            if h:
                by_hash[h].append(fpath)

    duplicates = {h: paths for h, paths in by_hash.items() if len(paths) > 1}

    if not duplicates:
        return f"✓ No duplicate files found in: {root}  (scanned {len(files):,} files ≥ {min_size_kb} KB)"

    total_wasted = 0
    groups = sorted(
        duplicates.values(), key=lambda x: os.path.getsize(x[0]) * (len(x) - 1), reverse=True
    )

    lines = [f"Duplicates found in {root} — {len(groups)} group(s)\n"]
    for group in groups[:30]:  # Cap output at 30 groups
        try:
            size = os.path.getsize(group[0])
        except Exception:
            size = 0
        wasted = size * (len(group) - 1)
        total_wasted += wasted
        lines.append(
            f"  [{_fmt_size(size)} each — {len(group)} copies — {_fmt_size(wasted)} wasted]"
        )
        for fpath in group:
            lines.append(f"    {fpath}")

    if len(groups) > 30:
        lines.append(f"  ... and {len(groups) - 30} more groups")

    lines.append(f"\nTotal wasted space: {_fmt_size(total_wasted)}")
    return "\n".join(lines)


def find_large_files(
    path: str = ".",
    top_n: int = 20,
    min_size_mb: float = 10.0,
    max_depth: int = 10,
) -> str:
    """
    Find the largest files in a directory tree.

    Args:
        path:        Directory to search.
        top_n:       How many to list (default 20).
        min_size_mb: Only show files larger than this (default 10 MB).
        max_depth:   Recursion depth (default 10).

    Returns:
        Ranked list of large files with sizes and last-modified dates.
    """
    root = os.path.expandvars(os.path.expanduser(path))
    if not os.path.isdir(root):
        return f"[error] Not a directory: {path}"

    min_bytes = int(min_size_mb * 1024 * 1024)
    files = [(p, st) for p, st in _walk(root, max_depth) if st.st_size >= min_bytes]
    files.sort(key=lambda x: x[1].st_size, reverse=True)

    if not files:
        return f"No files larger than {min_size_mb} MB found in: {root}"

    lines = [
        f"Largest files in {root} (≥ {min_size_mb} MB) — showing top {min(top_n, len(files))} of {len(files):,}\n"
    ]
    for fpath, st in files[:top_n]:
        mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d")
        lines.append(f"  {_fmt_size(st.st_size):>10}  {mtime}  {fpath}")

    return "\n".join(lines)


def find_junk_files(
    path: str = ".",
    max_depth: int = 8,
    dry_run: bool = True,
) -> str:
    """
    Find junk and temporary files that are safe to delete.

    Targets: .tmp, .temp, ~backups, Thumbs.db, .DS_Store, .bak, .crdownload,
    partially downloaded files, and Windows/macOS cruft files.

    Args:
        path:      Directory to scan.
        max_depth: Recursion depth (default 8).
        dry_run:   If True (default), only list files — do NOT delete.
                   Set dry_run=False to actually delete them.

    Returns:
        List of junk files found (and deleted if dry_run=False).
    """
    root = os.path.expandvars(os.path.expanduser(path))
    if not os.path.isdir(root):
        return f"[error] Not a directory: {path}"

    found = []
    for fpath, st in _walk(root, max_depth):
        fname = os.path.basename(fpath)
        if _JUNK_RE.search(fname):
            found.append((fpath, st.st_size))

    if not found:
        return f"✓ No junk files found in: {root}"

    total = sum(sz for _, sz in found)
    action = "Would delete" if dry_run else "Deleting"
    lines = [
        f"Junk files in {root} — {len(found):,} files  ({_fmt_size(total)} total)\n"
        f"Mode: {'DRY RUN (no files deleted)' if dry_run else '⚠ DELETING'}\n",
    ]
    deleted = 0
    errors = 0
    for fpath, sz in sorted(found, key=lambda x: x[1], reverse=True)[:100]:
        lines.append(f"  {action}: {_fmt_size(sz):>10}  {fpath}")
        if not dry_run:
            try:
                os.remove(fpath)
                deleted += 1
            except Exception as e:
                lines.append(f"    ✗ Error: {e}")
                errors += 1

    if len(found) > 100:
        lines.append(f"  ... and {len(found) - 100} more files")

    if not dry_run:
        lines.append(
            f"\nDeleted {deleted:,} files  |  Errors: {errors}  |  Freed: {_fmt_size(total)}"
        )
    else:
        lines.append(f"\nTotal recoverable: {_fmt_size(total)}  (run with dry_run=False to delete)")

    return "\n".join(lines)


def find_old_files(
    path: str = ".",
    days_old: int = 365,
    max_depth: int = 8,
    min_size_kb: int = 0,
) -> str:
    """
    Find files that haven't been modified in a long time.

    Args:
        path:        Directory to scan.
        days_old:    Files older than this many days (default 365 = 1 year).
        max_depth:   Recursion depth (default 8).
        min_size_kb: Only show files above this size (default 0 = all).

    Returns:
        List of old files with sizes and last-modified dates.
    """
    root = os.path.expandvars(os.path.expanduser(path))
    if not os.path.isdir(root):
        return f"[error] Not a directory: {path}"

    cutoff = time.time() - days_old * 86400
    min_bytes = min_size_kb * 1024
    found = [
        (p, st)
        for p, st in _walk(root, max_depth)
        if st.st_mtime < cutoff and st.st_size >= min_bytes
    ]
    found.sort(key=lambda x: x[1].st_mtime)

    if not found:
        return f"No files older than {days_old} days found in: {root}"

    total = sum(st.st_size for _, st in found)
    lines = [
        f"Files unmodified for ≥ {days_old} days in {root}\n"
        f"Found: {len(found):,} files  |  {_fmt_size(total)}\n",
    ]
    for fpath, st in found[:50]:
        mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d")
        lines.append(f"  {mtime}  {_fmt_size(st.st_size):>10}  {fpath}")

    if len(found) > 50:
        lines.append(f"\n  ... and {len(found)-50:,} more files")

    return "\n".join(lines)


def find_suspicious_files(
    path: str = ".",
    max_depth: int = 8,
) -> str:
    """
    Scan for files that look out of place or potentially malicious.

    Checks for: executables in non-standard locations, double-extension tricks
    (e.g. photo.jpg.exe), hidden files in user dirs, suspiciously named
    directories, and risky script files in document folders.

    Args:
        path:      Directory to scan.
        max_depth: Recursion depth (default 8).

    Returns:
        List of suspicious files with reasons.
    """
    root = os.path.expandvars(os.path.expanduser(path))
    if not os.path.isdir(root):
        return f"[error] Not a directory: {path}"

    findings: list[tuple[str, str]] = []

    # Check for suspicious directories
    for dirpath, dirnames, _ in os.walk(root):
        for dn in dirnames:
            if dn.lower() in _SUSPICIOUS_DIR_NAMES:
                full = os.path.join(dirpath, dn)
                findings.append((full, f"Suspicious directory name: {dn}"))
        # Stop walking past max_depth
        cur_depth = dirpath.count(os.sep) - root.count(os.sep)
        if cur_depth >= max_depth:
            dirnames.clear()

    for fpath, st in _walk(root, max_depth):
        fname = os.path.basename(fpath)
        ext = Path(fpath).suffix.lower()
        stem = Path(fpath).stem

        # Double extension: "resume.pdf.exe"
        if ext in _RISKY_EXTENSIONS and Path(stem).suffix:
            findings.append(
                (fpath, f"Double extension (possible disguise): ...{Path(stem).suffix}{ext}")
            )

        # Executable in temp/download dir
        risky_dirs = ["\\temp\\", "\\tmp\\", "\\downloads\\", "\\users\\public\\"]
        if ext in _RISKY_EXTENSIONS:
            path_lower = fpath.lower()
            for rd in risky_dirs:
                if rd in path_lower:
                    findings.append((fpath, f"Executable in risky location: {rd.strip(chr(92))}"))
                    break

        # Hidden files (starts with dot on Unix, or Windows hidden attribute)
        if fname.startswith(".") and not fname.startswith(".."):
            findings.append((fpath, "Hidden file (dot prefix)"))
        try:
            attrs = st.st_file_attributes if hasattr(st, "st_file_attributes") else 0
            if attrs & 0x2:  # FILE_ATTRIBUTE_HIDDEN
                findings.append((fpath, "Windows hidden attribute set"))
        except Exception:
            pass

        # Zero-byte executable
        if ext in _RISKY_EXTENSIONS and st.st_size == 0:
            findings.append((fpath, "Zero-byte executable"))

        # Very new executable (created in last hour) in non-standard dir
        if ext in _RISKY_EXTENSIONS and (time.time() - st.st_mtime < 3600):
            findings.append((fpath, "Executable modified in the last hour"))

    if not findings:
        return f"✓ No suspicious files detected in: {root}  ({max_depth} levels deep)"

    lines = [f"⚠  Suspicious file scan: {root}\n   {len(findings)} finding(s)\n"]
    for fpath, reason in findings[:60]:
        lines.append(f"  ⚠  {reason}\n     {fpath}")

    if len(findings) > 60:
        lines.append(f"\n  ... and {len(findings)-60} more findings")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------


def register(registry) -> None:
    registry.register(
        "scan_directory",
        scan_directory,
        description="Full directory health report: file count, size by type, largest subdirectories, age distribution.",
        category="file",
        args=[
            {
                "name": "path",
                "required": False,
                "description": "Directory to scan (default: current dir)",
            },
            {"name": "max_depth", "required": False, "description": "Recursion depth (default 5)"},
        ],
    )
    registry.register(
        "find_duplicates",
        find_duplicates,
        description="Find duplicate files by content hash. Groups identical files, shows wasted disk space.",
        category="file",
        args=[
            {"name": "path", "required": False, "description": "Directory to scan"},
            {
                "name": "min_size_kb",
                "required": False,
                "description": "Skip files smaller than this (default 1 KB)",
            },
            {"name": "max_depth", "required": False, "description": "Recursion depth (default 10)"},
        ],
    )
    registry.register(
        "find_large_files",
        find_large_files,
        description="Find the largest files in a directory tree. Helps reclaim disk space.",
        category="file",
        args=[
            {"name": "path", "required": False, "description": "Directory to search"},
            {"name": "top_n", "required": False, "description": "How many to list (default 20)"},
            {
                "name": "min_size_mb",
                "required": False,
                "description": "Minimum file size in MB (default 10)",
            },
        ],
    )
    registry.register(
        "find_junk_files",
        find_junk_files,
        description="Find and optionally delete junk/temp files: .tmp, .bak, Thumbs.db, .crdownload, etc. Use dry_run=False to actually delete.",
        category="file",
        args=[
            {"name": "path", "required": False, "description": "Directory to scan"},
            {
                "name": "dry_run",
                "required": False,
                "description": "True = list only, False = delete (default True)",
            },
            {"name": "max_depth", "required": False, "description": "Recursion depth (default 8)"},
        ],
    )
    registry.register(
        "find_old_files",
        find_old_files,
        description="Find files that haven't been modified in a long time. Good for archiving or cleaning stale data.",
        category="file",
        args=[
            {"name": "path", "required": False, "description": "Directory to scan"},
            {
                "name": "days_old",
                "required": False,
                "description": "Age threshold in days (default 365)",
            },
            {
                "name": "min_size_kb",
                "required": False,
                "description": "Minimum file size filter (default 0 = all)",
            },
        ],
    )
    registry.register(
        "find_suspicious_files",
        find_suspicious_files,
        description="Scan for malicious or out-of-place files: double extensions, executables in temp dirs, hidden files, recently modified executables.",
        category="file",
        args=[
            {"name": "path", "required": False, "description": "Directory to scan"},
            {"name": "max_depth", "required": False, "description": "Recursion depth (default 8)"},
        ],
    )
