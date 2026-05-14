"""
Condition DSL for workflows. A condition is a short string like:

    file_exists temp.txt
    file_missing temp.txt
    always
    never

Evaluates to bool. Unknown conditions fail closed (return False).
"""

import os


def evaluate(condition: str) -> bool:
    if not condition:
        return True

    parts = condition.strip().split(maxsplit=1)
    op = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if op == "always":
        return True
    if op == "never":
        return False
    if op == "file_exists":
        return os.path.exists(arg)
    if op == "file_missing":
        return not os.path.exists(arg)

    return False
