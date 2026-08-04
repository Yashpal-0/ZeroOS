# ZeroOS v0.3 — Acceptance Pass

Spec §11 sets seven success criteria for this release. This document records
the evidence for each, following the shape of
[the v0.2 acceptance pass](acceptance-2026-v02.md). Criterion 8 is not from
§11 — it covers a behaviour decided after the spec was written, and is
recorded here so it gets judged rather than assumed.

> **Status: NOT STARTED.** Every criterion below is unconfirmed. Criteria 3,
> 4, 5, and 7 have tests that pin them, and those tests pass at HEAD today —
> but a test passing in the suite is not the same thing as someone having
> run the acceptance walk and recorded that it does, and that distinction is
> the reason this document exists rather than a green test run standing in
> for it. Criteria 1, 2, and 6 have no test at all; they can only be settled
> by using the app, and none of that use has happened yet.

**Suite state at HEAD:** `312 passed, 0 failed`. The v0.2 baseline was 284;
v0.3 added 28 tests.

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Acts on a stored fact instead of asking again | NOT STARTED | hands-on |
| 2 | Proposes an unasked fact in ordinary use | NOT STARTED | hands-on — the release's real criterion |
| 3 | No tool-result text in any noticing payload | NOT STARTED | `tests/test_notice.py::test_tool_results_never_reach_the_noticing_request` |
| 4 | Fresh install's first request byte-identical to v0.1's | NOT STARTED | `tests/test_session.py::test_with_no_memories_there_is_exactly_one_system_message` |
| 5 | Every memory row starts unticked | NOT STARTED | `tests/test_gate.py::test_a_remember_row_is_offered_unticked`, `tests/test_dialog.py::test_a_row_offered_unticked_starts_unticked` |
| 6 | 150 × 300 stored, listed, and sent without the pane breaking | NOT STARTED | hands-on — the recall pane is the part at risk |
| 7 | Close never delayed by the summary dialog | NOT STARTED | `tests/test_window.py::test_close_request_halts_the_close_until_the_summary_finishes` |

---

## Criterion 1 — Acts on a stored fact instead of asking again

**NOT STARTED.**

Spec §11.1: "With a fact stored that bears on the request, the assistant
acts on it instead of asking for it again." This is model behaviour on a
live reply, not a return value a mock client can stand in for. A test can
prove a fact was *sent* — that is criterion 4's job, and v0.2's before it —
but nothing in the suite can prove a reply *used* what was sent rather than
asking the question the fact already answers. Only watching a real reply
settles that.

### Protocol

**Before opening the app:** store one fact by asking for it directly, then
close the session so it becomes ordinary state rather than something fresh
in the current context. In a later session, make a request that fact bears
on, without mentioning the fact. Write down, before that request is sent,
what the reply is predicted to do.

**Prediction:** _to be recorded here, before the request is sent._

**Answer:** _to be recorded here_ — the actual reply, and whether it matched
the prediction.

**Author-is-tester conflict.** The person running this protocol chooses both
the fact and the request it bears on, and picks the request specifically
because the connection is obvious to whoever wrote the test case. A real
user would not stage it this cleanly. This can show the assistant is
*capable* of acting on a fact when the connection is exact — it says
nothing about whether it notices a subtler connection a real user leaves
for it to find.

## Criterion 2 — Proposes an unasked fact in ordinary use

**NOT STARTED.** This is the criterion spec §11 calls "the one the whole
release is for," and it gets the least mechanical help of the seven.
`tests/test_notice.py` proves the noticing pass can produce a candidate from
a fixture transcript and proves the security filter around it holds. It
proves nothing about whether an unprompted proposal shows up in a
conversation a person is actually having.

### Protocol

**Day one:** use ZeroOS for an ordinary session — real requests, not ones
staged to bait a proposal — and, at some point, mention something in
passing that a reasonable noticing pass might keep: where a folder lives, a
preference stated once, not framed as an instruction to remember it.

**Before the next session opens:** write down a prediction — will a
proposal appear, and roughly what will it say.

**Prediction:** _to be recorded here, before the next session opens._

**Day two:** open the app and record what actually happened — did a
`remember` row appear unprompted, what did its text say, and does that text
match what was actually said in passing, rather than a paraphrase that
reads better than the original.

**Answer:** _to be recorded here._

**Author-is-tester conflict.** The tester is also the one who decides what
"something worth mentioning in passing" will be, which means the tester
already knows what a good proposal would look like before the model gets a
chance to surprise them. That foreknowledge cannot be removed by whoever
built the feature testing it alone; it is recorded here rather than
presented as a blind trial.

## Criterion 3 — No tool-result text in any noticing payload

