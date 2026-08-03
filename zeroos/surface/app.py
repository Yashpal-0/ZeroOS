"""Adw.Application: pick onboarding or the chat window, depending on the key."""

import gi

gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402

from zeroos.agent import credentials  # noqa: E402
from zeroos.surface.onboarding import build as build_onboarding  # noqa: E402
from zeroos.surface.window import ChatWindow  # noqa: E402

APP_ID = "io.zerostic.ZeroOS"


class ZeroOSApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID)

    def do_activate(self) -> None:
        try:
            key = credentials.load()
        except OSError:
            # Keyring unreachable (locked, sandboxed, no daemon): fall through
            # to onboarding rather than crash. store() there is guarded too.
            key = None
        if key:
            ChatWindow(self, key).present()
            return

        window = Adw.ApplicationWindow(application=self, default_width=560, default_height=520,
                                       title="ZeroOS")

        def accepted(new_key: str) -> None:
            window.close()
            ChatWindow(self, new_key).present()

        window.set_content(build_onboarding(accepted))
        window.present()


def main() -> int:
    return ZeroOSApplication().run(None)
