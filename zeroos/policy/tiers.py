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


def tier_of(name: str) -> Tier:
    """Look up a tool's tier. Unknown tools raise: fail closed, never open."""
    return TIERS[name]
