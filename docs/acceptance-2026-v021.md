# ZeroOS v0.2.1 — Acceptance Pass

Spec §11 sets seven success criteria for this release. This document records
the evidence for each, following the shape of
[the v0.2 acceptance pass](acceptance-2026-v02.md). Criterion 8 is not from
§11 — it covers a behaviour decided after the spec was written, and is
recorded here so it gets judged rather than assumed.

> **Status: RUN, with one criterion open, 2026-08-04.** Every criterion has
> been exercised. Criteria 3, 4, 5, and 7 are CONFIRMED from the suite —
> each cited test run individually rather than inferred from a green run,
> and criterion 3's mutation-checked. Criterion 6 is CONFIRMED: the store,
> the outgoing request, and the pane were all measured at 150 × 300, the
> pane rendered headless and looked at. Criteria 1, 2, and 8 are
> SCRIPT-CONFIRMED — driven against the real model through the real
> `Session`, which settles what they mechanically claim and does not settle
> what they are actually asking. See the status vocabulary below.
>
> **The walk found a Critical defect and it is fixed.** Criterion 2 came back
> with nothing proposed. The nothing was the bug, not the verdict: v0.2.1's
> headline feature had never fired once in production. Details under
> "What the walk found" below.

**Status vocabulary.** Three words, and the difference between them is the
point of this document.

- **CONFIRMED** — a test or a measurement settles it outright.
- **SCRIPT-CONFIRMED** — a script drove the real model through the real code
  path and the mechanical claim held. What such a script cannot reach is
  whether the behaviour reads, to a person, as attention or as nagging.
  Every SCRIPT-CONFIRMED criterion below names its remaining half explicitly.
- **NOT STARTED** — untouched.

A SCRIPT-CONFIRMED criterion is not a confirmed one. Collapsing the two would
be exactly the thing this document exists to prevent.

**Who ran it.** The assistant, at the user's instruction, on 2026-08-04. It
can run tests, mutate source, measure payloads, render the pane headless, and
drive real sessions against the real model. It cannot judge whether being
proposed a fact feels like attention. Every criterion that turns on that is
left half-open on purpose rather than argued into a verdict.

**Suite state at HEAD:** `318 passed, 0 failed`, measured with the whole
suite, `tests/test_app.py` included, with ZeroOS closed. The v0.2 baseline
was 284.

Most of the walk ran with that module excluded (`317 passed`) because it
segfaults while a ZeroOS instance is running: its `register()` returns a
*remote* GApplication, and `do_activate()` on a remote instance crashes
inside GTK. That is environmental and unrelated to this release — closing
the app is the whole fix — but the 318 above is a run, not 317 plus one.

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Acts on a stored fact instead of asking again | **SCRIPT-CONFIRMED** | fact crossed a session boundary and was acted on unprompted, live |
| 2 | Proposes an unasked fact in ordinary use | **SCRIPT-CONFIRMED** | proposed verbatim from a passing mention — *after* the defect below was fixed |
| 3 | No tool-result text in any noticing payload | **CONFIRMED** | `tests/test_notice.py::test_tool_results_never_reach_the_noticing_request`, run alone and mutation-checked |
| 4 | Fresh install's first request carries exactly one system message | **CONFIRMED** | `tests/test_session.py::test_with_no_memories_there_is_exactly_one_system_message` — the v0.1-parity half of this criterion was voided by the persona ruling, see below |
| 5 | Every memory row starts unticked | **CONFIRMED** | `tests/test_gate.py::test_a_remember_row_is_offered_unticked`, `tests/test_dialog.py::test_a_row_offered_unticked_starts_unticked` |
| 6 | 150 × 300 stored, listed, and sent without the pane breaking | **CONFIRMED** | store, request, and pane all measured at the cap; pane rendered and read |
| 7 | Close never delayed by the summary dialog | **CONFIRMED** | `tests/test_window.py::test_close_request_halts_the_close_until_the_summary_finishes` |
| 8 | A declined proposal is not raised again this session | **SCRIPT-CONFIRMED** | holds within the noticing path; **does not hold across paths** — see the finding |

### How the live criteria were run

Criteria 1, 2 and 8 were driven by a script that builds real `Session`
objects against the real model, with a recorder standing in for the consent
dialog. Each criterion got its **own** `ZEROOS_HOME`, with `XDG_DATA_HOME`
unset, and each run asserts its resolved `data_dir()` is inside that fixture
before anything writes — the user's real store is never opened. The API key
is read from the environment inside the process and never printed, logged,
or written anywhere.

