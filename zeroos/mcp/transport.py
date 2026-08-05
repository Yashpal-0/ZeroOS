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
        # follow_redirects defaults to False in httpx -- left implicit
        # deliberately: a redirect to another host would replay the
        # Authorization header above onto it, leaking this server's
        # credential to wherever it points.
        self._client = httpx.Client(timeout=CALL_TIMEOUT)
        self._ids = itertools.count(1)

    def send(self, method: str, params: dict) -> dict:
        request_id = next(self._ids)
        text, headers, status_code = self._post(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        )
        if status_code >= 400:
            # Status only, never the body or the URL: MCP servers commonly
            # authenticate by query parameter, and this client's own config
            # accepts any URL, so an interpolated error/URL can carry a
            # token straight into the pane or a model prompt.
            raise TransportError(f"The server refused {method} ({status_code}).")
        # Echoed on every later request to this server, per the Streamable
        # HTTP transport. Read from the initialize reply, but taken from any
        # reply that carries one -- a server is free to rotate it.
        session_id = headers.get("Mcp-Session-Id")
        if session_id:
            self._session_id = session_id
        content_type = headers.get("Content-Type", "")
        return _result_of(_select_frame(text, content_type, method, request_id), method)

    def notify(self, method: str, params: dict) -> None:
        self._post({"jsonrpc": "2.0", "method": method, "params": params}, read_body=False)

    def _post(self, message: dict, read_body: bool = True) -> tuple[str, httpx.Headers, int]:
        headers = dict(self._headers)
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        # Streamed rather than a plain .post(): httpx.Timeout's read
        # component bounds each chunk, not the call, so a server dripping
        # small chunks (SSE keep-alives, slow progress notifications) can
        # hold a plain .post() open indefinitely. The loop below enforces a
        # real wall-clock deadline across the whole read, the way
        # StdioTransport._await bounds its wait.
        deadline = time.monotonic() + CALL_TIMEOUT
        try:
            with self._client.stream("POST", self._url, json=message, headers=headers) as response:
                if not read_body:
                    # A notification's reply is a status line, nothing more
                    # -- reading the body would wait on a stream a server is
                    # free to hold open, which is exactly I1's failure mode.
                    return "", response.headers, response.status_code
                chunks = []
                for chunk in response.iter_text():
                    chunks.append(chunk)
                    if time.monotonic() > deadline:
                        raise TransportError("The server took too long to answer.")
                return "".join(chunks), response.headers, response.status_code
        except httpx.TimeoutException as error:
            raise TransportError("The server took too long to answer.") from error
        except (httpx.HTTPError, httpx.InvalidURL) as error:
            # InvalidURL is not an HTTPError in httpx 0.28 -- a malformed
            # authority (typo'd port, etc.) in a hand-edited server config
            # must not escape as a bare httpx exception either.
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


def _sse_payloads(text: str) -> list[str]:
    """One entry per SSE event, with that event's `data:` lines rejoined.

    The wire format lets one event's payload span several `data:` lines
    (a pretty-printed JSON body, for instance) -- a blank line is what ends
    an event, not a `data:` line.
    """
    payloads = []
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("data:"):
            lines.append(line[len("data:"):].strip())
        elif not line and lines:
            payloads.append("\n".join(lines))
            lines = []
    if lines:
        payloads.append("\n".join(lines))
    return payloads


def _select_frame(text: str, content_type: str, method: str, request_id: int) -> dict:
    """The JSON-RPC frame answering request_id.

    MCP allows notifications interleaved with the result on the same
    stream in any order, so the answer is not "the last thing on the
    wire" -- it is the one dict frame, wherever it falls, whose id matches
    this request. Anything else (a bare array/string, a notification, a
    stale frame for an earlier id) is not the answer and is skipped rather
    than trusted.
    """
    if "text/event-stream" in content_type:
        payloads = _sse_payloads(text)
        if not payloads:
            raise TransportError(f"The server sent no answer to {method}.")
    else:
        payloads = [text]

    frames = []
    for payload in payloads:
        try:
            parsed = json.loads(payload)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            frames.append(parsed)

    for frame in reversed(frames):
        if frame.get("id") == request_id:
            return frame

    if not frames:
        raise TransportError(f"The server's answer to {method} was not readable.")
    raise TransportError(f"The server sent no answer to {method}.")
