"""The complete catalog. Sixteen tools, no more.

If you are adding a tool: add it to its module's bind(), add it to
policy/tiers.py TIERS, and if it takes a path add it to PATH_ARGUMENTS.
tests/test_registry.py fails loudly if you forget any of the three.
"""

from zeroos.catalog import apps, files, openers, system


def build(gate):
    """Every tool, bound to this session's gate."""
    return [*apps.bind(gate), *files.bind(gate), *openers.bind(gate), *system.bind(gate)]
