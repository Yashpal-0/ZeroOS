"""The complete catalog. Nineteen tools.

If you are adding a tool: add it to its module's bind(), add it to
policy/tiers.py TIERS, and if it takes a path add it to PATH_ARGUMENTS.
tests/test_registry.py fails loudly if you forget any of the three.
"""

from zeroos.catalog import apps, files, memory, openers, shell, system


def build(gate):
    """Every tool, bound to this session's gate."""
    return [
        *apps.bind(gate),
        *files.bind(gate),
        *memory.bind(gate),
        *openers.bind(gate),
        *shell.bind(gate),
        *system.bind(gate),
    ]
