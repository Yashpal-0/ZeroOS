"""Spec §5's mounting half. Nothing here connects to anything real."""

import json
import threading

import pytest

from zeroos.mcp import config, mount
from zeroos.mcp.transport import TransportError
from zeroos.policy import gate as gate_module


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(mount, "_shutdown", False, raising=False)
    yield
    mount.close_all()


def write(servers) -> None:
    config.path().parent.mkdir(parents=True, exist_ok=True)
    config.path().write_text(json.dumps({"servers": servers}), encoding="utf-8")


class FakeLink:
    def __init__(self, tools=None, fail_on=None):
        self.tools = tools if tools is not None else [
            {"name": "read_file", "description": "Read.", "inputSchema": {"type": "object"}}
        ]
        self.fail_on = fail_on
        self.notified = []
        self.sent = []
        self.closed = False

    def send(self, method, params):
        self.sent.append((method, params))
        if method == self.fail_on:
            raise TransportError(f"boom on {method}")
        if method == "initialize":
            return {"protocolVersion": "2025-06-18"}
        if method == "tools/list":
            return {"tools": self.tools}
        return {}

    def notify(self, method, params):
        self.sent.append((method, params))
        self.notified.append(method)

    def stderr_tail(self):
        return ["a warning"]

    def close(self):
        self.closed = True


def stub_transports(monkeypatch, link):
    monkeypatch.setattr(mount, "StdioTransport", lambda command, env=None: link)
    monkeypatch.setattr(mount, "HttpTransport", lambda url, headers=None: link)


def allowing():
    return gate_module.Gate(lambda rows: [True] * len(rows))


def test_no_config_means_no_tools_and_no_status():
    mount.load(allowing())
    assert mount.tools() == []
    assert mount.status() == []


def test_a_stdio_server_mounts_its_tools(monkeypatch):
    write([{"name": "filesystem", "command": ["npx", "pkg"]}])
    stub_transports(monkeypatch, FakeLink())
    mount.load(allowing())
    assert [t.name for t in mount.tools()] == ["mcp__filesystem__read_file"]


def test_the_handshake_runs_in_order(monkeypatch):
    write([{"name": "s", "url": "https://example.test"}])
    link = FakeLink()
    stub_transports(monkeypatch, link)
    mount.load(allowing())
    assert link.sent == [
        (
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "ZeroOS", "version": "0.4.0"},
            },
        ),
        ("notifications/initialized", {}),
        ("tools/list", {}),
    ]
    assert link.notified == ["notifications/initialized"]


def test_status_reports_connected_with_a_count(monkeypatch):
    write([{"name": "s", "url": "https://example.test"}])
    stub_transports(monkeypatch, FakeLink())
    mount.load(allowing())
    record = mount.status()[0]
    assert record["name"] == "s"
    assert record["state"] == "connected"
    assert record["tools"] == 1


def test_a_failing_server_is_named_with_its_error_and_the_others_still_mount(monkeypatch):
    write([
        {"name": "broken", "url": "https://example.test"},
        {"name": "fine", "url": "https://example.test"},
    ])
    links = {"broken": FakeLink(fail_on="initialize"), "fine": FakeLink()}
    order = ["broken", "fine"]
    monkeypatch.setattr(mount, "HttpTransport", lambda url, headers=None: links[order.pop(0)])
    mount.load(allowing())
    by_name = {record["name"]: record for record in mount.status()}
    assert by_name["broken"]["state"] == "failed"
    assert "boom" in by_name["broken"]["error"]
    assert by_name["fine"]["state"] == "connected"
    assert [t.name for t in mount.tools()] == ["mcp__fine__read_file"]


def test_a_failed_handshake_closes_the_link_and_keeps_its_stderr(monkeypatch):
    write([{"name": "s", "command": ["x"]}])
    link = FakeLink(fail_on="initialize")
    stub_transports(monkeypatch, link)

    mount.load(allowing())

    assert link.closed is True
    assert mount.status()[0]["stderr"] == ["a warning"]


def test_a_failed_server_carries_its_stderr_tail(monkeypatch):
    write([{"name": "s", "command": ["x"]}])
    link = FakeLink(fail_on="tools/list")
    stub_transports(monkeypatch, link)
    mount.load(allowing())
    assert mount.status()[0]["stderr"] == ["a warning"]
    assert link.closed is True


def test_a_non_list_tools_result_mounts_as_an_empty_catalog(monkeypatch):
    write([{"name": "s", "url": "https://example.test"}])
    link = FakeLink(tools=5)
    stub_transports(monkeypatch, link)

    mount.load(allowing())

    assert mount.status()[0]["state"] == "connected"
    assert mount.status()[0]["tools"] == 0
    assert link.closed is False


