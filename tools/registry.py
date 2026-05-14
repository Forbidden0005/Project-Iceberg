"""
Central tool registry.

Each entry:
  func:        callable
  description: human description (used in help + LLM prompts)
  category:    file | system | web | custom (used for sub-agent routing)
  args:        list of {"name": str, "required": bool, "description": str}
"""

from tools.file_tools import (append_file, create_file, delete_file, list_dir,
                              move_file, read_file)
from tools.scan_tools import scan
from tools.scraper_tools import scrape_paginated
from tools.vision_tools import (analyze_image, capture_screen,
                                read_text_from_image)
from tools.web_tools import web_search

TOOL_REGISTRY = {
    "list_dir": {
        "func": list_dir,
        "description": "List the contents of a directory.",
        "category": "file",
        "args": [
            {
                "name": "path",
                "required": False,
                "description": "Directory path. Defaults to current dir.",
            },
        ],
    },
    "create_file": {
        "func": create_file,
        "description": "Create a file, optionally with content.",
        "category": "file",
        "args": [
            {"name": "path", "required": True, "description": "Path to create."},
            {"name": "content", "required": False, "description": "Text content to write."},
        ],
    },
    "delete_file": {
        "func": delete_file,
        "description": "Delete a single file (not a directory).",
        "category": "file",
        "args": [{"name": "path", "required": True, "description": "File to delete."}],
    },
    "move_file": {
        "func": move_file,
        "description": "Move or rename a file.",
        "category": "file",
        "args": [
            {"name": "src", "required": True, "description": "Source path."},
            {"name": "dst", "required": True, "description": "Destination path."},
        ],
    },
    "read_file": {
        "func": read_file,
        "description": "Read the contents of a text file.",
        "category": "file",
        "args": [{"name": "path", "required": True, "description": "File to read."}],
    },
    "append_file": {
        "func": append_file,
        "description": "Append text to a file (creates it if missing).",
        "category": "file",
        "args": [
            {"name": "path", "required": True, "description": "File to append to."},
            {"name": "content", "required": True, "description": "Text to append."},
        ],
    },
    "scan": {
        "func": scan,
        "description": "Walk a directory tree. Modes: LOW (dirs), MEDIUM (dirs+files), HIGH (files+previews).",
        "category": "file",
        "args": [
            {"name": "path", "required": False, "description": "Root to scan. Defaults to '.'."},
            {"name": "mode", "required": False, "description": "LOW | MEDIUM | HIGH."},
        ],
    },
    "web_search": {
        "func": web_search,
        "description": "Search the web via DuckDuckGo.",
        "category": "web",
        "args": [{"name": "query", "required": True, "description": "Search query."}],
    },
    "scrape_paginated": {
        "func": scrape_paginated,
        "description": "Scrape data from paginated websites. Handles button clicks, URL patterns, and infinite scroll.",
        "category": "web",
        "args": [
            {"name": "url", "required": True, "description": "Starting URL to scrape"},
            {
                "name": "selector",
                "required": True,
                "description": "CSS selector for elements to extract",
            },
            {
                "name": "extract",
                "required": False,
                "description": "What to extract: 'href', 'text', 'html', or attribute name",
            },
            {
                "name": "pagination",
                "required": False,
                "description": "Pagination type: 'auto', 'button', 'url', 'scroll'",
            },
            {
                "name": "max_pages",
                "required": False,
                "description": "Maximum pages to scrape (default: 10)",
            },
            {
                "name": "next_button",
                "required": False,
                "description": "CSS selector for next button",
            },
        ],
    },
    "analyze_image": {
        "func": analyze_image,
        "description": "Analyze an image file with a local vision model. Describe contents, answer questions, identify objects.",
        "category": "vision",
        "args": [
            {
                "name": "path",
                "required": True,
                "description": "Path to the image file (JPEG, PNG, WEBP, etc.)",
            },
            {
                "name": "prompt",
                "required": False,
                "description": "What to ask about the image. Default: general description.",
            },
        ],
    },
    "capture_screen": {
        "func": capture_screen,
        "description": "Take a screenshot of the primary display and analyze it with a vision model.",
        "category": "vision",
        "args": [
            {
                "name": "prompt",
                "required": False,
                "description": "What to ask about the screen. Default: general description.",
            },
        ],
    },
    "read_text_from_image": {
        "func": read_text_from_image,
        "description": "Extract text from an image using the vision model (OCR). Works on receipts, documents, screenshots.",
        "category": "vision",
        "args": [
            {
                "name": "path",
                "required": True,
                "description": "Path to the image file to extract text from.",
            },
        ],
    },
}


def get_tool(name: str):
    entry = TOOL_REGISTRY.get(name)
    return entry["func"] if entry else None


def get_category(name: str) -> str:
    entry = TOOL_REGISTRY.get(name)
    return entry["category"] if entry else "unknown"


def describe_all() -> str:
    """Human-readable tool list for the `tools` command."""
    lines = []
    for name, entry in sorted(TOOL_REGISTRY.items()):
        lines.append(f"  {name:20s} [{entry['category']}] - {entry['description']}")
    return "\n".join(lines)


def describe_for_llm() -> str:
    """Detailed tool spec for LLM prompts, with arg schema."""
    lines = []
    for name, entry in sorted(TOOL_REGISTRY.items()):
        arg_parts = []
        for a in entry.get("args", []):
            tag = "" if a.get("required") else "?"
            arg_parts.append(f"{a['name']}{tag}")
        sig = f"{name}({', '.join(arg_parts)})"
        lines.append(f"- {sig}: {entry['description']}")
        for a in entry.get("args", []):
            req = "required" if a.get("required") else "optional"
            lines.append(f"    - {a['name']} ({req}): {a['description']}")
    return "\n".join(lines)


def register(name: str, func, description: str = "", category: str = "custom", args=None) -> None:
    """Used by plugins to add tools at runtime."""
    TOOL_REGISTRY[name] = {
        "func": func,
        "description": description,
        "category": category,
        "args": args or [],
    }
