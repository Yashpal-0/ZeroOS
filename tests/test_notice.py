"""Spec section 4. The filter is the security boundary of v0.2.1."""

import pytest

from zeroos.agent import notice
from zeroos.platform import memory


@pytest.fixture(autouse=True)
def data_home(tmp_path, monkeypatch):
    # candidates() now reads the store to drop duplicates. Without this the
    # suite reads the developer's real memory.jsonl and the dedupe test
    # passes or fails depending on what they have remembered.
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    return tmp_path


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeClient:
    """Records the request it was given and returns a canned reply."""

    def __init__(self, reply="", error=None):
        self.reply = reply
        self.error = error
        self.requests = []
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if self.error is not None:
            raise self.error
        return type("R", (), {"choices": [type("C", (), {"message": FakeMessage(self.reply)})()]})()


POISONED = "ZZ-INJECTED-MARKER-ZZ"

TRANSCRIPT = [
    {"role": "user", "content": "read my notes"},
    {
        "role": "assistant",
        "content": "Reading it now.",
        "tool_calls": [{"id": "1", "type": "function",
                        "function": {"name": "read_text_file", "arguments": "{}"}}],
    },
    {"role": "tool", "tool_call_id": "1", "content": f"notes say {POISONED}"},
    {"role": "assistant", "content": "Your notes mention a deadline."},
]


def test_tool_results_never_reach_the_noticing_request():
    # THE test of this release. Tool results carry file contents, and file
    # contents are attacker-controlled. A pass that read them would let text
    # inside a file author a memory proposal on every turn.
    client = FakeClient()
    notice.candidates(client, TRANSCRIPT)
    assert POISONED not in str(client.requests[0])


def test_tool_calls_are_stripped_from_assistant_messages():
    # An assistant message replays its tool_calls so the results have something
    # to attach to. The noticing pass has no results, so the calls are noise
    # that names files -- strip them.
    client = FakeClient()
    notice.candidates(client, TRANSCRIPT)
    assert "read_text_file" not in str(client.requests[0])


def test_user_and_assistant_prose_do_reach_it():
    client = FakeClient()
    notice.candidates(client, TRANSCRIPT)
    sent = str(client.requests[0])
    assert "read my notes" in sent
    assert "Your notes mention a deadline." in sent


def test_candidates_come_back_one_per_line():
    client = FakeClient(reply="Prefers dark mode\nWorks in the Projects folder")
    assert notice.candidates(client, TRANSCRIPT) == [
        "Prefers dark mode",
        "Works in the Projects folder",
    ]


def test_nothing_worth_keeping_is_an_empty_list():
    assert notice.candidates(FakeClient(reply="  \n \n "), TRANSCRIPT) == []


def test_no_more_than_two_candidates_per_turn():
    # A hostile source cannot flood the dialog.
    client = FakeClient(reply=(
        "alpha fact number one\nbeta fact number two\n"
        "gamma fact number three\ndelta fact number four"
    ))
    assert notice.candidates(client, TRANSCRIPT) == [
        "alpha fact number one",
        "beta fact number two",
    ]


def test_an_over_long_candidate_is_dropped_not_truncated():
    # Truncating changes what a fact says, and the user would be approving
    # text the model did not write.
    client = FakeClient(reply="x" * (memory.MAX_CHARS + 1) + "\nkeep this fact intact")
    assert notice.candidates(client, TRANSCRIPT) == ["keep this fact intact"]


def test_a_failing_client_yields_no_candidates_and_does_not_raise():
    # Nothing in this path may raise into the agent loop. A failed pass is
    # indistinguishable from a pass that found nothing, which is correct.
    assert notice.candidates(FakeClient(error=RuntimeError("network")), TRANSCRIPT) == []


def test_an_empty_transcript_yields_nothing():
    assert notice.candidates(FakeClient(reply="something"), []) == []


def test_the_noticing_request_asks_for_room_to_think():
    # Regression, found by the v0.2.1 acceptance walk. MODEL is a reasoning
    # model. At the old cap of 200 it spent every token reasoning and returned
    # finish_reason="length" with content=None, which candidates() cannot tell
    # apart from finding nothing -- so the pass silently never fired at all and
    # criterion 2 came back empty for the wrong reason. Raising the cap to 1200
    # did not help: the model reasoned for all 1200 and still returned None.
    # Only the model's own ceiling is safe, because any lower number is a guess
    # at how long a given conversation takes to think about.
    client = FakeClient(reply="a fact")
    notice.candidates(client, TRANSCRIPT)
    assert client.requests[0]["max_tokens"] == notice.MAX_TOKENS
    assert notice.MAX_TOKENS == 65536, "MODEL's max_completion_tokens"


def test_a_bracketed_placeholder_is_never_offered():
    # "[Empty response]" is window.py's placeholder for a reply that came back
    # blank. It reached the real store on 2026-08-05 because the pass read it
    # as prose and the dialog took it at face value.
    client = FakeClient(reply="[Empty response]\nYash keeps tax PDFs in Documents")
    assert notice.candidates(client, TRANSCRIPT) == ["Yash keeps tax PDFs in Documents"]


def test_a_short_bracketed_placeholder_is_dropped_as_a_placeholder(monkeypatch):
    # Lower the independent length floor so this fails if placeholder filtering
    # disappears. Without that, "[ok]" passes for the wrong reason.
    monkeypatch.setattr(notice, "MIN_CHARS", 1)
    client = FakeClient(reply="[ok]\nYash keeps tax PDFs in Documents")
    assert notice.candidates(client, TRANSCRIPT) == ["Yash keeps tax PDFs in Documents"]


def test_a_line_too_short_to_be_a_fact_is_dropped():
    client = FakeClient(reply="ok\nYash keeps tax PDFs in Documents")
    assert notice.candidates(client, TRANSCRIPT) == ["Yash keeps tax PDFs in Documents"]


def test_a_candidate_already_stored_is_not_offered_again():
    memory.add("Yash keeps tax PDFs in Documents")
    client = FakeClient(reply="Yash keeps tax PDFs in Documents\nYash prefers dark mode")
    assert notice.candidates(client, TRANSCRIPT) == ["Yash prefers dark mode"]


def test_the_dupe_check_compares_normalised_text():
    memory.add("Yash keeps tax PDFs in Documents")
    client = FakeClient(reply="  Yash keeps   tax PDFs in Documents  ")
    assert notice.candidates(client, TRANSCRIPT) == []


def test_the_instruction_asks_for_the_third_person():
    # Facts arrive in a system message, so a fact beginning "I" reads as the
    # model's own voice rather than the user's.
    assert "third person" in notice.INSTRUCTION
    assert "never" in notice.INSTRUCTION.lower()