Separate homes are not tidiness. Criterion 6's fixture holds 150 facts at the
cap; a criterion 1 run pointed at it would have every `remember` refused for
space and would read as "memory does not persist" — a false negative for the
wrong reason.

### The run

```
$ /usr/bin/python3 -m pytest -v \
    tests/test_notice.py::test_tool_results_never_reach_the_noticing_request \
    tests/test_session.py::test_with_no_memories_there_is_exactly_one_system_message \
    tests/test_gate.py::test_a_remember_row_is_offered_unticked \
    tests/test_dialog.py::test_a_row_offered_unticked_starts_unticked \
    tests/test_window.py::test_close_request_halts_the_close_until_the_summary_finishes
tests/test_notice.py::test_tool_results_never_reach_the_noticing_request PASSED
tests/test_session.py::test_with_no_memories_there_is_exactly_one_system_message PASSED
tests/test_gate.py::test_a_remember_row_is_offered_unticked PASSED
tests/test_dialog.py::test_a_row_offered_unticked_starts_unticked PASSED
tests/test_window.py::test_close_request_halts_the_close_until_the_summary_finishes PASSED
5 passed, 4 warnings in 2.24s
```

## What the walk found

### Critical, now fixed — the noticing pass had never fired

Criterion 2's first live run proposed nothing at all. `notice.candidates()`
returns `[]` both when it finds nothing and when it throws, so "nothing" is
never self-explaining; a probe against the same transcript discriminated it:

```
finish_reason: length
reasoning_tokens: 200   completion_tokens: 202   content: None
```

`MODEL` is a reasoning model. At `notice.MAX_TOKENS = 200` it spent the entire
budget thinking, was cut off before writing a single character of content, and
returned `content=None` — which `candidates()` reads as "found nothing".
**v0.2.1's headline feature had never produced a candidate in production.**
Every green test in `tests/test_notice.py` passed throughout, because they all
feed a fake client a canned reply; none of them could see the request's token
budget.

Raising the budget is not the fix. At 1200 the model reasoned for all 1200 and
still returned `None` — the reasoning expands to whatever it is given. Two
things actually work:

| Attempt | reasoning tokens | content |
|---|---|---|
| `MAX_TOKENS` 200 (shipped) | 200 | `None` |
| `MAX_TOKENS` 1200 | 1200 | `None` |
| `reasoning: {enabled: false}`, 200 | 0 | the fact, verbatim |
| `MAX_TOKENS` 65536, reasoning auto | 1170 | the fact, verbatim |

**USER RULING:** the ceiling, with reasoning left on. `notice.MAX_TOKENS` and
`session.MAX_TOKENS` are both now 65536, `MODEL`'s `max_completion_tokens`.
It is a ceiling and not a spend — a pass that reasons for ~1200 tokens is
billed for ~1200 — but it does mean the noticing pass now bills roughly
**1,200 reasoning tokens per turn (~$0.00016)** that the shipped version was
not paying, because the shipped version was not working. Pinned by
`tests/test_notice.py::test_the_noticing_request_asks_for_room_to_think`.

The same ruling raised `session.MAX_TOKENS` from 4096 to 65536, and that
half is not measured here. The main step loop is now free to reason and
answer up to the ceiling on every one of up to `MAX_STEPS` iterations, so
generated tokens per turn will rise by an amount this walk did not put a
number on. Still a ceiling rather than a spend, and 4096 was itself a guess
— but it belongs in the billing-gate arithmetic beside the 1,200.

The general lesson is worth more than the fix: a function that swallows its
own failure into an ordinary-looking return value cannot be trusted to tell
you it is healthy, and no amount of testing it with a fake client will find
that out. It took running the thing for real.

### Important, not fixed — a decline only sticks within one path

Criterion 8's run showed the same fact proposed twice in one session, by two
different routes:

```
turn 1   Remember: "Yash's tax paperwork is stored in Documents/Tax folder"
turn 2   Remember: "My tax paperwork all lives in the Documents folder, in a folder called Tax."
```

Turn 1 is the model calling `remember` itself, having read the sentence as a
request. Turn 2 is the noticing pass offering the same fact in the user's own
words. `Session._offered` records only what the *noticing* path has offered,
so declining the model's own `remember` does not stop the noticing pass
raising the same thing on the next turn — which is precisely the erosion
`_offered` was added to prevent, one route over.

Not fixed here, deliberately. The two texts are not equal as strings and never
will be, so suppressing the second means comparing them by meaning — which is
the consolidation machinery the standing ruling excludes. Recorded for a
decision rather than solved by reflex.

### One finding, from criterion 6's measurement

