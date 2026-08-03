"""Catalog-wide contract: no tool may ever raise into the agent loop.

Belongs here rather than in a per-module test file (test_catalog_files.py,
test_catalog_openers.py, test_catalog_system.py) because it is a property of
every tool in the built catalog at once, driven off registry.build() and each
tool's own input_schema rather than any one module's specifics.
"""

import pytest

from zeroos.catalog import apps as catalog_apps
from zeroos.catalog import files as catalog_files
from zeroos.catalog import openers as catalog_openers
from zeroos.catalog import system as catalog_system
from zeroos.catalog import registry
from zeroos.policy import gate as gate_module
from zeroos.policy.tiers import PATH_ARGUMENTS

LONG_STRING = "x" * 1_000_000
_FILLER = {"string": "x", "integer": 1, "number": 1.0, "boolean": True}
_WRONG_TYPE = {"string": 12345, "integer": "not an int", "number": "not a number", "boolean": "not a bool"}


@pytest.fixture
def tools(tmp_path, monkeypatch):
    """The full sixteen-tool catalog, with every system-touching seam stubbed.

    Hostile arguments like "" resolve *inside* the sandbox (to its root), so
    file tools aren't safe to leave live here the way test_catalog_files.py
    leaves them: an empty path is a legal argument to trash_file, and a
    resolve()-then-real-trash would trash the sandbox root itself.
    """
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(catalog_apps.platform_apps, "installed", lambda: ["Firefox"])
    monkeypatch.setattr(catalog_apps.platform_apps, "launch", lambda n: True)
    monkeypatch.setattr(catalog_system.platform_system, "read_clipboard", lambda: "clip")
    monkeypatch.setattr(catalog_system.platform_system, "write_clipboard", lambda t: None)
    monkeypatch.setattr(catalog_system.platform_system, "set_volume", lambda p: None)
    monkeypatch.setattr(catalog_system.platform_system, "notify", lambda t, b: None)
    monkeypatch.setattr(catalog_openers.opener, "launch_path", lambda p: None)
    monkeypatch.setattr(catalog_openers.opener, "launch_uri", lambda u: None)
    monkeypatch.setattr(catalog_files.platform_files, "search", lambda root, query: [])
    monkeypatch.setattr(catalog_files.platform_files, "make_folder", lambda p: None)
    monkeypatch.setattr(catalog_files.platform_files, "copy", lambda s, d: None)
    monkeypatch.setattr(catalog_files.platform_files, "move", lambda s, d: None)
    monkeypatch.setattr(catalog_files.platform_files, "trash", lambda p: None)
    gate = gate_module.Gate(lambda rows: [True] * len(rows))
    return registry.build(gate)


def _hostile_calls(properties, path_shaped):
    """Argument dicts covering the brief's hostile categories, one axis at a time."""
    cases = [{}]  # missing every required argument
    if not properties:
        return cases
    cases.append({name: None for name in properties})
    cases.append({name: _WRONG_TYPE[spec["type"]] for name, spec in properties.items()})
    cases.append(
        {name: "" if spec["type"] == "string" else _FILLER[spec["type"]] for name, spec in properties.items()}
    )
    cases.append(
        {
            name: LONG_STRING if spec["type"] == "string" else _FILLER[spec["type"]]
            for name, spec in properties.items()
        }
    )
    if path_shaped:
        cases.append(
            {
                name: "\x00" if name in path_shaped else _FILLER[spec["type"]]
                for name, spec in properties.items()
            }
        )
    return cases


def test_no_tool_ever_raises_on_hostile_arguments(tools):
    # test_registry.py owns this count; asserted here so a miscount can't silently shrink what this test covers.
    assert len(tools) == 16
    for tool in tools:
        path_shaped = set(PATH_ARGUMENTS.get(tool.name, ()))
        for arguments in _hostile_calls(tool.input_schema["properties"], path_shaped):
            result = tool.call(arguments)
            assert isinstance(result, str), f"{tool.name}({arguments!r}) raised or returned {result!r}"
