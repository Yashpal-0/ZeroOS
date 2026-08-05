"""remember and forget. Spec §4.

Both are confirm-tier and must stay that way. The character cap is enforced
here rather than in the store because this is the layer with a string to hand
back to the model.

store.add and store.remove never raise — a failed write comes back as ""
or False — so neither function here needs a try/except around them.
"""

from zeroos.platform import memory as store
from zeroos.catalog.tool import tool
from zeroos.policy.gate import Verdict

_SAVE_FAILED = "Couldn't save that — try again in a moment."
_REMOVE_FAILED = "Couldn't remove that — try again in a moment."


def bind(gate):
    @tool
    def remember(text: str) -> str:
        """Store one short fact about the user or their preferences so it is
        available in future conversations.

        Args:
            text: The fact, in one sentence, in the third person -- "Yash keeps
                tax PDFs in Documents", not "I keep tax PDFs in Documents".

        Use this only when the user asks you to remember something, or states
        a lasting preference. Do not use it to store the contents of files, or
        anything the user has not said themselves.
        """
        # Decide before validating. gate.prepare has already shown this call's
        # row by the time the body runs (§7 says so explicitly, and calls the
        # post-approval length rejection deliberate), so returning early here
        # left the user's answer sitting unread in the ledger: a denied over-long
        # fact came back as the length message, which _run classifies as
        # "executed". actions.log would then record verdict "executed" for a
        # confirm-tier call the user declined -- the one question §6 says the
        # log exists to answer.
        verdict, message = gate.decide("remember", {"text": text})
        if verdict is not Verdict.ALLOW:
            return message
        clean = store.normalise(text)
        if not clean:
            return "There was nothing there to remember."
        if len(clean) > store.MAX_CHARS:
            return f"That is too long to remember — keep it under {store.MAX_CHARS} characters."
        if not store.add(clean):
            return _SAVE_FAILED
        return f"Remembered: {clean}"

    @tool
    def forget(fact_id: str) -> str:
        """Delete one remembered fact.

        Args:
            fact_id: The id shown in square brackets beside the fact in the
                list of remembered things.

        Use this when the user asks to forget something specific, or when they
        want two overlapping facts replaced by one: remember the merged fact
        and forget the old ones in the same reply, and the user approves the
        whole batch in one dialog.
        """
        verdict, message = gate.decide("forget", {"fact_id": fact_id})
        if verdict is not Verdict.ALLOW:
            return message
        existed = store.text_of(fact_id) is not None
        if not store.remove(fact_id):
            return _REMOVE_FAILED if existed else "Nothing is remembered under that name."
        return "Forgotten."

    return [remember, forget]