At the cap the injected memory block is **47,107 characters — about 11,800
tokens on every turn**. v0.2's ceiling was 50 × 200 = 10,000 characters, so
the per-turn memory payload grew roughly **4.7×**, and v0.2.1 additionally
sends a second model call per turn for the noticing pass. Nothing breaks —
this is the cap working as specified — but the roadmap's per-turn cost
estimate, and the argument built on it in the billing gate, predate both
changes and no longer describe what ships. Recorded here rather than in the
roadmap because it was measured here.

---

## Criterion 1 — Acts on a stored fact instead of asking again

**SCRIPT-CONFIRMED, 2026-08-04.**

Spec §11.1: "With a fact stored that bears on the request, the assistant
acts on it instead of asking for it again." This is model behaviour on a
live reply, not a return value a mock client can stand in for. A test can
prove a fact was *sent* — that is criterion 4's job, and v0.2's before it —
but nothing in the suite can prove a reply *used* what was sent rather than
asking the question the fact already answers.

So it was run for real. Session A stored a fact and closed. Session B is a
fresh `Session` object over the same store, and its question deliberately
avoids the words "thesis", "Documents", and "remember":

```
-- session A --
  [dialog] ['Remember: "my thesis chapters live in the Thesis folder inside Documents"']
A reply: Done.
stored after A: ['my thesis chapters live in the Thesis folder inside Documents']

-- session B, fresh object, same store --
injected block:
Things the user has asked you to remember. ...
[ee293d15] my thesis chapters live in the Thesis folder inside Documents

B asks: Where should I save the new chapter draft I just finished?
B reply: Your new chapter draft should go in the Thesis folder inside Documents, Sir.

RESULT: reply refers to the remembered location: True
```

The fact crossed the session boundary, reached the request, and was acted on
without being mentioned. That is the mechanical claim, and it holds.

**What this does not settle.** Whether the assistant finds a *subtler*
connection than one staged for it. See the conflict below — it is the reason
this is SCRIPT-CONFIRMED and not CONFIRMED.

**Author-is-tester conflict.** The person running this protocol chooses both
the fact and the request it bears on, and picks the request specifically
because the connection is obvious to whoever wrote the test case. A real
user would not stage it this cleanly. This can show the assistant is
*capable* of acting on a fact when the connection is exact — it says
nothing about whether it notices a subtler connection a real user leaves
for it to find.

## Criterion 2 — Proposes an unasked fact in ordinary use

**SCRIPT-CONFIRMED, 2026-08-04 — and this is the criterion that found the
defect.** This is the one spec §11 calls "the one the whole release is for,"
and it gets the least mechanical help of the seven. `tests/test_notice.py`
proves the noticing pass can produce a candidate from a fixture transcript
and proves the security filter around it holds. It proves nothing about
whether an unprompted proposal shows up in a conversation a person is
actually having — which is exactly why it was the criterion that noticed
the pass was dead.

**First run, against the shipped code:**

```
pending after turn 1: []
proposed texts: []
RESULT: something was proposed unprompted: False
```

That is not "there was nothing worth noticing". That is the pass returning
`[]` because its budget was spent on reasoning — see "What the walk found".

**Second run, after the fix.** A fact mentioned in passing inside a turn
whose actual request is about something else:

```
turn 1: The printer only works when it is plugged into the left-hand USB port,
        took me all morning to work that out. Anyway, how many files are in my
        Downloads folder?
reply:  I cannot find a Downloads folder in your home directory, Sir.

pending after turn 1: ['The printer only works when it is plugged into the left-hand USB port.']

turn 2 (ordinary, unrelated -- this is what opens the dialog):
  [dialog] ['Remember: "The printer only works when it is plugged into the left-hand USB port."']

RESULT: something was proposed unprompted: True
```

**The paraphrase check — the sharpest part of this criterion, and it is
mechanical.** §11.2 asks whether the proposed text matches what was said
rather than a flattering rewrite. Compare:

- said: *"The printer only works when it is plugged into the left-hand USB port, took me all morning to work that out."*
- proposed: *"The printer only works when it is plugged into the left-hand USB port."*

Word for word, with only the trailing aside dropped. No summary, no
improvement, nothing the user did not say. This half is settled.

**What this does not settle.** Whether an unrequested proposal, arriving in
the middle of a real session nobody staged, reads as attention or as
nagging. That is the rest of criterion 2 and no script reaches it.

### Protocol for the remaining half

**Day one:** use ZeroOS for an ordinary session — real requests, not ones
staged to bait a proposal — and, at some point, mention something in
passing that a reasonable noticing pass might keep: where a folder lives, a
preference stated once, not framed as an instruction to remember it.

**Before the next session opens:** write down a prediction — will a
proposal appear, and roughly what will it say.

