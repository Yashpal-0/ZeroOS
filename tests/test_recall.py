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