def test_a_failing_stderr_tail_cannot_escape_load(monkeypatch):
    write([{"name": "s", "command": ["x"]}])
    link = FakeLink(fail_on="initialize")
    link.stderr_tail = lambda: (_ for _ in ()).throw(RuntimeError("stderr exploded"))
    stub_transports(monkeypatch, link)

    mount.load(allowing())

    assert mount.status()[0]["stderr"] == []
    assert link.closed is True


def test_a_transport_that_will_not_construct_is_reported_not_raised(monkeypatch):
    write([{"name": "s", "command": ["x"]}])

    def refuses(command, env=None):
        raise TransportError("Could not start the server: no such file")

    monkeypatch.setattr(mount, "StdioTransport", refuses)
    mount.load(allowing())
    assert mount.status()[0]["state"] == "failed"
    assert mount.tools() == []


def test_a_config_entry_skipped_by_validation_is_shown_as_failed(monkeypatch):
    write([{"name": "bad", "command": "npx -y pkg"}])
    mount.load(allowing())
    record = mount.status()[0]
    assert record["state"] == "failed"
    assert "list" in record["error"]


def test_reloading_replaces_the_previous_mount_and_closes_it(monkeypatch):
    write([{"name": "s", "url": "https://example.test"}])
    first = FakeLink()
    stub_transports(monkeypatch, first)
    mount.load(allowing())
    second = FakeLink(tools=[{"name": "other", "description": "d", "inputSchema": {}}])
    stub_transports(monkeypatch, second)
    mount.load(allowing())
    assert first.closed is True
    assert [t.name for t in mount.tools()] == ["mcp__s__other"]


def test_an_older_slow_mount_cannot_replace_a_newer_mount(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    class SlowLink(FakeLink):
        def send(self, method, params):
            if method == "initialize":
                started.set()
                if not release.wait(2):
                    raise RuntimeError("test timed out waiting for release")
            return super().send(method, params)

    old = SlowLink(tools=[{"name": "old", "description": "d", "inputSchema": {}}])
    new = FakeLink(tools=[{"name": "new", "description": "d", "inputSchema": {}}])
    configs = iter([
        ([{"name": "s", "url": "https://old.test"}], []),
        ([{"name": "s", "url": "https://new.test"}], []),
    ])
    links = iter([old, new])
    monkeypatch.setattr(mount.config, "load", lambda: next(configs))
    monkeypatch.setattr(mount, "HttpTransport", lambda url, headers=None: next(links))

    worker = threading.Thread(target=mount.load, args=(allowing(),))
    worker.start()
    assert started.wait(1)
    mount.load(allowing())
    release.set()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert [tool.name for tool in mount.tools()] == ["mcp__s__new"]
    assert new.closed is False
    assert old.closed is True


def test_close_all_prevents_an_in_flight_mount_from_reinstalling_links(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    class SlowLink(FakeLink):
        def send(self, method, params):
            if method == "initialize":
                started.set()
                if not release.wait(2):
                    raise RuntimeError("test timed out waiting for release")
            return super().send(method, params)

    link = SlowLink()
    write([{"name": "s", "url": "https://example.test"}])
    stub_transports(monkeypatch, link)

    worker = threading.Thread(target=mount.load, args=(allowing(),))
    worker.start()
    assert started.wait(1)
    mount.close_all()
    release.set()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert mount.tools() == []
    assert mount.status() == []
    assert link.closed is True


def test_the_generation_advances_on_every_load(monkeypatch):
    before = mount.generation()
    mount.load(allowing())
    assert mount.generation() == before + 1
    mount.load(allowing())
    assert mount.generation() == before + 2


def test_close_all_advances_the_generation():
    before = mount.generation()
    mount.close_all()
    assert mount.generation() == before + 1


def test_close_all_closes_every_transport_and_never_raises(monkeypatch):
    write([{"name": "s", "url": "https://example.test"}])
    link = FakeLink()
    stub_transports(monkeypatch, link)
    mount.load(allowing())
    mount.close_all()
    assert link.closed is True
    mount.close_all()


def test_load_never_raises_even_when_everything_is_wrong(monkeypatch):
    write([{"name": "s", "url": "https://example.test"}])

    def explodes(url, headers=None):
        raise RuntimeError("entirely unexpected")

    monkeypatch.setattr(mount, "HttpTransport", explodes)
    mount.load(allowing())
    assert mount.status()[0]["state"] == "failed"
