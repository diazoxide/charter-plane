# charter keeps a little state outside every plane

[ADR 0033](0033-a-plane-is-a-project-and-a-window-may-hold-several.md) says the app opens planes
and arranges them in windows. That needs a list of planes and an arrangement, and neither is a
fact about any one plane: the list cannot live in a plane without choosing which plane owns the
others, and a plane deleted on Tuesday would take the list of the rest with it.

So charter gets a machine-level file, under the operating system's application-data directory
for this app. That bends the rule charter was built on — **the plane is the state** — and this
record exists to bend it on purpose, with a stated limit, rather than to have it worn away.

## The rule is not as absolute as it sounds, and the exception is already shipped

Two places in charter already answer this question, and they answer it in opposite directions.
Both were right, and the difference between them is the rule.

[ADR 0022](0022-a-harness-profile-belongs-to-one-machine.md) considered **"a per-user
`~/.config/charter` file"** for harness profiles and rejected it in one line, as the operator's
call: *"profiles are per plane and per machine, and a plane's own directory is where its other
configuration is."* Machine-local there means `charter.local.toml`, beside `charter.toml`, inside
the plane and out of git — and `.charter/` for the launch record and the wiring cache. Nothing
left the plane.

`charter/report.py:consent_path` does the opposite, and says why: consent to publish is kept
under `$CHARTER_CONFIG_HOME`, else `$XDG_CONFIG_HOME`, else `~/.config`, as
`charter/reporting-consent` — **"Not STATE_DIR: that is per control plane, so a Reporter with
several planes would be asked repeatedly until the safeguard became a reflex."**
[ADR 0003](0003-no-unattended-publish.md) records the same sentence as a consequence: filing
consent is "asked once per human and stored in user-level config".

**So this is the second such file, not the first**, and the claim that charter has never stored
anything outside a plane is wrong twice over: reporting consent has been outside every plane for
as long as `charter report` has existed, and charter-app already writes its panic log to
`app.path().app_log_dir()`, which is an OS directory belonging to the app and to no plane.

## The rule this record states

A fact may live outside every plane **only when it is about the operator or the machine and is
false inside any one plane.** Four facts qualify, and they are the whole of what this file holds:

- **which planes exist on this machine** — no plane can hold it;
- **how they were arranged in windows at the last quit** — an arrangement spans planes;
- **whether this human has approved this path** ([ADR
  0035](0035-a-plane-is-untrusted-until-the-operator-opens-it.md)) — asking once per plane is
  asking until the answer stops being read, which is `report.py`'s sentence applied to a second
  safeguard;
- **when each was last opened**, so the switcher can put the recent ones first.

Paths, timestamps, trust decisions, window layout. That is the list.

**Amended by [ADR 0040](0040-a-pin-is-an-arrangement-so-it-is-machine-state.md) (2026-09-22):
there is a fifth fact, and it is `how the operator arranged what this file already names`** —
which of the remembered planes are pinned, and which workspaces inside them. The operator ruled
that a pin is how one person likes their window rather than a fact about the plane, so it cannot
be committed to `charter.toml`. It is held to this record's own rule and its own test, and the
paragraph below about plane content still stands: a pinned workspace's name is a **reference**
into the plane, not a copy of what the plane says, and one that no longer resolves is dropped
with a reason. A chat pin is **not** here — this record forbids chat names outside a plane, and
that one goes in the plane's own `.charter/app/reopen.json`.

**Amended by [ADR 0042](0042-charter-updates-itself-and-nothing-it-cannot-verify-reaches-it.md)
(2026-09-22): there is a sixth fact, `which update channel this machine takes charter from`**
(stable or dev). It is the first fact here that is not about planes at all, and it qualifies on
this record's own test: it is about the machine (one binary serves every plane on it and cannot
be on two channels), it is false inside any one plane, and deleting it costs the operator one
preference, which falls back to stable. Every way of not knowing it reads as stable, never dev.

**And never plane content.** No workspace names, no todos, no memory, no chat names, no persona,
nothing a plane's own files already say. The test to apply to any field somebody wants to add:
*deleting this file must cost the operator their arrangement and their approvals and nothing
else; every plane must still open, complete, with everything it had.* A copy of plane content
outside the plane is a second answer to a question the plane already answers, and this codebase
has paid for two answers to one question twice in the same module — `find_root` against `place`
in M2.9, `find_root` against `command_root` in M2.16, both recorded in `plane.rs`'s own
docstrings.

## Where it lives, and what holds it shut

**The OS application-data directory**, through Tauri's own path API — not `~/.charter`, and not a
directory charter invents. Priority 2 is standard practice, the platform has a place for exactly
this, and the app already uses that API's sibling for its log directory.

