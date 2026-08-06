"""Connecting every configured server. Spec section 5.

load() must run on a worker thread, never on the GTK main thread. A dead
remote server costs the 120-second call timeout of section 4, and on the main
thread that is 120 seconds of no window at all. window.py presents immediately
with builtins alone and calls this from a thread.

Module-level state rather than an object: session.py, window.py and recall.py
all need the same mounted set, and threading one instance through three layers
buys nothing over a lock.
"""

import threading

from zeroos.mcp import config, remote
from zeroos.mcp.transport import HttpTransport, StdioTransport, TransportError

PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "ZeroOS", "version": "0.4.0"}

_lock = threading.Lock()
_tools: list = []
_status: list[dict] = []
_links: list = []
_generation = 0
_epoch = 0
_shutdown = False


def load(gate) -> None:
    """Connect everything in servers.json. Never raises.

    A server that fails is named in the pane with its error, not silently
    dropped, and the application starts anyway.
    """
    global _epoch
    with _lock:
        _epoch += 1
        epoch = _epoch

    valid, skipped = config.load()

    tools: list = []
    status: list[dict] = [
        {"name": entry["name"], "state": "failed", "tools": 0, "error": entry["reason"], "stderr": []}
        for entry in skipped
    ]
    links: list = []

    for entry in valid:
        link = None
        try:
            link = _connect(entry)
            _handshake(link)
            advertised = link.send("tools/list", {}).get("tools") or []
            if not isinstance(advertised, list):
                advertised = []
            mounted = remote.build(entry["name"], link, advertised, gate)
            tools.extend(mounted)
            links.append(link)
            status.append(
                {"name": entry["name"], "state": "connected", "tools": len(mounted),
                 "error": "", "stderr": []}
            )
        except TransportError as error:
            status.append(_failure(entry["name"], str(error), link))
            if link is not None:
                _close(link)
        except Exception as error:
            # Nothing about a misbehaving server may reach the caller: load()
            # runs at startup and from the pane, and both would take the window
            # with them.
            status.append(_failure(entry["name"], f"That didn't work — {error}", link))
            if link is not None:
                _close(link)

    _replace(tools, status, links, epoch)


def _connect(entry: dict):
    return (
        StdioTransport(entry["command"], entry.get("env"))
        if "command" in entry
        else HttpTransport(entry["url"], entry.get("headers"))
    )


def _handshake(link) -> None:
    link.send(
        "initialize",
        {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": CLIENT_INFO},
    )
    link.notify("notifications/initialized", {})


def _failure(name: str, error: str, link) -> dict:
    try:
        stderr = link.stderr_tail() if link is not None else []
    except Exception:
        stderr = []
    return {
        "name": name,
        "state": "failed",
        "tools": 0,
        "error": error,
        # The pane shows this beneath a failed stdio server. It is usually the
        # only place the real reason appears -- "command not found" arrives on
        # stderr, not as a protocol error.
        "stderr": stderr,
    }


def _replace(tools: list, status: list, links: list, epoch: int) -> None:
    global _tools, _status, _links, _generation
    with _lock:
        if _shutdown or epoch != _epoch:
            previous = links
        else:
            previous, _links = _links, links
            _tools, _status = tools, status
            _generation += 1
    for link in previous:
        _close(link)


def tools() -> list:
    with _lock:
        return list(_tools)


def status() -> list[dict]:
    with _lock:
        return [dict(record) for record in _status]


def generation() -> int:
    """Bumped by every completed load(). session.py compares it at the start of
    a turn -- never mid-turn, where a rebuild would race the step loop."""
    with _lock:
        return _generation


def close_all() -> None:
    global _tools, _status, _links, _generation, _shutdown
    with _lock:
        previous, _links = _links, []
        _tools, _status = [], []
        _generation += 1
        _shutdown = True
    for link in previous:
        _close(link)


def _close(link) -> None:
    try:
        link.close()
    except Exception:
        pass
