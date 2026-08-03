"""Action log. Spec section 6.

The log answers "what did it actually do", which is the first thing a
non-technical user asks when something surprises them. It records arguments
but never file contents: write_text_file's `content` and write_clipboard's
`text` ARE file contents, so they are replaced by a byte count.
"""

import json
import time
from pathlib import Path

from zeroos.platform import paths

CONTENT_ARGUMENTS = {"write_text_file": "content", "write_clipboard": "text"}
_RESULT_LIMIT = 400
_ROTATE_AT_BYTES = 5_000_000


def path() -> Path:
    return paths.data_dir() / "actions.log"


def _redact(name: str, arguments: dict) -> dict:
    content_argument = CONTENT_ARGUMENTS.get(name)
    if content_argument is None:
        return dict(arguments)
    redacted = dict(arguments)
    if content_argument in redacted:
        size = len(str(redacted[content_argument]).encode("utf-8"))
        redacted[content_argument] = f"{size} bytes"
    return redacted


def record(name: str, arguments: dict, tier: str, verdict: str, result: str) -> None:
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > _ROTATE_AT_BYTES:
        target.replace(target.with_suffix(".log.1"))
    entry = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tool": name,
        "arguments": _redact(name, arguments),
        "tier": tier,
        "verdict": verdict,
        "result": result[:_RESULT_LIMIT],
    }
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
