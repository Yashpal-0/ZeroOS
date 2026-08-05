"""Turn tool calls into sentences a non-technical reader understands.

Spec section 4.4: folder names not paths, counts not lists, no jargon.
"""

from pathlib import Path

from zeroos.platform import memory, paths
from zeroos.platform.memory import strip_control

TRASH_REASSURANCE = (
    "Files moved to the trash can be restored. ZeroOS never permanently deletes anything."
)

# ponytail: only move_file and copy_file collapse. Runs of other tools are rare
# enough in one turn that per-row is fine; extend this set if testing says otherwise.
_COLLAPSIBLE = {"move_file", "copy_file"}


def pretty(path) -> str:
    """Human-readable location: 'Documents / Tax 2025', never a full path."""
    p = Path(path)
    home = paths.home()
    try:
        relative = p.relative_to(home)
    except ValueError:
        return p.name or str(p)
    parts = relative.parts
    return " / ".join(parts) if parts else "Home"


def _folder(path) -> str:
    return pretty(Path(path).parent)


def _name(path) -> str:
    return Path(path).name


def _verb(tool: str) -> str:
    return "Move" if tool == "move_file" else "Copy"


def _for_display(text: str) -> str:
    """Cap the row length. The tool's own MAX_CHARS check runs after the
    dialog has been answered, so it cannot keep this short."""
    text = memory.normalise(text)
    return text if len(text) <= memory.MAX_CHARS else text[: memory.MAX_CHARS] + "…"


def _single(tool: str, args: dict) -> str:
    if tool == "run_command":
        # The one uncapped row in the application. _for_display is deliberately
        # not applied: the MCP cap below exists so a large argument blob cannot
        # swamp the dialog, but here the opposite risk governs -- a truncated
        # command is a command whose tail the user approved without seeing, and
        # the tail is where `&& rm -rf ~` goes. Measured at the 2026-08-04 caps
        # (dialog.py:48-52), a 1,012-character row renders 1,144 px tall in a
        # 304 px scrolled viewport with nothing truncated. Long commands make
        # the user scroll. That is the intended cost.
        #
        # strip_control, not normalise: newlines are preserved, because a
        # command that reads as one line here but runs as three is a row that
        # lies. Control characters go, so a command cannot repaint the dialog
        # around itself.
        command = strip_control(args.get("command", ""))
        return f"Run this command on your computer:\n  {command}"
    if tool == "create_folder":
        return f"Create a folder called {_name(args['path'])} in {_folder(args['path'])}"
    if tool == "write_text_file":
        return f"Save a note called {_name(args['path'])} in {_folder(args['path'])}"
    if tool == "trash_file":
        return f"Move {_name(args['path'])} to the trash"
    if tool == "write_clipboard":
        return "Put some text on your clipboard"
    if tool == "remember":
        return f'Remember: "{_for_display(args.get("text", ""))}"'
    if tool == "forget":
        text = memory.text_of(args.get("fact_id", ""))
        if text is None:
            return "Forget something that is no longer remembered"
        return f'Forget: "{_for_display(text)}"'
    if tool in _COLLAPSIBLE:
        return (
            f"{_verb(tool)} {_name(args['source'])} from {_folder(args['source'])} "
            f"into {_folder(args['destination'])}"
        )
    return f"Run {tool}"


def group_batch(calls: list[tuple[str, dict]]) -> list[tuple[str, list[int]]]:
    """One row per displayed line: its sentence, and which calls it covers.

    Rows are the unit the user ticks, so each must carry the indices it
    speaks for. Runs of the same collapsible tool sharing a source and
    destination folder become one counted row.
    """
    rows: list[tuple[str, list[int]]] = []
    index = 0
    while index < len(calls):
        tool, args = calls[index]
        if tool not in _COLLAPSIBLE:
            rows.append((_single(tool, args), [index]))
            index += 1
            continue

        destination = _folder(args["destination"])
        source = _folder(args["source"])
        run_end = index + 1
        while run_end < len(calls):
            next_tool, next_args = calls[run_end]
            if (
                next_tool != tool
                or _folder(next_args["destination"]) != destination
                or _folder(next_args["source"]) != source
            ):
                break
            run_end += 1

        covered = list(range(index, run_end))
        count = len(covered)
        if count == 1:
            rows.append((_single(tool, args), covered))
        else:
            rows.append(
                (f"{_verb(tool)} {count} files from {source} into {destination}", covered)
            )
        index = run_end
    return rows


def describe_batch(calls: list[tuple[str, dict]]) -> list[str]:
    """The sentences alone, for callers that do not need the mapping."""
    return [text for text, _ in group_batch(calls)]
