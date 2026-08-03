"""The batched approval dialog. Spec section 4.4.

Copy rules, all load-bearing:
  - folder names, never full paths        (describe.pretty already ensures it)
  - counts instead of lists past three    (describe.describe_batch collapses)
  - no jargon
  - the trash reassurance is permanent, not conditional
"""

import threading

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from zeroos.policy.describe import TRASH_REASSURANCE  # noqa: E402


def ask_on_main_thread(window, rows: list[tuple[str, bool]]) -> list[bool]:
    """Show the dialog from any thread and block until the user answers.

    Each row arrives paired with the state its box starts in. Memory rows
    arrive unticked (spec section 5): v0.3 puts rows here that the user did
    not ask for, and an unread dialog must store nothing rather than
    everything. The gate decides the state; this function only renders it.
    """
    answered = threading.Event()
    outcome: list[bool] = [False] * len(rows)

    def build() -> bool:
        dialog = Adw.AlertDialog(
            heading=_heading(len(rows)),
            body=TRASH_REASSURANCE,
        )
        checks = []
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for row, ticked in rows:
            check = Gtk.CheckButton(label=row, active=ticked)
            check.set_property("margin-start", 6)
            # A CheckButton's label does not wrap by default. describe_batch
            # caps a remember row at about 313 characters, which still runs far
            # wider than the dialog can ever be on one line, so what the user
            # sees is a sentence running off the edge. A row you cannot read is
            # not consent.
            check.get_last_child().set_wrap(True)
            check.get_last_child().set_xalign(0)
            checks.append(check)
            box.append(check)
        dialog.set_extra_child(box)

        dialog.add_response("deny", "Deny all")
        dialog.add_response("allow", _confirm_label(len(rows)))
        dialog.set_response_appearance("allow", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("allow")
        # Esc and the window X route to "deny", so dismissing the dialog fires
        # `responded` like any other answer. This is what lets the gate treat a
        # dismissal as a rejection the user made, rather than as a missing
        # answer it has to guess about. Do not remove it.
        dialog.set_close_response("deny")

        def responded(_dialog, response: str) -> None:
            if response == "allow":
                outcome[:] = [check.get_active() for check in checks]
            else:
                outcome[:] = [False] * len(rows)
            answered.set()

        dialog.connect("response", responded)
        dialog.present(window)
        return GLib.SOURCE_REMOVE

    GLib.idle_add(build)
    answered.wait()
    return outcome


def _heading(count: int) -> str:
    return "ZeroOS wants to do something" if count == 1 else f"ZeroOS wants to do {count} things"


def _confirm_label(count: int) -> str:
    return "Do it" if count == 1 else f"Do these {count} things"
