"""Spec §4. Both tools are confirm-tier and neither ever raises."""

import pytest

from zeroos.platform import memory
from zeroos.catalog import memory as catalog_memory
from zeroos.policy import gate as gate_module
from zeroos.policy.gate import Verdict
from zeroos.policy.tiers import Tier, tier_of


@pytest.fixture(autouse=True)
def data_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))


class AllowGate:
    def decide(self, name, args):
        return Verdict.ALLOW, ""


class DenyGate:
    def decide(self, name, args):
        return Verdict.DENY, "You said no."


def tools(gate):
    return {t.name: t for t in catalog_memory.bind(gate)}


def remember(gate, text):
    """Invoke remember the way the agent loop does: with a dictionary."""
    return tools(gate)["remember"].call({"text": text})


def forget(gate, fact_id):
    return tools(gate)["forget"].call({"fact_id": fact_id})


def test_both_tools_are_confirm_tier():
    assert tier_of("remember") is Tier.CONFIRM
    assert tier_of("forget") is Tier.CONFIRM


def test_remember_stores_the_fact():
    remember(AllowGate(), "My documents live in the Work folder")
    assert [f["text"] for f in memory.load()] == ["My documents live in the Work folder"]


def test_remember_normalises_before_storing():
    remember(AllowGate(), "a\n\nb\tc")
    assert memory.load()[0]["text"] == "a b c"


def test_a_denied_remember_stores_nothing():
    result = remember(DenyGate(), "should not land")
    assert result == "You said no."
    assert memory.load() == []


def test_a_denied_forget_deletes_nothing():
    fact_id = memory.add("keep me")
    assert forget(DenyGate(), fact_id) == "You said no."
    assert len(memory.load()) == 1


def test_an_empty_fact_is_refused():
    result = remember(AllowGate(), "   \n\t  ")
    assert memory.load() == []
    assert "nothing" in result.lower()


def test_a_fact_over_the_character_cap_is_refused():
    result = remember(AllowGate(), "x" * (memory.MAX_CHARS + 1))
    assert memory.load() == []
    assert str(memory.MAX_CHARS) in result


def test_an_over_long_fact_is_asked_about_before_it_is_refused():
    # The length check used to run before gate.decide, so a call rejected for
    # length consumed no verdict at all. gate.prepare has already shown the row
    # by then, so the user may have denied it -- and _run, seeing neither the
    # denial message nor a refusal, logged verdict "executed" for a confirm-tier
    # call the user said no to. Deciding first is what makes that verdict true.
    result = remember(DenyGate(), "x" * (memory.MAX_CHARS + 1))
    assert result == "You said no."
    assert memory.load() == []


def test_an_empty_fact_is_asked_about_before_it_is_refused():
    # Same seam as the length check above.
    assert remember(DenyGate(), "   \n\t  ") == "You said no."
    assert memory.load() == []


def test_a_fact_exactly_at_the_cap_is_stored():
    remember(AllowGate(), "x" * memory.MAX_CHARS)
    assert len(memory.load()) == 1


def test_storage_has_no_count_limit():
    # The old cap existed because everything stored was injected. Retrieval
    # bounds injection instead (memory.MAX_INJECTED), so a storage cap would
    # only refuse facts the user wanted kept.
    gate = AllowGate()
    for n in range(1000):
        remember(gate, f"Yash owns thing number {n}")
    assert len(memory.load()) == 1000
    assert not hasattr(memory, "MAX_FACTS")


def test_forget_removes_the_fact():
    fact_id = memory.add("goodbye")
    forget(AllowGate(), fact_id)
    assert memory.load() == []


def test_forget_an_unknown_id_says_so_without_raising():
    result = forget(AllowGate(), "deadbeef")
    assert "nothing" in result.lower()


def test_remember_does_not_report_success_when_the_store_write_fails(monkeypatch):
    # Amendment 1: store.add returns "" on a failed write; remember must not
    # tell the user the fact was remembered.
    monkeypatch.setattr(memory, "add", lambda text: "")
    result = remember(AllowGate(), "a fact")
    assert not result.lower().startswith("remembered")
    assert memory.load() == []


def test_forget_does_not_claim_success_when_the_write_fails(monkeypatch):
    # Amendment 1: store.remove returns False both for an unknown id and for
    # a failed write. Here the id exists, so the message must not be the
    # "no such thing remembered" wording — that would misreport what happened.
    fact_id = memory.add("keep me")
    monkeypatch.setattr(memory, "remove", lambda fid: False)
    result = forget(AllowGate(), fact_id)
    assert result != "Forgotten."
    assert "nothing" not in result.lower()
    assert len(memory.load()) == 1


def test_a_prepared_denial_is_not_re_asked_via_a_mismatched_ledger_key():
    # gate.decide's ledger is keyed on the *raw* arguments prepare() saw. If
    # remember() keyed on the normalised text instead, a call whose text
    # needs normalising (like this one, with a blank line) would miss the
    # ledger, fall into decide()'s unprepared-call branch, and get asked a
    # second time — a second chance to approve something already declined.
    asked = []

    def ask(rows):
        asked.append(list(rows))
        return [False]

    gate = gate_module.Gate(ask=ask)
    gate.prepare([("remember", {"text": "a\n\nb"})])
    result = remember(gate, "a\n\nb")

    assert result == gate_module.DENIED_MESSAGE
    assert len(asked) == 1, "the ledger entry from prepare() must be consumed, not missed"
    assert memory.load() == []


def test_neither_tool_raises_on_hostile_arguments():
    hostile = ["", "\x00", "../" * 500, "x" * 1_000_000, "🙂", "{}"]
    gate = AllowGate()
    for value in hostile:
        assert isinstance(remember(gate, value), str)
        assert isinstance(forget(gate, value), str)


