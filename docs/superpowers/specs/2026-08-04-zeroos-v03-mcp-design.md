# ZeroOS v0.3 — MCP Servers and the Shell — Design

**Date:** 2026-08-04
**Status:** Draft — not yet implemented
**Scope:** Third-party reach. Two halves that ship together: mounted MCP
servers, and a `run_command` tool. It assumes
[the v0.2 spec](2026-08-03-zeroos-v02-design.md) and
[the v0.2.1 spec](2026-08-04-zeroos-v021-memory-design.md) and does not restate
them.

---

## 1. What v0.3 Adds, and What It Ends

Two capabilities:

1. **MCP servers.** The user mounts a server; its tools join the catalog and
   appear to the model as any other tool. Both transports are supported: stdio
   servers spawned on the host, and remote servers over HTTP.
2. **A shell.** `run_command` runs an arbitrary command line on the host and
   returns its exit code, stdout and stderr.

The second one ends the project's founding wager. Through v0.2.1 the roadmap
staked ZeroOS on a fixed, auditable catalog beating an unbounded shell agent.
`run_command` is the unbounded shell agent. Section 10 rewrites the roadmap
rather than leaving it silently contradicted.

This is not the bet being tested and lost. No tester ever reached the catalog's
edge, because there were no testers. It was called off by the project's owner,
on 2026-08-04, in favour of reach.

### What still stands

- **The gate.** Every MCP tool and `run_command` are confirm-tier. Nothing runs
  unasked, and a dismissed dialog is still a rejection (`dialog.py:67`).
- **The consent row**, which is now load-bearing alone rather than one defence
  among several. Section 6 treats it accordingly.
- **The path sandbox**, over exactly the nine tools it always covered.

### What no longer stands

- **The path sandbox as a general defence.** `PATH_ARGUMENTS` is keyed by tool
  name, and a command line has no path argument to resolve. `run_command`
  routes around `sandbox.resolve` entirely. This is stated here so no reader
  assumes otherwise; it is a consequence of the feature, not an oversight in
  the implementation.
- **"It only does what was written."** What it does is now what the user mounts
  and what the user approves.

### Non-goals for v0.3

- **No per-server or per-tool trust levels.** Everything mounted is
  confirm-tier. No inference from tool names, no server-declared trust, no
  "this one is read-only so let it through." A server's own claims about itself
  are not evidence.
- **No credential storage.** Auth material for remote servers lives in
  `servers.json` as plain text, like any other config value. The secrets
  keyring is v0.4's subject and this release does not anticipate it.
- **No OAuth flow.** Bearer tokens and headers, pasted by the user.
- **No sampling, roots, prompts, or resources.** Only `tools/*`. MCP's other
  capabilities have no place to land in this application yet.
- **No on/off switch for `run_command`.** It is in the catalog or it is not.

---

## 2. Architecture Delta

One new package, one new catalog module, five edited files.

```
startup ── mount.load()                          zeroos/mcp/mount.py     NEW
              │  reads servers.json              zeroos/mcp/config.py    NEW
              │  spawns / connects each server   zeroos/mcp/transport.py NEW
              │  initialize, tools/list
              ▼
           [RemoteTool, ...]                     zeroos/mcp/remote.py    NEW

Session.__init__
    self._tools = {t.name: t for t in build(gate) + mount.tools()}
                                 ▲                    ▲
                        eighteen builtins    everything mounted
                        + run_command

model tool call ── session.py:272 ── gate ── tier_of() ── CONFIRM ── dialog
                                                                       │
                                              approved ────────────────┘
                                                   │
                                    Tool.call()  or  RemoteTool.call()
```

`registry.build()` is **not** modified. It keeps returning exactly the builtin
catalog, which is what `test_registry.py`'s three-place rule was written to
check. Composition happens in `session.py`, where the wire format already
lives.

---

## 3. The Config File

`paths.config_dir() / "servers.json"`, beside `settings.json`.

