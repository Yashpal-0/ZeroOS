"""One conversation with the model. Spec section 5.

The only file that knows a wire format exists. policy/, catalog/, and
platform/ never see a model, a message, or a request — which is what makes
changing provider a change to this file and a config string.

Conversation state is in-memory and per-session: closing the window discards
it. That is a v0.1 simplification, not a permanent one.
"""

import json
from datetime import datetime, timezone
from typing import Callable

import openai

from zeroos.agent import history, log, notice, usage
from zeroos.agent.prompt import MEMORY_CLOSING, MEMORY_PREFACE, PROMPTS
from zeroos.catalog.registry import build
from zeroos.mcp import mount
from zeroos.platform import memory, settings
from zeroos.policy.describe import describe_batch
from zeroos.policy.gate import DENIED_MESSAGE, Gate
from zeroos.policy.sandbox import REFUSAL_MESSAGE, ROOT_REFUSAL_MESSAGE
from zeroos.policy.tiers import tier_of

BASE_URL = "https://openrouter.ai/api/v1"
MODEL = "qwen/qwen3.7-flash"
MAX_TOKENS = 65536

# Not a budget — a runaway stop. A long task is allowed to take as many round
# trips as it needs; this only exists so a model stuck in a call/answer cycle
# cannot spin forever. In practice the binding limit is the context window,
# which fills long before step 1000, and the model will fail there first.
MAX_STEPS = 1000

UNKNOWN_TOOL = "That isn't something I can do."
STALLED = "I wasn't able to finish that one, Sir. Try asking for a smaller piece of it."


