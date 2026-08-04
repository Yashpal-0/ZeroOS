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


class _StubSession:
    """Stands in for Session so the window can be built without an API key.
    Records close() rather than writing a usage line."""

    def __init__(self, *args, **kwargs):
        self.closed = 0

    def close(self):
        self.closed += 1


def _window(monkeypatch):
    """A ChatWindow with its session stubbed out. Needs a display; the suite
    already runs the dialog tests against one."""
    gi.require_version("Adw", "1")
    gi.require_version("Gtk", "4.0")
    from gi.repository import Adw, Gtk

    Adw.init()
    monkeypatch.setattr(window, "Session", _StubSession)
    app = Adw.Application(application_id="io.zerostic.ZeroOS.Test")
    return window.ChatWindow(application=app, api_key="test"), Gtk


def test_the_header_bar_has_a_button_that_opens_the_recall_pane(monkeypatch):
    from zeroos.surface import recall

    opened = []
    monkeypatch.setattr(recall, "build", lambda parent: opened.append(parent) or _NoOpDialog())
    chat, Gtk = _window(monkeypatch)

    buttons = [w for w in _walk(chat) if isinstance(w, Gtk.Button)
               and w.get_property("tooltip-text") == "What ZeroOS knows"]
    assert len(buttons) == 1, "the header bar must offer exactly one way into the pane"
    buttons[0].emit("clicked")
    assert opened == [chat], "the button must actually build the pane, not just exist"


class _SyncThread:
    """Stands in for threading.Thread: runs the target immediately instead of
    on a real thread, so a test can assert on its effect right after emit()
    without racing a background thread it has no handle to."""

    def __init__(self, target, daemon=None):
        self._target = target

    def start(self) -> None:
        self._target()


def test_closing_the_window_records_the_session(monkeypatch):
    chat, _ = _window(monkeypatch)
    monkeypatch.setattr(window, "threading", type("_T", (), {"Thread": _SyncThread}))
    assert chat._session.closed == 0
    chat.emit("close-request")
    assert chat._session.closed == 1, (
        "nothing else in the app calls close(), so an unwired close-request "
        "means the usage line is never written"
    )


class _CapturingThread:
    """Stands in for threading.Thread: records the target instead of running
    it, so a test can assert on _on_close's synchronous effects -- the halt,
    the flag -- without the target's own work (session.close()) having run
    yet. Running it inline here would prove nothing: a deadlocking _on_close
    and a correct one look identical if start() runs the target immediately."""

    def __init__(self, target, daemon=None):
        self.target = target

    def start(self) -> None:
        pass


def test_close_request_halts_the_close_until_the_summary_finishes(monkeypatch):
    # ask_on_main_thread does GLib.idle_add then blocks on the event. Called
    # from the main thread -- which is where close-request runs -- the idle
    # callback can never fire, because the main loop is sitting inside wait().
    # It deadlocks every time. So the close is halted, the work moves to a
    # worker thread, and the window is destroyed when it comes back.
    chat, _ = _window(monkeypatch)
    monkeypatch.setattr(window, "threading", type("_T", (), {"Thread": _CapturingThread}))
    assert chat._on_close(chat) is True, "the first close-request must halt"
    assert chat._session.closed == 0, "close() must not run on the calling thread"
    chat._closing = True
    assert chat._on_close(chat) is False, "the second must let it through"


class _NoOpDialog:
    def present(self, parent):
        pass


def _walk(widget):
    found = []
    child = widget.get_first_child()
    while child is not None:
        found.append(child)
        found.extend(_walk(child))
        child = child.get_next_sibling()
    return found


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
