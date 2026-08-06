"""Spec §4. JSON-RPC framing, both transports. No test spawns a real process
or opens a real connection."""

import json
import queue
import socket
import threading
import time

import pytest

from zeroos.mcp import transport


class FakeStdout:
    """A file-like the test feeds line by line. readline() blocks until fed,
    which is what the real pipe does and what the reader thread expects."""

    def __init__(self):
        self._lines = queue.Queue()

    def feed(self, obj) -> None:
        self._lines.put(json.dumps(obj) + "\n")

    def readline(self) -> str:
        return self._lines.get()

    def close(self) -> None:
        self._lines.put("")


class FakeStdin:
    def __init__(self):
        self.written = []

    def write(self, text) -> None:
        self.written.append(text)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


class FakeProcess:
    def __init__(self):
        self.stdin = FakeStdin()
        self.stdout = FakeStdout()
        self.stderr = FakeStdout()
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout=None) -> int:
        return 0

    def kill(self) -> None:
        self.terminated = True

    def poll(self):
        return None


@pytest.fixture
def child(monkeypatch):
    process = FakeProcess()
    captured = {}

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        return process

    monkeypatch.setattr(transport.subprocess, "Popen", fake_popen)
    process.captured = captured
    return process


def test_the_argv_is_list_form_through_flatpak_spawn(child):
    transport.StdioTransport(["npx", "-y", "pkg"])
    assert child.captured["argv"] == ["flatpak-spawn", "--host", "npx", "-y", "pkg"]


def test_env_entries_become_env_flags(child):
    transport.StdioTransport(["npx"], env={"NODE_ENV": "production"})
    assert child.captured["argv"] == [
        "flatpak-spawn", "--host", "--env=NODE_ENV=production", "npx"
    ]


def test_send_writes_a_json_rpc_request_and_returns_the_result(child):
    link = transport.StdioTransport(["server"])
    child.stdout.feed({"jsonrpc": "2.0", "id": 1, "result": {"tools": []}})
    assert link.send("tools/list", {}) == {"tools": []}
    request = json.loads(child.stdin.written[0])
    assert request["jsonrpc"] == "2.0"
    assert request["method"] == "tools/list"
    assert request["id"] == 1
    assert child.stdin.written[0].endswith("\n")


