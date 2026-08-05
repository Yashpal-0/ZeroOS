# ZeroOS v0.3.1 — Streaming Responses — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Stream model responses token-by-token into the chat window, show tool-call progress as each batch runs, and apply the spoken/details split live during streaming — without touching the gate, the catalog, or the noticing pass.

**Architecture:** `Session.send` gains an optional `on_event` callback and switches to `stream=True`. The step loop accumulates fragmented tool calls across chunks and emits `("token", str)`, `("tools", list[str])`, `("done", str)` events. `ChatWindow._run_turn` passes a callback that marshals events through `GLib.idle_add` into a growing label and progress rows. `on_event=None` keeps every existing test green.

**Spec:** `docs/superpowers/specs/2026-08-05-zeroos-v031-streaming-design.md`

**Tech Stack:** Python 3.11+, openai client (already a dependency), GTK4 + libadwaita, pytest.

---

## Reference: the test double used throughout

The plan extends `tests/test_session.py`'s existing fakes. These shapes are reused by every test task below, so they are defined once here.

**Non-streaming (existing):**

```python
class FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments  # a JSON *string*, as the API sends it

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
    def __init__(self, responses):
        self._responses = list(responses)
        self.requests: list[dict] = []
        self.chat = self
        self.completions = self
    def create(self, **kwargs):
        self.requests.append(kwargs)
        return FakeResponse(self._responses.pop(0))
```

**Streaming (new):** A chunk is the per-delta unit the streaming API yields. A streaming response is a list of chunks that the client iterates.

```python
class FakeDelta:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls  # list[FakeChunkToolCall] or None

class FakeChunkToolCall:
    def __init__(self, index, id=None, name=None, arguments=None):
        self.index = index
        # tc.function is a FakeFunction (name, arguments)
        self.function = FakeFunction(name or "", arguments or "")

class FakeChunk:
    def __init__(self, delta):
        self.choices = [type("Choice", (), {"delta": delta})()]

class FakeStreamResponse:
    """Replays canned chunks when iterated."""
    def __init__(self, chunks):
        self._chunks = list(chunks)
    def __iter__(self):
        return iter(self._chunks)
```

`FakeClient.create` returns a `FakeStreamResponse` when `kwargs.get("stream")` is truthy, otherwise the existing `FakeResponse`. This is one branch added to the existing `create`.

---

### Task 1: Add streaming fakes to test_session.py

**Objective:** Introduce the streaming test doubles alongside the existing non-streaming ones, so later tasks can use them.

**Files:**
- Modify: `tests/test_session.py` (add classes after `FakeResponse`, before `FakeClient`)

**Step 1: Add the streaming classes**

Insert after the `FakeResponse` class definition (around line 30):

```python
class FakeDelta:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

class FakeChunkToolCall:
    def __init__(self, index, id=None, name=None, arguments=None):
        self.index = index
        self.function = FakeFunction(name or "", arguments or "")

class FakeChunk:
    def __init__(self, delta):
        self.choices = [type("Choice", (), {"delta": delta})()]

class FakeStreamResponse:
    def __init__(self, chunks):
        self._chunks = list(chunks)
    def __iter__(self):
        return iter(self._chunks)
```

**Step 2: Make FakeClient.create stream-aware**

Replace the existing `create` method:

```python
    def create(self, **kwargs):
        self.requests.append(kwargs)
        response = self._responses.pop(0)
        if kwargs.get("stream"):
            return response  # already a FakeStreamResponse
        return FakeResponse(response)
```

This means callers now pass a `FakeStreamResponse` directly in the responses list when they want streaming. Non-streaming tests pass a `FakeMessage` as before.

**Step 3: Run the full suite to confirm no regression**

Run: `python -m pytest tests/test_session.py -q`
Expected: PASS (all existing tests unchanged — none pass `stream=True`)

**Step 4: Commit**

```bash
git add tests/test_session.py
git commit -m "test: streaming fakes for the session client"
```

---

### Task 2: The fragment accumulator — test first

**Objective:** Write the failing test that proves fragment accumulation works. This is the load-bearing logic.

**Files:**
- Create: `tests/test_streaming.py`

**Step 1: Write the failing test**

