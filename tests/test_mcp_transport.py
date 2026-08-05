"""Spec §4. JSON-RPC framing, both transports. No test spawns a real process
or opens a real connection."""

import json
import queue
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
