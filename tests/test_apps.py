import pytest
from gi.repository import GLib

from zeroos.platform import apps


class _Info:
    def __init__(self, display_name):
        self._display_name = display_name

    def should_show(self):
        return True

    def get_display_name(self):
        return self._display_name

    def launch(self, files, context):
        raise GLib.Error("launch failed")


class _FailingAppInfo:
    """Stands in for Gio when the found app refuses to launch."""

    class AppInfo:
        @staticmethod
        def get_all():
            return [_Info("Rhythmbox")]


def test_a_gio_launch_failure_leaves_this_module_as_oserror(monkeypatch):
    """GLib.Error inherits from RuntimeError, so the catalog's
    `except OSError` would miss it. Same contract as
    zeroos/platform/opener.py and files.py."""
    monkeypatch.setattr(apps, "Gio", _FailingAppInfo)
    with pytest.raises(OSError):
        apps.launch("Rhythmbox")
