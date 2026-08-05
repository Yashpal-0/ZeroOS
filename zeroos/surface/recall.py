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

import shlex
import threading

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk  # noqa: E402

from zeroos.agent import history  # noqa: E402
from zeroos.mcp import config as mcp_config  # noqa: E402
from zeroos.mcp import mount  # noqa: E402
from zeroos.platform import memory, settings  # noqa: E402

_ADDRESS_LABELS = {"sir": "Sir", "maam": "Ma'am", "none": "No title"}


def forget(fact_id: str) -> None:
    memory.remove(fact_id)


def set_pinned(fact_id: str, pinned: bool) -> None:
    memory.set_pinned(fact_id, pinned)


def _pinned_count() -> int:
    return len([fact for fact in memory.load() if fact.get("pinned")])


def forget_everything() -> None:
    for fact in memory.load():
        memory.remove(fact["id"])


def clear_history() -> None:
    history.clear()


def choose_address(value: str) -> None:
    settings.set_address(value)


def build(parent, gate=None) -> Adw.PreferencesDialog:
    dialog = Adw.PreferencesDialog(title="What ZeroOS knows")
    dialog._gate = gate
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
    page.add(_servers_group(dialog))
    dialog.add(page)
    dialog._page = page


def _redraw(dialog) -> None:
    dialog.remove(dialog._page)
    _fill(dialog)


def _memory_group(dialog) -> Adw.PreferencesGroup:
    group = Adw.PreferencesGroup(
        title="Remembered",
        description=(
            "Things you asked ZeroOS to remember. It is told the "
            f"{memory.MAX_INJECTED} most relevant of these each time it "
            "answers — pinned ones always, so every pin is one less slot for "
            "the rest."
        ),
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
        switch = Gtk.Switch(
            active=bool(fact.get("pinned")),
            valign=Gtk.Align.CENTER,
            tooltip_text="Always tell ZeroOS this",
        )
        switch.connect("state-set", lambda _s, state, i=fact["id"]: _pin_row(dialog, i, state))
        row.add_suffix(switch)
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
        # Imported here, not at module scope: window.py imports this module, so
        # a top-level import would close the cycle. The whole reply is kept --
        # this pane is the archive, and nothing in it is too long to look at --
        # but the marker itself is window.py's format, not something to read.
        from zeroos.surface.window import MARKER

        row = Adw.ActionRow(title=turn["you"], use_markup=False,
                            subtitle=MARKER.sub("\n", turn["zeroos"]).strip())
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


def _pin_row(dialog, fact_id: str, state: bool) -> bool:
    """Pin or unpin one fact. True blocks the switch, which is the refusal.

    Pins fill the injection slots first, so an eleventh pin would push one of
    the ten out at injection time -- the user's explicit choice discarded
    without a word. Refusing here is the only place that failure can be made
    visible. Unpinning is never refused.
    """
    if state and _pinned_count() >= memory.MAX_INJECTED:
        _pin_limit_reached(dialog)
        return True
    set_pinned(fact_id, state)
    return False


def _pin_limit_reached(dialog) -> None:
    alert = Adw.AlertDialog(
        heading=f"{memory.MAX_INJECTED} facts are already pinned",
        body=(
            f"ZeroOS is told {memory.MAX_INJECTED} facts each time it answers, "
            "and pinned ones fill those first. Unpin something to pin this."
        ),
    )
    alert.add_response("ok", "OK")
    alert.present(dialog)


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


def add_server(entry: dict, gate) -> threading.Thread:
    """Write one server and remount. Like everything in this pane, it does not
    pass through the gate: recall.py:7-8's asymmetry holds, this is the user
    acting rather than the model. Correspondingly there is no add_server tool
    in the catalog and there will not be one.
    """
    valid, _ = mcp_config.load()
    mcp_config.save([e for e in valid if e["name"] != entry["name"]] + [entry])
    return _remount(gate)


def remove_server(name: str, gate) -> threading.Thread:
    valid, _ = mcp_config.load()
    mcp_config.save([entry for entry in valid if entry["name"] != name])
    return _remount(gate)


def _remount(gate) -> threading.Thread:
    """Off the main thread, for the reason spec section 5 gives: a dead remote
    server costs 120 seconds, and this runs from a button press.

    The thread is returned so a test can join it rather than sleep on it.
    """
    thread = threading.Thread(target=lambda: mount.load(gate), daemon=True)
    thread.start()
    return thread


def _servers_group(dialog) -> Adw.PreferencesGroup:
    group = Adw.PreferencesGroup(
        title="Servers",
        description="Extra tools ZeroOS can use. Everything a server offers asks before it runs.",
    )
    valid, skipped = mcp_config.load()
    states = {record["name"]: record for record in mount.status()}
    entries = [(entry["name"], states.get(entry["name"])) for entry in valid]
    entries += [(entry["name"], _skipped_record(entry)) for entry in skipped]

    if not entries:
        group.add(Adw.ActionRow(title="No servers yet.", use_markup=False))
    for name, record in entries:
        # use_markup=False on every row carrying a server-supplied string, for
        # the reason recall.py:10-12 already gives: it defaults to True, and a
        # status wrapped in <span> would render invisible in the screen that
        # exists so the user can remove the server.
        row = Adw.ActionRow(title=name, subtitle=_status_line(record), use_markup=False)
        row.set_property("title-lines", 0)
        row.set_property("subtitle-lines", 0)
        button = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER)
        button.connect("clicked", lambda _b, n=name: _remove_row(dialog, n))
        row.add_suffix(button)
        group.add(row)
    group.add(_add_server_row(dialog))
    return group


def _skipped_record(entry: dict) -> dict:
    return {"state": "failed", "tools": 0, "error": entry["reason"], "stderr": []}


def _status_line(record) -> str:
    if record is None:
        # mount.load() runs off the main thread, so a pane opened during
        # startup has a configured server and no record for it yet.
        return "Connecting…"
    if record["state"] == "connected":
        count = record["tools"]
        return f"Connected — {count} tool" + ("" if count == 1 else "s")
    detail = record.get("error", "")
    tail = " ".join(record.get("stderr", []))
    return f"Not working — {detail} {tail}".strip()


def _remove_row(dialog, name: str) -> None:
    remove_server(name, dialog._gate)
    _redraw(dialog)


def _add_server_row(dialog) -> Adw.ActionRow:
    """A footer row that opens a three-field alert to add a server."""
    row = Adw.ActionRow(
        activatable=True, title="Add a server", use_markup=False,
        subtitle="Name, command or URL.",
    )
    row.connect("activated", lambda _r: _add_server_dialog(dialog))
    return row


def _add_server_dialog(dialog) -> None:
    alert = Adw.AlertDialog(heading="Add a server")
    alert.add_response("cancel", "Cancel")
    alert.add_response("add", "Add")
    alert.set_default_response("cancel")
    alert.set_close_response("cancel")

    name = Adw.EntryRow(title="Name")
    command = Adw.EntryRow(title="Command (e.g. npx -y @mcp/server)")
    url = Adw.EntryRow(title="URL (https://…)")
    for entry_row in (name, command, url):
        alert.set_extra_child(entry_row)

    def _on_response(_a, response):
        if response != "add":
            return
        entry = {"name": name.get_text().strip()}
        cmd = command.get_text().strip()
        link = url.get_text().strip()
        if cmd:
            entry["command"] = shlex.split(cmd)
        elif link:
            entry["url"] = link
        else:
            return
        add_server(entry, dialog._gate)
        _redraw(dialog)

    alert.connect("response", _on_response)
    alert.present(dialog)
