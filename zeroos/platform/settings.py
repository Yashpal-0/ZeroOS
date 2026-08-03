"""User preferences. One key in v0.2: how ZeroOS addresses you.

Anything unreadable, unparseable, or unrecognised resolves to "sir", which is
v0.1's hardcoded behaviour. An absent settings file therefore changes nothing.
"""

import json
import os
from pathlib import Path

from zeroos.platform import paths

ADDRESSES = ("sir", "maam", "none")
DEFAULT = "sir"


def path() -> Path:
    return paths.config_dir() / "settings.json"


def _load() -> dict:
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def address() -> str:
    value = _load().get("address")
    return value if value in ADDRESSES else DEFAULT


def set_address(value: str) -> None:
    """Raises on an unknown value. Only the recall pane calls this; it is not
    reachable from the model, so failing loudly is safe here."""
    if value not in ADDRESSES:
        raise ValueError(f"unknown form of address: {value!r}")
    _save({**_load(), "address": value})


def _save(data: dict) -> None:
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(temp, target)
