import pytest

from zeroos.policy import gate
from zeroos.policy.sandbox import REFUSAL_MESSAGE


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    (tmp_path / "Downloads").mkdir()
    (tmp_path / "Documents").mkdir()
    return tmp_path


class Asker:
    """Records what it was shown and answers with a canned reply."""

    def __init__(self, answer=True):
        self.answer = answer
        self.calls: list[list[str]] = []

    def __call__(self, rows):
        self.calls.append(list(rows))
        if isinstance(self.answer, list):
            # A canned list that doesn't match the rows asked about makes this
            # fixture lie: it would answer a row the gate never showed, or leave
            # one unanswered, and the test would pass on a coincidence.
            assert len(self.answer) == len(rows), "canned answers must match rows"
            return self.answer
        return [self.answer] * len(rows)


def test_auto_tier_never_reaches_the_asker(home):
    asker = Asker()
    g = gate.Gate(asker)
    g.prepare([("read_text_file", {"path": str(home / "Documents" / "a.txt")})])
    assert asker.calls == []
    assert g.decide("read_text_file", {"path": str(home / "Documents" / "a.txt")})[0] is gate.Verdict.ALLOW


def test_confirm_tier_is_asked_once_for_the_whole_turn(home):
    asker = Asker()
    g = gate.Gate(asker)
    calls = [
        ("trash_file", {"path": str(home / "Downloads" / "a.iso")}),
        ("trash_file", {"path": str(home / "Downloads" / "b.iso")}),
    ]
    g.prepare(calls)
    assert len(asker.calls) == 1
    assert len(asker.calls[0]) == 2


def test_approved_calls_are_allowed(home):
    g = gate.Gate(Asker(answer=True))
    args = {"path": str(home / "Downloads" / "a.iso")}
    g.prepare([("trash_file", args)])
    assert g.decide("trash_file", args)[0] is gate.Verdict.ALLOW


def test_denied_calls_return_the_denial_message(home):
    g = gate.Gate(Asker(answer=False))
    args = {"path": str(home / "Downloads" / "a.iso")}
    g.prepare([("trash_file", args)])
    verdict, message = g.decide("trash_file", args)
    assert verdict is gate.Verdict.DENY
    assert message == gate.DENIED_MESSAGE


def test_partial_approval_allows_only_the_ticked_row(home):
    asker = Asker(answer=[True, False])
    g = gate.Gate(asker)
    first = {"path": str(home / "Downloads" / "a.iso")}
    second = {"path": str(home / "Downloads" / "b.iso")}
    g.prepare([("trash_file", first), ("trash_file", second)])
    assert g.decide("trash_file", first)[0] is gate.Verdict.ALLOW
    assert g.decide("trash_file", second)[0] is gate.Verdict.DENY


def test_sandbox_refusal_happens_before_the_asker_sees_it(home):
    asker = Asker()
    g = gate.Gate(asker)
    args = {"path": "/etc/shadow"}
    g.prepare([("trash_file", args)])
    assert asker.calls == []
    verdict, message = g.decide("trash_file", args)
    assert verdict is gate.Verdict.REFUSE
    assert message == REFUSAL_MESSAGE


def test_refused_auto_tier_call_is_also_refused(home):
    g = gate.Gate(Asker())
    args = {"path": str(home / ".ssh" / "id_rsa")}
    g.prepare([("read_text_file", args)])
    assert g.decide("read_text_file", args)[0] is gate.Verdict.REFUSE


def test_confirm_tier_without_prepare_is_asked_not_denied(home):
    # A call that skipped the batch has not been rejected — nobody has seen it.
    asker = Asker(answer=False)
    g = gate.Gate(asker)
    args = {"path": str(home / "Downloads" / "surprise.iso")}
    verdict, _ = g.decide("trash_file", args)
    assert len(asker.calls) == 1, "it must ask before it denies"
    assert verdict is gate.Verdict.DENY, "and deny only because the answer was no"


