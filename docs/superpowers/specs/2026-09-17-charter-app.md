# charter-app — one desktop app for running tons of harness sessions in parallel

**Status:** agreed 2026-09-17, amended 2026-09-18 (decisions 14-17 and the milestones: no Python in the app at any milestone) in a grill between the operator and the `steward` persona
(workspace `ide`), and amended the same day when the operator reordered the priorities (below).
Amended 2026-09-20 with decisions 22-28 and the milestone placement under them: the app had no
way to be given a plane, which this spec never noticed.
The decision and its reasons: `docs/adr/0025-charter-is-rebuilt-as-a-desktop-app-on-a-rust-core.md`.
The evidence: `docs/research/2026-09-17-gui-terminal-embedding.md`.

## The goal

A developer runs dozens of harness sessions (Claude Code, Codex) at once, across workspaces
and repos, and always knows which one needs them. It is one lightweight app on macOS, Linux
and Windows, with no daemon, carrying every charter concept: the plane, workspaces, personas,
todos, memory, vaults, guards.

## Priorities, in order

1. **Development experience.** A change is quick to make, quick to check and pleasant to work on.
2. **Robustness, through standard practice.** Mature, released, widely used tools, the way they
   are meant to be used. Nothing custom where a standard tool exists.
3. **Speed a person can notice.** No lag, no freeze. Speedups nobody can feel never cost 1 or 2.

When two choices conflict, the higher priority wins.

## Why charter is being rebuilt

- **Development is slow.** The tmux frame is 11.5k lines of plumbing, and tests are 3.3× the
  source.
- **Proof is missing.** Nothing tests end to end that a finished change works in the real app.
- **Reach is limited.** POSIX only; the frame does not run on Windows.
- **Scale hurts.** Watching many sessions in tmux panes is impractical.

## Language

- **App**: the desktop GUI. **Core**: the Rust library the app and the CLI share.
  **`charter` binary**: the CLI on PATH, called by hooks, scripts and agents.
- **Session**: one harness process in one PTY, owned by the core. **Chat**: a session as the
  UI shows it: its tab, its workspace, its state.
- **Session state**: `running`, `waiting` (on you), `done`, `failed`, `unknown`. Set only by
  harness hooks, never by reading output.
- **Python charter**: the current implementation, frozen, and the reference for differential
  tests until it is retired.

## Decisions

### Product

1. **One window.**
   - **Left:** a sidebar listing every workspace with its chats, and each chat's live state.
   - **Top:** a global "needs you" queue, plus OS notifications.
   - **Center:** tabs and free split panes.
   - **Right:** panels for the focused workspace: repos, branches, CI, todos, personas.
   - **Palette:** the command palette is the primary input, keyboard first.
2. **No TUI.** In the terminal, charter is the CLI.
3. **Session state comes from hooks only.** A hook calls `charter hook …`, which hands an
   event to the app through a socket the app owns. A harness with no such hook shows
   `unknown`. Amended 2026-09-18, by what M1.3 had to settle to build it:
   - **A socket, and nothing else was needed** — which closes the open question below. The app
     binds it and names it in the environment of every session it starts, beside that chat's
     own number. A hook therefore looks nothing up: no plane read, no discovery, no polling
     loop, and no Tauri plugin beyond the single-instance one already in use.
   - **`failed` is a non-zero exit.** No hook can report it — the process is gone. An exit
     status is the program telling the app directly, so it is not the harness OUTPUT that ADR
     0018 forbids reading. Operator's ruling, 2026-09-18.
   - **A harness may carry only part of the set.** Codex fires no `Notification` at all
     (measured, codex-cli 0.147.0), so a Codex chat can say it is running and it is done and
     can never say it is waiting on you. It shows what it can, and the UI says what it cannot,
     rather than being flattened to `unknown`. Operator's ruling, 2026-09-18.
   - **Which chat a report belongs to is decided by the process id, not by the conversation
     alone.** ADR 0024's C5 (a harness nested in the chat's own shell) and C6 (`/clear`) both
     report a conversation the chat has not seen, and `$CLAUDE_PID` is the whole of what tells
     them apart. The payload and the environment must AGREE on the conversation: using one as
     a fallback for the other is a hole, because the environment holds the OUTER chat's id.
   - **A chat inherits none of that from charter itself.** charter may be launched from inside
     a harness session, and a chat that inherited its `CLAUDE_PID` would report the launcher's
     identity as its own.
