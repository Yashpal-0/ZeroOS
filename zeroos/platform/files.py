"""File operations. GIO where it buys something, stdlib where it does not.

GIO is used for trash() only: moving to the XDG trash correctly means writing
trashinfo metadata, and Gio.File.trash() already does it.
"""

import shutil
from pathlib import Path

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402


def move(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(str(destination))
    shutil.move(str(source), str(destination))


def copy(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(str(destination))
    if source.is_dir():
        shutil.copytree(str(source), str(destination))
    else:
        shutil.copy2(str(source), str(destination))


def trash(path: Path) -> None:
    """Move to the XDG trash. Never deletes — see spec section 3."""
    if not path.exists():
        raise FileNotFoundError(str(path))
    try:
        Gio.File.new_for_path(str(path)).trash(None)
    except GLib.Error as error:
        # GLib.Error inherits from RuntimeError, not OSError, so it would sail
        # straight through the `except (OSError, ValueError)` in Task 7's
        # trash_file — the one catalog tool without a bare Exception catch. A
        # failed trash would then escape the catalog boundary and kill the turn.
        # Converting here keeps this module's stated contract true for every
        # caller instead of making each one remember a GIO-specific case.
        raise OSError(str(error)) from error


def make_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=False)


def search(root: Path, query: str, limit: int = 50) -> list[Path]:
    """Case-insensitive substring match on file names, breadth unlimited.

    ponytail: a live rglob, no index. Fine for a home directory on an SSD;
    if it becomes slow, the upgrade path is Tracker via D-Bus, not a
    hand-rolled index.
    """
    needle = query.lower()
    found: list[Path] = []
    for candidate in root.rglob("*"):
        if any(part.startswith(".") for part in candidate.relative_to(root).parts):
            continue
        if needle in candidate.name.lower():
            found.append(candidate)
            if len(found) >= limit:
                break
    return found
