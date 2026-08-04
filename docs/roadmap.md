# ZeroOS Roadmap

What ZeroOS is trying to become, in what order, and what deliberately is not being
built yet. v0.1 is specified in
[`docs/superpowers/specs/2026-08-02-zeroos-v01-design.md`](superpowers/specs/2026-08-02-zeroos-v01-design.md)
and built, as is
[v0.2](superpowers/specs/2026-08-03-zeroos-v02-design.md) and its point release
[v0.2.1](superpowers/specs/2026-08-04-zeroos-v021-memory-design.md). The next
phase is v0.3, MCP servers, unspecified as yet.

---

## The decomposition

"An Agent OS that works like JARVIS" is six independent subsystems. Each needs its
own spec, plan, and build cycle. Naming them separately is what keeps any one phase
shippable.

| # | Subsystem | What it is | Status |
|---|---|---|---|
| 1 | **Agent runtime** | The loop: text in, plan, tool calls, response. Conversation state, model config, cost control. | v0.1, extended v0.2 (approved facts, transcript, usage counts) and v0.2.1 (noticing pass, closing summary) |
| 2 | **Surface** | How the user talks to it: window, onboarding, permission dialog, packaging. | v0.1, extended v0.2 (recall pane) and v0.2.1 (unticked memory rows) |
| 3 | **Permissions & credentials** | What the agent may do, what it must ask about, where secrets live. | v0.1 (permissions) / later (third-party credentials) |
| 4 | **Integration layer** | Reach beyond the local machine: third-party services, MCP servers, plugins. | Later |
| 5 | **Perception** | What it can sense without being told: active window, calendar, notifications, screen text, room audio. Read-only. | Later |
| 6 | **Autonomy** | Acting without a human present: trust that is earned rather than asked for, unattended work, explaining afterwards. | Later |

Persistence is deliberately **not** a seventh subsystem. What v0.2 added is state
inside subsystem 1 and a pane inside subsystem 2 — a store with no loop of its own
and no surface of its own. Listing it separately would suggest it is shippable
separately, which is the one thing this table exists to say about a subsystem.
v0.2.1's noticing pass does not change that: it is another call inside subsystem 1's
loop, feeding the dialog subsystem 2 already had.

Subsystem 3 is split deliberately. Local permissions are v0.1 and load-bearing.
Third-party *credentials* — OAuth, token refresh, revocation, per-service scopes —
only exist once subsystem 4 does, and they are the thing that kills projects of this
shape at launch. Not the agent loop. Credentials.

Subsystems 5 and 6 are what separates an assistant from JARVIS, and they are listed
last because neither is safe to build before the four above it exist. Perception
without memory has nothing to relate what it sees to; autonomy without perception is
a scheduler guessing at intent.

---

## Build order

Each phase assumes the one before it shipped and was used by real people.

### v0.1 — Local desktop agent *(shipped)*

Text in, sixteen curated actions, batched permission dialog, GTK4 + Flatpak, Linux
only. Bring-your-own API key.

Success is a non-technical tester completing file and app tasks without a terminal.
Full criteria in the spec. Acceptance:
[`docs/acceptance-2026-v01.md`](acceptance-2026-v01.md).

### v0.2 — Memory and recall *(current)*

Conversation persists across sessions. The agent remembers stated preferences
("my documents live in ~/Work") and prior context.

Real problems to solve: what is remembered versus what is transcript, how the user
inspects and deletes memory, and what memory does to prompt size. v0.1 sends a fixed
prefix and does not cache. Memory makes the prefix grow and vary per session, which is
both the thing that raises cost and the thing that would defeat caching if it is ever
added — so memory belongs *after* the fixed block, not inside it.

**Built.** Three kinds of persistence, deliberately separated: a capped list of
approved facts (injected every turn as a *second* system message, so the fixed
block stays byte-identical and a future cache breakpoint stays possible), a
transcript that is displayed but never sent, and a usage line of counts only.
`remember` and `forget` are both confirm-tier — memory adds no new action
surface, but it does let attacker-controlled file text persist into a
privileged position, and an automatic `forget` would let injected text erase a
constraining memory. The recall pane exists so a carelessly-approved fact is
removable without a terminal. Catalog is now eighteen tools; suite 281 passing.

