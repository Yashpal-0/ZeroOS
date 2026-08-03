# ZeroOS v0.1 — Acceptance Pass

Spec §9 sets seven success criteria. This document records the evidence for
each. Criteria 1, 2, 3, and 7 are mechanical and were verified against the
test suite. Criterion 4's build-and-install half is now proven; its
menu-launch half, along with criteria 5 and 6, needs a human at the machine
and is left open pending that pass.

**Suite state at HEAD:** `170 passed, 0 failed`. (Warnings are pre-existing
PyGObject/asyncio deprecation notices, unrelated to the product.)

A final whole-branch review ran after the per-task reviews and found one
cross-cutting defect, now fixed in `d52e27b`: `session._run` classified a
`refuse_root` block as `"executed"` in the action log, because the sandbox
raises two different refusal messages and only one was compared. The guard
itself always held — the home folder was never touched — but the audit log
claimed otherwise, which is the §6 lie the log exists to prevent. Neither
scoped review could see it: `refuse_root` lives in the sandbox task and the
comparison in the session task. The review verified the rest of the
defense-in-depth chain holds end to end (see Open Items for what remains).

---

## Criterion 1 — All sixteen catalog functions implemented, each with a tier and unit tests

**PASS (mechanical).**

`tests/test_registry.py::test_the_catalog_has_exactly_sixteen_tools` asserts
`len(tools) == 16`. `test_every_catalog_tool_has_a_tier` asserts no tool is
without a tier. Both pass. Every catalog module carries its own unit tests
(`test_catalog_files.py`, `test_catalog_openers.py`, `test_catalog_apps.py`,
`test_catalog_system.py`); the full 170-test suite exercises them.

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

**BUILD AND INSTALL: PASS. Menu launch: pending your check.**

The Flatpak builds clean and is installed (`flatpak list --app` shows
`io.zerostic.ZeroOS`). Reproduce with:

```
flatpak remote-add --if-not-exists --user flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub org.gnome.Platform//47 org.gnome.Sdk//47
flatpak-builder --user --force-clean --install build packaging/io.zerostic.ZeroOS.yml
```

Verified inside the installed sandbox: `pactl` resolves at `/app/bin/pactl`
with no missing libraries, and `openai`, `pydantic`, `jiter`, `Gtk 4.0`,
`Adw 1` and `Secret 1` all import.

**Three defects the static review could not have caught, all fixed in
`d50de5c`:**

1. **The sdist install could never have worked.** `--no-build-isolation`
   forbids pip from fetching build backends, and `org.gnome.Sdk//47` ships
   only `setuptools`/`wheel` — eight of the sixteen dependencies build with
   `hatchling`. The build died at `Cannot import 'hatchling.build'`.
   Fixed by pinning all sixteen sources to upstream's published wheels.
2. **The Rust hazard does not exist.** `jiter` and `pydantic_core` publish
   `cp312 manylinux` wheels matching the runtime's Python 3.12, so no
   `cargo`, no compile, and no `rust-stable` SDK extension is needed. The
   review's two-package Rust risk is void.
3. **No icon existed.** The desktop file declared `Icon=io.zerostic.ZeroOS`
   and nothing ever shipped the file, so `appstreamcli` failed the build with
   `icon-not-found` — a failure that only appears at the end of a real build.
   Added `packaging/io.zerostic.ZeroOS.svg` and its install line.

**Still yours:** launch it from the applications menu (not the terminal) and
record whether it appeared without a logout.

> **Note:** `org.gnome.Platform//47` is end-of-life (unsupported since
> 2025-10-15). It builds and runs today; migrating to a supported runtime is
> worth doing before any public release.

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

> **Volume risk RESOLVED — `pactl` ships.** The predicted silent failure did
> not happen: `org.gnome.Sdk//47` does provide `/usr/bin/pactl`, the copy
> lands, and it runs inside the installed sandbox (`/app/bin/pactl`, 0 missing
> libraries). `set_volume` should work. The `|| true` remains a latent trap —
> it would hide the failure if a future SDK dropped the binary — but it is
> hiding nothing today.

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

1. ~~Build the Flatpak.~~ **DONE** — builds clean and is installed; see
   criterion 4. Three defects found and fixed in the process (`d50de5c`).
2. ~~Verify `pactl` survives the sandbox.~~ **DONE** — it ships and runs at
   `/app/bin/pactl`. That `set_volume` actually moves the sink volume is still
   worth a live check during criterion 6, task 3.
3. **Migrate off the end-of-life runtime.** `org.gnome.Platform//47` has been
   unsupported since 2025-10-15. It builds and runs today, so this does not
   block acceptance, but it should be settled before any public release.
4. **The batching contradiction (criterion 6, task 2).** The plan's live claim
   that `qwen/qwen3.7-flash` "returns three tool calls in a single response
   for a three-action request" did not hold in two Task 13 runs — the model
   emitted one. The batched dialog is therefore unproven against real
   batching. Decide: prompt-tune to elicit batching, or accept single-call
   behaviour (the gate degrades gracefully, but the feature goes unexercised).
5. **Cheap hardening, not a blocker.** `gate.py`'s two consent guards are bare
   `assert`s, which `python -O` / `PYTHONOPTIMIZE=1` would strip. The review
   confirmed the Flatpak does **not** launch under `-O` (manifest
   `command: zeroos`, desktop `Exec=zeroos`, no `PYTHONOPTIMIZE` in
   `finish-args`), so the no-silent-denial guarantee holds in v0.1 as shipped.
   Swapping both to explicit `if ...: raise RuntimeError(...)` would make that
   independent of how the app is launched.
6. **Unexplained `test_session.py` flakiness.** A reviewer running the suite
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