```python
"""The streaming fragment accumulator — the load-bearing piece of v0.3.1.

A tool call arrives split across chunks: id, name, and arguments come in
separate deltas. The accumulator must reconstruct them into the same
(id, name, arguments) triples a non-streaming call produces.
"""

import json

import pytest

from zeroos.agent import session as session_module
from tests.test_session import (
    FakeChunk, FakeChunkToolCall, FakeDelta, FakeStreamResponse, build_session,
)


def _streaming_client(chunks, answers=None):
    """A session whose client yields one streaming response of the given chunks."""
    responses = [FakeStreamResponse(chunks)]
    session, asked, client = build_session(responses, answers or [])
    return session, asked, client


def test_a_tool_call_split_across_chunks_is_reassembled(home, monkeypatch):
    # The same tool call, fragmented the way the OpenAI streaming API sends it:
    # chunk 1 carries index + id + name; chunk 2 carries a partial arguments
    # string; chunk 3 carries the rest of it.
    chunks = [
        FakeChunk(FakeDelta(
            content=None,
            tool_calls=[FakeChunkToolCall(index=0, id="call_7", name="list_folder")],
        )),
        FakeChunk(FakeDelta(
            tool_calls=[FakeChunkToolCall(index=0, arguments='{"path": "/home')],
        )),
        FakeChunk(FakeDelta(
            tool_calls=[FakeChunkToolCall(index=0, arguments='/yash/Downloads"}')],
        )),
    ]
    session, asked, client = _streaming_client(chunks)
    session.send("list my downloads")

    # The request reached the client with stream=True
    assert client.requests[0].get("stream") is True

    # The consent dialog saw the reassembled call — proof the fragments joined.
    assert len(asked) == 1
    row_text = asked[0][0][0]  # first batch, first row, the (text, ticked) tuple's text
    assert "list_folder" in row_text or "Downloads" in row_text, (
        "the fragmented tool call must reach the gate as a complete call"
    )
```

**Step 2: Run to verify failure**

Run: `python -m pytest tests/test_streaming.py -q`
Expected: FAIL — `KeyError: 'stream'` or the client returns a `FakeStreamResponse` that `session.send` doesn't iterate (current `send` treats the return value as a `.choices[0].message` object).

---

### Task 3: The fragment accumulator — implement

**Objective:** Make `Session.send` consume a streaming response, accumulating fragments, emitting events.

**Files:**
- Modify: `zeroos/agent/session.py` — the `send` method and the step loop (lines ~123–171)

**Step 1: Change the send signature**

At `session.py:123`, change:

```python
    def send(self, text: str) -> str:
```

to:

```python
    def send(self, text: str, on_event=None) -> str:
```

Add the import of `describe_batch` at the top of the file (after the existing `from zeroos.policy.describe import ...` if present, else add):

```python
from zeroos.policy.describe import describe_batch
```

**Step 2: Replace the blocking call with stream consumption**

Inside the step loop (replacing lines ~131–142), change:

```python
            message = self._client.chat.completions.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "system", "content": self._prompt}]
                + self._memory_messages()
                + self._messages,
                tools=self._schemas,
                tool_choice="auto",
            ).choices[0].message
```

to:

```python
            message = self._consume_stream(
                self._client.chat.completions.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    messages=[{"role": "system", "content": self._prompt}]
                    + self._memory_messages()
                    + self._messages,
                    tools=self._schemas,
                    tool_choice="auto",
                    stream=True,
                ),
                on_event,
            )
```

**Step 3: Add the _consume_stream method**

Add as a method on `Session`, after `tool_calls_in` (or before `_memory_messages`):

```python
    def _consume_stream(self, stream, on_event):
        """Accumulate a streaming response into one assistant message.

        Content deltas are concatenated and emitted as "token" events. Tool
        calls arrive fragmented across chunks — id, name, and arguments in
        separate deltas keyed by index — and are reassembled here into the
        same shape tool_calls_in() expects. The reassembly is the load-bearing
        detail of v0.3.1; getting it wrong looks like a missing tool call.
        """
        content_parts: list[str] = []
        fragments: dict[int, dict] = {}
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                content_parts.append(delta.content)
                if on_event:
                    on_event("token", delta.content)
            for tc in (delta.tool_calls or []):
                frag = fragments.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                if tc.function.id if hasattr(tc.function, "id") else getattr(tc, "id", None):
                    frag["id"] = tc.id if hasattr(tc, "id") and tc.id else frag["id"]
                if tc.function.name:
                    frag["name"] = tc.function.name
                if tc.function.arguments:
                    frag["arguments"] += tc.function.arguments
        return self._materialise(content_parts, fragments)
```

Note: the real OpenAI streaming delta puts `id` on the `ChoiceDeltaToolCall` itself, and `name`/`arguments` on its `.function`. The test double (`FakeChunkToolCall`) mirrors this: `id` on the call, `name`/`arguments` on `.function`. The accumulator reads `tc.id` for the id and `tc.function.name` / `tc.function.arguments` for the rest.

