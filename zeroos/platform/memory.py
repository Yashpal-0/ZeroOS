"""The fact store. Spec §3.

Lives in data_dir(), which the path sandbox already denies, so the model
cannot reach this file through read_text_file or write_text_file. The two
catalog functions in catalog/memory.py are the only write route, and both
are confirm-tier.

Nothing here raises into the agent loop. Caps are checked by the caller,
which has a string to return; add() assumes the check has happened.

This is the bottom layer: facts and a file, no prompt text. session.py
assembles the injected block from prompt.MEMORY_PREFACE and load(), which
is what lets policy/describe.py read facts without importing the agent.
"""

import json
import os
import re
import secrets
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from zeroos.platform import paths

# One fact, not the count. This is what makes "ten injected facts" a bounded
# number of characters, and what keeps a fact readable in the approval dialog
# row the user ticks -- the v0.2 acceptance walk found an oversized row running
# off the edge of the dialog.
MAX_CHARS = 1000

# What the model is told, per model call. Storage is unlimited; this is the
# only limit. A count rather than a character budget because MAX_CHARS already
# bounds a fact at 1000, so ten facts is at most 10,000 characters (~2,500
# tokens) whatever they say -- a second budget would bound something already
# bounded. Also the pin ceiling: pins fill these slots first, so recall.py
# refuses the eleventh rather than letting injection drop one silently.
MAX_INJECTED = 10

# Control characters that are not whitespace. Tabs and newlines survive this
# and are collapsed by the split() below; the rest are deleted, because a
# fact carrying terminal escapes is a fact meant to be read by something
# other than a human.
_STRIP = {c: None for c in range(32) if chr(c) not in " \t\n\r\v\f"} | {127: None}


def path() -> Path:
    return paths.data_dir() / "memory.jsonl"


def strip_control(text: str) -> str:
    """Delete control characters, leave whitespace alone.

    normalise() collapses whitespace as well; callers that must preserve
    line structure -- the run_command consent row, spec section 6 -- take
    this half on its own. A command that reads as one line in the dialog
    but runs as three is a row that lies.
    """
    return "".join(
        character
        for character in str(text).translate(_STRIP)
        if unicodedata.category(character) != "Cf"
    )


def normalise(text: str) -> str:
    """Collapse whitespace, strip control characters. Runs before the length
    check, so the characters counted are the characters displayed."""
    return " ".join(strip_control(text).split())


def load() -> list[dict]:
    try:
        raw = path().read_text(encoding="utf-8")
    except OSError:
        return []
    facts = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            fact = json.loads(line)
        except ValueError:
            continue
        if isinstance(fact, dict) and isinstance(fact.get("id"), str) and isinstance(fact.get("text"), str):
            facts.append(fact)
    return facts


def add(text: str) -> str:
    """Store a normalised fact and return its id. The caller checks the caps.
    Returns empty string if the write fails."""
    fact = {
        "id": secrets.token_hex(4),
        "text": text,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if not _write(load() + [fact]):
        return ""
    return fact["id"]


def remove(fact_id: str) -> bool:
    facts = load()
    kept = [f for f in facts if f["id"] != fact_id]
    if len(kept) == len(facts):
        return False
    return _write(kept)


def text_of(fact_id: str) -> str | None:
    for fact in load():
        if fact["id"] == fact_id:
            return fact["text"]
    return None


_WORD = re.compile(r"\w+")


def _match_query(text: str) -> str:
    """An FTS5 MATCH expression built from arbitrary user text.

    Word runs only, each one quoted. FTS5 operators (AND, OR, NOT, NEAR, *,
    ^, ") cannot survive that: a word like AND comes back inside quotes, where
    FTS5 reads it as a literal rather than syntax. The user's message is data
    here, exactly as a file's contents are data everywhere else in this app.
    """
    return " OR ".join(f'"{word}"' for word in _WORD.findall(text))


def _ranked(facts: list[dict], query: str, limit: int) -> list[dict]:
    """The best `limit` matches for the query, best first. Never raises.

    The index is built here and dropped when this returns. At a few thousand
    rows that is milliseconds, and it buys the property that matters: search
    is a pure function of the store, so a fact approved mid-turn is findable
    on the next model call with nothing to invalidate.

    bm25() returns a negative score and a better match is more negative, so
    plain ascending ORDER BY is best-first.

    ponytail: rebuilt per search. A session-scoped index with explicit
    invalidation only if profiling ever asks for it.
    """
    match = _match_query(query)
    if not match or limit <= 0:
        return []
    try:
        db = sqlite3.connect(":memory:")
        db.execute("CREATE VIRTUAL TABLE facts USING fts5(text)")
        db.executemany(
            "INSERT INTO facts(rowid, text) VALUES (?, ?)",
            [(n, fact["text"]) for n, fact in enumerate(facts)],
        )
        rows = db.execute(
            "SELECT rowid FROM facts WHERE facts MATCH ? ORDER BY bm25(facts) LIMIT ?",
            (match, limit),
        ).fetchall()
        db.close()
    except sqlite3.Error:
        # Every caller degrades rather than fails: selection carries on with
        # pinned and recent facts. Nothing here reaches the agent loop.
        return []
    return [facts[row[0]] for row in rows]


def search(query: str, limit: int = MAX_INJECTED) -> list[dict]:
    """The facts to put in front of the model this turn, at most `limit`.

    Three tiers, in injection order:

    1. Pinned, in storage order -- the user's explicit choice, which must
       never depend on matching the query.
    2. The best BM25 matches for the query.
    3. The most recent of whatever is left.

    Tier 3 is load-bearing. Measured against the real store on 2026-08-05,
    "What do you know about me?" matches no fact at all -- none of its words
    appears in one -- so a pure-retrieval block would be empty for exactly the
    question memory exists to answer. It also means a store of `limit` or
    fewer facts comes back whole, with no threshold and no special case.

    Never raises: a ranking failure loses tier 2 and keeps the other two.
    """
    facts = load()
    chosen = [fact for fact in facts if fact.get("pinned")][:limit]
    taken = {fact["id"] for fact in chosen}
    rest = [fact for fact in facts if fact["id"] not in taken]
    for fact in _ranked(rest, query, limit - len(chosen)) + list(reversed(rest)):
        if len(chosen) >= limit:
            break
        if fact["id"] not in taken:
            chosen.append(fact)
            taken.add(fact["id"])
    return chosen


def set_pinned(fact_id: str, pinned: bool) -> bool:
    """Pin or unpin one fact. False if the id is unknown or the write failed.

    Only surface/recall.py calls this. Pinning is a consent decision, like
    deletion, so no catalog tool exposes it and the model cannot reach it.
    """
    facts = load()
    for fact in facts:
        if fact["id"] == fact_id:
            fact["pinned"] = pinned
            return _write(facts)
    return False


def _write(facts: list[dict]) -> bool:
    """Write facts to disk atomically. Returns True on success, False on any
    OSError (permission denied, disk full, cross-device link, etc). Cleans up
    temp files on failure."""
    try:
        target = path()
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + ".tmp")
        temp.write_text("".join(json.dumps(f) + "\n" for f in facts), encoding="utf-8")
        os.replace(temp, target)
        return True
    except OSError:
        # Best-effort cleanup of temp file if it exists
        try:
            temp.unlink()
        except (OSError, NameError):
            pass
        return False
