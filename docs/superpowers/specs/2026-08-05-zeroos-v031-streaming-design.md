# ZeroOS v0.3.1 — Streaming Responses — Design

**Date:** 2026-08-05
**Status:** Draft — not yet implemented
**Scope:** Stream model responses into the chat window token-by-token, show
tool-call progress as each batch runs, and apply the spoken/details split live
during streaming. One point release: no new subsystem, no new tool, no change
to the catalog, the gate, or the noticing pass.

It assumes [the v0.1 spec](2026-08-02-zeroos-v01-design.md) (the surface layer
and the permission model) and does not restate it.

---

## 1. The problem

v0.3's `Session.send` (`agent/session.py:131`) makes one blocking
`chat.completions.create` per step and returns only the final string. The window
shows nothing until the whole turn finishes. For a conversational assistant
whose persona is *calm and unhurried*, every turn feels like a 3–8 second hang,
and multi-step turns (model writes text → calls tools → writes more text) render
nothing at all while tools execute. The roadmap flags latency as a standing
constraint; nothing in the codebase addresses it.

This is the single technical change that affects how JARVIS *feels* without
adding capability. No new tools, no new permissions, no new persistence.

### Why a point release and not a phase

It adds no subsystem and no action surface. The catalog, the gate, the noticing
pass, and the memory store are untouched. What changes is the rate at which
already-computed text reaches the screen.

---

## 2. What changes, and what does not

### Changes

- **`Session.send`** gains an optional `on_event` callback and switches to
  `stream=True`. The step loop accumulates streamed content and fragmented tool
  calls, and emits progress events.
- **`ChatWindow._run_turn`** passes a callback that marshals events to the main
  thread via `GLib.idle_add` (the existing pattern), rendering tokens into a
  growing label and tool descriptions into progress rows.
- **The spoken/details split** (`surface/window.py:split`) runs live during
  streaming, not only on the final reply.

### Does not change

- **The gate.** Tool calls are still collected, batched, and confirmed through
  the same dialog. Streaming changes when the user sees text, not when actions
  run.
- **The noticing pass.** Unchanged. It still runs on the filtered transcript
  after the turn.
- **History and the log.** `history.append` and `log.record` receive the same
  final values they do today.
- **The catalog.** No new tools.
- **The model or provider.** Still `qwen/qwen3.7-flash` via OpenRouter. The
  OpenAI client already supports `stream=True`.

---

## 3. The event protocol

`send(text, on_event=None) -> str`. When `on_event is None`, no events fire and
`send` behaves identically to v0.3 — every existing caller and test is
unchanged.

The callback signature is `Callable[[str, object], None]`. Three event types:

| Event | Payload | When | Frequency |
|---|---|---|---|
| `"token"` | `str` — one content delta | The model emits text | Many times per step |
| `"tools"` | `list[str]` — sentences from `describe_batch()` | All calls in a step collected, immediately before `gate.prepare()` | Once per tool step |
| `"done"` | `str` — the final reply | Turn complete | Once, last |

Events fire from the worker thread. Callers marshal to the UI thread; `window.py`
uses `GLib.idle_add`, exactly as it does today for `_show_reply` and
`_show_failure`.

### Why `"tools"` carries `describe_batch` output rather than tool names

The user chose tool-call progress that reads as a sentence ("Moving 4 files…"),
not a raw tool name. `policy/describe.py:describe_batch` already produces exactly
these sentences for the consent dialog. Reusing it means the progress string
and the consent row show the same words — no divergence between what the user
saw happen and what they approved.

### Verb tense

