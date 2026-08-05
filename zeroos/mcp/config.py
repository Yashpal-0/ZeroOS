"""MCP server configuration. Spec section 3.

Lives beside settings.json in paths.config_dir(), which sandbox.denied_roots()
already covers -- so no path tool the model can call can reach it. That matters
more here than it did for settings: a model that could write servers.json could
mount a server that spawns anything, and the mount would take effect without
any dialog on the next session. This is the most privileged file on disk.

Nothing in here raises. A malformed config must not stop the application from
starting, so every failure resolves to an empty server list, exactly as
settings._load() does.
"""

import json
import os
import re
from pathlib import Path

from zeroos.platform import paths

NAME_PATTERN = re.compile(r"^[a-z0-9-]+$")

# A JSON parser recurses once per nesting level. A ~200KB file nested 50,000
# levels deep blows the C stack before json.loads ever returns, and a caught
# RecursionError can leave the interpreter's stack in a state better not
# built on -- so depth is checked before the parse is attempted, not after.
# A real servers.json nests three deep; nothing legitimate approaches 100.
MAX_DEPTH = 100


def _too_deep(text: str) -> bool:
    """True if brackets in text ever nest past MAX_DEPTH.

    This is a character scan, not a parse: it does not know about string
    literals, so a header value containing more than MAX_DEPTH unescaped
    '[' or '{' characters would be rejected too. That is fine -- rejecting
    such a file with a clear reason is the correct outcome either way.
    """
    depth = 0
    for char in text:
        if char in "[{":
            depth += 1
            if depth > MAX_DEPTH:
                return True
        elif char in "]}":
            depth -= 1
    return False


def path() -> Path:
    return paths.config_dir() / "servers.json"


def load() -> tuple[list[dict], list[dict]]:
    """Every valid entry, and every skipped one with the reason why.

    The skipped half exists so the pane can say what is wrong with an entry.
    A config the user edited by hand and got subtly wrong is the ordinary
    case, and silently dropping it leaves them with a server that never
    appears and no way to find out why.
    """
    try:
        text = path().read_text(encoding="utf-8")
        if _too_deep(text):
            return [], []
        data = json.loads(text)
    except (OSError, ValueError, RecursionError):
        return [], []
    if not isinstance(data, dict):
        return [], []
    entries = data.get("servers")
    if not isinstance(entries, list):
        return [], []

    valid: list[dict] = []
    skipped: list[dict] = []
    seen_names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            skipped.append({"name": "(unnamed)", "reason": "not an object"})
            continue
        reason = _rejection(entry)
        if not reason and entry["name"] in seen_names:
            # First occurrence wins: the least surprising rule for a file a
            # user edited by hand, and it is what keeps two servers from
            # producing tool names that collide as mcp__<name>__<tool>.
            reason = "duplicate name; a server named this already appears earlier"
        if reason:
            name = entry.get("name")
            skipped.append(
                {"name": name if isinstance(name, str) and name else "(unnamed)", "reason": reason}
            )
            continue
        seen_names.add(entry["name"])
        valid.append(_clean(entry))
    return valid, skipped


def _rejection(entry: dict) -> str:
    """The reason this entry cannot be used, or "" if it can."""
    name = entry.get("name")
    if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
        # fullmatch, not match: "$" alone matches just before a trailing "\n",
        # which would let a name like "good\n" slip through.
        # Load-bearing, not tidiness: name becomes the middle segment of
        # mcp__<server>__<tool>, which is the string tier_of prefix-matches
        # and the string the consent row displays. A name containing __ would
        # let two different servers produce one tool name.
        return "name must be lowercase letters, digits and hyphens"

    has_command = "command" in entry
    has_url = "url" in entry
    if has_command == has_url:
        return "needs exactly one of command and url"

    if has_command:
        command = entry["command"]
        if not isinstance(command, list) or not command:
            return "command must be a non-empty list, never a string"
        if not all(isinstance(part, str) for part in command):
            return "every part of command must be text"
    else:
        if not isinstance(entry["url"], str) or not entry["url"]:
            return "url must be text"
    return ""


def _clean(entry: dict) -> dict:
    """The entry with only the fields this application reads."""
    cleaned: dict = {"name": entry["name"]}
    if "command" in entry:
        cleaned["command"] = list(entry["command"])
        cleaned["env"] = _string_map(entry.get("env"))
    else:
        cleaned["url"] = entry["url"]
        cleaned["headers"] = _string_map(entry.get("headers"))
    return cleaned


def _string_map(value) -> dict:
    if not isinstance(value, dict):
        return {}
    return {k: str(v) for k, v in value.items() if isinstance(k, str)}


def save(servers: list[dict]) -> bool:
    """Atomic write, matching settings._save(). False rather than an exception.

    The pane is the only caller, and a failed write there should leave the
    dialog standing with the old list rather than taking the window down.
    """
    target = path()
    temp = target.with_name(target.name + ".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp.write_text(json.dumps({"servers": servers}, indent=2), encoding="utf-8")
        os.replace(temp, target)
    except OSError:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    return True
