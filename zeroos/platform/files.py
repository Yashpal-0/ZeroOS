"""File operations. GIO where it buys something, stdlib where it does not.

GIO is used for trash() only: moving to the XDG trash correctly means writing
trashinfo metadata, and Gio.File.trash() already does it.
"""

import shutil
from pathlib import Path

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from zeroos.platform import paths



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
        try:
            trash_dir = paths.home() / ".local" / "share" / "Trash" / "files"
            trash_dir.mkdir(parents=True, exist_ok=True)
            target = trash_dir / path.name
            if target.exists():
                import time
                target = trash_dir / f"{path.stem}_{int(time.monotonic())}{path.suffix}"
            shutil.move(str(path), str(target))
        except Exception:
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
