"""Tests for the batched approval dialog (zeroos.surface.dialog), spec 4.4.

ask_on_main_thread blocks its caller until the dialog is answered, so it is
run on a worker thread here while this (test) thread pumps the GLib main
loop -- the same split the real app uses between the agent thread and the
GTK main thread. The dialog instance itself is captured by swapping in a
subclass of Adw.AlertDialog for the duration of each drive, so assertions
run against the real object the module builds rather than a stand-in.
"""

import threading
import time

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk, GLib

from zeroos.policy.describe import TRASH_REASSURANCE
from zeroos.surface import dialog as dialog_mod
from zeroos.surface.dialog import _confirm_label, _heading, ask_on_main_thread

Adw.init()


def _checks_of(dialog):
    checks = []
    child = dialog.get_extra_child().get_first_child()
    while child:
        checks.append(child)
        child = child.get_next_sibling()
    return checks


def _ask_and_drive(rows, act):
    """Build the dialog for `rows`, run `act(dialog, checks)` once it exists,
    and return (outcome, dialog). `act` must emit a "response" to unblock
    the worker thread running ask_on_main_thread.
    """
    real_alert_dialog = dialog_mod.Adw.AlertDialog
    captured = {}

    class CapturingAlertDialog(real_alert_dialog):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            captured["dialog"] = self

    dialog_mod.Adw.AlertDialog = CapturingAlertDialog
    window = Gtk.Window()
    result = {}
    try:
        def worker():
            result["value"] = ask_on_main_thread(window, rows)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        # ctx.iteration(True) blocks until a source fires. GLib.idle_add fires
        # almost immediately in practice, but nothing would ever wake this loop
        # if the worker died before reaching it, so a timeout heartbeat keeps
        # the deadline below real instead of inert.
        heartbeat = GLib.timeout_add(50, lambda: True)
        ctx = GLib.MainContext.default()
        deadline = time.monotonic() + 5
        while "dialog" not in captured and time.monotonic() < deadline:
            ctx.iteration(True)
        GLib.source_remove(heartbeat)
        assert "dialog" in captured, "dialog was never built"

        act(captured["dialog"], _checks_of(captured["dialog"]))

        thread.join(timeout=5)
        assert not thread.is_alive(), "ask_on_main_thread never returned"
    finally:
        dialog_mod.Adw.AlertDialog = real_alert_dialog

    return result["value"], captured["dialog"]


def test_heading_for_one_row():
    assert _heading(1) == "ZeroOS wants to do something"


def test_heading_for_three_rows():
    assert _heading(3) == "ZeroOS wants to do 3 things"


def test_confirm_label_for_one_row():
    assert _confirm_label(1) == "Do it"


def test_confirm_label_for_three_rows():
    assert _confirm_label(3) == "Do these 3 things"


def test_dialog_body_is_the_trash_reassurance():
    _, dialog = _ask_and_drive(["a", "b", "c"], lambda d, checks: d.emit("response", "deny"))
    assert dialog.get_body() == TRASH_REASSURANCE


def test_button_labels_for_one_row():
    _, dialog = _ask_and_drive(["a"], lambda d, checks: d.emit("response", "deny"))
    assert dialog.get_response_label("deny") == "Deny all"
    assert dialog.get_response_label("allow") == "Do it"


def test_button_labels_for_three_rows():
    _, dialog = _ask_and_drive(["a", "b", "c"], lambda d, checks: d.emit("response", "deny"))
    assert dialog.get_response_label("deny") == "Deny all"
    assert dialog.get_response_label("allow") == "Do these 3 things"


def test_allow_response_maps_unticked_middle_row_to_false():
    def act(dialog, checks):
        checks[1].set_active(False)
        dialog.emit("response", "allow")

    result, _ = _ask_and_drive(["a", "b", "c"], act)
    assert result == [True, False, True]


def test_deny_response_returns_all_false_regardless_of_checks():
    def act(dialog, checks):
        checks[1].set_active(False)
        dialog.emit("response", "deny")

    result, _ = _ask_and_drive(["a", "b", "c"], act)
    assert result == [False, False, False]


def test_dismissal_routes_to_deny():
    # Esc and the window X are not scriptable here; set_close_response("deny")
    # is the assertable proxy that the dialog would treat a dismissal as a
    # rejection rather than a missing answer.
    _, dialog = _ask_and_drive(["a"], lambda d, checks: d.emit("response", "deny"))
    assert dialog.get_close_response() == "deny"
