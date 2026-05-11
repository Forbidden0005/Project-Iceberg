"""
File system scan.

Modes:
  LOW    - directory names only
  MEDIUM - directories + files
  HIGH   - files + first N chars of each (text heuristic)
"""

import os

from agent_core.constants import SCAN_HIGH_MODE_FILE_CAP, SCAN_PREVIEW_BYTES, SCAN_PREVIEW_DISPLAY_CHARS


def scan(path: str = ".", mode: str = "LOW") -> str:
    if not os.path.exists(path):
        return f"Path not found: {path}"

    mode = mode.upper()
    if mode not in {"LOW", "MEDIUM", "HIGH"}:
        return f"Unknown mode: {mode} (use LOW|MEDIUM|HIGH)"

    out: list[str] = []
    file_count = 0

    for root, dirs, files in os.walk(path):
        # Skip common noise
        dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git", "node_modules", ".venv"}]

        if mode == "LOW":
            for d in dirs:
                out.append(os.path.join(root, d))
            continue

        if mode == "MEDIUM":
            for d in dirs:
                out.append(os.path.join(root, d) + "/")
            for f in files:
                out.append(os.path.join(root, f))
            continue

        # HIGH
        for f in files:
            if file_count >= SCAN_HIGH_MODE_FILE_CAP:
                out.append(f"[truncated: {SCAN_HIGH_MODE_FILE_CAP} file cap reached]")
                return "\n".join(out)

            fp = os.path.join(root, f)
            try:
                with open(fp, encoding="utf-8", errors="ignore") as fh:
                    content = fh.read(SCAN_PREVIEW_BYTES).replace("\n", " ")
                out.append(f"{fp}: {content[:SCAN_PREVIEW_DISPLAY_CHARS]}")
            except Exception:
                out.append(f"{fp}: <unreadable>")
            file_count += 1

    return "\n".join(out) if out else "(empty)"
