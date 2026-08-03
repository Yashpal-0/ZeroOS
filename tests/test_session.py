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
        return FakeResponse(self._responses.pop(0))


def tool_call(id_, name, **arguments):
    return FakeCall(id_, name, json.dumps(arguments))


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    (tmp_path / "Downloads").mkdir()
    (tmp_path / "Documents").mkdir()
    (tmp_path / "Downloads" / "a.pdf").write_text("x")
    (tmp_path / "Downloads" / "b.pdf").write_text("y")
    return tmp_path


def build_session(responses, answers):
    asked = []

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
    assert len(client.requests) == 1


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
    assert len(tools) == 16
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
    assert len(client.requests) == 3
    assert reply == session_module.STALLED, "a blank window reads as a crash"
