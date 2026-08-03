"""Approval gate. Spec section 4.3.

Two-phase because the loop gives us both opportunities and we need both:

  prepare()  runs once per assistant turn, before any tool executes. It sees
             every tool call at once, which is what makes a single batched
             dialog possible.
  decide()   runs inside each tool function, immediately before the side
             effect. It is the enforcement point, so a call that somehow
             skipped prepare() still cannot slip through.

The ledger is keyed by (tool name, arguments) rather than tool_use_id because
the decorated tool functions never see the id. Two identical calls in one turn
are interchangeable, so consuming entries in order is safe.
"""

from collections import defaultdict
from enum import Enum
from typing import Callable

from zeroos.policy import describe
from zeroos.policy.sandbox import REFUSAL_MESSAGE, Refused, resolve
from zeroos.policy.tiers import PATH_ARGUMENTS, Tier, tier_of

DENIED_MESSAGE = "The user declined this action."

# Memory rows arrive unticked; everything else arrives ticked. The distinction
# is not "did the user ask for this" — that would mean trusting the model's
# report of who asked, and injected file text can claim the user asked. So no
# remember row is exempt, including one the user requested out loud. Spec
# section 5.
_UNTICKED_BY_DEFAULT = {"remember"}


def _default_tick(name: str) -> bool:
    return name not in _UNTICKED_BY_DEFAULT


class Verdict(Enum):
    ALLOW = "allow"
    DENY = "deny"
    REFUSE = "refuse"


def _key(name: str, arguments: dict) -> tuple:
    return (name, tuple(sorted((k, str(v)) for k, v in arguments.items())))


def _resolve_arguments(name: str, arguments: dict) -> dict | None:
    """A display copy with every sandboxed argument resolved, or None if any escapes.

    Two jobs in one pass, because they need the same answer. The None is the
    sandbox verdict. The dict is what describe.pretty() needs: "Downloads/a.pdf"
    and "~/Downloads/a.pdf" are legal inputs naming the same file as the
    absolute form, but pretty() cannot strip a home prefix that isn't there, so
    it would render them as a bare filename and the dialog would ask the user
    to authorise deleting a file whose location it never showed. Per the plan's
    Global Constraints, sandbox.resolve is the only place that expands ~; every
    other module takes already-resolved paths from it.

    The copy is for display only. _key() stays on the raw arguments in both
    prepare() and decide(), so the two phases agree on what a call is.
    """
    display = dict(arguments)
    for argument in PATH_ARGUMENTS.get(name, ()):
        raw = arguments.get(argument)
        if raw is None:
            continue
        try:
            display[argument] = str(resolve(str(raw)))
        except Refused:
            return None
    return display


class Gate:
    def __init__(self, ask: Callable[[list[tuple[str, bool]]], list[bool]]) -> None:
        self._ask = ask
        self._ledger: dict[tuple, list[Verdict]] = defaultdict(list)

    def prepare(self, calls: list[tuple[str, dict]]) -> None:
        """Partition one turn's calls and ask about the confirm-tier ones."""
        self._ledger.clear()

        # pending holds the raw calls (what decide() will be keyed on); shown
        # holds the resolved display copies (what the user reads). Same length,
        # same order, so a row's indices address both.
        pending: list[tuple[str, dict]] = []
        shown: list[tuple[str, dict]] = []
        for name, arguments in calls:
            try:
                tier = tier_of(name)
            except KeyError:
                self._ledger[_key(name, arguments)].append(Verdict.REFUSE)
                continue
            resolved = _resolve_arguments(name, arguments)
            if resolved is None:
                self._ledger[_key(name, arguments)].append(Verdict.REFUSE)
                continue
            if tier is Tier.AUTO:
                self._ledger[_key(name, arguments)].append(Verdict.ALLOW)
            else:
                pending.append((name, arguments))
                shown.append((name, resolved))

        if not pending:
            return

        rows = describe.group_batch(shown)
        # A row may cover several calls (group_batch collapses runs), so it is
        # ticked by default only if every call under it is.
        answers = self._ask(
            [
                (text, all(_default_tick(pending[i][0]) for i in covered))
                for text, covered in rows
            ]
        )

        # The gate never invents a verdict. Every DENY here traces to a row the
        # user actually rejected — an unticked box, or a dismissed dialog, which
        # Task 15 turns into an explicit all-False answer. `_ask` is contracted
        # to return exactly one bool per row, so there is no "missing answer"
        # case to paper over, and indexing loudly is better than silently
        # denying an action nobody was asked about.
        assert len(answers) == len(rows), "_ask must answer every row"
        for row_number, (_, covered) in enumerate(rows):
            verdict = Verdict.ALLOW if answers[row_number] else Verdict.DENY
            for call_index in covered:
                name, arguments = pending[call_index]
                self._ledger[_key(name, arguments)].append(verdict)

    def decide(self, name: str, arguments: dict) -> tuple[Verdict, str]:
        """Enforcement point. Called from inside each tool function."""
        entries = self._ledger.get(_key(name, arguments))
        if entries:
            verdict = entries.pop(0)
            return verdict, self._message(verdict)

        # Nothing prepared for this call — it never went through a batch. Ask
        # now rather than deny now. An unprepared call is not a rejected call,
        # and the user has not had a chance to see it yet.
        try:
            tier = tier_of(name)
        except KeyError:
            return Verdict.REFUSE, REFUSAL_MESSAGE
        resolved = _resolve_arguments(name, arguments)
        if resolved is None:
            return Verdict.REFUSE, REFUSAL_MESSAGE
        if tier is Tier.AUTO:
            return Verdict.ALLOW, ""
        answers = self._ask(
            [(row, _default_tick(name)) for row in describe.describe_batch([(name, resolved)])]
        )
        # Same contract, same loudness as prepare(). One row was shown, so one
        # answer must come back; treating an absent answer as DENY would deny an
        # action on behalf of a user whose dialog malfunctioned.
        assert len(answers) == 1, "_ask must answer every row"
        verdict = Verdict.ALLOW if answers[0] else Verdict.DENY
        return verdict, self._message(verdict)

    @staticmethod
    def _message(verdict: Verdict) -> str:
        if verdict is Verdict.DENY:
            return DENIED_MESSAGE
        if verdict is Verdict.REFUSE:
            return REFUSAL_MESSAGE
        return ""
