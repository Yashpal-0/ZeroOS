"""The memory and history pane. Spec §10.

This pane is what makes spec §6's secondary defences real: a fact that got
through a carelessly-ticked dialog has to be findable and removable without
a terminal.

Deletion here does not pass through the gate. It is the user acting, not the
model — the same asymmetry as the user dragging a file to the trash.

Fact text and past messages are attacker-influenced (spec §6), and
Adw.PreferencesRow:use-markup defaults to TRUE — so every row carrying that
text sets use_markup=False explicitly. Not enabling it is not enough.
"""

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk  # noqa: E402

from zeroos.agent import history  # noqa: E402
from zeroos.platform import memory, settings  # noqa: E402

_ADDRESS_LABELS = {"sir": "Sir", "maam": "Ma'am", "none": "No title"}


def forget(fact_id: str) -> None:
    memory.remove(fact_id)


def forget_everything() -> None:
    for fact in memory.load():
        memory.remove(fact["id"])


def clear_history() -> None:
    history.clear()


def choose_address(value: str) -> None:
    settings.set_address(value)


def build(parent) -> Adw.PreferencesDialog:
    dialog = Adw.PreferencesDialog(title="What ZeroOS knows")
    _fill(dialog)
    return dialog


def _fill(dialog) -> None:
    """Build the one page. Kept separate from build() so a deletion can redraw
    the pane in place: the alternative is a widget that lies about the store
    until the user closes and reopens it."""
    page = Adw.PreferencesPage()
    page.add(_memory_group(dialog))
    page.add(_history_group(dialog))
    page.add(_settings_group(dialog))
    dialog.add(page)
    dialog._page = page


def _redraw(dialog) -> None:
    dialog.remove(dialog._page)
    _fill(dialog)


def _memory_group(dialog) -> Adw.PreferencesGroup:
    group = Adw.PreferencesGroup(
        title="Remembered",
        description="Things you asked ZeroOS to remember. It is told these every time you talk to it.",
    )
    facts = memory.load()
    if not facts:
        group.add(Adw.ActionRow(title="ZeroOS hasn't been asked to remember anything yet."))
        return group
    for fact in facts:
        # use_markup=False is load-bearing, not tidiness: it defaults to True
        # on Adw.PreferencesRow, and a fact wrapped in <span> would render
        # invisible in the screen that exists so the user can delete it.
        row = Adw.ActionRow(
            title=fact["text"], subtitle=fact.get("created", ""), use_markup=False
        )
        row.set_property("title-lines", 0)
        button = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER)
        button.connect("clicked", lambda _b, i=fact["id"]: _forget_row(dialog, i))
        row.add_suffix(button)
        group.add(row)
    group.add(_danger_row("Forget everything", lambda: _confirm(dialog, forget_everything)))
    return group


def _history_group(dialog) -> Adw.PreferencesGroup:
    group = Adw.PreferencesGroup(
        title="Past conversations",
        description="Kept so you can look back. ZeroOS is not told any of this.",
    )
    turns = history.load()
    if not turns:
        group.add(Adw.ActionRow(title="Nothing here yet."))
        return group
    for turn in reversed(turns):
        row = Adw.ActionRow(title=turn["you"], subtitle=turn["zeroos"], use_markup=False)
        row.set_property("title-lines", 0)
        row.set_property("subtitle-lines", 0)
        group.add(row)
    group.add(_danger_row("Clear history", lambda: _confirm(dialog, clear_history)))
    return group


def _settings_group(dialog) -> Adw.PreferencesGroup:
    group = Adw.PreferencesGroup(title="Settings")
    row = Adw.ComboRow(title="How ZeroOS addresses you")
    row.set_model(Gtk.StringList.new([_ADDRESS_LABELS[key] for key in settings.ADDRESSES]))
    row.set_selected(settings.ADDRESSES.index(settings.address()))
    row.connect(
        "notify::selected",
        lambda r, _p: choose_address(settings.ADDRESSES[r.get_selected()]),
    )
    dialog._address_row = row
    group.add(row)
    return group


def selected_address(dialog) -> str:
    return settings.ADDRESSES[dialog._address_row.get_selected()]


def _forget_row(dialog, fact_id: str) -> None:
    """One fact, deleted without a confirmation. Undoing it means asking ZeroOS
    to remember the thing again, which is a sentence — unlike the two bulk
    actions below, which are not recoverable that way."""
    forget(fact_id)
    _redraw(dialog)


def _danger_row(label: str, activate) -> Adw.ActionRow:
    row = Adw.ActionRow(activatable=True, title=label, use_markup=False)
    row.add_css_class("error")
    row.connect("activated", lambda _r: activate())
    return row


def _confirm(dialog, action) -> None:
    """The two bulk actions are the only thing in this pane the user cannot
    undo, so they ask first. The pane's own deletions never reach the gate —
    this is the user acting, and the question is courtesy, not policy."""
    alert = Adw.AlertDialog(
        heading="Are you sure?",
        body="This cannot be undone.",
    )
    alert.add_response("cancel", "Cancel")
    alert.add_response("delete", "Delete")
    alert.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
    alert.set_default_response("cancel")
    alert.set_close_response("cancel")
    alert.connect("response", lambda _a, response: _on_confirmed(dialog, action, response))
    alert.present(dialog)


def _on_confirmed(dialog, action, response: str) -> None:
    if response != "delete":
        return
    action()
    _redraw(dialog)