4. **A worktree per writing chat.** A chat that writes to a repo gets its own git worktree by
   default. The sidebar shows its branch. Merging back is an explicit action — `merge` lands
   it locally, fast-forward only, into the branch the piece was cut from; `publish` pushes;
   neither does the other, and neither takes `--all` (ADR 0020). Git is the only registry,
   reached through the git binary: **ADR 0027**. The design is
   `docs/superpowers/specs/2026-09-18-worktree-per-chat-design.md`.
5. **Lifecycle.** Closing the window hides the app to the tray. Quitting warns if a session is
   mid-turn and then ends every session. On the next launch, chats reopen through each
   harness's own resume.
6. **Harnesses in v1:** Claude Code and Codex. opencode follows.
7. **Remote sessions are not in v1.** Sessions sit behind one interface (spawn, read/write
   bytes, resize, exit) with local PTY as the first implementation, so SSH or devcontainers
   can be added later without a redesign.
8. **Extension points are not in v1.** The tmux frame's component/action seam is redesigned
   for the app later, not carried over.

### Architecture

9. **A Rust core owns every PTY and every terminal's state, headless**, using
   `alacritty_terminal` behind an engine trait. No second engine is built now. This holds
   because web UIs are capped at 16 WebGL contexts (research §5.1).
10. **The UI is Tauri 2 + React + TypeScript, and xterm.js draws only the panes on screen.**
    When a pane becomes visible, the core sends a snapshot of its screen, then streams its
    output. This is the VS Code reconnection pattern, not a hand-written renderer. GPUI is the
    fallback only if the M0 skeleton misses a limit below.
11. **Typed IPC.** Commands and events between core and UI are generated from Rust types
    (`tauri-specta`). No JSON shapes are written by hand on either side.
12. **Nothing in the core parses harness output to decide anything** (ADR 0018, carried over).

### Migration

13. **The plane format does not change.** `docs/plane-format.md` records every file and field
    the Python charter reads or writes (`charter.toml`, `charter.local.toml`, `personas/`,
    `workspaces/*/workspace.md|json`, memory files, `.charter/` state) and marks each one stable
    or internal. Fixture planes are generated from it, and both implementations test against
    them.
14. **The app never calls Python, at any milestone.** Amended 2026-09-18 on the operator's
    instruction: "final app should not use python, fully clean implementation in rust — no need
    to mix languages". The first plan had the app shelling out to Python `charter` for writes
    and hooks until M3. It does not: whatever a feature needs is ported to Rust **before** the
    feature that needs it, so no shipped path ever crosses languages, and no scaffolding is
    written that only exists to be deleted.
15. **Python is the oracle, not a dependency.** Every ported module passes a **differential
    test**: the same fixture plane and the same input give the same output and the same
    resulting plane in both implementations. That runs in CI, where Python is a test fixture —
    it is never in the app, the `charter` binary, or an installer.
16. **Security-critical parts are ported with the most care, not last:** hooks guard,
    gitpolicy, vaults and secrets each need the differential proof plus an external review
    before the Rust one answers for real. Ordering follows what a milestone needs; nothing
    ships on a Python fallback in the meantime.
17. **Python charter is frozen.** It keeps running as today's product until cutover, and gets
    bug fixes and security fixes only. New feature ideas go to the `charter-app` backlog.

### Engineering

18. **Repository:** a new repo, `charter-app`, which takes over the `charter` name at M4. The
    product is still called charter. This repo stays the Python implementation and the plane.
19. **Standard tooling, enforced in CI:**
    - **Rust:** the stable toolchain, `rustfmt`, `clippy -D warnings`, `cargo-deny` (licences
      and advisories).
    - **TypeScript:** `strict`, ESLint, Prettier.
    - **Dependencies:** Dependabot (built into GitHub, nothing to install).
    - **Tests:** Vitest for UI units, `cargo test` for the core, and scenario tests through
      Tauri's WebdriverIO service.
    - **Releases:** the Tauri updater with signed artifacts.
20. **Tests:**
    - **Main gate:** scenario tests driving the real app against a **fake harness binary** that
      replays recorded output and fires recorded hooks.
    - **Unit tests** stay small.
    - **Mutation testing** runs nightly on the core crate alone, with `cargo-mutants --in-diff`,
      sharded. It never blocks a PR.
21. **Distribution:** one signed installer per OS. It installs the app and puts `charter` on
    PATH. The Claude Code plugin keeps calling `charter hook …`. A final PyPI release points to
    the new install.

### Multi-plane — added 2026-09-20

**What this spec missed.** Decisions 1-21 never say where the app's plane comes from. In the
tmux frame it came from the shell that ran `charter`, and ADR 0025 carried that assumption into
an app that has no shell: charter-app resolves its plane from `std::env::current_dir()` and from
nothing else, so a double-clicked `.app` — working directory `/` — resolves none, shows
`No plane: …` and offers no way to give it one. **The app has only ever been usable when
launched from a terminal standing inside a plane.** The operator found this by opening it on
2026-09-20. There was no picker, no opener and no multi-plane anything in this spec, and there
is no ADR that decided against them; they were simply not seen.