That location is not incidental. `sandbox.denied_roots()` already includes
`paths.config_dir()` (`sandbox.py:30`), so no path tool the model can call —
`read_text_file`, `write_text_file`, `list_folder`, `search_files` — can reach
it. This matters more in v0.3 than it did before: a model that could write
`servers.json` could mount a server that spawns anything, and the mount would
take effect without any dialog on the next session. The file is the most
privileged thing on disk.

`run_command` can of course read and write it. That is what a shell is. It
cannot do so without the user approving a row that shows the command.

### Format

```json
{
  "servers": [
    {
      "name": "filesystem",
      "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/home/yash"],
      "env": {"NODE_ENV": "production"}
    },
    {
      "name": "linear",
      "url": "https://mcp.linear.app/mcp",
      "headers": {"Authorization": "Bearer lin_api_..."}
    }
  ]
}
```

| Field | Required | Notes |
|---|---|---|
| `name` | yes | Must match `^[a-z0-9-]+$` |
| `command` | one of | A **list**, never a string. Present means stdio. |
| `url` | one of | Present means HTTP. |
| `env` | no | stdio only. Merged over the spawned process's environment. |
| `headers` | no | HTTP only. |

Exactly one of `command` and `url`. An entry with both, neither, a bad `name`,
or a `command` that is a string rather than a list is skipped, and the reason
is shown in the pane.

`name` is validated because it is load-bearing, not for tidiness. It becomes
the middle segment of `mcp__<server>__<tool>` — the string `tier_of`
prefix-matches and the string the consent row displays. A `name` containing
`__` would let two different servers produce one tool name.

### Loading rules

`config.load()` never raises. An unreadable, unparseable, or non-conforming
file yields an empty server list, exactly as `settings._load()` does. A
malformed config must not stop the application from starting.

`config.save(servers)` writes atomically through a `.tmp` and `os.replace`,
matching `settings._save()`.

---

## 4. Transport

`transport.py` exposes one surface:

```python
class Transport:
    def send(self, method: str, params: dict) -> dict:  # raises TransportError
    def close(self) -> None:
```

Two implementations behind it. Both speak JSON-RPC 2.0 and both are used only
by `mount.py` and `RemoteTool`.

### stdio

The Flatpak has no node, no npx, no uvx, and no way to get them. The stdio MCP
ecosystem is therefore unreachable from inside the sandbox, and the server is
spawned on the host:

```python
["flatpak-spawn", "--host", *entry["command"]]
```

with `env` entries passed as `--env=KEY=VALUE`. List form throughout — never
a shell string, so nothing in a config value is interpreted by a shell.

Requires `--talk-name=org.freedesktop.Flatpak` in the manifest (section 9).

Framing is newline-delimited JSON on the child's stdin and stdout, per the MCP
stdio transport. The child's stderr is drained to `agent/log.py` and never
enters a model prompt.

The process is spawned once at mount and held for the application's life. On
quit, and on removal from the pane, it is terminated.

### HTTP

