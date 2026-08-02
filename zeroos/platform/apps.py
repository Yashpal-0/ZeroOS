"""Installed application discovery and launch, via .desktop entries."""

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402


def _visible():
    return [info for info in Gio.AppInfo.get_all() if info.should_show()]


def installed() -> list[str]:
    return sorted({info.get_display_name() for info in _visible()})


def _launch(info) -> bool:
    try:
        info.launch([], None)
    except GLib.Error as error:
        # Same contract as zeroos/platform/opener.py and files.py: GLib.Error
        # inherits from RuntimeError, not OSError, so it would sail straight
        # through the catalog's `except OSError`.
        raise OSError(str(error)) from error
    return True


def launch(name: str) -> bool:
    """Launch by display name, case-insensitive. False if no such app."""
    wanted = name.strip().lower()
    for info in _visible():
        if info.get_display_name().lower() == wanted:
            return _launch(info)
    for info in _visible():
        if wanted in info.get_display_name().lower():
            return _launch(info)
    return False