**Accepted except for the tester.** Criteria 1–8 are settled with citations.
The Flatpak now runs on `org.gnome.Platform//50`, and the §6 attack walk has
been run against the real model and a real dialog — it found one defect (an
oversized approval row ran off the edge of the dialog unwrapped) which is
fixed. What remains is criterion 9: two days with a non-technical tester. See
[`docs/acceptance-2026-v02.md`](acceptance-2026-v02.md) — criterion 9 is the
one that decides whether memory is a feature or a liability, and nothing
mechanical can stand in for it.

Specified in
[`docs/superpowers/specs/2026-08-03-zeroos-v02-design.md`](superpowers/specs/2026-08-03-zeroos-v02-design.md).

### v0.2.1 — Noticing and continuity *(shipped)*

v0.2 could remember; it could not notice. Every fact arrived because someone
typed a sentence that made the model reach for `remember`, which is a store
with a consent gate rather than an assistant that pays attention. This release
closes that gap without touching the gate.

**Built.** A noticing pass runs after each turn over the filtered transcript
and proposes up to two facts, surfaced at the start of the *next* turn so the
user has read the reply before being asked about it. A closing pass does the
same for the end of a session. Every proposed row arrives **unticked** — an
unread dialog now stores nothing, which is what makes proposing safe enough to
do at all. A declined fact is not raised again for the rest of that session.
The cap went from 50 × 200 to 950 × 1000. Suite 317 passing; catalog unchanged
at eighteen tools.

**Why a point release and not a phase.** It adds no subsystem and no action
surface. `remember` and `forget` are the same two confirm-tier tools v0.2
shipped; what changed is who initiates the call. Numbering it v0.3 would have
claimed the MCP slot below for work that never touched integration.

**The security boundary is the noticing filter.** The pass sees a rebuilt
transcript of `role` and `content` only — every `role == "tool"` message is
dropped, so file contents cannot drive what gets proposed. That filter is the
single most important test in the release, and the reasoning is spec §4 and §8.

Not accepted. Eight criteria, all unconfirmed, in
[`docs/acceptance-2026-v021.md`](acceptance-2026-v021.md) — four of them can
only be settled by sitting with the app, because what is being judged is
whether unrequested proposals read as attention or as nagging, and nothing
mechanical answers that.

Specified in
[`docs/superpowers/specs/2026-08-04-zeroos-v021-memory-design.md`](superpowers/specs/2026-08-04-zeroos-v021-memory-design.md).

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
That does not survive contact with arbitrary servers. Resolved by making every
mounted tool confirm-tier, and by adding a `run_command` shell tool alongside —
specified in
[`docs/superpowers/specs/2026-08-04-zeroos-v03-mcp-design.md`](superpowers/specs/2026-08-04-zeroos-v03-mcp-design.md).

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

### v0.6 — Presence

The agent stops being an app you open. A daemon, a morning briefing, and the ability
to speak first: *"Your Downloads folder has three hundred files in it."*

The hard problem is not generating remarks — it is **suppression**. An assistant that
surfaces everything it notices is a nag wearing a butler's voice, and the failure is
silent, because the user simply stops reading. Whatever ships must have an explicit
policy for what is worth interrupting for, and that policy needs to be as inspectable
as the action log.

Cheap probe available much earlier: `notify` is already in the v0.1 catalog, and a
timer plus that tool is most of the sensation at a fraction of the work. Worth pulling
forward as an experiment rather than waiting for the daemon.

### v0.7 — Awareness

Read-only senses: active window, calendar, incoming notifications, text on screen.

**This does not break the catalog bet, and the distinction is the whole reason it is
its own phase.** Screen *reading* and screen *control* are different objects. The
catalog bounds what the agent can *do*; a sensor adds no action to it. Reading carries
a privacy cost, which is bounded, auditable, and can be switched off per source.
Control carries unbounded action, which is the thing being refused. The deferred list
below previously merged them and cost a version.

