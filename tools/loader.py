"""Dynamically import plugin modules from tools/plugins/."""

import importlib
import os
import sys

from tools import registry


def load_plugins(plugins_path: str = "tools/plugins") -> int:
    """
    Import every top-level *.py in plugins_path.
    Each plugin must expose `register(registry)` where registry is the tools.registry module.
    Returns the number of plugins successfully loaded.
    """
    if not os.path.isdir(plugins_path):
        return 0

    base_path = os.path.abspath(".")
    if base_path not in sys.path:
        sys.path.insert(0, base_path)

    loaded = 0
    for filename in sorted(os.listdir(plugins_path)):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue

        module_name = filename[:-3]
        full_module = f"tools.plugins.{module_name}"

        try:
            module = importlib.import_module(full_module)
            if hasattr(module, "register"):
                module.register(registry)
                loaded += 1
        except Exception as e:
            print(f"[plugin load error] {module_name}: {e}")

    return loaded
