"""The chat window. Text in, replies out, agent work off the main thread.

A reply arrives in two parts: the sentence JARVIS says, and the part he only
shows. See split().
"""

import re
import threading

import gi

gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from zeroos.agent.session import Session  # noqa: E402
from zeroos.platform.system import remember_clipboard  # noqa: E402
from zeroos.surface import recall  # noqa: E402
from zeroos.surface.dialog import ask_on_main_thread  # noqa: E402


def _on_clipboard_text(clipboard, result) -> None:
    """read_text_async callback: mirrors whatever is on the clipboard, from
    any source, so read_clipboard() can see pastes ZeroOS did not write
    itself. See platform/system.py's read_clipboard() docstring."""
    try:
        text = clipboard.read_text_finish(result)
    except GLib.Error:
        return
    remember_clipboard(text or "")


def _watch_clipboard(clipboard) -> None:
    """Refresh the mirror now, and again every time the clipboard changes."""
    clipboard.read_text_async(None, _on_clipboard_text)
    clipboard.connect("changed", lambda cb: cb.read_text_async(None, _on_clipboard_text))


# The point at which a spoken line has stopped being one. Not a setting: a
# number the user can raise is a number that gets raised until the split stops
# meaning anything.
SPOKEN_MAX = 200

# A line of its own holding nothing but three hyphens -- what prompt.py asks
# for. Indentation is allowed because prompt.py's own example is indented, and
# a model that copies the example verbatim must not silently lose the split.
MARKER = re.compile(r"\n[ \t]*---[ \t]*(?:\n|$)")


def split(reply: str) -> tuple[str, str]:
    """The sentence JARVIS says, and the part he only shows.

    Presentation and nothing else. session.py keeps the whole reply, marker
    and all, in the message log and in history, so the model still sees what
    it said and the recall pane is unaffected by any of this.

    The first marker is the one that counts; a model that emits several keeps
    the rest inside the detail, where they read as the rules they look like.

    The length guard is for the turns where the model ignores the format at
    all. It cuts only at a sentence boundary: with no ". " inside the first
    SPOKEN_MAX characters nothing moves, because one long sentence spoken
    whole reads better than one cut mid-thought.
    """
    parts = MARKER.split(reply, maxsplit=1)
    spoken, detail = parts[0], parts[1] if len(parts) > 1 else ""
    if len(spoken) > SPOKEN_MAX:
        head, stop, tail = spoken[:SPOKEN_MAX].rpartition(". ")
        if head:
            detail = f"{tail}{spoken[SPOKEN_MAX:]}\n\n{detail}"
            spoken = head + stop.rstrip()
    spoken, detail = spoken.strip(), detail.strip()
    # A reply that is nothing but detail is still a reply. Showing it under an
    # empty line would be the blank window that send() already refuses to
    # produce, arriving by another route.
    return (spoken, detail) if spoken else (detail, "")


