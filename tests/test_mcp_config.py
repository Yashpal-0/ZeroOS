"""Spec §3. The config never raises; every failure path yields a value."""

import json

import pytest

from zeroos.mcp import config


@pytest.fixture(autouse=True)
def config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


def write(data) -> None:
    config.path().parent.mkdir(parents=True, exist_ok=True)
    config.path().write_text(json.dumps(data), encoding="utf-8")


def test_no_file_means_no_servers():
    assert config.load() == ([], [])


def test_the_file_lives_beside_settings_json():
    assert config.path().name == "servers.json"
    assert config.path().parent.name == "ZeroOS"


def test_a_stdio_entry_loads():
    write({"servers": [{"name": "filesystem", "command": ["npx", "-y", "pkg"]}]})
    valid, skipped = config.load()
    assert skipped == []
    assert valid[0]["name"] == "filesystem"
    assert valid[0]["command"] == ["npx", "-y", "pkg"]


def test_an_http_entry_loads():
    write({"servers": [{"name": "linear", "url": "https://example.test/mcp"}]})
    valid, _ = config.load()
    assert valid[0]["url"] == "https://example.test/mcp"


def test_unparseable_json_yields_empty():
    config.path().parent.mkdir(parents=True, exist_ok=True)
    config.path().write_text("{not json", encoding="utf-8")
    assert config.load() == ([], [])


def test_an_unreadable_file_yields_empty(monkeypatch):
    write({"servers": []})
    monkeypatch.setattr(
        type(config.path()), "read_text", lambda *a, **k: (_ for _ in ()).throw(OSError("nope"))
    )
    assert config.load() == ([], [])


def test_a_top_level_list_rather_than_an_object_yields_empty():
    write([{"name": "x", "url": "https://example.test"}])
    assert config.load() == ([], [])


def test_a_non_list_servers_key_yields_empty():
    write({"servers": "filesystem"})
    assert config.load() == ([], [])


def test_a_command_that_is_a_string_is_skipped():
    """Spec section 3: a list, never a string. A string would have to be split
    by something, and the something would be a shell."""
    write({"servers": [{"name": "bad", "command": "npx -y pkg"}]})
    valid, skipped = config.load()
    assert valid == []
    assert skipped[0]["name"] == "bad"
    assert "list" in skipped[0]["reason"]


def test_an_entry_with_both_command_and_url_is_skipped():
    write({"servers": [{"name": "both", "command": ["x"], "url": "https://example.test"}]})
    valid, skipped = config.load()
    assert valid == []
    assert len(skipped) == 1


def test_an_entry_with_neither_is_skipped():
    write({"servers": [{"name": "neither"}]})
    assert config.load()[0] == []


@pytest.mark.parametrize(
    "name", ["Filesystem", "file_system", "file system", "", "a__b", "café", "good\n", "good\r"]
)
def test_a_bad_name_is_skipped(name):
    """A name containing __ would let two servers produce one tool name."""
    write({"servers": [{"name": name, "url": "https://example.test"}]})
    valid, skipped = config.load()
    assert valid == []
    assert len(skipped) == 1


def test_a_missing_name_is_skipped_and_still_named_in_the_report():
    write({"servers": [{"url": "https://example.test"}]})
    _valid, skipped = config.load()
    assert skipped[0]["name"] == "(unnamed)"


def test_a_non_dict_entry_is_skipped_and_the_rest_load():
    write({"servers": ["nonsense", {"name": "good", "url": "https://example.test"}]})
    valid, skipped = config.load()
    assert [entry["name"] for entry in valid] == ["good"]
    assert len(skipped) == 1


def test_env_and_headers_survive():
    write({"servers": [
        {"name": "a", "command": ["x"], "env": {"NODE_ENV": "production"}},
        {"name": "b", "url": "https://example.test", "headers": {"Authorization": "Bearer t"}},
    ]})
    valid, _ = config.load()
    assert valid[0]["env"] == {"NODE_ENV": "production"}
    assert valid[1]["headers"] == {"Authorization": "Bearer t"}


def test_a_non_dict_env_is_dropped_rather_than_skipping_the_entry():
    write({"servers": [{"name": "a", "command": ["x"], "env": ["NODE_ENV=production"]}]})
    valid, _ = config.load()
    assert valid[0]["env"] == {}


def test_a_command_with_non_string_elements_is_skipped():
    write({"servers": [{"name": "a", "command": ["npx", 7]}]})
    assert config.load()[0] == []


def test_a_deeply_nested_file_is_rejected_without_raising():
    nested = "[" * (config.MAX_DEPTH + 1) + "]" * (config.MAX_DEPTH + 1)
    config.path().parent.mkdir(parents=True, exist_ok=True)
    config.path().write_text(nested, encoding="utf-8")
    assert config.load() == ([], [])


def test_a_file_nested_well_under_the_limit_still_loads():
    write({"servers": [{"name": "a", "url": "https://example.test", "headers": {"x": "y"}}]})
    valid, skipped = config.load()
    assert skipped == []
    assert valid[0]["name"] == "a"


def test_duplicate_names_the_first_wins_and_the_second_is_skipped():
    write({"servers": [
        {"name": "dup", "url": "https://example.test/a"},
        {"name": "dup", "url": "https://example.test/b"},
    ]})
    valid, skipped = config.load()
    assert [entry["name"] for entry in valid] == ["dup"]
    assert valid[0]["url"] == "https://example.test/a"
    assert len(skipped) == 1
    assert "duplicate" in skipped[0]["reason"]


def test_save_round_trips():
    assert config.save([{"name": "a", "url": "https://example.test"}]) is True
    valid, _ = config.load()
    assert valid[0]["name"] == "a"


def test_save_leaves_no_temp_file_behind():
    config.save([{"name": "a", "url": "https://example.test"}])
    assert [p.name for p in config.path().parent.iterdir()] == ["servers.json"]


def test_save_returns_false_rather_than_raising(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "blocked"))
    (tmp_path / "blocked").write_text("this is a file, not a directory")
    assert config.save([{"name": "a", "url": "https://example.test"}]) is False