**NOT STARTED.** Evidence:
`tests/test_notice.py::test_tool_results_never_reach_the_noticing_request`,
which builds a transcript whose tool result carries a marker string and
asserts the marker appears nowhere in the request `notice.candidates`
sends. Spec §4 calls this filter the security boundary of the release; spec
§9 calls this the single most important test in the section.

## Criterion 4 — Fresh install's first request byte-identical to v0.1's

**NOT STARTED.** Evidence:
`tests/test_session.py::test_with_no_memories_there_is_exactly_one_system_message`,
which asserts a fresh session's outgoing request carries exactly one system
message and that its content is `SYSTEM_PROMPT` unchanged. The
`MEMORY_PREFACE` sentence added in this release (spec §3) prefixes the
*second* system message, which does not exist on an empty store, so it
cannot move these bytes regardless of what it says.

## Criterion 5 — Every memory row starts unticked

**NOT STARTED.** Evidence:
`tests/test_gate.py::test_a_remember_row_is_offered_unticked` (the gate
supplies `False` as the default tick state for a `remember` row and `True`
for everything else) and
`tests/test_dialog.py::test_a_row_offered_unticked_starts_unticked` (the
dialog's checkbox actually renders unticked when told to). No `remember`
row is exempt, including one for a fact the user asked to be stored out
loud — spec §5's reasoning is that the only way to know who asked is the
model's own report, and that report is exactly what an attacker's file text
can forge.

## Criterion 6 — 150 × 300 stored, listed, and sent without the pane breaking

**NOT STARTED.**
`tests/test_catalog_memory.py::test_a_merge_at_the_cap_frees_room_for_the_merged_fact`
and the session tests covering `_memory_messages()` confirm the store and
the outgoing request handle the cap mechanically. Neither touches the
recall pane, which is the part actually at risk: 150 rows of up to 300
characters each is roughly four times v0.2's ceiling, and v0.2's own
acceptance pass (criterion 5, its §6 walk) found a legibility defect at a
much smaller size that no string-level test could see. This criterion needs
the pane opened for real, at the cap, and looked at.

### Protocol

**Setup:** populate the store to 150 facts near the 300-character ceiling —
scripted, not typed by hand one at a time — then open the recall pane.

**Prediction, written before opening the pane:** _to be recorded here_ —
does the pane stay scrollable and readable, or does it degrade (rows
running off the window, the delete button becoming unreachable, the pane
failing to lay out at all)?

**Answer:** _to be recorded here_, including whether all 150 rows are
present, whether deleting one still works at that count, and whether the
pane is legible rather than merely mapped — the same distinction v0.2's
acceptance pass drew and could not close for lack of a screenshot.

## Criterion 7 — Close never delayed by the summary dialog

**NOT STARTED.** Evidence:
`tests/test_window.py::test_close_request_halts_the_close_until_the_summary_finishes`,
which drives `ChatWindow._on_close` directly: the first call halts the
close and moves the session's `close()` to a worker thread rather than
running it on the calling thread, and the second call — once `_closing` is
set — lets the close through.

The mechanism this test pins is not the one spec §7 originally described.
See the amendment to spec §7 for what changed and why:
[`docs/superpowers/specs/2026-08-04-zeroos-v03-memory-design.md`](superpowers/specs/2026-08-04-zeroos-v03-memory-design.md#7-continuity).
The property this criterion actually needs — that a closing dialog cannot
delay the window's disappearance indefinitely — holds under the shipped
mechanism too, by a different route: `_on_close` returns immediately, the
summary runs on a worker thread, and the window destroys itself once that
thread finishes, rather than being hidden beforehand.

## Criterion 8 — A declined proposal is not raised again this session

**NOT STARTED.** Evidence:
`tests/test_session.py::test_a_declined_candidate_is_not_proposed_again_this_session`,
which runs three turns with the noticing pass returning the same fact every
time and the user declining, and asserts the dialog saw it exactly once.

Added after the spec was written, so it is here rather than in spec §11 —
see the "offered once per session" subsection of spec §4 for the reasoning.
It exists because the noticing pass reads the whole accumulated transcript
on every turn: without suppression, a declined fact returns on the next
turn and the next, and a dialog that keeps asking the same question is how
consent decays into reflex, which is the exact failure spec §8 names.

This criterion is behavioural, not mechanical, and the tests cannot close
it: what matters is whether being asked once and then left alone *feels*
like being listened to. Judge it during the sittings for criteria 1 and 2
rather than in its own session.

### Protocol

**Setup:** in one session, decline a proposed fact. Keep talking about the
same subject for several more turns.

**Prediction, written before the sitting:** _to be recorded here_ — does
the fact stay gone for the rest of the session, including from the closing
summary?

**Answer:** _to be recorded here_, and separately: does the assistant
behave as though it heard the refusal, or merely as though it forgot to
ask? Note also what happens in the *next* session, where the set is gone by
design and the fact may be raised again — and whether that reads as a fresh
start or as nagging.
