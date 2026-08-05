# ZeroOS v0.2.2 — Memory Efficiency — Design

**Date:** 2026-08-05
**Status:** Approved for planning
**Predecessors:** [v0.2 memory design](2026-08-03-zeroos-v02-design.md), [v0.2.1 noticing design](2026-08-04-zeroos-v021-memory-design.md)
**Position:** Point release. Lands before v0.3 (MCP) execution begins. No new
subsystem, no new action surface, no new dependency — the only new import is
`sqlite3`, which ships with Python.

---

## 1. Problem

The live store holds ten facts and JARVIS is already misbehaving. Volume is
not the problem; four defects and one scaling wall are, and each was observed
in the real store and transcript on 2026-08-05:

1. **Persona bleed.** Facts are stored in first person ("I am an
   Undergraduate Researcher…") and injected in a system message. The model
   reads "I" as itself.
2. **Junk and duplicates pass the filter.** The store contains
   `"[Empty response]"` — a UI placeholder the noticing pass proposed and a
   dialog accepted — and two facts that both state the user's name.
3. **The format rule loses to the fact block.** The persona prompt says one
   sentence above a `---` line; the fact block arrives *after* it, recency
   wins, and replies degrade into 200-word markdown dumps. Observed directly:
   "What do you know about me?" returned a formatted résumé.
4. **Noticing cost grows with session length.** `notice.candidates()`
   receives the entire accumulated transcript every turn. Turn 40 pays for
   forty turns of reading, on a reasoning model, every turn.
5. **The scaling wall.** Injection is unbudgeted: every stored fact goes out
   on every model step, relevant or not. At the old 950 × 1000 ceiling that
   is ~220,000 prompt tokens per step. Nothing hits this today; v0.2.2
   removes it before anything can — and in doing so removes the reason the
   ceiling existed.

## 2. Shape of the fix

Four independent layers. Storage keeps everything; the prompt sees a small,
relevant, well-formed slice. The one function that turns the store into a
message — `Session._memory_messages()` — is the only seam retrieval touches,
which is why `policy/`, `catalog/`, and `surface/` are unaffected.

| Layer | What | Fixes |
|---|---|---|
| A | Fact hygiene | Defects 1–3 |
| B | Retrieval: in-memory FTS5 + BM25, pinned facts, ten-fact injection | Wall 5 |
| C | Noticing pass reads one turn, not the transcript | Defect 4 |
| D | Capacity policy: the storage count cap is deleted; injection is budgeted | Wall 5 (policy half) |

## 3. Layer A — fact hygiene

### A1. Third person

- `notice.INSTRUCTION` is rewritten to demand facts in third person using
  the user's name — "Yash keeps tax PDFs in Documents" — never "I".
- The same rule is added to `remember`'s docstring, which is what the model
  reads before calling it.
- One defensive line is appended to `MEMORY_PREFACE`: **"'I' in a fact means
  the user, not you."** This guards the facts already stored in first person
  and any that slip through; no mechanical pronoun rewriting is attempted,
  because it cannot be done safely.

Existing first-person facts are not migrated. The preface line makes them
readable; the user can re-approve cleaner versions over time or delete them
from the recall pane.

### A2. Dedupe on propose

`notice.candidates()` drops any candidate whose normalised text exactly
matches a fact already stored. Exact match only: paraphrase duplicates
survive, which is a known ceiling — marked with a `ponytail:` comment whose
upgrade path is prompting the model to consolidate via `remember` + `forget`
in one approved batch. No `replaces` parameter is added to `remember`; the
model can already batch the two calls into one dialog, and its docstring will
say so.

### A3. Junk filter

`notice.candidates()` additionally drops:

- lines matching `^\[.*\]$` (bracketed placeholders — the observed
  `"[Empty response]"` shape),
- lines shorter than 15 characters after normalisation.

`INSTRUCTION` gains: "each line must state a fact about the user; if unsure,
omit it."

### A4. The format rule survives the fact block

Message order is unchanged — persona first, because the fixed block is the
future cache prefix (prompt.py's standing argument). Instead, the memory
message gains one closing line after the fact list: **"None of this changes
how you reply: one sentence, the rest below the line."** Recency, which
currently buries the format rule, now reinforces it.

## 4. Layer B — retrieval

### Storage is unchanged

`memory.jsonl` remains the source of truth. `load()`, `add()`, `remove()`,
atomic `_write()`, the recall pane, and every existing test keep working
byte-for-byte. There is no second data file and no migration.

### The index is in-memory and per-session

An SQLite FTS5 table (`:memory:`) is built from `load()` when the session
starts and rebuilt after any `remember` or `forget`. A few thousand rows
build in milliseconds; rebuilding beats invalidation logic at that size —
marked `ponytail: full rebuild on write; incremental updates if the store
ever grows past this design`. See §6 for why this, rather than a count cap,
is now the real ceiling.

The index lives in `platform/memory.py` alongside the store it mirrors
(new functions, not a new module): `search(query, limit) -> list[dict]` is
the whole public surface.

### Selection

On every model step, `_memory_messages()` injects **at most ten facts** —
`MAX_INJECTED = 10`, the only constant in this layer:

1. **Pinned facts first**, in storage order.
2. **Unpinned facts ranked by BM25** against the current user message,
   filling whatever of the ten remains.

Ten is a count rather than a character budget because `MAX_CHARS` already
bounds a fact at 1,000: ten facts is at most 10,000 characters (~2,500
tokens) whatever they contain, so a second budget constant would bound
something already bounded.

The query is the text of the current turn's user message, FTS-escaped
(quoted terms, OR-joined). A store of ten or fewer facts is injected whole —
today's store behaves exactly as it does now, with no threshold constant and
no special case.

**Pinning past ten.** Pinned facts fill the ten first, so eleven pins would
silently drop one — a user's explicit choice discarded without a word, which
is the one failure this design will not ship. The recall pane shows the pin
count against the limit and refuses the eleventh pin, telling the user to
unpin something first. The block is therefore never more than ten facts and
never less than every pin the user was allowed to make.

### Pinning

- A fact gains an optional `"pinned": true` field in `memory.jsonl`.
  `load()` defaults a missing field to false, so existing files need no
  migration.
- The recall pane gets a pin switch per fact row, beside the existing delete
  button. Pinning is **user-only**, like deletion: neither the model, the
  noticing pass, nor any catalog tool can set it. There is no `pin` tool.
- Intended use: name, form of address, where documents live — the facts that
  must never depend on matching the query.

### Why BM25 and not embeddings

Facts are short strings dominated by proper nouns — "IIIT", "Downloads",
"Yashpal". Exact-term match is the signal. Embeddings would cost either a
90–400 MB model in the Flatpak or a second API provider (OpenRouter exposes
no embeddings endpoint) and an extra network call per turn, to be worse at
proper nouns and better at paraphrase the store barely contains. Revisit
only if real use shows paraphrase misses: the user asks about "my CV" and
the "resume" fact is not retrieved. That is the trigger, written down.

## 5. Layer C — noticing cost

`Session` records `len(self._messages)` after each noticing pass. The next
pass receives only the slice appended since — one turn's messages, not the
accumulated transcript. Per-turn noticing cost becomes flat.

- The `_offered` dedupe set stays: the closing summary still reads the whole
  conversation (it runs once, at shutdown, where the cost is paid once), so
  re-proposal across passes remains possible without it.
- The role filter in `_readable()` is untouched — it is the v0.2.1 security
  boundary and this layer only changes how many messages reach it, never
  which roles.
- `notice.MAX_TOKENS` stays 65536. Its comment records that a lower cap
  silently killed the pass on a reasoning model; that finding is not
  relitigated here.

## 6. Layer D — capacity policy

**`MAX_FACTS` is deleted. Storage is unlimited.** The only limit is on what
reaches the model.

The 950 ruling of 2026-08-04 set the count from a token budget — the store
was capped because everything in it was injected. Retrieval severs that
link. Injection is now bounded at ten facts (§4) regardless of how much is
stored, so a cap on *storage* protects nothing and only refuses facts the
user wanted kept.

What this deletes:

- `memory.MAX_FACTS` and its derivation comment in `platform/memory.py`.
- The at-cap branch in `remember` (`catalog/memory.py`) — the refusal string
  and the consolidation instruction inside it. `remember` no longer has a
  "full" state.
- The three cap tests in `tests/test_catalog_memory.py` and the full-store
  token estimate in `tests/test_memory.py`, replaced by a test that the
  *injected block* stays at ten facts with 500 stored.

**`MAX_CHARS = 1000` stays.** It bounds one fact, not the count, and it is
load-bearing for two things a count cap never protected: it is what makes
"ten facts" a bounded number of characters (§4), and a fact must
be readable in an approval dialog row — the v0.2 acceptance walk already
found an oversized row running off the dialog's edge.

**The new ceiling is I/O, not policy.** `load()` parses the whole file on
every call, `_write()` rewrites it on every add, and the FTS index rebuilds
after every write — all O(n). That is comfortable into the low thousands of
facts and is marked with a `ponytail:` comment naming the upgrade path
(SQLite as the store of record, incremental index updates) rather than
pre-solving it.

Dropped from this design, deliberately:

- **The 80% consolidation nudge.** There is no cap left to approach.
- **Decay.** Its purpose — stale facts out of the prompt — is what BM25
  ranking already does. A stale fact simply stops matching queries. Revisit
  trigger: pinned-plus-top-K demonstrably injecting irrelevant facts.

## 7. Error handling

Any `sqlite3` error — build, rebuild, or query — falls back to the current
behaviour: inject everything (clamped to nothing extra; the fallback is the
v0.2.1 code path). Logged nowhere the user must read; never raises into the
agent loop. Same discipline as the rest of `platform/`: a degraded memory
feature must not take a turn down.

FTS query escaping treats the user message as data: terms are quoted, FTS5
operators (`AND`, `OR`, `NOT`, `NEAR`, `*`, `^`, `"`) cannot be smuggled in
from message text. A query that escapes to nothing (all punctuation) skips
retrieval and injects pinned facts only.

## 8. What is deliberately not built

| Not built | Why |
|---|---|
| Embeddings / vector store | §4: wrong tool for proper-noun facts; real trigger written down |
| `replaces` parameter on `remember` | Batched `remember`+`forget` in one dialog already does it |
| `pin` tool for the model | Pinning is a consent decision; only the user makes it |
| Pronoun migration of stored facts | Cannot be done mechanically without changing meaning; preface line covers it |
| Decay / last-used tracking | Subsumed by ranking; trigger recorded in §6 |
| Consolidation nudge, at-cap refusal | No cap left to approach (§6) |
| Second data file / migration | In-memory index over the existing jsonl |
| SQLite as the store of record | The jsonl is readable, atomic, and tested. Named as the upgrade path in §6, not taken now |

## 9. Testing

New tests, alongside the existing 317 which must stay green:

- **A:** junk filter drops `[Empty response]`-shaped and sub-15-char lines;
  exact-dupe candidates are dropped; `INSTRUCTION` and `MEMORY_PREFACE`
  contain the third-person and format-closing lines.
- **B:** a query matching one fact retrieves it ahead of non-matching facts;
  pinned facts are injected even when they match nothing; never more than
  ten facts are injected; a store of ten or fewer is injected whole; an
  eleventh pin is refused by the pane; FTS
  operators in a user message do not raise; index failure falls back to
  inject-all; `load()` tolerates a missing `pinned` field.
- **C:** the noticing pass receives only messages appended since the last
  pass; the closing summary still receives the full conversation.
- **D:** `remember` succeeds past the old 950 — no branch refuses on count;
  `memory.MAX_FACTS` no longer exists; a fact over `MAX_CHARS` is still
  rejected with its message.
- **Integration:** the second system message is rebuilt between steps
  (existing test) and still carries preface + facts + closing line in order.

Deleted tests, and why each is now wrong rather than merely stale:
`test_catalog_memory.py:105` (at-cap refusal), `:184` and `:199` (forget
makes room at the cap) assert a refusal that no longer exists;
`test_memory.py:174` bounds the prompt by `MAX_FACTS * MAX_CHARS`, which is
no longer what bounds the prompt — `MAX_INJECTED` is, and criterion 4 tests
it directly.

## 10. Files touched

| File | Change |
|---|---|
| `zeroos/agent/notice.py` | INSTRUCTION rewrite; junk + dupe filters |
| `zeroos/agent/prompt.py` | MEMORY_PREFACE: pronoun line + format closing line |
| `zeroos/agent/session.py` | `_memory_messages()` calls `search()`; noticing slice bookkeeping |
| `zeroos/platform/memory.py` | Delete `MAX_FACTS`; `pinned` field tolerance; FTS index + `search()` |
| `zeroos/catalog/memory.py` | Delete the at-cap branch; `remember` docstring: third person |
| `zeroos/surface/recall.py` | Pin switch per fact row; pin count against the limit; refuse the eleventh |
| `tests/test_catalog_memory.py`, `tests/test_memory.py` | Delete the four cap tests (§9) |
| `README.md`, `docs/roadmap.md` | "Up to 950 facts" is no longer true — unlimited storage, budgeted injection |

Estimate ~200 lines including tests.

## 11. Success criteria

1. "What do you know about me?" answers in one sentence above the line, the
   list below it — the format rule survives a populated store.
2. No stored fact is first person after the instruction change (new facts;
   old ones grandfathered).
3. A candidate matching a stored fact, a bracketed placeholder, or a
   sub-15-char line is never offered.
4. With 500 synthetic facts stored, the injected memory block holds exactly
   ten facts: every pinned one, then the highest-ranked matches for the
   turn's query.
5. Per-turn noticing input is one turn's messages regardless of session
   length.
6. A pinned fact appears in the block for a query it does not match.
7. Storing 1,000 facts succeeds — no count refuses, and criterion 4 still
   holds at that size.
8. Full suite green; a store of ten or fewer facts produces the same
   injected block as v0.2.1 did.
