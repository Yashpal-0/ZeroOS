"""Spec §10. The pane is what makes a bad memory removable without a terminal."""

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk  # noqa: E402

import pytest  # noqa: E402

from zeroos.agent import history  # noqa: E402
from zeroos.platform import memory, settings  # noqa: E402
from zeroos.surface import recall  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    Adw.init()


def labels(widget) -> list[str]:
    found = []
    child = widget.get_first_child()
    while child is not None:
        if isinstance(child, Gtk.Label):
            found.append(child.get_text())
        found.extend(labels(child))
        child = child.get_next_sibling()
    return found


def shown(dialog) -> list[str]:
    """Every label in a presented dialog.

    Adw.PreferencesDialog builds its widget tree lazily — before present() it
    has no children at all, so walking the return of build() finds nothing no
    matter what build() did. Presenting into a throwaway window realises the
    tree without needing the dialog on screen.
    """
    dialog.present(Gtk.Window())
    return labels(dialog)


def widgets(widget, kind) -> list:
    """Every descendant of the given type, in tree order."""
    found = []
    child = widget.get_first_child()
    while child is not None:
        if isinstance(child, kind):
            found.append(child)
        found.extend(widgets(child, kind))
        child = child.get_next_sibling()
    return found


def row_titled(dialog, title):
    return next(r for r in widgets(dialog, Adw.ActionRow) if r.get_title() == title)


def trash_button_for(dialog, title):
    """The trash button belonging to one named fact row.

    Not widgets(dialog, Gtk.Button)[0] — that is tree order across the whole
    presented dialog, which includes Adwaita's own chrome (a go-previous button
    already sits a few places along). One added header button upstream would
    silently turn this into a test that clicks the wrong widget.
    """
    return next(
        b
        for b in widgets(row_titled(dialog, title), Gtk.Button)
        if b.get_icon_name() == "user-trash-symbolic"
    )


def test_every_remembered_fact_is_shown():
    memory.add("My documents live in the Work folder")
    memory.add("Prefers PDFs over Word files")
    seen = shown(recall.build(None))
    assert any("My documents live in the Work folder" in text for text in seen)
    assert any("Prefers PDFs over Word files" in text for text in seen)


def test_the_empty_state_says_nothing_is_remembered():
    assert any("hasn't been asked to remember" in text for text in shown(recall.build(None)))


def test_deleting_a_fact_removes_it_from_the_store():
    fact_id = memory.add("delete me")
    recall.forget(fact_id)
    assert memory.load() == []


def test_forget_everything_empties_the_store():
    for n in range(5):
        memory.add(f"fact {n}")
    recall.forget_everything()
    assert memory.load() == []


def test_past_turns_are_shown_newest_first():
    history.append("older question", "older reply")
    history.append("newer question", "newer reply")
    seen = shown(recall.build(None))
    newer = next(i for i, t in enumerate(seen) if "newer question" in t)
    older = next(i for i, t in enumerate(seen) if "older question" in t)
    assert newer < older


def test_clearing_history_empties_it():
    history.append("q", "a")
    recall.clear_history()
    assert history.load() == []


def test_the_form_of_address_selector_reflects_the_stored_value():
    settings.set_address("maam")
    dialog = recall.build(None)
    assert recall.selected_address(dialog) == "maam"


def test_choosing_an_address_persists_it():
    recall.choose_address("none")
    assert settings.address() == "none"


def test_a_fact_containing_markup_is_shown_as_text():
    memory.add("<b>not bold</b>")
    assert any("<b>not bold</b>" in text for text in shown(recall.build(None)))


def test_a_past_turn_containing_markup_is_shown_as_text():
    """Same defence as the fact rows: history text is attacker-influenced too —
    a reply quoting a file's contents lands in this pane verbatim."""
    history.append("<i>question</i>", "<b>reply</b>")
    seen = shown(recall.build(None))
    assert any("<i>question</i>" in text for text in seen)
    assert any("<b>reply</b>" in text for text in seen)


# The tests above drive the module functions directly, which leaves every
# signal connect in this pane unproven: all of them can be deleted with the
# suite still green. These four drive the widgets instead, because "removable
# without a terminal" is a claim about the buttons, not about the functions
# behind them.


def test_the_trash_button_forgets_that_fact_and_leaves_the_others():
    memory.add("delete me")
    memory.add("keep me")
    dialog = recall.build(None)
    dialog.present(Gtk.Window())
    assert len(memory.load()) == 2

    trash_button_for(dialog, "delete me").emit("clicked")

    assert [fact["text"] for fact in memory.load()] == ["keep me"]
    seen = labels(dialog)
    assert not any("delete me" in text for text in seen)
    assert any("keep me" in text for text in seen)


def test_the_bulk_rows_ask_before_they_delete(monkeypatch):
    """Both danger rows must reach _confirm, and carry the right action into
    it. A row wired straight to the action would empty the store here."""
    asked = []
    monkeypatch.setattr(recall, "_confirm", lambda dialog, action: asked.append(action))
    memory.add("still here")
    history.append("q", "a")
    dialog = recall.build(None)
    dialog.present(Gtk.Window())

    row_titled(dialog, "Forget everything").emit("activated")
    row_titled(dialog, "Clear history").emit("activated")

    assert asked == [recall.forget_everything, recall.clear_history]
    assert len(memory.load()) == 1
    assert len(history.load()) == 1


def test_dismissing_the_confirmation_deletes_nothing():
    """cancel is both the default and the close response, so Escape and
    clicking away land here. Dismissal is never approval."""
    memory.add("survives")
    dialog = recall.build(None)
    dialog.present(Gtk.Window())

    recall._on_confirmed(dialog, recall.forget_everything, "cancel")
    assert len(memory.load()) == 1

    recall._on_confirmed(dialog, recall.forget_everything, "delete")
    assert memory.load() == []


def test_picking_a_form_of_address_in_the_combo_persists_it():
    settings.set_address("sir")
    dialog = recall.build(None)
    dialog.present(Gtk.Window())
    combo = widgets(dialog, Adw.ComboRow)[0]

    combo.set_selected(settings.ADDRESSES.index("none"))

    assert settings.address() == "none"
