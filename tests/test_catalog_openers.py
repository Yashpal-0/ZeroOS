import pytest

from zeroos.catalog import openers
from zeroos.policy import gate as gate_module


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    (tmp_path / "Downloads").mkdir()
    return tmp_path


@pytest.fixture
def registry(home, monkeypatch):
    """Openers bound to an approve-all gate, with the actual launch stubbed."""
    launched = []
    monkeypatch.setattr(openers.opener, "launch_path", lambda p: launched.append(("path", p)))
    monkeypatch.setattr(openers.opener, "launch_uri", lambda u: launched.append(("uri", u)))
    gate = gate_module.Gate(lambda rows: [True] * len(rows))
    return {tool.name: tool for tool in openers.bind(gate)}, launched


def test_opens_an_ordinary_document(registry, home):
    tools, launched = registry
    target = home / "Downloads" / "report.pdf"
    target.write_text("x")
    tools["open_path"].call({"path": str(target)})
    assert launched == [("path", target)]


def test_opens_a_folder(registry, home):
    tools, launched = registry
    tools["open_path"].call({"path": str(home / "Downloads")})
    assert launched == [("path", home / "Downloads")]


def test_refuses_a_desktop_entry(registry, home):
    tools, launched = registry
    target = home / "Downloads" / "trap.desktop"
    target.write_text("[Desktop Entry]")
    result = tools["open_path"].call({"path": str(target)})
    assert "documents and folders" in result
    assert launched == []


def test_refuses_an_executable_file(registry, home):
    tools, launched = registry
    target = home / "Downloads" / "installer"
    target.write_text("#!/bin/sh\n")
    target.chmod(0o755)
    result = tools["open_path"].call({"path": str(target)})
    assert "documents and folders" in result
    assert launched == []


@pytest.mark.parametrize("suffix", [".sh", ".AppImage", ".run", ".py"])
def test_refuses_known_script_suffixes_even_without_the_exec_bit(registry, home, suffix):
    tools, launched = registry
    target = home / "Downloads" / f"thing{suffix}"
    target.write_text("x")
    result = tools["open_path"].call({"path": str(target)})
    assert "documents and folders" in result
    assert launched == []


def test_refuses_a_path_outside_the_sandbox(registry):
    tools, launched = registry
    assert "off limits" in tools["open_path"].call({"path": "/etc/passwd"})
    assert launched == []


def test_opens_an_https_url(registry):
    tools, launched = registry
    tools["open_url"].call({"url": "https://example.com/page"})
    assert launched == [("uri", "https://example.com/page")]


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "javascript:alert(1)", "ms-msdt:/id", "steam://run/1", "data:text/html,x"],
)
def test_refuses_every_scheme_except_http_and_https(registry, url):
    tools, launched = registry
    result = tools["open_url"].call({"url": url})
    assert "web addresses" in result
    assert launched == []


def test_openers_never_raise(registry):
    tools, _ = registry
    assert isinstance(tools["open_path"].call({"path": "\x00"}), str)
    assert isinstance(tools["open_url"].call({"url": ""}), str)
