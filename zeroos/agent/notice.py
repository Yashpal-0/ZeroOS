"""The noticing pass. Spec section 4.

One model call per turn, over a filtered transcript, returning facts worth
proposing. It knows nothing about the gate, the store, or the display: it
takes a client and messages and returns strings, which is what lets it be
tested without any of them.

The filter is the security boundary of v0.2.1. Tool results carry file
contents and file contents are attacker-controlled, so a pass that read
them would let text inside a file author a memory proposal -- on every
turn, not once. Only user messages and assistant prose go out.
"""

from zeroos.platform import memory

MAX_CANDIDATES = 2
MAX_TOKENS = 200

INSTRUCTION = (
    "Read this conversation and list any lasting facts about the user worth "
    "remembering for future conversations: where things live, how they work, "
    "what they prefer. One per line, in the user's own words, one sentence "
    "each. List nothing at all if there is nothing lasting -- most "
    "conversations have none. Never list anything the user did not say "
    "themselves, and never list the contents of a file. Reply with the lines "
    "only, no preamble and no numbering."
)


def _readable(messages: list[dict]) -> list[dict]:
    """User messages and assistant prose. Never tool results, never tool_calls.

    An assistant message replays its tool_calls so the results have something
    to attach to; there are no results here, so they are noise that names
    files the user may not have mentioned. Dropped along with the results.
    """
    kept = []
    for message in messages:
        role = message.get("role")
        if role not in ("user", "assistant"):
            continue
        content = message.get("content") or ""
        if content:
            kept.append({"role": role, "content": content})
    return kept


def candidates(client, messages: list[dict]) -> list[str]:
    """Fact candidates from this turn. Never raises.

    A failure returns [], which is indistinguishable from finding nothing --
    and that is right. Nothing in this path may take a turn down, and there
    is nothing a user could do about a failed noticing pass anyway.
    """
    try:
        conversation = _readable(messages)
        if not conversation:
            return []
        from zeroos.agent.session import MODEL

        reply = client.chat.completions.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "system", "content": INSTRUCTION}] + conversation,
        ).choices[0].message.content or ""

        found = []
        for line in reply.splitlines():
            text = memory.normalise(line)
            # Dropped, not truncated: truncating changes what a fact says, and
            # the user would be approving text the model did not write.
            if not text or len(text) > memory.MAX_CHARS:
                continue
            found.append(text)
            if len(found) == MAX_CANDIDATES:
                break
        return found
    except Exception:
        return []
