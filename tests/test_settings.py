"""Spec §8. A missing or broken settings file must resolve to v0.1's behaviour."""

import json

import pytest

from zeroos.platform import settings


@pytest.fixture(autouse=True)
def config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


def test_no_settings_file_means_sir():
    assert settings.address() == "sir"


def test_set_and_read_back():
    settings.set_address("maam")
    assert settings.address() == "maam"


def test_none_is_a_valid_choice():
    settings.set_address("none")
    assert settings.address() == "none"


def test_unrecognised_value_falls_back_to_sir():
    settings.path().parent.mkdir(parents=True, exist_ok=True)
    settings.path().write_text(json.dumps({"address": "your majesty"}), encoding="utf-8")
    assert settings.address() == "sir"


def test_corrupt_file_falls_back_to_sir():
    settings.path().parent.mkdir(parents=True, exist_ok=True)
    settings.path().write_text("{not json", encoding="utf-8")
    assert settings.address() == "sir"


def test_file_holding_a_list_falls_back_to_sir():
    settings.path().parent.mkdir(parents=True, exist_ok=True)
    settings.path().write_text("[]", encoding="utf-8")
    assert settings.address() == "sir"


def test_set_address_rejects_an_unknown_value():
    with pytest.raises(ValueError):
        settings.set_address("your majesty")


def test_settings_live_under_the_config_dir(config_home):
    assert str(settings.path()).startswith(str(config_home))


def test_write_leaves_no_temp_file_behind():
    settings.set_address("maam")
    assert [p.name for p in settings.path().parent.iterdir()] == ["settings.json"]