def schema_for(tool) -> dict:
    """A @tool object in OpenAI wire shape."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


def tool_calls_in(message) -> list[tuple[str, str, dict]]:
    """The (call_id, name, arguments) triples requested in this message.

    `arguments` arrives as a JSON string the model composed, so it can be
    malformed. A malformed call becomes empty arguments rather than an
    exception: Tool.call then reports the missing arguments back to the
    model, which can correct itself. Crashing the turn cannot.
    """
    calls = []
    for call in getattr(message, "tool_calls", None) or []:
        try:
            arguments = json.loads(call.function.arguments or "{}")
        except (json.JSONDecodeError, TypeError):
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        calls.append((call.id, call.function.name, arguments))
    return calls


def _record(name: str, arguments: dict, verdict: str, result: str) -> None:
    """log.record(), but a logging failure can never take the turn down with it.

    record() does an unguarded mkdir/stat/replace/write (Task 11's review
    flagged this as the caller's responsibility) — a full disk or permission
    error must not stop the model from getting its tool result. tier_of()
    is resolved in here too, under the same guard: it also raises (KeyError,
    fail-closed) for a name that isn't in TIERS, and that must not kill the
    turn either.
    """
    try:
        tier = tier_of(name).value
    except KeyError:
        tier = "unknown"
    try:
        log.record(name, arguments, tier, verdict, result)
    except Exception:
        pass


class Session:
    def __init__(
        self,
        api_key: str,
        ask: Callable[[list[tuple[str, bool]]], list[bool]],
        client=None,
    ) -> None:
        self._gate = Gate(ask)
        self._rebuild_tools()
        self._messages: list[dict] = []
        self._client = client or openai.OpenAI(api_key=api_key, base_url=BASE_URL)
        # Resolved once, here — not per turn and not per step. A prompt built
        # per turn is the thing that makes caching impossible later, and the
        # form of address changing under a live conversation would read as the
        # assistant changing character mid-sentence.
        self._prompt = PROMPTS[settings.address()]
        self._started = datetime.now(timezone.utc)
        self._turns = self._actions = self._declined = 0
        # Candidates from the previous turn, waiting to be offered. In memory
        # and for at most one turn: there is no spool file and no recovery.
        self._pending: list[str] = []
        # Every candidate text this session has already put in front of the
        # user. The noticing pass reads the whole accumulated transcript every
        # turn, so a fact the user declined would otherwise be proposed again
        # on the next turn, and the next, until they gave in and ticked it --
        # which is the consent model eroding. What is recorded is what was
        # offered, not what was refused: an approved fact is already stored, so
        # not re-offering it is equally right. Dies with the session; a fresh
        # one may raise the same fact again, and nothing reaches disk.
        self._offered: set[str] = set()
        # How much of _messages the last noticing pass has already read. The
        # pass costs a reasoning-model call per turn, and sending the whole
        # accumulated transcript makes turn 40 pay to re-read the first 39 --
        # a cost that grows with a conversation rather than with what was said
        # in it. The closing summary in close() deliberately ignores this: it
        # runs once, and its job is the session as a whole.
        self._noticed = 0

    @property
    def gate(self) -> Gate:
        """The consent gate shared by this session's built-in and mounted tools."""
        return self._gate

    def send(self, text: str, on_event=None) -> str:
        """Run one turn to completion and return the model's final text.

        on_event, if given, is called from the worker thread with one of:
          ("token", str)   — one content delta, many times per step
          ("tools", [str]) — describe_batch sentences, once per tool step
          ("done", str)    — the final reply, once at the end
        When on_event is None, send behaves identically to v0.3.
        """
        self._refresh_tools_if_remounted()
        self._offer_candidates()
        self._messages.append({"role": "user", "content": text})
        self._turns += 1
        reply = ""

        for _ in range(MAX_STEPS):
            stream = self._client.chat.completions.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "system", "content": self._prompt}]
                + self._memory_messages(text)
                + self._messages,
                tools=self._schemas,
                tool_choice="auto",
                stream=True,
            )
            message = self._consume_stream(stream, on_event)

            calls = tool_calls_in(message)
            self._messages.append(self._as_history(message, calls))
            reply = message.content or reply

            if not calls:
                break

            # Every call is in hand before any of them runs. That is what
            # makes one dialog for the whole turn possible.
            if on_event:
                on_event("tools", describe_batch(
                    [(name, arguments) for _, name, arguments in calls]
                ))
            self._gate.prepare([(name, arguments) for _, name, arguments in calls])

            for call_id, name, arguments in calls:
                self._messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": self._run(name, arguments),
                    }
                )

        # A model that exhausts the step bound without ever writing a sentence
        # would otherwise return "" and leave the window blank, which reads as
        # a crash. Say something true instead.
        reply = reply or STALLED
        history.append(text, reply)
        # Produced now, offered at the top of the next turn. The dialog cannot
        # open before this returns: window.py renders the reply only after
        # send() comes back, and ask blocks until answered, so a dialog here
        # would ask about facts drawn from a reply the user has not seen.
        self._pending = notice.candidates(self._client, self._messages[self._noticed:])
        self._noticed = len(self._messages)
        if on_event:
            on_event("done", reply)
        return reply

    @staticmethod
    def _consume_stream(stream, on_event):
        """Accumulate a streaming response into one assistant message.

        Content deltas are concatenated and emitted as "token" events. Tool
        calls arrive fragmented across chunks — id, name, and arguments in
        separate deltas keyed by index — and are reassembled here into the
        same shape tool_calls_in() expects. The reassembly is the load-bearing
        detail of v0.3.1: getting it wrong looks like a missing tool call.
        """
        content_parts: list[str] = []
        fragments: dict[int, dict] = {}
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                content_parts.append(delta.content)
                if on_event:
                    on_event("token", delta.content)
            for tc in (getattr(delta, "tool_calls", None) or []):
                frag = fragments.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                if getattr(tc, "id", None):
                    frag["id"] = tc.id
                fn = getattr(tc, "function", None)
                if fn is not None:
                    if fn.name:
                        frag["name"] = fn.name
                    if fn.arguments:
                        frag["arguments"] += fn.arguments
        return Session._materialise(content_parts, fragments)

    @staticmethod
    def _materialise(content_parts: list[str], fragments: dict[int, dict]):
        """Build the object tool_calls_in() expects from accumulated pieces."""

        class _Function:
            def __init__(self, name, arguments):
                self.name = name
                self.arguments = arguments

        class _Call:
            def __init__(self, id_, name, arguments):
                self.id = id_
                self.function = _Function(name, arguments)

        class _Message:
            def __init__(self, content, tool_calls):
                self.content = content
                self.tool_calls = tool_calls or None

        calls = [
            _Call(f["id"], f["name"], f["arguments"])
            for f in (fragments.get(i) for i in sorted(fragments))
            if f
        ]
        return _Message("".join(content_parts) or None, calls if calls else None)

    def _memory_messages(self, query: str) -> list[dict]:
        """The second system message, or nothing at all.

        `query` is the text the user typed this turn, not the most recent
        message: inside the step loop that is usually a tool result, and
        ranking facts against a directory listing would change what the model
        remembers halfway through a turn. Constant across every step, so the
        block is stable within a turn.

        Read inside the step loop, not once per turn: a remember approved
        halfway through a turn must be visible to the next model call in that
        same turn, or the assistant appears to forget what it just confirmed.
        search() rebuilds its index per call, so there is nothing to
        invalidate when that happens.

        Empty means omitted, not sent blank — a fresh install's request
        carries exactly one system message, and nothing section 3 adds can
        reach it. Spec §13.4. (§13.4 originally said "byte-identical to
        v0.1's"; the persona ruling of 2026-08-04 replaced the prompt text,
        which voids the parity half and leaves this half intact.)

        The preface lives in prompt.py and the facts in platform/memory.py;
        joining them is this layer's job, which is what keeps the store free
        of prompt text and importable from policy/describe.py.
        """
        facts = memory.search(query)
        if not facts:
            return []
        lines = "\n".join(f"[{f['id']}] {f['text']}" for f in facts)
        block = f"{MEMORY_PREFACE}\n\n{lines}\n\n{MEMORY_CLOSING}"
        return [{"role": "system", "content": block}]

    def _offer_candidates(self) -> None:
        """Put the previous turn's candidates through the ordinary dialog.

        Runs before the step loop, so the loop's own prepare() clears a ledger
        whose entries have already been consumed. Drained first: offering the
        same candidate twice would ask about a fact already answered. Filtered
        against _offered for the same reason across turns rather than within
        one -- see its comment in __init__ for why the noticing pass keeps
        finding a fact the user has already been asked about.

        A session's final turn is not dropped: close() runs its own noticing
        pass over the finished conversation and offers the result through here,
        so the last thing said still gets its chance to be remembered.

        Guarded here rather than at the call sites, which is the only place
        that guards both. prepare() reaches the GTK layer, so it can fail; in
        send() an unguarded failure would surface to the user as the "couldn't
        reach the model" banner, blaming the network for a dialog fault and
        losing the message they typed.
        """
        found, self._pending = self._pending, []
        found = [text for text in found if text not in self._offered]
        if not found:
            return
        try:
            self._gate.prepare([("remember", {"text": text}) for text in found])
            # Marked offered only once the dialog has actually reached the user.
            # Ahead of prepare(), a GTK fault would both drain the candidate and
            # record it as asked about, and the noticing pass would keep finding
            # it every turn only for this filter to drop it -- unofferable for
            # the rest of the session over a question nobody was ever shown.
            self._offered.update(found)
            for text in found:
                # Through _run, not store.add: an approved candidate is an
                # ordinary remember and belongs in actions.log and the counters
                # like one.
                self._run("remember", {"text": text})
        except Exception:
            pass

    def close(self, summary: bool = True) -> None:
        """Called once, on window shutdown. Never raises.

        Pass summary=False when a turn is still running. The closing summary
        would otherwise call prepare() on a second thread, and prepare() opens
        by clearing the consent ledger -- so the live turn's next decide()
        would find its verdicts gone and ask the user again for an action they
        had already approved. Spec section 7 says the summary is skipped
        entirely in that case, and skipping is what the caller gets here.
        Skipping, not waiting: a lock would park shutdown behind a consent
        dialog the user must answer after having asked to quit.

        The usage line is written either way. It describes the session, not
        the summary, and it is the only record that the session happened.

        Order matters: the closing summary's approved remembers go through
        _run and increment _actions, so usage.record must come last or the
        line undercounts the session it describes.

        The summary carries the same guard as the noticing pass. A network
        failure on the way out must not take shutdown down with it, and
        there is nothing a user can do about a failed summary at the moment
        the window has already gone. usage.record swallows its own failures
        separately.
        """
        if summary:
            try:
                self._pending = notice.candidates(self._client, self._messages)
                self._offer_candidates()
            except Exception:
                pass
        usage.record(self._started, self._turns, self._actions, self._declined)

    def _rebuild_tools(self) -> None:
        """Builtins plus everything mounted, in one dict.

        registry.build() stays builtin-only -- that is what test_registry.py's
        three-place rule was written to check -- so the composition happens
        here, where the wire format already lives.
        """
        self._mounted_at = mount.generation()
        self._tools = {tool.name: tool for tool in build(self._gate) + mount.tools()}
        self._schemas = [schema_for(tool) for tool in self._tools.values()]

    def _refresh_tools_if_remounted(self) -> None:
        """Pick up a pane change at the start of a turn, never mid-turn.

        A rebuild inside the step loop would swap the dict the loop is
        dispatching through and the schema list already sent to the model,
        which is a race for no benefit -- the user who just added a server can
        wait until their next message.
        """
        if mount.generation() != self._mounted_at:
            self._rebuild_tools()

    def _run(self, name: str, arguments: dict) -> str:
        """Execute one call. Always returns a string for the model to read."""
        tool = self._tools.get(name)
        if tool is None:
            _record(name, arguments, "refused", UNKNOWN_TOOL)
            return UNKNOWN_TOOL
        result = tool.call(arguments)
        # The bound tool swallows a denial or a sandbox refusal and returns the
        # message instead of raising, so the return value is the only evidence
        # of what happened. Logging every call as "executed" would make the log
        # claim ZeroOS did things the user declined — the exact question §6
        # says the log exists to answer.
        decision = (
            "declined" if result == DENIED_MESSAGE
            else "refused" if result in (REFUSAL_MESSAGE, ROOT_REFUSAL_MESSAGE)
            else "executed"
        )
        if decision == "executed":
            self._actions += 1
        elif decision == "declined":
            self._declined += 1
        _record(name, arguments, decision, result)
        return result

    @staticmethod
    def _as_history(message, calls) -> dict:
        """The assistant message, in the shape the API expects it replayed.

        It must be appended before the tool results, and it must still carry
        its tool_calls, or the results have nothing to attach to.
        """
        entry: dict = {"role": "assistant", "content": message.content or ""}
        if calls:
            entry["tool_calls"] = [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }
                for call_id, name, arguments in calls
            ]
        return entry