What has to be designed: which sources are on by default (none), how the user sees
what was sensed, and whether sensed text is admissible as instruction — it is not,
for the same reason file contents are not, and the surface is much larger here.

### v0.8 — Autonomy

Trust that is earned rather than requested. An action class approved repeatedly with
no rejections graduates from `confirm` to `auto` — visibly, revocably, with the action
log as the receipt. Unattended and long-running work becomes possible because the
per-action dialog is no longer the only consent mechanism.

This is the phase where the product either becomes JARVIS or becomes a nag, and it is
a trust model rather than a feature. Two things it must ship with: explainability
(*"why did you do that"* stops being optional the moment nobody was watching), and a
graduation rule conservative enough that a single bad promotion is survivable.

Note this phase inverts v0.1's founding sentence — "You ask before you act." It does
not discard it; it defines the conditions under which the asking has already happened.
That argument should be written down before any code is.

### v0.9 — Reach

The physical world: lights, thermostats, media, whatever the house exposes. Mostly an
MCP consumption problem rather than new architecture, which is why it sits after v0.3.

Device continuity — the same agent in the laptop, the phone, the room — belongs here
too, and is the point at which local-only stops being true. Treat it as a separate
go/no-go, not a feature of this phase.

### v1.0 — Ambient

Always listening, identity-aware, interruptible mid-sentence.

Ordered last for a security reason, not a difficulty one: always-listening without
identity is a microphone that takes commands from anyone in the room. Speaker identity
is the gate on this phase, not a refinement of it.

---

## Cross-cutting

Three concerns thread through every phase above rather than landing in one. Tracked
here so they are not rediscovered per release.

- **Opinion.** *"I'd advise against that, Sir."* The v0.1 prompt tells the agent to
  accept refusal without argument, which is right for a tool and wrong for an
  assistant. This is a prompt change and close to free — the largest amount of
  character per byte available anywhere in this document. Ship it whenever.
- **Latency.** Every phase makes it worse, and conversational presence is the first
  thing to die. Budget it as a standing constraint, not a task.
- ~~**Implicit learning.**~~ **Closed in v0.2.1.** JARVIS was never told anything with
  a `remember` tool, and now neither is this — a noticing pass proposes facts nobody
  asked it to. The gate this entry said it needed turned out to be two rules rather
  than a mechanism: every proposed row arrives unticked, so an unread dialog stores
  nothing, and a declined fact is not raised again that session. The consent model is
  not inverted, it is inverted *and* weakened deliberately, which spec §8 argues is a
  mitigation rather than a repair. What remains open is whether it reads as attention
  or as nagging, which is acceptance criteria 1, 2, and 8, not a design question.

---

## Deferred, with reasons

Not "someday maybe" — each is a real feature with a reason it is not now.

| Feature | Why not yet |
|---|---|
| **Multi-agent / subagents** | Solves a problem this design does not have. A single loop over eighteen tools does not need delegation. Distinct from v0.8's unattended work, which is one agent running unwatched, not several coordinating. Revisit only when a real task demonstrably exceeds one context. |
| **Parallel task graph** | v0.1 already executes multiple tool calls per turn. A dependency graph across turns is speculative until a workload demands it. |
| **Screen and input *control*** | Synthesising keystrokes and clicks is the direct opposite of the curated catalog: unbounded, unauditable, and impossible to preview honestly in an approval dialog — "click at (840, 210)" tells the user nothing. Note this is **not** the same as screen *reading*, which is v0.7 and adds no action surface. Reconsider only if the catalog approach demonstrably hits a ceiling. |
| **Windows and macOS** | Every catalog function is OS-specific plumbing. Porting means rewriting `platform/`, which is the point of isolating it, but it doubles the surface to test. |
| **Plugin system** | A plugin system before MCP would be inventing a worse MCP. |
| **Cloud sync** | Contradicts the local-only constraint and introduces a backend. v0.9's device continuity is the same trade in a smaller wrapper and deserves the same scrutiny. |

