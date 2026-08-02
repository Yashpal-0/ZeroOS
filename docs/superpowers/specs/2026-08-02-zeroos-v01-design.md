# ZeroOS v0.1 — Design

**Date:** 2026-08-02
**Status:** Draft for review
**Scope:** v0.1 only. Later phases live in [`docs/roadmap.md`](../../roadmap.md).

---

## 1. What ZeroOS Literally Is

ZeroOS is **not** an operating system. It is a desktop application for Linux that
accepts typed natural language and performs a bounded set of audited actions on the
user's own machine.

One sentence for the README: *ZeroOS is a text-driven assistant that operates your
Linux desktop through a fixed catalog of safe actions.*

The "Agent OS" framing is product branding. Architecturally it is a chat window
attached to an agent loop attached to a permission gate attached to ~16 functions.
Everything in this document follows from taking that literally.

### Target user

A non-technical person on a Linux desktop. They do not open a terminal. They do not
know what a path is. They expect an application they install from a store, launch
from a menu, and type into.

This audience is deliberately small — non-technical Linux desktop users are a narrow
market. The decision is intentional (the developer runs Linux daily and will dogfood
it). It is recorded here so nobody re-litigates it later.

### v0.1 constraints

| Constraint | Value |
|---|---|
| Input | Text only. No voice, no images. |
| Reach | Local machine only. No OAuth, no third-party accounts, no server. |
| Action model | Curated catalog. No raw shell, ever. |
| OS | Linux desktop (GNOME-first; Wayland and X11). |
| Model | `qwen/qwen3.7-flash` via OpenRouter. |

### Non-goals for v0.1

Voice input. Long-term memory across sessions. Multiple cooperating agents. Scheduled
or background tasks. Computer-use / screen control. Cloud sync. Windows or macOS.
Third-party service integrations (Gmail, Slack, Calendar). Plugin system.

Each is a real feature; each belongs to a later phase with its own spec.

---

## 2. Architecture

Five layers. Each is a directory, each has one job, each can be understood without
reading the others.

```
surface/     GTK4 chat window, onboarding, permission dialog
agent/       Model session loop, system prompt, conversation state
policy/      Permission tiers, path sandbox, approval batching
catalog/     The ~16 action functions
platform/    Thin Linux wrappers: XDG portals, D-Bus, GIO, xdg-open
```

Dependency direction is strictly downward. `catalog/` calls `platform/`. `agent/`
calls `policy/` and `catalog/`. Nothing calls `surface/` — the surface calls in and
receives callbacks.

`policy/` is a pure decision layer: given a set of requested tool calls it returns a
partition (run now / needs approval / refused) and the plain-language description of
each. It never draws anything. `agent/` takes the "needs approval" set, hands it to
whatever approval callback it was constructed with, and waits. In the app that
callback is the GTK dialog; in tests it is a function that returns a fixed answer.
That is what makes the permission model testable without a display.

### Why OpenRouter and a hand-written loop

The model is `qwen/qwen3.7-flash`, reached through OpenRouter's OpenAI-compatible
`/chat/completions` endpoint using the `openai` Python SDK pointed at
`https://openrouter.ai/api/v1`. The agent loop — request, execute tools, feed results
back, repeat — is about forty lines we own, running over **only the tools we define**.
There is no built-in filesystem or shell access because there is no vendor harness to
supply one.

That absence is the security property, not a limitation. Three alternatives were
considered and rejected:

