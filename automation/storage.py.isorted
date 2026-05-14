"""Load workflow JSON files from disk."""

import glob
import json
import os
from typing import Any


def load_workflows(path: str = "workflows") -> list[dict[str, Any]]:
    """Read every *.json in `path` and return them as a list of dicts."""
    if not os.path.isdir(path):
        return []

    workflows: list[dict[str, Any]] = []
    for file in sorted(glob.glob(os.path.join(path, "*.json"))):
        try:
            with open(file, encoding="utf-8") as f:
                data = json.load(f)
            data["_source"] = file
            workflows.append(data)
        except Exception as e:
            # Don't blow up the whole app for one bad workflow
            print(f"[workflow load error] {file}: {e}")

    return workflows


def save_workflow(workflow: dict[str, Any], path: str = "workflows") -> str:
    os.makedirs(path, exist_ok=True)
    name = workflow.get("name", "workflow")
    file_path = os.path.join(path, f"{name}.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(workflow, f, indent=2)
    return file_path
