# ZeroOS v0.1 — Acceptance Pass

Spec §9 sets seven success criteria. This document records the evidence for
each. Criteria 1, 2, 3, and 7 are mechanical and were verified by the agent
against the test suite at HEAD `c1b32e5`. Criteria 4, 5, and 6 require a
human at the machine — a clean install, an onboarding run, and a real
non-technical tester — and are left blank here pending that pass.

**Suite state at HEAD:** `169 passed, 0 failed` across three consecutive runs
of `python -m pytest -q`. (Warnings are pre-existing PyGObject/asyncio
deprecation notices, unrelated to the product.)

---

## Criterion 1 — All sixteen catalog functions implemented, each with a tier and unit tests

**PASS (mechanical).**

`tests/test_registry.py::test_the_catalog_has_exactly_sixteen_tools` asserts
`len(tools) == 16`. `test_every_catalog_tool_has_a_tier` asserts no tool is
without a tier. Both pass. Every catalog module carries its own unit tests
(`test_catalog_files.py`, `test_catalog_openers.py`, `test_catalog_apps.py`,
`test_catalog_system.py`); the full 169-test suite exercises them.

## Criterion 2 — The policy gate suite passes, including every adversarial path case in §8

**PASS (mechanical).**

`tests/test_sandbox.py`: 19/19 pass, covering the adversarial path cases —
`..` traversal out of home, symlink into a denied directory, symlink pointing
outside home, SSH under a symlinked home before SSH exists, the action log
under a relocated `XDG_DATA_HOME`, the keyring directory under a relocated
`XDG_DATA_HOME`, the config dir under a relocated `XDG_CONFIG_HOME`, and null
bytes. `tests/test_gate.py` (the tier/decision suite) passes in full.

## Criterion 3 — Batched approval dialog handles a mixed-tier turn

**PASS (mechanical, unit-level).**

`tests/test_session.py::test_mixed_tier_turn_asks_once_and_runs_auto_tools`
verifies `auto` actions run without a dialog and `confirm` actions collect
into one. `test_partial_approval_runs_only_the_ticked_action` verifies only
the ticked rows execute. `test_declined_action_is_not_logged_as_executed`
verifies denials return to the model as results and are not logged as
executed. `tests/test_dialog.py` (10 tests) drives the real `Adw.AlertDialog`
across the main-loop/thread boundary and confirms dismissal routes to denial.

> **Caveat — batching has not been observed from the live model.** In both
> live runs during Task 13, `qwen/qwen3.7-flash` emitted a *single* tool call
> where the spec's §4.3 batching premise expects several (e.g. one
> `create_folder` instead of `create_folder` plus two `move_file`). The gate
> and dialog are batch-size-agnostic, so nothing is broken, but the
> batched-approval dialog — the feature the gate exists to serve — is
> unproven against real model output. See **Open Items** below.

## Criterion 4 — `flatpak install` succeeds on a clean GNOME system and the app launches from the applications menu

**PENDING — requires the build, which requires the toolchain.**

The Flatpak manifest (`packaging/io.zerostic.ZeroOS.yml`), desktop entry, and
metainfo are written, internally consistent, and hash-verified, but **the
manifest has never been built.** Two things block this:

1. `flatpak` and `flatpak-builder` are not installed on the build machine;
   installing them needs sudo (`sudo apt install flatpak flatpak-builder`),
   which is the user's call.
2. **Two dependencies build from Rust source.** `pydantic_core` and `jiter`
   are both pyo3/maturin Rust extensions; the offline sdist install forces a
   build needing `cargo` + `rustc`, which `org.gnome.Sdk//47` does not ship by
   default. The build will need
   `org.freedesktop.Sdk.Extension.rust-stable` added, or binary wheels
   permitted for those two packages. The implementer flagged
   `pydantic_core`; the reviewer caught that `jiter` is the same hazard, so
   expect *two* Rust builds, not one.

**To run this criterion** (once the toolchain is in place):

```
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install flathub org.gnome.Platform//47 org.gnome.Sdk//47
flatpak install flathub org.freedesktop.Sdk.Extension.rust-stable//24.08
flatpak-builder --force-clean --install --user build packaging/io.zerostic.ZeroOS.yml
```

Then launch from the applications menu, not the terminal. Record whether it
appeared without a logout.

