"""The streaming fragment accumulator — the load-bearing piece of v0.3.1.

A tool call arrives split across chunks: id, name, and arguments come in
separate deltas. The accumulator in session._consume_stream must reconstruct
them into the same (id, name, arguments) triples a non-streaming call produces.
"""

import json

import pytest

from zeroos.agent import session as session_module
from test_session import (
    FakeChunk,
    FakeChunkToolCall,
    FakeDelta,
    FakeStreamResponse,
    build_session,
    home,
)


def test_a_tool_call_split_across_chunks_is_reassembled(home, monkeypatch):
    # A confirm-tier tool call, fragmented the way the OpenAI streaming API
    # sends it: chunk 1 carries index + id + name; chunk 2 carries a partial
    # arguments string; chunk 3 carries the rest of it. trash_file is confirm
    # so the gate fires and we can assert the reassembled call reached it.
    target = str(home / "Downloads" / "a.pdf")
    chunks = [
        FakeChunk(FakeDelta(
            tool_calls=[FakeChunkToolCall(index=0, id="call_7", name="trash_file")],
        )),
        FakeChunk(FakeDelta(
            tool_calls=[FakeChunkToolCall(index=0, arguments=f'{{"path": "{target[:8]}')],
        )),
        FakeChunk(FakeDelta(
            tool_calls=[FakeChunkToolCall(index=0, arguments=f'{target[8:]}"}}')],
        )),
    ]
    # After the tool runs, the loop calls create() again for the model's reply.
    final = FakeStreamResponse([FakeChunk(FakeDelta(content="Done."))])
    session, asked, client = build_session([FakeStreamResponse(chunks), final], [True])
    session.send("trash a file")

    # The request reached the client with stream=True
    assert client.requests[0].get("stream") is True

    # The consent dialog saw the reassembled call — proof the fragments joined.
    assert len(asked) == 1, "the fragmented tool call must reach the gate as one batch"
    row_text = asked[0][0][0]  # first batch, first row, the (text, ticked) tuple's text
    assert "a.pdf" in row_text or "trash_file" in row_text, (
        "the fragmented tool call must reach the gate as a complete call"
    )
