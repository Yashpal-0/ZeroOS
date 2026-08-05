"""JSON-RPC over stdio and HTTP. Spec section 4.

This module knows about framing and nothing else -- no tools, no schemas, no
consent. mount.py and remote.py are its only callers.
"""

import itertools
import json
import queue
import subprocess
import threading

CALL_TIMEOUT = 120
STDERR_LINES = 20


class TransportError(Exception):
    """Something went wrong talking to a server.

    The message is read by two audiences: the pane, where it appears beneath a
    failed server, and the model, where RemoteTool.call turns it into the tool
    result. Both want a sentence, not a traceback.
    """


class StdioTransport:
    """A server spawned on the host and spoken to over its pipes.

    The Flatpak has no node, no npx, no uvx, and no way to get them, so the
    stdio MCP ecosystem is only reachable through flatpak-spawn --host. List
    form throughout: nothing in a config value is interpreted by a shell.
    """

    def __init__(self, command: list[str], env: dict | None = None) -> None:
        argv = ["flatpak-spawn", "--host"]
        for key, value in (env or {}).items():
            argv.append(f"--env={key}={value}")
        argv += list(command)
        try:
            self._process = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except (OSError, ValueError) as error:
            raise TransportError(f"Could not start the server: {error}") from error

        self._inbox: queue.Queue = queue.Queue()
        self._stderr: list[str] = []
        self._stderr_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._ids = itertools.count(1)
        self._closed = False

        threading.Thread(target=self._read_stdout, daemon=True).start()
        # An undrained pipe fills and deadlocks the child, so this thread runs
        # whether or not anyone ever looks at the output. Past the last
        # STDERR_LINES lines it is discarded: it does not go to agent/log.py,
        # which answers "what did ZeroOS do" for a non-technical user and
        # rotates on a size budget -- a chatty server would push the user's own
        # history out of it. A server's debug output can also carry the
        # server's own credentials. It never enters a model prompt.
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self) -> None:
        while True:
            try:
                line = self._process.stdout.readline()
            except (OSError, ValueError):
                line = ""
            if not line:
                self._inbox.put(None)  # EOF: the child is gone
                return
            try:
                self._inbox.put(json.loads(line))
            except ValueError:
                continue  # a server that logs to stdout is noisy, not fatal

    def _read_stderr(self) -> None:
        while True:
            try:
                line = self._process.stderr.readline()
            except (OSError, ValueError):
                return
            if not line:
                return
            with self._stderr_lock:
                self._stderr.append(line.rstrip("\n"))
                del self._stderr[:-STDERR_LINES]

    def stderr_tail(self) -> list[str]:
        with self._stderr_lock:
            return list(self._stderr)

    def send(self, method: str, params: dict) -> dict:
        with self._send_lock:
            request_id = next(self._ids)
            self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
            return _result_of(self._await(request_id), method)

    def notify(self, method: str, params: dict) -> None:
        """No id, no response expected -- the MCP handshake's step 2."""
        with self._send_lock:
            self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def _write(self, message: dict) -> None:
        try:
            self._process.stdin.write(json.dumps(message) + "\n")
            self._process.stdin.flush()
        except (OSError, ValueError) as error:
            raise TransportError(f"The server stopped listening: {error}") from error

    def _await(self, request_id: int) -> dict:
        """The reply with this id. Anything else on the wire is discarded."""
        while True:
            try:
                message = self._inbox.get(timeout=CALL_TIMEOUT)
            except queue.Empty:
                raise TransportError("The server took too long to answer.") from None
            if message is None:
                raise TransportError("The server stopped running.")
            if message.get("id") == request_id:
                return message

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for shut in (self._process.terminate, self._process.kill):
            try:
                shut()
                self._process.wait(timeout=5)
                return
            except Exception:
                continue


def _result_of(message: dict, method: str) -> dict:
    error = message.get("error")
    if error:
        detail = error.get("message", "no detail") if isinstance(error, dict) else str(error)
        raise TransportError(f"The server refused {method}: {detail}")
    result = message.get("result")
    return result if isinstance(result, dict) else {}
