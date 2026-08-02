"""Hand a path or URL to the desktop's default handler."""

from pathlib import Path

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402


def _launch(uri: str) -> None:
    try:
        Gio.AppInfo.launch_default_for_uri(uri, None)
    except GLib.Error as error:
        # Same contract as platform/files.py: GLib.Error inherits from
        # RuntimeError, not OSError, so it would sail straight through the
        # `except (OSError, ValueError)` in the opener tools. No registered
        # handler and portal failures are both ordinary inside a Flatpak.
        raise OSError(str(error)) from error


def launch_path(path: Path) -> None:
    _launch(Gio.File.new_for_path(str(path)).get_uri())


def launch_uri(uri: str) -> None:
    _launch(uri)