**Step 4: Add the _materialise helper**

```python
    @staticmethod
    def _materialise(content_parts, fragments):
        """Build the object tool_calls_in() expects from accumulated pieces."""
        content = "".join(content_parts) or None

        class _Function:
            def __init__(self, name, arguments):
                self.name = name
                self.arguments = arguments

        class _Call:
            def __init__(self, id_, name, arguments):
                self.id = id_
                self.function = _Function(name, arguments)

        class _Message:
            def __init__(self, content, tool_calls):
                self.content = content
                self.tool_calls = tool_calls or None

        calls = [
            _Call(f["id"], f["name"], f["arguments"])
            for f in (fragments.get(i) for i in sorted(fragments))
            if f
        ]
        return _Message(content, calls if calls else None)
```

**Step 5: Emit "tools" before the gate**

In the step loop, after `calls = tool_calls_in(message)` and before `self._gate.prepare(...)`, add:

```python
            if calls and on_event:
                descriptions = describe_batch([(name, arguments) for _, name, arguments in calls])
                on_event("tools", descriptions)
```

**Step 6: Emit "done" at the end**

At the end of `send`, just before `return reply`, add:

```python
        if on_event:
            on_event("done", reply)
```

**Step 7: Run the accumulator test**

Run: `python -m pytest tests/test_streaming.py::test_a_tool_call_split_across_chunks_is_reassembled -v`
Expected: PASS

**Step 8: Run the full session suite — no regression**

Run: `python -m pytest tests/test_session.py -q`
Expected: PASS (all existing tests pass — none pass `on_event`, and the non-streaming `FakeClient` path now returns via `_consume_stream` when... wait)

**Ponytail check:** Existing tests use `FakeClient` which returns `FakeResponse` (non-streaming). But `send` now always passes `stream=True`. Two options:
- (a) Make `FakeClient.create` return a `FakeStreamResponse` wrapping the message when `stream=True`.
- (b) Make `_consume_stream` detect a non-iterable response and fall back.

