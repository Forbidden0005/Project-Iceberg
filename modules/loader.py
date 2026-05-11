"""Module loader - discovers and imports modules from modules/ directory.

Each module must be in its own subdirectory with a module.py file that exports
a MODULE instance conforming to the Module protocol.

Example:
    modules/
        drive_manager/
            module.py       # exports MODULE = DriveManagerModule(...)
            tools.py        # optional module-specific tools
        code_engineer/
            module.py       # exports MODULE = CodeEngineerModule(...)
"""

import importlib.util
import sys
from pathlib import Path
from typing import Dict

from agent_core.logger import get_logger
from modules.base import Module

logger = get_logger()


def discover_modules(modules_dir: str | Path = "modules") -> Dict[str, Module]:
    """Scan modules/ directory and import all valid modules.

    A valid module:
    - Lives in modules/<name>/
    - Has a module.py file
    - module.py exports a MODULE instance

    Args:
        modules_dir: Path to modules directory (default: "modules")

    Returns:
        Dict mapping module_id -> Module instance
    """
    modules_path = Path(modules_dir)
    if not modules_path.exists():
        logger.warning("modules directory not found: %s", modules_path)
        return {}

    discovered = {}

    for child in sorted(modules_path.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("_"):  # Skip __pycache__ etc
            continue

        module_file = child / "module.py"
        if not module_file.exists():
            logger.debug("skipping %s: no module.py", child.name)
            continue

        try:
            module_instance = _load_module_file(child.name, module_file)
            if module_instance:
                discovered[module_instance.manifest.id] = module_instance
                logger.info(
                    "loaded module: %s v%s", module_instance.manifest.name, module_instance.manifest.version
                )
        except Exception as e:
            logger.error("failed to load module %s: %s", child.name, e)

    return discovered


def _load_module_file(module_name: str, module_file: Path) -> Module | None:
    """Load a single module.py file and extract the MODULE export.

    Args:
        module_name: Name of the module (folder name)
        module_file: Path to the module.py file

    Returns:
        Module instance if valid, None otherwise
    """
    spec = importlib.util.spec_from_file_location(f"modules.{module_name}.module", module_file)
    if not spec or not spec.loader:
        return None

    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    if not hasattr(mod, "MODULE"):
        logger.warning("module %s has no MODULE export", module_name)
        return None

    instance = mod.MODULE

    # Validate that it has required attributes
    if not hasattr(instance, "manifest"):
        logger.error("module %s.MODULE has no manifest", module_name)
        return None

    if not hasattr(instance, "system_prompt"):
        logger.error("module %s.MODULE has no system_prompt", module_name)
        return None

    if not hasattr(instance, "get_tools"):
        logger.error("module %s.MODULE has no get_tools method", module_name)
        return None

    return instance
