"""list_apps and open_app."""

from zeroos.catalog.tool import _UNEXPECTED, tool

from zeroos.platform import apps as platform_apps
from zeroos.policy.gate import Verdict


def bind(gate):
    @tool
    def list_apps() -> str:
        """List the applications installed on this computer.

        Use this before open_app when you are not sure what the user's
        application is actually called.
        """
        verdict, message = gate.decide("list_apps", {})
        if verdict is not Verdict.ALLOW:
            return message
        try:
            names = platform_apps.installed()
        except OSError:
            return _UNEXPECTED
        return "\n".join(names) if names else "No applications found."

    @tool
    def open_app(name: str) -> str:
        """Open an application the user already has installed.

        Args:
            name: The application's name as it appears in the user's
                launcher, for example "Firefox" or "Rhythmbox".

        Use list_apps first when the user's wording might not match what the
        application is actually called.
        """
        verdict, message = gate.decide("open_app", {"name": name})
        if verdict is not Verdict.ALLOW:
            return message
        try:
            if not platform_apps.launch(name):
                return f"I couldn't find an app called {name}."
        except OSError:
            return _UNEXPECTED
        return f"Opened {name}."

    return [list_apps, open_app]