These decisions continue the numbering rather than joining 1-8, because a decision's number is
how it is cited and nothing here is renumbered.

22. **A project is a plane.** The top-level switcher is a plane switcher, and "Open Project…"
    opens a directory that has, or will get, a `charter.toml`. There is no second container:
    ADR 0007 removed the second plane shape so that no code would ask which shape it was in.
    **ADR 0033.**
23. **One window per plane, and a window may hold several.** Planes are top-level tabs in a
    window, merged into one window or split back out — Zed's project tabs, named by the
    operator. `tauri-plugin-single-instance` stays exactly as it is: one process, many windows.
    A second launch hands its plane to the running process, which raises the window holding it
    or opens one. Two processes on one plane would be two sets of sessions, two writers of that
    plane's `.charter/app/reopen.json`, two hook sockets and a Quit that ends half the work.
    **ADR 0033.**
24. **cwd is a first-launch hint, never ongoing truth.** Launched from a terminal inside a plane
    → open that plane. Launched any other way → the opener. Once a window has a plane, that
    plane is explicit and the working directory is never consulted again. The CLI keeps its own
    resolution untouched. M2.16 was exactly the cost of two resolvers disagreeing (`resolve`
    against `command_root`), and the app has the same split live today: `plane_root` asks
    `plane::resolve`, which honours `$CHARTER_ROOT`; `setup` asks `plane::find_root`, which does
    not. **ADR 0034.**
25. **charter keeps a machine-level record outside every plane**, under the OS application-data
    directory: the planes on this machine, when each was last opened, the window arrangement,
    and the trust decisions of decision 26. `0600` where the OS has modes, gated, tolerant of
    paths that have moved or gone, and **never plane content** — deleting it must cost the
    arrangement and the approvals and nothing else. This is the second such file, not the first:
    `charter report`'s consent has lived under the user's config home since ADR 0003.
    **ADR 0034.**
