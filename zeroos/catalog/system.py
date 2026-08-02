"""read_clipboard, write_clipboard, set_volume, notify."""

import subprocess

from zeroos.catalog.tool import _UNEXPECTED, tool

from zeroos.platform import system as platform_system
from zeroos.policy.gate import Verdict


def bind(gate):
    @tool
    def read_clipboard() -> str:
        """Read whatever text is currently on the user's clipboard.

        Only text is available. If the user copied an image or a file, this
        returns nothing.
        """
        verdict, message = gate.decide("read_clipboard", {})
        if verdict is not Verdict.ALLOW:
            return message
        try:
            text = platform_system.read_clipboard()
        except OSError:
            return _UNEXPECTED
        return text or "The clipboard is empty."

    @tool
    def write_clipboard(text: str) -> str:
        """Put text on the user's clipboard, replacing what was there.

        Args:
            text: The text to copy.
        """
        verdict, message = gate.decide("write_clipboard", {"text": text})
        if verdict is not Verdict.ALLOW:
            return message
        try:
            platform_system.write_clipboard(text)
        except OSError:
            return _UNEXPECTED
        return "Copied to your clipboard."

    @tool
    def set_volume(percent: int) -> str:
        """Set the system output volume.

        Args:
            percent: Loudness from 0 to 100. Values outside that range are
                clamped, so 0 is silent and 100 is full volume.
        """
        verdict, message = gate.decide("set_volume", {"percent": percent})
        if verdict is not Verdict.ALLOW:
            return message
        clamped = max(0, min(100, int(percent)))
        try:
            platform_system.set_volume(clamped)
        except (OSError, ValueError, subprocess.SubprocessError):
            return _UNEXPECTED
        return f"Volume set to {clamped}%."

    @tool
    def notify(title: str, body: str) -> str:
        """Show the user a desktop notification.

        Args:
            title: Short headline.
            body: One or two sentences of detail.

        Use this to tell the user something finished while they were looking
        elsewhere. Do not use it to reply to them — reply in the conversation.
        """
        verdict, message = gate.decide("notify", {"title": title, "body": body})
        if verdict is not Verdict.ALLOW:
            return message
        try:
            platform_system.notify(title, body)
        except OSError:
            return _UNEXPECTED
        return "Notification sent."

    return [read_clipboard, write_clipboard, set_volume, notify]
