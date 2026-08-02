import os
import uuid

import pytest

from zeroos.catalog import files as catalog_files
from zeroos.catalog.tool import tool
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


def _trash_dir_for(start):
    """GIO's per-volume trash: <mountpoint>/.Trash-<uid>/files/.

    Walks up from `start` to the mount root (the last ancestor sharing its
    st_dev). pyproject pins --basetemp to the repo volume so the scratch file
    sits on a real filesystem GIO can trash to.
    """
    dev = start.stat().st_dev
    mount = start
    for parent in start.parents:
        try:
            if parent.stat().st_dev != dev:
                break
        except OSError:
            break
        mount = parent
    return mount / f".Trash-{os.getuid()}" / "files"


def test_trashes_rather_than_deletes(tools, home):
    registry, _ = tools
    name = f"junk-{uuid.uuid4().hex[:8]}.iso"
    target = home / "Downloads" / name
    target.write_text("x")
    call(registry, "trash_file", path=str(target))
    assert not target.exists()
    # "gone" alone cannot tell trash from permanent delete — path.unlink()
    # would pass that assertion. The file must actually be sitting in the
    # trash, which is the product's central promise.
    assert (_trash_dir_for(home) / name).exists()


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


@pytest.mark.parametrize("name, prep, args, untouched", [
    ("trash_file",
     lambda h: (h / "Downloads" / "keep.pdf").write_text("x"),
     lambda h: {"path": str(h / "Downloads" / "keep.pdf")},
     lambda h: (h / "Downloads" / "keep.pdf").exists()),
    ("write_text_file", None,
     lambda h: {"path": str(h / "Documents" / "new.txt"), "content": "x"},
     lambda h: not (h / "Documents" / "new.txt").exists()),
    ("copy_file",
     lambda h: (h / "Downloads" / "src.pdf").write_text("x"),
     lambda h: {"source": str(h / "Downloads" / "src.pdf"),
                "destination": str(h / "Documents" / "out.pdf")},
     lambda h: (h / "Downloads" / "src.pdf").exists()
               and not (h / "Documents" / "out.pdf").exists()),
    ("create_folder", None,
     lambda h: {"path": str(h / "Documents" / "NewFolder")},
     lambda h: not (h / "Documents" / "NewFolder").exists()),
])
def test_a_denied_mutation_leaves_the_filesystem_untouched(home, name, prep, args, untouched):
    gate = gate_module.Gate(lambda rows: [False] * len(rows))
    registry = {tool.name: tool for tool in catalog_files.bind(gate)}
    if prep:
        prep(home)
    call_args = args(home)
    gate.prepare([(name, call_args)])
    assert call(registry, name, **call_args) == gate_module.DENIED_MESSAGE
    assert untouched(home), f"{name} mutated the filesystem despite a denial"


@pytest.mark.parametrize("nonsense", [
    # Bad strings: a null byte trips the path sandbox inside the function.
    {"path": "\x00", "source": "\x00", "destination": "\x00", "query": "x",
     "location": "\x00", "content": "x"},
    # Wrong types: a non-string for a str parameter never reaches the function
    # — Tool.call rejects it before invoke, so resolve()/query.lower() never
    # see a value they would choke on.
    {"path": None, "source": 42, "destination": [], "query": {},
     "location": True, "content": 3.14},
])
def test_no_file_tool_ever_raises(tools, home, nonsense):
    registry, _ = tools
    for name, tool in registry.items():
        accepted = {k: v for k, v in nonsense.items() if k in tool.input_schema["properties"]}
        assert isinstance(tool.call(accepted), str), f"{name} raised or returned non-str"


def test_a_malfunctioning_gate_does_not_escape_tool_call(home):
    # A broken consent dialog — one whose decide() raises — must not kill the
    # turn. Tool.call's backstop converts any escaping exception into a string,
    # so the agent loop always gets a safe reply.
    class RaisingGate(gate_module.Gate):
        def decide(self, name, arguments):
            raise RuntimeError("consent dialog exploded")

    gate = RaisingGate(lambda rows: [True] * len(rows))
    registry = {t.name: t for t in catalog_files.bind(gate)}
    result = call(registry, "trash_file", path=str(home / "Documents" / "x.txt"))
    assert isinstance(result, str), "a raising gate escaped Tool.call"


def test_trailing_docstring_prose_stays_in_the_description():
    # Prose after the Args: block belongs to the description the model reads,
    # not to the last argument's schema entry.
    @tool
    def sample(path: str) -> str:
        """Read a thing.

        Args:
            path: The thing.

        Only use this for text. Never for binaries.
        """
        return path

    assert "Only use this for text" in sample.description
    assert sample.input_schema["properties"]["path"]["description"] == "The thing."
