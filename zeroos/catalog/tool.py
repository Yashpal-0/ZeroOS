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


def _split_docstring(doc: str) -> tuple[str, dict[str, str]]:
    """Split a Google-style docstring into (description, {argument: description})."""
    description: list[str] = []
    arguments: dict[str, str] = {}
    current: str | None = None
    in_args = False

    for line in inspect.cleandoc(doc or "").splitlines():
        line = line.strip()
        if line == "Args:":
            in_args = True
            continue
        if not in_args:
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
        input, not a bug. Unknown keys are dropped and a missing required
        argument comes back as a sentence the model can read and retry from.
        """
        accepted = {k: v for k, v in arguments.items() if k in self.input_schema["properties"]}
        missing = [k for k in self.input_schema["required"] if k not in accepted]
        if missing:
            return f"That didn't work — {self.name} needs {', '.join(missing)}."
        return self.func(**accepted)


# ponytail: the decorator is the class. @tool on a function returns a Tool.
tool = Tool
