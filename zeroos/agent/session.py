"""One conversation with the model. Spec section 5.

The only file that knows a wire format exists. policy/, catalog/, and
platform/ never see a model, a message, or a request — which is what makes
changing provider a change to this file and a config string.

Conversation state is in-memory and per-session: closing the window discards
it. That is a v0.1 simplification, not a permanent one.
"""

import json
from typing import Callable

import openai

from zeroos.agent import log
from zeroos.agent.prompt import SYSTEM_PROMPT
from zeroos.catalog.registry import build
from zeroos.policy.gate import DENIED_MESSAGE, Gate
from zeroos.policy.sandbox import REFUSAL_MESSAGE
from zeroos.policy.tiers import tier_of

BASE_URL = "https://openrouter.ai/api/v1"
MODEL = "qwen/qwen3.7-flash"
MAX_TOKENS = 4096

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
        ask: Callable[[list[str]], list[bool]],
        client=None,
    ) -> None:
        self._gate = Gate(ask)
        self._tools = {tool.name: tool for tool in build(self._gate)}
        self._schemas = [schema_for(tool) for tool in self._tools.values()]
        self._messages: list[dict] = []
        self._client = client or openai.OpenAI(api_key=api_key, base_url=BASE_URL)

    def send(self, text: str) -> str:
        """Run one turn to completion and return the model's final text."""
        self._messages.append({"role": "user", "content": text})
        reply = ""

        for _ in range(MAX_STEPS):
            message = self._client.chat.completions.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}] + self._messages,
                tools=self._schemas,
                tool_choice="auto",
            ).choices[0].message

            calls = tool_calls_in(message)
            self._messages.append(self._as_history(message, calls))
            reply = message.content or reply

            if not calls:
                break

            # Every call is in hand before any of them runs. That is what
            # makes one dialog for the whole turn possible.
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
        return reply or STALLED

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
            else "refused" if result == REFUSAL_MESSAGE
            else "executed"
        )
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
