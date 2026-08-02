import pytest

from zeroos.catalog import apps as catalog_apps
from zeroos.catalog import system as catalog_system
from zeroos.policy import gate as gate_module


@pytest.fixture
def registry(monkeypatch, tmp_path):
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    recorded = {}
    monkeypatch.setattr(catalog_apps.platform_apps, "installed", lambda: ["Firefox", "Rhythmbox"])
    monkeypatch.setattr(catalog_apps.platform_apps, "launch", lambda n: recorded.setdefault("launched", n) or True)
    monkeypatch.setattr(catalog_system.platform_system, "read_clipboard", lambda: "clip contents")
    monkeypatch.setattr(catalog_system.platform_system, "write_clipboard", lambda t: recorded.setdefault("clip", t))
    monkeypatch.setattr(catalog_system.platform_system, "set_volume", lambda p: recorded.setdefault("volume", p))
    monkeypatch.setattr(catalog_system.platform_system, "notify", lambda t, b: recorded.setdefault("notice", (t, b)))
    gate = gate_module.Gate(lambda rows: [True] * len(rows))
    tools = {t.name: t for t in catalog_apps.bind(gate) + catalog_system.bind(gate)}
    return tools, recorded


def test_lists_installed_apps(registry):
    tools, _ = registry
    assert "Rhythmbox" in tools["list_apps"].call({})


def test_opens_an_app(registry):
    tools, recorded = registry
    tools["open_app"].call({"name": "Rhythmbox"})
    assert recorded["launched"] == "Rhythmbox"


def test_reads_the_clipboard(registry):
    tools, _ = registry
    assert "clip contents" in tools["read_clipboard"].call({})


def test_writes_the_clipboard(registry):
    tools, recorded = registry
    tools["write_clipboard"].call({"text": "hello"})
    assert recorded["clip"] == "hello"


def test_a_denied_clipboard_write_does_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    touched = []
    monkeypatch.setattr(catalog_system.platform_system, "write_clipboard", lambda t: touched.append(t))
    gate = gate_module.Gate(lambda rows: [False] * len(rows))
    tools = {t.name: t for t in catalog_system.bind(gate)}
    gate.prepare([("write_clipboard", {"text": "secret"})])
    assert tools["write_clipboard"].call({"text": "secret"}) == gate_module.DENIED_MESSAGE
    assert touched == []


@pytest.mark.parametrize("percent,expected", [(-10, 0), (0, 0), (55, 55), (100, 100), (400, 100)])
def test_volume_is_clamped(registry, percent, expected):
    tools, recorded = registry
    recorded.pop("volume", None)
    tools["set_volume"].call({"percent": percent})
    assert recorded["volume"] == expected


def test_sends_a_notification(registry):
    tools, recorded = registry
    tools["notify"].call({"title": "Done", "body": "All finished"})
    assert recorded["notice"] == ("Done", "All finished")


def test_unknown_app_reports_without_raising(registry, monkeypatch):
    tools, _ = registry
    monkeypatch.setattr(catalog_apps.platform_apps, "launch", lambda n: False)
    assert "couldn't find" in tools["open_app"].call({"name": "Nonexistent"})