26. **A plane is untrusted until the operator opens it once and approves it.** A plane's
    committed `.claude/settings.json` travels — `layer.rs`'s `WORKSPACE_KEYS = ["enabledPlugins",
    "env"]` — into every directory a harness reads config from, so a stranger's plane chooses
    your plugins and sets your environment; and opening a plane starts programs out of its
    `.charter/app/reopen.json`. First open shows what the plane will contribute and asks, before
    the reopen runs; the answer is a fingerprint of what was approved, stored per decision 25.
    Two limits already exist and stay named: `permissions` travels only as `ask`/`deny`, never
    `allow` (`RESTRICTIVE`), and ADR 0022 keeps harness profiles out of the committed file.
    **ADR 0035.**
27. **`charter init` on an existing repo adopts that repo as the plane's first clone by
    default**, making the plane beside it rather than writing plane scaffolding and `.gitignore`
    rules into somebody else's repository. "Make this repo itself the plane" stays available and
    becomes the non-default — it is how charter's own plane exists. This **diverges from the
    Python oracle** (decision 15) on a command that is already ported; Python is frozen
    (decision 17), so the `init`-inside-a-repo differential scenario records an intended
    difference rather than being normalised. **ADR 0035.**
28. **Cold launch restores the window set from the last quit** — same planes, same tabs, same
    merges. Each plane's own `.charter/app/reopen.json` still restores that plane's chats and is
    unchanged; the two records are separate because an arrangement spans planes and a plane's
    chats travel with the plane. A plane that has moved or gone is dropped with a line saying
    so, never an error dialog. `--no-restore` starts clean. **ADR 0033.**

## Limits (acceptance)

Only what a person would notice. Measured on the operator's machine, in the scenario harness.

| | Limit |
| --- | --- |
| Live sessions | **50**. This is the product's scale, not a speed target |
| 2 MB and 13 MB output bursts | the UI never freezes; input and other panes stay responsive |
| Keystroke to screen | ≤ 50 ms while 49 other sessions stream |
| Tab or pane switch | ≤ 100 ms |
| Hook call (`charter hook …`) | ≤ 50 ms |
| Cold start | ≤ 2 s |
| Idle hidden session | ≤ 50 MB, with scrollback at the shipped cap |
| Synchronized-output animation (`?2026`) | smooth, ≥ 30 fps (xterm.js#6071 is why this is listed) |

tmux's end-to-end throughput is re-measured in M0 on the same machine and recorded as a
**reference**, not a gate.

## Milestones

Each milestone is something the operator actually uses, not a layer.

- **M0: walking skeleton.** Tauri + Rust core + xterm.js, with 50 fake sessions and one
  scenario test green in CI on macOS and Linux. It is measured against the limits above and
  locks the stack. GPUI is tried only if a limit is missed. **Done** — the measurements and
  the lock are ADR 0026, and the benchmark is `node tools/bench.mjs` in charter-app.
- **M1: daily driver on macOS, on Rust alone.** The app replaces the tmux frame for the
  operator, and every part of it is Rust:
  - the plane read *and written* in Rust: workspaces, chats, personas, todos, profiles
  - the workspace sidebar and the "needs you" queue
  - chats with the profile and persona picker
  - a worktree per chat (ADR 0027) — with one gap named there and not papered over: the
    harness layer is not yet written into a worktree, so such a chat runs without charter's
    guards, its row says `unwired`, and a persona cannot be attached to it
  - read-only panels and the palette
  - lifecycle: tray, a quit warning mid-turn, reopen on relaunch
  - `charter hook …` answered by the Rust binary, which is also what meets the hook limit
    ADR 0026 measured at 107.6 ms through Python

  Each ported piece carries its differential test against Python.
- **M2: the rest of the CLI.** Every remaining command the plane needs — recall, save, sync,
  clone, doctor, news, report, git-policy — with differential tests, so the Rust `charter` is
  the only one a plane needs.
- **M3: security-critical parts proven.** Hooks guard, gitpolicy, vaults and secrets get their
  external review against the Rust implementation (the pieces themselves land whenever a
  milestone needs them, never on a Python fallback).
- **M4: public release.** Linux, then Windows (ConPTY, bundled package), signed installers,
  the final PyPI release pointing to the new install, and Python charter retired.

### Where the multi-plane work goes (added 2026-09-20)

Decisions 22-28 are product work this spec missed, not a milestone of their own, so they are
placed inside the existing ones and the placement is part of the decision.

- **M2 gains the opener, the plane switcher and the machine-level record** — decisions 22, 23,
  24, 25 and 28. It goes here because M2 is where the app stops needing a terminal for
  anything, and an app that can only be started from a terminal is the largest remaining place
  where it still does. The expensive half is not the UI: `Hooks`, `Chats` and `Plane` are
  `app.manage(...)` process-wide singletons today, `Plane` is one `Option<PathBuf>` for the
  whole process, and fifteen commands take one of those as `tauri::State`. The window has to
  carry the plane and that state has to be keyed by it before a second plane in a window is
  anything but a second plane writing through the first one's state.
- **M2 also gains decision 27**, `charter init`'s new default, because `init` is already ported
  and the opener is what makes the old default dangerous. Its differential scenario changes in
  the same commit that changes the default, marked as an intended divergence.
- **M3 gains the trust gate** — decision 26. It is an ask in front of a real exposure, it is
  measured against `layer.rs` and `reopen.rs` rather than assumed, and M3 is where the parts
  that decide what runs get their external review. It must land no later than the first build
  an operator other than this one installs, because until it does, opening an unknown plane is
  a decision made silently.
- **M1 is not reopened.** It was declared a daily driver against a definition that assumed a
  terminal launch. That is worth writing down rather than quietly re-scoping: the bar moved
  under it, and the app has been unusable from an icon for every day it has been called done.

## What M0 reported

M0 measured the skeleton against the limits above on the operator's machine and locked the
stack: **ADR 0026**. It answers the first of the questions this section left open.

- **The scrollback cap is 5000 lines**, and a hidden session holding that much at 150 columns
  costs 20.2 MB of the 50 MB the limit allows. Fifty of them add about 1 GB to the app.
- **xterm.js draws with its own DOM renderer.** WebGL was measured beside it: both meet every
  limit, and neither is faster at the same things, so the simpler one wins on priority 1. The
  addon stays behind a switch, because many panes on screen is the one thing it is better at.
- **The hook call is missed**: 107.6 ms through Python charter, against a 1.8 ms start for the
  Rust binary. M3 is where it is met, and it is not the stack's to fix.
- **A `?2026` animation falls to one frame a second** if a writer pauses inside an open update
  (xterm.js#6071), against 52 draws a second when repaints are written whole. The core can
  close it in M1 by never ending a chunk inside an open update, with a deadline of its own.

Still open:

- ~~Whether the file or socket for hook events (decision 3) needs anything beyond Tauri's own
  single-instance and IPC plugins.~~ **Answered 2026-09-18 by M1.3: neither.** A unix socket
  named in each session's own environment needs no discovery and no plugin. Decision 3 records
  what else that milestone had to settle.
