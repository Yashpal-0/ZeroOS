"""The shell. Spec section 8.

One tool, confirm-tier, and deliberately outside the path sandbox: a command
line has no path argument to resolve, and a shell can construct one at runtime
from anything. run_command can read ~/.ssh, servers.json, and memory.jsonl.
The consent row is what stands between the model and each of those, and it is
the only thing that does.
"""

from zeroos.catalog.tool import cap, tool
from zeroos.platform import shell as platform_shell
from zeroos.policy.gate import Verdict


def bind(gate):
    @tool
    def run_command(command: str) -> str:
        """Run a command on the user's computer and return what it printed.

        Args:
            command: The command to run.
        """
        verdict, message = gate.decide("run_command", {"command": command})
        if verdict is not Verdict.ALLOW:
            return message
        # Capped here rather than in platform/shell.py: the cap exists for the
        # model's context window, which is a catalog-layer concern, and
        # platform/ does not import catalog/.
        return cap(platform_shell.run(command))

    return [run_command]
