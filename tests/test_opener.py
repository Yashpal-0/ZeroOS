import pytest
from gi.repository import GLib

from zeroos.platform import opener


class _NoHandler:
    """Stands in for Gio when nothing on the system claims the URI."""

    class AppInfo:
        @staticmethod
        def launch_default_for_uri(uri, context):
            raise GLib.Error("no application is registered as handling this file")


def test_a_gio_failure_leaves_this_module_as_oserror(monkeypatch):
    """GLib.Error inherits from RuntimeError, so the catalog's
    `except (OSError, ValueError)` would miss it. Same contract as
    zeroos/platform/files.py."""
    monkeypatch.setattr(opener, "Gio", _NoHandler)
    with pytest.raises(OSError):
        opener.launch_uri("https://example.com")