**Prediction:** _to be recorded here, before the next session opens, by the
person who will grade it._ Deliberately left blank by the assistant. This
instrument works only because the grader commits before seeing the outcome;
a prediction written and then graded by the same party that ran the script
is theatre, and writing one here would have destroyed the only thing the
protocol was for.

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

**CONFIRMED, 2026-08-04.** Run alone, and — because this is the criterion
everything else in the release rests on — shown able to fail. `_readable` in
`zeroos/agent/notice.py` was replaced with `return list(messages)`, a
pass-through filter, and the test failed:

```
$ # with _readable replaced by a pass-through
$ /usr/bin/python3 -m pytest -q \
    tests/test_notice.py::test_tool_results_never_reach_the_noticing_request
FAILED tests/test_notice.py::test_tool_results_never_reach_the_noticing_request
1 failed, 1 warning in 0.39s
```

Source restored from a backup and `git diff` confirmed clean afterwards. A
passing security test proves nothing on its own; this one detects the exact
regression it is named for.

**What this does not cover.** It proves the filter drops `role == "tool"`
messages from the payload `notice.candidates` builds. It does not prove no
future producer puts file text into an `assistant` message's `content`,
where the filter would pass it through by design. That hazard was traced to
be unreachable at the time of writing — the three `_messages` producers all
emit either prose or tool results — and it is unreachable by argument, not
by test.

Evidence:
`tests/test_notice.py::test_tool_results_never_reach_the_noticing_request`,
which builds a transcript whose tool result carries a marker string and
asserts the marker appears nowhere in the request `notice.candidates`
sends. Spec §4 calls this filter the security boundary of the release; spec
§9 calls this the single most important test in the section.

## Criterion 4 — Fresh install's first request carries exactly one system message

**The criterion as written no longer holds, because it was retired on
purpose.** It was drafted as "byte-identical to v0.1's", and the USER RULING
of 2026-08-04 replaced the system prompt with the JARVIS persona. The v0.1
bytes are gone by decision, not by drift, so the parity clause is void and
this section states the property that survived it.

**CONFIRMED, 2026-08-04**, for that surviving property. Run alone; passed.
Evidence:
`tests/test_session.py::test_with_no_memories_there_is_exactly_one_system_message`,
which asserts a fresh session's outgoing request carries exactly one system
message and that its content is `prompt.SYSTEM_PROMPT`. Note what that
assertion is and is not: it compares the request against the current value of
`SYSTEM_PROMPT`, so it proves the request carries the prompt and nothing
appended to it — it cannot prove `SYSTEM_PROMPT` itself has not changed. The
thing that pins the bytes is
`tests/test_prompt.py::test_sir_variant_is_byte_identical_to_the_pinned_system_prompt`,
and its pin now holds the JARVIS text.

What still matters here, and what the test does prove: the `MEMORY_PREFACE`
sentence added in this release (spec §3) prefixes the *second* system
message, which does not exist on an empty store. Nothing section 3 adds can
reach a fresh install's first request regardless of what it says.

## Criterion 5 — Every memory row starts unticked

**CONFIRMED, 2026-08-04.** Both tests run alone; both passed. Evidence:
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

**CONFIRMED, 2026-08-04.** The store, the outgoing request, and the pane were
all measured at the true worst case. The pane was built, counted, deleted
from, and rendered to an image and looked at.

**Stored.** 150 facts written through `memory.add()` itself rather than
hand-written JSON, so the record shape is correct by construction. Every
fact is *exactly* 300 characters — the ceiling, not near it:

```
facts=150 min_len=300 max_len=300 cap=300
```

**Sent.** `Session._memory_messages()` against that store returns exactly one
message, as specified, and it is large:

```
system messages from memory: 1
injected block chars: 47,107
rough tokens (chars/4): 11,776
lines: 152
```

Nothing fails. The cap does what it says and growth is bounded. But 47 KB on
every turn is the number this criterion existed to discover, and it is worth
carrying to the roadmap's billing gate rather than leaving here — see the
finding at the top of this document.

**Listed.** The real `recall.build()` pane was constructed against that store
under Xvfb and its widget tree walked:

```
before: rows=151 fact_rows=150
every stored fact has a row, in store order: OK
longest row title: 300 chars
title-lines property: 0
after one delete: rows=150 fact_rows=149
delete at 150 removed exactly one row and one record: OK
```

Every stored fact has a row, in store order, with no truncation of the title —
`title-lines = 0` means unlimited, so a 300-character fact wraps rather than
being clipped. The 151st row is "Forget everything". Deleting a row at 150
removes exactly one row and exactly one record, and `_redraw()` survives
rebuilding the whole list.

