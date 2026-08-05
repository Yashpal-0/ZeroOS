"""End-to-end with a stubbed client. No network, no display."""

import json

import pytest

from zeroos.agent import session as session_module


class FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments  # a JSON *string*, exactly as the API sends it


class FakeCall:
    def __init__(self, id_, name, arguments):
        self.id = id_
        self.function = FakeFunction(name, arguments)


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class FakeResponse:
    def __init__(self, message):
        self.choices = [type("Choice", (), {"message": message})()]


# --- Streaming fakes (v0.3.1) ---
# A chunk is the per-delta unit the streaming API yields. A tool call arrives
# fragmented across chunks: id, name, and arguments in separate deltas keyed
# by index. FakeStreamResponse replays a list of chunks when iterated.

class FakeDelta:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class FakeChunkToolCall:
    def __init__(self, index, id=None, name=None, arguments=None):
        self.index = index
        self.id = id
        # tc.function is a FakeFunction (name, arguments) — same shape as the
        # real ChoiceDeltaToolCall, which puts name/arguments on .function.
        self.function = FakeFunction(name or "", arguments or "")


class FakeChunk:
    def __init__(self, delta):
        self.choices = [type("Choice", (), {"delta": delta})()]


class FakeStreamResponse:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def __iter__(self):
        return iter(self._chunks)


