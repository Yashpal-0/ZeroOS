"""Hand a path or URL to the desktop's default handler."""

from pathlib import Path

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio  # noqa: E402


def launch_path(path: Path) -> None:
    Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(str(path)).get_uri(), None)


def launch_uri(uri: str) -> None:
    Gio.AppInfo.launch_default_for_uri(uri, None)