def test_a_json_rpc_error_becomes_a_transport_error(child):
    link = transport.StdioTransport(["server"])
    child.stdout.feed({"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "no such method"}})
    with pytest.raises(transport.TransportError) as caught:
        link.send("tools/list", {})
    assert "no such method" in str(caught.value)


def test_a_response_for_another_id_is_skipped(child):
    link = transport.StdioTransport(["server"])
    child.stdout.feed({"jsonrpc": "2.0", "id": 99, "result": {"stale": True}})
    child.stdout.feed({"jsonrpc": "2.0", "id": 1, "result": {"fresh": True}})
    assert link.send("tools/list", {}) == {"fresh": True}


def test_an_unparseable_line_is_skipped(child):
    link = transport.StdioTransport(["server"])
    child.stdout._lines.put("this is not json\n")
    child.stdout.feed({"jsonrpc": "2.0", "id": 1, "result": {}})
    assert link.send("tools/list", {}) == {}


def test_a_notification_carries_no_id_and_does_not_wait(child):
    link = transport.StdioTransport(["server"])
    link.notify("notifications/initialized", {})
    request = json.loads(child.stdin.written[0])
    assert "id" not in request
    assert request["method"] == "notifications/initialized"


def test_a_silent_server_times_out_rather_than_hanging(child, monkeypatch):
    monkeypatch.setattr(transport, "CALL_TIMEOUT", 0.1)
    link = transport.StdioTransport(["server"])
    with pytest.raises(transport.TransportError) as caught:
        link.send("tools/list", {})
    assert "too long" in str(caught.value)


def test_a_dead_child_reports_rather_than_blocking_forever(child):
    link = transport.StdioTransport(["server"])
    child.stdout.close()  # EOF
    with pytest.raises(transport.TransportError):
        link.send("tools/list", {})


def test_stderr_is_drained_and_only_the_last_twenty_lines_are_kept(child):
    link = transport.StdioTransport(["server"])
    for n in range(50):
        child.stderr._lines.put(f"line {n}\n")
    child.stdout.feed({"jsonrpc": "2.0", "id": 1, "result": {}})
    link.send("tools/list", {})
    # The drain thread's scheduling isn't guaranteed by the send() round trip
    # alone, so poll for up to a second rather than asserting immediately.
    for _ in range(100):
        if len(link.stderr_tail()) == 20:
            break
        time.sleep(0.01)
    tail = link.stderr_tail()
    assert len(tail) <= transport.STDERR_LINES
    assert tail[-1] == "line 49"


def test_a_child_that_will_not_spawn_raises_transport_error(monkeypatch):
    def missing(argv, **kwargs):
        raise FileNotFoundError("flatpak-spawn")

    monkeypatch.setattr(transport.subprocess, "Popen", missing)
    with pytest.raises(transport.TransportError):
        transport.StdioTransport(["server"])


def test_close_terminates_the_child_and_never_raises(child):
    link = transport.StdioTransport(["server"])
    link.close()
    assert child.terminated is True
    link.close()  # twice is fine


def test_a_non_object_frame_is_skipped_rather_than_crashing(child):
    link = transport.StdioTransport(["server"])
    child.stdout.feed([1, 2, 3])  # valid JSON, not a JSON-RPC frame
    child.stdout.feed({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
    assert link.send("tools/list", {}) == {"ok": True}


def test_a_literal_null_line_does_not_fake_server_death(child):
    link = transport.StdioTransport(["server"])
    child.stdout.feed(None)  # json.loads("null") is None, same as the EOF sentinel
    child.stdout.feed({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
    assert link.send("tools/list", {}) == {"ok": True}


def test_a_second_send_after_the_child_dies_reports_promptly(child, monkeypatch):
    monkeypatch.setattr(transport, "CALL_TIMEOUT", 5)
    link = transport.StdioTransport(["server"])
    child.stdout.close()  # EOF
    with pytest.raises(transport.TransportError):
        link.send("tools/list", {})
    start = time.monotonic()
    with pytest.raises(transport.TransportError) as caught:
        link.send("tools/list", {})
    assert time.monotonic() - start < 1  # not the full 5s CALL_TIMEOUT
    assert "stopped running" in str(caught.value)


def test_unmatched_notifications_do_not_extend_the_deadline(child, monkeypatch):
    monkeypatch.setattr(transport, "CALL_TIMEOUT", 0.5)
    link = transport.StdioTransport(["server"])

    def drip():
        for _ in range(6):
            time.sleep(0.1)
            child.stdout.feed({"jsonrpc": "2.0", "method": "notifications/progress", "params": {}})

    threading.Thread(target=drip, daemon=True).start()
    start = time.monotonic()
    with pytest.raises(transport.TransportError) as caught:
        link.send("tools/list", {})
    assert time.monotonic() - start < 1  # bounded by CALL_TIMEOUT, not 0.6s of chatter
    assert "too long" in str(caught.value)


class FakeStreamResponse:
    """Stands in for what httpx.Client.stream() yields. Body is exposed only
    through iter_text(), same as the real thing, so a test cannot pass by
    accident via a .text shortcut the implementation doesn't use."""

    def __init__(self, body, content_type="application/json", headers=None, status=200):
        self._chunks = [body] if isinstance(body, str) else list(body)
        self.status_code = status
        self.headers = {"Content-Type": content_type, **(headers or {})}

    def iter_text(self):
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


@pytest.fixture
def streamed(monkeypatch):
    """Capture every streamed POST and return queued responses in order."""
    calls = []
    responses = []

    def fake_stream(self, method, url, **kwargs):
        calls.append({"method": method, "url": url, **kwargs})
        return responses.pop(0)

    monkeypatch.setattr(transport.httpx.Client, "stream", fake_stream)
    return calls, responses


def test_http_send_posts_json_rpc_and_returns_the_result(streamed):
    calls, responses = streamed
    responses.append(FakeStreamResponse(json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"tools": []}})))
    link = transport.HttpTransport("https://example.test/mcp", {"Authorization": "Bearer t"})
    assert link.send("tools/list", {}) == {"tools": []}
    assert calls[0]["url"] == "https://example.test/mcp"
    assert calls[0]["headers"]["Accept"] == "application/json, text/event-stream"
    assert calls[0]["headers"]["Authorization"] == "Bearer t"
    assert calls[0]["json"]["method"] == "tools/list"


def test_a_server_sent_event_response_uses_the_matching_result_frame(streamed):
    calls, responses = streamed
    body = (
        "event: message\n"
        'data: {"jsonrpc":"2.0","id":1,"result":{"stale":true}}\n'
        "\n"
        "event: message\n"
        'data: {"jsonrpc":"2.0","id":1,"result":{"fresh":true}}\n'
        "\n"
    )
    responses.append(FakeStreamResponse(body, content_type="text/event-stream"))
    link = transport.HttpTransport("https://example.test/mcp")
    assert link.send("tools/list", {}) == {"fresh": True}


def test_id_correlation_finds_the_result_behind_a_trailing_notification(streamed):
    """I4: a notification frame arriving after the result must not shadow
    it -- MCP does not guarantee the result is the last thing on the wire."""
    calls, responses = streamed
    body = (
        "event: message\n"
        'data: {"jsonrpc":"2.0","id":1,"result":{"tools":["real"]}}\n'
        "\n"
        "event: message\n"
        'data: {"jsonrpc":"2.0","method":"notifications/progress","params":{}}\n'
        "\n"
    )
    responses.append(FakeStreamResponse(body, content_type="text/event-stream"))
    link = transport.HttpTransport("https://example.test/mcp")
    assert link.send("tools/list", {}) == {"tools": ["real"]}


def test_an_sse_stream_with_only_notifications_becomes_a_transport_error(streamed):
    calls, responses = streamed
    body = 'event: message\ndata: {"jsonrpc":"2.0","method":"notifications/progress","params":{}}\n\n'
    responses.append(FakeStreamResponse(body, content_type="text/event-stream"))
    link = transport.HttpTransport("https://example.test/mcp")
    with pytest.raises(transport.TransportError):
        link.send("tools/list", {})


def test_a_pretty_printed_sse_event_spanning_several_data_lines_still_parses(streamed):
    calls, responses = streamed
    body = (
        "event: message\n"
        "data: {\n"
        'data:   "jsonrpc": "2.0",\n'
        'data:   "id": 1,\n'
        'data:   "result": {"ok": true}\n'
        "data: }\n"
        "\n"
    )
    responses.append(FakeStreamResponse(body, content_type="text/event-stream"))
    link = transport.HttpTransport("https://example.test/mcp")
    assert link.send("tools/list", {}) == {"ok": True}


def test_the_session_id_from_initialize_is_echoed_on_later_requests(streamed):
    calls, responses = streamed
    responses.append(
        FakeStreamResponse(
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}),
            headers={"Mcp-Session-Id": "abc123"},
        )
    )
    responses.append(FakeStreamResponse(json.dumps({"jsonrpc": "2.0", "id": 2, "result": {}})))
    link = transport.HttpTransport("https://example.test/mcp")
    link.send("initialize", {})
    link.send("tools/list", {})
    assert "Mcp-Session-Id" not in calls[0]["headers"]
    assert calls[1]["headers"]["Mcp-Session-Id"] == "abc123"


def test_a_network_failure_becomes_a_transport_error(monkeypatch):
    def refuses(self, method, url, **kwargs):
        raise transport.httpx.ConnectError("refused")

    monkeypatch.setattr(transport.httpx.Client, "stream", refuses)
    link = transport.HttpTransport("https://example.test/mcp")
    with pytest.raises(transport.TransportError):
        link.send("tools/list", {})


def test_a_rejected_header_value_does_not_leak_into_the_error(monkeypatch):
    marker = "invented-placeholder"
    header = f"Bearer {marker}\n"

    def rejects(self, method, url, **kwargs):
        value = kwargs["headers"]["Authorization"].encode()
        raise transport.httpx.LocalProtocolError(f"Illegal header value {value!r}")

    monkeypatch.setattr(transport.httpx.Client, "stream", rejects)
    link = transport.HttpTransport(
        "https://example.test/mcp", {"Authorization": header}
    )
    with pytest.raises(transport.TransportError) as caught:
        link.send("tools/list", {})

    assert marker not in str(caught.value)


def test_an_http_timeout_says_so(monkeypatch):
    """Also the regression guard for the broad `except Exception` added in
    round 2: TimeoutException must still be caught by its own clause and
    keep this wording, not fall through and get relabelled "Could not reach
    the server" -- which only holds if that clause is checked first."""

    def slow(self, method, url, **kwargs):
        raise transport.httpx.TimeoutException("slow")

    monkeypatch.setattr(transport.httpx.Client, "stream", slow)
    link = transport.HttpTransport("https://example.test/mcp")
    with pytest.raises(transport.TransportError) as caught:
        link.send("tools/list", {})
    assert "too long" in str(caught.value)


def test_a_malformed_url_becomes_a_transport_error_not_a_bare_httpx_exception():
    """C1: httpx.InvalidURL is a bare Exception, not an HTTPError, in
    httpx 0.28.1 -- a typo'd port in a hand-edited server config must not
    escape as one. No mocking: URL validation fails before any I/O."""
    link = transport.HttpTransport("https://example.test:notaport/mcp", {"Authorization": "Bearer SECRET"})
    with pytest.raises(transport.TransportError) as caught:
        link.send("tools/list", {})
    assert "SECRET" not in str(caught.value)


def test_an_over_long_hostname_label_becomes_a_transport_error_too():
    """C1 residual: httpx doesn't wrap everything in HTTPError/InvalidURL --
    an over-long hostname label surfaces as a bare UnicodeEncodeError from
    the idna codec deep inside httpcore. Catching that requires a broad
    except Exception, so this is also what proves the broadening didn't
    swallow anything it shouldn't. No mocking: fails before any I/O."""
    link = transport.HttpTransport(f"http://{'a' * 300}.test/mcp", {"Authorization": "Bearer SECRET"})
    with pytest.raises(transport.TransportError) as caught:
        link.send("tools/list", {})
    assert "SECRET" not in str(caught.value)


def test_a_json_rpc_error_over_http_becomes_a_transport_error(streamed):
    _calls, responses = streamed
    responses.append(
        FakeStreamResponse(
            json.dumps({"jsonrpc": "2.0", "id": 1, "error": {"message": "unauthorised"}})
        )
    )
    link = transport.HttpTransport("https://example.test/mcp")
    with pytest.raises(transport.TransportError) as caught:
        link.send("tools/list", {})
    assert "unauthorised" in str(caught.value)


def test_an_id_null_error_frame_is_used_when_nothing_matches_the_request_id(streamed):
    """A parse/invalid-request JSON-RPC error carries "id": null, not the
    request's id, since it has no valid request to attach to -- it must
    still surface its detail rather than collapsing into the generic
    "no answer" message."""
    _calls, responses = streamed
    responses.append(
        FakeStreamResponse(
            json.dumps({"jsonrpc": "2.0", "id": None, "error": {"message": "bad request"}})
        )
    )
    link = transport.HttpTransport("https://example.test/mcp")
    with pytest.raises(transport.TransportError) as caught:
        link.send("tools/list", {})
    assert "bad request" in str(caught.value)


def test_an_unparseable_body_becomes_a_transport_error(streamed):
    _calls, responses = streamed
    responses.append(FakeStreamResponse("<html>gateway error</html>"))
    link = transport.HttpTransport("https://example.test/mcp")
    with pytest.raises(transport.TransportError):
        link.send("tools/list", {})


def test_a_non_dict_json_body_becomes_a_transport_error(streamed):
    _calls, responses = streamed
    responses.append(FakeStreamResponse(json.dumps([1, 2, 3])))
    link = transport.HttpTransport("https://example.test/mcp")
    with pytest.raises(transport.TransportError):
        link.send("tools/list", {})


def test_a_non_2xx_status_becomes_a_transport_error_without_leaking_the_url_or_body(streamed):
    """I3: a 401 with a JSON body used to fall through to _result_of and
    come back as an empty success. The fix message must also not repeat
    the query string -- MCP servers commonly authenticate that way."""
    _calls, responses = streamed
    responses.append(FakeStreamResponse(json.dumps({"detail": "invalid token"}), status=401))
    link = transport.HttpTransport("https://example.test/mcp?api_key=SECRET123")
    with pytest.raises(transport.TransportError) as caught:
        link.send("tools/list", {})
    message = str(caught.value)
    assert "401" in message
    assert "SECRET123" not in message
    assert "invalid token" not in message


def test_http_notify_against_a_non_2xx_status_becomes_a_transport_error(streamed):
    """The status check moved into _post so both callers get it -- an
    expired token must not make notify (the handshake's step 2) fail
    silently just because nothing currently reads its return value."""
    _calls, responses = streamed
    responses.append(FakeStreamResponse("", content_type="text/plain", status=401))
    link = transport.HttpTransport("https://example.test/mcp")
    with pytest.raises(transport.TransportError) as caught:
        link.notify("notifications/initialized", {})
    assert "401" in str(caught.value)


def test_http_notify_sends_a_frame_with_no_id(streamed):
    calls, responses = streamed
    responses.append(FakeStreamResponse("", content_type="text/plain", status=202))
    link = transport.HttpTransport("https://example.test/mcp")
    link.notify("notifications/initialized", {})
    assert "id" not in calls[0]["json"]


def test_http_notify_returns_without_waiting_for_the_body(monkeypatch):
    """I2: reading the body -- even to discard it -- blocks on whatever the
    server does with the connection afterward. A real socket that answers
    the headers and then holds the body open forever proves notify doesn't
    wait on it; a mock that never sends bytes at all couldn't tell us that."""
    monkeypatch.setattr(transport, "CALL_TIMEOUT", 5.0)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    stop = threading.Event()

    def serve():
        conn, _ = server.accept()
        try:
            conn.recv(65536)
            conn.sendall(b"HTTP/1.1 202 Accepted\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\n")
            stop.wait(5)  # holds the body open -- a server that never finishes it
        except OSError:
            pass
        finally:
            conn.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        link = transport.HttpTransport(f"http://127.0.0.1:{port}/mcp")
        start = time.monotonic()
        link.notify("notifications/initialized", {})
        assert time.monotonic() - start < 1  # did not wait for CALL_TIMEOUT or body close
    finally:
        stop.set()
        server.close()
        thread.join(timeout=2)
        assert not thread.is_alive()  # a stuck server thread must not pass silently


def test_a_slow_drip_is_bounded_by_call_timeout_not_left_hanging(monkeypatch):
    """I1: httpx.Timeout's read component bounds each chunk, not the call
    -- a server that keeps the connection alive with small chunks can hold
    a plain .post() open indefinitely. Proven against a real loopback
    socket, since a fast fake can't demonstrate a wall-clock bound."""
    monkeypatch.setattr(transport, "CALL_TIMEOUT", 1.0)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    stop = threading.Event()

    def serve():
        conn, _ = server.accept()
        try:
            conn.recv(65536)
            conn.sendall(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\n\r\n"
            )
            # Self-bounded: if the client's deadline check ever regresses,
            # this test must fail (send() returns normally once the server
            # gives up and closes), not hang -- there's no pytest-timeout in
            # this suite to rescue a stuck read.
            giving_up_at = time.monotonic() + 5
            while not stop.is_set() and time.monotonic() < giving_up_at:
                conn.sendall(b": keep-alive\n\n")
                stop.wait(0.3)
        except OSError:
            pass
        finally:
            conn.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        link = transport.HttpTransport(f"http://127.0.0.1:{port}/mcp")
        start = time.monotonic()
        with pytest.raises(transport.TransportError) as caught:
            link.send("tools/list", {})
        elapsed = time.monotonic() - start
        assert "too long" in str(caught.value)
        assert elapsed < 3  # bounded, not the drip running forever
    finally:
        stop.set()
        server.close()
        thread.join(timeout=2)
        assert not thread.is_alive()  # a stuck server thread must not pass silently


def test_http_has_no_stderr_and_closing_never_raises():
    link = transport.HttpTransport("https://example.test/mcp")
    assert link.stderr_tail() == []
    link.close()
    link.close()