*Scheduled and background tasks* previously sat in this table. They are now v0.6 and
v0.8 — the reason given for deferring them was the consent story for actions taken
while the user is absent, and that is exactly what v0.8 is for.

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
*most expensive* option to build.

**This was to be decided before v0.2 was planned. It was not, v0.2 is built, and
v0.2.1 shipped past it as well.** Nothing broke, because bring-your-own-key still
holds for a dogfooding build — but the deadline has now been missed twice, and a
missed deadline that costs nothing twice is a deadline nobody believes. The
decision gates the first non-developer tester, who is v0.2 criterion 9, and two
releases have now been built without one.

One thing this leaves open: abuse control. An absorbed-cost proxy with no auth is a
free inference endpoint the moment anyone points a script at it.

**The prompt-growth worry attached here is resolved.** It assumed conversation memory
would grow the prompt every turn. It does not — a capped list of approved facts goes
out as a second system message, and the transcript is never sent at all. Growth is
bounded by the cap rather than by session length, and `usage.log` records the
per-session counts to check it against. v0.2.1 raised that cap from 50 × 200 to
950 × 1000 characters, which moves the ceiling and does not remove it; it also added
one extra model call per turn for the noticing pass, which is a real cost increase
this estimate does not yet include.

**The deeper problem is that the whole estimate assumes a human typing.** A hundred
turns a day is a rate limit imposed by hands. From v0.6 onward the agent runs without
one — a daemon that observes, considers, and occasionally speaks is inference with no
natural ceiling, and v0.7's sensors make each of those turns larger. This gate is
therefore not a pre-launch checkbox but the constraint that decides whether the
presence phases can exist at all. Whatever is decided for v0.2 should be checked again
against v0.6 before that phase is planned.

### Others

- **Cost transparency in the UI.** Deliberately *not* built for v0.1. At $0.00006 a
  turn, a running cost display would show `$0.00` for weeks and teach the user nothing.
  One of its two triggers is now settled: v0.2 memory does **not** grow prompts
  materially — the fact list is capped and the transcript is never sent. The other
  trigger stands, and is the only one that ever mattered: a proxy would make someone
  else's budget the one being spent.
- **Crash and error reporting.** Currently a local log file. Fine for dogfooding,
  insufficient once testers exist and cannot read it.
- ~~**Form of address is hardcoded.**~~ **Closed in v0.2.** It is a preference now,
  with a neutral default, changeable from the recall pane. The v0.1 prompt text is
  still shipped byte-for-byte as the "Sir" variant, because criterion 4 turns on that
  string not changing.
- **A written trust story.** "What can this app do to my files?" needs a plain-language
  answer on the project page, backed by the fact that the catalog is eighteen readable
  functions. v0.2 adds a second question to answer plainly — "what does it remember,
  and how do I make it forget?" — which the recall pane answers in the product but
  nothing answers on the page. v0.2.1 adds a third and harder one: "why did it just
  ask to remember something I never told it to?" A user who cannot answer that reads
  an unprompted proposal as the app going through their files, which is the opposite
  of the impression the noticing filter exists to earn.

---

## What no version delivers

The phases above are a route to something JARVIS-shaped. Four things are not on that
route, and saying so here prevents them being quietly promised later.

- **Absolute trust.** JARVIS never asks. v0.8 approaches that asymptotically and
  should never arrive: the log, the graduation rule, and the ability to revoke *are*
  the product. Since v0.3 this is not a preference but the last defence — with
  `run_command` in the catalog, an agent that stopped asking would be an
  unattended shell.
- **Cross-device continuity.** Achievable, but it ends local-only. That is a different
  product rather than a later one, which is why v0.9 flags it as its own go/no-go.
- **Genuine domain expertise.** "Design me a suit" is model capability, not
  architecture. Nothing in this roadmap moves it.
- **Reading the room.** Knowing that someone is frustrated and adjusting is the part
  of the fiction that is still fiction. Tone can be configured; it cannot be sensed.

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
