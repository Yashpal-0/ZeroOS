"""JSON-RPC over stdio and HTTP. Spec section 4.

This module knows about framing and nothing else -- no tools, no schemas, no
consent. mount.py and remote.py are its only callers.
"""

import itertools
import json
import queue
import subprocess
import threading
import time

import httpx

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
                message = json.loads(line)
            except ValueError:
                continue  # a server that logs to stdout is noisy, not fatal
            if isinstance(message, dict):
                # A bare list/string/number/null parses fine but is not a
                # JSON-RPC frame -- .get("id") on it would raise, and a literal
                # null would be indistinguishable from the EOF sentinel below.
                self._inbox.put(message)

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
        """The reply with this id. Anything else on the wire is discarded.

        CALL_TIMEOUT bounds the whole wait, not each queue.get -- a server
        that keeps sending id-less notifications (tools/call progress is
        legitimate MCP traffic) must not be able to reset the clock and
        block forever.
        """
        deadline = time.monotonic() + CALL_TIMEOUT
        while True:
            try:
                message = self._inbox.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty:
                raise TransportError("The server took too long to answer.") from None
            if message is None:
                self._inbox.put(None)  # every later caller must see EOF too
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


class HttpTransport:
    """A remote server over Streamable HTTP.

    One POST per message. If the reply is an event stream the JSON is on the
    last `data:` line -- servers send progress notifications ahead of the
    result, and the result is the one this client is waiting for.
    """

    def __init__(self, url: str, headers: dict | None = None) -> None:
        self._url = url
        self._headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **(headers or {}),
        }
        self._session_id = None
        self._client = httpx.Client(timeout=CALL_TIMEOUT)
        self._ids = itertools.count(1)

    def send(self, method: str, params: dict) -> dict:
        request_id = next(self._ids)
        response = self._post(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        )
        # Echoed on every later request to this server, per the Streamable
        # HTTP transport. Read from the initialize reply, but taken from any
        # reply that carries one -- a server is free to rotate it.
        session_id = response.headers.get("Mcp-Session-Id")
        if session_id:
            self._session_id = session_id
        return _result_of(_body_of(response, method), method)

    def notify(self, method: str, params: dict) -> None:
        self._post({"jsonrpc": "2.0", "method": method, "params": params})

    def _post(self, message: dict):
        headers = dict(self._headers)
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        try:
            return self._client.post(self._url, json=message, headers=headers)
        except httpx.TimeoutException as error:
            raise TransportError("The server took too long to answer.") from error
        except httpx.HTTPError as error:
            raise TransportError(f"Could not reach the server: {error}") from error

    def stderr_tail(self) -> list[str]:
        """Nothing to show: a remote server's logs are the remote server's.
        Present so mount.py never has to ask which transport it is holding."""
        return []

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass


def _body_of(response, method: str) -> dict:
    content_type = response.headers.get("Content-Type", "")
    text = response.text
    if "text/event-stream" in content_type:
        payloads = [
            line[len("data:"):].strip()
            for line in text.splitlines()
            if line.startswith("data:")
        ]
        if not payloads:
            raise TransportError(f"The server sent no answer to {method}.")
        text = payloads[-1]
    try:
        parsed = json.loads(text)
    except ValueError as error:
        raise TransportError(f"The server's answer to {method} was not readable.") from error
    return parsed if isinstance(parsed, dict) else {}
