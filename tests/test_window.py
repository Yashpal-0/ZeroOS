"""Tests for zeroos.surface.window's clipboard mirror wiring.

platform/system.py's read_clipboard() can only ever see text ZeroOS itself
wrote via write_clipboard() unless something calls remember_clipboard() with
whatever is actually on the system clipboard. window.py is that something:
it watches Gdk's default clipboard and mirrors any change, from any source.
These tests exercise the callback directly, with a fake clipboard object, so
they do not depend on GLib main-loop timing or a real paste.
"""

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib

from zeroos.platform import system
from zeroos.surface import window


class _FakeClipboard:
    def __init__(self, text):
        self._text = text

    def read_text_finish(self, result):
        return self._text


class _FailingClipboard:
    def read_text_finish(self, result):
        raise GLib.Error("no text on clipboard")


class _RecordingClipboard:
    """Stands in for Gdk.Clipboard: records the "changed" handler instead of
    needing a real GLib main loop to fire it."""

    def __init__(self, text):
        self._text = text
        self.handlers = {}

    def read_text_async(self, cancellable, callback):
        callback(self, None)

    def read_text_finish(self, result):
        return self._text

    def connect(self, name, handler):
        self.handlers[name] = handler


def test_text_from_outside_zeroos_reaches_read_clipboard(monkeypatch):
    monkeypatch.setattr(system, "_CLIPBOARD_MIRROR", {})
    window._on_clipboard_text(_FakeClipboard("copied in firefox"), None)
    assert system.read_clipboard() == "copied in firefox"


def test_none_text_is_mirrored_as_empty_string(monkeypatch):
    monkeypatch.setattr(system, "_CLIPBOARD_MIRROR", {})
    window._on_clipboard_text(_FakeClipboard(None), None)
    assert system.read_clipboard() == ""


def test_a_read_failure_is_swallowed_not_raised(monkeypatch):
    monkeypatch.setattr(system, "_CLIPBOARD_MIRROR", {})
    window._on_clipboard_text(_FailingClipboard(), None)  # must not raise


def test_watch_clipboard_mirrors_a_later_external_change(monkeypatch):
    # Discriminating test: unlike the _on_clipboard_text tests above, this
    # exercises _watch_clipboard itself, so it fails if either the initial
    # read_text_async call or the "changed" signal connection is removed.
    monkeypatch.setattr(system, "_CLIPBOARD_MIRROR", {})
    clipboard = _RecordingClipboard("copied in firefox")
    window._watch_clipboard(clipboard)
    assert system.read_clipboard() == "copied in firefox"

    clipboard._text = "copied in a text editor"
    clipboard.handlers["changed"](clipboard)
    assert system.read_clipboard() == "copied in a text editor"
