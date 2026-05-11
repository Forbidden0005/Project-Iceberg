"""Basic file system tools. Every tool returns a string for the executor."""

import os
import shutil

from agent_core.constants import READ_FILE_MAX_BYTES


def list_dir(path: str = ".") -> str:
    if not os.path.isdir(path):
        return f"Not a directory: {path}"
    try:
        entries = os.listdir(path)
    except PermissionError:
        return f"Permission denied: {path}"

    def _mark(name: str) -> str:
        full = os.path.join(path, name)
        return f"{name}/" if os.path.isdir(full) else name

    return "\n".join(sorted(_mark(e) for e in entries)) or "(empty)"


def create_file(path: str, content: str = "") -> str:
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Created {path}"
    except Exception as e:
        return f"Error creating {path}: {e}"


def delete_file(path: str) -> str:
    if not os.path.exists(path):
        return f"Not found: {path}"
    try:
        if os.path.isdir(path):
            return f"Refusing to delete directory via delete_file: {path}"
        os.remove(path)
        return f"Deleted {path}"
    except Exception as e:
        return f"Error deleting {path}: {e}"


def move_file(src: str, dst: str) -> str:
    if not os.path.exists(src):
        return f"Source not found: {src}"
    try:
        parent = os.path.dirname(dst)
        if parent:
            os.makedirs(parent, exist_ok=True)
        shutil.move(src, dst)
        return f"Moved {src} -> {dst}"
    except Exception as e:
        return f"Error moving {src} -> {dst}: {e}"


def read_file(path: str, max_bytes: int = READ_FILE_MAX_BYTES) -> str:
    if not os.path.isfile(path):
        return f"Not a file: {path}"
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            data = f.read(max_bytes + 1)
        if len(data) > max_bytes:
            return data[:max_bytes] + f"\n\n[truncated at {max_bytes} bytes]"
        return data
    except Exception as e:
        return f"Error reading {path}: {e}"


def append_file(path: str, content: str = "") -> str:
    """Append content to an existing file, or create it if missing."""
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(content)
        return f"Appended to {path}"
    except Exception as e:
        return f"Error appending to {path}: {e}"
