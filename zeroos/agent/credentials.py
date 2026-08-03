"""API key storage. Spec section 7.

Environment first (development), then libsecret (the shipped Flatpak). Never
a config file: ~/.config/ZeroOS is on the sandbox denylist anyway, but the key
should not sit on disk in plaintext regardless.
"""

import os

import gi
import openai

gi.require_version("Secret", "1")
from gi.repository import GLib, Secret  # noqa: E402

from zeroos.agent.session import BASE_URL

ENV_VAR = "OPENROUTER_API_KEY"

_SCHEMA = Secret.Schema.new(
    "io.zerostic.ZeroOS",
    Secret.SchemaFlags.NONE,
    {"purpose": Secret.SchemaAttributeType.STRING},
)
_ATTRIBUTES = {"purpose": "openrouter-api-key"}


def store(key: str) -> None:
    try:
        Secret.password_store_sync(
            _SCHEMA, _ATTRIBUTES, Secret.COLLECTION_DEFAULT, "ZeroOS API key", key, None
        )
    except GLib.Error as error:
        # GLib.Error inherits from RuntimeError, not OSError, so it would sail
        # straight through an `except OSError` in onboarding. An unreachable
        # Secret Service (sandboxed, locked, no daemon) is exactly the case
        # this module exists to handle, so convert it here for every caller.
        raise OSError(str(error)) from error


def load() -> str | None:
    """The key, or None. An environment key wins and skips onboarding."""
    from_env = os.environ.get(ENV_VAR)
    if from_env:
        return from_env
    try:
        return Secret.password_lookup_sync(_SCHEMA, _ATTRIBUTES, None)
    except GLib.Error as error:
        # See store()'s comment: convert here too so a keyring hiccup at
        # startup falls through to onboarding instead of crashing.
        raise OSError(str(error)) from error


def validate(key: str) -> bool:
    """Free round trip: GET /key returns the key's own limit and usage.

    No tokens are generated, so onboarding can validate as many attempts as
    the user needs without charging them for typos.
    """
    client = openai.OpenAI(api_key=key, base_url=BASE_URL)
    try:
        client.get("/key", cast_to=object)
    except openai.AuthenticationError:
        return False
    except openai.APIError:
        # Network trouble, not a bad key. Let onboarding surface it separately.
        raise
    return True