`httpx` is already a bundled dependency (openai's; manifest line 53). No new
module.

`POST` the JSON-RPC body to `url` with `Accept: application/json,
text/event-stream` and the configured `headers`. If the response is
`application/json`, parse it. If it is `text/event-stream`, take the JSON from
the last `data:` line. If the `initialize` response carries an
`Mcp-Session-Id` header, echo it on every subsequent request to that server.

### Handshake and calls

| Step | Method | Notes |
|---|---|---|
| 1 | `initialize` | `{"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "ZeroOS", "version": "0.3.0"}}` |
| 2 | `notifications/initialized` | A notification — no `id`, no response expected |
| 3 | `tools/list` | Returns `{"tools": [{"name", "description", "inputSchema"}]}` |
| 4 | `tools/call` | `{"name": <bare server-side name>, "arguments": {...}}` |

Step 4 sends the **bare** name the server advertised, not the composed
`mcp__…` name. The composition exists for ZeroOS's tier table and dialog; the
server has never heard of it.

`tools/call` returns `{"content": [{"type": "text", "text": ...}],
"isError": bool}`. Non-text content blocks are rendered as
`[<type> content, not shown]` — the model gets an honest placeholder rather
than a silently dropped block.

**Timeout: 120 seconds per call.** A hung server would otherwise hang the whole
agent loop, which is less capable, not more. On timeout the call returns a
sentence saying so.

---

## 5. `RemoteTool` and Mounting

### Why not `Tool`

`catalog/tool.py`'s `Tool.__init__(self, func)` derives `input_schema` from
`inspect.signature`. An MCP tool has no function — it has a JSON Schema that
arrived over a wire. The two ways to force it through `Tool` are code
generation, or a `**kwargs` function that makes `Tool`'s own arity and type
checking vacuous. Both are worse code in exchange for a false sense of reuse.

`RemoteTool` is a sibling class with the same four members `session.py`
actually consumes:

```python
class RemoteTool:
    name: str            # "mcp__<server>__<tool>"
    description: str     # the server's, normalised
    input_schema: dict   # the server's inputSchema, verbatim
    def call(self, arguments: dict) -> str: ...
```

`session.py` cannot tell the difference. That is the whole reason this shape
was chosen over the alternatives.

`input_schema` is passed through **verbatim**. ZeroOS does not validate the
model's arguments against it — the server does, and rewriting a schema we do
not understand is how a tool call starts meaning something other than what the
dialog showed.

### `call` never raises

Same contract as `Tool.call`. Every exception — transport, timeout, protocol,
malformed response — is caught and returned as a readable sentence. A server
being down must not end the agent loop. `_UNEXPECTED = "That didn't work."` is
the fallback, matching `tool.py`.

Results are capped at **40,000 characters** (~10k tokens against a 65,536
`MAX_TOKENS` window). Truncation appends an explicit marker saying the result
was cut, so the model narrows and retries rather than reasoning off a silently
truncated result.

### Names are sanitised

A server's advertised tool names and descriptions are attacker-influenced in
exactly the sense `recall.py:10` already means. Both pass through
`memory.normalise` — which strips control characters and collapses whitespace —
before composition. A tool named with an embedded newline must not be able to
make a consent row read as something other than what will run.

A tool whose name does not survive normalisation to a non-empty string is
skipped.

### Mounting

`mount.load()` runs once at startup and, on demand, when the pane changes
something:

1. `config.load()`.
2. For each entry: connect, `initialize`, `tools/list`.
3. Build a `RemoteTool` per advertised tool.
4. Record per-server status: connected with a tool count, or failed with the
   error string.

A server that fails to connect is **named in the pane with its error**, not
silently dropped, and the application starts anyway.

`mount.tools()` returns the flat list. `mount.status()` returns the per-server
record for the pane.

---

## 6. Consent Copy

### MCP tools — name and raw JSON

```
mcp__filesystem__read_file {"path": "/home/yash/notes.md"}
```

No paraphrase. ZeroOS does not know what an arbitrary server's tool does, and
copy that guesses would be copy that occasionally lies in the one place the
user is being asked to decide. The honest row is the one that shows exactly
what is about to be sent.

Arguments are serialised with `json.dumps(arguments, ensure_ascii=False)` and
run through `describe._for_display`, which caps the row at `memory.MAX_CHARS`
like every other row.

### `run_command` — its own copy

`run_command` is a tool ZeroOS wrote, so ZeroOS can write copy for it:

```
Run this command on your computer:
  rm -rf ~/Documents/Tax 2025
```

The command appears **verbatim on its own line**, never paraphrased,
summarised, or shortened to a description of what it appears to do. The dialog
already wraps and scrolls (`dialog.py:53`), and the row shows the same bytes
that will reach the shell.

This is the single most consequential row in the application. With host
execution in the manifest, the confirm gate is the only thing between the model
and the machine, and this row is how the user works that gate.

---

## 7. Tier Resolution

`policy/tiers.py` gains one branch, before the dict lookup:

```python
MCP_PREFIX = "mcp__"

def tier_of(name: str) -> Tier:
    if name.startswith(MCP_PREFIX):
        return Tier.CONFIRM
    return TIERS[name]
```

Three properties this preserves, all deliberate:

- **`TIERS` is never mutated.** No mount-time write to module state, so
  `test_registry.py`'s three-place rule keeps meaning what it means.
- **Unknown non-MCP names still raise `KeyError`.** Fail-closed stays closed.
- **The prefix is ours.** `mcp__<server>__<tool>` is composed by `mount.py`
  from a validated `name` in a file the model cannot write. A server cannot
  name itself into or out of a tier.

`run_command` is an ordinary entry in `TIERS`, set to `CONFIRM`, and absent
from `PATH_ARGUMENTS` — see section 8.

---

## 8. `run_command`

New module `zeroos/catalog/shell.py`, bound like every other catalog module.

```python
def run_command(command: str) -> str:
    """Run a command on the user's computer and return what it printed."""
```

A real Python function, so it is a plain `Tool` and `input_schema` derives from
the signature as usual.

### Execution

```python
["flatpak-spawn", "--host", "/bin/sh", "-c", command]
```

List form. The Semgrep hook hard-blocks `subprocess` with `shell=True`, and
list form is correct here regardless: the command string is handed to `sh -c`
as a single argument, so nothing about the surrounding Python invocation can
alter it.

Working directory is `paths.home()`.

**Timeout: 300 seconds.** Long enough to compile something. On expiry the
process is killed and the tool returns a sentence saying it was still running
after five minutes.

### Return value

Exit code, stdout, and stderr — all three. A command whose failure is invisible
is a command the model debugs blind:

```
exit 1

<stdout, if any>

--- stderr ---
<stderr, if any>
```

Capped at 40,000 characters with the same explicit truncation marker as section
5.

### No path sandbox

`run_command` is **not** in `PATH_ARGUMENTS` and cannot be. The sandbox works
by resolving named path arguments against `paths.home()` and a denylist; a
command line has no path argument to resolve, and a shell can construct one at
runtime from anything.

So: `run_command` can read `~/.ssh`. It can read `servers.json`. It can read
`memory.jsonl`. The consent row is what stands between the model and each of
those, and it is the only thing that does. This spec says so plainly rather
than letting an implementer infer that some other layer is still catching it.

---

## 9. Packaging

`packaging/io.zerostic.ZeroOS.yml` gains one line to `finish-args`:

```yaml
  - --talk-name=org.freedesktop.Flatpak
```

This is what `flatpak-spawn --host` requires, and it is a genuine escape from
the sandbox: with it, the application can run any command as the user. Both
halves of v0.3 depend on it — stdio MCP servers and `run_command` — so it is
one permission, not two.

No new Python modules. `httpx` is already vendored.

`pyproject.toml` version to `0.3.0`.

---

## 10. Roadmap Changes

Committed with this spec, not deferred.

### `docs/roadmap.md` lines 361-376 — "The bet"

Replaced wholesale:

```markdown
## The bet, and how it ended

The core wager was that a **fixed, auditable catalog** beats an unbounded shell
agent for non-technical users — that the ceiling of "it only does what was
written" is higher in practice than the floor of "it can do anything, and
sometimes does the wrong anything."

v0.3 ends it. The catalog is no longer fixed: MCP servers add tools the user
mounts, and `run_command` runs whatever a shell runs. This was not the wager
being tested and lost. No tester ever reached the catalog's edge, because there
were no testers. It was called off by the project's owner on 2026-08-04, in
favour of reach.

What was staked on the bet, and what stands without it:

- **The gate stands, and is now the whole defence.** Every MCP tool and
  `run_command` are confirm-tier. Nothing runs unasked.
- **The path sandbox does not survive `run_command`.** `PATH_ARGUMENTS` is keyed
  by tool name, and a command line has no path argument to resolve. It guards
  the nine catalog tools it always guarded. It guards nothing beyond them.
- **The consent row is now load-bearing alone.** It used to be one defence among
  several.

The old prediction — failure surfacing at v0.8 when a trusted user still cannot
express what they want — is now untestable. The replacement is narrower and
worth watching from the first tester onward: **does anyone read the
`run_command` row before ticking it?** If not, the graduation rule at v0.8 is
built on sand and the tiers are ornament.
```

### `docs/roadmap.md` lines 350-353 — "Absolute trust"

The last clause names the shell agent as the thing the project argues against.
Replaced:

```markdown
- **Absolute trust.** JARVIS never asks. v0.8 approaches that asymptotically and
  should never arrive: the log, the graduation rule, and the ability to revoke
  *are* the product. Since v0.3 this is not a preference but the last defence —
  with `run_command` in the catalog, an agent that stopped asking would be an
  unattended shell.
```

### Stale numbers

Lines 106 and 307-308 still say the memory caps went "from 50 × 200 to
150 × 300". They are 950 × 1000 since 2026-08-04. Corrected in the same commit.

---

## 11. The Pane

A fourth group in the existing `recall.py` dialog — `_servers_group()`,
alongside `_memory_group`, `_history_group`, and `_settings_group`. Not a new
file and not a new dialog.

Each row shows a server's name, its status (connected with a tool count, or
failed with the error), and a trash button. A footer row adds one, opening a
small form: name, and either a command line or a URL.

