import pytest

from zeroos.catalog import files as catalog_files
from zeroos.policy import gate as gate_module


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    (tmp_path / "Documents").mkdir()
    (tmp_path / "Downloads").mkdir()
    return tmp_path


@pytest.fixture
def tools(home):
    """All file tools, bound to a gate that approves everything."""
    gate = gate_module.Gate(lambda rows: [True] * len(rows))
    return {tool.name: tool for tool in catalog_files.bind(gate)}, gate


def call(tools, name, **kwargs):
    """Invoke a tool the way the agent loop does: with a dictionary."""
    return tools[name].call(kwargs)


def test_writes_and_reads_a_file(tools, home):
    registry, _ = tools
    target = str(home / "Documents" / "note.txt")
    call(registry, "write_text_file", path=target, content="hello")
    assert (home / "Documents" / "note.txt").read_text() == "hello"
    assert "hello" in call(registry, "read_text_file", path=target)


def test_lists_a_folder(tools, home):
    registry, _ = tools
    (home / "Documents" / "a.txt").write_text("")
    result = call(registry, "list_folder", path=str(home / "Documents"))
    assert "a.txt" in result


def test_searches_by_name(tools, home):
    registry, _ = tools
    (home / "Downloads" / "invoice-2025.pdf").write_text("")
    result = call(registry, "search_files", query="invoice", location=str(home / "Downloads"))
    assert "invoice-2025.pdf" in result


def test_moves_a_file(tools, home):
    registry, _ = tools
    source = home / "Downloads" / "a.pdf"
    source.write_text("x")
    call(registry, "move_file", source=str(source), destination=str(home / "Documents" / "a.pdf"))
    assert not source.exists()
    assert (home / "Documents" / "a.pdf").exists()


def test_trashes_rather_than_deletes(tools, home):
    registry, _ = tools
    target = home / "Downloads" / "junk.iso"
    target.write_text("x")
    call(registry, "trash_file", path=str(target))
    assert not target.exists()


def test_creates_a_folder(tools, home):
    registry, _ = tools
    call(registry, "create_folder", path=str(home / "Documents" / "Tax 2025"))
    assert (home / "Documents" / "Tax 2025").is_dir()


def test_refuses_a_path_outside_the_sandbox(tools):
    registry, _ = tools
    assert "off limits" in call(registry, "read_text_file", path="/etc/passwd")


def test_reports_a_missing_file_without_raising(tools, home):
    registry, _ = tools
    assert "No file" in call(registry, "read_text_file", path=str(home / "Documents" / "nope.txt"))


def test_reports_an_existing_destination_without_raising(tools, home):
    registry, _ = tools
    (home / "Downloads" / "a.pdf").write_text("x")
    (home / "Documents" / "a.pdf").write_text("y")
    result = call(
        registry, "move_file",
        source=str(home / "Downloads" / "a.pdf"),
        destination=str(home / "Documents" / "a.pdf"),
    )
    assert "already there" in result


def test_a_denied_move_does_not_touch_the_filesystem(home):
    gate = gate_module.Gate(lambda rows: [False] * len(rows))
    registry = {tool.name: tool for tool in catalog_files.bind(gate)}
    source = home / "Downloads" / "a.pdf"
    source.write_text("x")
    args = {"source": str(source), "destination": str(home / "Documents" / "a.pdf")}
    gate.prepare([("move_file", args)])
    result = call(registry, "move_file", **args)
    assert result == gate_module.DENIED_MESSAGE
    assert source.exists()
    assert not (home / "Documents" / "a.pdf").exists()


def test_no_file_tool_ever_raises(tools, home):
    registry, _ = tools
    nonsense = {"path": "\x00", "source": "\x00", "destination": "\x00", "query": "x",
                "location": "\x00", "content": "x"}
    for name, tool in registry.items():
        accepted = {k: v for k, v in nonsense.items() if k in tool.input_schema["properties"]}
        assert isinstance(tool.call(accepted), str)
