"""Spec section 4. The filter is the security boundary of v0.3."""

import pytest

from zeroos.agent import notice
from zeroos.platform import memory


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
    client = FakeClient(reply="one\ntwo\nthree\nfour")
    assert notice.candidates(client, TRANSCRIPT) == ["one", "two"]


def test_an_over_long_candidate_is_dropped_not_truncated():
    # Truncating changes what a fact says, and the user would be approving
    # text the model did not write.
    client = FakeClient(reply="x" * (memory.MAX_CHARS + 1) + "\nkeep me")
    assert notice.candidates(client, TRANSCRIPT) == ["keep me"]


def test_a_failing_client_yields_no_candidates_and_does_not_raise():
    # Nothing in this path may raise into the agent loop. A failed pass is
    # indistinguishable from a pass that found nothing, which is correct.
    assert notice.candidates(FakeClient(error=RuntimeError("network")), TRANSCRIPT) == []


def test_an_empty_transcript_yields_nothing():
    assert notice.candidates(FakeClient(reply="something"), []) == []
