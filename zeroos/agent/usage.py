"""One line per session. Spec §9.

Separate from actions.log because that file answers one question — what did
ZeroOS do to my computer — and it answers it faster if every line means the
same thing.

Counts and timestamps only. No message content, no fact text, no filenames.
If you are about to add a field here, check that it is a number.
"""

from datetime import datetime, timezone
from pathlib import Path

from zeroos.platform import paths


def path() -> Path:
    return paths.data_dir() / "usage.log"


def record(started: datetime, turns: int, actions: int, declined: int) -> None:
    """Never raises. A failure to record usage must not take the app down on
    the way out."""
    ended = datetime.now(timezone.utc)
    line = (
        f"{_stamp(started)} ended={_stamp(ended)} "
        f"turns={turns} actions={actions} declined={declined}\n"
    )
    try:
        _append(line)
    except OSError:
        pass


def _append(line: str) -> None:
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(line)


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")
