import pytest

from zeroos.catalog.tool import tool


@tool
def demo(path: str, count: int = 1) -> str:
    """Do a thing to a file.

    Args:
        path: Where the file lives.
        count: How many times. Defaults to once.
    """
    return f"{path}x{count}"


def test_name_comes_from_the_function():
    assert demo.name == "demo"


def test_description_excludes_the_args_block():
    assert demo.description == "Do a thing to a file."


def test_schema_types_come_from_annotations():
    assert demo.input_schema["properties"]["path"]["type"] == "string"
    assert demo.input_schema["properties"]["count"]["type"] == "integer"


def test_argument_descriptions_come_from_the_docstring():
    assert demo.input_schema["properties"]["path"]["description"] == "Where the file lives."


def test_a_wrapped_argument_description_is_joined():
    assert demo.input_schema["properties"]["count"]["description"] == "How many times. Defaults to once."


def test_only_arguments_without_defaults_are_required():
    assert demo.input_schema["required"] == ["path"]


def test_schema_forbids_extra_properties():
    assert demo.input_schema["additionalProperties"] is False


def test_call_takes_a_dictionary():
    assert demo.call({"path": "a", "count": 2}) == "ax2"


def test_call_drops_keys_the_schema_does_not_declare():
    assert demo.call({"path": "a", "nonsense": True}) == "ax1"


def test_call_reports_a_missing_required_argument_without_raising():
    assert "needs path" in demo.call({})


def test_an_unannotated_argument_is_a_load_time_error():
    with pytest.raises(TypeError):

        @tool
        def broken(path):
            """No annotation on path."""
