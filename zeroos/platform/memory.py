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

MAX_FACTS = 50
MAX_CHARS = 200

# Control characters that are not whitespace. Tabs and newlines survive this
# and are collapsed by the split() below; the rest are deleted, because a
# fact carrying terminal escapes is a fact meant to be read by something
# other than a human.
_STRIP = {c: None for c in range(32) if chr(c) not in " \t\n\r\v\f"} | {127: None}


def path() -> Path:
    return paths.data_dir() / "memory.jsonl"


def normalise(text: str) -> str:
    """Collapse whitespace, strip control characters. Runs before the length
    check, so the characters counted are the characters displayed."""
    return " ".join(str(text).translate(_STRIP).split())


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
    """Store a normalised fact and return its id. The caller checks the caps."""
    fact = {
        "id": secrets.token_hex(4),
        "text": text,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    _write(load() + [fact])
    return fact["id"]


def remove(fact_id: str) -> bool:
    facts = load()
    kept = [f for f in facts if f["id"] != fact_id]
    if len(kept) == len(facts):
        return False
    _write(kept)
    return True


def text_of(fact_id: str) -> str | None:
    for fact in load():
        if fact["id"] == fact_id:
            return fact["text"]
    return None


def _write(facts: list[dict]) -> None:
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    temp.write_text("".join(json.dumps(f) + "\n" for f in facts), encoding="utf-8")
    os.replace(temp, target)
