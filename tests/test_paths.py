import os
from pathlib import Path

from zeroos.platform import paths


def test_home_defaults_to_real_home():
    assert paths.home() == Path.home()


def test_home_is_overridable_for_tests(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    assert paths.home() == tmp_path


def test_data_dir_is_under_home(monkeypatch, tmp_path):
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert paths.data_dir() == tmp_path / ".local" / "share" / "ZeroOS"


def test_data_dir_respects_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert paths.data_dir() == tmp_path / "xdg" / "ZeroOS"
