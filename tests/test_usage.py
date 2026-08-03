# tests/test_usage.py
"""Spec §9. Counts and timestamps. Nothing a person said."""

from datetime import datetime, timezone

import pytest

from zeroos.agent import usage


@pytest.fixture(autouse=True)
def data_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    return tmp_path


def test_a_session_writes_one_line():
    usage.record(datetime.now(timezone.utc), turns=6, actions=11, declined=1)
    assert len(usage.path().read_text(encoding="utf-8").strip().splitlines()) == 1


def test_the_line_carries_the_counts():
    usage.record(datetime.now(timezone.utc), turns=6, actions=11, declined=1)
    line = usage.path().read_text(encoding="utf-8")
    assert "turns=6" in line
    assert "actions=11" in line
    assert "declined=1" in line


def test_sessions_accumulate():
    for _ in range(3):
        usage.record(datetime.now(timezone.utc), turns=1, actions=0, declined=0)
    assert len(usage.path().read_text(encoding="utf-8").strip().splitlines()) == 3


def test_a_session_with_no_turns_is_still_recorded():
    usage.record(datetime.now(timezone.utc), turns=0, actions=0, declined=0)
    assert "turns=0" in usage.path().read_text(encoding="utf-8")


def test_an_unwritable_directory_does_not_raise(monkeypatch):
    monkeypatch.setattr(
        usage, "_append", lambda line: (_ for _ in ()).throw(OSError("read-only"))
    )
    usage.record(datetime.now(timezone.utc), turns=1, actions=0, declined=0)


def test_the_usage_log_lives_under_the_data_dir(data_home):
    assert str(usage.path()).startswith(str(data_home))