`describe_batch` produces imperative sentences ("Move 4 files from Documents
into Tax 2025"). As a progress indicator, present continuous ("Moving 4
files…") reads as *happening*. This is a cosmetic follow-up, deferred: it
requires either a new `describe` variant or a tense parameter, neither of which
is worth the surface area until a tester confirms the imperative reads wrong.
The spec marks this as a known gap, not a defect.

---

## 4. Streaming accumulation (`agent/session.py`)

The step loop replaces one blocking call with stream consumption:

```
stream = client.chat.completions.create(..., stream=True)
content = ""
fragments = {}   # {call_index: {"id":..., "name":..., "arguments": str}}
for chunk in stream:
    delta = chunk.choices[0].delta
    if delta.content:
        content += delta.content
        if on_event: on_event("token", delta.content)
    if delta.tool_calls:
        for tc in delta.tool_calls:
            frag = fragments.setdefault(tc.index, {"id":"", "name":"", "arguments":""})
            if tc.id:       frag["id"] = tc.id
            if tc.function and tc.function.name:
                            frag["name"] = tc.function.name
            if tc.function and tc.function.arguments:
                            frag["arguments"] += tc.function.arguments
```

After the stream ends, the assistant message is materialised from `content` and
`fragments`. `tool_calls_in(message)` is unchanged — it receives complete
strings, whether they arrived in one non-streaming call or across many chunks.

### Fragment accumulation is the load-bearing detail

The OpenAI streaming API splits a single tool call across chunks: `id` in one
chunk, `name` in the next, `arguments` as a JSON string delivered in pieces. The
accumulator must concatenate per-`index` before the result is usable. Getting
this wrong produces empty tool names, truncated argument JSON, or calls silently
dropped — all of which would look like a model or tool failure rather than a
streaming bug.

### Intermediate text is shown, not discarded

v0.3's `reply = message.content or reply` silently drops step 1's text when
step 2 writes new text. With streaming, step 1's tokens already reached the
screen — deleting them would be jarring. Each step's text remains as its own
finalised bubble; `reply` still tracks the last non-empty content for history
and the `"done"` event.

### A step may emit tool calls with no text

A model step can return only tool calls and no content. No `"token"` events
fire for that step, so no streaming bubble is created — only the `"tools"`
event fires, producing a progress row. This is normal and requires no special
handling: the accumulator's `content` stays `""`, `message.content` is `None`,
and `reply` retains whatever the previous step produced.

### Which bubble `"done"` replaces

`"done"` replaces only the *current* streaming bubble — the one belonging to
the last step — with the final split applied. Earlier steps' bubbles are
already finalised (their tokens stopped, their split settled) and are not
touched again.

### `MAX_STEPS`, `MAX_TOKENS`, and the stall fallback

All unchanged. The stream is consumed inside the existing `for _ in
range(MAX_STEPS)` loop. `STALLED` (the "I wasn't able to finish that one"
fallback) still fires when no content was produced across all steps.

---

## 5. Rendering (`surface/window.py`)

### The streaming bubble

A `"token"` event appends its delta to a growing `Gtk.Label`. The label is
appended to the transcript once, on the first token of a step, and updated in
place thereafter.

### Live split during streaming

The spoken/details split (`window.py:split`) runs incrementally as tokens
arrive:

- **Before the `---` marker appears:** all tokens render in the spoken bubble.
- **Once the marker arrives:** the spoken portion freezes; subsequent tokens
  flow into a details expander beneath it.

To keep this cheap, splitting does not re-run over the whole buffer on every
token. Once the marker has been seen, only the details portion grows; the spoken
portion is fixed. The marker match uses the existing `MARKER` regex
(`window.py:48`), unchanged.

### `"tools"` event → progress row

A dimmed `Gtk.Label` (CSS class added for muted styling) is appended to the
transcript with the sentence from `describe_batch`. It remains visible after the
tools run — it records what happened, not a spinner that disappears. Multiple
tool steps in one turn stack naturally as separate rows.

### `"done"` event → finalise

The full `split()` runs on the final reply, applying the `SPOKEN_MAX` length
guard and the sentence-boundary cut that mid-stream splitting skips. The
streaming bubble is replaced with the final formatted result (spoken label +
optional details expander), matching v0.3's `_show_reply` output. This is the
one moment the spoken text may change — overflow can move to details. It happens
once, at the end of the turn.

### Threading invariant

Unchanged. Every UI mutation still goes through `GLib.idle_add`. The callback
fires from the worker thread but touches no GTK directly — same discipline as
the existing `_show_reply` / `_show_failure` path.

---

## 6. What does not change about the surface

- **The approval dialog** (`surface/dialog.py`). Untouched. The `"tools"` event
  fires *before* `gate.prepare()`, which is what opens the dialog; the progress
  row is on the transcript, not in the dialog.
- **The recall pane, onboarding, clipboard mirror.** Untouched.
- **Failure handling.** `_show_failure` still fires on an exception from
  `send()`. A mid-stream network drop raises from the stream iterator and is
  caught by the same `try/except` in `_run_turn`.

---

## 7. Testing

### Existing tests stay green

`on_event=None` means `send()` is identical to v0.3. All 390 tests run
unchanged.

### New tests

1. **`tests/test_streaming.py`** — the fragment accumulator. A fake client
   yields canned chunks (content deltas plus a tool call split across three
   chunks: `id`, `name`, `arguments`). Assert the accumulated message matches
   what `tool_calls_in` expects: the same `(id, name, arguments)` triples a
   non-streaming call would produce. This is the one check that fails if fragment
   accumulation breaks.

2. **Extend `tests/test_session.py`** — events fire in order. A recorded
   callback receives `("token", ...)*`, `("tools", [...])`, `("done", reply)`
   in sequence for a two-step turn (text, then tools, then final text).

3. **Extend `tests/test_window.py`** — live split during streaming. Feed
   `"token"` events into the handler; assert the spoken label and details
   expander match the expected final split. Covers marker-mid-stream and the
   `SPOKEN_MAX` length guard on finalise.

### Ponytail self-check

The fragment accumulator is the one non-trivial piece of new logic. An inline
`assert`-based `demo()` in a scratch check (run once, by hand, before the test
suite covers it) confirms round-trip parity: the same model output, streamed and
non-streamed, produces identical `(id, name, arguments)` triples.

---

## 8. Out of scope

- **Verb tense in `describe_batch`** ("Move" → "Moving"). Cosmetic; deferred
  until a tester notices.
- **A model router or fallback chain.** YAGNI until an outage actually bites.
- **Prompt caching.** $0.00006/turn; the cache breakpoint is preserved by the
  fixed system prompt, and wiring cache is not worth it now.
- **Cancelling a stream mid-turn.** The user cannot abort a running turn. v0.3
  has no abort either; adding one is a separate, larger change (it touches the
  gate's in-flight state and is unsafe to bolt on here).

---

## 9. Acceptance criteria

1. **Token streaming.** During the final model call of a turn, text appears in
   the window incrementally, not all at once after the call returns.
2. **Tool-call progress.** Before the approval dialog opens for a batch, a
   progress row showing `describe_batch` output appears in the transcript and
   remains visible after the batch runs.
3. **Live split.** When the model emits the `---` marker mid-stream, tokens
   before it are shown as spoken and tokens after it flow into a details
   expander, without waiting for the message to complete.
4. **No regression.** All 390 existing tests pass unchanged.
5. **New tests pass.** The fragment accumulator, event ordering, and streaming
   split tests described in §7 pass.
6. **Failure path intact.** A mid-stream network drop surfaces the "Couldn't
   reach the model" banner, same as v0.3.

---

## 10. The bet, and how it ends

The wager behind this release is narrow: **streaming changes how JARVIS feels
without changing what it can do.** The persona is *calm and unhurried*; a 3–8
second frozen window is neither. If, after this ships, a tester still perceives
latency as the product's weakness, the problem is the model or the provider, not
the render path — and that is a v0.4 concern, not a v0.3.1 patch.
