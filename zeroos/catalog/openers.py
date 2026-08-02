"""open_path and open_url. Spec section 3.

These are auto-tier, so nothing stops them at the dialog. They are also the
only auto-tier tools that can make something *run* rather than open. That
combination is why the restrictions below exist: read_text_file and
search_files pull untrusted file content into context, and without these
checks a file saying "open the installer in Downloads" would be an execution
primitive.
"""

import os
from pathlib import Path

from zeroos.catalog.tool import _UNEXPECTED, tool

from zeroos.platform import opener
from zeroos.policy.gate import Verdict
from zeroos.policy.sandbox import Refused, resolve

EXECUTABLE_SUFFIXES = frozenset(
    {".desktop", ".sh", ".bash", ".zsh", ".run", ".appimage", ".bin", ".py", ".pl", ".rb"}
)
ALLOWED_SCHEMES = frozenset({"http", "https"})

NOT_A_DOCUMENT = "I can only open documents and folders, not programs."
NOT_A_WEB_ADDRESS = "I can only open web addresses that start with http or https."


def is_launchable(path: Path) -> bool:
    """True if opening this would execute it rather than view it."""
    if path.suffix.lower() in EXECUTABLE_SUFFIXES:
        return True
    return path.is_file() and os.access(path, os.X_OK)


def bind(gate):
    @tool
    def open_path(path: str) -> str:
        """Open a file or folder in whichever application handles it.

        Args:
            path: The file or folder to open.

        This opens documents, media, and folders only. It will not run
        programs, scripts, or installers — if the user wants that, tell them
        to launch it themselves.
        """
        verdict, message = gate.decide("open_path", {"path": path})
        if verdict is not Verdict.ALLOW:
            return message
        try:
            target = resolve(path)
            if not target.exists():
                return "No file at that location."
            if is_launchable(target):
                return NOT_A_DOCUMENT
            opener.launch_path(target)
        except Refused as refused:
            return refused.message
        except (OSError, ValueError):
            return _UNEXPECTED
        return f"Opened {target.name}."

    @tool
    def open_url(url: str) -> str:
        """Open a web address in the user's browser.

        Args:
            url: The address to open. Must start with http:// or https://.

        Only web addresses work. Anything else — file paths, app links,
        custom schemes — is refused.
        """
        verdict, message = gate.decide("open_url", {"url": url})
        if verdict is not Verdict.ALLOW:
            return message
        scheme, separator, _ = url.partition("://")
        if not separator or scheme.lower() not in ALLOWED_SCHEMES:
            return NOT_A_WEB_ADDRESS
        try:
            opener.launch_uri(url)
        except (OSError, ValueError):
            return _UNEXPECTED
        return "Opened it in your browser."

    return [open_path, open_url]