**Not `$CHARTER_HOME`.** That variable moves a *plane's* state directory, and every reader of it
in the core hard-codes `.charter` under a plane root — `adopt.rs:baseline_file` says so in its own
docstring, and `profiletrust`, `wiring` and `hookwire` all do the same. A machine's file is not a
plane's state, and borrowing the variable would make `$CHARTER_HOME` mean two things.

**`0600` — the mode charter already keeps on its own private state.** Not by calling
`plane::write_private`, which gates the path it writes against a plane root and there is no
plane here; by holding the same mode through whatever writes this one. And the honest half: on
Windows a mode bit is not an ACL, `write_private` drops the `0600` silently there, and that is
[ADR 0031](0031-windows-gets-charters-guards-or-it-gets-no-charter.md)'s
open item #98. This record does not fix it and does not get to assume it is fixed — on Windows
this file is as private as the user profile directory it sits in, and no more.

**Every unreadable state is an empty state.** A missing file, a file that will not parse, a link
where a file should be, something far too large: each reads as "no arrangement and no approvals",
and the app opens the opener. Never as "no record, so everything is fine" — that direction is
what `profiletrust` opens its module documentation refusing, and the trust decisions in this file
are the same kind of answer.

**Tolerant of paths that have moved or gone.** A plane that is no longer there is dropped with a
line; the app still starts. The file is a convenience and the plane is the truth.

One hazard that follows and is not closed by anything above: **a trust entry keyed on a path
alone would be inherited by whatever is at that path later.** The answer is ADR 0035's — an entry
records what was approved, not just where — and it is named here because this file is where such
an entry would be stored and a later reader will be tempted to key it on the path.

## cwd is a first-launch hint, never ongoing truth

The same decision settles where a window's plane comes from, because the alternative is the
failure charter has already had twice.

- Launched from a terminal standing inside a plane → open that plane.
- Launched any other way → the opener.
- **Once a window has a plane, that plane is explicit, and the working directory is never
  consulted again.**
- The CLI's own resolution (`plane::resolve`: `$CHARTER_ROOT`, else `find_root`) is untouched.

The reason is measured and it is live in the app today. `plane_root` — the command the UI asks,
and whose answer the UI hands to `worktreeRemove`, `worktreeMerge` and the palette — calls
`charter_core::plane::resolve`, which takes `$CHARTER_ROOT` when it is set. `setup`, which
decides the hook socket, the chats that are reopened and the plane the exit handler writes its
record into, calls `charter_core::plane::find_root` directly, which does not look at that
variable at all. **Launch the app with `$CHARTER_ROOT` naming one plane while standing in
another and the window's sessions belong to one plane while the window's UI names the other.**
That is exactly M2.16 — `resolve` against `command_root` — reproduced inside the app, and
`plane.rs` already records the verdict from the first time: *"Two functions whose whole contract
is to name the same directory are kept in step by being one function."*

After this decision there is one thing that decides a window's plane, and it is the window's own
record. The working directory and `$CHARTER_ROOT` feed exactly one moment — the first window of a
launch that restored nothing — and never again. A resolver that runs once cannot drift from a
resolver that runs later, because there is no later.

## What was rejected

- **Putting the list of planes in a plane.** Which one? The last one opened owns the rest, and
  deleting it loses them. There is no non-arbitrary answer, which is the shape of a fact that does
  not belong in a plane.
- **Reusing `$CHARTER_HOME`.** Above: it names a plane's state directory, and every reader in the
  core spells `.charter` under a plane root.
- **A `~/.charter` directory of charter's own invention.** The platform has a directory for an
  app's data on all three operating systems and Tauri hands it over. Priority 2.
- **Re-resolving the plane from the working directory as the app runs.** It is how a terminal
  program behaves and it is why there were two resolvers to reconcile in M2.16.
- **Keeping the window arrangement in each plane's `.charter/app/reopen.json`.** An arrangement
  spans planes, so every plane would hold a partial copy of the same fact, and a plane opened on
  another machine would arrange that machine's windows.

## Consequences

- charter now has a file no plane can reproduce. Two machines sharing every plane still arrange
  them differently, and a fresh machine opens the opener with an empty list — intended, and the
  price of the rule above.
- A plane copied to another machine carries no approval with it, so ADR 0035's ask runs again
  there. Intended: an approval is one human's, on one machine.
- Losing a home directory loses the arrangement and the approvals. Everything else survives,
  because everything else is in the planes. That is the test this record set, applied to the worst
  case.
- The file decides what the app opens and what it trusts, which makes it worth writing to. It is
  machine-local and `0600` on POSIX, and a process that can write it can already write the
  operator's shell profile — so this is a lock on the door, not a wall, and `profiletrust`'s
  statement of the same limit applies to it word for word.
- The rule in this record is narrow on purpose, and the next feature that wants a field in this
  file has to argue against it rather than append to it.
