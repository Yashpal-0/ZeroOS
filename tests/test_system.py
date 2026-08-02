from zeroos.platform import system


def test_write_clipboard_updates_the_mirror_that_read_clipboard_uses(monkeypatch):
    """The catalog test mocks platform_system entirely, so it never exercises
    this module's own mirror bookkeeping — check it here instead."""
    monkeypatch.setattr(system, "_clipboard", lambda: type("C", (), {"set": lambda self, t: None})())
    system.write_clipboard("hello")
    assert system.read_clipboard() == "hello"


def test_read_clipboard_defaults_to_empty(monkeypatch):
    monkeypatch.setattr(system, "_CLIPBOARD_MIRROR", {})
    assert system.read_clipboard() == ""
