import pytest

from zeroos.policy import describe


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    return tmp_path


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
