"""
firewall_manager.py — Windows Firewall manager plugin.

Uses netsh advfirewall (built into every Windows version since Vista).
No pip dependencies required.

Tools provided:
  firewall_status       — Current firewall profile state (domain/private/public)
  list_firewall_rules   — All rules with optional name/direction/action filter
  get_firewall_rule     — Full details on a single rule
  add_firewall_rule     — Create a new inbound or outbound rule
  delete_firewall_rule  — Remove a rule by name
  enable_firewall       — Turn the firewall on for a profile
  disable_firewall      — Turn the firewall off for a profile (⚠️ risky)
  block_app             — Block an executable from network access
  unblock_app           — Remove block rules for an executable
"""

from __future__ import annotations

import subprocess

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _netsh(*args: str, timeout: int = 15) -> tuple[int, str]:
    """Run netsh and return (returncode, output)."""
    cmd = ["netsh", "advfirewall"] + list(args)
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return -1, "[netsh timed out]"
    except FileNotFoundError:
        return -1, "[netsh not found — this tool requires Windows]"


def _parse_show_state(out: str) -> str:
    """Format the output of 'show allprofiles state' nicely."""
    lines = ["Windows Firewall Status:", ""]
    current_profile = ""
    for line in out.splitlines():
        line = line.strip()
        if not line or "---" in line or line.startswith("Ok"):
            continue
        if "Profile Settings" in line:
            current_profile = line.replace("Profile Settings:", "").strip()
            lines.append(f"  [{current_profile}]")
        elif ":" in line:
            key, _, val = line.partition(":")
            icon = "🔥" if "ON" in val.upper() else "⬜"
            lines.append(f"    {icon} {key.strip()}: {val.strip()}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: firewall_status
# ---------------------------------------------------------------------------


def firewall_status() -> str:
    """
    Show the current Windows Firewall state for all profiles
    (Domain, Private, Public).
    """
    rc, out = _netsh("show", "allprofiles", "state")
    if rc != 0:
        return f"[firewall_status error] {out}"
    return _parse_show_state(out)


# ---------------------------------------------------------------------------
# Tool: list_firewall_rules
# ---------------------------------------------------------------------------


def list_firewall_rules(
    name_filter: str = "",
    direction: str = "all",
    action: str = "all",
    enabled_only: bool = False,
    max_results: int = 100,
) -> str:
    """
    List Windows Firewall rules with optional filters.

    Args:
        name_filter:  Filter rules by name substring (case-insensitive).
        direction:    'all' (default), 'in', or 'out'.
        action:       'all' (default), 'allow', or 'block'.
        enabled_only: Only show enabled rules (default False).
        max_results:  Cap on results returned (default 100).
    """
    args = ["firewall", "show", "rule", "name=all", "verbose"]
    rc, out = _netsh(*args, timeout=30)
    if rc != 0:
        return f"[list_firewall_rules error] {out}"

    # Parse rules from verbose output (each rule block separated by blank lines)
    rules: list[dict] = []
    current: dict = {}

    for line in out.splitlines():
        line = line.strip()
        if not line:
            if current.get("name"):
                rules.append(current)
            current = {}
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            k = key.strip().lower().replace(" ", "_")
            current[k] = val.strip()

    if current.get("name"):
        rules.append(current)

    # Apply filters
    if name_filter:
        nf = name_filter.lower()
        rules = [r for r in rules if nf in r.get("rule_name", r.get("name", "")).lower()]

    if direction != "all":
        rules = [r for r in rules if direction.lower() in r.get("direction", "").lower()]

    if action != "all":
        rules = [r for r in rules if action.lower() in r.get("action", "").lower()]

    if enabled_only:
        rules = [r for r in rules if "yes" in r.get("enabled", "").lower()]

    rules = rules[:max_results]

    if not rules:
        return "No firewall rules matched your filters."

    lines = [
        f"{'Rule Name':<45} {'Dir':<5} {'Action':<8} {'Enabled':<9} {'Profile'}",
        "-" * 90,
    ]
    for r in rules:
        name = r.get("rule_name", r.get("name", "?"))[:44]
        direc = r.get("direction", "?")[:4]
        action_val = r.get("action", "?")[:7]
        enabled = r.get("enabled", "?")
        profile = r.get("profiles", r.get("profile", "?"))[:20]
        action_icon = "✅" if "Allow" in action_val else ("🚫" if "Block" in action_val else " ")
        enabled_icon = "✅" if "Yes" in enabled else "⛔"
        lines.append(
            f"{name:<45} {direc:<5} {action_icon} {action_val:<7} {enabled_icon} {enabled:<8} {profile}"
        )

    lines.append(f"\nTotal: {len(rules)} rule(s)")
    if len(rules) == max_results:
        lines.append(f"(limited to {max_results} — use name_filter or increase max_results)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: get_firewall_rule
# ---------------------------------------------------------------------------


def get_firewall_rule(name: str) -> str:
    """
    Show full details for a specific firewall rule.

    Args:
        name: Exact or partial rule name.
    """
    rc, out = _netsh("firewall", "show", "rule", f"name={name}", "verbose")
    if rc != 0:
        return f"[get_firewall_rule error] {out}"
    if "No rules match" in out or not out.strip():
        return f"No firewall rule found matching '{name}'."
    return out


# ---------------------------------------------------------------------------
# Tool: add_firewall_rule
# ---------------------------------------------------------------------------


def add_firewall_rule(
    name: str,
    direction: str = "in",
    action: str = "allow",
    protocol: str = "tcp",
    local_port: str = "",
    remote_ip: str = "any",
    program: str = "",
    profile: str = "any",
    description: str = "",
) -> str:
    """
    Create a new Windows Firewall rule.

    Args:
        name:       Descriptive name for the rule.
        direction:  'in' (inbound, default) or 'out' (outbound).
        action:     'allow' (default) or 'block'.
        protocol:   'tcp' (default), 'udp', 'any', or a protocol number.
        local_port: Port number(s) or range (e.g. '80', '8080-8090', 'any').
        remote_ip:  Remote IP or subnet to apply rule to (default 'any').
        program:    Full path to an executable to restrict rule to.
        profile:    'any' (default), 'domain', 'private', 'public'.
        description: Optional description for the rule.
    """
    args = [
        "firewall",
        "add",
        "rule",
        f"name={name}",
        f"dir={direction}",
        f"action={action}",
        f"protocol={protocol}",
        f"profile={profile}",
        f"remoteip={remote_ip}",
        "enable=yes",
    ]

    if local_port:
        args.append(f"localport={local_port}")
    if program:
        args.append(f"program={program}")
    if description:
        args.append(f"description={description}")

    rc, out = _netsh(*args)
    if rc == 0 or "Ok." in out:
        return (
            f"✅ Firewall rule '{name}' created:\n"
            f"   Direction: {direction}  Action: {action}  Protocol: {protocol}\n"
            f"   Port: {local_port or 'any'}  Remote IP: {remote_ip}  Profile: {profile}\n"
            f"{out}"
        )
    return f"❌ Failed to create rule '{name}' (exit {rc}):\n{out}"


# ---------------------------------------------------------------------------
# Tool: delete_firewall_rule
# ---------------------------------------------------------------------------


def delete_firewall_rule(name: str, dry_run: bool = True) -> str:
    """
    Delete a Windows Firewall rule by name.

    Args:
        name:    Name of the rule to delete (exact match).
        dry_run: Preview without deleting (default True — set False to delete).
    """
    if dry_run:
        # Check if it exists first
        rc, out = _netsh("firewall", "show", "rule", f"name={name}")
        if "No rules match" in out or not out.strip():
            return f"No rule named '{name}' exists."
        return (
            f"[DRY RUN] Would delete firewall rule '{name}'.\n"
            f"Run with dry_run=False to actually delete.\n\nCurrent rule:\n{out}"
        )

    rc, out = _netsh("firewall", "delete", "rule", f"name={name}")
    if rc == 0 or "Ok." in out or "Deleted" in out:
        return f"✅ Firewall rule '{name}' deleted."
    return f"❌ Failed to delete rule '{name}' (exit {rc}):\n{out}"


# ---------------------------------------------------------------------------
# Tool: enable_firewall / disable_firewall
# ---------------------------------------------------------------------------


def enable_firewall(profile: str = "all") -> str:
    """
    Enable Windows Firewall for a profile.

    Args:
        profile: 'all' (default), 'domain', 'private', 'public'.
    """
    profile_arg = "allprofiles" if profile == "all" else profile + "profile"
    rc, out = _netsh("set", profile_arg, "state", "on")
    if rc == 0 or "Ok." in out:
        return f"✅ Windows Firewall enabled ({profile} profile)."
    return f"❌ Failed to enable firewall (exit {rc}):\n{out}"


def disable_firewall(profile: str = "all") -> str:
    """
    Disable Windows Firewall for a profile.

    ⚠️  WARNING: Disabling the firewall removes network protection.
    Only do this temporarily for troubleshooting.

    Args:
        profile: 'all' (default), 'domain', 'private', 'public'.
    """
    profile_arg = "allprofiles" if profile == "all" else f"{profile}profile"
    rc, out = _netsh("set", profile_arg, "state", "off")
    if rc == 0 or "Ok." in out:
        return (
            f"⚠️  Windows Firewall DISABLED ({profile} profile).\n"
            f"Run enable_firewall() to re-enable when done."
        )
    return f"❌ Failed to disable firewall (exit {rc}):\n{out}"


# ---------------------------------------------------------------------------
# Tool: block_app / unblock_app
# ---------------------------------------------------------------------------


def block_app(program_path: str, name: str = "", dry_run: bool = True) -> str:
    """
    Block an executable from all network access (inbound + outbound).

    Args:
        program_path: Full path to the executable to block.
        name:         Rule name (auto-generated from exe name if omitted).
        dry_run:      Preview without creating rules (default True).
    """
    from pathlib import Path

    exe_name = Path(program_path).name
    rule_name = name or f"BLOCK_{exe_name}"

    if dry_run:
        return (
            f"[DRY RUN] Would create 2 rules to block '{exe_name}':\n"
            f"  1. BLOCK inbound  — {rule_name}_IN\n"
            f"  2. BLOCK outbound — {rule_name}_OUT\n"
            f"  Program: {program_path}\n\n"
            f"Run with dry_run=False to apply."
        )

    results = []
    for direction, suffix in [("in", "_IN"), ("out", "_OUT")]:
        rc, out = _netsh(
            "firewall",
            "add",
            "rule",
            f"name={rule_name}{suffix}",
            f"dir={direction}",
            "action=block",
            "protocol=any",
            f"program={program_path}",
            "enable=yes",
            "profile=any",
        )
        if rc == 0 or "Ok." in out:
            results.append(f"✅ {direction.upper()} rule created: {rule_name}{suffix}")
        else:
            results.append(f"❌ {direction.upper()} rule failed (exit {rc}): {out}")

    return "\n".join(results)


def unblock_app(name: str, dry_run: bool = True) -> str:
    """
    Remove block rules for an application (by rule name prefix or exact name).

    Args:
        name:    Rule name prefix used when block_app was called (e.g. 'BLOCK_chrome.exe').
        dry_run: Preview without deleting (default True).
    """
    # Try exact match and _IN / _OUT suffixes
    candidates = [name, f"{name}_IN", f"{name}_OUT"]
    results = []

    for rule in candidates:
        rc, out = _netsh("firewall", "show", "rule", f"name={rule}")
        if "No rules match" not in out and out.strip():
            if dry_run:
                results.append(f"[DRY RUN] Would delete rule: {rule}")
            else:
                rc2, out2 = _netsh("firewall", "delete", "rule", f"name={rule}")
                if rc2 == 0 or "Ok." in out2:
                    results.append(f"✅ Deleted rule: {rule}")
                else:
                    results.append(f"❌ Failed to delete '{rule}': {out2}")

    if not results:
        return f"No rules found matching '{name}' (or '{name}_IN' / '{name}_OUT')."

    if dry_run:
        results.append("\nRe-run with dry_run=False to actually delete.")
    return "\n".join(results)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(registry) -> None:
    registry.register(
        "firewall_status",
        firewall_status,
        description="Show Windows Firewall state for Domain, Private, and Public profiles.",
        category="system",
        args=[],
    )

    registry.register(
        "list_firewall_rules",
        list_firewall_rules,
        description=(
            "List Windows Firewall rules. Filter by name, direction (in/out), "
            "action (allow/block), and enabled status."
        ),
        category="system",
        args=[
            {
                "name": "name_filter",
                "required": False,
                "description": "Filter by rule name substring",
            },
            {
                "name": "direction",
                "required": False,
                "description": "'all' (default), 'in', or 'out'",
            },
            {
                "name": "action",
                "required": False,
                "description": "'all' (default), 'allow', or 'block'",
            },
            {
                "name": "enabled_only",
                "required": False,
                "description": "Only show enabled rules (default False)",
            },
            {
                "name": "max_results",
                "required": False,
                "description": "Maximum rules to return (default 100)",
            },
        ],
    )

    registry.register(
        "get_firewall_rule",
        get_firewall_rule,
        description="Show full details for a specific Windows Firewall rule by name.",
        category="system",
        args=[
            {"name": "name", "required": True, "description": "Rule name (exact or partial)"},
        ],
    )

    registry.register(
        "add_firewall_rule",
        add_firewall_rule,
        description=(
            "Create a new Windows Firewall rule. Specify direction (in/out), "
            "action (allow/block), protocol, port, and optionally a specific program."
        ),
        category="system",
        args=[
            {"name": "name", "required": True, "description": "Name for the new rule"},
            {"name": "direction", "required": False, "description": "'in' (default) or 'out'"},
            {"name": "action", "required": False, "description": "'allow' (default) or 'block'"},
            {
                "name": "protocol",
                "required": False,
                "description": "'tcp' (default), 'udp', or 'any'",
            },
            {
                "name": "local_port",
                "required": False,
                "description": "Port or range (e.g. '80', '8080-8090', 'any')",
            },
            {
                "name": "remote_ip",
                "required": False,
                "description": "Remote IP/subnet to match (default 'any')",
            },
            {
                "name": "program",
                "required": False,
                "description": "Full path to executable to restrict rule to",
            },
            {
                "name": "profile",
                "required": False,
                "description": "'any' (default), 'domain', 'private', 'public'",
            },
        ],
    )

    registry.register(
        "delete_firewall_rule",
        delete_firewall_rule,
        description=(
            "Delete a Windows Firewall rule by name. "
            "dry_run=True (default) shows what would be deleted without acting."
        ),
        category="system",
        args=[
            {"name": "name", "required": True, "description": "Exact rule name to delete"},
            {
                "name": "dry_run",
                "required": False,
                "description": "Preview without deleting (default True)",
            },
        ],
    )

    registry.register(
        "enable_firewall",
        enable_firewall,
        description="Enable Windows Firewall for all profiles or a specific profile (domain/private/public).",
        category="system",
        args=[
            {
                "name": "profile",
                "required": False,
                "description": "'all' (default), 'domain', 'private', 'public'",
            },
        ],
    )

    registry.register(
        "disable_firewall",
        disable_firewall,
        description=(
            "⚠️  Disable Windows Firewall for a profile. "
            "Use only for troubleshooting — re-enable immediately after."
        ),
        category="system",
        args=[
            {
                "name": "profile",
                "required": False,
                "description": "'all' (default), 'domain', 'private', 'public'",
            },
        ],
    )

    registry.register(
        "block_app",
        block_app,
        description=(
            "Block an executable from all network access by creating inbound + outbound "
            "firewall rules. dry_run=True by default."
        ),
        category="system",
        args=[
            {
                "name": "program_path",
                "required": True,
                "description": "Full path to the executable to block",
            },
            {
                "name": "name",
                "required": False,
                "description": "Rule name prefix (auto-generated if omitted)",
            },
            {
                "name": "dry_run",
                "required": False,
                "description": "Preview without creating rules (default True)",
            },
        ],
    )

    registry.register(
        "unblock_app",
        unblock_app,
        description="Remove block_app firewall rules for an application by rule name prefix.",
        category="system",
        args=[
            {
                "name": "name",
                "required": True,
                "description": "Rule name used with block_app (e.g. 'BLOCK_chrome.exe')",
            },
            {
                "name": "dry_run",
                "required": False,
                "description": "Preview without deleting (default True)",
            },
        ],
    )
