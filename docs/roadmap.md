# ZeroOS Roadmap

What ZeroOS is trying to become, in what order, and what deliberately is not being
built yet. The current phase is specified in
[`docs/superpowers/specs/2026-08-02-zeroos-v01-design.md`](superpowers/specs/2026-08-02-zeroos-v01-design.md).

---

## The decomposition

"An Agent OS that works like JARVIS" is four independent subsystems. Each needs its
own spec, plan, and build cycle. Naming them separately is what keeps any one phase
shippable.

| # | Subsystem | What it is | Status |
|---|---|---|---|
| 1 | **Agent runtime** | The loop: text in, plan, tool calls, response. Conversation state, model config, cost control. | v0.1 |
| 2 | **Surface** | How the user talks to it: window, onboarding, permission dialog, packaging. | v0.1 |
| 3 | **Permissions & credentials** | What the agent may do, what it must ask about, where secrets live. | v0.1 (permissions) / later (third-party credentials) |
| 4 | **Integration layer** | Reach beyond the local machine: third-party services, MCP servers, plugins. | Later |

Subsystem 3 is split deliberately. Local permissions are v0.1 and load-bearing.
Third-party *credentials* — OAuth, token refresh, revocation, per-service scopes —
only exist once subsystem 4 does, and they are the thing that kills projects of this
shape at launch. Not the agent loop. Credentials.

---

## Build order

Each phase assumes the one before it shipped and was used by real people.

### v0.1 — Local desktop agent *(current)*

Text in, sixteen curated actions, batched permission dialog, GTK4 + Flatpak, Linux
only. Bring-your-own API key.

Success is a non-technical tester completing file and app tasks without a terminal.
Full criteria in the spec.

### v0.2 — Memory and recall

Conversation persists across sessions. The agent remembers stated preferences
("my documents live in ~/Work") and prior context.

Real problems to solve: what is remembered versus what is transcript, how the user
inspects and deletes memory, and what memory does to prompt size. v0.1 sends a fixed
prefix and does not cache. Memory makes the prefix grow and vary per session, which is
both the thing that raises cost and the thing that would defeat caching if it is ever
added — so memory belongs *after* the fixed block, not inside it.

### v0.3 — MCP servers

Third-party reach without a bespoke integration for each service. MCP is already the
industry standard for this; building a proprietary tool-registry instead is the most
likely way this project dies of maintenance.

The design already accommodates it: an MCP server advertises tools as JSON Schema, which
is the same shape `agent/` already sends for the catalog. Mounting a server means
appending to the tools list and routing its calls to the server instead of a local
function. The curated catalog and the MCP ecosystem are not competing designs — same
door.

Genuinely hard part, and the reason this is its own phase: MCP tools arrive with
**unknown permission tiers**. The v0.1 model assigns tiers by hand at author time.
That does not survive contact with arbitrary servers. Needs its own spec.

### v0.4 — Credentials

OAuth flows, token storage and refresh, per-service scopes, revocation, and a UI that
lets a non-technical user understand and undo what they granted.

Only meaningful once v0.3 gives the agent something to authenticate against. Assume
this phase is larger than it looks.

### v0.5 — Voice

The originally deferred input mode. Speech to text feeding the existing loop, and
optionally text to speech out.

The interesting design problem is not transcription — it is that voice removes the
opportunity to read a permission dialog. Either confirmations become spoken and
explicitly acknowledged, or voice is restricted to `auto`-tier actions. Do not
retrofit this into v0.1's dialog.

---

## Deferred, with reasons

Not "someday maybe" — each is a real feature with a reason it is not now.

| Feature | Why not yet |
|---|---|
| **Multi-agent / subagents** | Solves a problem v0.1 does not have. A single loop over sixteen tools does not need delegation. Revisit only when a real task demonstrably exceeds one context. |
| **Scheduled and background tasks** | Requires a daemon, a scheduler, and a permission story for actions taken while the user is absent — which is a different and harder consent problem. |
| **Parallel task graph** | v0.1 already executes multiple tool calls per turn. A dependency graph across turns is speculative until a workload demands it. |
| **Computer use / screen control** | The direct opposite of the curated catalog. Powerful, unbounded, and unauditable — reconsider only if the catalog approach demonstrably hits a ceiling. |
| **Windows and macOS** | Every catalog function is OS-specific plumbing. Porting means rewriting `platform/`, which is the point of isolating it, but it doubles the surface to test. |
| **Plugin system** | A plugin system before MCP would be inventing a worse MCP. |
| **Cloud sync** | Contradicts the local-only constraint and introduces a backend. |

---

## Pre-launch gates

Things that do not block building but do block calling it launched.

### Billing model — must be decided before public release

v0.1 assumes bring-your-own API key. That is fine for testers and wrong for the stated
audience. Three shapes, each with a real cost:

| Shape | What it means | Cost |
|---|---|---|
| **Bring your own key** *(v0.1)* | User creates an OpenRouter key, pastes it in. | Free to build. Contradicts the non-technical premise — most of this audience will not get past it. |
| **Proxy, absorbed cost** | ZeroOS routes through a backend on the developer's key. | Needs a backend, which contradicts "local only, zero hosting". Inference is cheap enough not to be the objection — see below. |
| **Subscription with proxy** | Backend plus auth plus billing plus quota. | Viable business. Is a second project in its own right, larger than v0.1. |

**The cost objection to proxying is gone; the architectural one is not.** At
`qwen/qwen3.7-flash` pricing, a measured three-action turn costs $0.00006. A user doing
a hundred turns a day costs about **$0.18 a month**; a thousand such users cost about
**$180 a month**, and hosting the proxy would likely exceed the inference bill. That
kills the "unbounded cost" argument this table previously made.

What remains is that a proxy makes the app no longer local-only, which is a design
change, not a budget one. Absorbed cost is now the *cheapest* option to run and the
*most expensive* option to build. Decide before v0.2 is planned, not at launch.

Two things this leaves open: abuse control (an absorbed-cost proxy with no auth is a
free inference endpoint the moment anyone points a script at it), and the fact that the
cost estimate above assumes turns stay small. Conversation memory in v0.2 grows the
prompt every turn, and prompt tokens are the side that scales.

### Others

- **Cost transparency in the UI.** Deliberately *not* built for v0.1. At $0.00006 a
  turn, a running cost display would show `$0.00` for weeks and teach the user nothing.
  It becomes necessary if v0.2 memory grows prompts materially, or if a proxy makes
  someone else's budget the one being spent.
- **Crash and error reporting.** Currently a local log file. Fine for dogfooding,
  insufficient once testers exist and cannot read it.
- **Form of address is hardcoded.** The v0.1 system prompt addresses the user as "Sir",
  which is right for a single-developer dogfooding build and wrong the moment anyone
  else runs it. Make it a preference — with a neutral default — before testers exist.
- **A written trust story.** "What can this app do to my files?" needs a plain-language
  answer on the project page, backed by the fact that the catalog is sixteen readable
  functions.

---

## The bet

The core wager is that a **fixed, auditable catalog** beats an unbounded shell agent
for non-technical users — that the ceiling of "it only does what was written" is
higher in practice than the floor of "it can do anything, and sometimes does the wrong
anything."

If that is wrong, the signal will be users constantly asking for things the catalog
cannot express. That signal is worth watching from the first tester onward.
