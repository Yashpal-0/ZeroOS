"""Clipboard, volume, and notifications."""

import subprocess

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gdk, Gio  # noqa: E402


def _clipboard():
    display = Gdk.Display.get_default()
    if display is None:
        raise OSError("no display")
    return display.get_clipboard()


def read_clipboard() -> str:
    # ponytail: synchronous read via the GTK main loop is awkward, so the
    # window installs a text-only mirror and this returns its last value.
    # See surface/window.py: it calls remember_clipboard() on focus-in.
    return _CLIPBOARD_MIRROR.get("text", "")


_CLIPBOARD_MIRROR: dict[str, str] = {}


def remember_clipboard(text: str) -> None:
    """Called by the window whenever the clipboard changes."""
    _CLIPBOARD_MIRROR["text"] = text


def write_clipboard(text: str) -> None:
    _clipboard().set(text)
    remember_clipboard(text)


def set_volume(percent: int) -> None:
    """Set the default sink's volume.

    ponytail: shells out to pactl rather than binding libgvc. If pactl turns
    out to be missing from the Flatpak runtime, Task 16 bundles
    pulseaudio-utils; that is cheaper than a D-Bus audio binding.

    NOTE: list form, never shell=True — a repository hook blocks the latter.
    """
    subprocess.run(
        ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"],
        check=True,
        capture_output=True,
        timeout=5,
    )


def notify(title: str, body: str) -> None:
    application = Gio.Application.get_default()
    if application is None:
        raise OSError("no application")
    notification = Gio.Notification.new(title)
    notification.set_body(body)
    application.send_notification(None, notification)
