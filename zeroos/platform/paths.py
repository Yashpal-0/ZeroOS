"""Directory resolution. Everything that needs $HOME goes through here."""

import os
from pathlib import Path

APP_NAME = "ZeroOS"


def home() -> Path:
    """The user's home directory.

    ZEROOS_HOME overrides it so tests can point the whole application at a
    temporary directory without touching the real home.
    """
    override = os.environ.get("ZEROOS_HOME")
    return Path(override) if override else Path.home()


def data_dir() -> Path:
    """Where the action log lives."""
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else home() / ".local" / "share"
    return base / APP_NAME


def config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else home() / ".config"
    return base / APP_NAME
