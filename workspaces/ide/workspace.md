# ide

> **Living charter** for this workspace — its north star and shared context.
> Keep it current as the work evolves (edit this file, or `charter workspace vision "…"`).
> It's committed + shared for LIVE workspaces, and a fork inherits it — so anyone
> can pick up the task with full context. Never put secrets here (vault only).

## Vision

Rebuild charter as one lightweight cross-platform desktop app (repo charter-app): a Rust core with a Tauri 2 + React + TypeScript UI (ADR 0025, spec docs/superpowers/specs/2026-09-17-charter-app.md). Tons of parallel harness sessions, always knowing which one needs you, no daemon, same plane on disk. Priorities: development experience, then robustness through standard practice, then speed a person can notice. Milestones: M0 walking skeleton, M1 daily driver on macOS, M2 core in Rust, M3 security-critical parts, M4 public release.

## Context & decisions

<!-- Key facts, constraints, and design/architecture decisions found while working —
     the durable "why", not a chronological log. Grow this as you learn. -->

### Create/edit-workspace flow (settled 2026-09-25, ships as ONE charter-app PR)

- **Outer chat starts in `/`** — root cause: `charter_core::start::ready` resolves
  `here = cwd or plane root` (start.rs:181) but returns the raw `start.cwd` (start.rs:228);
  `None` reaches `Session::spawn`, which falls back to `current_dir()` = `/` for a
  Finder/Dock launch. Fix: `cwd: Some(here)` + unit test + correct the PlaneView.tsx:796 comment.
- **Empty plane entry point:** centre empty state offers "Create a workspace" as the primary action,
  and the workspace strip (with its `+`) always renders when a plane is open.
- **Repo picker is live and per-user:** each open calls the operator's own `gh`/`glab`
  (GitHub `GET /user/repos`, which includes private repos), filtered to the plane's `[[forge]]` owners and excludes;
  kept in memory for the window, refresh button, nothing written to the plane for the listing.
- **Inventory becomes add-only:** picking repos upserts their records into `inventory/repos.json`;
  `charter discover` changes from overwrite to add/update-only, so no engineer's run drops another's repos.
- **Clone in background:** the workspace is created immediately; clones run off the UI thread with
  per-repo status (cloning / done / failed + retry).
- **Edit flow:** workspace settings gets a Repos group with the same picker. Tick clones;
  untick removes the clone only past the `work_at_risk` guard.
- **No gh auth:** inline "run `gh auth login`" notice + retry; creating without repos still works.

### Saving repos (operator's ruling 2026-09-25, ADR 0051 amended; shipped in charter-app #404)

- **The title-bar Save saves the plane only.** A workspace repo is a developer's: charter never
  commits or pushes one from a press that did not name it.
- **Save all lives only in the Saving tab**, behind a confirmation listing each repo, its branch,
  what it takes and where its save goes. It saves exactly the list it showed.
- **An unconfigured repo is `off`**; charter saves no repo until `[repos.<name>] mode` says how.
- **Each repo row says where its Save goes**, including where it stops short (no forge, no target,
  detached). The words must match `reposave`'s steps: a PR save on the base or default branch
  commits there first, then pushes that commit as `charter/<ws>/…`.

## Glossary

<!-- Task/domain vocabulary so a teammate or a fork isn't lost: `term` — definition. -->

_Nothing yet._

## Log

Chronological "what was done" lives in the task memo — `memory/notes.md`
(append with `charter workspace note "…"`).

## Sessions

1 session record — the latest is [Title-bar Save saves the plane only; Save all asks first (#404)](sessions/20260929-175318-title-bar-save-saves-the-plane-only-save-all-ask.md) (2026-09-29 17:53); all of them, newest first, in [sessions/index.md](sessions/index.md).
