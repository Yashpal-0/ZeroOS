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


def test_add_returns_empty_string_on_write_failure(tmp_path, monkeypatch):
    """When write fails, add returns "" instead of raising."""
    data_home = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    # Create parent so data_home's parent exists, but make data_home a file
    data_home.parent.mkdir(parents=True, exist_ok=True)
    data_home.write_text("not a directory")
    # Now mkdir will fail because data_home is a file
    result = memory.add("should fail")
    assert result == ""


def test_remove_returns_false_on_write_failure(tmp_path, monkeypatch):
    """When write fails, remove returns False instead of raising."""
    data_home = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    # First add succeeds
    data_home.mkdir(parents=True, exist_ok=True)
    fact_id = memory.add("something")
    assert fact_id != ""
    # Make directory unwritable
    import stat
    data_home.chmod(0o444)  # read-only
    try:
        # remove should return False, not raise
        result = memory.remove(fact_id)
        assert result is False
    finally:
        data_home.chmod(0o755)  # restore for cleanup


def test_temp_file_cleaned_up_on_write_failure(tmp_path, monkeypatch):
    """When write fails partway, temp file is cleaned up."""
    data_home = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    data_home.mkdir(parents=True, exist_ok=True)
    memory.add("first")
    # Make directory unwritable to cause write to fail
    import stat
    data_home.chmod(0o444)  # read-only
    try:
        # add should return "" and not leave a temp file
        result = memory.add("second")
        assert result == ""
        # Verify no .tmp files left behind by listing dir with write re-enabled
    finally:
        data_home.chmod(0o755)  # restore for cleanup
        temp_files = [p for p in data_home.iterdir() if p.name.endswith(".tmp")]
        assert len(temp_files) == 0, f"Temp files left behind: {temp_files}"


def test_a_matching_fact_ranks_ahead_of_a_non_matching_one():
    facts = [
        {"id": "a", "text": "Yash prefers dark mode"},
        {"id": "b", "text": "Yash keeps tax PDFs in Documents"},
    ]
    ranked = memory._ranked(facts, "where are my tax pdfs", 10)
    assert [f["id"] for f in ranked] == ["b"]


def test_ranking_respects_its_limit():
    facts = [{"id": str(n), "text": f"Yash owns document number {n}"} for n in range(50)]
    assert len(memory._ranked(facts, "document", 10)) == 10


def test_fts_operators_in_a_user_message_are_data_not_syntax():
    # The query is built from the user's message. An unbalanced quote or a bare
    # NEAR would be a syntax error the agent loop would see as a crash.
    facts = [{"id": "a", "text": "Yash keeps tax PDFs in Documents"}]
    assert memory._ranked(facts, 'tax AND NOT "unbalanced NEAR( *', 10)


def test_a_query_with_no_words_ranks_nothing():
    facts = [{"id": "a", "text": "Yash keeps tax PDFs in Documents"}]
    assert memory._ranked(facts, "?! ... ***", 10) == []


def test_a_sqlite_failure_ranks_nothing_instead_of_raising(monkeypatch):
    # A degraded memory feature must not take a turn down. Task 5's selection
    # continues past this with pins and recency.
    def explode(*args, **kwargs):
        raise memory.sqlite3.OperationalError("no such module: fts5")

    monkeypatch.setattr(memory.sqlite3, "connect", explode)
    facts = [{"id": "a", "text": "Yash keeps tax PDFs in Documents"}]
    assert memory._ranked(facts, "tax", 10) == []


def test_a_small_store_is_returned_whole_whatever_the_query():
    # The v0.2.1 guarantee, kept: below the limit, nothing is dropped. This is
    # what recency backfill buys -- there is no threshold constant.
    for n in range(4):
        memory.add(f"Yash owns thing number {n}")
    assert len(memory.search("something entirely unrelated")) == 4


def test_a_query_matching_nothing_still_returns_the_limit():
    # Measured on the real store: "What do you know about me?" matches no fact
    # under BM25. Pure retrieval would send an empty block for the one question
    # memory exists to answer.
    for n in range(30):
        memory.add(f"Yash owns thing number {n}")
    found = memory.search("What do you know about me?")
    assert len(found) == memory.MAX_INJECTED


def test_the_backfill_takes_the_most_recent():
    for n in range(30):
        memory.add(f"Yash owns thing number {n}")
    found = memory.search("What do you know about me?")
    assert found[0]["text"] == "Yash owns thing number 29"


def test_a_matching_fact_beats_a_more_recent_one():
    memory.add("Yash keeps tax PDFs in Documents")
    for n in range(30):
        memory.add(f"Yash owns thing number {n}")
    found = memory.search("where are my tax pdfs")
    assert found[0]["text"] == "Yash keeps tax PDFs in Documents"


def test_never_more_than_the_limit_comes_back():
    for n in range(500):
        memory.add(f"Yash owns document number {n}")
    assert len(memory.search("document")) == memory.MAX_INJECTED


def test_a_pinned_fact_comes_back_for_a_query_it_does_not_match():
    pinned = memory.add("Yash prefers to be called Yash, not Yashpal")
    memory.set_pinned(pinned, True)
    for n in range(30):
        memory.add(f"Yash owns thing number {n}")
    found = memory.search("where are my tax pdfs")
    assert found[0]["id"] == pinned


def test_a_hand_edited_store_with_too_many_pins_keeps_the_first_ten():
    ids = []
    for n in range(memory.MAX_INJECTED + 5):
        fact_id = memory.add(f"Yash owns thing number {n}")
        memory.set_pinned(fact_id, True)
        ids.append(fact_id)

    assert [fact["id"] for fact in memory.search("unrelated")] == ids[:memory.MAX_INJECTED]


def test_a_pinned_fact_is_never_listed_twice():
    pinned = memory.add("Yash keeps tax PDFs in Documents")
    memory.set_pinned(pinned, True)
    memory.add("Yash prefers dark mode")
    found = memory.search("where are my tax pdfs")
    assert [f["id"] for f in found].count(pinned) == 1


def test_a_fact_written_before_pinning_existed_is_still_selectable():
    # No migration: a jsonl line with no "pinned" key must behave as unpinned.
    memory.path().parent.mkdir(parents=True, exist_ok=True)
    memory.path().write_text('{"id": "old", "text": "Yash keeps tax PDFs in Documents"}\n')
    assert [f["id"] for f in memory.search("tax pdfs")] == ["old"]


def test_set_pinned_on_an_unknown_id_returns_false():
    assert memory.set_pinned("nope", True) is False


def test_unpinning_puts_a_fact_back_in_the_ranked_pool():
    fact_id = memory.add("Yash prefers dark mode")
    memory.set_pinned(fact_id, True)
    memory.set_pinned(fact_id, False)
    assert memory.load()[0].get("pinned") is False
