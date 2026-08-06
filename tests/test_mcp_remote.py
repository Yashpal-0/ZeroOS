"""Spec section 5. RemoteTool wears Tool's four members and never raises."""

import pytest

from zeroos.catalog.tool import MAX_RESULT, _UNEXPECTED
from zeroos.mcp import remote
from zeroos.mcp.transport import TransportError
from zeroos.policy import gate as gate_module

SCHEMA = {
    "type": "object",
    "properties": {"path": {"type": "string"}},
    "required": ["path"],
    "additionalProperties": False,
}


class FakeLink:
    def __init__(self, result=None, error=None):
        self._result = result if result is not None else {"content": [{"type": "text", "text": "ok"}]}
        self._error = error
        self.sent = []

    def send(self, method, params):
        self.sent.append((method, params))
        if self._error is not None:
            raise self._error
        return self._result


def allowing():
    gate = gate_module.Gate(lambda rows: [True] * len(rows))
    return gate


def one(server="filesystem", advertised=None, link=None, gate=None):
    advertised = advertised or [
        {"name": "read_file", "description": "Read a file.", "inputSchema": SCHEMA}
    ]
    tools = remote.build(server, link or FakeLink(), advertised, gate or allowing())
    return tools[0]


def test_the_name_is_composed():
    assert one().name == "mcp__filesystem__read_file"


def test_the_input_schema_passes_through_byte_identical():
    """Verbatim, not merely equal: ZeroOS must not rewrite a schema it does
    not understand, and `is` is the only assertion that proves it did not."""
    tool = one()
    assert tool.input_schema is SCHEMA


def test_a_missing_input_schema_becomes_an_empty_object_schema():
    tool = one(advertised=[{"name": "ping", "description": "Ping."}])
    assert tool.input_schema == {"type": "object", "properties": {}}


def test_missing_input_schemas_do_not_share_mutable_properties():
    tools = remote.build(
        "s",
        FakeLink(),
        [{"name": "first"}, {"name": "second"}],
        allowing(),
    )
    tools[0].input_schema["properties"]["x"] = {"type": "string"}
    assert tools[1].input_schema == {"type": "object", "properties": {}}


def test_the_bare_name_is_what_reaches_the_server():
    link = FakeLink()
    tool = one(link=link)
    tool.call({"path": "/tmp/x"})
    method, params = link.sent[0]
    assert method == "tools/call"
    assert params["name"] == "read_file"
    assert params["arguments"] == {"path": "/tmp/x"}


def test_a_text_result_comes_back_as_text():
    assert one().call({"path": "/tmp/x"}) == "ok"


def test_several_text_blocks_are_joined():
    link = FakeLink(result={"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]})
    assert one(link=link).call({"path": "/x"}) == "a\nb"


def test_a_non_text_block_gets_an_honest_placeholder():
    link = FakeLink(result={"content": [{"type": "image", "data": "..."}]})
    assert one(link=link).call({"path": "/x"}) == "[image content, not shown]"


def test_an_is_error_result_is_still_returned_as_a_string():
    link = FakeLink(result={"content": [{"type": "text", "text": "no such file"}], "isError": True})
    result = one(link=link).call({"path": "/x"})
    assert isinstance(result, str)
    assert "no such file" in result


def test_a_transport_failure_returns_a_sentence():
    link = FakeLink(error=TransportError("The server took too long to answer."))
    result = one(link=link).call({"path": "/x"})
    assert result == "The server took too long to answer."


def test_any_other_exception_returns_the_shared_fallback():
    link = FakeLink(error=RuntimeError("something unforeseen"))
    assert one(link=link).call({"path": "/x"}) == _UNEXPECTED


def test_a_gate_failure_returns_the_shared_fallback_without_calling_the_server():
    class BrokenGate:
        def decide(self, name, arguments):
            raise RuntimeError("dialog exploded")

    link = FakeLink()
    assert one(link=link, gate=BrokenGate()).call({"path": "/x"}) == _UNEXPECTED
    assert link.sent == []


def test_a_result_shaped_wrongly_does_not_raise():
    for bad in [
        {},
        {"content": "not a list"},
        {"content": [None]},
        {"content": [{"type": "text"}]},
        None,
        [],
        "text",
        [1, 2],
    ]:
        assert isinstance(remote._text_of(bad), str)


def test_the_result_is_capped_with_an_explicit_marker():
    link = FakeLink(result={"content": [{"type": "text", "text": "x" * 200_000}]})
    result = one(link=link).call({"path": "/x"})
    assert len(result) < MAX_RESULT + 200
    assert "cut off" in result.lower()


def test_a_denied_call_never_reaches_the_server():
    link = FakeLink()
    gate = gate_module.Gate(lambda rows: [False] * len(rows))
    tool = one(link=link, gate=gate)
    gate.prepare([(tool.name, {"path": "/x"})])
    assert tool.call({"path": "/x"}) == gate_module.DENIED_MESSAGE
    assert link.sent == []


def test_control_characters_in_a_server_name_cannot_reach_a_row():
    tool = one(advertised=[
        {"name": "read\x1b[2Jfile", "description": "d" * 50, "inputSchema": SCHEMA}
    ])
    assert "\x1b" not in tool.name
    assert tool.name == "mcp__filesystem__read[2Jfile"


def test_a_newline_in_a_description_is_collapsed():
    tool = one(advertised=[{"name": "x", "description": "first\nsecond", "inputSchema": SCHEMA}])
    assert tool.description == "first second"


def test_a_tool_whose_name_does_not_survive_is_skipped():
    tools = remote.build(
        "filesystem",
        FakeLink(),
        [
            {"name": "\x00\x07", "description": "d", "inputSchema": SCHEMA},
            {"name": "good", "description": "d", "inputSchema": SCHEMA},
        ],
        allowing(),
    )
    assert [t.name for t in tools] == ["mcp__filesystem__good"]


def test_a_malformed_advertised_entry_is_skipped_rather_than_raising():
    tools = remote.build("s", FakeLink(), ["nonsense", {"no_name": True}], allowing())
    assert tools == []
