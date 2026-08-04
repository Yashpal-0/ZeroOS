# ZeroOS

A text-driven assistant that operates your Linux desktop through a fixed catalog of
safe actions.

Type what you want in plain language. ZeroOS finds files, moves them, opens apps,
manages your clipboard — several at a time — and asks before it changes anything.

It is not an operating system. It is a desktop app with an agent loop, a permission
gate, and eighteen audited actions. It has no shell access and no way to permanently
delete a file.

## Install

```bash
flatpak-builder --force-clean --install --user build packaging/io.zerostic.ZeroOS.yml
flatpak run io.zerostic.ZeroOS
```

On first launch ZeroOS asks for an OpenRouter API key. Usage is billed by
OpenRouter and costs a fraction of a penny per request; see
[the design spec](docs/superpowers/specs/2026-08-02-zeroos-v01-design.md#7-api-key-and-billing).

## What it remembers

ZeroOS can keep up to 150 short facts about you — where your documents live, how
you like to be addressed — and puts them in front of the model on every turn.

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

## Documentation

- [v0.1 design spec](docs/superpowers/specs/2026-08-02-zeroos-v01-design.md) — architecture, action catalog, permission model, success criteria
- [v0.2 design spec](docs/superpowers/specs/2026-08-03-zeroos-v02-design.md) — memory, transcript, the recall pane, prompt-injection defences
- [v0.2 acceptance pass](docs/acceptance-2026-v02.md) — the evidence for each criterion, including what could not be shown
- [Roadmap](docs/roadmap.md) — subsystem decomposition, build order, deferred features, pre-launch gates

## v0.2 at a glance

| | |
|---|---|
| Input | Text only |
| Reach | Local machine only — no accounts, no server |
| Actions | 18 curated functions. No shell. No permanent delete. |
| Memory | Up to 150 facts, 300 characters each, every one approved by hand |
| Platform | Linux desktop (GNOME-first), shipped as a Flatpak |
| Built with | Python, GTK4 + libadwaita, `qwen/qwen3.7-flash` via OpenRouter |
