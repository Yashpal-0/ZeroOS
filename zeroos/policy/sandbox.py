"""Path sandbox. Spec section 4.2.

Every path argument reaching the catalog passes through resolve() first.
Order matters: expand, absolutise, THEN resolve symlinks, THEN check the
denylist. Checking before resolution would let a symlink walk out of the
sandbox.
"""

from pathlib import Path

from zeroos.platform import paths

REFUSAL_MESSAGE = "That location is off limits."


class Refused(Exception):
    """The path is outside the sandbox. Carries the message shown to the model."""

    def __init__(self, message: str = REFUSAL_MESSAGE) -> None:
        super().__init__(message)
        self.message = message


def denied_roots() -> tuple[Path, ...]:
    h = paths.home()
    return (
        h / ".ssh",
        h / ".gnupg",
        paths.config_dir(),
        paths.data_dir(),
        h / ".local" / "share" / "keyrings",
    )


def resolve(raw: str) -> Path:
    """Resolve a path argument, or raise Refused.

    Path.resolve() is non-strict: it follows every symlink it can and
    normalises the rest, so a not-yet-created file resolves fine as long as
    its parent chain does.
    """
    h = paths.home()

    # Path.expanduser() reads $HOME / the pwd database, not paths.home(), so
    # it would bypass the ZEROOS_HOME test override. Expand "~" against
    # paths.home() ourselves instead.
    candidate = Path(raw)
    if raw == "~" or raw.startswith("~/"):
        candidate = h if raw == "~" else h / raw[2:]
    if not candidate.is_absolute():
        candidate = h / candidate

    try:
        resolved = candidate.resolve()
    except ValueError:
        # e.g. an embedded null byte. Not a valid path either way.
        raise Refused()
    home_resolved = h.resolve()

    if resolved != home_resolved and not resolved.is_relative_to(home_resolved):
        raise Refused()

    for denied in denied_roots():
        # Always resolve, even if the denied root doesn't exist yet: a
        # symlinked home (or an intermediate symlink, e.g. a dotfile
        # manager's ~/.local/share) must not let a missing ~/.ssh slip
        # through unresolved and dodge the containment check below.
        denied = denied.resolve()
        if resolved == denied or resolved.is_relative_to(denied):
            raise Refused()

    return resolved