- **A vendor-specific harness** (Anthropic's Tool Runner, or any equivalent) — supplies
  the loop, but couples the app to one provider's SDK and wire format. OpenRouter's
  value is that the model is a config string; a provider-locked harness throws that
  away to save forty lines.
- **Hosted agent platforms** — the provider runs the loop *and* a remote sandbox. A
  remote sandbox cannot touch the user's local machine, which is the entire product.
- **A batteries-included coding-agent SDK** — built-in Bash/Read/Write. Fastest to a
  demo, but it is a raw-shell agent wearing a permission system. That is the model
  rejected in favour of a curated catalog, and it puts `rm -rf` one confused approval
  away from a non-technical user.

Owning the loop turns out to help the part of this design that is actually novel. A
harness that yields per-turn forces an assumption about *when* it yields relative to
executing tools; get that wrong and the batched approval dialog (§4.3) silently
degrades into one dialog per action. With a hand-written loop the entire `tool_calls`
array is in hand before anything runs, so batching is correct by construction rather
than by hook ordering.

This was verified against the live model before the design was fixed: a single
create-folder-then-move-two-files request returned `finish_reason: "tool_calls"` with
three tool calls in one response. Parallel tool calling is the mechanism the whole
"control multiple things at once" premise rests on, and it works here.

**Provider portability.** `policy/`, `catalog/`, and `platform/` never see a model, a
message, or a request. Only `agent/session.py` knows the wire format. Changing model
or provider is a change to that one file plus a config string.

### Why Python + GTK4

Python because Linux desktop automation is a Python-native problem: PyGObject binds
GTK4, libadwaita, **and** GIO's D-Bus client. One dependency covers UI, portals, and
system messaging. The equivalent TypeScript path would call the same D-Bus interfaces
through a worse binding layer, or split the project into two languages.

GTK4 + libadwaita specifically: it is the GNOME-native toolkit, so the app looks like
it belongs on the target desktop; Flatpak ships a first-class GNOME runtime that
already contains it, so packaging adds nothing; and it is the same PyGObject import
already required for portals.

Packaged as a **Flatpak**. XDG portals then handle file access, screenshots, and
notifications through permission prompts the desktop already knows how to show.

---

## 3. The Action Catalog

Sixteen functions. This list is exhaustive for v0.1 — the agent cannot perform any
action absent from this table. That is what "safe by construction" means, and it is
checkable by reading one file.

**Tier** is the permission tier (§4). **Sandboxed** means the path arguments are
subject to the path sandbox (§4.2).

| # | Function | Arguments | Tier | Sandboxed |
|---|---|---|---|---|
| 1 | `list_apps` | — | auto | — |
| 2 | `open_app` | `name` | auto | — |
| 3 | `open_path` | `path` | auto | yes |
| 4 | `open_url` | `url` | auto | — |
| 5 | `search_files` | `query`, `location`, `kind` | auto | yes |
| 6 | `read_text_file` | `path` | auto | yes |
| 7 | `list_folder` | `path` | auto | yes |
| 8 | `read_clipboard` | — | auto | — |
| 9 | `notify` | `title`, `body` | auto | — |
| 10 | `set_volume` | `percent` | auto | — |
| 11 | `write_clipboard` | `text` | confirm | — |
| 12 | `create_folder` | `path` | confirm | yes |
| 13 | `write_text_file` | `path`, `content` | confirm | yes |
| 14 | `copy_file` | `source`, `destination` | confirm | yes |
| 15 | `move_file` | `source`, `destination` | confirm | yes |
| 16 | `trash_file` | `path` | confirm | yes |

### The two openers are restricted, not merely sandboxed

`open_path` and `open_url` hand their argument to the desktop's default handler. Left
unrestricted at `auto` tier they are an execution path that never reaches the approval
dialog — a `.desktop` file, an executable script, or an AppImage in `~/Downloads`
*launches* rather than opens. That would make §9's criterion 7 false.

- **`open_path`** refuses any target that is a `.desktop` entry, has the executable bit
  set, or carries a known script extension. Documents, media, and folders only. A
  refusal returns `"I can only open documents and folders, not programs."`
- **`open_url`** accepts `http` and `https` only. `file://` re-enters the same hole
  through the browser, and custom scheme handlers launch registered applications with
  argument values the agent chose.

These restrictions matter more than they look, because of where untrusted text enters.
`read_text_file` and `search_files` are `auto` tier and pull file *content* into
context. A file containing "open the installer in Downloads" is an injection attempt.
Against the rest of the catalog the tier system handles this well — an injected
instruction to write, move, or trash lands in the confirm dialog, described in plain
language, and the user sees an action they did not ask for. The openers were the one
gap in that argument. Restricting them closes it.

### Deliberate absences

- **No `delete_file`.** `trash_file` moves to the XDG trash. Every destructive action
  in v0.1 is reversible by the user through their file manager. There is no code path
  that permanently destroys data.
- **No shell, no `run_command`, no `sudo`.** Not gated — absent.
- **No network requests beyond `open_url`,** which hands the URL to the default
  browser rather than fetching it.
- **No window management.** Wayland deliberately denies applications the ability to
  enumerate or focus other windows, and the compositor-specific workarounds are
  fragile. Deferred rather than half-built.
- **No `take_screenshot`.** The portal makes it possible, but the agent cannot see
  images in a text-only v0.1, so it would only produce files. Deferred to the vision
  phase.

### Tool descriptions are part of the design

Each function's docstring becomes the tool description the model reads. These are written
for the model, not for developers: they state what the action does, what the arguments
mean, and — critically — when *not* to use it. `move_file` says it cannot overwrite
without confirmation; `search_files` says it searches the user's home directory only.

---

## 4. Permission Model

This is the load-bearing component. An agent that can touch a local filesystem on
behalf of a non-technical user lives or dies here.

### 4.1 Tiers

Three tiers, assigned per function in the table above. The assignment lives in one
table in `policy/`, not scattered across the catalog.

| Tier | Rule | Rationale |
|---|---|---|
| **auto** | Runs without asking. | Read-only or trivially reversible. Prompting here trains the user to click through prompts, which destroys the value of the confirm tier. |
| **confirm** | Requires explicit approval before running. | Mutates or creates something on disk or in the clipboard. |
| **never** | Not implemented. | See "Deliberate absences". |

There is no "always allow" for the confirm tier in v0.1. A remembered blanket approval
for `move_file` is indistinguishable from having no gate. Per-action memory is a
roadmap item that needs its own design.

### 4.2 Path sandbox

Every `path`, `source`, and `destination` argument is resolved (symlinks followed,
`..` collapsed) and checked before the function body runs:

- **Allowed:** anything under `$HOME`.
- **Denied:** `~/.ssh`, `~/.gnupg`, `~/.config/ZeroOS`, `~/.local/share/ZeroOS`,
  `~/.local/share/keyrings`, and any dotfile directory matching a small denylist. Also
  everything outside `$HOME`.

ZeroOS's own log directory is on the denylist deliberately: without it the agent can
read its own action log at `auto` tier, which is both a privacy leak and a way for
earlier-session content to re-enter context unbidden.

A denied path returns a normal tool result — `"That location is off limits."` — not an
exception. The model reads it and explains to the user rather than crashing.

The denylist is checked *after* symlink resolution, so a symlink from
`~/Documents/keys` to `~/.ssh` does not bypass it.

### 4.3 Batched approval — "control multiple things at once"

The model emits multiple entries in `tool_calls` in a single response. This is how
ZeroOS controls several things at once — verified live on `qwen/qwen3.7-flash`, three
calls in one response. It also creates the one genuinely novel UX problem in v0.1.

The naive design shows one modal dialog per pending action. Ask a user to approve five
dialogs in a row and by the third they are clicking Approve without reading. The
permission gate then measures nothing.

**v0.1 behaviour:**

1. All `auto`-tier calls in the turn execute immediately, concurrently.
2. All `confirm`-tier calls in the turn are collected and presented in **one dialog**
   listing every pending action in plain language.
3. The user picks: **Do all**, **Deny all**, or unticks individual rows and confirms
   the rest.
4. Denied actions return `"The user declined this action."` as their tool result. The
   model sees the denial and adapts — it does not retry the same call.

Here "turn" means **one model response**, not one user message. A request the model
answers in several rounds — create a folder, look at what landed in it, then move
files — asks once per round, because the second round's actions do not exist while
the first dialog is open. Nothing can batch approval for an action not yet proposed.
The guarantee is that every `confirm` action the model proposes *at the same time* is
shown together, and that the user is never asked twice about the same action.

Ordering: within a turn, approved `confirm` actions execute sequentially in the order
the model emitted them, because file operations can depend on each other (create the
folder, then move files into it). `auto` actions have no such dependency and run in
parallel.

### 4.4 Dialog copy

Written for someone who does not know what a path is. Actions are described by intent,
not by function signature.

> **ZeroOS wants to do 3 things**
>
> - ☑ Create a folder called **Tax 2025** in **Documents**
> - ☑ Move **4 files** from **Downloads** into **Documents / Tax 2025**
> - ☑ Save a note called **checklist.txt** in **Documents / Tax 2025**
>
> Files moved to the trash can be restored. ZeroOS never permanently deletes anything.
>
> [ Deny all ]                                        [ Do these 3 things ]

Rules for this copy: folder names in bold, never full paths; counts instead of file
lists past three items (with an expander); no jargon ("move" not "mv", "folder" not
"directory"); the reassurance line about trash is permanent, not conditional.

---

## 5. Data Flow

One turn, end to end:

1. User types into the GTK window. Text goes to `agent/`.
2. `agent/` appends it to conversation state and posts to OpenRouter with the system
   prompt, the catalog schemas, and the message history.
3. The model responds with text and/or a `tool_calls` array.
4. Before execution, `policy/` partitions the calls by tier and runs the path
   sandbox check on every path argument.
5. `auto` calls execute concurrently. `confirm` calls are passed to `agent/`'s
   approval callback as a single batch; in the app that callback shows the dialog and
   returns the user's choices.
6. Approved calls execute sequentially through `catalog/`, which calls `platform/`.
7. All results — successes, errors, denials, sandbox refusals — go back as tool
   results. The loop continues.
8. When `finish_reason` is no longer `"tool_calls"`, the final text renders in the
   window.

Conversation state is in-memory and per-session. Closing the window discards it. That
is a v0.1 simplification, not a permanent decision — see the roadmap's memory phase.

### Model configuration and cost

| Setting | Value | Why |
|---|---|---|
| Model | `qwen/qwen3.7-flash` | Tool-capable, 1M context, cheapest tier that plans multi-step file work |
| `max_tokens` | 4096 | A turn is a short reply plus a handful of tool calls. The model's ceiling is 65,536; nothing here needs it, and a low cap bounds a runaway loop |
| `reasoning` | left at the model's default | The measured turn spent 256 reasoning tokens unprompted and planned correctly. No reason to pay to raise it or risk lowering it |
| `tool_choice` | `"auto"` | The model must be free to answer without acting |

Pricing is $0.03 per million prompt tokens and $0.13 per million completion tokens. The
measured three-action turn used 400 prompt and 379 completion tokens: **$0.00006**.
A heavy day of a hundred such turns is under a cent.

**No prompt caching in v0.1.** The system prompt plus sixteen tool schemas is a large
byte-identical prefix and is the textbook case for it, but the measured turn reported
`cached_tokens: 0` and cost six thousandths of a cent. Optimizing that is work with no
payoff. The usage block reports `cached_tokens` on every response; if conversations
grow long enough for prompt size to matter, measure there first.

This cost profile is the single biggest consequence of the model choice, and it changes
the pre-launch billing gate in the roadmap — see §7.

---

## 6. Error Handling

The governing rule: **catalog functions never raise into the agent loop.** Every
failure becomes a tool result string the model can read and act on.

| Failure | Result |
|---|---|
| Path outside sandbox | `"That location is off limits."` |
| File not found | `"No file at that location."` |
| Destination exists | `"A file with that name is already there."` — model asks the user how to proceed |
| Permission denied by OS | `"The system wouldn't allow that."` |
| User declined in dialog | `"The user declined this action."` |
| Portal request rejected | `"The desktop didn't grant permission for that."` |
| Unexpected exception | Caught at the catalog boundary, logged, returned as `"That didn't work."` |

Failures that are *not* the model's problem surface in the UI instead:

- **API errors** (network, rate limit, invalid key) — an inline banner with a Retry
  button. The turn is not lost; the message stays in the box.
- **Missing or invalid API key** — routes back into onboarding.

Logging: every tool call, its arguments, its tier, the approval decision, and its
result go to a local rotating log at `~/.local/share/ZeroOS/`. Arguments are logged
with two exemptions — `write_text_file`'s `content` and `write_clipboard`'s `text` are
recorded as a byte count only, since those arguments *are* file content. Nothing reads
back the body of a file into the log. The log is the only way to answer "what did it
actually do", which a non-technical user will ask the moment something surprises them.

---

## 7. API Key and Billing

**v0.1 assumption:** the user supplies their own OpenRouter API key. There are two ways
the key reaches the app, and both are needed.

| Path | Source | Who uses it |
|---|---|---|
| Development | `OPENROUTER_API_KEY` and `OPENROUTER_BASE_URL` from the environment | The developer, running from a checkout |
| Shipped app | System keyring via libsecret through the Secret Service portal, entered during onboarding | Everyone else |

The environment path is checked first and skips onboarding entirely when set. This is
not a convenience — a Flatpak runs in a sandbox that cannot read the developer's shell
profile, so without the keyring path the shipped app has no key at all, and without the
environment path dogfooding means retyping a key into a dialog. The key is never
written to a config file and never enters the conversation.

Startup validates the key with `GET /api/v1/key`, which returns the key's own limit and
usage. A 401 routes into onboarding; a network failure shows the retry banner from §6
and does not discard the key.

**On billing.** The stated audience does not casually obtain an API key, so v0.1's
bring-your-own-key is honestly a dogfooding and early-tester posture, not a shippable
one. What the model choice changes is the *cost* of the alternative: at $0.00006 per
turn, a hosted proxy absorbing usage for a hundred users at a hundred turns a day is
under twenty cents a day. Proxying is no longer unaffordable — it is now purely an
architectural objection, since a proxy contradicts the "local only, zero hosting"
constraint that makes v0.1 buildable at all.

That is a real gate and it stays a gate; the roadmap carries the three candidate shapes
and their consequences. v0.1 ships bring-your-own-key and does not block on it.

Onboarding therefore has to do real work: explain what a key is, link directly to the
console page that creates one, validate it with a cheap call before accepting it, and
state plainly that usage costs money and roughly how much.

---

## 8. Testing

Three levels, matched to the three things that can break.

**Catalog functions** — each gets unit tests against a temporary directory. These are
straightforward: does `move_file` move, does `trash_file` land the file in the XDG
trash, does `search_files` respect its location argument. Portal-backed functions are
tested against a stub portal.

**The policy gate** — table-driven tests, and the most important suite in the project.
Every catalog function has a tier assertion, so adding a function without a tier fails
a test. The path sandbox gets adversarial cases: `..` traversal, absolute paths outside
`$HOME`, symlinks pointing into `~/.ssh`, symlinks pointing outside `$HOME`, paths
that resolve differently before and after normalization. If exactly one suite is kept,
this is it.

**One end-to-end test** — a stubbed model that emits a fixed sequence of `tool_use`
blocks, including a mixed-tier turn, driving the full loop with the dialog auto-answered.
This proves the batching, ordering, and denial paths work together, which unit tests
cannot show.

Not tested in v0.1: GTK widget rendering, and model output quality. The first needs
tooling out of proportion to the payoff; the second is evaluated by hand against the
success criteria below.

---

## 9. Success Criteria

v0.1 is done when all of the following hold:

1. All sixteen catalog functions are implemented, each with a tier and unit tests.
2. The policy gate suite passes, including every adversarial path case in §8.
3. The batched approval dialog handles a mixed-tier turn: `auto` actions run,
   `confirm` actions appear in one dialog, partial approval executes only the ticked
   rows, denials come back to the model as results.
4. `flatpak install` succeeds on a clean GNOME system and the app launches from the
   applications menu.
5. Onboarding takes a user from first launch to a working key without a terminal.
6. A non-technical tester, given only the app and no instructions, completes all three:
   - "Find the PDF I downloaded yesterday and put it in a new folder called Taxes"
   - "What's in my Downloads folder? Delete the ones I don't need" *(exercises the
     dialog, trash semantics, and multi-action batching)*
   - "Open my music player and turn the volume down"
7. No code path can perform an action outside the catalog table.

Criterion 6 is the real one. The others are necessary; that one is the product.

---

## 10. Open Items

Two, both resolved with stated assumptions rather than left dangling:

- **Billing model** (§7) — v0.1 assumes bring-your-own-key. Pre-launch gate in the
  roadmap.
- **Conversation memory** (§5) — v0.1 assumes per-session, discarded on close. The
  memory phase in the roadmap revisits it.

Nothing else in this document is TBD. If something reads as ambiguous during
implementation planning, that is a spec bug — fix it here first.