## Criterion 5 — Onboarding takes a user from first launch to a working key without a terminal

**PENDING — requires a human at the screen.**

With the keyring entry cleared (`secret-tool clear purpose openrouter-api-key`),
launch the installed app and reach a working chat window without opening a
terminal. Record any step where the onboarding screen should have explained
something it did not.

## Criterion 6 — A non-technical tester, given only the app and no instructions, completes all three tasks

**PENDING — this is the real criterion. Spec §9: "The others are necessary;
that one is the product."**

Find a non-technical Linux user. Give them the installed app and no
instructions. Ask them to do all three:

1. *"Find the PDF I downloaded yesterday and put it in a new folder called Taxes"*
2. *"What's in my Downloads folder? Delete the ones I don't need"* (exercises
   the dialog, trash semantics, and multi-action batching)
3. *"Open my music player and turn the volume down"*

Watch without helping. Record for each: completed or not, where they
hesitated, whether they read the approval dialog or clicked through it, and
anything they said out loud.

> **Known risk to task 3 — volume.** The `pulseaudio-utils` manifest module
> runs `install -Dm755 /usr/bin/pactl /app/bin/pactl || true`, which copies
> `pactl` from the *build* sandbox filesystem — which almost certainly does
> not contain it. The `|| true` swallows the failure silently, so the shipped
> app may have no `pactl`, in which case `set_volume` fails and task 3 cannot
> complete. This is unverifiable until the build runs; see Open Items.

## Criterion 7 — No code path can perform an action outside the catalog table

**PASS (mechanical).**

`tests/test_registry.py::test_no_tool_name_hints_at_shell_access` asserts no
tool name leaks shell capability. `test_every_tiered_tool_exists_in_the_catalog`
and `test_every_sandboxed_argument_exists_on_its_tool` assert the registry and
catalog are consistent in both directions. The catalog exposes no shell
primitive: there is no `run_command`, no `execute`, no path argument that is
not sandboxed. `set_volume` shells out to `pactl` internally, but the model
can only invoke the bounded `set_volume` tool, never `pactl` directly.

---

## Open Items (to resolve before or during the user's pass)

1. **Build the Flatpak (blocks criteria 4, 5, 6).** Install the toolchain and
   add the Rust SDK extension (two Rust-built deps: `pydantic_core`, `jiter`).
   This is the single largest open item; nothing past it can be tested.
2. **Verify `pactl` survives the sandbox (blocks criterion 6, task 3).** Once
   built, confirm `set_volume` actually changes the sink volume. If the
   `|| true` module swallowed a missing `pactl`, fix the manifest to fetch
   `pactl` correctly or bundle pulseaudio-utils properly.
3. **The batching contradiction (criterion 6, task 2).** The plan's live claim
   that `qwen/qwen3.7-flash` "returns three tool calls in a single response
   for a three-action request" did not hold in two Task 13 runs — the model
   emitted one. The batched dialog is therefore unproven against real
   batching. Decide: prompt-tune to elicit batching, or accept single-call
   behaviour (the gate degrades gracefully, but the feature goes unexercised).
4. **Unexplained `test_session.py` flakiness.** A reviewer running the suite
   from a BASE worktree saw 3 intermittent failures in `tests/test_session.py`.
   It does **not** reproduce at HEAD (4 consecutive clean runs of the full
   suite, 3 isolated runs of `test_session.py`, including with `-p no:randomly`).
   Left open for the final whole-branch review rather than closed on the
   strength of these passes.

## Deferred minors (cosmetic; do not block acceptance)

- `platform/system.py:22` comment says the clipboard mirror is updated "on
  focus-in"; the implementation correctly uses the `Gdk.Clipboard` "changed"
  signal instead. Comment is stale.
- No test asserts `ChatWindow.__init__` wires `_watch_clipboard` to the real
  display clipboard (driven with a fake in isolation).
- `tests/test_dialog.py::test_dismissal_routes_to_deny` asserts
  `get_close_response() == "deny"` (a proxy), since firing a real window-close
  is not scriptable in-process.
- `session.py` does not read `OPENROUTER_BASE_URL` from the environment
  (spec §7 mentions it); `BASE_URL` is hardcoded. Belongs to `session.py`, not
  a correctness issue.
