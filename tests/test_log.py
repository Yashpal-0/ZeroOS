import json

import pytest

from zeroos.agent import log


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ZEROOS_HOME", str(tmp_path))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    return tmp_path


def entries(home):
    return [json.loads(line) for line in log.path().read_text().splitlines()]


def test_records_a_call(home):
    log.record("move_file", {"source": "a", "destination": "b"}, "confirm", "allow", "Moved a.")
    written = entries(home)[0]
    assert written["tool"] == "move_file"
    assert written["arguments"]["source"] == "a"
    assert written["verdict"] == "allow"


def test_file_content_is_replaced_by_a_byte_count(home):
    log.record("write_text_file", {"path": "a.txt", "content": "secret data"}, "confirm", "allow", "Saved.")
    written = entries(home)[0]
    assert written["arguments"]["path"] == "a.txt"
    assert written["arguments"]["content"] == "11 bytes"
    assert "secret" not in log.path().read_text()


def test_clipboard_text_is_replaced_by_a_byte_count(home):
    log.record("write_clipboard", {"text": "hunter2"}, "confirm", "allow", "Copied.")
    assert entries(home)[0]["arguments"]["text"] == "7 bytes"
    assert "hunter2" not in log.path().read_text()


def test_read_results_are_not_logged_verbatim(home):
    log.record("read_text_file", {"path": "a.txt"}, "auto", "allow", "a" * 5000)
    assert len(log.path().read_text()) < 1000


def test_appends_rather_than_overwrites(home):
    log.record("list_apps", {}, "auto", "allow", "ok")
    log.record("list_apps", {}, "auto", "allow", "ok")
    assert len(entries(home)) == 2
