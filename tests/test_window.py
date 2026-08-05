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
        self.summaries = []
        self._gate = None  # window.py's mount.load thread reads this

    def close(self, summary=True):
        self.closed += 1
        self.summaries.append(summary)


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
    monkeypatch.setattr(recall, "build", lambda parent, gate=None: opened.append(parent) or _NoOpDialog())
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
    assert chat._closing is True, (
        "the first call must set the flag itself -- setting it here instead "
        "would let an _on_close that never sets it pass, and in the app that "
        "spawns a second close() thread on a second X press"
    )
    assert chat._on_close(chat) is False, "the second must let it through"


def test_closing_during_a_turn_skips_the_summary(monkeypatch):
    # Spec section 7: the summary is skipped entirely when the model is
    # mid-turn. The summary's dialog routes through gate.prepare(), which
    # opens by clearing the consent ledger -- under a live turn that makes the
    # turn re-ask for an action the user has already approved.
    chat, _ = _window(monkeypatch)
    monkeypatch.setattr(window, "threading", type("_T", (), {"Thread": _SyncThread}))
    scheduled = []
    monkeypatch.setattr(window.GLib, "idle_add", lambda callback, *a: scheduled.append(callback))

    chat._busy = True
    chat.emit("close-request")

    assert chat._session.summaries == [False], "a turn in flight means no summary"
    assert chat.destroy in scheduled, "the window must still go away"


def test_closing_between_turns_still_runs_the_summary(monkeypatch):
    # The complement: without this, skipping unconditionally would pass.
    chat, _ = _window(monkeypatch)
    monkeypatch.setattr(window, "threading", type("_T", (), {"Thread": _SyncThread}))
    monkeypatch.setattr(window.GLib, "idle_add", lambda callback, *a: None)

    chat.emit("close-request")

    assert chat._session.summaries == [True]


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


def test_a_reply_with_no_marker_is_spoken_whole():
    assert window.split("Four tax PDFs are filed, Sir.") == (
        "Four tax PDFs are filed, Sir.", ""
    )


def test_the_marker_moves_everything_after_it_out_of_the_spoken_line():
    spoken, detail = window.split("Four tax PDFs are filed, Sir.\n---\n2024-return.pdf\nw2.pdf")
    assert spoken == "Four tax PDFs are filed, Sir."
    assert detail == "2024-return.pdf\nw2.pdf"


def test_an_indented_marker_still_splits():
    # prompt.py's example is indented, so a model copying it verbatim indents
    # the marker. Matching only a flush-left one would lose the split on
    # exactly the replies that followed the instructions most literally.
    spoken, detail = window.split("Filed, Sir.\n    ---\n    2024-return.pdf")
    assert (spoken, detail) == ("Filed, Sir.", "2024-return.pdf")


def test_a_long_spoken_line_is_cut_back_to_a_sentence():
    long_line = "I looked at every one of them. " * 12  # well past SPOKEN_MAX
    spoken, detail = window.split(long_line + "\n---\nthe list")
    assert len(spoken) <= window.SPOKEN_MAX
    assert spoken.endswith("."), "the guard must cut at a sentence, not mid-word"
    assert detail.endswith("the list"), (
        "the overflow belongs above the detail the model itself moved down, "
        "not appended after it"
    )
    assert "I looked at every one of them." in detail


def test_one_long_sentence_is_left_alone():
    # No ". " within reach. Speaking it whole is worse than nothing being
    # shown; cutting it mid-thought is worse than both.
    unbroken = "a" * (window.SPOKEN_MAX + 50)
    assert window.split(unbroken) == (unbroken, "")


def test_a_reply_that_is_only_detail_is_still_spoken():
    # Otherwise the label is blank, which reads as the crash session.py's
    # STALLED message exists to avoid.
    assert window.split("\n---\njust the list") == ("just the list", "")


def test_the_prompt_asks_for_the_marker_the_window_splits_on():
    # The two halves of the design are in different files; nothing else fails
    # if one of them changes the format and the other does not.
    from zeroos.agent import prompt

    assert window.MARKER.search(prompt.SYSTEM_PROMPT), (
        "the prompt's worked example must show a marker line window.py "
        "recognises -- the model copies the example, not the description"
    )


def test_the_details_are_shown_but_not_spoken(monkeypatch):
    chat, Gtk = _window(monkeypatch)
    chat._show_reply("Filed, Sir.\n---\n2024-return.pdf")

    labels = [w.get_text() for w in _walk(chat._transcript) if isinstance(w, Gtk.Label)]
    expanders = [w for w in _walk(chat._transcript) if isinstance(w, Gtk.Expander)]
    assert "Filed, Sir." in labels
    assert len(expanders) == 1, "the detail must be behind a disclosure, not in the reply"
    assert expanders[0].get_expanded() is False, "the user must not have to read it"


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


def test_streaming_tokens_then_done_produces_spoken_and_details(monkeypatch):
    """Tokens stream into a label; 'done' finalises via split() into spoken +
    a details expander when the reply carries a --- marker."""
    chat, Gtk = _window(monkeypatch)

    # Stream tokens that build a reply containing the marker.
    for token in ["Four files moved.\n", "---\n", "a.pdf b.pdf"]:
        chat._handle_event("token", token)

    # Finalise: _show_reply applies split() to the full reply.
    chat._show_reply("Four files moved.\n---\na.pdf b.pdf")

    labels = [w for w in _walk(chat) if isinstance(w, Gtk.Label)]
    texts = [l.get_label() for l in labels]
    assert any("Four files moved" in t for t in texts), "spoken must be visible"
    expanders = [w for w in _walk(chat) if isinstance(w, Gtk.Expander)]
    assert len(expanders) >= 1, "details must be collapsed under an expander"


def test_streaming_tool_event_appends_a_dimmed_row(monkeypatch):
    """A 'tools' event appends a progress row and resets the streaming bubble."""
    chat, Gtk = _window(monkeypatch)

    chat._handle_event("token", "Checking ")
    chat._handle_event("tools", ["Move a.pdf to the trash"])

    labels = [w for w in _walk(chat) if isinstance(w, Gtk.Label)]
    texts = [l.get_label() for l in labels]
    assert any("Checking" in t for t in texts), "streamed text must remain"
    assert any("Move a.pdf" in t for t in texts), "the tools row must appear"
    assert chat._streaming_label is None, "tools must reset the streaming bubble"


def test_the_window_loads_mounts_off_the_main_thread():
    """Spec section 5: a dead remote server costs the 120-second call timeout,
    and on the main thread that is 120 seconds of no window at all. The
    constructor must start a worker thread whose target is mount.load."""
    import inspect

    from zeroos.mcp import mount

    source = inspect.getsource(window.ChatWindow.__init__)
    assert "mount.load" in source, (
        "__init__ must call mount.load off the main thread so the window "
        "presents immediately with builtins"
    )
    assert "threading.Thread" in source, "the mount load must run on a worker thread"
