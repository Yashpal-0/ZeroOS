"""Spec §9. History is persisted and displayed. It is never sent to a model."""

import pytest

from zeroos.agent import history


@pytest.fixture(autouse=True)
def data_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    return tmp_path


def test_no_file_means_no_history():
    assert history.load() == []


def test_append_then_load():
    history.append("find my tax pdf", "I found one file.")
    turn = history.load()[0]
    assert turn["you"] == "find my tax pdf"
    assert turn["zeroos"] == "I found one file."
    assert turn["at"].endswith("Z")


def test_turns_keep_their_order():
    for n in range(5):
        history.append(f"q{n}", f"a{n}")
    assert [t["you"] for t in history.load()] == ["q0", "q1", "q2", "q3", "q4"]


def test_history_is_trimmed_to_the_cap_keeping_the_newest():
    for n in range(history.MAX_TURNS + 10):
        history.append(f"q{n}", "a")
    turns = history.load()
    assert len(turns) == history.MAX_TURNS
    assert turns[-1]["you"] == f"q{history.MAX_TURNS + 9}"
    assert turns[0]["you"] == "q10"


def test_newlines_in_a_turn_survive_as_one_record():
    history.append("line one\nline two", "reply\nreply")
    assert len(history.load()) == 1
    assert history.load()[0]["you"] == "line one\nline two"


def test_a_corrupt_line_is_skipped():
    history.append("q", "a")
    with history.path().open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")
    history.append("q2", "a2")
    assert [t["you"] for t in history.load()] == ["q", "q2"]


def test_an_unreadable_file_loads_as_empty(monkeypatch):
    history.append("q", "a")
    monkeypatch.setattr(
        type(history.path()), "read_text", lambda *a, **k: (_ for _ in ()).throw(OSError("nope"))
    )
    assert history.load() == []


def test_clear_empties_it():
    history.append("q", "a")
    history.clear()
    assert history.load() == []


def test_history_lives_under_the_data_dir(data_home):
    assert str(history.path()).startswith(str(data_home))


def test_append_does_not_raise_on_write_failure(tmp_path, monkeypatch):
    """A failed persistence is acceptable; an exception into the agent loop is
    not. append swallows the failed _write and returns None."""
    data_home = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    # Parent exists, but data_home itself is a file, so mkdir fails.
    data_home.parent.mkdir(parents=True, exist_ok=True)
    data_home.write_text("not a directory")
    result = history.append("should not raise", "reply")
    assert result is None
