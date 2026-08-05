"""Running a command on the user's computer. Spec section 8.

The Flatpak sandbox is escaped deliberately here: flatpak-spawn --host runs
the command as the user, outside every restriction the manifest otherwise
imposes. Nothing in this module limits what a command can do -- the confirm
dialog is the only thing that does, and policy/describe.py writes the row.
"""

import subprocess

from zeroos.platform import paths

TIMEOUT_SECONDS = 300
_TIMED_OUT = "The command was still running after five minutes, so it was stopped."


def run(command: str) -> str:
    """Run one command and return exit code, stdout and stderr. Never raises.

    List form, not shell=True: the command string reaches `sh -c` as a single
    argument, so nothing about this Python invocation can alter it.

    Uncapped. catalog/shell.py caps what the model reads back; this module is
    below catalog/ and does not import upward.
    """
    try:
        finished = subprocess.run(
            ["flatpak-spawn", "--host", "/bin/sh", "-c", command],
            cwd=paths.home(),
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return _TIMED_OUT
    except (OSError, ValueError) as error:
        return f"The command could not be started: {error}"

    # All three, always. A command whose failure is invisible is a command
    # the model debugs blind.
    parts = [f"exit {finished.returncode}"]
    if finished.stdout:
        parts.append(finished.stdout)
    if finished.stderr:
        parts.append(f"--- stderr ---\n{finished.stderr}")
    return "\n\n".join(parts)