`use_markup=False` on every row carrying a server-supplied string, for the
reason `recall.py:10-12` already gives — `Adw.PreferencesRow:use-markup`
defaults to `TRUE`, and a status string wrapped in `<span>` would render
invisible in the screen that exists so the user can remove the server.

Like everything else in this pane, mounting and unmounting do not pass through
the gate. `recall.py:7-8`'s asymmetry holds: this is the user acting, not the
model. Correspondingly, **mounting is never a tool the model can call.** There
is no `add_server` in the catalog and there will not be one.

### Taking effect

A change in the pane marks the session's tool set dirty. The session rebuilds
`self._tools` and `self._schemas` at the **start of the next turn** — never
mid-turn, where a rebuild would race the step loop. Roughly three lines in
`session.py`, and it beats telling the user to restart the application.

---

## 12. Testing

New files:

| File | Covers |
|---|---|
| `tests/test_mcp_config.py` | Every malformed-config path yields `[]` rather than raising; name validation; the `command`-as-string rejection; atomic save |
| `tests/test_mcp_transport.py` | JSON-RPC framing both ways against a fake stdio child and a stubbed `httpx`; the SSE `data:` path; session-id echo; timeout |
| `tests/test_mcp_remote.py` | `input_schema` passthrough is byte-identical; `call` returns a sentence for every failure mode and never raises; the 40,000-char cap and its marker; control characters in a server-supplied name cannot reach a row |
| `tests/test_shell.py` | Exit code, stdout and stderr all present; timeout kills and reports; the argv is list-form with `sh -c` |

Edited:

- `tests/test_tiers.py` — an `mcp__` name resolves `CONFIRM` without touching
  `TIERS`; an unknown non-MCP name still raises; `run_command` is `CONFIRM` and
  absent from `PATH_ARGUMENTS`.
- `tests/test_registry.py` — unchanged in intent. `build()` still returns only
  builtins, now nineteen with `run_command`.
- `tests/test_describe.py` — the `run_command` row contains the command
  verbatim on its own line; an MCP row is name plus `json.dumps` of the
  arguments.
- `tests/test_session.py` — a mounted tool dispatches through the same path as a
  builtin; a mount that changed mid-session is picked up at the start of the
  next turn and never mid-turn.

No test spawns a real host process or opens a real network connection.

---

## 13. Open Question Deferred to v0.4

Remote-server auth material sits in `servers.json` in plain text. The file is
outside the model's path sandbox but it is not encrypted and it is not in the
keyring. v0.4 is credentials; this is the first thing it should pick up.