class FakeClient:
    """Replays canned responses and records every request it was sent."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests: list[dict] = []
        # The real client is client.chat.completions.create; this is the
        # smallest thing with that shape.
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        response = self._responses.pop(0)
        if kwargs.get("stream"):
            # Callers pass a FakeStreamResponse for streaming, or a legacy
            # FakeMessage which we wrap in a single-chunk stream so the
            # existing non-streaming tests work unchanged under stream=True.
            if isinstance(response, FakeStreamResponse):
                return response
            tool_calls = [
                FakeChunkToolCall(
                    index=i, id=c.id, name=c.function.name, arguments=c.function.arguments,
                )
                for i, c in enumerate(response.tool_calls or [])
            ]
            return FakeStreamResponse([FakeChunk(FakeDelta(
                content=response.content, tool_calls=tool_calls or None,
            ))])
        return FakeResponse(response)


def tool_call(id_, name, **arguments):
    return FakeCall(id_, name, json.dumps(arguments))


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    # v0.2 stores resolve through paths.config_dir() too, and an inherited
    # XDG_CONFIG_HOME would point the settings file at the real config.
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    (tmp_path / "Downloads").mkdir()
    (tmp_path / "Documents").mkdir()
    (tmp_path / "Downloads" / "a.pdf").write_text("x")
    (tmp_path / "Downloads" / "b.pdf").write_text("y")
    return tmp_path


def build_session(responses, answers, ask=None):
    asked = []

    if ask is None:
        def ask(rows):
            asked.append(list(rows))
            return answers[: len(rows)]

    client = FakeClient(responses)
    session = session_module.Session(api_key="test", ask=ask, client=client)
    return session, asked, client


def test_mixed_tier_turn_asks_once_and_runs_auto_tools(home):
    responses = [
        FakeMessage(tool_calls=[
            tool_call("1", "list_folder", path=str(home / "Downloads")),
            tool_call("2", "trash_file", path=str(home / "Downloads" / "a.pdf")),
            tool_call("3", "trash_file", path=str(home / "Downloads" / "b.pdf")),
        ]),
        FakeMessage(content="Done — I removed two files, Sir."),
    ]
    session, asked, _ = build_session(responses, [True, True])
    reply = session.send("clean up downloads")

    assert len(asked) == 1, "the confirm-tier calls must produce exactly one dialog"
    assert len(asked[0]) == 2, "only the two trash calls need approval"
    assert reply == "Done — I removed two files, Sir."
    assert not (home / "Downloads" / "a.pdf").exists()


def test_partial_approval_runs_only_the_ticked_action(home):
    responses = [
        FakeMessage(tool_calls=[
            tool_call("1", "trash_file", path=str(home / "Downloads" / "a.pdf")),
            tool_call("2", "trash_file", path=str(home / "Downloads" / "b.pdf")),
        ]),
        FakeMessage(content="Removed one."),
    ]
    session, _, _ = build_session(responses, [True, False])
    session.send("tidy up")

    assert not (home / "Downloads" / "a.pdf").exists()
    assert (home / "Downloads" / "b.pdf").exists(), "the unticked action must not run"


def test_declined_action_is_not_logged_as_executed(home, monkeypatch):
    written = []
    monkeypatch.setattr(
        session_module.log, "record",
        lambda name, arguments, tier, verdict, result: written.append((name, verdict)),
    )
    responses = [
        FakeMessage(tool_calls=[
            tool_call("1", "trash_file", path=str(home / "Downloads" / "a.pdf")),
        ]),
        FakeMessage(content="Left it alone."),
    ]
    session, _, _ = build_session(responses, [False])
    session.send("bin that file")

    assert written == [("trash_file", "declined")], (
        "a log that reports declined actions as executed cannot answer "
        "'what did it actually do' — the one question §6 says it exists for"
    )


def test_a_root_refusal_is_not_logged_as_executed(home, monkeypatch):
    """sandbox raises two different refusal messages; the log must know both.

    refuse_root() carries ROOT_REFUSAL_MESSAGE, not the default REFUSAL_MESSAGE,
    so a decision that only compares the latter records the blocked action as
    "executed" — the log claiming ZeroOS trashed the home folder it refused to
    touch.
    """
    written = []
    monkeypatch.setattr(
        session_module.log, "record",
        lambda name, arguments, tier, verdict, result: written.append((name, verdict)),
    )
    responses = [
        FakeMessage(tool_calls=[tool_call("1", "trash_file", path="~")]),
        FakeMessage(content="I can't do that."),
    ]
    session, _, _ = build_session(responses, [True])
    session.send("bin my home folder")

    assert written == [("trash_file", "refused")], (
        "refuse_root blocked the action, so the log must not claim it executed"
    )


def test_every_tool_call_is_answered_with_its_own_id(home):
    responses = [
        FakeMessage(tool_calls=[
            tool_call("call_a", "trash_file", path=str(home / "Downloads" / "a.pdf")),
            tool_call("call_b", "trash_file", path=str(home / "Downloads" / "b.pdf")),
        ]),
        FakeMessage(content="Both gone."),
    ]
    session, _, client = build_session(responses, [True, False])
    session.send("tidy up")

    sent = client.requests[1]["messages"]
    answered = {m["tool_call_id"] for m in sent if m.get("role") == "tool"}
    assert answered == {"call_a", "call_b"}, "an unanswered tool_call is a 400 from the API"


def test_a_denied_action_is_still_answered_with_the_denial_text(home):
    responses = [
        FakeMessage(tool_calls=[tool_call("1", "trash_file", path=str(home / "Downloads" / "a.pdf"))]),
        FakeMessage(content="I left it alone."),
    ]
    session, _, client = build_session(responses, [False])
    session.send("delete it")

    results = [m for m in client.requests[1]["messages"] if m.get("role") == "tool"]
    assert len(results) == 1
    assert "declined" in results[0]["content"]
    assert (home / "Downloads" / "a.pdf").exists()


def test_the_assistant_tool_call_message_is_replayed_before_its_results(home):
    responses = [
        FakeMessage(tool_calls=[tool_call("1", "list_folder", path=str(home / "Downloads"))]),
        FakeMessage(content="Two files."),
    ]
    session, _, client = build_session(responses, [])
    session.send("what's in downloads")

    roles = [m["role"] for m in client.requests[1]["messages"]]
    assert roles.index("assistant") < roles.index("tool")


def test_a_turn_with_no_tools_makes_one_request(home):
    session, asked, client = build_session([FakeMessage(content="Hello.")], [])
    assert session.send("hi") == "Hello."
    assert asked == []
    # Two requests: the reply, plus the noticing pass send() fires at the end
    # of the turn.
    assert len(client.requests) == 2


def test_the_system_prompt_leads_every_request(home):
    from zeroos.agent.prompt import SYSTEM_PROMPT

    session, _, client = build_session([FakeMessage(content="Hi.")], [])
    session.send("hi")
    first = client.requests[0]["messages"][0]
    assert first == {"role": "system", "content": SYSTEM_PROMPT}


def test_tools_are_sent_in_openai_wire_shape(home):
    session, _, client = build_session([FakeMessage(content="Hi.")], [])
    session.send("hi")
    tools = client.requests[0]["tools"]
    assert len(tools) == 19
    assert tools[0]["type"] == "function"
    assert set(tools[0]["function"]) == {"name", "description", "parameters"}
    assert tools[0]["function"]["parameters"]["type"] == "object"


def test_the_turn_is_written_to_the_action_log(home):
    from zeroos.agent import log

    responses = [
        FakeMessage(tool_calls=[tool_call("1", "list_folder", path=str(home / "Downloads"))]),
        FakeMessage(content="Two files."),
    ]
    session, _, _ = build_session(responses, [])
    session.send("what's in downloads")
    assert "list_folder" in log.path().read_text()


def test_tool_calls_in_parses_the_json_argument_string():
    message = FakeMessage(tool_calls=[tool_call("1", "notify", title="a", body="b")])
    assert session_module.tool_calls_in(message) == [("1", "notify", {"title": "a", "body": "b"})]


def test_tool_calls_in_survives_malformed_json():
    message = FakeMessage(tool_calls=[FakeCall("1", "notify", "{not json")])
    assert session_module.tool_calls_in(message) == [("1", "notify", {})]


def test_a_message_with_no_tool_calls_yields_none():
    assert session_module.tool_calls_in(FakeMessage(content="hi")) == []


def test_an_unknown_tool_name_is_answered_rather_than_crashing(home):
    responses = [
        FakeMessage(tool_calls=[tool_call("1", "run_shell_command", cmd="rm -rf /")]),
        FakeMessage(content="I can't do that."),
    ]
    session, _, client = build_session(responses, [])
    reply = session.send("wipe the disk")

    results = [m for m in client.requests[1]["messages"] if m.get("role") == "tool"]
    assert len(results) == 1
    assert reply == "I can't do that."


def system_messages(request) -> list[dict]:
    return [m for m in request["messages"] if m["role"] == "system"]


def test_with_no_memories_there_is_exactly_one_system_message(home):
    """Spec §13.4. A fresh install sends the prompt and nothing appended.

    Not a byte-identity test, despite what §13.4 originally said: it compares
    against the current SYSTEM_PROMPT, so it cannot see that value change.
    The bytes are pinned in test_prompt.py. What this catches is section 3
    leaking into the first request of an empty store.
    """
    from zeroos.agent.prompt import SYSTEM_PROMPT

    session, _, client = build_session([FakeMessage(content="hello")], [])
    session.send("hi")
    system = system_messages(client.requests[0])
    assert len(system) == 1
    assert system[0]["content"] == SYSTEM_PROMPT


def test_a_stored_memory_becomes_a_second_system_message(home):
    from zeroos.agent.prompt import SYSTEM_PROMPT
    from zeroos.platform import memory

    memory.add("My documents live in the Work folder")
    session, _, client = build_session([FakeMessage(content="hello")], [])
    session.send("hi")
    system = system_messages(client.requests[0])
    assert len(system) == 2
    assert system[0]["content"] == SYSTEM_PROMPT
    assert "My documents live in the Work folder" in system[1]["content"]


def test_the_second_system_message_lists_facts_with_their_ids_under_the_preface(home):
    from zeroos.agent.prompt import MEMORY_PREFACE
    from zeroos.platform import memory

    first = memory.add("alpha")
    second = memory.add("beta")
    session, _, client = build_session([FakeMessage(content="hello")], [])
    session.send("hi")
    block = system_messages(client.requests[0])[1]
    assert block["content"].startswith(MEMORY_PREFACE)
    assert f"[{first}] alpha" in block["content"]
    assert f"[{second}] beta" in block["content"]


def test_the_fixed_prompt_is_never_interpolated(home):
    from zeroos.platform import memory

    memory.add("a fact")
    session, _, client = build_session([FakeMessage(content="hello")], [])
    session.send("hi")
    assert "a fact" not in system_messages(client.requests[0])[0]["content"]


def test_the_memory_block_is_rebuilt_between_steps(home):
    """A remember approved mid-turn is visible to the very next model call.

    Built once per send() instead, the fact would not appear until the user
    typed again — the assistant forgetting what it just confirmed.
    """
    responses = [
        FakeMessage(tool_calls=[tool_call("1", "remember", text="mid-turn fact")]),
        FakeMessage(content="done"),
    ]
    session, _, client = build_session(responses, [True])
    session.send("remember something")
    second = system_messages(client.requests[1])
    assert any("mid-turn fact" in m["content"] for m in second)


def test_the_form_of_address_is_resolved_once_at_construction(home):
    from zeroos.agent.prompt import PROMPTS
    from zeroos.platform import settings

    settings.set_address("maam")
    session, _, client = build_session([FakeMessage(content="hello")], [])
    settings.set_address("sir")
    session.send("hi")
    assert system_messages(client.requests[0])[0]["content"] == PROMPTS["maam"]


def test_a_completed_turn_lands_in_history(home):
    from zeroos.agent import history

    session, _, _ = build_session([FakeMessage(content="I found one file.")], [])
    session.send("find my tax pdf")
    turns = history.load()
    assert len(turns) == 1
    assert turns[0]["you"] == "find my tax pdf"
    assert turns[0]["zeroos"] == "I found one file."


def test_history_never_reaches_the_model(home):
    """Asserts on the whole request body. Spec §1: history is displayed, not sent."""
    from zeroos.agent import history

    history.append("a turn from last week", "and its reply")
    session, _, client = build_session([FakeMessage(content="hello")], [])
    session.send("hi")
    body = repr(client.requests[0])
    assert "a turn from last week" not in body
    assert "and its reply" not in body


def test_a_prior_sessions_history_does_not_grow_the_prompt(home):
    from zeroos.agent import history

    for n in range(200):
        history.append(f"q{n}", f"a{n}")
    session, _, client = build_session([FakeMessage(content="hello")], [])
    session.send("hi")
    assert len(client.requests[0]["messages"]) == 2  # system + user


def test_close_records_the_session(home):
    from zeroos.agent import usage

    session, _, _ = build_session([FakeMessage(content="hello")], [])
    session.send("hi")
    session.close()
    assert "turns=1" in usage.path().read_text(encoding="utf-8")


def test_close_counts_executed_and_declined_actions(home):
    from zeroos.agent import usage

    responses = [
        FakeMessage(tool_calls=[tool_call("1", "list_apps")]),
        FakeMessage(content="done"),
    ]
    session, _, _ = build_session(responses, [])
    session.send("what apps do I have")
    session.close()
    line = usage.path().read_text(encoding="utf-8")
    assert "actions=1" in line
    assert "declined=0" in line


def test_close_counts_a_declined_action(home):
    from zeroos.agent import usage

    responses = [
        FakeMessage(tool_calls=[tool_call("1", "trash_file", path=str(home / "Downloads" / "a.pdf"))]),
        FakeMessage(content="left it"),
    ]
    session, _, _ = build_session(responses, [False])
    session.send("bin that")
    session.close()
    line = usage.path().read_text(encoding="utf-8")
    assert "declined=1" in line
    assert "actions=0" in line


def test_close_writes_no_message_content(home):
    from zeroos.agent import usage

    session, _, _ = build_session([FakeMessage(content="a secret reply")], [])
    session.send("a secret question")
    session.close()
    assert "secret" not in usage.path().read_text(encoding="utf-8")


def test_the_closing_summary_is_counted_before_the_usage_line(home, monkeypatch):
    # A summary remember approved on the way out increments _actions via _run.
    # If usage.record ran first, the line would undercount the session it is
    # describing.
    from zeroos.platform import memory

    monkeypatch.setattr(
        "zeroos.agent.notice.candidates", lambda client, messages: ["a closing fact"]
    )
    recorded = {}
    monkeypatch.setattr(
        "zeroos.agent.usage.record",
        lambda started, turns, actions, declined: recorded.update(actions=actions),
    )
    session, _, _ = build_session(
        [FakeMessage(content="Done.")], [], ask=lambda rows: [True] * len(rows)
    )
    session.send("hi")
    session.close()
    assert recorded["actions"] >= 1
    assert [f["text"] for f in memory.load()] == ["a closing fact"]


def test_close_never_raises_when_the_summary_fails(home, monkeypatch):
    # A network failure on the way out must not take shutdown down, and there
    # is nothing a user can do about it once the window is already gone.
    # Patched in after send(): notice.candidates already ran once, clean, as
    # part of that turn. What this test pins is close()'s own guard around
    # its closing-summary call, not send()'s ordinary one.
    def explode(client, messages):
        raise RuntimeError("network")

    session, _, _ = build_session([FakeMessage(content="Done.")], [])
    session.send("hi")
    monkeypatch.setattr("zeroos.agent.notice.candidates", explode)
    session.close()  # must return normally


def test_close_with_nothing_to_summarise_opens_no_dialog(home, monkeypatch):
    monkeypatch.setattr("zeroos.agent.notice.candidates", lambda client, messages: [])

    # Recorded rather than raised, for the same reason as the turn-path test
    # above: close() and _offer_candidates both swallow exceptions, so an ask
    # that raised would be absorbed and this test would go green against the
    # regression it names.
    seen = []
    session, _, _ = build_session(
        [FakeMessage(content="Done.")], [],
        ask=lambda rows: (seen.append(list(rows)), [False] * len(rows))[1],
    )
    session.send("hi")
    session.close()
    assert seen == [], "no dialog when there is nothing to summarise"


def test_a_dialog_that_never_opened_does_not_burn_the_candidate(home):
    # The _offered filter exists to stop a declined fact being re-proposed all
    # session. If a candidate were marked offered before prepare() succeeded, a
    # GTK fault would silently spend it: the noticing pass keeps finding the
    # fact, this filter keeps dropping it, and the user is never once asked.
    session, asked, _ = build_session([FakeMessage(content="Done.")], [])

    def explode(pending):
        raise RuntimeError("the dialog layer fell over")

    session._gate.prepare = explode
    session._pending = ["a fact nobody was shown"]
    session._offer_candidates()

    assert session._offered == set(), "an unasked question is not an asked one"
    assert asked == []


def test_the_loop_is_bounded(home, monkeypatch):
    # A model that never stops calling tools must not hang the app. The real
    # ceiling is 1000; shrink it here so the test does not send 1000 requests
    # to prove a bound that is the same bound at any size.
    monkeypatch.setattr(session_module, "MAX_STEPS", 3)
    responses = [
        FakeMessage(tool_calls=[tool_call(str(n), "list_folder", path=str(home / "Downloads"))])
        for n in range(8)
    ]
    session, _, client = build_session(responses, [])
    reply = session.send("loop forever")
    # Three from the bounded loop, plus one more for the noticing pass send()
    # fires at the end of the turn.
    assert len(client.requests) == 4
    assert reply == session_module.STALLED, "a blank window reads as a crash"


def test_a_turn_that_produces_candidates_does_not_show_a_dialog(home, monkeypatch):
    # window.py renders the reply only after send() returns, and ask blocks.
    # A dialog inside this turn would ask the user to approve facts drawn from
    # a reply they have not been shown, with the window still reading busy.
    monkeypatch.setattr(
        "zeroos.agent.notice.candidates", lambda client, messages: ["a noticed fact"]
    )

    # Recorded rather than raised: _offer_candidates swallows exceptions, so
    # an ask that raised would be silently absorbed and this test would pass
    # against the very regression it exists to catch.
    seen = []
    session, _, _ = build_session(
        [FakeMessage(content="Done.")], [],
        ask=lambda rows: (seen.append(list(rows)), [False] * len(rows))[1],
    )
    assert session.send("hi") == "Done."
    assert seen == [], "no dialog may open during the turn that noticed"


def test_candidates_are_offered_at_the_start_of_the_next_turn(home, monkeypatch):
    from zeroos.platform import memory

    monkeypatch.setattr(
        "zeroos.agent.notice.candidates", lambda client, messages: ["a noticed fact"]
    )
    seen = []

    def ask(rows):
        seen.append(list(rows))
        return [True] * len(rows)

    session, _, _ = build_session(
        [FakeMessage(content="One."), FakeMessage(content="Two.")], [], ask=ask
    )
    session.send("hi")
    assert seen == []
    session.send("again")
    assert len(seen) == 1
    assert seen[0][0][1] is False, "a candidate row must arrive unticked"
    assert [f["text"] for f in memory.load()] == ["a noticed fact"]


def test_a_declined_candidate_stores_nothing(home, monkeypatch):
    from zeroos.platform import memory

    monkeypatch.setattr(
        "zeroos.agent.notice.candidates", lambda client, messages: ["a noticed fact"]
    )
    session, _, _ = build_session(
        [FakeMessage(content="One."), FakeMessage(content="Two.")],
        [],
        ask=lambda rows: [False] * len(rows),
    )
    session.send("hi")
    session.send("again")
    assert memory.load() == []


def test_an_approved_candidate_is_logged_as_an_ordinary_remember(home, monkeypatch):
    # A candidate must go through _run, not store.add directly, or the log
    # would fail to show it as one of ZeroOS's own actions.
    written = []
    monkeypatch.setattr(
        session_module.log, "record",
        lambda name, arguments, tier, verdict, result: written.append((name, verdict)),
    )
    monkeypatch.setattr(
        "zeroos.agent.notice.candidates", lambda client, messages: ["a noticed fact"]
    )
    session, _, _ = build_session(
        [FakeMessage(content="One."), FakeMessage(content="Two.")], [],
        ask=lambda rows: [True] * len(rows),
    )
    session.send("hi")
    session.send("again")
    assert written == [("remember", "executed")]


def test_a_declined_candidate_is_logged_as_declined(home, monkeypatch):
    written = []
    monkeypatch.setattr(
        session_module.log, "record",
        lambda name, arguments, tier, verdict, result: written.append((name, verdict)),
    )
    monkeypatch.setattr(
        "zeroos.agent.notice.candidates", lambda client, messages: ["a noticed fact"]
    )
    session, _, _ = build_session(
        [FakeMessage(content="One."), FakeMessage(content="Two.")], [],
        ask=lambda rows: [False] * len(rows),
    )
    session.send("hi")
    session.send("again")
    assert written == [("remember", "declined")]


def test_candidates_are_offered_once_and_not_again(home, monkeypatch):
    # _pending is drained before it is offered. Offering twice would ask the
    # user about a fact they already answered.
    replies = iter([["a noticed fact"], [], []])
    monkeypatch.setattr(
        "zeroos.agent.notice.candidates", lambda client, messages: next(replies)
    )
    seen = []
    session, _, _ = build_session(
        [FakeMessage(content="One."), FakeMessage(content="Two."), FakeMessage(content="Three.")],
        [],
        ask=lambda rows: (seen.append(list(rows)), [False] * len(rows))[1],
    )
    session.send("a")
    session.send("b")
    session.send("c")
    assert len(seen) == 1


def test_a_declined_candidate_is_not_proposed_again_this_session(home, monkeypatch):
    # The noticing pass reads the whole accumulated transcript every turn, so
    # the turn that produced a fact stays in view and the pass keeps finding
    # it. Without a record of what was already offered, the user who unticks
    # a row is asked about the same fact on every subsequent turn until they
    # give in -- a dialog that re-asks after a refusal is not consent.
    fact = "my tax stuff is in Documents"
    monkeypatch.setattr("zeroos.agent.notice.candidates", lambda client, messages: [fact])
    seen = []
    session, _, _ = build_session(
        [FakeMessage(content="One."), FakeMessage(content="Two."), FakeMessage(content="Three.")],
        [],
        ask=lambda rows: (seen.append([text for text, _ticked in rows]), [False] * len(rows))[1],
    )
    session.send("a")
    session.send("b")
    session.send("c")
    assert len(seen) == 1, "the fact must reach the dialog once, not once per turn"
    # Asserted on the text, not just the count, so the test cannot pass
    # vacuously if the noticing pass starts returning nothing at all.
    assert fact in seen[0][0]


def test_a_close_during_a_turn_skips_the_summary_but_still_records(home, monkeypatch):
    # Spec section 7. close() runs on a second thread while the turn's own
    # thread is still in the step loop; the summary's prepare() would clear
    # the consent ledger under it. The usage line is not part of the summary
    # and must still be written -- it describes the session, and it is the
    # only record that the session happened.
    recorded = []
    monkeypatch.setattr(
        session_module.usage, "record",
        lambda started, turns, actions, declined: recorded.append(turns),
    )

    session, _, client = build_session([FakeMessage(content="Done.")], [])
    session.send("hi")
    before = len(client.requests)

    session.close(summary=False)

    # The request count is what discriminates: notice.candidates swallows its
    # own failures, so a summary that did run would leave no other trace here.
    assert len(client.requests) == before, "the closing pass must not be sent"
    assert recorded == [1], "the usage line must be written even with no summary"


def test_the_memory_block_ends_with_the_format_reminder(home):
    """The fact block used to be the last thing the model read, and the format
    rule lost to it on recency: a populated store turned one-sentence replies
    into markdown dumps. The block now ends by restating the rule."""
    from zeroos.agent.prompt import MEMORY_CLOSING
    from zeroos.platform import memory

    memory.add("Yash keeps tax PDFs in Documents")
    session, _, client = build_session([FakeMessage(content="hello")], [])
    session.send("hi")
    block = system_messages(client.requests[0])[1]["content"]
    assert block.endswith(MEMORY_CLOSING)
    assert block.index("Yash keeps tax PDFs") < block.index(MEMORY_CLOSING)