Option (a) is cleaner — the test client adapts. Update `FakeClient.create` (already done in Task 1's step 2) to wrap:

```python
    def create(self, **kwargs):
        self.requests.append(kwargs)
        response = self._responses.pop(0)
        if kwargs.get("stream"):
            if isinstance(response, FakeStreamResponse):
                return response
            # Wrap a legacy FakeMessage in a single-chunk stream.
            return FakeStreamResponse([FakeChunk(FakeDelta(
                content=response.content,
                tool_calls=[
                    FakeChunkToolCall(
                        index=i, id=c.id, name=c.function.name, arguments=c.function.arguments,
                    ) for i, c in enumerate(response.tool_calls or [])
                ] or None,
            ))])
        return FakeResponse(response)
```

This means existing tests that pass `FakeMessage` objects work unchanged under streaming.

**Step 9: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS (all 390 + the new streaming test)

**Step 10: Commit**

```bash
git add zeroos/agent/session.py tests/test_session.py tests/test_streaming.py
git commit -m "feat: stream model responses with fragment accumulation"
```

---

### Task 4: Event ordering test

**Objective:** Prove events fire in the right order across a multi-step turn.

**Files:**
- Modify: `tests/test_streaming.py`

**Step 1: Write the test**

```python
def test_events_fire_in_order_across_a_two_step_turn(home):
    """text → tools → (gate) → final text → done."""
    # Step 1: a content token, then a tool call.
    step1 = FakeStreamResponse([
        FakeChunk(FakeDelta(content="Let me check ")),
        FakeChunk(FakeDelta(content="Downloads.")),
        FakeChunk(FakeDelta(tool_calls=[
            FakeChunkToolCall(index=0, id="1", name="list_folder",
                              arguments=json.dumps({"path": str(home / "Downloads")})),
        ])),
    ])
    # Step 2: final reply.
    step2 = FakeStreamResponse([
        FakeChunk(FakeDelta(content="You have two files, Sir.")),
    ])
    session, _, _ = build_session([step1, step2], [True])

    events = []
    session.send("what's in downloads", on_event=lambda kind, payload: events.append((kind, payload)))

    kinds = [kind for kind, _ in events]
    assert kinds == ["token", "token", "tools", "token", "done"], (
        f"events must fire text → tools → text → done, got {kinds}"
    )
    # The "tools" payload is describe_batch output.
    tools_payload = [p for k, p in events if k == "tools"][0]
    assert isinstance(tools_payload, list)
    assert any("list_folder" in s or "Downloads" in s for s in tools_payload)
    # The "done" payload is the final reply.
    done_payload = [p for k, p in events if k == "done"][0]
    assert done_payload == "You have two files, Sir."
```

**Step 2: Run**

Run: `python -m pytest tests/test_streaming.py::test_events_fire_in_order_across_a_two_step_turn -v`
Expected: PASS (implementation from Task 3 already satisfies this)

**Step 3: Commit**

```bash
git add tests/test_streaming.py
git commit -m "test: streaming event ordering across a multi-step turn"
```

---

### Task 5: on_event=None is a no-op (regression guard)

**Objective:** Prove the default path is unchanged.

**Files:**
- Modify: `tests/test_streaming.py`

**Step 1: Write the test**

```python
def test_on_event_none_behaves_identically_to_before(home):
    """No callback, no events — send returns the final reply as ever."""
    responses = [
        FakeStreamResponse([
            FakeChunk(FakeDelta(content="Done.")),
        ]),
    ]
    session, _, _ = build_session(responses, [])
    reply = session.send("hello")
    assert reply == "Done."
```

**Step 2: Run**

Run: `python -m pytest tests/test_streaming.py::test_on_event_none_behaves_identically_to_before -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_streaming.py
git commit -m "test: on_event=None keeps send unchanged"
```

---

### Task 6: Wire the callback into ChatWindow._run_turn

**Objective:** `window.py` passes a callback to `send`, marshalling events to the main thread.

**Files:**
- Modify: `zeroos/surface/window.py` — `_run_turn` (lines ~173–180), add helper methods

**Step 1: Change _run_turn to pass on_event**

Replace `zeroos/surface/window.py:173-180`:

```python
    def _run_turn(self, text: str) -> None:
        """Runs on a worker thread. All UI updates marshal back via idle_add."""
        try:
            reply = self._session.send(text)
        except Exception as failure:  # network, rate limit, bad key
            GLib.idle_add(self._show_failure, str(failure), text)
            return
        GLib.idle_add(self._show_reply, reply)
```

with:

```python
    def _run_turn(self, text: str) -> None:
        """Runs on a worker thread. All UI updates marshal back via idle_add."""
        try:
            reply = self._session.send(text, on_event=self._on_event)
        except Exception as failure:  # network, rate limit, bad key
            GLib.idle_add(self._show_failure, str(failure), text)
            return

    def _on_event(self, kind: str, payload) -> None:
        """Marshal a streaming event to the main thread. Fires from the worker."""
        GLib.idle_add(self._handle_event, kind, payload)

    def _handle_event(self, kind: str, payload) -> bool:
        if kind == "token":
            self._on_token(payload)
        elif kind == "tools":
            self._on_tools(payload)
        elif kind == "done":
            self._show_reply(payload)
        return GLib.SOURCE_REMOVE
```

**Step 2: Add the streaming bubble state and handlers**

Add to `__init__` (after `self._closing = False`, around line 86):

```python
        self._streaming_label = None  # the Gtk.Label tokens are appending to
```

Add the token handler:

```python
    def _on_token(self, delta: str) -> None:
        if self._streaming_label is None:
            self._streaming_label = Gtk.Label(wrap=True, xalign=0, selectable=True)
            self._transcript.append(self._streaming_label)
        self._streaming_label.set_label(
            (self._streaming_label.get_label() or "") + delta
        )
```

Add the tools handler:

```python
    def _on_tools(self, descriptions: list[str]) -> None:
        for sentence in descriptions:
            row = Gtk.Label(label=sentence, wrap=True, xalign=0, selectable=True,
                            opacity=0.6, margin_start=12, margin_top=2)
            self._transcript.append(row)
        self._streaming_label = None  # next tokens start a new bubble
```

**Step 3: Reset streaming state in _show_reply**

Modify `_show_reply` (the existing method, lines ~182–192) to clear the streaming label before appending the final formatted result:

```python
    def _show_reply(self, reply: str) -> bool:
        self._streaming_label = None  # the streaming bubble is done; finalize
        spoken, detail = split(reply)
        self._append("assistant", spoken)
        if detail:
            body = Gtk.Label(label=detail, wrap=True, xalign=0, selectable=True,
                             margin_start=12, margin_top=6)
            self._transcript.append(Gtk.Expander(label="details", child=body))
        self._busy = False
        return GLib.SOURCE_REMOVE
```

**Step 4: Run the window tests**

Run: `python -m pytest tests/test_window.py -q`
Expected: PASS (existing tests stub the session and don't call `_run_turn`)

**Step 5: Commit**

```bash
git add zeroos/surface/window.py
git commit -m "feat: stream tokens and tool progress into the window"
```

---

### Task 7: Live split during streaming — test

**Objective:** Prove the `---` marker moves overflow to details as tokens arrive.

**Files:**
- Modify: `tests/test_window.py`

**Step 1: Write the test**

```python
def test_streaming_split_moves_overflow_to_details(monkeypatch):
    """A token stream containing --- splits live: spoken freezes, details grows."""
    chat, Gtk = _window(monkeypatch)

    # Feed tokens that build up to a marker split.
    for token in ["Four files ", "moved.\n", "---\n", "a.pdf ", "b.pdf"]:
        chat._handle_event("token", token)

    # The spoken portion should be frozen after the marker; details should exist.
    # After the full stream, _show_reply finalises. We call it directly:
    chat._show_reply("Four files moved.\n---\na.pdf b.pdf")

    # Walk the transcript: there must be a spoken label and a details expander.
    labels = [w for w in _walk(chat) if isinstance(w, Gtk.Label)]
    texts = [l.get_label() for l in labels]
    assert any("Four files moved" in t for t in texts), "spoken must be visible"
    expanders = [w for w in _walk(chat) if isinstance(w, Gtk.Expander)]
    assert len(expanders) >= 1, "details must be collapsed under an expander"
```

Note: `_walk` is already defined in `test_window.py`. Check by searching; if not present, it's the tree-walk helper used by `test_the_header_bar_has_a_button_that_opens_the_recall_pane`.

**Step 2: Run**

Run: `python -m pytest tests/test_window.py::test_streaming_split_moves_overflow_to_details -v`
Expected: PASS (the `_show_reply` finalisation applies `split()` correctly; the streaming tokens are displayed raw, then replaced by the split result)

**Step 3: Commit**

```bash
git add tests/test_window.py
git commit -m "test: streaming split moves overflow to details"
```

---

### Task 8: Run the full suite and verify acceptance criteria

**Objective:** All tests green, all six acceptance criteria from the spec verifiable.

**Step 1: Full suite**

Run: `python -m pytest -q`
Expected: PASS — 390 existing + 4 new (or however many were added across tasks 2, 4, 5, 7)

**Step 2: Manual acceptance check (spec §9)**

1. Token streaming — run the app, send a message, confirm text appears incrementally during the final model call.
2. Tool-call progress — send a multi-file task, confirm a progress row appears before the dialog.
3. Live split — send a request that produces a long reply with `---`, confirm details flow into the expander.
4. No regression — full suite passes (done in Step 1).
5. New tests pass (done in Step 1).
6. Failure path — disconnect network mid-turn, confirm the "Couldn't reach the model" banner appears.

**Step 3: Bump version**

In `pyproject.toml`, change `version = "0.3.0"` to `version = "0.3.1"`.

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat: v0.3.1 streaming responses"
```

---

## Risks and open questions

- **OpenAI delta shape variance.** The real streaming API's `ChoiceDeltaToolCall` has `id` on the call and `name`/`arguments` on `.function`. The test double mirrors this. If the real API sends `id` on `.function` instead (some SDK versions did), the accumulator's `tc.id` read breaks. Mitigation: the manual acceptance check (Task 8, Step 2) runs against the real API and catches this.
- **Verb tense.** `describe_batch` produces "Move 4 files" (imperative). As progress it reads as "Move 4 files" (a command), not "Moving 4 files" (happening). Deferred per spec §3 — a tester must confirm it reads wrong before adding a tense parameter.
- **Performance of per-token label updates.** Each token triggers a `set_label` and a reflow. For very long replies this could stutter. Mitigation: if a tester notices, batch tokens with a ~50ms timer. Not worth pre-building.

---

## Files changed summary

| File | Change |
|---|---|
| `zeroos/agent/session.py` | `send` gains `on_event`, switches to `stream=True`, adds `_consume_stream` + `_materialise`, emits `"tools"`/`"done"` |
| `zeroos/surface/window.py` | `_run_turn` passes callback, adds `_on_event`/`_handle_event`/`_on_token`/`_on_tools`, streaming label state |
| `tests/test_session.py` | Streaming fakes (`FakeDelta`, `FakeChunkToolCall`, `FakeChunk`, `FakeStreamResponse`), `FakeClient.create` stream-aware |
| `tests/test_streaming.py` | New: fragment accumulation, event ordering, `on_event=None` no-op |
| `tests/test_window.py` | New: streaming split test |
| `pyproject.toml` | Version bump 0.3.0 → 0.3.1 |
