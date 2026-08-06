"""One advertised server tool, wearing Tool's shape. Spec section 5.

catalog/tool.py's Tool derives its input_schema from inspect.signature. An MCP
tool has no function -- it has a JSON Schema that arrived over a wire. Forcing
it through Tool means either code generation or a **kwargs function that makes
Tool's own arity and type checking vacuous. RemoteTool is a sibling with the
same four members session.py actually consumes, so session.py cannot tell the
difference. That is the whole reason for this shape.
"""

from zeroos.catalog.tool import _UNEXPECTED, cap
from zeroos.platform import memory
from zeroos.mcp.transport import TransportError
from zeroos.policy.gate import Verdict
from zeroos.policy.tiers import MCP_PREFIX


class RemoteTool:
    def __init__(self, server: str, bare_name: str, description: str, schema: dict, link, gate):
        # mcp__<server>__<tool>, composed here from a name validated by
        # config.py out of a file the model cannot write. tier_of prefix-matches
        # this string and the consent row displays it, so a server cannot name
        # itself into or out of a tier.
        self.name = f"{MCP_PREFIX}{server}__{bare_name}"
        self.description = description
        # Verbatim. ZeroOS does not validate the model's arguments against it --
        # the server does, and rewriting a schema we do not understand is how a
        # tool call starts meaning something other than what the dialog showed.
        self.input_schema = schema
        self._bare_name = bare_name
        self._link = link
        self._gate = gate

    def call(self, arguments: dict) -> str:
        """Same contract as Tool.call: always a string, never an exception.

        A server being down must not end the agent loop.
        """
        try:
            verdict, message = self._gate.decide(self.name, arguments)
            if verdict is not Verdict.ALLOW:
                return message
            # The bare name the server advertised, not the composed one. The
            # composition exists for ZeroOS's tier table and dialog; the server
            # has never heard of it.
            result = self._link.send(
                "tools/call", {"name": self._bare_name, "arguments": arguments}
            )
            return cap(_text_of(result))
        except TransportError as error:
            return str(error)
        except Exception:
            return _UNEXPECTED


def _text_of(result) -> str:
    """The content blocks, flattened. Never raises on a shape we did not expect."""
    if not isinstance(result, dict):
        return _UNEXPECTED
    blocks = result.get("content")
    if not isinstance(blocks, list):
        return _UNEXPECTED
    lines = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            lines.append(str(block.get("text", "")))
        else:
            # An honest placeholder rather than a silently dropped block: the
            # model can say "the server sent an image" instead of reasoning
            # from a gap it never knew was there.
            lines.append(f"[{kind} content, not shown]")
    return "\n".join(lines) if lines else "The server returned nothing."


def build(server: str, link, advertised: list, gate) -> list:
    """A RemoteTool per advertised tool. Malformed entries are skipped.

    Names and descriptions are attacker-influenced in exactly the sense
    recall.py:10 already means, so both pass through memory.normalise -- a tool
    named with an embedded newline must not be able to make a consent row read
    as something other than what will run. A name that does not survive to a
    non-empty string is dropped entirely.
    """
    tools = []
    for entry in advertised:
        if not isinstance(entry, dict):
            continue
        bare_name = memory.normalise(entry.get("name", ""))
        if not bare_name:
            continue
        schema = entry.get("inputSchema")
        tools.append(
            RemoteTool(
                server,
                bare_name,
                memory.normalise(entry.get("description", "")),
                schema if isinstance(schema, dict) else {"type": "object", "properties": {}},
                link,
                gate,
            )
        )
    return tools
