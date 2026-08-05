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
import secrets
from datetime import datetime, timezone
from pathlib import Path

from zeroos.platform import paths

# USER RULING, 2026-08-04: the store's ceiling is a share of the context
# window rather than a number picked for comfort, and the share is 250,000
# tokens. These two are the whole of that budget, so they are set from a
# measurement rather than an estimate: 950 x 1000 renders a 961,707-character
# block, and the real model reported 220,354 prompt tokens for it. Facts
# written in varied prose tokenize a little worse than the probe's repeated
# text (3.95 chars/token against 4.36), which puts the true worst case near
# 243,000 -- still inside the budget, which is why the numbers are 950 and
# 1000 rather than the 975 the arithmetic alone would allow.
#
# Raising these does not raise what a turn normally costs: the block is
# whatever is stored, and a store with nine facts in it sends nine.
MAX_FACTS = 950
MAX_CHARS = 1000

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
    return str(text).translate(_STRIP)


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
