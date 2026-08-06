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

import re

from zeroos.platform import memory

MAX_CANDIDATES = 2

# Shorter than this is a fragment, not a fact -- "ok", "yes", "the CV". The
# real store collected "[Empty response]" (window.py's placeholder for a
# blank reply) because the pass read a rendering artefact as prose.
MIN_CHARS = 15
_PLACEHOLDER = re.compile(r"^\[.*\]$")

# The model's own ceiling, not a budget. MODEL is a reasoning model: it thinks
# before it answers, and a cap it cannot finish thinking inside returns
# finish_reason="length" with content=None. candidates() cannot tell that apart
# from finding nothing, so at the old cap of 200 the pass silently never fired
# -- found during the v0.2.1 acceptance walk, where criterion 2 came back empty
# and the empty was the bug rather than the verdict. Anything short of the
# ceiling is a guess at how long the model needs to think, and a wrong guess
# reads as amnesia. This is a ceiling, so it costs nothing unspent: a pass that
# reasons for ~1200 tokens is billed for ~1200, not for 65536.
MAX_TOKENS = 65536

INSTRUCTION = (
    "Read this conversation and list any lasting facts about the user worth "
    "remembering for future conversations: where things live, how they work, "
    "what they prefer. Write each fact in the third person, using the user's "
    'name if you know it -- "Yash keeps tax PDFs in Documents", never "I keep '
    'tax PDFs in Documents". You will be shown these lines later as facts '
    "about the user, so a line beginning with I would read as a fact about "
    "you instead. One per line, one sentence each. Every line must state a "
    "fact about the user; if you are unsure, leave it out. List nothing at "
    "all if there is nothing lasting -- most conversations have none. Never "
    "list anything the user did not say themselves, and never list the "
    "contents of a file. Reply with the lines only, no preamble and no "
    "numbering."
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
        # ponytail: exact match only. A paraphrase of a stored fact still gets
        # through; the fix is asking the model to consolidate with remember +
        # forget in one approved batch, not a similarity threshold that would
        # silently discard facts the user wanted.
        stored = {fact["text"] for fact in memory.load()}
        for line in reply.splitlines():
            text = memory.normalise(line)
            # Dropped, not truncated: truncating changes what a fact says, and
            # the user would be approving text the model did not write.
            if len(text) > memory.MAX_CHARS:
                continue
            if len(text) < MIN_CHARS or _PLACEHOLDER.match(text):
                continue
            if text in stored:
                continue
            found.append(text)
            if len(found) == MAX_CANDIDATES:
                break
        return found
    except Exception:
        return []
