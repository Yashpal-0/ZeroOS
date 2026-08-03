"""Tests for zeroos.surface.onboarding (Task 16, spec section 7).

build() returns the content Box directly rather than wrapping it in an
Adw.NavigationPage. The brief's original code returned
Adw.NavigationPage(title=..., child=box) and app.py called
window.set_content(build_onboarding(accepted).get_child()) -- but
NavigationPage parents `box` in its own constructor, and GTK4 refuses to
reparent a widget that already has one. test_the_box_can_be_set_as_a_windows_
content_without_a_gtk_critical below is the regression check for that.
"""

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk

from zeroos.agent import credentials
from zeroos.surface import onboarding

Adw.init()


def _children(box):
    widgets = []
    child = box.get_first_child()
    while child:
        widgets.append(child)
        child = child.get_next_sibling()
    return widgets


def _entry_of(box):
    # Adw.PasswordEntryRow is itself a Gtk.ListBoxRow subclass, so
    # listbox.append(entry) did not wrap it -- the row IS the entry.
    listbox = _children(box)[3]
    return listbox.get_row_at_index(0)


def _status_of(box):
    return _children(box)[4]


def _button_of(box):
    return _children(box)[5]


def test_build_returns_a_plain_box():
    assert isinstance(onboarding.build(lambda key: None), Gtk.Box)


def test_the_box_can_be_set_as_a_windows_content_without_a_gtk_critical(capsys):
    window = Adw.Window()
    window.set_content(onboarding.build(lambda key: None))
    assert "CRITICAL" not in capsys.readouterr().err


def test_empty_key_shows_a_status_message_and_does_not_call_on_accepted():
    accepted = []
    box = onboarding.build(accepted.append)
    _button_of(box).emit("clicked")
    assert "paste" in _status_of(box).get_label().lower()
    assert accepted == []


def test_a_validate_failure_shows_a_status_message(monkeypatch):
    monkeypatch.setattr(credentials, "validate", lambda key: False)
    accepted = []
    box = onboarding.build(accepted.append)
    _entry_of(box).set_text("sk-bad")
    _button_of(box).emit("clicked")
    assert "didn't work" in _status_of(box).get_label()
    assert accepted == []


def test_a_store_failure_shows_a_retry_message_and_does_not_crash(monkeypatch):
    monkeypatch.setattr(credentials, "validate", lambda key: True)

    def boom(key):
        raise OSError("Secret Service unreachable")

    monkeypatch.setattr(credentials, "store", boom)
    accepted = []
    box = onboarding.build(accepted.append)
    _entry_of(box).set_text("sk-good")
    _button_of(box).emit("clicked")  # must not raise
    assert "keyring" in _status_of(box).get_label().lower()
    assert accepted == []


def test_a_valid_key_calls_on_accepted_with_the_key(monkeypatch):
    monkeypatch.setattr(credentials, "validate", lambda key: True)
    monkeypatch.setattr(credentials, "store", lambda key: None)
    accepted = []
    box = onboarding.build(accepted.append)
    _entry_of(box).set_text("sk-good")
    _button_of(box).emit("clicked")
    assert accepted == ["sk-good"]
