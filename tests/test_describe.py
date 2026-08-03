import pytest

from zeroos.platform import memory
from zeroos.policy import describe


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture(autouse=True)
def data_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))


def test_pretty_strips_the_home_prefix(home):
    assert describe.pretty(home / "Documents" / "Tax 2025") == "Documents / Tax 2025"


def test_pretty_names_home_itself(home):
    assert describe.pretty(home) == "Home"


def test_describes_creating_a_folder(home):
    rows = describe.describe_batch([("create_folder", {"path": str(home / "Documents" / "Tax 2025")})])
    assert rows == ["Create a folder called Tax 2025 in Documents"]


def test_describes_a_single_move(home):
    rows = describe.describe_batch(
        [("move_file", {"source": str(home / "Downloads" / "a.pdf"), "destination": str(home / "Documents" / "a.pdf")})]
    )
    assert rows == ["Move a.pdf from Downloads into Documents"]


def test_collapses_a_run_of_moves_sharing_a_destination(home):
    calls = [
        ("move_file", {"source": str(home / "Downloads" / f"{n}.pdf"), "destination": str(home / "Documents" / "Tax 2025" / f"{n}.pdf")})
        for n in range(4)
    ]
    rows = describe.describe_batch(calls)
    assert rows == ["Move 4 files from Downloads into Documents / Tax 2025"]


def test_does_not_collapse_moves_with_different_destinations(home):
    calls = [
        ("move_file", {"source": str(home / "Downloads" / "a.pdf"), "destination": str(home / "Documents" / "a.pdf")}),
        ("move_file", {"source": str(home / "Downloads" / "b.pdf"), "destination": str(home / "Pictures" / "b.pdf")}),
    ]
    assert len(describe.describe_batch(calls)) == 2


def test_describes_trashing(home):
    rows = describe.describe_batch([("trash_file", {"path": str(home / "Downloads" / "junk.iso")})])
    assert rows == ["Move junk.iso to the trash"]


def test_describes_writing_a_file(home):
    rows = describe.describe_batch(
        [("write_text_file", {"path": str(home / "Documents" / "checklist.txt"), "content": "x"})]
    )
    assert rows == ["Save a note called checklist.txt in Documents"]


def test_describes_the_clipboard(home):
    rows = describe.describe_batch([("write_clipboard", {"text": "hello"})])
    assert rows == ["Put some text on your clipboard"]


def test_never_shows_a_full_path(home):
    rows = describe.describe_batch([("trash_file", {"path": str(home / "Downloads" / "junk.iso")})])
    assert str(home) not in rows[0]


def test_group_batch_reports_which_calls_each_row_covers(home):
    calls = [
        ("create_folder", {"path": str(home / "Documents" / "Tax 2025")}),
        ("move_file", {"source": str(home / "Downloads" / "a.pdf"), "destination": str(home / "Documents" / "Tax 2025" / "a.pdf")}),
        ("move_file", {"source": str(home / "Downloads" / "b.pdf"), "destination": str(home / "Documents" / "Tax 2025" / "b.pdf")}),
    ]
    groups = describe.group_batch(calls)
    assert [text for text, _ in groups] == [
        "Create a folder called Tax 2025 in Documents",
        "Move 2 files from Downloads into Documents / Tax 2025",
    ]
    assert [indices for _, indices in groups] == [[0], [1, 2]]


def test_group_batch_covers_every_call_exactly_once(home):
    calls = [
        ("move_file", {"source": str(home / "Downloads" / "a.pdf"), "destination": str(home / "Documents" / "a.pdf")}),
        ("move_file", {"source": str(home / "Downloads" / "b.pdf"), "destination": str(home / "Pictures" / "b.pdf")}),
        ("trash_file", {"path": str(home / "Downloads" / "junk.iso")}),
    ]
    covered = [i for _, indices in describe.group_batch(calls) for i in indices]
    assert sorted(covered) == list(range(len(calls)))


def test_remember_shows_the_text_being_stored():
    row = describe.describe_batch(
        [("remember", {"text": "My documents live in the Work folder"})]
    )[0]
    assert row == 'Remember: "My documents live in the Work folder"'


def test_remember_shows_the_normalised_text_that_will_be_stored():
    row = describe.describe_batch([("remember", {"text": "a\n\nb"})])[0]
    assert row == 'Remember: "a b"'


def test_forget_resolves_the_id_to_the_facts_text():
    fact_id = memory.add("My documents live in the Work folder")
    row = describe.describe_batch([("forget", {"fact_id": fact_id})])[0]
    assert row == 'Forget: "My documents live in the Work folder"'


def test_forget_never_shows_a_bare_id():
    fact_id = memory.add("something")
    row = describe.describe_batch([("forget", {"fact_id": fact_id})])[0]
    # Equality gives this teeth: a wrong implementation (wrong fact's text,
    # a hardcoded string) can dodge a bare substring check but not this.
    assert row == 'Forget: "something"'
    assert fact_id not in row


def test_forget_an_unknown_id_says_so_in_plain_words():
    row = describe.describe_batch([("forget", {"fact_id": "deadbeef"})])[0]
    assert row == "Forget something that is no longer remembered"


def test_no_memory_row_says_run():
    rows = describe.describe_batch(
        [("remember", {"text": "x"}), ("forget", {"fact_id": "deadbeef"})]
    )
    assert not any(row.startswith("Run ") for row in rows)


def test_a_memory_row_is_always_one_line():
    # Catches a dropped memory.normalise() call: without it the embedded
    # newline survives into the row instead of collapsing to a space.
    row = describe.describe_batch([("remember", {"text": "first\nsecond"})])[0]
    assert "\n" not in row


def test_memory_rows_do_not_collapse_into_a_count():
    rows = describe.describe_batch([("remember", {"text": f"fact {n}"}) for n in range(4)])
    assert len(rows) == 4


def test_an_enormous_remember_is_truncated_for_display():
    """The tool's MAX_CHARS check runs after the dialog. Without truncation
    here a 10 KB argument becomes a 10 KB row, and the row is what spec §6
    asks the user to read."""
    row = describe.describe_batch([("remember", {"text": "x" * 10_000})])[0]
    assert len(row) < memory.MAX_CHARS + 40
    assert row.endswith('…"')


def test_a_remember_row_truncates_at_the_store_cap_not_a_fixed_number():
    # describe._for_display caps on memory.MAX_CHARS, so raising the store cap
    # must move the dialog cap with it. If someone later hardcodes a number
    # here, a fact the user is asked to approve gets cut mid-sentence and the
    # row stops being the thing they consented to.
    row = describe.describe_batch([("remember", {"text": "x" * (memory.MAX_CHARS + 50)})])[0]
    assert "x" * memory.MAX_CHARS in row
    assert row.endswith('…"')