class ChatWindow(Adw.ApplicationWindow):
    def __init__(self, application, api_key: str) -> None:
        super().__init__(application=application, default_width=720, default_height=560,
                         title="ZeroOS")
        self._session = Session(api_key=api_key, ask=lambda rows: ask_on_main_thread(self, rows))
        self._busy = False
        self._closing = False
        # The Gtk.Label tokens are streaming into, or None when the next token
        # starts a new bubble. Reset on "done" and before each "tools" batch.
        self._streaming_label = None

        _watch_clipboard(Gdk.Display.get_default().get_clipboard())

        self._transcript = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                                   margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        scroller = Gtk.ScrolledWindow(vexpand=True, child=self._transcript)

        self._entry = Gtk.Entry(placeholder_text="What would you like me to do?",
                                margin_start=12, margin_end=12, margin_bottom=12)
        self._entry.connect("activate", self._on_submit)

        self._banner = Adw.Banner(revealed=False, button_label="Retry")
        self._banner.connect("button-clicked", lambda _b: self._on_submit(self._entry))

        header = Adw.HeaderBar()
        knows = Gtk.Button(icon_name="view-list-symbolic", tooltip_text="What ZeroOS knows")
        knows.connect("clicked", lambda _b: recall.build(self).present(self))
        header.pack_end(knows)

        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        layout.append(header)
        layout.append(self._banner)
        layout.append(scroller)
        layout.append(self._entry)
        self.set_content(layout)

        # Without this the usage line is never written: nothing else in the
        # app calls close(), and the process just exits.
        self.connect("close-request", self._on_close)

    def _on_close(self, _window) -> bool:
        """Halt the close, run the closing summary off the main thread, then
        destroy for real.

        session.close() may open the approval dialog, and
        dialog.ask_on_main_thread does GLib.idle_add followed by a blocking
        wait. Called from the main thread -- which is where close-request
        runs -- the idle callback can never fire, because the main loop is
        inside that wait. It deadlocks every time.

        The window stays visible until close() returns: ask_on_main_thread's
        dialog is presented on this window (dialog.present(window)), so
        hiding the window first would present the dialog on a parent that
        is not on screen, and the user could never answer it. destroy() at
        the end takes the window away, dialog and all, in one step.

        A turn still in flight means no closing summary, per spec section 7:
        the summary's dialog would clear the consent ledger out from under the
        running turn. The flag is read here, on the main thread, and handed to
        the worker as a value. Every other read and write of _busy is on the
        main thread too -- _on_submit is a signal handler, and the two clears
        arrive by idle_add -- and that is the whole reason a flag is enough
        where a lock would otherwise be needed. Reading it inside finish()
        would be a read from the worker and would give that reason away.
        """
        if self._closing:
            return False
        self._closing = True
        summary = not self._busy

        def finish() -> None:
            self._session.close(summary=summary)
            GLib.idle_add(self.destroy)

        threading.Thread(target=finish, daemon=True).start()
        return True

    def _append(self, who: str, text: str) -> None:
        label = Gtk.Label(label=text, wrap=True, xalign=0, selectable=True)
        if who == "user":
            label.add_css_class("accent")
        self._transcript.append(label)

    def _on_submit(self, entry) -> None:
        if self._busy:
            return
        text = entry.get_text().strip()
        if not text:
            return
        self._banner.set_revealed(False)
        self._append("user", text)
        entry.set_text("")
        self._busy = True
        # The entry stays populated on failure so the user does not retype.
        threading.Thread(target=self._run_turn, args=(text,), daemon=True).start()

    def _run_turn(self, text: str) -> None:
        """Runs on a worker thread. All UI updates marshal back via idle_add."""
        try:
            self._session.send(text, on_event=self._on_event)
        except Exception as failure:  # network, rate limit, bad key
            GLib.idle_add(self._show_failure, str(failure), text)

    def _on_event(self, kind: str, payload) -> None:
        """Marshal a streaming event to the main thread. Fires from the worker."""
        GLib.idle_add(self._handle_event, kind, payload)

    def _handle_event(self, kind: str, payload) -> bool:
        if kind == "token":
            self._on_token(payload)
        elif kind == "tools":
            self._on_tools(payload)
        elif kind == "done":
            self._show_reply(payload)
        return GLib.SOURCE_REMOVE

    def _on_token(self, delta: str) -> None:
        if self._streaming_label is None:
            self._streaming_label = Gtk.Label(wrap=True, xalign=0, selectable=True)
            self._transcript.append(self._streaming_label)
        self._streaming_label.set_label(
            (self._streaming_label.get_label() or "") + delta
        )

    def _on_tools(self, descriptions: list[str]) -> None:
        # ponytail: per-token set_label is O(n) per token, so very long replies
        # are O(n²) in the label length. Batch with a ~50ms timer if a tester
        # notices stutter. Not worth pre-building.
        for sentence in descriptions:
            row = Gtk.Label(label=sentence, wrap=True, xalign=0, selectable=True,
                            opacity=0.6, margin_start=12, margin_top=2)
            self._transcript.append(row)
        self._streaming_label = None  # next tokens start a new bubble

    def _show_reply(self, reply: str) -> bool:
        self._streaming_label = None  # finalize: the streaming bubble is done
        spoken, detail = split(reply)
        self._append("assistant", spoken)
        if detail:
            # Collapsed. The whole point of moving it off the spoken line is
            # that the user does not have to read it.
            body = Gtk.Label(label=detail, wrap=True, xalign=0, selectable=True,
                             margin_start=12, margin_top=6)
            self._transcript.append(Gtk.Expander(label="details", child=body))
        self._busy = False
        return GLib.SOURCE_REMOVE

    def _show_failure(self, detail: str, original: str) -> bool:
        self._banner.set_title("Couldn't reach the model. Check your connection.")
        self._banner.set_revealed(True)
        self._entry.set_text(original)
        self._busy = False
        return GLib.SOURCE_REMOVE
