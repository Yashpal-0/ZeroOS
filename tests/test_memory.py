"""Spec §3. The store never raises; every failure path returns a value."""

import pytest

from zeroos.platform import memory


@pytest.fixture(autouse=True)
def data_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    return tmp_path


def test_no_file_means_no_memories():
    assert memory.load() == []


def test_add_then_load():
    fact_id = memory.add("My documents live in the Work folder")
    assert [f["text"] for f in memory.load()] == ["My documents live in the Work folder"]
    assert memory.load()[0]["id"] == fact_id


def test_ids_are_distinct():
    ids = {memory.add(f"fact {n}") for n in range(20)}
    assert len(ids) == 20


def test_remove_returns_true_and_drops_the_fact():
    fact_id = memory.add("something")
    assert memory.remove(fact_id) is True
    assert memory.load() == []


def test_remove_an_unknown_id_returns_false_and_changes_nothing():
    memory.add("something")
    assert memory.remove("deadbeef") is False
    assert len(memory.load()) == 1


def test_remove_tolerates_hostile_ids():
    for hostile in ["", "../../etc/passwd", "\x00", "x" * 100_000, "🙂"]:
        assert memory.remove(hostile) is False


def test_text_of_resolves_an_id():
    fact_id = memory.add("My documents live in the Work folder")
    assert memory.text_of(fact_id) == "My documents live in the Work folder"
    assert memory.text_of("deadbeef") is None


def test_newlines_and_tabs_collapse_to_single_spaces():
    assert memory.normalise("a\n\nb\tc   d") == "a b c d"


def test_control_characters_are_stripped():
    assert memory.normalise("hello\x1b[31mworld\x07") == "hello[31mworld"


def test_normalise_trims():
    assert memory.normalise("   spaced   ") == "spaced"


def test_a_stored_fact_is_always_one_line():
    memory.add(memory.normalise("first\nsecond"))
    assert len(memory.path().read_text(encoding="utf-8").strip().splitlines()) == 1


def test_the_store_never_imports_the_agent_package():
    """Spec §2's dependency order: platform is the bottom layer. If this
    module grew an `agent` import, policy/describe.py importing it (Task 5)
    would drag the agent package into the policy layer."""
    import inspect

    source = inspect.getsource(memory)
    assert "zeroos.agent" not in source


def test_a_corrupt_line_is_skipped_and_the_rest_load():
    memory.add("alpha")
    memory.add("beta")
    lines = memory.path().read_text(encoding="utf-8").splitlines()
    memory.path().write_text("\n".join([lines[0], "{not json", lines[1]]) + "\n", encoding="utf-8")
    assert [f["text"] for f in memory.load()] == ["alpha", "beta"]


def test_a_line_missing_required_keys_is_skipped():
    memory.path().parent.mkdir(parents=True, exist_ok=True)
    memory.path().write_text('{"id": "abc"}\n{"id": "d", "text": "kept"}\n', encoding="utf-8")
    assert [f["text"] for f in memory.load()] == ["kept"]


def test_an_unreadable_file_loads_as_empty(monkeypatch):
    memory.add("alpha")
    monkeypatch.setattr(
        type(memory.path()), "read_text", lambda *a, **k: (_ for _ in ()).throw(OSError("nope"))
    )
    assert memory.load() == []


def test_writes_leave_no_temp_file_behind():
    memory.add("alpha")
    assert [p.name for p in memory.path().parent.iterdir()] == ["memory.jsonl"]


def test_the_store_lives_under_the_data_dir(data_home):
    assert str(memory.path()).startswith(str(data_home))
