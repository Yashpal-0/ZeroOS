"""Permission tiers. Spec section 4.1.

The 'never' tier from the spec has no representation here on purpose: those
actions are absent from the catalog rather than gated, so there is nothing to
tabulate.
"""

from enum import Enum


class Tier(Enum):
    AUTO = "auto"
    CONFIRM = "confirm"


TIERS: dict[str, Tier] = {
    "list_apps": Tier.AUTO,
    "open_app": Tier.AUTO,
    "open_path": Tier.AUTO,
    "open_url": Tier.AUTO,
    "search_files": Tier.AUTO,
    "read_text_file": Tier.AUTO,
    "list_folder": Tier.AUTO,
    "read_clipboard": Tier.AUTO,
    "notify": Tier.AUTO,
    "set_volume": Tier.AUTO,
    "write_clipboard": Tier.CONFIRM,
    "create_folder": Tier.CONFIRM,
    "write_text_file": Tier.CONFIRM,
    "copy_file": Tier.CONFIRM,
    "move_file": Tier.CONFIRM,
    "trash_file": Tier.CONFIRM,
    "remember": Tier.CONFIRM,
    "forget": Tier.CONFIRM,
    "run_command": Tier.CONFIRM,
}

PATH_ARGUMENTS: dict[str, tuple[str, ...]] = {
    "open_path": ("path",),
    "search_files": ("location",),
    "read_text_file": ("path",),
    "list_folder": ("path",),
    "create_folder": ("path",),
    "write_text_file": ("path",),
    "copy_file": ("source", "destination"),
    "move_file": ("source", "destination"),
    "trash_file": ("path",),
}


MCP_PREFIX = "mcp__"


def tier_of(name: str) -> Tier:
    """Look up a tool's tier. Unknown tools raise: fail closed, never open.

    Every MCP tool is CONFIRM, resolved by prefix rather than by a mount-time
    write to TIERS. Three properties that buys, all deliberate: TIERS is never
    mutated, so test_registry.py's three-place rule keeps meaning what it
    means; unknown non-MCP names still raise; and the prefix is ours -- mount.py
    composes it from a name config.py validated, out of a file the model cannot
    write, so a server cannot name itself into or out of a tier.
    """
    if name.startswith(MCP_PREFIX):
        return Tier.CONFIRM
    return TIERS[name]
