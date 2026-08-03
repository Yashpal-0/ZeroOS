"""The chat window. Text in, replies out, agent work off the main thread."""

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


class ChatWindow(Adw.ApplicationWindow):
    def __init__(self, application, api_key: str) -> None:
        super().__init__(application=application, default_width=720, default_height=560,
                         title="ZeroOS")
        self._session = Session(api_key=api_key, ask=lambda rows: ask_on_main_thread(self, rows))
        self._busy = False

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
        self._session.close()
        return False

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
            reply = self._session.send(text)
        except Exception as failure:  # network, rate limit, bad key
            GLib.idle_add(self._show_failure, str(failure), text)
            return
        GLib.idle_add(self._show_reply, reply)

    def _show_reply(self, reply: str) -> bool:
        self._append("assistant", reply)
        self._busy = False
        return GLib.SOURCE_REMOVE

    def _show_failure(self, detail: str, original: str) -> bool:
        self._banner.set_title("Couldn't reach the model. Check your connection.")
        self._banner.set_revealed(True)
        self._entry.set_text(original)
        self._busy = False
        return GLib.SOURCE_REMOVE
