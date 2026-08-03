import pytest

from zeroos.catalog import registry
from zeroos.policy import gate as gate_module
from zeroos.policy.tiers import PATH_ARGUMENTS, TIERS


@pytest.fixture
def tools(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    gate = gate_module.Gate(lambda rows: [True] * len(rows))
    return registry.build(gate)


def test_the_catalog_has_exactly_sixteen_tools(tools):
    assert len(tools) == 16


def test_every_catalog_tool_has_a_tier(tools):
    assert {t.name for t in tools} == set(TIERS)


def test_every_tiered_tool_exists_in_the_catalog(tools):
    names = {t.name for t in tools}
    for name in TIERS:
        assert name in names


def test_every_sandboxed_argument_exists_on_its_tool(tools):
    by_name = {t.name: t for t in tools}
    for name, arguments in PATH_ARGUMENTS.items():
        properties = by_name[name].input_schema["properties"]
        for argument in arguments:
            assert argument in properties, f"{name} has no argument {argument!r}"


def test_every_path_shaped_argument_is_declared_sandboxed(tools):
    """The direction that matters. PATH_ARGUMENTS is what the gate resolves and
    shows the user; an argument that takes a path but is missing from it reaches
    the filesystem unresolved and undisplayed."""
    path_shaped = {"path", "location", "source", "destination", "folder", "file"}
    for tool in tools:
        declared = set(PATH_ARGUMENTS.get(tool.name, ()))
        for argument in tool.input_schema["properties"]:
            if argument in path_shaped:
                assert argument in declared, (
                    f"{tool.name}'s {argument!r} looks like a path but is not in PATH_ARGUMENTS"
                )


def test_no_tool_name_hints_at_shell_access(tools):
    forbidden = {"shell", "exec", "command", "sudo", "delete", "remove"}
    for tool in tools:
        assert not (forbidden & set(tool.name.split("_")))


def test_every_tool_has_a_description_for_the_model(tools):
    for tool in tools:
        assert tool.description and len(tool.description) > 40
