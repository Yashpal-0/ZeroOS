"""The @tool decorator: an annotated function becomes a described, callable tool.

Carries the surface the rest of the project relies on:

    .name           the function name
    .description    the docstring, minus its Args: block
    .input_schema   JSON Schema derived from the signature
    .call(dict)     invoke with a dictionary of arguments

Deliberately knows nothing about any provider's wire format. agent/session.py
wraps input_schema into whatever shape the API wants; nothing else needs to.
"""

import inspect

_JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean"}

# Returned when a tool fails in a way the function's own handler didn't catch
# — a bug, or a consent-gate malfunction. Deliberately generic: the agent loop
# must learn only that the action did not happen, never crash details. The
# traceback goes to the action log (Task 11) for us, not to the model.
_UNEXPECTED = "That didn't work."

# A tool result the model has to read back. 40,000 characters is ~10k tokens
# against a 65,536 MAX_TOKENS window. The marker is explicit so the model
# narrows and retries rather than reasoning off a result it does not know
# was cut. Shared with mcp/remote.py, which caps server results the same way.
MAX_RESULT = 40_000
_CUT = "\n\n[cut off at 40,000 characters. Narrow the request and try again.]"


def cap(text: str) -> str:
    return text if len(text) <= MAX_RESULT else text[:MAX_RESULT] + _CUT


def _matches_json_type(value, json_type: str) -> bool:
    """True if a Python value fits the declared JSON Schema type.

    bool is a subclass of int in Python, so it is rejected for the numeric
    types — JSON Schema treats integer and boolean as distinct.
    """
    if json_type == "string":
        return isinstance(value, str)
    if json_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if json_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if json_type == "boolean":
        return isinstance(value, bool)
    return True


def _split_docstring(doc: str) -> tuple[str, dict[str, str]]:
    """Split a Google-style docstring into (description, {argument: description})."""
    description: list[str] = []
    arguments: dict[str, str] = {}
    current: str | None = None
    in_args = False

    for raw in inspect.cleandoc(doc or "").splitlines():
        line = raw.strip()
        if line == "Args:":
            in_args = True
            continue
        if not in_args:
            description.append(line)
            continue
        # Argument lines are indented. cleandoc has already stripped the common
        # indent, so a non-empty line back at column 0 has left the Args block —
        # trailing prose that belongs to the description, not to any argument.
        if raw and not raw.startswith(" "):
            in_args = False
            current = None
            description.append(line)
            continue
        head, _, rest = line.partition(":")
        if rest and head.isidentifier():
            current = head
            arguments[current] = rest.strip()
        elif current and line:
            arguments[current] += " " + line

    return "\n".join(description).strip(), arguments


class Tool:
    def __init__(self, func) -> None:
        self.func = func
        self.name = func.__name__
        self.description, argument_docs = _split_docstring(func.__doc__)

        properties: dict[str, dict] = {}
        required: list[str] = []
        for parameter in inspect.signature(func).parameters.values():
            json_type = _JSON_TYPES.get(parameter.annotation)
            if json_type is None:
                raise TypeError(
                    f"{self.name}.{parameter.name} needs a str/int/float/bool annotation"
                )
            properties[parameter.name] = {
                "type": json_type,
                "description": argument_docs.get(parameter.name, ""),
            }
            if parameter.default is inspect.Parameter.empty:
                required.append(parameter.name)

        self.input_schema = {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    def call(self, arguments: dict) -> str:
        """Invoke with a dictionary. Never raises on a malformed call.

        The model writes these arguments, so a wrong shape is an expected
        input, not a bug. Unknown keys are dropped, a missing or wrong-typed
        argument comes back as a sentence the model can read and retry from,
        and any exception that still escapes the function becomes
        "That didn't work." rather than killing the turn.
        """
        properties = self.input_schema["properties"]
        accepted = {k: v for k, v in arguments.items() if k in properties}
        missing = [k for k in self.input_schema["required"] if k not in accepted]
        if missing:
            return f"That didn't work — {self.name} needs {', '.join(missing)}."
        bad = [k for k, v in accepted.items() if not _matches_json_type(v, properties[k]["type"])]
        if bad:
            return f"That didn't work — {self.name} got wrong types for {', '.join(bad)}."
        try:
            return self.func(**accepted)
        except Exception:
            return _UNEXPECTED


# ponytail: the decorator is the class. @tool on a function returns a Tool.
tool = Tool
