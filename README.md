# ZeroOS

A text-driven assistant that operates your Linux desktop through a fixed catalog of
safe actions.

Type what you want in plain language. ZeroOS finds files, moves them, opens apps,
manages your clipboard — several at a time — and asks before it changes anything.

It is not an operating system. It is a desktop app with an agent loop, a permission
gate, and nineteen audited actions. Every action is assigned a permission tier.

## Install

```bash
flatpak-builder --force-clean --install --user build packaging/io.zerostic.ZeroOS.yml
flatpak run io.zerostic.ZeroOS
```

On first launch ZeroOS asks for an OpenRouter API key. Usage is billed by
OpenRouter and costs a fraction of a penny per request; see
[the design spec](docs/superpowers/specs/2026-08-02-zeroos-v01-design.md#7-api-key-and-billing).

## What it remembers

ZeroOS remembers as many short facts about you as you care to approve — where your
documents live, how you like to be addressed. It is told the ten most relevant each
time it answers, and you can pin the ones it must never be without.

Nothing is remembered without you ticking a box that shows the full text first,
and nothing is forgotten without one either. Facts are the model's proposal; the
dialog is where they become real.

ZeroOS also proposes facts of its own — things you mentioned in passing that
look worth keeping. Those arrive in the same dialog as everything else, and
every memory box starts **unticked**, including ones you asked for out loud.
A dialog you close without reading stores nothing.

What it reads to make those proposals is what you typed and what it said
back. It never reads the contents of files it opened for you.

The list button in the header bar — it is tooltipped **What ZeroOS knows** —
opens a pane listing every stored fact
with a delete button beside it, the conversation transcript, and the form of
address. Deleting from that pane is you acting, not the model, so it does not go
through the approval dialog. Everything is removable there without a terminal.

The transcript is kept and displayed but is **never sent to the model** — the
model sees only the current conversation and the stored facts. A per-session
usage line records counts and timestamps only: no message text, no fact text, no
filenames.

## Servers

ZeroOS can reach beyond the local machine through MCP servers. The recall pane
lists every configured server with its live status — connecting, connected, or
not working with the server's last error. A delete button removes it, and a
three-field form (name, command or URL) adds one.

Every tool a server offers is confirm-tier: it asks before it runs. The
`run_command` shell tool joins the catalog at the same tier. Nothing a mounted
server offers runs unasked.

## Documentation

- [v0.1 design spec](docs/superpowers/specs/2026-08-02-zeroos-v01-design.md) — architecture, action catalog, permission model, success criteria
- [v0.2 design spec](docs/superpowers/specs/2026-08-03-zeroos-v02-design.md) — memory, transcript, the recall pane, prompt-injection defences
- [v0.2 acceptance pass](docs/acceptance-2026-v02.md) — the evidence for each criterion, including what could not be shown
- [Roadmap](docs/roadmap.md) — subsystem decomposition, build order, deferred features, pre-launch gates

## v0.2.1 at a glance

| | |
|---|---|
| Input | Text only |
| Reach | Local machine only — no accounts, no server |
| Actions | 19 curated functions, all permission-tiered. |
| Memory | Unlimited facts, 1000 characters each, every one approved by hand; ten sent per reply |
| Platform | Linux desktop (GNOME-first), shipped as a Flatpak |
| Built with | Python, GTK4 + libadwaita, `qwen/qwen3.7-flash` via OpenRouter |