**Looked at.** Rendered to PNG through `GskRenderer.render_texture` and read:

- Rows wrap to seven or eight lines and show the fact in full. Nothing is
  clipped, nothing runs off the window.
- The timestamp subtitle stays legible under the wrapped title.
- The trash button stays vertically centred and reachable on every row,
  including the tallest.
- No layout failure, no overlap, no collapsed row.

Legible, not merely mapped. The v0.2 defect this criterion was written to
catch does not reproduce at 150 × 300.

**One usability observation, not a defect.** A 300-character fact renders at
roughly 100 px tall, so a full store is on the order of 15,000 px of
scrolling — about fifteen screens — with no search and no grouping. Every
row is individually fine; finding a particular one is not. Worth knowing
before the cap is raised again.

**The fixture, if it is wanted by hand.** A populated home is waiting:

```bash
env -u XDG_DATA_HOME \
    ZEROOS_HOME=/tmp/claude-1000/-run-media-yash-External-Zerostic-ZeroOS/17fab52a-f514-4e27-9b63-d1755551c52d/scratchpad/c6-home \
    /usr/bin/python3 -m zeroos
```

`ZEROOS_HOME` is the override `paths.home()` already provides for exactly
this; `XDG_DATA_HOME` must be unset alongside it or `data_dir()` wins and the
real store is used instead. The real memory store is untouched by this
walk. Note the fixture is in a scratch directory and will not survive a
reboot — rebuild it with the same script if it is gone.

### Original notes

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

**CONFIRMED, 2026-08-04.** Run alone; passed. Evidence:
`tests/test_window.py::test_close_request_halts_the_close_until_the_summary_finishes`,
which drives `ChatWindow._on_close` directly: the first call halts the
close and moves the session's `close()` to a worker thread rather than
running it on the calling thread, and the second call — once `_closing` is
set — lets the close through.

The mechanism this test pins is not the one spec §7 originally described.
See the amendment to spec §7 for what changed and why:
[`docs/superpowers/specs/2026-08-04-zeroos-v021-memory-design.md`](superpowers/specs/2026-08-04-zeroos-v021-memory-design.md#7-continuity).
The property this criterion actually needs — that a closing dialog cannot
delay the window's disappearance indefinitely — holds under the shipped
mechanism too, by a different route: `_on_close` returns immediately, the
summary runs on a worker thread, and the window destroys itself once that
thread finishes, rather than being hidden beforehand.

## Criterion 8 — A declined proposal is not raised again this session

**SCRIPT-CONFIRMED within the noticing path, 2026-08-04 — and it does not
hold across paths.** Evidence:
`tests/test_session.py::test_a_declined_candidate_is_not_proposed_again_this_session`,
which runs three turns with the noticing pass returning the same fact every
time and the user declining, and asserts the dialog saw it exactly once.

**Live run.** A fact stated, the proposal declined, then three more turns
still on the same subject, then a close with the summary enabled:

```
turn 1: My tax paperwork all lives in the Documents folder, in a folder called Tax.
  [dialog] ['Remember: "Yash's tax paperwork is stored in Documents/Tax folder"']

turn 2 -- the dialog opens here and is declined:
  [dialog] ['Remember: "My tax paperwork all lives in the Documents folder, in a folder called Tax."']

turns 3 and 4 -- still talking about the same subject:
dialogs so far: 2

close(summary=True):
dialogs after close: 2

RESULT: nothing was stored: True
RESULT: proposed exactly once, never again: True
```

The noticing path behaves: proposed once, declined, never raised again —
including from the closing summary, which is the part no existing test
covered. Nothing reached the store.

**But look at turn 1.** That dialog is a *different* path — the model calling
`remember` itself, having read the sentence as a request — and it is the same
fact in different words. Declining it did not stop the noticing pass asking
again on turn 2. `Session._offered` tracks only what the noticing path has
offered, so a decline sticks within one route and not across the two. This is
recorded in full under "What the walk found" and is left for a decision, not
patched: matching those two strings means matching them by meaning, which is
the consolidation machinery the standing ruling excludes.

Added after the spec was written, so it is here rather than in spec §11 —
see the "offered once per session" subsection of spec §4 for the reasoning.
It exists because the noticing pass reads the whole accumulated transcript
on every turn: without suppression, a declined fact returns on the next
turn and the next, and a dialog that keeps asking the same question is how
consent decays into reflex, which is the exact failure spec §8 names.

What the script cannot close: whether being asked once and then left alone
*feels* like being listened to. Judge that during the sittings for criteria
1 and 2 rather than in its own session.

### Protocol for the remaining half

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
