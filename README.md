# ZeroOS

A text-driven assistant that operates your Linux desktop through a fixed catalog of
safe actions.

Type what you want in plain language. ZeroOS finds files, moves them, opens apps,
manages your clipboard — several at a time — and asks before it changes anything.

It is not an operating system. It is a desktop app with an agent loop, a permission
gate, and sixteen audited actions. It has no shell access and no way to permanently
delete a file.

**Status:** pre-implementation. Design only.

## Documentation

- [v0.1 design spec](docs/superpowers/specs/2026-08-02-zeroos-v01-design.md) — architecture, action catalog, permission model, success criteria
- [Roadmap](docs/roadmap.md) — subsystem decomposition, build order, deferred features, pre-launch gates

## v0.1 at a glance

| | |
|---|---|
| Input | Text only |
| Reach | Local machine only — no accounts, no server |
| Actions | 16 curated functions. No shell. No permanent delete. |
| Platform | Linux desktop (GNOME-first), shipped as a Flatpak |
| Built with | Python, GTK4 + libadwaita, `qwen/qwen3.7-flash` via OpenRouter |
