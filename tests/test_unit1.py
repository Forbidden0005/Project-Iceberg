import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from modules.base import BaseModule, ModuleManifest, ModuleTools

print("OK: Module protocol imports")
print(f"OK: ModuleManifest: {ModuleManifest.__name__}")
print(f"OK: ModuleTools: {ModuleTools.__name__}")
print(f"OK: BaseModule: {BaseModule.__name__}")
print("\nUnit 1: PASSED")
