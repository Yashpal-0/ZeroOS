"""Past turns. Spec §9.

Persisted so the conversation survives a restart, displayed in the recall
pane, and never read back into a prompt. The only importer of this module
is surface/recall.py, plus the one line in session.py that writes to it.

What is stored is what the window showed: the user's text and the reply.
Not session._messages, which is full of empty assistant content and tool
results.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from zeroos.platform import paths

MAX_TURNS = 500


def path() -> Path:
    return paths.data_dir() / "history.jsonl"


def load() -> list[dict]:
    try:
        raw = path().read_text(encoding="utf-8")
    except OSError:
        return []
    turns = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            turn = json.loads(line)
        except ValueError:
            continue
        if isinstance(turn, dict) and "you" in turn and "zeroos" in turn:
            turns.append(turn)
    return turns


def append(you: str, zeroos: str) -> None:
    turn = {
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "you": you,
        "zeroos": zeroos,
    }
    # A failed persistence is benign; an exception in the loop is not.
    _write((load() + [turn])[-MAX_TURNS:])


def clear() -> None:
    _write([])


def _write(turns: list[dict]) -> bool:
    """Write turns to disk atomically. Returns True on success, False on any
    OSError (permission denied, disk full, cross-device link, etc). Cleans up
    temp files on failure. Never raises into the agent loop."""
    try:
        target = path()
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + ".tmp")
        temp.write_text("".join(json.dumps(t) + "\n" for t in turns), encoding="utf-8")
        os.replace(temp, target)
        return True
    except OSError:
        try:
            temp.unlink()
        except (OSError, NameError):
            pass
        return False
