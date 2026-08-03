"""Tests for zeroos.surface.app.

do_activate() must never crash: a keyring failure at startup is exactly the
case credentials.load() converts GLib.Error into OSError for (see
credentials.py), and it has to fall through to onboarding rather than take
the app down. All scenarios below -- keyring failure, a stored key, and
accepting onboarding -- are exercised on one registered application instance
-- GApplication only allows one primary instance per application_id to be
registered on the session bus per process, so a second
ZeroOSApplication().register() in the same test session collides with the
first. register() is called before do_activate() because GApplication logs
its own unrelated critical ("windows must be added after ::startup") when a
window is created before the application is registered -- a quirk of calling
do_activate() directly in a test, not something any path under test causes.
"""

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk

from zeroos.agent import credentials
from zeroos.surface import app as app_mod
from zeroos.surface.window import ChatWindow

Adw.init()


def test_do_activate_handles_a_keyring_failure_then_a_stored_key(monkeypatch, capsys):
    application = app_mod.ZeroOSApplication()
    application.register()

    def boom():
        raise OSError("Secret Service not available")

    monkeypatch.setattr(credentials, "load", boom)
    application.do_activate()  # falls through to onboarding, must not raise

    monkeypatch.setattr(credentials, "load", lambda: "sk-existing")
    application.do_activate()  # goes straight to the chat window, must not raise

    assert "CRITICAL" not in capsys.readouterr().err

    _accept_onboarding_and_check_it_hands_off_to_the_chat_window(application, monkeypatch, capsys)


def _accept_onboarding_and_check_it_hands_off_to_the_chat_window(application, monkeypatch, capsys):
    # Reuses the application registered above -- GApplication allows only one
    # primary instance per application_id per process (see module docstring).
    for leftover in list(application.get_windows()):
        leftover.close()

    monkeypatch.setattr(credentials, "load", lambda: (_ for _ in ()).throw(OSError("no key")))
    application.do_activate()  # onboarding branch
    onboarding_window = application.get_windows()[-1]

    monkeypatch.setattr(credentials, "validate", lambda key: True)
    monkeypatch.setattr(credentials, "store", lambda key: None)

    box = onboarding_window.get_content()
    listbox = box.get_first_child()
    while not isinstance(listbox, Gtk.ListBox):
        listbox = listbox.get_next_sibling()
    entry = listbox.get_row_at_index(0)
    entry.set_text("sk-new")

    button = box.get_last_child()
    while not isinstance(button, Gtk.Button):
        button = button.get_prev_sibling()
    button.emit("clicked")  # runs onboarding.build()'s on_accepted -> app.py's accepted()

    assert onboarding_window.get_visible() is False
    windows = application.get_windows()
    assert len(windows) == 1
    assert isinstance(windows[0], ChatWindow)
    assert "CRITICAL" not in capsys.readouterr().err