def test_a_short_answer_list_is_an_error_not_a_silent_denial(home):
    # The gate has no fallback for a missing answer on purpose: guessing DENY
    # would deny an action the user was never asked about. A dialog that
    # under-answers is a bug in the dialog and must be loud.
    # Not the Asker fixture — it now refuses to under-answer, so it would raise
    # its own assertion and the gate's would never be reached.
    g = gate.Gate(lambda rows: [])
    with pytest.raises(AssertionError):
        g.prepare([("trash_file", {"path": str(home / "Downloads" / "a.iso")})])


def test_an_unanswered_single_ask_is_an_error_not_a_silent_denial(home):
    # decide()'s one-off ask carries the same contract as prepare()'s batch.
    # A dialog that returns no answer is a broken dialog, not a rejection, and
    # treating it as DENY would be exactly the silent denial spec 4.3 forbids.
    g = gate.Gate(lambda rows: [])
    with pytest.raises(AssertionError):
        g.decide("trash_file", {"path": str(home / "Downloads" / "a.iso")})


def test_unknown_tool_is_refused(home):
    g = gate.Gate(Asker())
    verdict, _ = g.decide("run_shell_command", {"cmd": "rm -rf /"})
    assert verdict is gate.Verdict.REFUSE


def test_collapsed_rows_still_map_to_individual_decisions(home):
    # Four moves collapse to one row; one tick must approve all four.
    asker = Asker(answer=[True])
    g = gate.Gate(asker)
    calls = [
        (
            "move_file",
            {
                "source": str(home / "Downloads" / f"{n}.pdf"),
                "destination": str(home / "Documents" / f"{n}.pdf"),
            },
        )
        for n in range(4)
    ]
    g.prepare(calls)
    assert len(asker.calls[0]) == 1
    for _, args in calls:
        assert g.decide("move_file", args)[0] is gate.Verdict.ALLOW
    # The verdicts alone do not prove the fan-out worked. A call the row failed
    # to cover arrives at decide() unprepared, and decide() correctly re-asks —
    # so it ends up ALLOWed anyway and the assertions above stay green. The
    # dialog count is what distinguishes "covered by the row" from "asked twice".
    assert len(asker.calls) == 1, "every call in the row was prepared; none may re-ask"


def test_a_relative_path_prepared_is_the_same_call_when_decided(home):
    # prepare() renders resolved paths but must key the ledger on the raw ones.
    # If the two sides key differently, decide() will not recognise the call
    # prepare() just asked about and will ask a second time. Every other
    # prepare-then-decide test here uses absolute paths, where resolve() is a
    # no-op and the mismatch cannot show itself.
    asker = Asker(answer=True)
    g = gate.Gate(asker)
    args = {"path": "Downloads/a.iso"}
    g.prepare([("trash_file", args)])
    assert len(asker.calls) == 1
    assert g.decide("trash_file", args)[0] is gate.Verdict.ALLOW
    assert len(asker.calls) == 1, "decide must not re-ask what prepare already covered"


def test_a_relative_path_still_shows_its_folder(home):
    # A model may emit "Downloads/Tax 2025/a.pdf" or "~/Downloads/Tax 2025/a.pdf".
    # The sandbox accepts both — they name the same file as the absolute form —
    # so the dialog must name the same folder for all three. describe.pretty()
    # can only do that if it is handed the resolved path.
    asker = Asker()
    g = gate.Gate(asker)
    g.prepare(
        [("move_file", {"source": "Downloads/Tax 2025/a.pdf", "destination": "Documents/a.pdf"})]
    )
    assert asker.calls[0] == ["Move a.pdf from Downloads / Tax 2025 into Documents"]


def test_a_bare_filename_shows_the_home_folder(home):
    asker = Asker()
    g = gate.Gate(asker)
    g.prepare([("write_text_file", {"path": "notes.txt", "content": "x"})])
    assert asker.calls[0] == ["Save a note called notes.txt in Home"]
