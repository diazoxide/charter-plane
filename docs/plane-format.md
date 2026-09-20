# The plane format

A **control plane** is a directory marked by `charter.toml`. This document records what is
inside one: every file and every field the Python `charter` reads or writes, as it does today
at commit `50d31dc` (0.62.1).

It exists because charter is being rebuilt as a desktop app on a Rust core (ADR 0025, spec
`docs/superpowers/specs/2026-09-17-charter-app.md`, decision 13). **The plane format does not
change.** The app reads *and writes* the plane in Rust from M1, and answers its own hooks: no
shipped path crosses languages, and Python charter is the differential oracle in CI rather than a
dependency of the app (ADR 0025 as amended, spec decisions 14 and 15). Until Python charter is
retired at M4 both implementations still work on the *same plane at the same time* — the CLI, the
hooks a plane is already wired with and a running tmux frame are Python — so a file one of them
writes is a file the other one may be reading a moment later.

This document is the contract between them. It is descriptive, not aspirational: where the code
and the prose docs disagree, the code is recorded here and the disagreement is named.

## How to read it

Every file is marked **stable** or **internal**.

- **stable** — the rebuild must read it, and write it, exactly as recorded here. A file is
  stable when any of these is true: the operator edits it by hand; it is committed to the
  plane's git and so travels to other machines and people; a process other than the one that
  wrote it reads it; or a harness (Claude Code, opencode, Codex) reads it.
- **internal** — implementation state: written and read by one module as a cache, lock or
  marker, safe to delete, rebuilt on demand. The rebuild may change these, and each entry says
  what deleting it costs.

Marking is deliberately generous. Anything charter writes that another process reads is stable,
because during the migration those two processes are Python charter and the app.

Every claim cites the code that makes it true, as `charter/<module>.py:<line>` at `50d31dc`.
Citations are checked mechanically; if you move code, re-run the check (below).

Four calls were close enough to be worth stating outright:

- **`.charter/frame/**` is the tmux frame's.** The app replaces that frame rather than
  reading its state, so it neither reads nor writes there. The ruling is spelled out at
  [`frame/`](#frame--the-tmux-frames-own-state-chats-panels-reopen), and ADR 0032 records
  what it costs the one ladder that reads a file there — the workspace resolution order.
- **A cache a second process reads is still internal** when deleting it costs only
  recomputation — `cache/harness-wiring.json`, `cache/repostate.json`, `cache/glstate.json`.
  Each entry says what deleting it costs, which is the thing a rebuild actually needs.
- **`.charter-generated` is stable.** Deleting it does not degrade gracefully: every file
  it vouches for is then read as the operator's own and never refreshed again.
- **`.charter/harness-profiles-launched.json` is stable**, though it lives in the state
  directory: it records an operator's consent to run a command, and a second process reads
  it to decide whether to ask again (ADR 0022).

Field tables use: **Required** (must be present), **Optional** (a default applies, given in the
row), and the status of that field where it differs from its file's.

## Contents

- [Fixture planes](#fixture-planes)
  - [Checking the citations](#checking-the-citations)
- [Finding the plane, and the plane root](#finding-the-plane-and-the-plane-root)
  - [Plane-root discovery (no file of its own, but the rule every file below hangs off)](#plane-root-discovery-no-file-of-its-own-but-the-rule-every-file-below-hangs-off)
  - [`charter.toml`](#chartertoml)
  - [`charter.local.toml`](#charterlocaltoml)
  - [`.charter/harness-profiles-launched.json`](#charterharness-profiles-launchedjson)
  - [`.gitignore` (plane root)](#gitignore-plane-root)
  - [Baseline directories: `personas/`, `inventory/`, `workspaces/`](#baseline-directories-personas-inventory-workspaces)
  - [`personas/<front-door>/` (what `charter init` scaffolds at the plane root)](#personasfront-door-what-charter-init-scaffolds-at-the-plane-root)
  - [`inventory/repos.json`](#inventoryreposjson)
  - [`docs/topology.md`](#docstopologymd)
  - [`README.md` — the generated persona roster block](#readmemd--the-generated-persona-roster-block)
  - [Plane-root files that exist but are **not** this area](#plane-root-files-that-exist-but-are-not-this-area)
- [Workspaces](#workspaces)
  - [`workspaces/`](#workspaces-1)
  - [`workspaces/.default`](#workspacesdefault)
  - [`workspaces/<ws>/`](#workspacesws)
  - [`workspaces/<ws>/workspace.md` — the living charter](#workspaceswsworkspacemd--the-living-charter)
  - [`workspaces/<ws>/workspace.json` — the committed manifest](#workspaceswsworkspacejson--the-committed-manifest)
  - [`workspaces/<ws>/memory/` — the task journal](#workspaceswsmemory--the-task-journal)
  - [`workspaces/<ws>/todos/`](#workspaceswstodos)
  - [`workspaces/<ws>/refs/README.md` (and whatever else the operator drops in `refs/`)](#workspaceswsrefsreadmemd-and-whatever-else-the-operator-drops-in-refs)
  - [`workspaces/<ws>/changes/<slug>.json` — a cross-repo change](#workspaceswschangesslugjson--a-cross-repo-change)
  - [`workspaces/<ws>/changes/log/<host>.jsonl` — the landing log](#workspaceswschangesloghostjsonl--the-landing-log)
  - [`workspaces/<ws>/pieces/<host>.jsonl` — the piece claim log](#workspaceswspieceshostjsonl--the-piece-claim-log)
  - [`workspaces/<ws>/pieces/seen/<repo>.json` and `pieces/seen/<repo>/<piece>.json`](#workspaceswspiecesseenrepojson-and-piecesseenrepopiecejson)
  - [`workspaces/<ws>/.charter-structure` — the layout stamp](#workspaceswscharter-structure--the-layout-stamp)
  - [`workspaces/<ws>/.charter-generated` — the harness-layer ownership marker](#workspaceswscharter-generated--the-harness-layer-ownership-marker)
  - [`workspaces/<ws>/.claude/settings.json` — the generated harness layer](#workspaceswsclaudesettingsjson--the-generated-harness-layer)
  - [`workspaces/<ws>/<repo>/` — a cloned repo (guest checkout)](#workspaceswsrepo--a-cloned-repo-guest-checkout)
  - [`<clone>/.git/info/exclude` — charter's managed block](#clonegitinfoexclude--charters-managed-block)
  - [`workspaces/<ws>/.worktrees/<repo>/<piece>/` — pieces](#workspaceswsworktreesrepopiece--pieces)
  - [`.gitignore` (plane root) — the managed live-workspace block](#gitignore-plane-root--the-managed-live-workspace-block)
  - [`.charter/…` — active-workspace pointers and per-plane workspace state](#charter--active-workspace-pointers-and-per-plane-workspace-state)
- [Personas, memory and the roster](#personas-memory-and-the-roster)
  - [`personas/`](#personas)
  - [`personas/<name>/persona.md`](#personasnamepersonamd)
  - [`personas/<name>.md` (legacy flat layout)](#personasnamemd-legacy-flat-layout)
  - [`personas/<name>/memory/MEMORY.md`](#personasnamememorymemorymd)
  - [`personas/<name>/memory/<slug>.md` (and `personas/_shared/memory/<slug>.md`)](#personasnamememoryslugmd-and-personassharedmemoryslugmd)
  - [`personas/<name>/memory/archive/<slug>.md`](#personasnamememoryarchiveslugmd)
  - [`personas/<name>/memory/.gitkeep`, `personas/<name>/refs/.gitkeep`](#personasnamememorygitkeep-personasnamerefsgitkeep)
  - [`personas/<name>/refs/README.md` and `personas/<name>/refs/**`](#personasnamerefsreadmemd-and-personasnamerefs)
  - [`personas/<name>/mcp.json`](#personasnamemcpjson)
  - [`personas/<name>/bin/<script>`](#personasnamebinscript)
  - [`personas/_shared/` (`memory/`, `refs/`)](#personasshared-memory-refs)
  - [`personas/.default` (legacy)](#personasdefault-legacy)
  - [`personas/_dispatch/<YYYY-MM>.<host>.jsonl`](#personasdispatchyyyy-mmhostjsonl)
  - [`personas/_dispatch/<YYYY-MM>.<host>.backfill.jsonl`](#personasdispatchyyyy-mmhostbackfilljsonl)
  - [`personas/_skills/<YYYY-MM>.<host>.jsonl`](#personasskillsyyyy-mmhostjsonl)
  - [`.claude/agents/<name>.md` (generated sub-agent)](#claudeagentsnamemd-generated-sub-agent)
  - [`.charter/persona-state/ephemeral/<session>/<name|_shared>/<slug>.md`](#charterpersona-stateephemeralsessionnamesharedslugmd)
  - [`.charter/persona-state/trace/<session>.jsonl`](#charterpersona-statetracesessionjsonl)
  - [`.charter/reports/<id>.json`](#charterreportsidjson)
  - [`~/.config/charter/reporting-consent` (outside the plane)](#configcharterreporting-consent-outside-the-plane)
  - [`.charter/sessions/<sid>.persona`, `.charter/terminals/<tid>.persona`, `.charter/active-persona`](#chartersessionssidpersona-charterterminalstidpersona-charteractive-persona)
  - [`.charter/mcp-approved.json`](#chartermcp-approvedjson)
  - [`[memory] share` — how it affects persona files](#memory-share--how-it-affects-persona-files)
- [Vaults: the registry, and nothing inside it](#vaults-the-registry-and-nothing-inside-it)
  - [`vaults.json` (plane root — the SHARED half)](#vaultsjson-plane-root--the-shared-half)
  - [`.charter/vaults.json` (the LOCAL half)](#chartervaultsjson-the-local-half)
  - [`.charter/vaults/` (directory)](#chartervaults-directory)
  - [`.charter/vaults/<name>.json` — plain-file vault](#chartervaultsnamejson--plain-file-vault)
  - [`.charter/vaults/<name>.meta.json` — rotation sidecar](#chartervaultsnamemetajson--rotation-sidecar)
  - [`.charter/vaults/<name>.json` — reference vault (same path, different content)](#chartervaultsnamejson--reference-vault-same-path-different-content)
  - [Secret reference syntax](#secret-reference-syntax)
  - [`.charter/fingerprint.key`](#charterfingerprintkey)
  - [1Password provider — not a file, but a shape another implementation must match](#1password-provider--not-a-file-but-a-shape-another-implementation-must-match)
  - [Guarded paths (why a harness cannot read any of the above)](#guarded-paths-why-a-harness-cannot-read-any-of-the-above)
- [Files charter writes that a harness reads](#files-charter-writes-that-a-harness-reads)
  - [2a. Inside the plane](#2a-inside-the-plane)
  - [`<plane>/.claude/settings.json`](#planeclaudesettingsjson)
  - [`<plane>/.claude/settings.local.json`](#planeclaudesettingslocaljson)
  - [`<plane>/opencode.json`](#planeopencodejson)
  - [`<plane>/.gitignore` (the lines charter owns)](#planegitignore-the-lines-charter-owns)
  - [Generated harness layer in `workspaces/<ws>/` and in clones](#generated-harness-layer-in-workspacesws-and-in-clones)
  - [2b. Outside the plane (machine-global)](#2b-outside-the-plane-machine-global)
  - [`~/.config/opencode/plugin/charter.ts` (`$XDG_CONFIG_HOME` honoured)](#configopencodeplugincharterts-xdgconfighome-honoured)
  - [`~/.config/opencode/command/charter.md`](#configopencodecommandchartermd)
  - [`~/.config/opencode/charter-context.md`](#configopencodecharter-contextmd)
  - [`~/.config/opencode/opencode.json`](#configopencodeopencodejson)
  - [`~/.codex/config.toml` (`$CODEX_HOME` honoured)](#codexconfigtoml-codexhome-honoured)
  - [Claude Code's own files — charter does NOT write them](#claude-codes-own-files--charter-does-not-write-them)
  - [The shipped plugin's `hooks/hooks.json`](#the-shipped-plugins-hookshooksjson)
  - [2c. Git config charter sets](#2c-git-config-charter-sets)
  - [2d. Charter-private caches in this area](#2d-charter-private-caches-in-this-area)
  - [`.charter/cache/harness-wiring.json`](#chartercacheharness-wiringjson)
  - [`.charter/unrecorded/<sha256[:32]>.json`](#charterunrecordedsha25632json)
- [`.charter/` — runtime state](#charter--runtime-state)
  - [Conventions that apply to every file in this area](#conventions-that-apply-to-every-file-in-this-area)
  - [`sessions/` — per-session markers](#sessions--per-session-markers)
  - [`sessions/<sid>.workspace`](#sessionssidworkspace)
  - [`sessions/<sid>.lock`](#sessionssidlock)
  - [`sessions/<sid>.tools` — the persona tool **ceiling**](#sessionssidtools--the-persona-tool-ceiling)
  - [`sessions/<sid>.gate` — "a ceiling was taken for this session"](#sessionssidgate--a-ceiling-was-taken-for-this-session)
  - [`sessions/<sid>.usage` — token/cache trend ring buffer](#sessionssidusage--tokencache-trend-ring-buffer)
  - [`sessions/<sid>.memnudge`](#sessionssidmemnudge)
  - [`sessions/<sid>.configver`](#sessionssidconfigver)
  - [`sessions/<sid>.<tool_use_id>.<kind>.ask-pending`](#sessionssidtooluseidkindask-pending)
  - [`sessions/<sid>.route-pending`](#sessionssidroute-pending)
  - [`sessions/<sid>.persona`](#sessionssidpersona)
  - [`terminals/` — per-pane pointers](#terminals--per-pane-pointers)
  - [`terminals/<tid>.workspace`, `terminals/<tid>.persona`](#terminalstidworkspace-terminalstidpersona)
  - [`frame/` — the tmux frame's own state (chats, panels, reopen)](#frame--the-tmux-frames-own-state-chats-panels-reopen)
  - [`frame/chat-ids.json`](#framechat-idsjson)
  - [`frame/chat-ids.lock`](#framechat-idslock)
  - [`frame/<chat>/` — one directory per chat](#framechat--one-directory-per-chat)
  - [`frame/reopen.json`](#framereopenjson)
  - [`frame/<chat>.transcript`](#framechattranscript)
  - [`frame/<frame-id>/` for a non-chat frame (e.g. the live plane's `probe-1`)](#frameframe-id-for-a-non-chat-frame-eg-the-live-planes-probe-1)
  - [`app/` — the desktop app's own state](#app--the-desktop-apps-own-state)
  - [`app/reopen.json`](#appreopenjson)
  - [Top-level markers, gates and ledgers](#top-level-markers-gates-and-ledgers)
  - [`chat-turns/<chat>`](#chat-turnschat)
  - [`dispatch-inflight/<agent>.<random>.json`](#dispatch-inflightagentrandomjson)
  - [`commit-gate/<sid>`](#commit-gatesid)
  - [`dispatch-commit.lock`](#dispatch-commitlock)
  - [`guard-seen.json`](#guard-seenjson)
  - [`mcp-approved.json`](#mcp-approvedjson)
  - [`agent-personas.json`](#agent-personasjson)
  - [`plane-push.json`](#plane-pushjson)
  - [`ws-edit-nudge/<sid>-<workspace>`](#ws-edit-nudgesid-workspace)
  - [`ws-autosave/<workspace>`](#ws-autosaveworkspace)
  - [`workspace-tab-order`](#workspace-tab-order)
  - [`workspace-arrivals/<workspace>`](#workspace-arrivalsworkspace)
  - [`unrecorded/<sha256(realpath(tree))[:32]>.json`](#unrecordedsha256realpathtree32json)
  - [`locks/harness-wiring-<digest16>.lock`](#locksharness-wiring-digest16lock)
  - [`active-workspace` (legacy)](#active-workspace-legacy)
  - [`active-persona`](#active-persona)
  - [`cache/` — derived data with a TTL](#cache--derived-data-with-a-ttl)
  - [`cache/repostate.json`](#cacherepostatejson)
  - [`cache/glstate.json`](#cacheglstatejson)
  - [`cache/glstate.refreshing`](#cacheglstaterefreshing)
  - [`cache/update.json` and `cache/update.checking`](#cacheupdatejson-and-cacheupdatechecking)
  - [`cache/update-baseline`](#cacheupdate-baseline)
  - [`cache/vaulthealth.json`](#cachevaulthealthjson)
  - [`cache/harness-wiring.json`](#cacheharness-wiringjson)
  - [State charter keeps **outside** the plane](#state-charter-keeps-outside-the-plane)
  - [Environment variables that move or key this state](#environment-variables-that-move-or-key-this-state)
  - [What the tmux frame and the status line read that a **hook** wrote](#what-the-tmux-frame-and-the-status-line-read-that-a-hook-wrote)
- [Appendix: what this survey found in the code](#appendix-what-this-survey-found-in-the-code)
  - [In the plane root](#in-the-plane-root)
  - [In workspaces](#in-workspaces)
  - [In personas and memory](#in-personas-and-memory)
  - [In the vaults and the harness wiring](#in-the-vaults-and-the-harness-wiring)
  - [In `.charter/`](#in-charter)

## Fixture planes

The spec asks for fixture planes both implementations test against. They live in the
`charter-app` repo, at `tests/fixtures/planes/`, and they are **generated by running this
charter** — never hand-written — so they are true by construction. That repo's
`tests/fixtures/planes/generate.py` records the exact commands, and its README records what is
pinned (clock, hostname, user, session id, `PATH`) to keep a regeneration byte-identical, and
what a committed fixture cannot carry (every `.git` directory, the caches keyed by absolute
path, `fingerprint.key`, and the empty directories a fresh plane has — `inventory/` and
`workspaces/` — which are recorded beside each plane instead).

There are two: `minimal`, what `charter init` leaves behind, and `daily`, a plane in use — a
LIVE workspace with a clone, memory, todos and a snapshot; a second workspace left local; a
second persona with its own and shared memory; a vault registry; and the session state a
harness run leaves in `.charter/`. A file documented here that no fixture holds is one no
offline command writes; the entry for it says which writer to call instead.

One practical note for an agent working with them: charter's guard denies tool calls that
read a `.charter/vaults/` path, and it cannot know that a fixture vault holds only the
literal `fixture-not-a-secret`. Expect the denial, and do not work around it.

### Checking the citations

`tests/test_the_plane_format_spec_cites_lines_that_exist.py` walks every citation in this
document and fails if the file is gone, the line is past the end of it, or the line is blank —
the three ways a line number rots when code moves under it. It is a pointer check, not a truth
check: it cannot tell whether the cited line still says what this document claims. If it goes
red, re-derive the numbers rather than editing them by hand.

## Finding the plane, and the plane root

Covered here: `charter.toml`, `charter.local.toml`, `.charter/harness-profiles-launched.json`,
plane-root discovery, `.gitignore`, the baseline directories, the `charter init` front-door
scaffold, `inventory/repos.json`, `docs/topology.md`, and the generated README roster block.

---

### Plane-root discovery (no file of its own, but the rule every file below hangs off)

- **Marker:** `charter.toml` at the directory — `is_file`, never a directory
  (`charter/root.py:17`, `charter/root.py:62`). **Status: stable** — it is the one thing a
  second implementation must agree on to find the same plane.
- **Resolution order** (`charter/root.py:32`, `find_root`):
  1. `$CHARTER_ROOT` wins outright; it is `expanduser`'d and `resolve`'d, and a value with no
     `charter.toml` under it **raises** rather than falling back to the walk
     (`charter/root.py:49`, `charter/root.py:56`).
  2. Otherwise walk up from `start` (default cwd, resolved) through `(cur, *cur.parents)`
     (`charter/root.py:60`).
  3. A found marker is redirected to the **main working tree** when the directory is a linked
     git worktree whose main tree also carries the marker (`charter/root.py:310` `_plane_of`,
     `charter/root.py:157` `main_worktree_of` — pure path arithmetic on the `.git` file's
     `gitdir:` line, no subprocess).
  4. Then hop **outward** through any enclosing plane's `workspaces/` until the answer stops
     moving (`charter/root.py:91` `_outermost`, `charter/root.py:333` `enclosing_plane`: the
     enclosing marker only counts when `here.relative_to(parent/"workspaces")` succeeds,
     `charter/root.py:363`).
  5. If no marker at all: if the cwd (or an ancestor) is a linked worktree, retry from its
     main tree and that tree's parents (`charter/root.py:79`).
  6. Still nothing → `ControlPlaneNotFound` (`charter/root.py:88`); `find_root_or_cwd`
     swallows that and returns the start directory instead (`charter/root.py:370`), which is
     what makes `charter --version` and `charter init` work outside a plane.
- `config` bootstraps from this at **import** of any command
  (`charter/config.py:918`), and `config.use(root)` re-points the whole module
  (`charter/config.py:844`). `charter init` calls `use()` the moment it writes the marker
  (`charter/commands.py:2718` then `config.use(root)`).
- **Env vars charter honours here:** `CHARTER_ROOT` (`charter/root.py:20`), `CHARTER_HOME`
  (the state dir, `charter/config.py:42`), `CHARTER_WORKTREES` (`charter/config.py:82`).
- `NESTED_ORIGIN` records the nested plane the caller stands in when the hop fired
  (`charter/config.py:697`, `charter/root.py:131`).
- `.charter-generated` / `.charter-structure` are **workspace-interior** markers written by
  `charter/workspace.py:1935` and `charter/workspace.py:4477`, not plane-root ones — they
  belong to the workspaces area.

Paths derived from the root (all in `derive`, `charter/config.py:661`) that land in this area:
`ROOT` (`:680`), `HAS_CONTROL_PLANE` (`:684`), `SHARED_VAULTS = root/"vaults.json"` (`:774`),
`WORKSPACES_DIR` (`:780`), `INVENTORY = root/"inventory"/"repos.json"` (`:783`),
`DOCS_DIR = root/"docs"` (`:786`), `PERSONAS_DIR` (`:819`), `STATE_DIR` (`:791`).

---

### `charter.toml`

- **Format:** TOML (parsed with stdlib `tomllib`, `charter/instance.py:122`). Hand-maintained;
  charter only ever edits two keys, as raw text.
- **Status:** **stable** — committed, hand-edited, and read by every charter process, every
  hook process, and the frame's panel processes.
- **Written by:** `charter/commands.py:1066` `_render_charter_toml` (via `cmd_init`,
  `charter/commands.py:2718`) for a fresh plane; thereafter only
  `charter/instance.py:389` `_set_key` — a **line-span textual edit** used by
  `set_locked_version` (`charter/instance.py:325`), `set_default_persona`
  (`charter/instance.py:331`), `declare_default_persona` (`:342`) and
  `clear_default_persona` (`:355`). `charter version bump` also commits it
  (`charter/commands.py:3842`).
- **Read by:** `charter/instance.py:105` `load` — and *only* there:
  `charter/config.py:719` (every command/hook, at import), plus direct re-reads in
  `charter/commands.py:211`, `charter/commands.py:3614`, `charter/hooks.py:7260`,
  `charter/statusline.py:2123`, `charter/statusline.py:2141`, `charter/doctor.py:343`,
  `charter/persona.py:1031`, `charter/profiles.py:432`, `charter/forge/registry.py:96`,
  `charter/forge/registry.py:140`, `charter/commands_update.py:604`.
- **Git:** committed (nothing ignores it; `_GITIGNORE_BASELINE` ignores its *local* sibling
  only, `charter/commands.py:1104`).
- **Encoding details for a byte-identical writer:**
  - `init` renders exactly: `schema = 1`, blank, `[[forge]]`, `kind = "<kind>"`, optional
    `owner = "..."`, optional `host = "..."`, blank, `[memory]`, `share = "local"`, trailing
    newline (`charter/commands.py:1066`–`charter/commands.py:1078`). String values go through
    `json.dumps` (`charter/commands.py:1058` `_toml_str`) — JSON escaping is used as a
    faithful subset of TOML basic-string escaping.
  - `_set_key` (`charter/instance.py:389`) reads with `splitlines(keepends=True)` and writes
    with `p.write_text("".join(lines))` (`charter/instance.py:441`) — **not** atomic, no temp
    file, no lock, comments and formatting preserved.
    - Section located by `^[ \t]*\[<section>\][ \t]*$`; the edit is confined to that section's
      span, ending at the next line matching `^[ \t]*\[` (`charter/instance.py:416`,
      `charter/instance.py:426`).
    - Existing key: only the value is replaced, the `key<spaces>=<spaces>` prefix is kept
      (`charter/instance.py:441`).
    - Key absent, section present: inserted as the **first line after the header**,
      `key = "value"\n` (`charter/instance.py:438`).
    - Section absent: appended as `"\n", "[<section>]\n", 'key = "value"\n'` after a newline
      fixup if the file did not end in one (`charter/instance.py:424`).
    - Removal (`value=None`) deletes the key line and **leaves the emptied section header**
      (`charter/instance.py:436`); a missing section or missing key rewrites nothing.
    - Values are always emitted double-quoted, so only string-valued keys are writable this
      way. Measured: `set_locked_version` on the `init` output appends
      `\n[charter]\nversion = "0.62.1"\n`.
- **Schema/refusal:** `plane_version` (`charter/instance.py:79`) — absent `schema` means
  `UNSTAMPED = 1` (`charter/instance.py:63`), a non-`int` (or `bool`) value means "cannot
  place" → `PlaneFormatUnknown`; `found > SCHEMA` → `SchemaTooNew`
  (`charter/instance.py:133`). `config.derive` records it as `PLANE_REFUSAL`
  (`charter/config.py:723`) and `cli` declines every command except
  `doctor`/`update`/`version`/`_version-check` (`charter/cli.py:2224` `_DESPITE_REFUSAL`,
  `charter/cli.py:2239`). Malformed TOML instead raises `ValueError`, is caught, and becomes
  `CONFIG_ERROR` with empty defaults (`charter/config.py:725`, `charter/doctor.py:323`).
- **General rule for every `[section]` below:** an absent or wrong-typed section/value
  **degrades to the shipped default** and never raises — `charter.toml` is on the import path
  of `charter --version` (`charter/instance.py:1994`, `:2955`, `:3039`). The two exceptions
  that *report* rather than swallow are `[harness] default` (`refused`,
  `charter/instance.py:3097`) and `[[frame.component]]` (whole arrangement refused,
  `charter/instance.py:2400`).

| Field | Type | Required / default | Meaning | Status | Source |
|---|---|---|---|---|---|
| `schema` | int (top level) | optional; absent = 1 | Plane format version. Only buys refusal. | stable | `charter/instance.py:98` |
| `[[forge]]` | array of tables | optional; none = one default GitLab forge | One block per forge tracked. Index 0 is `config.GROUP`/`EXCLUDE`. | stable | `charter/instance.py:143` |
| `[[forge]].kind` | str | default `"gitlab"`; one of `gitlab`, `github` | Backend class. Unknown kind = that block skipped + reported. | stable | `charter/forge/registry.py:69`, `charter/forge/registry.py:15` |
| `[[forge]].group` / `.owner` | str | optional; `group` wins, else `owner`, else `""` | Org/group whose repos are discovered. | stable | `charter/instance.py:162` |
| `[[forge]].host` | str | optional; default `gitlab.com` / `github.com` | Self-hosted host. Must match `_HOST_RE` (bare host, optional `:port`) or the block is refused. | stable | `charter/forge/registry.py:29`, `charter/forge/registry.py:56` |
| `[[forge]].exclude` | array of str | optional; default `()` | Repo names never written to the inventory; per block. | stable | `charter/instance.py:170` |
| `[memory].share` | str | default `"local"`; one of `local`,`commit`,`push` | How far a written memory travels. Unknown value clamps to `local`. | stable | `charter/instance.py:466`, `charter/instance.py:265` |
| `[workspace].default` | str | default `"default"` | Workspace used when nothing else selected. Validated by `workspace_name_ok` (`^[A-Za-z0-9][A-Za-z0-9._-]*$` + `contain.segment_ok`); invalid → fallback. | stable | `charter/instance.py:243`, `charter/instance.py:181` |
| `[persona].default` | str | optional; blank = absent = `None` | The plane's front door persona. Written by `charter persona default`. | stable | `charter/instance.py:259` |
| `[plane].worktrees` | str | optional; `None` = `workspaces/<ws>/.worktrees/` | Relocated worktree root. Relative resolves against ROOT; a committed value must satisfy `contain.plane_adjacent` or it is ignored (doctor warns). `$CHARTER_WORKTREES` overrides and is unrestricted. | stable | `charter/instance.py:488`, `charter/config.py:82` |
| `[charter].version` | str | optional | The version lock. Reported **as written** (even if malformed); must match `^\d+\.\d+\.\d+$` before it is acted on. | stable | `charter/instance.py:321`, `charter/instance.py:290` |
| `[update].channel` | str | default `"stable"`; closed set `stable`,`dev` | Which charter this plane tracks. Unknown → `stable`; the matched **constant** is stored, never the file's string. | stable | `charter/instance.py:2948`, `charter/instance.py:2936` |
| `[harness].default` | str | default `None` | What bare `charter` launches. Matched against the harness registry's `cli_name`s; a non-match is recorded as `refused` (contained) rather than ignored. | stable | `charter/instance.py:3000`, `charter/instance.py:3088` |
| `[harness.<name>]` | table | — | **Refused here**: profiles live in `charter.local.toml`. Reported by name. | stable | `charter/profiles.py:316`, `charter/profiles.py:132` |

#### `[frame]` — every key, via `FRAME_FIELDS` (`charter/instance.py:1652`)

Merged over `FRAME_DEFAULTS` by `frame_of` (`charter/instance.py:1994`); the section must be a
table or the defaults are returned whole (`charter/instance.py:2064`). Only the **TOML
spelling** is honoured — three keys are hyphenated; the underscore form is not an alias.
Type-checked against the default (`charter/instance.py:2147`: a `bool`/non-`bool` mismatch is
rejected first, then `isinstance(value, type(default))`).

| Field | Type | Default | Meaning | Status | Source |
|---|---|---|---|---|---|
| `slots` | list[str] | `["top","bottom","repos","right"]` | Edges to draw, **in split order (geometry)**. Filtered against `FRAME_SLOTS` (`top`,`bottom`,`repos`,`right`); an empty result is treated as "not written". | stable | `charter/instance.py:1682`, `charter/instance.py:564` |
| `density` | str | `"full"` | Preset over `slots`: `minimal`/`normal`/`full`. Expands to `slots` **only when declared and no usable explicit `slots`**. Carries a `verbosity` (`terse`/`normal`). | stable | `charter/instance.py:1692`, `charter/instance.py:628` |
| `mouse` | bool | `false` | tmux mouse reporting. | stable | `charter/instance.py:1752` |
| `chrome` | str | `"off"` | Pane surface: `off`/`dark`/`light`. Word is a key into `FRAME_CHROME`; never a style string. | stable | `charter/instance.py:1766`, `charter/instance.py:729` |
| `rules` | str | `"hidden"` | Pane-seam treatment: `hidden`/`visible`. | stable | `charter/instance.py:1788`, `charter/instance.py:1161` |
| `text` | str | `"default"` | Frame foreground; one of `FRAME_PANE_FG`'s 17 words (`default`, 8 ANSI names, 8 `bright*`). | stable | `charter/instance.py:1796`, `charter/instance.py:983` |
| `dim` | bool | `true` | Whether SGR 2 is appended to charter's rules. | stable | `charter/instance.py:1816` |
| `ok` / `warn` / `bad` | str | `"green"` / `"yellow"` / `"red"` | Accent colours; same 17-word vocabulary as `text`. | stable | `charter/instance.py:1845` |
| `hotkey` | str | `"F2"` | Palette key. Must match `_HOTKEY_RE` **and** differ from the frame gate key, or it degrades to the default — a newline here reached tmux config text (measured RCE). | stable | `charter/instance.py:1848`, `charter/instance.py:1937`, `charter/instance.py:2134` |
| `record` | bool | `true` | Whether the frame writes the plane down as it changes. | stable | `charter/instance.py:1858` |
| `restore` | bool | `true` | Whether bare `charter` puts the recorded plane back. | stable | `charter/instance.py:1870` |
| `history-limit` | int | `50000` | tmux scrollback. | stable | `charter/instance.py:1871` |
| `min-cols` | int | `100` | Below this, slots are dropped. | stable | `charter/instance.py:1872` |
| `min-rows` | int | `20` | Same, vertically. | stable | `charter/instance.py:1873` |

#### `[[frame.component]]` — the arrangement (`charter/instance.py:2421`)

An array of tables; the whole arrangement is **refused as one** on the first bad key
(`charter/instance.py:2400` carries the sentence, and `frame_of` stores it as
`components_refused`, `charter/instance.py:2158`). When accepted it **replaces** `slots`
(`charter/instance.py:2160`). The complete key form is
`("use","edge","size","visible","key","bg","pad")` (`charter/instance.py:2204`) — any other
key refuses.

| Field | Type | Required / default | Meaning | Status | Source |
|---|---|---|---|---|---|
| `use` | str | required, unique | Component id: a built-in (`identity`, `attention`, `repos`, `sidebar`, `personas`, `todos`, `changes`, `chats`, `workspaces` — `charter/frame/builtins.py:985`ff) or an id an installed distribution supplies. | stable | `charter/instance.py:2624`, `charter/instance.py:2802` |
| `edge` | str | required for a non-built-in; for a built-in it may only **echo** its own edge | One of `top`,`bottom`,`left`,`right` (`charter/frame/component.py:55`). | stable | `charter/instance.py:2801`, `charter/instance.py:2758` |
| `size` | int | required (≥1) for a non-built-in; for a built-in only where the built-in's size is `Content`, else it may only echo | Cells. | stable | `charter/instance.py:2811`, `charter/instance.py:2273` |
| `visible` | bool | default `true` | Whether it is drawn at launch (invisible components still get a toggle key). | stable | `charter/instance.py:2661` |
| `key` | str | optional | tmux toggle key; `toggle_key`/`_HOTKEY_RE`, and refused if already bound (palette, hatch, gate, mouse keys, another component). | stable | `charter/instance.py:2667`, `charter/instance.py:2710` |
| `bg` | str | optional | One of `FRAME_PANE_BG`'s 17 words. | stable | `charter/instance.py:2725`, `charter/instance.py:886` |
| `pad` | int | default `0`, max `5` | Horizontal inset, out of the content budget; `bool` refused. | stable | `charter/instance.py:2742`, `charter/instance.py:1046` |

---

### `charter.local.toml`

- **Format:** TOML. **Charter never writes this file** — it is hand-edited (or edited by a
  chat) and read only.
- **Status:** **stable** — the operator edits it by hand, and two different processes read it
  (the CLI/`doctor`, and the frame launcher/selector on a launch).
- **Written by:** nobody in charter. `charter init`/`reinit` only add the `.gitignore` line for
  it (`charter/commands.py:1803`, `charter/commands.py:1806`).
- **Read by:** `charter/profiles.py:240` `_read_local` (the only reader), through
  `charter/profiles.py:284` `derive` and `charter/profiles.py:404` `current` (memoized per
  process on `(root, local bytes, charter.toml bytes)`, `charter/profiles.py:428`). Surfaces:
  `charter harness list` (`charter/commands_harness.py:62`), `charter doctor`
  (`charter/doctor.py:755`), the launcher/selector (`charter/frame/launcher.py:478`,
  `charter/frame/selector.py:25`).
- **Git:** gitignored — the baseline writes `/charter.local.toml`
  (`charter/commands.py:1104`), and `reinit` backfills it
  (`charter/commands.py:1821`). If git *would* carry it (tracked, committable, or git cannot
  say), **every profile in it is refused** (`charter/profiles.py:518` `ignore_check`,
  `charter/profiles.py:456` `with_ignore_check`).
- **Encoding details:** only `[harness]` is read; any other top-level key is refused with a
  sentence (`charter/profiles.py:325`). A missing file declares nothing and is not a refusal
  (`charter/profiles.py:241`). Profile `env` is stored **sorted by name**
  (`charter/profiles.py:363`), and `~` in `command[0]` and in every `env` value is expanded
  only at launch (`charter/profiles.py:474`, `charter/profiles.py:480`) — never in the file
  and never in the launch record.

| Field | Type | Required / default | Meaning | Status | Source |
|---|---|---|---|---|---|
| `[harness].default` | str | optional | Which profile the selector starts on; wins over `charter.toml`'s. Kept only if it names a profile that survived validation, else recorded as `default_refused`. | stable | `charter/profiles.py:76`, `charter/profiles.py:336`, `charter/profiles.py:366` |
| `[harness.<name>]` | table | one per profile | A profile. Name must match `^[A-Za-z0-9][A-Za-z0-9_-]*$` (no dot), may not be `default`, may not collide with a `charter` command word, and replaces a built-in of the same name (a *refused* one takes the name with it). | stable | `charter/profiles.py:69`, `charter/profiles.py:255`, `charter/profiles.py:443`, `charter/profiles.py:359` |
| `…​.kind` | str | required | The word typed after `charter`: `claude`/`codex`/`opencode` (registry `cli_name`s). | stable | `charter/profiles.py:257` |
| `…​.command` | list[str] | required, non-empty, all non-empty strings | argv. Never a shell string — no shell runs it. Refused if its first word is charter itself. | stable | `charter/profiles.py:261`, `charter/profiles.py:445` |
| `…​.env` | table of str→str | optional, default `{}` | Environment for the harness process. A name starting `CHARTER_` is refused; a name containing `KEY`/`TOKEN`/`SECRET`/`PASSWORD` (case-insensitive) is refused. | stable | `charter/profiles.py:265`, `charter/profiles.py:89`, `charter/profiles.py:58` |
| any other key in a profile table | — | — | Refuses that profile (e.g. `enviroment`). | stable | `charter/profiles.py:86`, `charter/profiles.py:278` |

---

### `.charter/harness-profiles-launched.json`

- **Format:** JSON object, `{ "<profile name>": {"kind": str, "command": [str], "env": {str: str}} }`.
- **Status:** **stable** — it lives under `.charter/` and is written and read by *different*
  processes (a launch, a frame keypress under a hook, a `charter reopen`), and it decides
  whether a command runs. It is not safe to delete in the "no consequence" sense: deleting it
  makes every declared profile ask for approval again (it fails towards asking, never towards
  running — `charter/profiletrust.py:129`).
- **Written by:** `charter/profiletrust.py:155` `record_launched` — `config.replace_for`
  (atomic temp+rename, private 0600) of `json.dumps({**_read(), name: fingerprint}, indent=2) + "\n"`
  (`charter/profiletrust.py:172`). Triggered by approving a profile at the prompt
  (`charter/profiletrust.py:303`) and by a launch that runs one.
- **Read by:** `charter/profiletrust.py:138` `_read` → `last_launched`
  (`charter/profiletrust.py:144`), `approval_needed` (`charter/profiletrust.py:195`),
  `refusal` (`charter/profiletrust.py:306`), the frame launcher and `charter reopen`.
- **Git:** gitignored (inside `/.charter/`, `charter/commands.py:1096`).
- **Encoding details:** `indent=2`, trailing newline, `ensure_ascii` default (true); key order
  is insertion order of the existing document with an updated key keeping its position; `env`
  is a dict built from the already-sorted `Profile.env` pairs (`charter/profiletrust.py:126`).
  Whole-file read-modify-write with **no lock** — two concurrent approvals can lose one. Mode
  0600 and the directory 0700 via `config.private_mkdir`/`replace_for`
  (`charter/config.py:389`, `charter/config.py:595`).
  The fingerprint is **as declared, before `~` expansion** (`charter/profiletrust.py:121`).
  A built-in profile is never recorded and never asks (`charter/profiletrust.py:187`).

---

### `.gitignore` (plane root)

- **Format:** plain text, line-oriented, append-only from charter's side.
- **Status:** **stable** — committed, hand-edited, and it carries two literal anchors other
  charter code depends on.
- **Written by:**
  - `charter/commands.py:1116` `_ensure_gitignore` (from `cmd_init`): writes
    `_GITIGNORE_BASELINE` verbatim when the file is absent (`charter/commands.py:1129`),
    otherwise appends only the missing whole lines through the one shared appender.
  - `charter/util.py:472` `append_gitignore` — the single writer for additions. It appends
    `"\n\n"`-separated: existing body `rstrip("\n") + "\n\n"`, then `# <header>\n`, then one
    line each (`charter/util.py:499`). Headers seen: ``added by `charter init` ``
    (`charter/commands.py:1152`), ``added by `charter guard --local` ``
    (`charter/commands.py:1792`), ``added by `charter reinit` — harness profiles stay on this machine``
    (`charter/commands.py:1821`), ``added by `charter browser install` `` (`charter/browser.py:173`).
  - `charter/workspace.py:1408` `_write_live_block` rewrites the managed live-workspace block
    (markers `charter/workspace.py:1338`, `charter/workspace.py:1339`) — **workspaces area**,
    noted here only because it splices at the `!/workspaces/.gitkeep` anchor.
- **Read by:** `charter/workspace.py:1346` `live_workspaces`, the presence checks in
  `charter/commands.py:1134`, `charter/util.py:494`, plus git itself (the real consumer).
- **Git:** committed.
- **Encoding details:** the baseline is a fixed here-doc (`charter/commands.py:1087`–`:1113`),
  comments included, and the exact lines matter:
  - `/workspaces/*/*` (`charter/commands.py:1091`) and `!/workspaces/.gitkeep`
    (`charter/commands.py:1092`) — the second is the **literal anchor**
    `workspace.set_live` splices the managed block after (`charter/workspace.py:1414`).
  - `/.charter/` (`charter/commands.py:1096`)
  - `/.claude/settings.local.json` (`charter/commands.py:1100`, constant at
    `charter/commands.py:1771`)
  - `/charter.local.toml` (`charter/commands.py:1104`, constant at `charter/commands.py:1803`)
  - `__pycache__/`, `*.py[cod]`, `.venv/`, `.DS_Store` (`charter/commands.py:1107`–`:1112`)
  - Presence detection is **whole-line, stripped**, except `.charter/` which is a substring
    test on the body (`charter/commands.py:1136`) — both quirks are deliberate and recorded.
  - Plain `write_text`; no atomic write, no lock.

---

### Baseline directories: `personas/`, `inventory/`, `workspaces/`

- **Format:** directories. **Status: stable** — `instance.drift` reports their absence and
  `charter reinit` heals it, and their names are part of the layout a second implementation
  must resolve.
- **Written by:** `charter/commands.py:2907` `_create_baseline_dirs` (shared by `cmd_init`
  `charter/commands.py:2685` and `cmd_reinit` `charter/commands.py:2934`) over
  `instance.BASELINE_DIRS` (`charter/instance.py:504`). Plain `mkdir(parents=True,
  exist_ok=True)`, never tightened (they are committed content). A baseline path occupied by a
  **file** is reported as blocked and the command exits 1 — charter never deletes or renames.
- **Read by:** `charter/instance.py:507` `drift`, `charter/doctor.py:441`
  `check_control_plane_schema`, and every consumer of `PERSONAS_DIR`/`WORKSPACES_DIR`/`INVENTORY`.
- **Git:** committed (empty dirs are not, in practice — note below).
- **Defect worth recording:** nothing creates `workspaces/.gitkeep`, although the baseline
  `.gitignore` names it as a negation and as the splice anchor (`charter/commands.py:1092`).
  Measured on a fresh `charter init`: `workspaces/` is created empty and no `.gitkeep` is
  written, so an empty `workspaces/` does not survive a clone. Only
  `personas/<front-door>/{memory,refs}/.gitkeep` is written (`charter/commands.py:2680`).

---

### `personas/<front-door>/` (what `charter init` scaffolds at the plane root)

- **Status:** **stable** (committed). The persona file *format* is the personas area's; what
  belongs here is only that `init` creates it and declares it.
- **Written by:** `charter/commands.py:2651` `_ensure_front_door`, called from `cmd_init`.
  Default name `steward` (`charter/cli.py:114`), `--front-door NAME` renames it,
  `--no-front-door` suppresses it (`charter/cli.py:117`).
  - Skipped entirely if the plane already has **any** persona (`personas/*/persona.md` or the
    legacy `personas/*.md`) or if `[persona] default` is already declared
    (`charter/commands.py:2669`).
  - Writes `personas/<name>/persona.md` from the `_FRONT_DOOR` template
    (`charter/commands.py:2597`), with `{name}` and a title-cased `{role}` derived from the
    name (`-`/`_` → space, `.title()`), then `memory/.gitkeep` and `refs/.gitkeep`
    (`charter/commands.py:2680`), then `instance.set_default_persona`
    (`charter/commands.py:2681`).
- **Git:** committed.

---

### `inventory/repos.json`

- **Format:** JSON object.
- **Status:** **stable** — tracked in git, shared across machines, and read by commands,
  `doctor` and the status line.
- **Written by:** `charter/inventory.py:292` `save` (only writer), called from
  `charter/commands.py:172` (`charter discover`).
- **Read by:** `charter/inventory.py:71` `load` → `charter/inventory.py:173` `repos`
  (`charter/commands.py:218`, `:366`, `:641`, `:880`; `charter/statusline.py:792`;
  `charter/doctor.py:3674`), and `charter/inventory.py:265` `find`.
- **Git:** committed (nothing ignores `inventory/`).
- **Encoding details:** `json.dumps(doc, indent=2, ensure_ascii=False) + "\n"` via
  `write_text` (`charter/inventory.py:315`) — not atomic, no lock; the parent directory is
  created first (`charter/inventory.py:314`). Records are **sorted by `name`**
  (`charter/inventory.py:304`), and `merge` sorts the same way
  (`charter/inventory.py:262`). Deliberately **no generated-at timestamp**
  (`charter/inventory.py:295`). Records whose `source` is `"plane"` are stripped before
  writing (`charter/inventory.py:303`, `charter/inventory.py:81`) — the plane's own repo is
  derived at read time from `git remote get-url origin` (`charter/inventory.py:97`), never
  persisted. Key order is the literal dict order below.

| Field | Type | Required / default | Meaning | Status | Source |
|---|---|---|---|---|---|
| `group` | str | required | `config.GROUP` at write time (first `[[forge]]`'s group/owner). | stable | `charter/inventory.py:306` |
| `count` | int | required | `len(repos)`. | stable | `charter/inventory.py:307` |
| `note` | str | required | Fixed sentence naming the group and `charter discover`; absent from the empty skeleton `load` returns. | stable | `charter/inventory.py:308` |
| `repos` | array of record | required | The repos, sorted by `name`. | stable | `charter/inventory.py:312` |
| `repos[].name` | str | required | Bare name; the on-disk clone directory. Must pass `contain.segment_ok` at merge or the row is dropped. | stable | `charter/commands.py:86`, `charter/inventory.py:239` |
| `repos[].path_with_namespace` | str | required | `<owner>/<name>`; the identity half of `(forge, path)`. | stable | `charter/commands.py:87` |
| `repos[].ssh_url` | str | required | SSH clone URL as the forge reports it; rewritten to HTTPS at clone time. | stable | `charter/commands.py:88` |
| `repos[].default_branch` | str | default `"main"` | Branch announced and cloned. | stable | `charter/commands.py:89` |
| `repos[].kind` | str | derived | `classify_kind(name)`: `workspace`/`docs`/`frontend`/`service`/`api`/`core`/`app`. | stable | `charter/commands.py:90`, `charter/inventory.py:21` |
| `repos[].stack` | str | derived; `"unknown"` | `classify_stack(root file list)`; `"unknown"` also means the probe failed (a warning, not a field). | stable | `charter/commands.py:91`, `charter/inventory.py:39` |
| `repos[].description` | str | `""` | Forge description, stripped. | stable | `charter/commands.py:92` |
| `repos[].topics` | array | `[]` | Forge topics. | stable | `charter/commands.py:93` |
| `repos[].web_url` | str | `""` | Forge HTML page, no `.git`. Used to build the HTTPS clone URL. | stable | `charter/commands.py:94` |
| `repos[].forge` | str | defaults to the querying forge's `kind` | Which forge the record came from; `gitlab` when absent (legacy). | stable | `charter/commands.py:97`, `charter/forge/registry.py:18` |
| `repos[].source` | str | only on the derived plane repo, value `"plane"` | Marks a record charter derived rather than discovered; stripped before save. | internal (never persisted) | `charter/inventory.py:164`, `charter/inventory.py:303` |

---

### `docs/topology.md`

- **Format:** Markdown, fully generated.
- **Status:** **stable** — committed, and written by one process to be read by people (and by
  anything regenerating it: a byte-different render is a spurious diff).
- **Written by:** `charter/commands.py:224` (`charter docs` / `charter docs generate`, and the
  tail of `charter discover` unless `--no-docs`), body from `charter/render.py:43`
  `topology_md`; `DOCS_DIR` is created first (`charter/commands.py:223`). Refuses to write at
  all when the inventory is empty (`charter/commands.py:219`).
- **Read by:** people; `charter status` points at it (`charter/commands.py:918`).
- **Git:** committed.
- **Encoding details:** `render.topology_md(doc) + "\n"` — the renderer already ends with an
  empty element, so the file ends with a blank line then newline. Fixed structure
  (`charter/render.py:45`–`charter/render.py:63`): the `BANNER` comment
  (`charter/render.py:7`), `# Repository Topology`, a count line
  `**N repos** in the `<group>` <label>.`, a blockquote, then a 5-column table
  (`| Repo | Kind | Stack | Branch | Description |`) with one row per repo **sorted by name**
  (`charter/render.py:44`). `<label>` is `"GitLab group"`/`"GitHub org"` only when every record
  agrees on one forge kind, else the neutral `"group"` (`charter/render.py:26`). Cells escape
  `|` and flatten newlines (`charter/render.py:17`). No timestamp anywhere.

---

### `README.md` — the generated persona roster block

- **Format:** Markdown block spliced into a hand-written file between two literal markers.
- **Status:** **stable** — committed, and the markers are a contract with a hand-written file.
- **Written by:** `charter/commands.py:331` `refresh_readme_personas`, called from
  `charter docs` (`charter/commands.py:229`); body from `charter/render.py:76` `personas_md`,
  splice by `charter/render.py:149` `splice_personas`. Plain `write_text`
  (`charter/commands.py:356`), only when the result differs.
- **Read by:** people. The markers are `<!-- BEGIN personas — GENERATED by `charter docs`; do
  not edit by hand. -->` (`charter/render.py:13`) and `<!-- END personas -->`
  (`charter/render.py:14`); **absent markers mean charter writes nothing**
  (`charter/render.py:154`), which is the case on charter's own plane today.
- **Git:** committed.
- **Encoding details:** rows sorted by `(-dispatches, name)` (`charter/render.py:99`), a
  12-cell unicode bar (`charter/render.py:68`), an optional mermaid pie when any dispatch is
  recorded, and a `⚑` legend only when a flag appears. The counts come from the dispatch
  tally and each persona's memory directory — the **personas area** owns those.

---

### `charter browser install` — three more plane-root paths

`charter browser` installs a vendor CLI into the plane, and a plane reader meets its
directories at the root. None is charter's own format; all three are named because an
enumerator that does not expect them has to guess.

- **`.claude/skills/playwright-cli/`** (`SKILL_DIR`, `charter/browser.py:79`) — the pages the
  vendor's generator writes, read by Claude Code as project skills. **stable** in the sense
  that matters here: a harness reads it. Written by the generator, not by charter.
- **`.playwright/`** (`CONFIG_DIR`, `charter/browser.py:96`) — created by `install` itself
  (`initWorkspace`), holding `.playwright/cli.config.json`. Project configuration. charter
  deliberately says nothing about whether a plane commits it (ADR 0017), and writes no
  `.gitignore` line for it.
- **`.playwright-cli/`** (`OUTPUT_DIR`, `charter/browser.py:90`) — the vendor's output
  directory: traces under `.playwright-cli/trace`, plus snapshots, screenshots and PDFs.
  Created when something is written there, never by `install`. charter **does** append
  `.playwright-cli/` to the plane's `.gitignore` (`ensure_output_ignored`,
  `charter/browser.py:151`, header at `charter/browser.py:173`) because a trace carries
  authenticated network traffic — the one of the three charter takes a position on.

### Plane-root files that exist but are **not** this area

Named so the assembled doc does not lose them: `vaults.json` (committed shared vault registry,
`charter/config.py:774` — vaults area), `.claude/settings.json` and `opencode.json` at the
plane root (written by `charter init`'s harness wiring — `charter/commands.py:2296`,
`charter/commands.py:2321`, `charter/commands.py:2098`, `charter/commands.py:1233` — harness
area), `workspaces/*` (workspaces area), `personas/*` internals (personas area),
`.charter/*` other than the profile launch record (runtime-state areas). The plane's own
`.claude/skills/**`, `.opencode/agent/**` and `.codex/skills/**` are committed plane content
that charter copies into a clone rather than authors; they are described where that mirror is
(`charter/harness/claude_code.py:53`).

---

## Workspaces

Everything Python charter reads or writes under `workspaces/`, plus the three places
outside it that decide or record a workspace's state: the plane's `.gitignore` managed
block, the guest checkouts' `.git/info/exclude` block, and the `.charter/` pointers.

All citations are against the clone at commit `50d31dc`.

Two rules hold for the whole area and are not repeated per file:

- **Name rule.** A workspace name is `instance.workspace_name_ok` — `contain.segment_ok`
  plus `^[A-Za-z0-9][A-Za-z0-9._-]*$` (`charter/instance.py:181`, `charter/instance.py:199`),
  asked through `workspace.valid_name` (`charter/workspace.py:211`). Every name read off
  disk is re-checked before it is joined onto a path.
- **Writer helpers.** `config.write_for` (`charter/config.py:504`) writes whole,
  `config.replace_for` (`charter/config.py:595`) writes atomically through a temp named
  `<target>.<pid>.<12 random hex>.tmp` (`charter/config.py:592`, `TEMP_SUFFIX = ".tmp"` at
  `charter/config.py:552`), `config.create_for` (`charter/config.py:517`) creates with
  `O_EXCL` only where nothing is at the name. Files under `.charter/` come out 0600/0700
  (`config.private_mkdir`, `charter/config.py:190`); files inside `workspaces/` keep the umask's mode, because `write_for` dispatches on where the
  path is (`charter/config.py:504`).

---

### `workspaces/`

- **Format:** directory.
- **Status:** stable — the operator's clones live here, and the plane's `.gitignore` names
  it literally.
- **Written by:** `charter init` (`charter/commands.py:1091` writes `/workspaces/*/*` and
  `!/workspaces/.gitkeep` into `.gitignore`); the directory itself by
  `workspace.ensure` → `wd.mkdir(parents=True)` (`charter/workspace.py:1313`).
- **Read by:** `workspace.read_workspaces` (`charter/workspace.py:914`),
  `workspace.legacy_flat_clones` (`charter/workspace.py:1290`), `gitpolicy.scan` via
  `charter/commands.py:3268`.
- **Git:** the directory is committed only through `workspaces/.gitkeep`; everything two
  levels down is ignored by `/workspaces/*/*` unless the LIVE block un-ignores it.
- **Encoding details:** a one-time migration renames a legacy `repos/` to `workspaces/`
  (`workspace._ensure_layout`, `charter/workspace.py:53`). An entry whose name starts with
  `.` is never a workspace (`charter/workspace.py:926`); an entry that is itself a clone
  (a `.git` directory) is not a workspace either (`charter/workspace.py:928`).
  `charter init` does **not** create `workspaces/default/` — the first command that puts
  something in it does; the name is always listable anyway (`charter/commands_workspace.py:116`).

### `workspaces/.default`

- **Format:** plain text — one workspace name, `\n`-terminated.
- **Status:** stable — committed (the default ignore rule `/workspaces/*/*` does not match
  a file directly under `workspaces/`, `charter/workspace.py:508`), hand-editable, and read
  by every process that resolves a workspace.
- **Written by:** `workspace.set_declared_default` (`charter/workspace.py:512`, through
  `contain.writable`), from `charter workspace default <name>`
  (`charter/commands_workspace.py:669`). Removed by `workspace.clear_declared_default`
  (`charter/workspace.py:524`) for `--clear`.
- **Read by:** `workspace.declared_default` (`charter/workspace.py:487`), which is a rung of
  `workspace.chosen` (`charter/workspace.py:646`) and of `workspace.source`
  (`charter/workspace.py:676`).
- **Git:** committed.
- **Encoding details:** exactly `name + "\n"` (`charter/workspace.py:512`). On read the
  value is `.strip()`ed and re-checked with `valid_name`; a `contain.file_refusal` (symlink,
  FIFO, oversized) makes it read as absent (`charter/workspace.py:488`).

### `workspaces/<ws>/`

- **Format:** directory.
- **Status:** stable — it *is* the workspace.
- **Written by:** `workspace.ensure` (`charter/workspace.py:1313`), which then calls
  `scaffold` best-effort (`charter/workspace.py:1315`). Reached from `workspace create`,
  `workspace use`, `charter clone` (`charter/commands.py:385`), `restore`, `fork`, and every
  frame launch.
- **Read by:** everything in this area.
- **Git:** the directory entry is ignored by `/workspaces/*/*`.
- **Encoding details:** `scaffold` refuses the whole directory when it does not resolve
  inside `workspaces/` (`charter/workspace.py:1840`). Baseline creation order is
  memory → refs → workspace.md → workspace.json → harness layer → structure stamp
  (`charter/workspace.py:1851`–`1885`), each path skipped when `_baseline_answers` says it
  cannot be checked or something is in the way (`charter/workspace.py:1849`).

### `workspaces/<ws>/workspace.md` — the living charter

- **Format:** Markdown; charter parses and rewrites `## ` sections, no frontmatter.
- **Status:** stable — hand-edited, committed for a LIVE workspace, read by the SessionStart
  digest, the status line/tab strip (vision cell) and `handoff`.
- **Written by:** `workspace.scaffold_charter` (`charter/workspace.py:4360`, template at
  `charter/workspace.py:4295`) and `workspace.set_vision` (`charter/workspace.py:4370`);
  commands `workspace create --vision`, `workspace vision "…"`
  (`charter/commands_workspace.py:1613`). Copied wholesale by `fork`
  (`charter/commands_workspace.py:1689`).
- **Read by:** `workspace.read_charter` (`charter/workspace.py:4373`), `read_vision`
  (`charter/workspace.py:4441`), `_vision_cell` (`charter/commands_workspace.py:64`),
  `last_active` (`charter/workspace.py:4421`).
- **Git:** gitignored unless LIVE (`!/workspaces/<ws>/workspace.md`,
  `charter/workspace.py:1397`).
- **Encoding details:**
  - Created only when absent, with `config.create_for` (`charter/workspace.py:4360`); a
    file that exists is never overwritten, only its `## Vision` body replaced.
  - Template: `# <name>`, a 4-line block quote, then `## Vision`, `## Context & decisions`,
    `## Glossary`, `## Log` (`charter/workspace.py:4295`–`4323`). The unset vision body is
    the placeholder at `charter/workspace.py:4290` (`_Not set yet — …`).
  - Section replacement: `_replace_md_section` (`charter/workspace.py:4326`) keeps the
    `## <header>` line, replaces everything to the next line starting `"## "` or EOF with
    `"", body.strip(), ""`, rstrips the file and adds one trailing `\n`; a missing section is
    appended as `\n## <header>\n\n<body>\n`. The header match is
    `^##\s+Vision\s*$`, case-insensitive (`charter/workspace.py:4332`).
  - Vision extraction: `^##\s+Vision\s*$(.*?)(?=^##\s|\Z)` with `MULTILINE|DOTALL`, body
    stripped, and a body starting `_Not set yet` reads as unset
    (`charter/workspace.py:4441`–`4444`).
  - Reads are refused (`""`) when the *directory* or the file fails containment
    (`charter/workspace.py:4391`).

### `workspaces/<ws>/workspace.json` — the committed manifest

- **Format:** JSON object, `json.dumps(doc, indent=2) + "\n"` (`charter/workspace.py:1612`).
- **Status:** stable — committed for LIVE workspaces, restored on other machines, and
  hand-editable (`manifest_owner` exists precisely to tell charter's copy from a hand's).
- **Written by:** `workspace._write_manifest` (`charter/workspace.py:1589`) via
  `write_manifest` (`charter/workspace.py:1577`, the deliberate writer: `snapshot`, `fork`,
  `rename`), `scaffold_manifest` (`charter/workspace.py:1652`, birth) and `record_members`
  (`charter/workspace.py:1684`, a clone landing — `charter/commands.py:477`).
  Commands: `workspace create`/`use`/`clone` (through `ensure`),
  `workspace snapshot` (`charter/commands_workspace.py:942`),
  `workspace fork` (`charter/commands_workspace.py:1719`),
  `workspace rename` (`charter/workspace.py:1488`),
  `workspace reinit` (backfill, `charter/workspace.py:4645`).
- **Read by:** `workspace.read_manifest` (`charter/workspace.py:1500`), `manifest_owner`
  (`charter/workspace.py:1556`), `restore` (`charter/commands_workspace.py:955`), `fork`
  (`charter/commands_workspace.py:1709`), `merge_repo_rows` (`charter/workspace.py:1739`),
  `last_active` (`charter/workspace.py:4421`).
- **Git:** gitignored unless LIVE (`!/workspaces/<ws>/workspace.json`,
  `charter/workspace.py:1397`); it is the first path of the managed block.
- **Encoding details:**
  - Atomic: `config.replace_for` through a pid+random temp beside the file
    (`charter/workspace.py:1612`), path first run through `contain.writable`
    (`charter/workspace.py:1609`), which **raises** on a symlink out of the plane.
  - Key order is insertion order of the dict the writer built, with `charter_generated`
    appended last (`charter/workspace.py:1611`). The birth document's order is
    `name, description, repos, updated_at, updated_by` (`charter/workspace.py:1677`);
    `snapshot` and `fork` mutate a read document, so a manifest that already existed keeps
    the order it had on disk, and `fork` inserts `forked_from` after `name`
    (`charter/commands_workspace.py:1713`–`1718`).
  - `repos` rows are sorted by name whenever charter adds one
    (`charter/workspace.py:1729`); `snapshot` writes them in `clones()` order, which is
    already sorted (`charter/workspace.py:1248`).

| Field | Type | Required / default | Meaning | Status | Source |
|---|---|---|---|---|---|
| `name` | string | required; the workspace's own name | identity; rewritten by `rename` | stable | `charter/workspace.py:1677`, `charter/workspace.py:1487` |
| `description` | string | `""` | free text, set by `snapshot --description` | stable | `charter/commands_workspace.py:937` |
| `repos` | list of objects | `[]` | membership, and optionally pinned branches | stable | `charter/workspace.py:1677` |
| `repos[].name` | string | required | clone directory name under the workspace; untrusted, gated by `contain.child` on restore | stable | `charter/workspace.py:1649`, `charter/commands_workspace.py:985` |
| `repos[].branch` | string | **absent** for every row charter writes itself; set by `snapshot` | the branch `restore` checks out; a row without one restores at the default branch | stable | `charter/commands_workspace.py:939`, `charter/commands_workspace.py:1014` |
| `updated_at` | string | required | UTC ISO-8601, `timespec="seconds"`, e.g. `2026-09-17T14:01:35+00:00` | stable | `charter/workspace.py:1616`, `charter/commands_workspace.py:940` |
| `updated_by` | string | required | `$USER` or `"unknown"` for automatic writes (`charter/workspace.py:1633`); `git config user.name` for `snapshot`/`fork` (`charter/commands_workspace.py:860`) | stable | `charter/workspace.py:1679` |
| `forked_from` | string | present only on a fork | the source workspace | stable | `charter/commands_workspace.py:1714` |
| `charter_generated` | string | written on every charter write | sha256 of the rest of the document, canonically serialised | stable | `charter/workspace.py:1529`, `charter/workspace.py:1611` |

**`charter_generated` computation** (a Rust writer must match it byte for byte):
`sha256(json.dumps({k: v for k, v in doc.items() if k != "charter_generated"}, sort_keys=True).encode("utf-8")).hexdigest()`
— body at `charter/workspace.py:1540`, digest at `charter/workspace.py:1945`. Note
`sort_keys=True` and Python's default separators (`", "`, `": "`) for the *digest* input,
while the file on disk is `indent=2` in insertion order. Ownership: a document whose
`charter_generated` matches is `"charter"`; anything else present is `"operator"` and the
automatic writers leave it byte for byte alone; absent is `"absent"`
(`charter/workspace.py:1556`–`1574`). A present-but-unparseable file is `"operator"`.

### `workspaces/<ws>/memory/` — the task journal

- **Format:** directory of Markdown files plus a `MEMORY.md` index.
- **Status:** stable — committed for LIVE workspaces, hand-editable, read by the SessionStart
  briefing, `charter recall`, `doctor` and `curate`.
- **Written by:** `workspace.scaffold_memory` (`charter/workspace.py:1817`) →
  `memstore.ensure_index` (`charter/memstore.py:86`); `workspace.remember`
  (`charter/workspace.py:4231`) → `memstore.write` (`charter/memstore.py:101`);
  `workspace.forget_memory` (`charter/workspace.py:4257`) → `memstore.forget`
  (`charter/memstore.py:452`); `curate.apply_safe` via `workspace optimize`
  (`charter/commands_workspace.py:724`); `memstore.archive` (`charter/memstore.py:503`).
  Commands: `workspace remember|note`, `workspace forget`, `ws todo done` (writes a closing
  memory, `charter/commands_workspace.py:1516`), `workspace optimize --apply`, `fork` (copy).
- **Read by:** `memstore.files`/`entries`/`search` (`charter/memstore.py:169`, `289`, `367`),
  `workspace.recall` (`charter/workspace.py:4244`), `recall.py`, `doctor` (index drift),
  `last_active` (`charter/workspace.py:4424`).
- **Git:** gitignored unless LIVE; the block un-ignores both `memory` and `memory/**`
  (`charter/workspace.py:1398`) — two lines, because un-ignoring the directory alone does
  not re-include its files.

#### `workspaces/<ws>/memory/MEMORY.md`

- **Encoding details:** created once, `config.create_for`, with the header at
  `charter/workspace.py:1802` formatted with the workspace name, and a trailing `\n`
  guaranteed (`charter/memstore.py:97`). Entries are **appended** as
  `- [{title}]({filename})\n` (`charter/memstore.py:144`), in `"a"` mode — no rewrite, so
  the order is the order memories were written. A deletion filters the lines containing
  `({filename})` and rewrites the file joined with `\n` plus one trailing `\n`
  (`charter/memstore.py:489`). Index links are recognised by
  `\(([A-Za-z0-9][\w.-]*\.md)\)` (`charter/memstore.py:214`).
  A legacy `notes.md` is grandfathered into the index once, as
  `- [Task memo (legacy)](notes.md)` (`charter/workspace.py:1824`).

#### `workspaces/<ws>/memory/<YYYYMMDD-HHMMSS>-<slug>.md`

- **Encoding details:**
  - Filename: `now.strftime("%Y%m%d-%H%M%S-")` + `slug(title)` + `.md`
    (`charter/memstore.py:119`–`121`). **The stamp is LOCAL time** — `datetime.datetime.now()`
    with no timezone (`charter/memstore.py:65`).
  - Slug: lowercase, every run of `[^a-z0-9]+` → `-`, stripped of leading/trailing `-`,
    truncated to 48 chars, `"note"` when empty (`charter/memstore.py:23`, `26`–`28`).
  - Collision: `-2`, `-3`, … appended before `.md` while the path exists
    (`charter/memstore.py:122`–`124`).
  - Title: the first non-blank line of the body, stripped, capped at `TITLE_MAX = 72`
    (`charter/memstore.py:33`, `charter/memstore.py:36`), or an explicit `--title`.
  - Body: `"# {title}\n\n_{now:%Y-%m-%d %H:%M} · {kind}_\n\n{text}\n"`
    (`charter/memstore.py:132`); `kind` is `"persistent"` for workspace memories (the
    default, `charter/memstore.py:102`). The text is `.strip()`ed; empty raises.
  - Closed todos: `ws todo done <slug>` writes a memory whose text is
    `f"Closed todo: {title}"` before deleting the todo
    (`charter/commands_workspace.py:1516`–`1517`), so its filename is
    `<stamp>-closed-todo-<slug-of-the-title>.md`.
  - `memory/archive/<name>.md` holds retired memories, moved by `memstore.archive`
    (`charter/memstore.py:510`, `charter/memstore.py:524`); it is out of every listing
    because listings take only `*.md` directly in the directory
    (`charter/memstore.py:208`).
  - `memory/notes.md` is the pre-v2 single-log memo, still read by
    `workspace.read_notes` (`charter/workspace.py:4271`) and never written any more.

### `workspaces/<ws>/todos/`

- **Format:** the same per-file memory store, with its own header. One file per todo plus
  `MEMORY.md`.
- **Status:** stable — committed for LIVE workspaces, listed by `ws todo`, counted by the
  status line and by `workspace remove`'s warning, and inherited by `fork`.
- **Written by:** `todos.scaffold` (`charter/todos.py:73`), `todos.add`
  (`charter/todos.py:93`); commands `charter ws todo "<text>"`
  (`charter/commands_workspace.py:1462`), `ws todo done|forget <slug>` (deletes —
  `charter/commands_workspace.py:1519`), `fork` (directory copy,
  `charter/commands_workspace.py:1702`).
- **Read by:** `todos.open_todos` (`charter/todos.py:219`), `todos.count_open`
  (`charter/todos.py:236`), `todos.search` (`charter/todos.py:232`),
  `todos.duplicate_of` (`charter/todos.py:133`), `last_active`
  (`charter/workspace.py:4424`).
- **Git:** gitignored unless LIVE — `todos` and `todos/**`
  (`charter/workspace.py:1399`), matched by `_ws_meta_paths`
  (`charter/commands_workspace.py:1118`).
- **Encoding details:** exactly the memory-file rules above (`todos.add` calls
  `memstore.write(..., timestamped=True, index=True)`), so a todo file is
  `<YYYYMMDD-HHMMSS>-<slug>.md` holding `# <title>`, `_<YYYY-MM-DD HH:MM> · persistent_`,
  the body. The index header is at `charter/todos.py:31`. **There is no state field**:
  closing deletes the file and its index line (ADR 0004/0006,
  `charter/commands_workspace.py:1469`). The slug a caller closes by is the file stem, and
  it must be one path segment (`charter/commands_workspace.py:1498`). Ordering is the
  filename's second resolution (whole seconds, ties broken alphabetically,
  `charter/todos.py:93`, `charter/memstore.py:119`). Age comes from the in-body `_YYYY-MM-DD` stamp, falling back
  to the filename prefix (`charter/memstore.py:150`).

### `workspaces/<ws>/refs/README.md` (and whatever else the operator drops in `refs/`)

- **Format:** Markdown; the rest of the directory is arbitrary operator content.
- **Status:** stable — it is a baseline component `structure_status` reports and `reinit`
  repairs, and the operator writes into the directory.
- **Written by:** `workspace.scaffold` (`charter/workspace.py:1855`–`1864`), only when
  `_exists(rr, follow=True) is False`, through `config.create_for`.
- **Read by:** `_required_components` (`charter/workspace.py:4511`), `last_active`
  (`charter/workspace.py:4424`), `recall`'s ref search (`charter/recall.py:130` is the
  persona twin).
- **Git:** gitignored always — `refs/` is **not** in the LIVE block
  (`charter/workspace.py:1397`–`1401`).
- **Encoding details:** body is
  `f"# {name} — task references\n\nDrop docs, links, and snippets for this task here (local, gitignored).\n"`
  (`charter/workspace.py:1864`).

### `workspaces/<ws>/changes/<slug>.json` — a cross-repo change

- **Format:** JSON object; `json.dumps(ordered, indent=2) + "\n"` (`charter/change.py:781`).
- **Status:** stable — committed for LIVE workspaces, hand-editable, an untrusted input
  validated on read and write.
- **Written by:** `change.write` (`charter/change.py:420`, through `contain.writable` +
  `config.write_for`); commands `charter change create|add|drop|…`
  (`charter/commands_change.py:175`). Removed by `change.forget`
  (`charter/change.py:435`).
- **Read by:** `change.read` (`charter/change.py:393`), `change.all_for`/`read_all`
  (`charter/change.py:446`, `465`), `change.has_records` (`charter/change.py:368`),
  the frame's gather, `charter change show|list|land`.
- **Git:** gitignored unless LIVE — `changes` and `changes/**` are un-ignored and
  `changes/log/` is re-ignored inside the block (`charter/workspace.py:1400`–`1401`).
  The directory is created lazily by the first `change create`, never by `scaffold`
  (`charter/change.py:335`).
- **Encoding details:** the serialiser is canonical — top-level keys in `KEYS` order,
  each member's keys in `MEMBER_KEYS` order, each exclusion's in `EXCLUSION_KEYS` order
  (`charter/change.py:778`–`781`), so a record read and written back is byte-identical.
  The slug must satisfy `instance.change_name_ok` — `^[A-Za-z0-9][A-Za-z0-9._-]*$`
  (`charter/instance.py:211`, `charter/change.py:352`) — and must equal `rec["change"]`
  (`charter/change.py:520`). The key set is **closed at both ends**: an unknown or a missing
  key is a `RecordError` (`charter/change.py:569`–`585`). Every string field must be one
  plain line within `contain.PATH_DISPLAY_LIMIT` (`charter/change.py:97`,
  `charter/change.py:599`–`605`). There is no state field of any kind.

| Field | Type | Required / default | Meaning | Status | Source |
|---|---|---|---|---|---|
| `change` | string | required, `== slug` | the change's name | stable | `charter/change.py:83` |
| `why` | string | required, one line | what the work is for | stable | `charter/change.py:526` |
| `created` | string | required | UTC ISO-8601 seconds, from `commands_change._now` | stable | `charter/commands_change.py:108`, `charter/commands_change.py:227` |
| `by` | string | required | `git config user.name`, else `$USER`, else `"unknown"` | stable | `charter/commands_change.py:111` |
| `members` | list | required, `[]` | one row per participating repo | stable | `charter/change.py:759` |
| `members[].repo` | string | required | repo name, `contain.segment_ok` (not `valid_name`: `.github` is legal) | stable | `charter/change.py:609` |
| `members[].branch` | string | required; default `change/<slug>` | this change's branch in that repo; may not start `-` | stable | `charter/change.py:762`, `charter/change.py:626` |
| `members[].needs` | list of strings | required, `[]` | repos that must land first; must name members; no self-loops, no cycles | stable | `charter/change.py:88`, `charter/change.py:652` |
| `excluded` | list | required, `[]` | repos considered and left out | stable | `charter/change.py:102` |
| `excluded[].repo` | string | required | repo name | stable | `charter/change.py:557` |
| `excluded[].why` | string | required, one line | why it is out | stable | `charter/change.py:561` |
| `excluded[].at` | string | required | UTC ISO-8601 seconds when it was dropped | stable | `charter/commands_change.py:321` |

### `workspaces/<ws>/changes/log/<host>.jsonl` — the landing log

- **Format:** JSON Lines, one object per line, `O_APPEND`, no lock.
- **Status:** stable — it is read by a *different* process from the one that wrote it (the
  frame's pane, `change show`, the land gate), and by other hosts' charter on the same disk;
  never committed.
- **Written by:** `commands_change._append_landing` (`charter/commands_change.py:1092`), from
  `charter change land` (`charter/commands_change.py:1501`), after the merge is read back.
  `change.record_landing` (`charter/change.py:156`) is a second writer with the same shape
  — see the Appendix.
- **Read by:** `change.read_landings` (`charter/change.py:217`), `change.landings`
  (`charter/change.py:189`), `commands_change.landings` (`charter/commands_change.py:1109`),
  `change.declared_landings` (`charter/change.py:244`).
- **Git:** committed **never** — `/workspaces/<ws>/changes/log/` re-ignored inside the LIVE
  block (`charter/workspace.py:1401`), and `_ws_meta_paths` stages `changes/` only when
  `change.has_records` is true (`charter/commands_workspace.py:1119`).
- **Encoding details:** filename is the short hostname, `socket.gethostname().split(".")[0]`
  with every character outside `[A-Za-z0-9_-]` removed, truncated to 32, `"unknown"` when
  empty (`charter/change.py:142`, `charter/pieces.py:71`). The line is
  `contain.json_line(line, sort_keys=True) + "\n"` — **keys sorted, `ensure_ascii=True`**
  (`charter/commands_change.py:1099`, `charter/contain.py:473`), written with
  `os.open(..., O_WRONLY|O_CREAT|O_APPEND, 0o644)` (`charter/commands_change.py:1100`).
  A reader skips any line that is not an object whose key set is exactly `LOG_FIELDS`
  (`charter/change.py:234`), and sorts by `ts` (`charter/change.py:241`).

| Field | Type | Required / default | Meaning | Status | Source |
|---|---|---|---|---|---|
| `ts` | string | required | UTC ISO-8601 seconds | stable | `charter/commands_change.py:1092` |
| `change` | string | required | the change's slug | stable | `charter/change.py:113` |
| `repo` | string | required | the member that landed | stable | `charter/change.py:113` |
| `number` | int | required | the request number charter merged | stable | `charter/commands_change.py:1093` |
| `merge` | string | required | sha of the merge commit charter created | stable | `charter/change.py:113` |
| `head` | string | required | the member branch tip it was created from | stable | `charter/change.py:113` |

### `workspaces/<ws>/pieces/<host>.jsonl` — the piece claim log

- **Format:** JSON Lines, `O_APPEND`, no lock.
- **Status:** stable — written by `charter wt add`/`wt done` and read by the status line,
  `wt list` and the frame; never committed, but read by processes other than the writer.
- **Written by:** `pieces.record` (`charter/pieces.py:122`), from
  `charter/commands_worktree.py:167` (`claimed`) and `charter/commands_worktree.py:233`
  (`done`/`abandoned`).
- **Read by:** `pieces.events` (`charter/pieces.py:148`), `claims`
  (`charter/pieces.py:167`), `declarations` (`charter/pieces.py:185`), `silence`
  (`charter/pieces.py:368`).
- **Git:** never committed — `pieces` is deliberately absent from the LIVE block
  (`charter/pieces.py:49`), so `/workspaces/*/*` keeps it ignored.
- **Encoding details:** filename `<host>.jsonl`, same host rule as above
  (`charter/pieces.py:85`, `charter/pieces.py:71`). Line is
  `json.dumps(line, sort_keys=True) + "\n"` (`charter/pieces.py:120`), `0o644`,
  `O_APPEND` (`charter/pieces.py:122`). A malformed line is skipped
  (`charter/pieces.py:159`); events are sorted by `ts` (`charter/pieces.py:164`).
  Key set is closed by test (`FIELDS`, `charter/pieces.py:55`); the vocabulary is
  `claimed|done|abandoned` and nothing else (`charter/pieces.py:64`), enforced by a
  `ValueError` on write (`charter/pieces.py:101`).

| Field | Type | Required / default | Meaning | Status | Source |
|---|---|---|---|---|---|
| `ts` | string | required | UTC ISO-8601 seconds | stable | `charter/pieces.py:105` |
| `event` | string | required | `claimed` / `done` / `abandoned` | stable | `charter/pieces.py:64` |
| `repo` | string | required | clone the worktree belongs to | stable | `charter/pieces.py:107` |
| `piece` | string | required | the worktree/piece name | stable | `charter/pieces.py:108` |
| `session` | string or null | required key | `session.current()` at write time | stable | `charter/pieces.py:109` |
| `host` | string | required | short hostname | stable | `charter/pieces.py:110` |
| `persona` | string or null | required key | `persona.resolve_active()` | stable | `charter/pieces.py:111` |
| `reason` | string | present only when given | a `done`/`abandoned` reason | stable | `charter/pieces.py:113` |

### `workspaces/<ws>/pieces/seen/<repo>.json` and `pieces/seen/<repo>/<piece>.json`

- **Format:** one small JSON object, **overwritten** each turn.
- **Status:** stable — written by a hook process and read by the status line and `wt list`,
  which are different processes.
- **Written by:** `pieces.seen` (`charter/pieces.py:276`), from `hooks._touch_piece`
  (`charter/hooks.py:6264`), which every turn-level handler calls
  (`charter/hooks.py:6352`, `6488`, `7609`, `7775`, `8040`, `8703`).
- **Read by:** `pieces.last_seen` (`charter/pieces.py:330`), `presence`
  (`charter/pieces.py:293`), `seen_age` (`charter/pieces.py:363`), `silence`
  (`charter/pieces.py:384`).
- **Git:** never committed (under `pieces/`).
- **Encoding details:** `json.dumps(blob, sort_keys=True) + "\n"` via `Path.write_text`
  (`charter/pieces.py:276`). A clone's own record is `seen/<repo>.json`; a piece's is
  `seen/<repo>/<piece>.json` (`charter/pieces.py:236`). Keys: `ts` (UTC ISO seconds),
  `session`, and — only when a persona was resolved — `persona` and `by`
  (`charter/pieces.py:268`–`271`). `by` is `{persona: ts}`, pruned to the last hour
  (`PRESENCE_WINDOW`, `charter/pieces.py:220`) and capped at 8 entries
  (`PRESENCE_KEEP`, `charter/pieces.py:225`).

### `workspaces/<ws>/.charter-structure` — the layout stamp

- **Format:** plain text: the integer version and `\n`.
- **Status:** **stable** — the status line reads it in a different process from the one
  that wrote it. Deleting it makes the workspace read as version 0, so the status line
  flags `⚠ reinit` and
  `charter workspace reinit` re-stamps it. Nothing else is lost.
- **Written by:** `workspace.scaffold` (`charter/workspace.py:1885`), through a raw
  `os.open(..., O_WRONLY|O_CREAT|O_TRUNC|O_NOFOLLOW|O_NONBLOCK, 0o666)`
  (`charter/workspace.py:1880`) — never through a symlink, never into a FIFO.
- **Read by:** `workspace._stamp` (`charter/workspace.py:4539`, `O_RDONLY|O_NOFOLLOW|
  O_NONBLOCK`, `int(os.read(fd, 4096).strip())`), `structure_version`
  (`charter/workspace.py:4515`), `structure_status` (`charter/workspace.py:4584`),
  `needs_reinit` (`charter/workspace.py:4618`).
- **Git:** gitignored (`/workspaces/*/*`; not in the LIVE block).
- **Encoding details:** `STRUCTURE_VERSION = 5` today (`charter/workspace.py:4473`) — v2
  memory-as-DB, v3 `changes/` in the LIVE block, v4 the harness layer, v5 every workspace
  has a `workspace.json`. A pre-rename `.edm-structure` is renamed in place on first read
  (`charter/workspace.py:4477`–`4500`). "Current" is `version >= STRUCTURE_VERSION` **and**
  no baseline file missing (`charter/workspace.py:4585`).

### `workspaces/<ws>/.charter-generated` — the harness-layer ownership marker

- **Format:** JSON object, `json.dumps(marker, indent=2) + "\n"`
  (`charter/workspace.py:2946`); `{relative path: sha256 hex}` or, while a write is pending,
  `{relative path: [sha256, …]}`.
- **Status:** stable — the same marker shape is written into guest checkouts, where another
  process (a later launch, `doctor`, `reinit`) reads it to decide what is charter's to
  rewrite, withdraw or hide. Delete it and charter loses its claim: every generated file
  reads as `foreign` and is never rewritten again, which is the failure mode this file
  exists to avoid, so it is not "safe to delete".
- **Written by:** `workspace._publish_marker` (`charter/workspace.py:2943`) from
  `_materialise` (`charter/workspace.py:2807`, `charter/workspace.py:2837`); removed
  entirely when it would name nothing (`charter/workspace.py:2950`) and by `unwire_guest`
  (`charter/workspace.py:4198`).
- **Read by:** `_read_marker_at` (`charter/workspace.py:2212`), `_layer_status`
  (`charter/workspace.py:2568`), `_charter_owned` (`charter/workspace.py:3336`),
  `_unwanted` (`charter/workspace.py:2611`), `_yours_untracked`
  (`charter/workspace.py:3777`).
- **Git:** gitignored in a workspace directory by `/workspaces/*/*`; in a guest checkout it
  is listed in charter's `.git/info/exclude` block (`charter/workspace.py:3372`). A marker
  git **tracks** is dropped as untrusted (`charter/workspace.py:2176`, `2239`).
- **Encoding details:** written whole through `_write_whole` — temp
  `.charter-generated.<pid>.<12 hex>.tmp` beside the target, `fsync`, mode of the replaced
  file preserved, one `os.replace` (`charter/workspace.py:2913`–`2924`). Keys must be
  relative in-checkout paths: an absolute, drive-qualified, NUL-bearing or `..`-bearing key
  invalidates the whole marker (`charter/workspace.py:2155`–`2173`, `2237`). A value may be
  a string (settled) or a list of strings (pending, published *before* the write)
  (`charter/workspace.py:2440`–`2456`, `2806`). Key order is dict order: the intent dict is
  built from the marker read plus the writes, so it is effectively the order paths first
  appeared. The digest is `content_digest` — sha256 of the UTF-8 text charter wrote
  (`charter/workspace.py:1945`).

### `workspaces/<ws>/.claude/settings.json` — the generated harness layer

- **Format:** JSON, `json.dumps(doc, indent=2) + "\n"`
  (`charter/harness/claude_code.py:485`).
- **Status:** stable — Claude Code reads it for any chat rooted in the workspace directory.
- **Written by:** `workspace.wire_harnesses` → `_materialise` → `_write_whole`
  (`charter/workspace.py:2677`, `charter/workspace.py:2824`), content from
  `ClaudeCodeHarness.workspace_files` (`charter/harness/claude_code.py:447`). Reached from
  `workspace.scaffold` on every `ensure` (`charter/workspace.py:1870`) and from
  `workspace reinit` (`charter/workspace.py:4644`).
- **Read by:** Claude Code itself; charter reads it back only to compare against what it
  wants (`_layer_status`, `charter/workspace.py:2562`) and to answer
  `rules_not_in_force` (`charter/workspace.py:3984`).
- **Git:** gitignored — `/workspaces/*/*` covers it and the LIVE block never un-ignores
  `.claude/` (`charter/workspace.py:1397`–`1401`).
- **Encoding details:** a 1:1 mirror of the plane's own `.claude/settings.json`, limited to
  `WORKSPACE_KEYS = ("enabledPlugins", "env")` (`charter/harness/claude_code.py:53`) plus a
  `permissions` object holding only the **restrictive** buckets (`ask`, `deny`), appended
  last (`charter/harness/claude_code.py:484`). Empty plane settings → no file and no marker
  entry at all. opencode and Codex contribute nothing here and declare the
  `WORKSPACE_SCOPE` deficit instead (`charter/harness/opencode.py:751`,
  `charter/harness/codex.py:182`), reported by `workspace.harness_deficits`
  (`charter/workspace.py:1971`).

### `workspaces/<ws>/<repo>/` — a cloned repo (guest checkout)

- **Format:** an ordinary git clone. Charter recognises it by `<dir>/.git` being a
  **directory** (`workspace.is_clone`, `charter/workspace.py:300`, via `_directory`
  `charter/workspace.py:2287`); a linked worktree's `.git` is a file and is excluded there
  on purpose. `guest_trees` is the wider question — anything with a resolvable git dir
  (`charter/workspace.py:3126`, `_children` at `charter/workspace.py:3139`).
- **Status:** stable — the operator's own repository. Charter is a guest and writes only
  the paths below.
- **Written by (charter's own files only):** `workspace.wire_guest`
  (`charter/workspace.py:4059`) from `wire_harnesses` (`charter/workspace.py:2680`),
  `charter clone` (`charter/commands.py:500`) and `charter wt add`
  (`charter/commands_worktree.py:194`). Removed by `unwire_guest`
  (`charter/workspace.py:4148`) and `unwire_guests` on `workspace remove`
  (`charter/workspace.py:4211`, `charter/commands_workspace.py:374`).
- **Git:** everything charter writes there is listed one path at a time in that checkout's
  `.git/info/exclude`; charter never touches the checkout's `.gitignore` and never stages
  anything in it (`charter/workspace.py:1916`–`1920`).
- **Files charter generates inside a clone** (`_guest_files`, `charter/workspace.py:2135`):
  - `.claude/settings.json` — the same mirror as the workspace directory's.
  - `.claude/settings.local.json` — the plane's **local** ask/deny rules, checkout only
    (`charter/harness/claude_code.py:487`, `CHECKOUT_LOCAL_SETTINGS` at
    `charter/harness/claude_code.py:95`). It is *co-written*: the harness saves "don't ask
    again" into it, so charter never rewrites it once edited and never withdraws its
    exclude line (`charter/harness/claude_code.py:387`, `charter/workspace.py:3353`).
  - a 1:1 copy of the plane's `.claude/agents/**`, `.claude/skills/**`,
    `.opencode/agent/**`, `.codex/skills/**` — every registered harness's
    `inherited_paths` (`charter/workspace.py:2105`, `charter/harness/claude_code.py:169`,
    `charter/harness/opencode.py:831`, `charter/harness/codex.py:236`). Keys are
    `<declared path>/<relative posix path>` (`charter/workspace.py:2131`).
  - `.charter-generated` — the marker, as above.
- **Encoding details:** a tree whose root does not resolve inside `workspaces/` (or, for a
  piece, inside the worktree root) is never written to — `_wired_tree_ok`
  (`charter/workspace.py:3302`). Every individual write is refused if the path or its
  parent resolves out of the tree (`_inside`, `charter/workspace.py:2848`;
  `_write_whole`, `charter/workspace.py:2906`). Withdrawals only ever reach a path under a
  harness root (`_generated_roots`, `charter/workspace.py:2587`) whose content still matches
  the recorded digest (`charter/workspace.py:2642`), and empty parent directories are pruned
  (`_prune_empty`, `charter/workspace.py:4123`).

### `<clone>/.git/info/exclude` — charter's managed block

- **Format:** plain text; a delimited block inside a file the operator also owns.
- **Status:** stable — git reads it, and charter reads it back on every launch and repair.
- **Written by:** `workspace._register_excludes` (`charter/workspace.py:3876`) through
  `_write_whole` (`charter/workspace.py:3908`), from `wire_guest`
  (`charter/workspace.py:4102`, `charter/workspace.py:4112`) and `unwire_guest`
  (`charter/workspace.py:4207`).
- **Read by:** `_exclude_state` (`charter/workspace.py:3791`), `unaccounted`
  (`charter/workspace.py:3830`), `unhidden` (`charter/workspace.py:3840`), `guest_layer`
  (`charter/workspace.py:3959`) — and git.
- **Git:** never committed, never tracked; it lives in the **common** git directory, so a
  linked worktree and its clone share one (`git_exclude_file`, `charter/workspace.py:269`,
  resolving `commondir` at `charter/workspace.py:287`).
- **Encoding details:**
  - Markers: `# >>> charter (generated layer — \`charter workspace reinit\`) >>>` and
    `# <<< charter <<<` (`charter/workspace.py:3114`–`3115`), with a fixed three-line note
    between the begin marker and the paths (`charter/workspace.py:3118`).
  - Each listed path is written as `/<rel>` (anchored), except the temp pattern
    `.charter-generated.*.tmp`, written unanchored (`charter/workspace.py:3390`,
    `charter/workspace.py:3381`). Block ends with one `\n` (`charter/workspace.py:3391`).
  - Order: sorted rels, then `.charter-generated`, then the temp pattern
    (`charter/workspace.py:3756`–`3760`).
  - Replacement is in place between the markers; an unterminated block runs to EOF and is
    replaced whole (`_replace_block`, `charter/workspace.py:3404`; `_block_span`,
    `charter/workspace.py:3431`). A file with no block and nothing to add is handed back
    byte for byte (`charter/workspace.py:3419`).
  - The block holds what **every** tree sharing this exclude needs (`_shared_rels`,
    `charter/workspace.py:3656`); a line is only dropped when its path is proved absent in
    all of them, and a line is never *added* over an untracked file of the operator's in a
    sibling tree (`charter/workspace.py:3718`–`3734`).

### `workspaces/<ws>/.worktrees/<repo>/<piece>/` — pieces

- **Format:** git linked worktrees.
- **Status:** stable — the layout is a contract: `worktree.locate` and `workspace.from_path`
  derive the active workspace from a path of exactly this shape.
- **Written by:** `git worktree add` under `charter wt add`; the path comes from
  `worktree.path_for` (`charter/worktree.py:77`) and `worktree.root`
  (`charter/worktree.py:34`).
- **Read by:** `worktree.locate` (`charter/worktree.py:37`), `dirs_for`
  (`charter/worktree.py:238`), `list_for` (`charter/worktree.py:128`),
  `workspace._pieces` (`charter/workspace.py:3180`), `_piece_at`
  (`charter/workspace.py:3247`).
- **Git:** `DIR_NAME = ".worktrees"` (`charter/worktree.py:28`) starts with a dot, so it is
  never taken for a repo (`charter/workspace.py:450`) and is gitignored by
  `/workspaces/*/*`.
- **Encoding details:** the in-plane layout is `workspaces/<ws>/.worktrees/<repo>/<piece>`;
  with a relocated root it is `<root>/<ws>/<repo>/<piece>` and `.worktrees` disappears from
  the path (`charter/worktree.py:31`–`34`, `charter/worktree.py:53`–`58`). The root is
  `$CHARTER_WORKTREES` → `[plane] worktrees` → `None` (in-plane)
  (`charter/config.py:82`–`88`); a *committed* `[plane] worktrees` must be plane-adjacent
  (`contain.plane_adjacent`, `charter/config.py:88`), the env var takes anything. **Git is
  the only registry** — nothing records a worktree in workspace state
  (`charter/worktree.py:3`); charter's own listing spawns
  `git worktree list --porcelain` with the repository-local git env unset and a 5 s timeout
  (`charter/workspace.py:3623`, `_GIT_TIMEOUT` at `charter/workspace.py:3451`,
  `_GIT_ENV` at `charter/workspace.py:3464`). Charter writes the same guest layer into each
  piece (`charter/workspace.py:3136`).

### `.gitignore` (plane root) — the managed live-workspace block

- **Format:** plain text block inside the plane's own `.gitignore`.
- **Status:** stable — committed, so liveness travels with the plane; it *is* the record of
  which workspaces are LIVE.
- **Written by:** `workspace._write_live_block` (`charter/workspace.py:1418`) from
  `set_live` (`charter/workspace.py:1440`) and `refresh_live_block`
  (`charter/workspace.py:1430`, called by every `reinit`, `charter/workspace.py:4650`).
  Commands: `charter workspace live [--off]`, `workspace create --live`, `fork --live`,
  `rename` (moves the entry, `charter/workspace.py:1490`).
- **Read by:** `workspace.live_workspaces` (`charter/workspace.py:1346`), `is_live`
  (`charter/workspace.py:1366`) — and git.
- **Git:** committed.
- **Encoding details:**
  - Markers, verbatim:
    `# >>> charter live workspaces (managed by \`charter workspace live\`) >>>` and
    `# <<< charter live workspaces <<<` (`charter/workspace.py:1338`–`1339`).
  - Nine lines per LIVE workspace, workspaces sorted by name
    (`charter/workspace.py:1396`–`1401`):
    `!/workspaces/<n>/workspace.json`, `!/workspaces/<n>/workspace.md`,
    `!/workspaces/<n>/memory`, `!/workspaces/<n>/memory/**`,
    `!/workspaces/<n>/todos`, `!/workspaces/<n>/todos/**`,
    `!/workspaces/<n>/changes`, `!/workspaces/<n>/changes/**`,
    `/workspaces/<n>/changes/log/`.
  - Lines are joined with `\n` and the block has no trailing newline of its own; the rewrite
    is `re.sub(BEGIN .*? END, block, flags=DOTALL)` (`charter/workspace.py:1412`). A first
    write is inserted directly after the literal line `!/workspaces/.gitkeep\n`
    (`charter/workspace.py:1414`) — the anchor `charter init` writes
    (`charter/commands.py:1091`) — else appended at EOF with one blank-free `\n` on each side
    (`charter/workspace.py:1417`). Written with a plain `gi.write_text`, non-atomically.
  - Liveness is *parsed back* only from the `workspace.json` line:
    `^!/workspaces/([^/]+)/workspace\.json$` inside the block
    (`charter/workspace.py:1360`).
  - What a LIVE workspace actually stages is `_ws_meta_paths`
    (`charter/commands_workspace.py:1094`, list built at `charter/commands_workspace.py:1116`): `workspace.json`, `workspace.md`, `memory`,
    `todos` (each only if it exists) and `changes` only when `change.has_records`
    (`charter/commands_workspace.py:1119`). The two lists must agree and only a test holds
    them together.

### `.charter/…` — active-workspace pointers and per-plane workspace state

These are `.charter`'s to document in full; named here because they decide which workspace
a command acts on, or record workspace state.

| Path | What it holds | Status | Source |
|---|---|---|---|
| `.charter/sessions/<sid>.workspace` | the workspace chosen for that session, `name + "\n"` | stable (read by the status line, hooks, every command) | `charter/workspace.py:66`, written `charter/workspace.py:823` |
| `.charter/sessions/<sid>.lock` | the workspace that session is locked to, `name + "\n"` | stable | `charter/workspace.py:709`, written `charter/workspace.py:824` |
| `.charter/terminals/<tid>.workspace` | the terminal pane's workspace | stable | `charter/workspace.py:192`, written `charter/workspace.py:819` |
| `.charter/workspace-tab-order` | one workspace name per line, the tab strip's order | stable — the frame and the palette read the order another process wrote; deleting it costs the order, which the next launch recomputes (`charter/workspace.py:1066`) | `charter/workspace.py:978`, written `charter/workspace.py:1023` |
| `.charter/workspace-arrivals/<name>` | empty file; its existence marks "a handoff landed here" | stable — one process records the arrival, another reads it; deleting it clears the mark only | `charter/workspace.py:1113`, `charter/workspace.py:1127` |
| `.charter/unrecorded/<sha256(realpath(tree))[:32]>.json` | `{"errno": …, "says": …}` for a marker publish that failed | stable — `doctor` reads it in another process; recomputed on the next failed publish | `charter/workspace.py:2960`, written `charter/workspace.py:2977` |
| `.charter/ws-autosave/<ws>` | debounce marker (mtime + a float) for the Stop-hook autosave | internal — deleting it costs one extra commit attempt | `charter/commands_workspace.py:1171`, written `charter/commands_workspace.py:1179` |

Resolution order (`workspace.chosen`, `charter/workspace.py:615`–`649`, and `resolve`
adding the built-in fallback, `charter/workspace.py:586`):
`--workspace` → `$CHARTER_WORKSPACE` (stripped; whitespace-only is unset,
`charter/workspace.py:550`) → **the tree you stand in** (`from_path`,
`charter/workspace.py:348`) → `.charter/sessions/<sid>.workspace` → the frame's launch record
(`for_frame`, `charter/workspace.py:114`) → `.charter/terminals/<tid>.workspace` →
`workspaces/.default` → `config.DEFAULT_WORKSPACE` (`[workspace] default`, fallback
`"default"`, `charter/config.py:31`, `charter/config.py:734`). Pointers older than 30 days
are pruned from both directories on every `set_active` (`charter/workspace.py:45`,
`charter/workspace.py:881`).

**The Rust charter has every rung of this ladder but the frame's launch record**, because
`.charter/frame/**` is the tmux frame's and that binary neither reads nor writes there (the
ruling above). The two can therefore answer differently in exactly one state — a chat the frame
launched, with no session pointer yet — where the Rust side falls through to
`.charter/terminals/<tid>.workspace` and below. ADR 0032 records the decision, what an operator
on a frame-driven plane sees until then, and the one command that closes it.

---

## Personas, memory and the roster

The modules that own this area: `charter/persona.py`, `charter/memstore.py`,
`charter/recall.py`, `charter/curate.py`, `charter/commands_persona.py`,
`charter/dispatch.py`, `charter/skilluse.py`, `charter/report.py`.

Plane roots used below (`charter/config.py:819`, `:824`, `:828`, `:834`, `:36`):

| Global | Value |
|---|---|
| `PERSONAS_DIR` | `<plane>/personas` — `charter/config.py:819` |
| `SHARED_PERSONA` | `_shared` — `charter/config.py:36` |
| `PERSONA_STATE_DIR` | `<plane>/.charter/persona-state` — `charter/config.py:824` |
| `ACTIVE_PERSONA_FILE` | `<plane>/.charter/active-persona` — `charter/config.py:828` |
| `REPORTS_DIR` | `<plane>/.charter/reports` — `charter/config.py:834` |

A persona name is `[a-z0-9][a-z0-9._-]*`, matched with `fullmatch`
(`charter/persona.py:47`, `charter/persona.py:78`). A leading `_` is reserved for charter's
own namespaces (`_shared`, `_dispatch`, `_skills`) and `list_personas` skips any directory
starting with `_` (`charter/persona.py:234`).

---

### `personas/`

- **Format:** directory.
- **Status:** stable — committed; the operator creates personas here by hand or with
  `charter persona create`; every process (CLI, hooks, status line, frame) enumerates it.
- **Written by:** `charter/commands.py:2651` (`_ensure_front_door`, `charter init`),
  `charter/commands_persona.py:110` (`cmd_persona_create`), `charter/persona.py:2493`
  (`migrate`).
- **Read by:** `charter/persona.py:225` (`list_personas`) — the roster every other surface
  starts from: `charter/statusline.py:1779`, `charter/render.py:95`, `charter/doctor.py`,
  `charter/frame/switch.py`, `charter/report.py:169` (scrub), `charter/hooks.py:8138`.
- **Git:** committed. Nothing in `_GITIGNORE_BASELINE` (`charter/commands.py:1087`) covers
  `personas/`; verified with `git check-ignore` on the live plane (exit 1 = not ignored).
- **Encoding details:** membership = a subdirectory holding `persona.md`, not starting with
  `_` (`charter/persona.py:234`), plus legacy flat `personas/*.md` whose stem is not
  `readme` (case-insensitive, `charter/persona.py:230`). `list_personas` returns a sorted
  list of names.

---

### `personas/<name>/persona.md`

- **Format:** Markdown with a minimal, line-based frontmatter block (NOT YAML: no parser,
  no quote stripping, no nesting, no comments).
- **Status:** stable — hand-edited, committed, and read by the tool gate, the status line,
  hooks, `sync-agents` and (in M1-M3) the app.
- **Written by:** `charter/commands_persona.py:123` (`cmd_persona_create`, template at
  `:36`/`:57`), `charter/commands.py:2677` (`_ensure_front_door`, template at
  `charter/commands.py:2597`), `charter/persona.py:2504` (`migrate` renames the legacy flat
  file here). Plain `Path.write_text` — no atomic rename, no lock.
- **Read by:** `charter/persona.py:456` (`load`) is the single reader; through it
  `resolve` (`:872`), `lineage` (`:839`), `tools_of` (`:1580`), `effective_tools` (`:1691`),
  `vault_of` (`:2240`), `is_draft` (`:1846`), `declared_skills` (`:1957`), `routing_level`
  (`:939`), `routes_to` (`:962`), `lint` (`:2018`); `charter/toolgate.py:896`
  (PreToolUse gate), `charter/commands_persona.py:867` (`_render_agent`),
  `charter/hooks.py:7402` (SessionStart identity block), `charter/statusline.py`,
  `charter/render.py:97`, `charter/doctor.py`.
- **Git:** committed.
- **Encoding details:**
  - Frontmatter is parsed only when the file **starts with** `---`; `text.split("---", 2)`
    must yield ≥3 parts (`charter/persona.py:258`-`:260`). `parts[1]` is the frontmatter,
    `parts[2]` the body (stripped, `:268`).
  - Each frontmatter line: skipped if it has no `:`; `key, _, value = line.partition(":")`;
    both sides `.strip()`ed; empty key skipped (`charter/persona.py:261`-`:267`). Quotes are
    **kept** as part of the value (`charter/persona.py:95`).
  - Order is preserved as pairs and then collapsed to a dict — **last line wins** for a
    repeated key, and the duplicate is reported as an error (`charter/persona.py:489`,
    `charter/persona.py:355`).
  - Keys are matched **exactly**; a key differing only by case is an error and blocks agent
    generation (`charter/persona.py:329`, `charter/commands_persona.py:1127`). Unknown keys
    are a lint warning only (`charter/persona.py:2100`).
  - List-valued keys are comma-separated; `_csv_list` strips a surrounding `[…]` and each
    item (`charter/persona.py:510`).
  - `name` defaults to the directory name when absent (`charter/persona.py:484`).
  - Writer's key order (create): `name, role, vault, [extends], [delegate-when], draft`
    (`charter/commands_persona.py:36`, `:113`, `:118` — `extends` is spliced after `vault`,
    then `delegate-when` after `vault` too, so `extends` ends up above `delegate-when`;
    confirmed by running `persona create --extends`). Front door order:
    `name, role, vault, routing, delegate-when` (`charter/commands.py:2597`).
  - Body: everything after the closing `---`, stripped.

Full frontmatter vocabulary — `KNOWN_KEYS = AGENT_PASSTHROUGH_KEYS | CHARTER_OWN_KEYS`
(`charter/persona.py:305`, `charter/persona.py:309`, `charter/persona.py:322`). Every value
is a string; "type" below is how charter interprets it.

| Field | Type | Required / default | Meaning | Status | Source |
|---|---|---|---|---|---|
| `name` | string | defaults to directory name | Identity; emitted as the agent's `name:` | stable | `charter/persona.py:484`, `charter/commands_persona.py:870` |
| `role` | string (one line) | none; `lint` warns | Human role; in listings, the agent description and the session identity block | stable | `charter/commands_persona.py:779`, `charter/persona.py:2068` |
| `vault` | string, or the reserved `none` | none; `lint` warns; falls back to a vault tagged with the persona name | Which vault this persona's secrets live in. `none` = deliberately holds none → `vault_of` returns `None` | stable | `charter/persona.py:2218`, `:2240`, `:2221` |
| `extends` | one persona name | absent | Parent whose charter+tools are inherited; chain resolved root→child, cycle-safe | stable | `charter/persona.py:839`, `:872` |
| `uses` | CSV of persona names | absent | Routing edge; legacy grant (vault + tools + delegation) when `borrows:` is absent | stable | `charter/persona.py:1587`, `:1691` |
| `borrows` | CSV of persona names, or `none` | **absent ≠ empty**: absent = legacy `uses:` grant, `none`/unreadable = nothing | Which personas' tools the gate auto-approves | stable | `charter/persona.py:1656`, `:1597`, `:1616` |
| `delegate-when` | prose (one line) | none; `lint` warns; `create` requires it unless `--extends` | Routing trigger; becomes the generated agent's description | stable | `charter/commands_persona.py:780`, `:806` |
| `description` | string | absent | Agent description override (lower precedence than `agent-description`) | stable | `charter/commands_persona.py:869` |
| `agent-description` | string | absent | Agent description override (wins) | stable | `charter/commands_persona.py:869` |
| `tools` | CSV of program names | absent = none | Programs auto-approved by the PreToolUse gate while active; unioned along `extends` | stable | `charter/persona.py:1580`, `charter/toolgate.py:896` |
| `agent-tools` | CSV of harness tool names | absent = sub-agent inherits every tool | Emitted as the agent's `tools:`; MCP grants appended | stable | `charter/commands_persona.py:879`-`:892` |
| `disallowed-tools` | CSV | absent | Emitted as the agent's `disallowedTools:` (denylist) | stable | `charter/commands_persona.py:923` |
| `skills` | CSV of `[plugin:]skill` | absent | Preloaded into the sub-agent; emitted as `skills:`; linted against installed skills | stable | `charter/persona.py:1957`, `charter/commands_persona.py:908` |
| `draft` | `true/yes/1/on` (case-insensitive) truthy set | absent = not a draft | While set, **no** sub-agent is generated and any generated one is removed | stable | `charter/persona.py:1843`, `:1846`, `charter/commands_persona.py:1150` |
| `routing` | `off` \| `advise` \| `require` | absent/unknown → `off` | How insistently this persona hands work away; drives the UserPromptSubmit roster block | stable | `charter/persona.py:936`, `:939`, `charter/hooks.py:8518` |
| `routes-to` | CSV of persona names | absent | Priority order for the roster (never restricts) | stable | `charter/persona.py:962`, `:1001` |
| `activity` | `orchestrator` \| `standby` \| `advisory` | absent | Declares memory volume is not a usage signal; changes `persona stats` status | stable | `charter/persona.py:2408`, `:2444` |
| `dispatch-isolation` | `worktree` | absent | Emits `isolation: worktree` into the agent and a sentence into its description | stable | `charter/commands_persona.py:802`, `:916` |
| `model` | string | absent | Passed through verbatim into the agent frontmatter | stable | `charter/persona.py:305`, `charter/commands_persona.py:953` |
| `color` | string | absent | Passed through verbatim | stable | same |
| `memory` | string (truthy) | absent | Passed through verbatim **and** adds the "two memory stores" note to the body | stable | `charter/commands_persona.py:962` |

Inheritance merge (`charter/persona.py:872`-`:909`): iterate the chain root→child; every
truthy scalar key overwrites (child wins, `:892`); `tools`, `agent-tools`, `uses` are
order-preserving unions, parent first, deduped, and `uses` drops self (`:894`-`:896`);
`extends` itself is not copied into the merged meta; charters are concatenated, each
non-root ancestor's body prefixed with
`\n\n---\n\n### ⤷ \`{child}\` extends \`{parent}\` — its own charter\n\n` (`:900`);
`meta["name"]` is forced back to the queried name (`:905`); merged list keys are re-joined
with `", "` (`:907`-`:908`).

---

### `personas/<name>.md` (legacy flat layout)

- **Format:** same file as above, one level up.
- **Status:** stable — still resolved for read on old checkouts.
- **Written by:** nothing any more; `charter/persona.py:2493` (`migrate`) moves it to
  `personas/<name>/persona.md` and scaffolds `memory/` + `refs/`.
- **Read by:** `charter/persona.py:172` (`def_path` prefers the directory layout, falls back
  here, else returns the canonical new path), `charter/persona.py:230` (`list_personas`).
- **Git:** committed.
- **Encoding details:** identical parsing. A stem of `readme` (any case) is not a persona.

---

### `personas/<name>/memory/MEMORY.md`

- **Format:** Markdown; a header block then one link line per memory.
- **Status:** stable — committed, hand-editable, read by the SessionStart hook, `doctor`,
  `curate` and `persona recall`.
- **Written by:** `charter/persona.py:2265` (`scaffold_memory`, header at `:2277`),
  `charter/memstore.py:138` (`index_append`, appends one line), `charter/memstore.py:472`
  (`_drop_index_line`, the only truncating write), `charter/memstore.py:86` (`ensure_index`,
  used by workspace memory; `O_EXCL` create at `:97`).
- **Read by:** `charter/hooks.py:6823` (`_read_index` → SessionStart memory digest,
  `charter/hooks.py:6908`), `charter/memstore.py:259` (`_listed` → `index_drift` at `:217`,
  `doctor`, `curate.report` at `charter/curate.py:71`),
  `charter/commands_persona.py:1267` (`persona recall` prints it verbatim).
- **Git:** committed.
- **Encoding details:**
  - Scaffold header (`charter/persona.py:2277`), exactly:
    `# Memory Index — {name|"shared (all personas)"}\n\nOne line per memory; each links a file holding a single durable fact.\nWritten by the persona as it learns; committed and shared.\n`
    — note **no blank line** between the header and the first appended entry (confirmed on
    the live plane and in a temp plane).
  - `index_append` fallback header when the file is missing: `# Memory Index\n\n`
    (`charter/memstore.py:142`).
  - Entry line: `- [{title}]({filename})\n`, appended in `"a"` mode, chronological by write
    order (`charter/memstore.py:143`-`:144`). No sorting, no dedupe.
  - Readers match `- [` prefix (`charter/hooks.py:6851`) and the link regex
    `\(([A-Za-z0-9][\w.-]*\.md)\)` (`charter/memstore.py:214`).
  - `MEMORY.md` is excluded from the memory-file glob by name
    (`charter/memstore.py:208`).
  - Deletion rewrites the file as the surviving lines joined with `\n` plus one trailing
    `\n` (none when empty) — `charter/memstore.py:489`-`:490`.

---

### `personas/<name>/memory/<slug>.md` (and `personas/_shared/memory/<slug>.md`)

- **Format:** Markdown; fixed 3-part shape.
- **Status:** stable — committed, shared with the team, read by every recall path and by the
  session briefing.
- **Written by:** `charter/memstore.py:101` (`write`) via `charter/persona.py:2298`
  (`remember`), from `charter persona remember` (`charter/commands_persona.py:1188`).
- **Read by:** `charter/memstore.py:169`/`:197` (`files`/`read_files` — the one gate),
  `:289` (`entries`), `:367` (`search`), `:408` (`duplicates`), `:429` (`resolve`);
  `charter/persona.py:2330`/`:2356`/`:2411`; `charter/recall.py:204` (`charter recall`);
  `charter/curate.py:38`; `charter/statusline.py:1779`; `charter/render.py:95`;
  `charter/hooks.py:6866` (digest counts).
- **Git:** committed. Whether charter itself commits/pushes it is `[memory] share`
  (below).
- **Encoding details:**
  - Content, exactly (`charter/memstore.py:131`-`:132`):
    `# {title}\n\n_{YYYY-MM-DD HH:MM} · {kind}_\n\n{text}\n`
    — `·` is U+00B7 with single spaces; `kind` is `persistent` for committed persona memory,
    `ephemeral` for scratch (`charter/persona.py:2317`).
  - Timestamp is **local, naive** `datetime.now()` (`charter/memstore.py:64`), minute
    precision. Persona memory is never `timestamped=` (no `YYYYMMDD-HHMMSS-` filename
    prefix) — `charter/persona.py:2320`, `charter/memstore.py:119`.
  - `text` is `.strip()`ed; empty raises `ValueError` (`charter/memstore.py:107`-`:109`).
  - Title = explicit `--title` or the first line of the body, stripped, capped at 72
    (`charter/persona.py:2315`, `charter/memstore.py:33`, `:110`).
  - Filename = `slug(title) + ".md"`; slug = lowercase, every run of non-`[a-z0-9]`
    replaced by `-`, leading/trailing `-` stripped, then **truncated to 48 chars** (so a
    trailing `-` can survive), `"note"` when empty (`charter/memstore.py:23`, `:26`-`:28`).
    Collision → `-2`, `-3`, … before `.md` (`charter/memstore.py:123`-`:124`).
  - Write goes through `config.write_for` (`charter/memstore.py:131`); outside
    `.charter/` that is a plain `open`, so the umask decides the mode. Not atomic.
  - Date used by `stats`/`recall --since`: in-body `_YYYY-MM-DD` stamp
    (`^_(\d{4}-\d{2}-\d{2})[ T]`, multiline — `charter/memstore.py:147`), falling back to a
    `YYYYMMDD-` filename prefix (`:160`).

| Field | Type | Required / default | Meaning | Status | Source |
|---|---|---|---|---|---|
| `# <title>` line | first `# ` line | required (written always) | Title used by index, search (3× weight) and `entries` | stable | `charter/memstore.py:132`, `:325` |
| `_<stamp> · <kind>_` line | `%Y-%m-%d %H:%M` + kind | required (written always) | Recording date; `kind` ∈ `persistent`/`ephemeral` | stable | `charter/memstore.py:132`, `charter/persona.py:2317` |
| body | free Markdown | required, non-empty | The fact | stable | `charter/memstore.py:107` |

---

### `personas/<name>/memory/archive/<slug>.md`

- **Format:** same memory file, moved.
- **Status:** stable — committed; a reversible retire that drops the memory out of every
  glob (the glob is flat, so `archive/` is invisible to `files()`).
- **Written by:** `charter/memstore.py:503` (`archive`) via `charter/curate.py:92`
  (`apply_safe`, exact-duplicate collapse) — reached by `charter persona optimize --apply`.
- **Read by:** nothing in charter (deliberately out of the active set); git history and
  humans only.
- **Git:** committed.
- **Encoding details:** `rename` into `<mem_dir>/archive/`, created with `mkdir_for`;
  collision → `<stem>-2.md` (`charter/memstore.py:521`-`:523`); the index line is dropped
  (`:525`).

---

### `personas/<name>/memory/.gitkeep`, `personas/<name>/refs/.gitkeep`

- **Format:** empty file.
- **Status:** stable — committed, and the only reason an empty `memory/`/`refs/` survives a
  clone. (A front-door persona has these and **no** `MEMORY.md`/`README.md`.)
- **Written by:** `charter/commands.py:2680` (`_ensure_front_door`, `charter init` only).
- **Read by:** nothing (`files()` filters to `*.md`, `charter/memstore.py:208`).
- **Git:** committed.

---

### `personas/<name>/refs/README.md` and `personas/<name>/refs/**`

- **Format:** Markdown documents, arbitrarily nested.
- **Status:** stable — committed curated docs; `charter recall` reads them as a default
  scope; the operator writes them by hand.
- **Written by:** `charter/persona.py:2283`-`:2291` (`scaffold_memory` writes only
  `README.md`); everything else is hand-written.
- **Read by:** `charter/recall.py:128`-`:133` + `:142` (`_ref_dirs`, recursive: every
  subdirectory is offered as its own source because `memstore.files` is a flat glob);
  `charter/commands_persona.py:322` (`persona show` counts refs, excluding `README.md`).
- **Git:** committed.
- **Encoding details:** `README.md` scaffold text at `charter/persona.py:2287`-`:2291`:
  `# References — {who}\n\nCurated docs, links, and snippets this role collects. Committed and shared. Never store secrets here — those live only in the vault.\n`.
  Refs are read as memory files (`*.md`, `MEMORY.md` excluded), so an `# ` heading is the
  title and a `_date_` line, if present, is the date.

---

### `personas/<name>/mcp.json`

- **Format:** JSON — `.mcp.json`'s schema plus charter-only `secrets` / `secret_files` maps
  per server.
- **Status:** stable — committed, hand-written (often pasted from a server's README), read
  by `sync-agents`, `lint`, `persona use` and the consent flow.
- **Written by:** nothing in charter — hand-edited only.
- **Read by:** `charter/persona.py:653` (`_mcp_declared`) → `mcp_servers` (`:622`),
  `mcp_refused` (`:641`), `mcp_credentialed` (`:799`), `mcp_withheld` (`:832`),
  `mcp_render_entry` (`:730`); `charter/commands_persona.py:876`/`:926` (render),
  `charter/commands_persona.py:1996` (`--approve-mcp`), `charter/persona.py:2114` (`lint`).
- **Git:** committed.
- **Encoding details:**
  - Only `doc["mcpServers"]` is read and it must be a dict; any `OSError`/`ValueError` is
    swallowed and the file skipped (`charter/persona.py:673`-`:677`).
  - Unioned along the `extends` chain **reversed** (parent first, child wins) —
    `charter/persona.py:667`.
  - Server names are bounded at the boundary: `[A-Za-z0-9_][A-Za-z0-9._-]{0,63}`, `fullmatch`
    (`charter/persona.py:549`, `:552`). A refused name drops the server and is reported as a
    lint error and a `sync-agents` warning.
  - Rendering (`charter/persona.py:730`): `secrets`/`secret_files` keys are removed from the
    emitted entry; with a real vault (`vault: none` → no vault, `:689`) **and** a recorded
    approval (`charter/mcpseen.py`), the entry becomes
    `command: "charter"`, `args: ["secret","exec",<vault>, "--env","NAME=key"…, "--file","NAME=key"…, "--stream"|"--exec", "--", <original command>, *<original args>]`
    (`charter/persona.py:781`-`:794`). `--stream` whenever any `secret_files` is present.

| Field | Type | Required / default | Meaning | Status | Source |
|---|---|---|---|---|---|
| `mcpServers` | object | required (else no servers) | Map of server name → entry | stable | `charter/persona.py:674` |
| `mcpServers.<name>` | string key | must match `_MCP_NAME_RE` | Server name; also interpolated into `mcp__<name>__*` | stable | `charter/persona.py:549`, `charter/commands_persona.py:890` |
| `…command`, `…args`, `…env`, any other key | as `.mcp.json` | passed through | Emitted verbatim into the agent (all unknown keys are kept) | stable | `charter/persona.py:747` |
| `…secrets` | `{ENV_VAR: vault-key}` | optional | Vault value injected as an env var | stable | `charter/persona.py:751`, `:782`-`:783` |
| `…secret_files` | `{ENV_VAR: vault-key}` | optional | Vault value materialised to a 0600 file whose path is the env var | stable | `charter/persona.py:758`, `:784`-`:785` |

---

### `personas/<name>/bin/<script>`

- **Format:** any executable file.
- **Status:** stable — committed, hand-written, run by the dispatched agent by path and
  vouched for by the Bash tool gate.
- **Written by:** nothing in charter.
- **Read by:** `charter/persona.py:580` (`bin_scripts`, union along the reversed lineage,
  executable files only), `charter/persona.py:610` (`bin_issues` — a non-executable file is
  a lint warning), `charter/commands_persona.py:978`-`:1010` (the "You carry your own
  executables" block in the generated agent), `charter/toolgate.py` (inode check for a path
  in command position).
- **Git:** committed, mode bit included.
- **Encoding details:** flat `sorted(d.iterdir())` per ancestor; only `f.is_file() and
  os.access(f, os.X_OK)` counts (`charter/persona.py:604`-`:606`). `uses:`/`borrows:` do
  **not** carry scripts. Paths are rendered plane-relative in the agent
  (`charter/commands_persona.py:858`, `:1003`).

---

### `personas/_shared/` (`memory/`, `refs/`)

- **Format:** exactly the per-persona `memory/` and `refs/` above.
- **Status:** stable — committed cross-persona namespace.
- **Written by:** `charter/persona.py:2294` (`ensure_shared` → `scaffold_memory(..., shared=True)`),
  reached from `persona create` (`charter/commands_persona.py:125`) and `persona migrate`
  (`:1842`); memories by `charter persona remember --shared`.
- **Read by:** `charter/recall.py:124` (`shared` scope, default-on), `:132` (`refs:shared`),
  `charter/hooks.py:6910` (shared half of the SessionStart digest),
  `charter/commands_persona.py:1259` (`persona recall`), `persona stats _shared` /
  `persona optimize` (`charter/commands_persona.py:1571`, `:1757`).
- **Git:** committed.
- **Encoding details:** index header says `# Memory Index — shared (all personas)`
  (`charter/persona.py:2276`). `_shared` is outside the persona alphabet on purpose, so no
  persona can take the name; `list_personas` never returns it.

---

### `personas/.default` (legacy)

- **Format:** plain text — one persona name plus optional whitespace.
- **Status:** stable — committed, hand-written, read on every turn by the persona resolver.
- **Written by:** nothing writes it any more; `charter persona default --clear` unlinks it
  (`charter/commands_persona.py:580`).
- **Read by:** `charter/persona.py:915` (`default_persona`) → `_resolved` (`:1407`),
  `plane_default` (`:1058`).
- **Git:** committed.
- **Encoding details:** read, `.strip()`ed; the value must pass `reference_ok` **and** the
  persona's definition file must exist, else the rung resolves to nothing
  (`charter/persona.py:930`). Ranked **below** `charter.toml` `[persona] default`
  (`charter/persona.py:1404`-`:1409`).

---

### `personas/_dispatch/<YYYY-MM>.<host>.jsonl`

- **Format:** JSON Lines, append-only; one object per line.
- **Status:** stable — committed (so the tally merges across machines), written by a hook
  process and read by the CLI, the status line and the frame switcher.
- **Written by:** `charter/dispatch.py:65` (`record`), `:98` (`record_advice`), `:134`
  (`record_resume`), `:170` (`record_handoff`) — driven by
  `charter/hooks.py:8170` (PostToolUse Task/Agent), `charter/hooks.py:8141` (PostToolUse
  SendMessage), `charter/hooks.py:8518` (UserPromptSubmit roster block),
  `charter/commands_handoff.py:261`.
- **Read by:** `charter/dispatch.py:322` (`_read_all`, memoised per file by
  `(mtime_ns, size)` at `:261`) → `tally` (`:343`), `last_seen` (`:354`), `advice_tally`
  (`:118`), `resume_tally` (`:208`), `generic_share` (`:368`),
  `routed_since_first_advice` (`:222`); `charter/persona.py:1061` (`_dispatches` → `by_use`
  → status line and frame switcher), `charter/commands_persona.py:1577` (`persona stats`).
- **Git:** committed; `charter/hooks.py:8189` (`_commit_dispatch`) commits/pushes it
  reactively **only** when `[memory] share` is `commit`/`push` (default `local` → left
  uncommitted for the operator).
- **Encoding details:**
  - Path: `personas/_dispatch/{when:%Y-%m}.{host}.jsonl` (`charter/dispatch.py:60`-`:62`),
    `when` is UTC now (`:56`).
  - `host` = `socket.gethostname()` first label, `[^A-Za-z0-9_-]` stripped, 32 chars,
    `"unknown"` when empty (`charter/dispatch.py:50`-`:53`). No env override.
  - One line = `json.dumps(obj, sort_keys=True) + "\n"` → **keys are alphabetical**, ASCII
    escaped, no spaces beyond `json.dumps` defaults (`", "`/`": "`).
  - Written with `os.open(..., O_WRONLY|O_CREAT|O_APPEND, 0o644)` and one `os.write` — no
    lock; `record_handoff` additionally passes `O_NOFOLLOW` (`charter/dispatch.py:198`).
  - `ts` = `datetime.now(timezone.utc).isoformat(timespec="seconds")` →
    `2026-09-17T14:01:20+00:00`. A row with no timezone is read as UTC
    (`charter/dispatch.py:338`).
  - A row is kept by the reader only if it is a dict with `agent` or `event`
    (`charter/dispatch.py:316`); unparseable lines are skipped silently.

| Field | Type | Required / default | Meaning | Status | Source |
|---|---|---|---|---|---|
| `ts` | ISO-8601 UTC, seconds | always | When | stable | `charter/dispatch.py:77` |
| `agent` | string | on dispatch + resume rows | `subagent_type` — a persona name or a generic (`general-purpose`, `Explore`, `claude`, `Plan`) | stable | `charter/dispatch.py:77`, `:43` |
| `event` | `advice` \| `resume` \| `handoff` | absent on a plain dispatch (that absence *is* what `tally` counts) | Row kind | stable | `charter/dispatch.py:95`, `:131`, `:167`, `:351` |
| `placement` | `here` \| `elsewhere` | handoff rows only | Was the new chat in this workspace | stable | `charter/dispatch.py:190`, `charter/commands_handoff.py:261` |
| `created` | bool | handoff rows only | Whether the handoff created the workspace | stable | `charter/dispatch.py:189` |

Nothing else may appear: no prompt, description, workspace name or persona name on a
handoff row (`charter/dispatch.py:170` docstring).

---

### `personas/_dispatch/<YYYY-MM>.<host>.backfill.jsonl`

- **Format:** JSON Lines, **rewritten whole** (not appended).
- **Status:** stable — committed, read by the same tally readers as the live file.
- **Written by:** `charter/dispatch.py:476` (`backfill`), from
  `charter persona dispatch-backfill` (`charter/commands_persona.py:1714`, which then
  commits the files at `:1734`-`:1736`).
- **Read by:** the same `_read_all` glob (`charter/dispatch.py:327`); excluded from
  `_live_keys` (`:417`) so it never de-duplicates against itself.
- **Git:** committed.
- **Encoding details:** every existing `*.backfill.jsonl` is unlinked, then each month file
  is written as the **sorted set** of its `json.dumps({"ts","agent"}, sort_keys=True)` lines
  joined by `\n` plus a trailing `\n` (`charter/dispatch.py:500`-`:503`). Rows carry only
  `ts` and `agent`. Source: this project's Claude Code transcripts under
  `~/.claude/projects/<plane path with "/"→"-">` (`charter/dispatch.py:383`-`:394`,
  `:443`); `ts` is the transcript timestamp truncated to 19 chars (`:472`), so backfilled
  rows have **no timezone suffix** and are read as UTC. `last_backfill()` uses the file
  mtime (`:430`).

---

### `personas/_skills/<YYYY-MM>.<host>.jsonl`

- **Format:** JSON Lines, append-only.
- **Status:** stable — committed, written by a hook, read by `persona stats`.
- **Written by:** `charter/skilluse.py:67` (`record`) from `charter/hooks.py:8054`
  (PostToolUse on the `Skill` tool; reads `tool_input.skill` or opencode's `name`).
- **Read by:** `charter/skilluse.py:95` (`_read_all`) → `by_persona` (`:121`), `drift`
  (`:133`); `charter/commands_persona.py:1622` (`persona stats` SKILLS block).
- **Git:** committed. Nothing commits it automatically (no `_commit_dispatch` equivalent).
- **Encoding details:** path `personas/_skills/{%Y-%m}.{host}.jsonl`
  (`charter/skilluse.py:59`, `:62`-`:64`), same host derivation (`:48`-`:51`); same
  `json.dumps(..., sort_keys=True)` + `\n`, same `O_APPEND`, `0o644` (`:80`-`:85`). Rows
  without a truthy `skill` are ignored on read (`:116`).

| Field | Type | Required / default | Meaning | Status | Source |
|---|---|---|---|---|---|
| `ts` | ISO-8601 UTC, seconds | always | When | stable | `charter/skilluse.py:80` |
| `skill` | string | always (row dropped if empty) | Skill name as the harness reported it; may be `plugin:skill`, compared on the leaf | stable | `charter/skilluse.py:82`, `:128` |
| `persona` | string or **`null`** | always present; `null` when no persona is active | Which persona invoked it | stable | `charter/skilluse.py:82` |

---

### `.claude/agents/<name>.md` (generated sub-agent)

- **Format:** Markdown with YAML frontmatter (the harness's format).
- **Status:** stable — committed, read by Claude Code itself, and regenerated byte-for-byte
  by `lint`'s staleness check (`charter/commands_persona.py:1437` compares
  `path.read_text().strip()` with a fresh render — so a Rust writer must match exactly or
  every persona lints stale).
- **Written by:** `charter/commands_persona.py:1164` (`_write_agent`), from
  `charter persona sync-agents` (`:2035`/`:2066`), `persona create` (`:129`) and
  `persona migrate` (`:1854`). Removed by `_remove_agent` (`:1168`) for a draft, an
  unreadable frontmatter key, a removed persona, or an orphan sweep (`:2101`-`:2106`).
- **Read by:** Claude Code (sub-agent definition); `charter/commands_persona.py:1434`
  (staleness), `charter/freshness.py:24` (restart hint),
  `charter/workspace.py:2081`/`:4127` (mirrored into a workspace's checkouts).
- **Git:** committed (`.gitignore` covers only `.claude/settings.local.json` —
  `charter/commands.py:1100`; `git ls-files` on the live plane lists all five agents).
- **Encoding details:**
  - Whole file = `"---\n" + "\n".join(fm) + "\n---\n" + body` (`charter/commands_persona.py:1117`);
    `body` starts with the marker comment and ends with a trailing newline.
  - Frontmatter lines, in this fixed order (`charter/commands_persona.py:870`-`:955`):
    1. `name: <name>`
    2. `description: "<escaped>"` — `_yaml_str` (`:773`): newlines → spaces, strip, then
       `\` → `\\` and `"` → `\"`, wrapped in double quotes.
    3. `tools: <agent-tools>[, mcp__<server>__*…]` — only when `agent-tools` is set; MCP
       grants appended for each declared server whose name passes `mcp_name_ok` and is not
       already mentioned (`:879`-`:892`).
    4. `skills: a, b` — when `skills:` is declared (`:908`-`:910`).
    5. `isolation: worktree` — when `dispatch-isolation: worktree` (`:916`-`:917`).
    6. `disallowedTools: <verbatim>` — when `disallowed-tools` is set (`:923`-`:924`).
    7. `mcpServers:` followed by `  - {"<server>": {…}}` per server, **sorted by server
       name**, each a one-line JSON object of the whole single-key mapping via
       `contain.json_line` (`:926`-`:952`).
    8. passthrough keys in declaration order `model`, `color`, `memory` (`:953`-`:955`,
       `charter/persona.py:305`).
  - Marker (the file's identity as generated):
    `<!-- GENERATED by \`charter persona sync-agents\` from <plane-relative persona.md> — edit the persona, not this file. -->`
    (`charter/commands_persona.py:766`, `:1105`). A file without the marker is never
    overwritten or deleted (`:1159`, `:1171`).
  - Body sections, in order (`charter/commands_persona.py:1105`-`:1116`): intro line naming
    the persona and role → the **resolved** charter (inheritance concatenated) → `## As a
    persona sub-agent` with the forge credential rule (`_credential_rule`, `:811` — derived
    from the plane's declared forges, so `gh` vs `glab` varies per plane), the credential
    block (`:1077` or the `vault: none` variant at `:1085`), the `bin/` block, the
    `uses:`/`borrows:` block (wording differs by whether `borrows:` is declared, `:1020`
    vs `:1029`), the `memory:` note (only when `memory:` is set), the generic handoff line,
    the conventions line → `## Memory`.
  - Description when neither `agent-description` nor `description` is set
    (`charter/commands_persona.py:778`-`:808`): `The {role} persona. Delegate to it for
    {delegate-when}.` (or `Delegate {role.lower()} tasks to it.`) plus one of
    ` Runs {tools} and pulls credentials from the '{vault}' vault.` /
    ` Runs {tools}. Holds no credentials of its own.` /
    ` Pulls credentials from the '{vault}' vault.` / ` Holds no credentials of its own.`,
    plus a worktree sentence when `dispatch-isolation: worktree`.
  - Written with plain `write_text` into `<tree>/.claude/agents/`; `sync-agents` run from a
    linked worktree writes into that worktree (`charter/commands_persona.py:2048`-`:2063`).

---

### `.charter/persona-state/ephemeral/<session>/<name|_shared>/<slug>.md`

- **Format:** the memory-file shape above, `kind` = `ephemeral`.
- **Status:** internal — one module writes and reads it as session scratch, it is
  gitignored, and it is deleted by the GC. Deleting it loses that session's scratch notes
  only; nothing regenerates them, and no other process depends on them.
- **Written by:** `charter/persona.py:2298` (`remember(..., ephemeral=True)` →
  `memstore.write(..., index=False)` at `:2320`), from
  `charter persona remember --ephemeral`.
- **Read by:** `charter/persona.py:2330` (`memories(..., ephemeral=True)`),
  `charter/recall.py:122` (the opt-in `ephemeral` scope),
  `charter/commands_persona.py:1271` (`persona recall`), `charter/statusline.py:1779`.
- **Git:** gitignored — it is under `/.charter/`, ignored by `_GITIGNORE_BASELINE`
  (`charter/commands.py:1095`).
- **Encoding details:** `<session>` is `session.bucket()` — `$CHARTER_SESSION_ID`, else
  `$CLAUDE_CODE_SESSION_ID`, else the literal `nosession`
  (`charter/session.py:65`-`:66`, `:23`, `charter/persona.py:205`-`:215`). No `MEMORY.md` is
  written here (`index=False`). Directories are created 0700 via `config.mkdir_for`
  (`charter/memstore.py:83`), files 0600 via `config.open_for`. GC: a session directory that
  is not the current one and whose newest mtime is older than 6h is `rmtree`d
  (`charter/persona.py:2462`-`:2490`), from `charter persona _gc`
  (`charter/commands_persona.py:1917`) on SessionStart.

---

### `.charter/persona-state/trace/<session>.jsonl`

- **Format:** JSON Lines, append-only.
- **Status:** stable (by the brief's rule) — written by hooks and CLI commands in one
  process and read by `charter trace` / `charter persona recall` in another. Machine-local
  and safe to delete (the history is lost; nothing regenerates it), so it is a borderline
  call — see the Appendix.
- **Written by:** `charter/trace.py:69` (`record`) — persona-relevant events:
  `persona-use` (`charter/persona.py:1533`), `memory` (`charter/persona.py:2323`), `note`
  (`charter/commands_persona.py:1821`), `dispatch`/`resume`/`skill` (`charter/hooks.py`),
  plus guard/secret events owned by other areas.
- **Read by:** `charter/trace.py:93` (`read`), `:106` (`for_persona`),
  `charter/commands_persona.py:1280`, `:1824`, `charter/commands_persona.py:1868`
  (`charter trace`).
- **Git:** gitignored (under `/.charter/`).
- **Encoding details:** one `contain.json_line(rec) + "\n"` per event, appended through
  `config.open_for` (0600 under the state dir). Every record carries
  `ts` = **local naive** `datetime.now().isoformat(timespec="seconds")` and `event`; other
  fields are the call's kwargs with `None` dropped, in insertion order (**not** sorted —
  unlike the `_dispatch` store). `<session>` is `session.bucket()`.

---

### `.charter/reports/<id>.json`

- **Format:** JSON object, `indent=2`, no trailing newline.
- **Status:** stable — written by `cli.main`'s crash handler in one process and read by
  every later `charter report …` invocation; the Reporter reads and edits the drafts.
  (Document the **shape only** — contents may quote a Reporter's own prose.)
- **Written by:** `charter/report.py:302` (`_write`, via `config.write_for` into a 0700
  dir), from `record_bug` (`:374`) / `record_described` (`:384`) / `mark_sent` (`:630`);
  crash path `charter/cli.py:2028`.
- **Read by:** `charter/report.py:268` (`load`), `:281` (`_all` → `pending`,
  `all_reports`), `charter/commands_report.py`.
- **Git:** gitignored (under `/.charter/`).
- **Encoding details:** filename `<id>.json` where `id` is the 16-hex fingerprint —
  for a bug, `sha256(exception_type + "\n" + deepest charter frame)[:16]`
  (`charter/report.py:91`-`:110`); for a described report,
  `sha256(kind + "\n" + scrubbed text)[:16]` (`:397`). Same id twice = the same file, with
  `occurrences` incremented (`:351`). Caps: 25 distinct pending reports
  (`charter/report.py:38`, `:359`), unsent drafts older than 30 days pruned on write
  (`:43`, `:325`).

| Field | Type | Required / default | Meaning | Status | Source |
|---|---|---|---|---|---|
| `id` | 16 hex chars | always | Fingerprint = filename stem | stable | `charter/report.py:364` |
| `kind` | `bug` \| `gap` | always | Report kind (also an upstream label) | stable | `charter/report.py:365`, `:608` |
| `payload` | object | always | Closed allowlist; see below | stable | `charter/report.py:54` |
| `occurrences` | int | 1 | Times seen on this machine | stable | `charter/report.py:351`, `:367` |
| `first_seen` / `last_seen` | float epoch seconds | `time.time()` | Draft age (drives pruning) | stable | `charter/report.py:368`-`:369` |
| `issue_url` | string \| `null` | `null` | Set by `mark_sent` once filed | stable | `charter/report.py:370`, `:635` |
| `payload.charter_version` | string | always | `charter.__version__` | stable | `charter/report.py:121` |
| `payload.python_version` | string | always | `platform.python_version()` | stable | `charter/report.py:122` |
| `payload.os` | string | always | `platform.platform()` | stable | `charter/report.py:123` |
| `payload.subcommand` | string | bug only | Subcommand name (never argv) | stable | `charter/report.py:124` |
| `payload.exception_type` | string | bug only | Exception class name | stable | `charter/report.py:124` |
| `payload.frames` | list of `charter/<file>:<line> in <fn>` | bug only | Charter frames only, package-relative | stable | `charter/report.py:68`-`:88` |
| `payload.message` | string | bug only | `str(exc)` — free text, unvetted | stable | `charter/report.py:126` |
| `payload.text` | string | gap/described only | Scrubbed prose | stable | `charter/report.py:249` |
| `payload.scrubbed` | list of category labels (`[workspace]`, `[persona]`, `[vault]`, `[token-env]`, `home paths`) | gap/described only | What the scrub removed | stable | `charter/report.py:155`, `:254` |

Persona relevance of the scrub: `charter/report.py:164`-`:175` redacts every persona name
(`persona.list_personas()`) and every workspace/vault identifier out of a described report
before it is stored.

---

### `~/.config/charter/reporting-consent` (outside the plane)

- **Format:** plain text, one sentence.
- **Status:** stable — it is the consent record `charter report send` gates on, written by
  one command and read by another, and the Reporter deletes it to withdraw.
- **Written by:** `charter/report.py:472` (`grant_consent`) from
  `charter/commands_report.py:104`.
- **Read by:** `charter/report.py:468` (`has_consent`) — existence only; contents are never
  parsed.
- **Git:** outside the plane. Path is
  `$CHARTER_CONFIG_HOME` → `$XDG_CONFIG_HOME` → `~/.config`, then `charter/reporting-consent`
  (`charter/report.py:462`-`:465`) — deliberately per-human, not per-plane and not committed.
- **Encoding details:** exact body at `charter/report.py:475`-`:477`; parent created with a
  plain `mkdir(parents=True)`, written with `write_text` (umask decides the mode).

---

### `.charter/sessions/<sid>.persona`, `.charter/terminals/<tid>.persona`, `.charter/active-persona`

- **Format:** plain text — the persona name plus `\n`.
- **Status:** stable — written by `charter persona use` in one process and read by every
  other charter process in that session/terminal (status line, hooks, tool gate, frame).
  (The `sessions/`/`terminals/` directories themselves belong to the workspaces area; the
  `.persona` files in them are `persona.py`'s.)
- **Written by:** `charter/persona.py:1488` (`set_active`, `config.write_for` at `:1528` →
  0600 under a 0700 dir); the plane-wide file only when there is neither a session id nor a
  terminal id (`:1529`-`:1530`). Removed by `clear_active` (`:1541`).
- **Read by:** `charter/persona.py:1199` (`_read_pointer`) → `_resolved` (`:1379`) →
  `resolve_active`/`selection`, `for_session` (`:1225`), `pointers_naming` (`:1208`).
- **Git:** gitignored (under `/.charter/`).
- **Encoding details:** content is `name + "\n"`; readers `.strip()` and treat empty as
  unset. Resolution order (`charter/persona.py:1379`-`:1410`): `--persona` →
  `$CHARTER_PERSONA` (stripped; whitespace-only = unset, `:1242`) → session pointer →
  terminal pointer → `.charter/active-persona` → `charter.toml` `[persona] default` →
  `personas/.default` → none. A rung naming a persona that does not exist still wins
  (`charter/persona.py:1438`). Session id = `session.bucket()`; terminal id =
  `session.terminal()` (`$TERM_SESSION_ID`/`$TMUX_PANE`/`$STY`/`$SSH_TTY`), and a `%9` pane
  becomes the filename `-9.persona` (observed in the fixture run).

---

### `.charter/mcp-approved.json`

- **Format:** JSON object, `indent=2`, `ensure_ascii=False`, trailing newline.
- **Status:** stable — written by `sync-agents --approve-mcp` and read by the render on a
  later run; machine-local by design (an approval must not travel in git).
- **Written by:** `charter/mcpseen.py:253` (`approve`, replaces the persona's whole set),
  from `charter/commands_persona.py:2029`.
- **Read by:** `charter/mcpseen.py:247` (`approved`) → `charter/persona.py:779`
  (`mcp_render_entry`) and `mcp_withheld` (`:832`).
- **Git:** gitignored (under `/.charter/`).
- **Encoding details:** `{"<persona>": ["<64-hex sha256>", …]}`, values sorted
  (`charter/mcpseen.py:262`, digest at `charter/mcpseen.py:236`). The fingerprint is a SHA-256 of the **consent line** the
  operator was shown. (This file sits on the boundary with the secrets area; included here
  because `persona.py` is its only consumer.)

---

### `[memory] share` — how it affects persona files

`charter.toml`'s `[memory] share` (`local` | `commit` | `push`, default `local`,
`charter/instance.py:460`, clamped at `charter/instance.py:444`) decides only whether charter *itself* commits
and pushes the files above — never their format:

- `charter persona remember` (persistent): commits the memory file **and** its `MEMORY.md`
  (`charter/commands_persona.py:1206`-`:1209` → `charter/planegit.py:98`).
- `charter persona forget`: commits the memory **directory**
  (`charter/commands_persona.py:1308`-`:1310`).
- `charter persona optimize --apply`: commits the memory directory
  (`charter/commands_persona.py:1786`-`:1787`).
- `charter persona dispatch-backfill`: commits every `_dispatch/*.jsonl`
  (`charter/commands_persona.py:1734`-`:1736`).
- The dispatch hook: commits the one tally file it appended, under an flock
  (`charter/hooks.py:8189`-`:8216`).
- `charter persona memory-sync`: commits every uncommitted path matching
  `personas/[^/]+/(?:memory|refs)/` regardless of posture, after a secret scan
  (`charter/commands_persona.py:1316`, `:1345`-`:1400`).

Under `local` (the default) charter writes the files and commits nothing; `personas/`
therefore shows up in `git status` for a human.

---

## Vaults: the registry, and nothing inside it

This section and the one after it cover two areas that meet: the vault registry — its shape,
never its contents — and every file charter writes for a harness to read, inside the plane
and outside it. Both use two conventions:

- **plane root** = `config.ROOT`; **state dir** = `config.STATE_DIR` = `<plane>/.charter/`
  unless `$CHARTER_HOME` is set, in which case it is that path verbatim
  (`charter/config.py:791`, `charter/config.py:99`).
- "**IF ABSENT**" = charter writes only the key(s) it owns, only when they are not already
  there, and never repairs or reformats a file it cannot parse.

No real vault content was read for this section. Shapes come from the writers in
`charter/secrets/*` plus a throwaway plane generated for the survey, whose only value is the
literal `fixture-not-a-secret`.

### `vaults.json` (plane root — the SHARED half)

- **Format:** JSON object.
- **Status:** **stable** — committed to the plane's git, hand-editable, read by every
  charter process (doctor, statusline, hooks) and written by `charter vault add --share`.
- **Written by:** `charter/secrets/registry.py:215` (`save_shared`) → `_write`
  (`charter/secrets/registry.py:173`), from `add_vault`/`remove_vault`
  (`charter/secrets/registry.py:304`, `charter/secrets/registry.py:347`). Commands:
  `charter vault add <name> … --share`, `charter vault remove <name>`.
- **Read by:** `charter/secrets/registry.py:65` (`load_shared`) → `load_registry`
  (`charter/secrets/registry.py:95`); `charter/secrets/registry.py:134`
  (`shared_files_outside_plane`, doctor); `charter/secrets/registry.py:119`
  (`malformed_shared`).
- **Path:** `charter/config.py:774` (`SHARED_VAULTS = root / "vaults.json"`).
- **Git:** committed (nothing in `_GITIGNORE_BASELINE`, `charter/commands.py:1087`,
  ignores it — only `/.charter/` is ignored).
- **Encoding:** `json.dump(doc, f, indent=2, ensure_ascii=False)` + one trailing `"\n"`
  (`charter/secrets/registry.py:197`-`198`). Key order = **insertion order**, never
  sorted. Mode **0644**, set on the descriptor with `fchmod` before the truncate
  (`charter/secrets/registry.py:188`-`193`, `charter/secrets/registry.py:215`). Not atomic
  (no tmp+rename), no locking. Parent created with `config.private_mkdir`
  (`charter/secrets/registry.py:187`).

| Field | Type | Required / default | Meaning | Status | Source |
|---|---|---|---|---|---|
| `vaults` | object | defaulted to `{}` on read | name → entry | stable | `charter/secrets/registry.py:60` |
| `vaults.<name>` | object | — | one vault. A non-object entry is dropped from the merged view and reported | stable | `charter/secrets/registry.py:92` |
| `vaults.<name>.provider` | string | required | `plain-file` \| `reference` \| `1password` | stable | `charter/secrets/registry.py:39`, `:245` |
| `vaults.<name>.persona` | string \| null | written always, `null` when no `--persona` | persona tag | stable | `charter/secrets/registry.py:299` |
| `vaults.<name>.config` | object | written always (may be `{}`) | provider config, merged per key over the local half | stable | `charter/secrets/registry.py:113` |

`config` keys (all providers share the namespace):

| Key | Type | Written when | Meaning | Status | Source |
|---|---|---|---|---|---|
| `file` | string | `plain-file` and `reference` always; other providers only with `--file` | vault file; **relative to the plane root when inside it, else absolute** | stable | `charter/commands_secrets.py:141`, `:147`, `:149`; `charter/commands_secrets.py:34` (`_portable_file`); resolved by `charter/secrets/base.py:40` |
| `op-vault` | string | `--provider 1password` (required) | 1Password vault name | stable | `charter/commands_secrets.py:177`, read `charter/secrets/onepassword.py:134` |
| `op-item` | string | `--op-item` only | item title; default `charter-<vault>` | stable | `charter/commands_secrets.py:179`, read `charter/secrets/onepassword.py:149` |
| `account` | string | `--account` | 1Password account pin — **LOCAL_ONLY, never written to the shared half** | stable | `charter/secrets/registry.py:50`, `:298`, `:317` |
| `env` | object `{TARGET: SOURCE}` | `--env TARGET=SOURCE` / `--token-env X` | env var NAMES only (e.g. `{"OP_SERVICE_ACCOUNT_TOKEN": "OP_ACME_TOKEN"}`); never a value | stable | `charter/commands_secrets.py:188`, `charter/commands_secrets.py:80`; read `charter/secrets/base.py:291` |
| `version` | string | hand-written only | `browser://` resolver's npx package version | stable | `charter/secrets/reference.py:104` |

Legacy spellings `op_vault` / `op_item` are still read (`charter/secrets/onepassword.py:134`,
`:149`) and never written.

### `.charter/vaults.json` (the LOCAL half)

- **Format:** JSON object, same schema as above.
- **Status:** **stable** — hand-editable, and read by other processes (statusline counts it
  directly: `charter/statusline.py:799`; doctor; every `charter secret` call).
- **Written by:** `charter/secrets/registry.py:209` (`save_registry`), from `add_vault`
  without `--share` (`charter/secrets/registry.py:331`), from `--share` when local-only
  keys survive (`charter/secrets/registry.py:321`-`327`), and `remove_vault`
  (`charter/secrets/registry.py:350`). Commands: `charter vault add`, `charter vault
  remove`, `charter persona create --vault` (`charter/commands_persona.py:141`).
- **Read by:** `charter/secrets/registry.py:69` (`load_local`), `:95` (`load_registry`),
  `:228` (`scope_of`); `charter/statusline.py:799`.
- **Path:** `charter/config.py:794`.
- **Git:** gitignored via the `/.charter/` line in `_GITIGNORE_BASELINE`
  (`charter/commands.py:1094`, written by `_ensure_gitignore`, `charter/commands.py:1116`).
- **Encoding:** identical writer, mode **0600** (`charter/secrets/registry.py:209`).
- **Merge rule (the app must reproduce it):** shared is the base, local is layered **per
  field**; `config` is dict-updated key by key, other fields overwrite when not `None`
  (`charter/secrets/registry.py:104`-`116`). A `--share` publish REDUCES the local entry to
  its `LOCAL_ONLY_KEYS`, or deletes it (`charter/secrets/registry.py:316`-`327`).
  `scope_of` reports `shared` / `local` / `both` (`charter/secrets/registry.py:222`).

### `.charter/vaults/` (directory)

- **Status:** **stable** — the default home for plain-file and reference vault files, named
  by `config.VAULTS_DIR` (`charter/config.py:799`) and by the guard
  (`charter/hooks.py:553`).
- **Modes:** created 0700, **every level charter itself creates** chmod'ed to 0700
  (`charter/secrets/base.py:61` → `charter/config.py:190` `private_mkdir`). A directory
  that already exists is left as found and merely *reported*
  (`charter/secrets/base.py:105` `loose_dirs`, rendered by `charter/secrets/base.py:195`).
- Measured on a plane generated for this survey (modes as charter writes them, which is
  not what a git checkout of a fixture reproduces): `.charter` `drwx------`, `.charter/vaults` `drwx------`,
  every file inside `-rw-------`.
- File names: `<vault name>.json` and `<vault name>.meta.json` by default
  (`charter/commands_secrets.py:141`, `charter/secrets/plain_file.py:165`). Any other path
  is legal via `--file`, absolute included (`charter/secrets/base.py:40`).

Live-plane check (names and modes only, no contents): the real plane has
`.charter/vaults.json` and a `.charter/vaults/` directory of `<name>.json` /
`<name>.meta.json` files, all `0600`, matching the fixture.

### `.charter/vaults/<name>.json` — plain-file vault

- **Format:** flat JSON object, `key → secret value` (values may be multi-line).
- **Status:** **stable** — the operator may hand-author it, and the file is the vault.
- **Written by:** `charter/secrets/plain_file.py:97` (`_save`) →
  `charter/secrets/plain_file.py:42` (`_write_private`). Commands: `charter secret set`,
  `charter secret rm`.
- **Read by:** `charter/secrets/plain_file.py:29` (`_load`) — `get`, `keys`, `health`,
  `ages`; `charter/doctor.py` and the status line through `health()`.
- **Git:** default path gitignored via `/.charter/`. A `--file` path inside the plane that
  git does NOT ignore is refused at registration (`charter/commands_secrets.py:159`-`170`,
  using `git check-ignore`).
- **Encoding:** `json.dump(payload, f, indent=2, ensure_ascii=False)` + trailing newline
  (`charter/secrets/plain_file.py:91`-`92`). Insertion order (i.e. previous file order,
  then newly-set keys appended). Mode 0600 settled on the **descriptor** and read back
  before any byte is written; a mode with any of `0o077` set is refused and nothing is
  written (`charter/secrets/plain_file.py:72`-`87`). Not atomic (in-place truncate), no
  locking. `get` first tightens a loose mode (`charter/secrets/plain_file.py:137`); the
  read-only paths report instead of repairing (`charter/secrets/base.py:214` `mode_note`).

Shape with placeholder values:

```json
{
  "API_TOKEN": "fixture-not-a-secret",
  "KUBECONFIG": "fixture-not-a-secret\nline two\n"
}
```

### `.charter/vaults/<name>.meta.json` — rotation sidecar

- **Format:** JSON object `key → {"set_at": "YYYY-MM-DD"}`.
- **Status:** **stable** — read by `charter secret audit` in a later process; holds no
  values, only key names and dates.
- **Written by:** `charter/secrets/plain_file.py:148` (`set`) and `:158` (`delete`) via the
  same `_write_private` (`charter/secrets/plain_file.py:177`).
- **Read by:** `charter/secrets/plain_file.py:167` (`_load_meta`), `:182` (`ages`) →
  `charter/commands_secrets.py:496` (`cmd_secret_audit`).
- **Name derivation:** `<vault file stem> + ".meta.json"` in the vault file's own directory
  (`charter/secrets/plain_file.py:165`) — so a `--file` outside the plane puts the sidecar
  outside too.
- **Git / encoding:** as the vault file (0600, indent 2, trailing newline). Date is
  `datetime.date.today().isoformat()` — **local date, no timezone**
  (`charter/secrets/plain_file.py:148`).

```json
{ "API_TOKEN": { "set_at": "2026-09-17" } }
```

### `.charter/vaults/<name>.json` — reference vault (same path, different content)

- **Format:** flat JSON object, `key → reference URI`.
- **Status:** **stable** — designed to be committed by a team (it holds no values) and
  hand-edited.
- **Written by:** `charter/secrets/reference.py:191` (`_save`). Commands: `charter secret
  set <vault> <key> --value 'op://…'`, `charter secret rm`.
- **Read by:** `charter/secrets/reference.py:179` (`_load`) — `get`, `keys`, `health`,
  `reference_for`.
- **Encoding — differs from the plain-file writer and this matters to a byte-identical
  implementation:** `json.dumps(data, indent=2, sort_keys=True) + "\n"` written with
  `Path.write_text`, then `os.chmod(p, 0o600)` **after** the write
  (`charter/secrets/reference.py:194`-`195`). So: **sorted keys** here, insertion order in
  the plain-file vault; and the mode is applied after the content, not before.
- **Git:** default path is under `.charter/` and therefore ignored; a team that commits
  these points `--file` at a tracked path, which is allowed for this provider (the
  unignored-path refusal is `plain-file` only, `charter/commands_secrets.py:159`).

```json
{
  "DEPLOY_TOKEN": "op://Engineering/deploy/token",
  "DB_PASSWORD": "vault://secret/data/app#DB_PASSWORD"
}
```

### Secret reference syntax

Registered schemes: `charter/secrets/reference.py:112`
(`_RESOLVERS = {"op", "vault", "browser"}`). A value that is not a string, or whose scheme
is not in that map, is not a reference (`charter/secrets/reference.py:130` `scheme_of`).

| Syntax | Resolved with | Validation | Source |
|---|---|---|---|
| `op://<vault>/<item>/<field>` | `op read --no-newline <uri>` | netloc present and ≥2 path segments | `charter/secrets/reference.py:49` |
| `vault://<path>#<FIELD>` | `vault kv get -field=<FIELD> <path>` | path and fragment both non-empty | `charter/secrets/reference.py:58` |
| `browser://<session>/<source>/<name>` | `npx …` via `charter/browser.py` | `source` ∈ `browser.SESSION_SOURCES`; key is the rest of the path verbatim | `charter/secrets/reference.py:69` |

A resolved value has exactly one trailing `\n` stripped
(`charter/secrets/reference.py:277`). Resolution is bounded by
`RESOLVE_TIMEOUT = 60.0` (`charter/secrets/reference.py:127`).

**Consumption syntaxes** (CLI surface, not files, but they are what a harness's command
line carries): `--env NAME=<key>`, `--file ENVVAR=<key>` (0600 temp file, prefix
`charter-<vault>-<key>-`), `--dotenv ENVVAR=NAME:key` (0600 temp file, prefix
`charter-<vault>-dotenv-`, entries sharing an ENVVAR merged in flag order)
— `charter/commands_secrets.py:1060`, `:1078`, `:1106`, `:1123`.

### `.charter/fingerprint.key`

- **Format:** raw binary, exactly 32 bytes (`KEY_BYTES`, `charter/secrets/fingerprint.py:63`).
- **Status:** **stable** — key material. Losing it silently changes the `fp:` values this
  plane prints, and a charter process computing one reads it. `charter/hooks.py:554` names
  the file among the paths a harness tool call is refused; that bounds what an agent does
  through the harness, not what a process on the machine can open. Deleting it is not free:
  it is regenerated on next use, and `fp:` values printed before it stop matching.
- **Written by:** `charter/secrets/fingerprint.py:105`-`114` (`_key`), lazily on first use.
  Created only by a command that masks a value — `charter secret get` (without `--reveal`),
  `charter secret set` does **not** create it (measured: after `secret set` the file was
  absent; after `secret get` it appeared, 32 bytes, `-rw-------`).
- **Read by:** `charter/secrets/fingerprint.py:91` (`_key`) → `fingerprint()`
  (`charter/secrets/fingerprint.py:122`) → `masked()` (`:166`) →
  `charter/commands_secrets.py:604`.
- **Path:** `config.STATE_DIR / "fingerprint.key"` (`charter/secrets/fingerprint.py:65`,
  `:76`). **Git:** ignored with the rest of `.charter/`.
- **Encoding:** `os.urandom(32)`, no newline; 0600 fchmod'ed and read back before the write,
  refusing on any `0o077` bit; a file of the wrong length is regenerated
  (`charter/secrets/fingerprint.py:94`, `:111`).
- **Fingerprint format on output:** `fp:` + first 12 hex chars of
  `HMAC-SHA256(key, value.encode("utf-8"))` (`charter/secrets/fingerprint.py:134`). The
  masked line is `<size band> · fp:<12 hex>`, or just the band when no key can be made
  (`charter/secrets/fingerprint.py:169`). Size bands: `empty`, `1–15 bytes`, then
  power-of-two bands `16–31`, `32–63`, … up to `1024+ bytes`, counted in UTF-8 bytes, with
  an **en dash** (`charter/secrets/fingerprint.py:155`-`163`).

### 1Password provider — not a file, but a shape another implementation must match

One item per charter vault, its concealed fields are the secrets
(`charter/secrets/onepassword.py:552` `_write`):

```json
{"title": "charter-<vault>", "category": "PASSWORD",
 "tags": ["charter", "charter:<vault>"],
 "fields": [{"id": "<existing id or key>", "label": "<key>",
             "type": "CONCEALED", "value": "…"}]}
```

Title default `charter-<vault>` (`charter/secrets/onepassword.py:149`), tag literals from
`_TAG = "charter"` / `_CATEGORY = "PASSWORD"` (`charter/secrets/onepassword.py:99`, `:102`),
vault tag `charter:<vault>` (`charter/secrets/onepassword.py:159`), fields sorted by key
(`charter/secrets/onepassword.py:567`). Reads go through `op read --no-newline
op://<op-vault>/<op-item>/<key>` (`charter/secrets/onepassword.py:223`). Legacy
one-item-per-key titles `charter-<vault>-<key>` are detected and reported, never written
(`charter/secrets/onepassword.py:156`, `:581`).

### Guarded paths

`charter/hooks.py:553` — `_VAULT_PATH_RE` matches `.charter/vaults…`, `.charter/browser`,
`.charter/active-`, `.charter/fingerprint`, case-insensitively and in every separator
spelling; `charter/toolgate.py:276` guards `config.STATE_DIR` and `config.VAULTS_DIR` plus
each registered vault's own `file` (`charter/toolgate.py:301`, `:322`). Observed: a
`cat .charter/vaults/<name>.json` tool call was denied by charter's own PreToolUse guard,
and a differently-shaped shell command reading the same path in another session was not.
The guard reads the shape of a tool call, which is what it says of itself (`docs/hooks.md`,
"When a guard is wrong") — so this section records the paths it names, not a boundary around
the bytes. A rebuild that reimplements the guard reproduces the matching, and inherits the
same bound.

---

## Files charter writes that a harness reads

### 2a. Inside the plane

### `<plane>/.claude/settings.json`

- **Format:** JSON object (Claude Code's own schema; charter owns three key paths).
- **Status:** **stable** — committed, operator-owned, read by Claude Code itself.
- **Written by (each key IF ABSENT, never a repair):**
  - `hooks.PreToolUse[]` ← `_GUARD_HOOK` (`charter/commands.py:1186`), by
    `charter/commands.py:1233` (`_ensure_guard_hook`), from `charter init` /
    `charter reinit`. **Skipped entirely when an enabled charter plugin already dispatches
    `charter hook pretooluse`** (`charter/commands.py:1258` via
    `charter/commands.py:1197` → `doctor._plugin_declaring_guard`, which always asks about
    `~/.claude`, not `$CLAUDE_CONFIG_DIR`).
  - `env.CHARTER_HARNESS = "claude-code"` ← `charter/commands.py:2256`
    (`ensure_env_var`), called from `charter/harness/claude_code.py:335` (`wire`) through
    `_wire_harnesses` (`charter/commands.py:2296`).
  - `permissions.ask[]` / `permissions.allow[]` ← `charter/commands.py:1686`
    (`add_permission_rule`), from `charter guard ask|allow` and, for the one rule `init`
    writes, `ensure_handoff_gate` (`charter/commands.py:2098`, pattern
    `charter/commands.py:1398`).
  - `enabledPlugins` is **written by the `claude` CLI**, not by charter (see 2b).
- **Read by:** Claude Code; charter reads it back at `charter/commands.py:1636`
  (`_load_settings`), `charter/harness/claude_code.py:402`, `charter/commands.py:2139`
  (`_rules_in`), `charter/doctor.py`.
- **Git:** committed — explicitly NOT ignored (`charter/commands.py:1098`-`1099`).
- **Encoding:** parsed **as Claude Code parses it** (`NaN`/`Infinity` rejected) —
  `charter/commands.py:1652` → `doctor._json_as_claude_code_parses`; an unparseable file is
  refused whole, never rewritten. Re-dumped through `_json_style`
  (`charter/commands.py:1320`), which copies the file's existing indent and separators, and
  the trailing newline is preserved only if the file had one
  (`charter/commands.py:1305`-`1306`, `charter/commands.py:2291`). `add_permission_rule`
  always appends `"\n"` (`charter/commands.py:1741`). A fresh file is
  `json.dumps(..., indent=2) + "\n"` (`charter/commands.py:1265`).

| Key path charter owns | Value | Merge rule | Status | Source |
|---|---|---|---|---|
| `hooks.PreToolUse[]` | `{"matcher": "Bash", "hooks": [{"type": "command", "command": "charter hook pretooluse", "timeout": 10}]}` | append once; skipped if the plugin declares it | stable | `charter/commands.py:1186` |
| `env.CHARTER_HARNESS` | `"claude-code"` | set IF ABSENT; an `env` that is not an object is left alone | stable | `charter/commands.py:2279` |
| `permissions.ask[]` | e.g. `"Bash(charter handoff *)"` | append IF ABSENT; wrong-typed block ⇒ `malformed`, no write | stable | `charter/commands.py:1727`-`1737` |
| `permissions.allow[]` | e.g. `"Bash(gh pr view *)"` | same | stable | `charter/commands.py:1832` |
| `enabledPlugins."charter@charter"` | `true` | written by `claude plugin install`, mirrored by charter into workspaces | stable | `charter/harness/claude_code.py:53` |

**Rule syntax** (`charter/commands.py:1367` `_as_rule`): a bare command becomes
`Bash(<pattern>)`; a string already matching `Tool(...)` for
`_RULE_TOOLS` (`charter/commands.py:1345`), a bare tool name, or `mcp__[A-Za-z0-9_-]+`
(`charter/commands.py:1354`) is written verbatim; an `mcp__…` pattern with a wildcard or
arguments raises `UnexpressibleRule` and nothing is written.

Measured after `init` + `guard ask 'terraform apply *'`:

```json
{ "env": {"CHARTER_HARNESS": "claude-code"},
  "permissions": {"ask": ["Bash(charter handoff *)", "Bash(terraform apply *)"]},
  "enabledPlugins": {"charter@charter": true} }
```
(no `hooks` block — the plugin install ran first, which is `init`'s deliberate order,
`charter/commands.py:2822`.)

### `<plane>/.claude/settings.local.json`

- **Format / status:** as above, **stable** (Claude Code reads it, at the session directory
  **and at the git root**, measured on 2.1.267 — `charter/harness/claude_code.py:76`-`95`).
- **Written by:** `charter/commands.py:1686` with `local=True`
  (`charter/commands.py:1720`), from `charter guard ask|allow --local`. Path constant
  `charter/commands.py:1766`.
- **Read by:** Claude Code; charter via `_load_json_settings`
  (`charter/commands.py:1666`), `charter/harness/claude_code.py:403`.
- **Git:** gitignored — baseline line `/.claude/settings.local.json`
  (`charter/commands.py:1771`), also backfilled at the moment a `--local` rule is written
  (`charter/commands.py:1774`).
- **Encoding:** identical writer. Fixture: `{"permissions": {"allow": ["Bash(gh pr view *)"]}}`.

### `<plane>/opencode.json`

- **Format:** JSON object (opencode's schema).
- **Status:** **stable** — committed, read by opencode at the repository root.
- **Written by:** `charter/harness/opencode.py:1183` (`_apply_rule`) → written at
  `charter/harness/opencode.py:1279`; reached from `charter guard ask|allow` (never
  `--local`, which opencode answers `unsupported`, `charter/harness/opencode.py:1171`).
- **Read by:** opencode; charter at `charter/harness/opencode.py:479`
  (`_configured_plugins`, for the foreign-plugin report).
- **Git:** committed (nothing ignores it).
- **Encoding:** `json.dumps(doc, indent=2) + "\n"` (`charter/harness/opencode.py:1266`) —
  **no `_json_style` equivalent**, so an existing file is re-dumped at indent 2.
  Unparseable ⇒ `malformed`, nothing written.
- **Key paths charter owns:** `permission.<tool>.<glob> = "ask"|"allow"`, or for the five
  `FLAT_ONLY_PERMISSIONS` (`charter/harness/opencode.py:142`) `permission.<tool> =
  "ask"|"allow"` and only when the glob is `*` (anything else is `unsupported`,
  `charter/harness/opencode.py:1250`). Pattern translation
  (`charter/harness/opencode.py:992` `ask_rule`): `mcp__<server>__<tool>` →
  (`<server>_<tool>`, `*`); `Tool(pattern)`/`tool(pattern)` → (`<opencode tool id>`,
  `pattern`) using `TOOL_NAMES` (`charter/harness/opencode.py:47`); anything else →
  (`bash`, pattern).
- Fixture: `{"permission": {"bash": {"charter handoff *": "ask", "terraform apply *": "ask"}}}`.

### `<plane>/.gitignore` (the lines charter owns)

- **Status:** **stable** — committed, read by git and by the operator.
- **Written by:** `charter/commands.py:1116` (`_ensure_gitignore`, `init`) from the baseline
  at `charter/commands.py:1087`; backfilled additively by
  `charter/commands.py:1774` (`--local` rules) and `charter/commands.py:1806`
  (`charter reinit`, `/charter.local.toml`), both through `util.append_gitignore`
  (`charter/util.py:472`).
- **Lines charter owns:** `/workspaces/*/*`, `!/workspaces/.gitkeep`, `/.charter/`,
  `/.claude/settings.local.json`, `/charter.local.toml`, plus the Python/OS block in the
  baseline. Presence is tested per line (whole-line, except `.charter/` which is a substring
  test) — `charter/commands.py:1133`-`1141`. Never removed or reordered.
  (The managed live-workspace block `# >>> charter live workspaces …` is
  `charter/workspace.py:1338` — the workspace area's.)

### Generated harness layer in `workspaces/<ws>/` and in clones

One generic materialiser (`charter/workspace.py:2737` `_materialise`), driven by each
harness's `workspace_files` / `checkout_files` (`charter/workspace.py:2020`
`_harness_files`), refusing any relative path that escapes the base
(`charter/workspace.py:2044`-`2047`).

#### `workspaces/<ws>/.claude/settings.json` (generated)

- **Status:** **stable** — read by Claude Code for a chat whose cwd is the workspace
  directory (project settings do not walk up).
- **Written by:** `charter/harness/claude_code.py:447` (`workspace_files`) →
  `charter/workspace.py:2649` (`wire_harnesses`), called from `workspace.scaffold`/`ensure`
  on every launch, from `charter workspace reinit`, and from `charter guard ask` via
  `charter/commands.py:1909` (`_mirror_into_workspaces`).
- **Content:** exactly the plane's own `enabledPlugins` and `env` keys
  (`WORKSPACE_KEYS`, `charter/harness/claude_code.py:53`), plus `permissions` filtered to
  `ask`/`deny` only (`RESTRICTIVE_BUCKETS`, `charter/harness/claude_code.py:67`;
  `allow` never travels). Key order: the two mirrored keys in `WORKSPACE_KEYS` order,
  `permissions` appended last (`charter/harness/claude_code.py:484`).
- **Encoding:** `json.dumps(doc, indent=2) + "\n"` (`charter/harness/claude_code.py:485`);
  written whole through tmp+fsync+`os.replace` (`charter/workspace.py:2874` `_write_whole`).
  Empty plane settings ⇒ **no file at all**.
- **Git:** inside `workspaces/<ws>/`, already ignored by `/workspaces/*/*`.

#### `workspaces/<ws>/<repo>/.claude/settings.json` and `.claude/settings.local.json` (generated, in a clone)

- Same generator; a clone additionally gets `checkout_files`
  (`charter/harness/claude_code.py:487`): `{"permissions": {<ask/deny from the plane's
  LOCAL file>}}` as `json.dumps(..., indent=2) + "\n"`
  (`charter/harness/claude_code.py:499`). `allow` never travels, which is why the fixture
  clone got no local file.
- `.claude/settings.local.json` is also **co-written by Claude Code itself** ("don't ask
  again"), so it is listed in `cowritten` (`charter/harness/claude_code.py:387`) and is
  never rewritten once the harness has edited it (`charter/workspace.py:3336`).

#### Mirrored plane paths in a clone

`charter/workspace.py:2077` (`_inherited_files`) copies, 1:1 as text, every registered
harness's `inherited_paths`: `.claude/agents`, `.claude/skills`
(`charter/harness/claude_code.py:169`), `.opencode/agent`
(`charter/harness/opencode.py:831`), `.codex/skills`
(`charter/harness/codex.py:236`). **`CLAUDE.md` / `AGENTS.md` are deliberately never
generated or mirrored** (`charter/harness/base.py:245`-`249`,
`charter/harness/claude_code.py:160`); charter writes no project-instructions file.

#### `<workspace-or-checkout>/.charter-generated`

- **Format:** JSON object, `relative path → sha256 hex` (a **list** of hexes while a write
  is pending) — `charter/workspace.py:2440` (`_recorded`), `charter/workspace.py:2806`.
- **Status:** **stable** — it is the ownership record two processes (a launch and `doctor`)
  read, and deleting it makes charter treat every generated file as foreign: nothing is
  overwritten, exclude lines are dropped, `doctor` reports the layer as not charter's.
- **Written by:** `charter/workspace.py:2933` (`_publish_marker`) →
  `_write_whole` with `json.dumps(marker, indent=2) + "\n"`
  (`charter/workspace.py:2946`). Removed when it would name nothing (`:2948`).
- **Read by:** `charter/workspace.py:2212` (`_read_marker_at`) — the next launch, `doctor`,
  `charter workspace reinit`, `unwire_guest`.
- **Git:** never committed; in a clone it is hidden via `info/exclude`. A marker git
  **tracks** is distrusted whole (`charter/workspace.py:2176`), as is one holding an
  absolute/`..` key (`charter/workspace.py:2155`).
- **Digest:** `sha256(text)` of the text charter wrote, hex (`charter/workspace.py:1938`).
- Fixture: `{ ".claude/settings.json": "08dcdf9e…" }`.

#### `<clone>/.git/info/exclude` — charter's managed block

- **Status:** **stable** — read by git in a repo charter does not own; the operator sees it.
- **Written by:** `charter/workspace.py:3876` (`_register_excludes`) →
  `_replace_block` (`charter/workspace.py:3404`) → `_write_whole`. Reached from
  `wire_guest` (`charter/workspace.py:4059`), i.e. every launch, `charter clone`
  (`charter/commands.py:483` `_wire_clones`) and `charter workspace reinit`.
- **Shape** (`charter/workspace.py:3384` `_exclude_block`): begin marker
  `# >>> charter (generated layer — `charter workspace reinit`) >>>`
  (`charter/workspace.py:3114`), the three `_EXCLUDE_NOTE` comment lines
  (`charter/workspace.py:3118`), one `/`-anchored line per generated path in
  `_shared_rels` order, the unanchored temp glob `.charter-generated.*.tmp`
  (`charter/workspace.py:3381`), then `# <<< charter <<<` (`charter/workspace.py:3115`),
  and a trailing newline. Idempotent: the block is replaced, never appended; an
  unterminated block runs to EOF and is replaced whole. A file with no charter block and
  nothing to add is handed back byte for byte (`charter/workspace.py:3424`-`3425`).
- The block, verbatim, as charter writes it:
  `/.claude/settings.json`, `/.charter-generated`, `.charter-generated.*.tmp`.
- **Temp files:** every write in a checkout goes through
  `.charter-generated.<pid>.<hex12>.tmp` beside the target, fsynced, then `os.replace`,
  keeping the replaced file's mode (`charter/workspace.py:2913`-`2924`).

### 2b. Outside the plane (machine-global)

### `~/.config/opencode/plugin/charter.ts` (`$XDG_CONFIG_HOME` honoured)

- **Format:** TypeScript module, generated from `_SHIM_TEMPLATE`
  (`charter/harness/opencode.py:244`, rendered at `charter/harness/opencode.py:403`).
- **Status:** **stable** — opencode loads it; it is what sets `$CHARTER_HARNESS` and routes
  every tool call to `charter hook <handler>`.
- **Written by:** `charter/harness/opencode.py:626` (`ensure_shim`, create-only) and
  `charter/harness/opencode.py:588` (`refresh_shim`, which replaces a shim stamped with an
  **older** charter version), from `charter/harness/opencode.py:956` (`wire`) via
  `_wire_harnesses` (`init`, `reinit`, `charter harness install`), and from `upgrade`
  (`charter/harness/opencode.py:921`).
- **Read by:** opencode. Charter compares it **byte for byte** to `SHIM_BYTES`
  (`charter/harness/opencode.py:417`, `:441`) and refuses to overwrite anything it cannot
  vouch for (`charter/harness/opencode.py:537` `unvouched`).
- **Git:** outside every repo.
- **Encoding:** UTF-8 bytes written with `write_bytes`
  (`charter/harness/opencode.py:622`, `:638`). First line is the stamp
  `// charter-version: <version>` (`charter/harness/opencode.py:401`). The embedded tables
  are `json.dumps(..., indent=2, sort_keys=True)` for `TOOL_NAMES`, `PRE_HOOKS`,
  `POST_HOOKS` and plain `json.dumps` for `DEFAULT_PRE_HOOK` / `EFFECTFUL_TOOLS`
  (`charter/harness/opencode.py:405`-`409`). **The file's bytes therefore change with every
  charter version** and with any change to those four tables.
- **Realm rule:** anything else in `plugin/` is foreign and reported
  (`charter/harness/opencode.py:501`), because opencode loads the whole directory into one
  module realm.

### `~/.config/opencode/command/charter.md`

- **Format:** Markdown with YAML frontmatter (`description:`), body embeds
  `` !`echo '{}' | charter statusline` ``.
- **Status:** **stable** — opencode reads it as the `/charter` command.
- **Written by:** `charter/harness/opencode.py:984` (`wire`), **create-only** (never
  refreshed). Constant: `charter/harness/opencode.py:225` (`COMMAND`), path
  `charter/harness/opencode.py:221`.
- **Git:** outside every repo. **Encoding:** the constant verbatim, trailing newline
  included.

### `~/.config/opencode/charter-context.md`

- **Format:** Markdown; an HTML comment header then `hooks.context_block(None)`.
- **Status:** **stable** — opencode reads it (it is named in `instructions`), and it is the
  substitute for a SessionStart hook.
- **Written by:** `charter/harness/opencode.py:642` (`write_context`) — **always
  overwritten**, the one generated file charter repairs; called from `wire`
  (`charter/harness/opencode.py:986`).
- **Encoding:** `"<!-- Generated by charter. Do not edit: rewritten whenever the plane's
  state changes. -->\n\n" + body.strip() + "\n"`, or `_No control-plane context._` when the
  body is empty (`charter/harness/opencode.py:655`-`657`). **Content is plane state** —
  active workspace, todos, personas — so it is nondeterministic by design.

### `~/.config/opencode/opencode.json`

- **Status:** **stable** — opencode's own global config.
- **Written by:** `charter/harness/opencode.py:660` (`ensure_instructions`): appends the
  **absolute** path of `charter-context.md` to `instructions`, IF ABSENT
  (`charter/harness/opencode.py:683`). Unparseable or wrong-typed ⇒ `malformed`, nothing
  written.
- **Encoding:** `json.dumps(doc, indent=2) + "\n"` (`charter/harness/opencode.py:685`).
- Fixture: `{"instructions": ["<abs path>/charter-context.md"]}`.

### `~/.codex/config.toml` (`$CODEX_HOME` honoured)

- **Format:** TOML; charter appends **whole tables or nothing**.
- **Status:** **stable** — Codex reads it; it is machine-wide.
- **Written by:** `charter/harness/codex.py:100` (`install`) → `p.write_text(raw + sep +
  _block())` (`charter/harness/codex.py:141`). **Only** from `charter harness install
  codex` / a Codex profile (`charter/commands_harness.py:169`); `CodexHarness.wire` writes
  nothing on purpose (`charter/harness/codex.py:295`).
- **Read by:** Codex; charter at `charter/harness/codex.py:126` and
  `charter/wiring.py:506` (`_codex`).
- **Block written** (`charter/harness/codex.py:82` `_block`), appended with a separating
  newline only when the file does not end in one (`charter/harness/codex.py:140`):

```toml

[shell_environment_policy]
set = { CHARTER_HARNESS = "codex" }
```

- **Refusals:** a config already declaring `hooks.<event>` (other than `hooks.state`) ⇒
  `doubled`, nothing written (`charter/harness/codex.py:132`-`136`); an existing
  `shell_environment_policy` ⇒ `present`, nothing written (`charter/harness/codex.py:137`).
- **Keys charter READS but never writes:** `plugins."charter@charter".enabled`,
  `hooks.state."charter@charter:hooks/hooks.json:<event>:<group>:<hook>".trusted_hash`
  (`charter/wiring.py:634` `_codex_marks`, `charter/wiring.py:92` `CODEX_TRUST_PREFIX`).

### Claude Code's own files — charter does NOT write them

`~/.claude/plugins/installed_plugins.json`, `~/.claude/plugins/known_marketplaces.json`,
`~/.claude/settings.json` and `~/.claude.json` are written by the `claude` binary. Charter
shells out — `claude plugin marketplace add diazoxide/charter` then `claude plugin install
charter@charter --scope project -y` (`charter/plugincache.py:335`-`336`,
`charter/plugincache.py:112`, `:131`) — from `Harness.provision`
(`charter/harness/claude_code.py:338`), i.e. only `charter init` and `charter doctor
--fix`. The module docstring states the rule explicitly: *"Everything here talks to `claude
plugin … --json`, never to Claude Code's files"* (`charter/plugincache.py:27`-`32`).
Charter reads them only as **mtime/size stamps** for its wiring cache
(`charter/wiring.py:775` `_claude_stamps`).

Measured in a throwaway `$HOME` after `charter init` (written by `claude`, shape recorded here
because a Rust implementation will read the same entries through the CLI):

| File | Entry charter cares about | Source |
|---|---|---|
| `plugins/installed_plugins.json` | `plugins["charter@charter"][] = {scope, installPath, version, installedAt, lastUpdated, gitCommitSha, projectPath}` | `charter/plugincache.py:196` (`_our_entries`), `:257` (`covers`) |
| `plugins/known_marketplaces.json` | `charter.source = {source: "github", repo: "diazoxide/charter"}`, `installLocation` | `charter/plugincache.py:456` (`marketplace_clone`) |
| `~/.claude/settings.json` | `extraKnownMarketplaces.charter` — written by `claude`, never by charter | `charter/commands.py:1240` (names it as a key charter must not touch) |
| `~/.claude.json` | `mcpServers`; deliberately NOT stamped, because the probe itself writes this file | `charter/harness/claude_code.py:221`, `charter/wiring.py:822` |

Config-folder resolution a second implementation must copy exactly:
`CLAUDE_CONFIG_DIR ?? ~/.claude`, NFC-normalised, **empty value kept**
(`charter/harness/claude_code.py:192`); but for `.claude.json` it is
`CLAUDE_CONFIG_DIR || ~`, un-normalised, with a legacy `<config home>/.config.json`
winning while it exists (`charter/harness/claude_code.py:221`).

### The shipped plugin's `hooks/hooks.json`

- **Format:** JSON, `{"hooks": {<Event>: [{"matcher": …, "hooks": [{"type": "command",
  "command": "charter hook <handler> --plugin-version X.Y.Z", "timeout": N}]}]}}`.
- **Status:** **stable** — it is the file Claude Code and Codex dispatch from, and Codex
  numbers its trust-ledger keys `<event>:<group>:<hook>` against the **installed copy**
  (`charter/wiring.py:573` `_codex_guard_keys`, `charter/wiring.py:613`
  `_guard_positions`). It lives in the charter repo (release artifact), not in a plane.
- **Read by:** the harness; charter at `charter/wiring.py:601` (the installed copy under
  `<CODEX_HOME>/plugins/cache/charter/charter/<version>/hooks/hooks.json`) and
  `charter/hooks.py:8986` (`--plugin-version` skew check).
- At `50d31dc`: SessionStart 1, UserPromptSubmit 1, PreToolUse 4, PostToolUse 5, Stop 1,
  SubagentStop 1 groups.

### 2c. Git config charter sets

- **Status:** **stable** — git reads it; it is per-repo `.git/config`.
- **Written by:** `charter/gitpolicy.py:170` (`apply`) → `git config --local …`
  (`charter/gitpolicy.py:190`, `:195`). Callers: `charter clone`
  (`charter/commands.py:615`), `init --clone-this-repo` (`charter/commands.py:2558`),
  `charter git-policy --apply` (`charter/commands.py:3301`).
- **Scope:** `--local` only — never `--global`/`--system` (`charter/gitpolicy.py:9`-`14`).
- **Keys, resolved per repo from its own forge** (`charter/gitpolicy.py:111` `forge_for`,
  default GitLab when there is no `origin`):

| Key | Value | Source |
|---|---|---|
| `credential.helper` | `!<cli> auth git-credential` (`gh` or `glab`) | `charter/gitpolicy.py:45`, `charter/forge/github.py:488` |
| `commit.gpgsign` | `false` | `charter/gitpolicy.py:50` |
| `tag.gpgsign` | `false` | `charter/gitpolicy.py:51` |
| `url.https://<host>/.insteadOf` | added once per SSH form: `git@<host>:` and `ssh://git@<host>/` (`--add`, multi-valued) | `charter/gitpolicy.py:195`, `charter/forge/github.py:491` |

- Idempotent: a key is rewritten only when its **last** value differs; an insteadOf form is
  added only when absent (`charter/gitpolicy.py:186`-`196`). An unrecognised forge ⇒ nothing
  applied (`charter/gitpolicy.py:180`).
- **Read, never written:** `core.worktree` out of `<git dir>/config`, parsed by charter's
  own mini-parser with a 262144-byte cap (`charter/gitconfig.py:71`, `:153`,
  `charter/gitconfig.py:61`); relative values resolve against the **git directory**
  (`charter/gitconfig.py:94`).

### 2d. Charter-private caches in this area

### `.charter/cache/harness-wiring.json`

- **Format:** JSON object, `sha256 key → {state, detail, fix, checked_at, stamp}`.
- **Status:** **internal** — written and read only by `charter/wiring.py` for the profile
  selector; deleting it costs one extra probe per profile (the selector re-probes on a
  miss, `charter/wiring.py:844`). A launch never reads it (`charter/wiring.py:849`).
- **Written by:** `charter/wiring.py:870` (`remember`) →
  `config.write_for(path, json.dumps(doc, indent=2) + "\n")` (`charter/wiring.py:890`),
  under `config.private_mkdir` (`:889`). Only `wired`/`unwired` are stored.
- **Key:** `sha256(json.dumps({**profiletrust.fingerprint(p), "name", "cwd"},
  sort_keys=True))` (`charter/wiring.py:770`).
- **Stamp:** `{str(path): [st_mtime_ns, st_size] | null}` over each kind's stamped paths
  (`charter/wiring.py:820`; Claude Code `charter/wiring.py:786`, Codex
  `charter/wiring.py:807`, opencode `charter/wiring.py:815`).
- **Freshness:** `0 <= now - checked_at < 86400` (`charter/wiring.py:89`, `:858`).

### `.charter/unrecorded/<sha256[:32]>.json`

- **Format:** `{"errno": "<name or int>", "says": "<strerror>"}` + newline.
- **Status:** **stable** — written by the snapshot path to explain why a checkout's marker
  could not be published, and read by `doctor` in a different process
  (`charter/workspace.py:2984`); removed on the first successful publish. Deleting it costs
  the reason on one `doctor` row, and nothing else.
- **Written by:** `charter/workspace.py:2977` (`_note_unrecorded`), path
  `charter/workspace.py:2956` (`config.STATE_DIR / "unrecorded" / f"{key}.json"`, key =
  `sha256(realpath(tree))[:32]`).

---

## `.charter/` — runtime state

Everything below lives under the plane's **state directory**. It is `<plane root>/.charter/`
unless `$CHARTER_HOME` is set, in which case it is that path **verbatim**
(`charter/config.py:110`, `charter/config.py:114`). A legacy `.edm/` is renamed to
`.charter/` once, on derivation (`charter/config.py:114`).

Out of scope here (other sections): `vaults.json`, `vaults/`, `fingerprint.key`
(secrets), `harness-profiles-launched.json` (config), `persona-state/`, `reports/`
(personas). They are named where a reader in this area touches them.

### Conventions that apply to every file in this area

**Modes.** Every directory charter creates under the state dir is `0700`
(`config.private_mkdir`, `charter/config.py:190`); every file charter writes there is
`0600`, settled with `fchmod` on the descriptor *before* any content
(`STATE_FILE_MODE`, `charter/config.py:389`). A Rust writer must do the same — charter
does not re-tighten a pre-existing directory but does tighten a pre-existing file.

**Write primitives** (all dispatch on "is this path under the state dir"):

| Call | Semantics | Source |
|---|---|---|
| `config.write_for(p, data)` | whole-file write, truncate after `fchmod`, not atomic | `charter/config.py:504` |
| `config.replace_for(p, data)` | **atomic**: write `<name>.<pid>.<12 hex>.tmp` beside, then `os.replace` | `charter/config.py:595`, temp name `charter/config.py:592` |
| `config.create_for(p, data)` | `O_EXCL` create; returns False if it already existed | `charter/config.py:517` |
| `config.touch_for(p)` | create empty (append mode) + `os.utime` — the mtime is the payload | `charter/config.py:644` |
| `config.private_mkdir` / `claim_private_dir` | 0700 mkdir / `O_EXCL`-style claim of a directory | `charter/config.py:190`, `charter/config.py:283` |

**Git.** The whole directory is gitignored: `charter init` writes `/.charter/` into the
plane's `.gitignore` (`charter/commands.py:1096` in `_GITIGNORE_BASELINE`,
`charter/commands.py:1137` for the additive path). So **nothing in this area is committed**;
"stable" below never means "shared through git", it means "a second process reads it".

**Two id shapes are used as file/directory names**

* *session id* — `session.current()`: `$CHARTER_SESSION_ID` → `$CLAUDE_CODE_SESSION_ID`,
  stripped of every character outside `[A-Za-z0-9._-]` (`charter/session.py:65`,
  `charter/session.py:25`). Inside a frame this is the **chat id** (`ide.2`), which shadows
  Claude Code's own session id (`charter/session.py:46`).
* *terminal id* — `session.terminal()`: `TERM_SESSION_ID` → `TMUX_PANE` → `STY` →
  `SSH_TTY` → `os.ttyname(0)`, with every character outside `[A-Za-z0-9._-]` replaced by
  `-` (`charter/session.py:73`, `charter/session.py:119`). So `%9` → `-9`,
  `/dev/ttys032` → `-dev-ttys032` (confirmed against the live plane).

---

### `sessions/` — per-session markers

### `sessions/<sid>.workspace`
- **Format:** plain text, one workspace name + `\n`
- **Status:** **stable** — written by `charter ws use` / the reconcile path, read by every
  other charter process (status line, hooks, frame panels) to answer "which workspace is
  this session on".
- **Written by:** `charter/workspace.py:823` (`set_active`), `charter/workspace.py:851`
  (`reconcile`, seeding from the terminal pointer); commands: `charter workspace use|ws use`
  (`charter/commands_workspace.py:220`), `charter workspace reconcile`
  (`charter/commands_workspace.py:1377`), frame launch (`charter/commands_frame.py:5535`)
- **Read by:** `charter/workspace.py:66`/`for_session` (`charter/workspace.py:111`),
  `workspace.source` (`charter/workspace.py:669`), rename sweep
  (`charter/workspace.py:1450`), freshness scan (`charter/workspace.py:4431`)
- **Git:** gitignored
- **Encoding:** value + trailing `\n`; non-atomic `write_for`; read is `.read_text().strip()`,
  empty → "no pointer"; name is re-validated on read (`instance.workspace_name_ok`).
- **Lifetime:** pruned when older than 30 days on any `set_active`
  (`_SESSION_MAX_AGE`, `charter/workspace.py:45`, sweep at `charter/workspace.py:887`).

### `sessions/<sid>.lock`
- **Format:** plain text, workspace name + `\n`
- **Status:** **stable** — a second process (any later `charter ws use`, the frame) reads it
  to refuse an unforced switch.
- **Written by:** `charter/workspace.py:824` (`set_active` — "confirming = locking")
- **Read by:** `charter/workspace.py:766` (`is_locked`), removed by `unlock`
  (`charter/workspace.py:781`)
- **Git:** gitignored
- **Encoding:** as `.workspace`. Inside a frame the *launch* lock outranks this file
  (`launch_lock` → `frame/state.own_workspace`, `charter/workspace.py:744`).

### `sessions/<sid>.tools` — the persona tool **ceiling**
- **Format:** JSON object `{"<persona>": ["<tool>", …]}`, `sort_keys=True`, no trailing newline
- **Status:** **stable** — written by the SessionStart hook, read by the PreToolUse guard in
  a *different* process, and by `charter persona …`. Security-relevant: it is what a
  mid-session `tools:` edit cannot raise.
- **Written by:** `charter/toolgate.py:813` (`snapshot`), called from
  `charter/hooks.py:7620` (`sessionstart`)
- **Read by:** `charter/toolgate.py:857` (`frozen_tools`), `charter/commands_persona.py:411`
- **Git:** gitignored
- **Encoding:** `json.dumps(data, sort_keys=True)`, written with `replace_for` (atomic).
  Present-but-unparseable ⇒ **approve nothing** (`charter/toolgate.py:859`).

### `sessions/<sid>.gate` — "a ceiling was taken for this session"
- **Format:** empty file; existence is the whole payload
- **Status:** **stable** — a deliberately separate fact from `.tools`; deleting `.tools`
  alone must not re-snapshot (#443, `charter/toolgate.py:752`).
- **Written by:** `charter/toolgate.py:808` (`touch_for`, **before** the ceiling)
- **Read by:** `charter/toolgate.py:877` (`_ceiling_was_taken`)
- **Git:** gitignored
- **Encoding:** zero bytes; write ordering matters (marker first, ceiling second).

### `sessions/<sid>.usage` — token/cache trend ring buffer
- **Format:** plain text, one CSV row per turn: `read,write,hit,ctx`; at most 16 rows
  (`_TREND_KEEP`, `charter/statusline.py:363`); trailing newline
- **Status:** **stable** — written by `charter statusline` (fed Claude Code's per-turn
  payload) and read by the frame's panels in another process
  (`recorded_context_gauge`, `charter/statusline.py:735`); `ctx` exists **only** here.
- **Written by:** `charter/statusline.py:414` (`_record_turn`), via
  `statusline.record_usage` (`charter/statusline.py:643`)
- **Read by:** `charter/statusline.py:459` (`_usage_rows`), `charter/statusline.py:467`,
  `charter/statusline.py:735`; panels through `frame/slots.py`
- **Git:** gitignored
- **Encoding:** `"\n".join(rows) + "\n"`; a row is appended only when `(read, write)`
  differs from the last row (`charter/statusline.py:408`); `ctx` may be the empty field
  (`…,100,`) meaning "no percentage", never `0`. 3-field rows (older charter) still parse.
- **Keyed on Claude Code's own session id from the payload**, not on `$CHARTER_SESSION_ID`
  (`charter/statusline.py:616`) — so in a frame this file's name differs from the chat id.

### `sessions/<sid>.memnudge`
- **Format:** plain text, a decimal integer, no newline
- **Status:** **internal** — a counter written and read only by `hooks` (PostToolUse). Deleted
  ⇒ the memory-cadence nudge restarts its count at 0; nothing else changes.
- **Written by:** `charter/hooks.py:7689` (`_memnudge_set`), bumped `charter/hooks.py:7698`
- **Read by:** `charter/hooks.py:7680`
- **Git:** gitignored

### `sessions/<sid>.configver`
- **Format:** plain text, a 40-char git sha + `\n`
- **Status:** **internal** — hooks-only baseline for the "control plane updated" nudge.
  Deleted ⇒ the next UserPromptSubmit re-baselines silently and nudges once less.
- **Written by:** `charter/hooks.py:7875` (`_write_configver`)
- **Read by:** `charter/hooks.py:7891`
- **Git:** gitignored

### `sessions/<sid>.<tool_use_id>.<kind>.ask-pending`
- **Format:** empty file; existence is the payload. `<kind>` ∈ `routing-ask`, `dispatch-ask`
  (`_ASK_KINDS`, `charter/hooks.py:213`)
- **Status:** **internal** — written by one hook event and taken by another in the same
  chat, purely to trace "the operator approved the thing we asked about". Deleted ⇒ the
  approval is not traced; no behaviour changes.
- **Written by:** `charter/hooks.py:285` (`_ask_mark_set`)
- **Read/removed by:** `charter/hooks.py:314` (`_ask_mark_take`)
- **Git:** gitignored
- **Encoding:** every component is stripped of chars outside `[A-Za-z0-9._-]`
  (`charter/hooks.py:275`). `_ask_mark_take` unlinks only on approval, and a declined ask
  **deliberately** leaves its marker: that asymmetry is what makes "asked N, approved M"
  countable (`charter/workspace.py:875`-`:879`, #290). The leftovers are swept with the rest
  of `sessions/` after 30 days by `workspace._prune` (`charter/workspace.py:881`), which runs
  on `set_active` — so a plane nobody switches workspaces in accumulates them (80 were on the
  plane this was written against).

### `sessions/<sid>.route-pending`
- **Format:** plain text, comma-separated persona names + `\n`
- **Status:** **internal** — set by one hook event and taken by the next in the same
  process family. Deleted ⇒ the routing suggestion is forgotten.
- **Written by:** `charter/hooks.py:8366` (`_route_mark_set`)
- **Read by:** `charter/hooks.py:8377` (`_route_mark_take`), cleared `charter/hooks.py:8388`
- **Git:** gitignored

### `sessions/<sid>.persona`
- **Format:** plain text, persona name + `\n` (personas area — listed because it lives here)
- **Status:** **stable** — written by `charter persona use`, read by the guard, the status
  line and the frame.
- **Written by:** `charter/persona.py:1528` (`set_active`)
- **Read by:** `charter/persona.py:1238` (`for_session`), `charter/persona.py:1219`
- **Git:** gitignored

*Reaping:* when a frame chat is reaped, every `sessions/<chat>.*` marker is removed
(`charter/frame/state.py:3377` (`_forget_session`, `charter/frame/state.py:3328`)).

---

### `terminals/` — per-pane pointers

### `terminals/<tid>.workspace`, `terminals/<tid>.persona`
- **Format:** plain text, one name + `\n`
- **Status:** **stable** — survives closing/reopening the harness in the same pane and is
  read by every later process in that pane.
- **Written by:** `charter/workspace.py:819` (`set_active`), `charter/persona.py:1528`
- **Read by:** `charter/workspace.py:192` + `charter/workspace.py:674`,
  `charter/persona.py:1196`
- **Git:** gitignored
- **Encoding:** filename is the sanitised terminal id (see conventions). Pruned with
  `sessions/` after 30 days (`charter/workspace.py:882`).

---

### `frame/` — the tmux frame's own state (chats, panels, reopen)

`frame/` root: `charter/frame/state.py:229`. Two name shapes appear inside it:
a **chat id** `<workspace-prefix>.<n>` (`charter/frame/state.py:316`, prefix rule
`charter/frame/state.py:104`: every char outside `[A-Za-z0-9_-]` → `_`) and the legacy
**frame id** `<prefix>-<pid>` (`charter/frame/state.py:121`). Both are held to
`[A-Za-z0-9._-]+` (`charter/frame/chats.py:69`).

> **Ruling: `frame/` belongs to the tmux frame, and the app stays out of it.**
> `docs/control-plane.md:872` says these files may change shape in any release and carry no
> format version, and that stands. The app does not draw the tmux frame — it replaces it
> (spec decision 3, milestone M1) — so it keeps its own window state and neither reads nor
> writes anything under `.charter/frame/`. The entries below are recorded because a plane
> the app is working on may have a tmux frame running on it, and because "who owns this
> file" is part of the format. They are marked by what they are to *charter*: a file two
> charter processes share is stable to them. If the app ever needs one of these, it is
> promoted to stable here first, and charter stops calling it scratch at the same time.

### `frame/chat-ids.json`
- **Format:** JSON object `{"<prefix>": <highest ordinal used>}`, `sort_keys=True`, trailing `\n`
- **Status:** **stable** — the high-water mark that stops a reused chat id; read and raised
  by every process that mints a chat.
- **Written by:** `charter/frame/state.py:383` (`_raise_mark`, `replace_for`, under the lock)
- **Read by:** `charter/frame/state.py:363` (`_read_mark`), `highest_ordinal`
  (`charter/frame/state.py:463`)
- **Git:** gitignored
- **Encoding:** `json.dumps(marks, sort_keys=True) + "\n"`, atomic; the mark is only ever
  raised (`max`), never lowered. Allocation also scans directory names, `reopen.json` and
  `sessions/` markers (`charter/frame/state.py:430`, `:437`, `:449`).

### `frame/chat-ids.lock`
- **Format:** empty file used with `flock(LOCK_EX)`
- **Status:** **stable** — the cross-process mutex for id allocation; the app must take the
  same lock to mint an id.
- **Written by / locked by:** `charter/frame/state.py:349` (`_locked`, opened `"a"`)
- **Git:** gitignored
- **Deleted?** recreated on demand, but deleting it while another process holds it defeats
  the mutual exclusion.

### `frame/<chat>/` — one directory per chat
Claimed with `claim_private_dir` (`charter/frame/state.py:318`) so a claim is a race-free
`mkdir`. Every file below is one value; unless said otherwise the writer is
`config.replace_for` (atomic) and the reader is `.read_text().strip()`.

| File | Format | Written by | Read by | Status |
|---|---|---|---|---|
| `launcher` | pid + `\n` | `charter/frame/state.py:556` (`_record_claim`) | `charter/frame/state.py:3223` (`_claiming_pid`), `chats.is_chat` | stable — distinguishes a launching chat from a live one |
| `version` | `time.time_ns()` + `\n` | `charter/frame/state.py:630` (`bump`) | `charter/frame/state.py:664`, `charter/frame/panel.py:802` | **stable — the repaint clock.** A hook writes it (`notify.plane_changed`, `charter/frame/notify.py:132`) and every panel process `stat`s/reads it to know it must redraw |
| `notice` | `<expiry epoch float>\n<text>\n` | `charter/frame/state.py:738` (`say`) | `charter/frame/state.py:769`, `:803` | stable — one process writes, the panels render it; TTL 4.0s (`charter/frame/state.py:675`), refusals 10.0s (`:683`) |
| `exit` | int + `\n` | `charter/frame/state.py:818` | `charter/frame/state.py:2460` | stable |
| `harness` | tmux pane id (`%172`) + `\n` | `charter/frame/state.py:919` | `charter/frame/state.py:935`, `chat_in_pane` (`:962`) | stable |
| `harness.pid` | int + `\n` | `charter/frame/state.py:1216` | `charter/frame/state.py:1221` | stable — written from the SessionStart hook (`charter/hooks.py:6090`) |
| `session` | harness session id + `\n`, held to `[A-Za-z0-9][A-Za-z0-9_-]{0,127}` (`charter/frame/state.py:1128`) | `charter/frame/state.py:1020` (`record_harness_session`) | `charter/frame/state.py:1044` | **stable — hook writes, frame reads.** Set by `charter/hooks.py:6102` |
| `session.durable` | same id + `\n` | `charter/frame/state.py:1094` (`_record_kept_session`) | `kept_harness_session`, `charter/frame/state.py:1099` | stable — survives `clear_harness_session` |
| `session.adopted` | empty, `create_for` (O_EXCL) | `charter/frame/state.py:1243` (`adopt_report`) | `charter/frame/state.py:1248` | stable — first-writer-wins adoption |
| `session.start` | `resumed\n` or `fresh\n` | `charter/frame/state.py:1277` | `charter/frame/state.py:1282` | stable |
| `conversation` | absolute path to the harness transcript `.jsonl` + `\n` | `charter/frame/state.py:1175`, from the hook's `transcript_path` (`charter/hooks.py:6104`) | `charter/frame/state.py:1181` | **stable — one process writes it, another reads it**; only ever `stat`ed by charter |
| `server` | tmux socket name (`charter-plane-<hash>`) + `\n` | `charter/frame/state.py:1317` | `charter/frame/state.py:1335` | stable |
| `workspace` | workspace name + `\n` | `charter/frame/state.py:1384` (`record_workspace`) | `charter/frame/state.py:1514` (`frame_workspace`) → membership (`own_workspace`, `charter/frame/state.py:1619`) | **stable — decides a chat's workspace membership** |
| `profile` | harness-profile name + `\n` | `charter/frame/state.py:1415` | `charter/frame/state.py:1420` | stable |
| `launch` | `<int code>\n<text>` | `charter/frame/state.py:1464` | `charter/frame/state.py:1469` | stable |
| `density` | level word + `\n` | `charter/frame/state.py:1819` | `charter/frame/state.py:1840` | stable (operator-visible layout choice) |
| `bar_rows` | int + `\n` | `charter/frame/state.py:1873` | `charter/frame/state.py:1904` | stable |
| `asserted_bars` | JSON `{"window_rows": int, "panes": [str…] (sorted), "rows": {str: int}}` | `charter/frame/state.py:1953` | `charter/frame/state.py:1997` | stable |
| `chrome` | level word + `\n` | `charter/frame/state.py:2037` | `charter/frame/state.py:2063` | stable |
| `change` | change slug + `\n` | `charter/frame/state.py:2084` | `charter/frame/state.py:2107` | stable |
| `selection` | name + `\n` | `charter/frame/state.py:2145` | `charter/frame/state.py:2166` | stable |
| `hidden` | one name per line | `charter/frame/state.py:2195` | `charter/frame/state.py:2222` | stable |
| `identity` | JSON object of the five frame env vars (`CHARTER_SESSION_ID`, `CHARTER_HARNESS`, `CHARTER_ROOT`, `CHARTER_WORKSPACE`, `CHARTER_PERSONA` — `charter/commands_frame.py:3058`) | `charter/frame/state.py:2354` | `charter/frame/state.py:2375`; pins read at `charter/frame/state.py:1616` | **stable — the chat's environment contract** |
| `panes` | JSON `{ "<panel slot>": "<pane id>" }` | `charter/frame/state.py:2422` | `charter/frame/state.py:2446` | stable |
| `cwd` | absolute path + `\n` | `charter/frame/state.py:2501` | `charter/frame/state.py:2506` | stable |
| `brief` | free text (no trailing-newline normalisation) | `charter/frame/state.py:2566` | `charter/frame/state.py:2571` | stable — the handoff brief the next chat is launched with |
| `brief.owed` | `1\n` | `charter/frame/state.py:2635` | `charter/frame/state.py:2640` | internal marker; deleted ⇒ the chat is not asked for a brief |
| `title` | one line + `\n` (clipped) | `charter/frame/state.py:2719` | `charter/frame/state.py:2727` | stable — the tab label |
| `closed` | `1\n` | `charter/frame/state.py:2784` | `charter/frame/state.py:2789` | stable |
| `waiting` | `1\n` | `charter/frame/state.py:2840` | `charter/frame/state.py:2845` | stable |
| `drawn` | `1\n` | `charter/frame/state.py:2916` | `charter/frame/state.py:2921` | internal (first-draw marker) |
| `ended` | `1\n`, `create_for` (O_EXCL, claim) | `charter/frame/state.py:2948` (`claim_ended`) | `charter/frame/state.py:2953` | **stable** — exactly-once "this chat ended" claim |
| `drawer` | pane id + `\n` | `charter/frame/state.py:3015` | `charter/frame/state.py:3020` | stable |
| `respawn/<slot>` | int + `\n`, in a `respawn/` subdirectory (`charter/frame/state.py:3059`) | `charter/frame/state.py:3133` | `charter/frame/state.py:3124` | internal — attempt counter; `clear_respawn` rmtree's it (`charter/frame/state.py:3165`) |
| `gather.json` | JSON snapshot of the workspace scan (see below); `json.dumps(data)` with **no** indent and **no** trailing newline, written atomically | `charter/frame/gather.py:408` | `charter/frame/gather.py:483`, panels via `gather.read`/`cached` | **stable — the frame's panels read what a detached gather wrote** |
| `tmux.conf` | tmux config text | the placeholder at `charter/commands_frame.py:6621`, then the real config (`conf_text`) at `charter/commands_frame.py:6744` | tmux itself | stable (read by another program) |

`gather.json` fields (`charter/frame/gather.py:105` for the empty shape,
`charter/frame/gather.py:191` for a repo row):

| Field | Type | Meaning | Source |
|---|---|---|---|
| `gathered_at` | float epoch | when the scan ran | `charter/frame/gather.py:106` |
| `workspace` | str | workspace the scan is for | `charter/frame/gather.py:107` |
| `current_repo` | str \| null | repo the cwd is in | `charter/frame/gather.py:108` |
| `repos` | list of objects | `name, branch, dirty, tracked_dirty, ahead, behind, ci, change, sigil, current, worktree_count` | `charter/frame/gather.py:192`–`:202` |
| `worktrees` | list | detail worktrees, same row shape | `charter/frame/gather.py:110` |
| `todos` / `todo_count` | list / int | ≤ 20 rows (`charter/frame/gather.py:82`) | `charter/frame/gather.py:111` |
| `changes` | list of objects | `change, why, state, landed, total, excluded, members[]` | `charter/frame/gather.py:162`–`:173` |

Validity test on read is only `repos` and `worktrees` being lists
(`charter/frame/gather.py:430`); anything else unparseable is treated as "unreadable"
rather than empty (`charter/frame/gather.py:487`).

### `frame/reopen.json`
- **Format:** JSON, `indent=2`, `sort_keys=True`, trailing `\n`
- **Status:** **stable** — written by a quit or by the recorder and read by a *later*
  `charter reopen`; it is the plane's session manifest.
- **Written by:** `charter/frame/reopen.py:320` (`write`), called from
  `charter/commands_frame.py:11128`
- **Read by:** `charter/frame/reopen.py:344` (`read`), also scanned for ordinals
  (`charter/frame/state.py:437`)
- **Git:** gitignored
- **No lock** — last writer wins, deliberately (`charter/frame/reopen.py:28`).

| Field | Type | Required / default | Meaning | Status | Source |
|---|---|---|---|---|---|
| `version` | int | `1`, exact match or the manifest is ignored | format version | stable | `charter/frame/reopen.py:63`, check `:347` |
| `at` | int epoch | required (0 if absent) | when it was recorded | stable | `charter/frame/reopen.py:313` |
| `focus` | str | `""` | workspace that had focus | stable | `charter/frame/reopen.py:314` |
| `writer` | str | `"quit"` \| `"recorder"`, default `quit` | who wrote it | stable | `charter/frame/reopen.py:89`, `:368` |
| `frames[]` | list | required | one entry per workspace | stable | `charter/frame/reopen.py:316` |
| `frames[].workspace` | str | required | workspace name | stable | `charter/frame/reopen.py:316` |
| `frames[].chats[]` | list | required, non-empty entries kept | the chats | stable | `charter/frame/reopen.py:317` |
| `chat` | str | required, `ID_RE` | chat id | stable | `charter/frame/reopen.py:110` |
| `workspace` | str | required, valid name | its workspace | stable | `charter/frame/reopen.py:117` |
| `persona` | str | `""` | active persona | stable | `charter/frame/reopen.py:121` |
| `harness` | str | `""` | harness name | stable | `charter/frame/reopen.py:125` |
| `cwd` | str | `""` | directory it ran in | stable | `charter/frame/reopen.py:128` |
| `resume` | str | `""` | harness session id to resume | stable | `charter/frame/reopen.py:131` |
| `transcript` | str | `""` | file name of the captured transcript | stable | `charter/frame/reopen.py:133` |
| `active` | bool | `False` | was the focused chat | stable | `charter/frame/reopen.py:137` |
| `profile` | str | `""` | harness profile | stable | `charter/frame/reopen.py:146` |
| `brief` | str | `""` | its brief | stable | `charter/frame/reopen.py:159` |
| `conversation` | str | `""` | harness transcript path | stable | `charter/frame/reopen.py:163` |
| `ended` | bool | `False` | the harness had ended | stable | `charter/frame/reopen.py:171` |
| `title` | str | `""` | tab title | stable | `charter/frame/reopen.py:183` |

Unknown keys are dropped on read; non-string values become `""`
(`charter/frame/reopen.py:383`).

### `frame/<chat>.transcript`
- **Format:** plain text — the tmux `capture-pane` output of the chat's pane
- **Status:** **stable** — written at quit, read later by a pager and by `charter reopen`
- **Written by:** `charter/commands_frame.py:10656` (`_capture_transcript`, via
  `capture-pane -p -e -N -S -2000`, `charter/commands_frame.py:10603`/`:10616`); trimmed
  from the **end in bytes** (512 KB cap)
- **Read by:** `charter/commands_frame.py:12503`, `charter/frame/builtin_actions.py:926`
- **Git:** gitignored; pruned to the chats in the manifest
  (`charter/frame/reopen.py:428`)

### `frame/<frame-id>/` for a non-chat frame (e.g. the live plane's `probe-1`)
Same directory shape, name minted by `frame_id(workspace, pid)`
(`charter/frame/state.py:121`). Only `gather.json` + `version` are typically present.

---

### `app/` — the desktop app's own state

`.charter/app/` is the **charter-app** rebuild's, the way `.charter/frame/` is the tmux
frame's. Python charter neither reads nor writes anything under it, and the app stays out
of `frame/` in the same way — the app replaces that frame rather than sharing its state
(ADR 0025, and the note at the top of this file).

It is recorded here because this file records every file charter's implementations put in a
plane, and because the two share a plane during the migration: an operator running both
will see this directory, and whoever next changes the app should find its format written
down rather than read off the code.

### `app/reopen.json`
- **Format:** JSON, `indent=2`, trailing `\n`. Written beside itself as
  `reopen.json.writing` and renamed over, so a launch never reads half of one.
- **Status:** **internal** — written and read by the app alone. Deleting it costs one
  relaunch's worth of chats: the app starts with none open, which is what a first launch
  does anyway. No second process reads it, which is what would make it stable.
- **Written by:** `app/src-tauri/src/lib.rs` (charter-app) — whenever what is open changes
  (a chat started, closed, or brought to front), and again on the way out. Not only on the
  way out: an app that is killed, or crashes, runs no exit handler.
- **Read by:** `app/src-tauri/src/lib.rs`, in Tauri's `setup`, before there is a window —
  so a relaunch does not depend on a webview having run.
- **Git:** gitignored already, by the plane's own `/.charter/` line.
- **No lock** — one app per plane (Tauri's single-instance plugin), and last writer wins.

| Field | Type | Required / default | Meaning |
|---|---|---|---|
| `version` | int | `1`; any other value and the record is ignored whole | format version |
| `at` | int epoch | required | when it was written; nothing reads it |
| `chats[]` | list | required | one entry per chat that was open |
| `chats[].program` | str | required | the program, as it was launched: a path or a bare name |
| `chats[].args` | list[str] | default `[]` | its arguments, **without** any charter added — a resume spells those differently from a start, so they are decided again at the reopen |
| `chats[].cwd` | str | default `""` (absent) | the directory it ran in |
| `chats[].name` | str | default `""` | what the operator calls the chat; a harness that takes a name is given it again |
| `chats[].resume` | str | default `""` | the harness session id to resume. Held to `[A-Za-z0-9][A-Za-z0-9_-]{0,127}` — the Python charter's `SESSION_ID_RE` (`charter/frame/state.py:1128`) — on the way in, and a value that is not one reads as empty. It reaches a command line, and one starting with `-` would be a flag the operator never typed. The chat still comes back, as a new one |
| `chats[].active` | bool | default `false` | whether it was the chat in front |
| `chats[].profile` | str | default `""` (absent) | the harness profile the chat started on, by NAME — never its command or its environment, so an edit to `charter.local.toml` takes effect at the reopen and the account it names never reaches this file (ADR 0022). Held to a name charter would mint; anything else reads as empty |
| `chats[].persona` | str | default `""` (absent) | the persona the chat adopted, under the same rule |
| `chats[].footer` | str | default `""` | `"show"` where this chat draws charter's footer in its pane, empty otherwise ([ADR 0029](adr/0029-the-pane-footer-is-blanked-by-default-and-a-chat-may-keep-it.md)). The same word the chat's `$CHARTER_FOOTER` carries, so the record and the launch cannot mean different things by it. **Any other value reads as empty** — a record written before this key existed, and one somebody else wrote, both come back blanked, which is what the app did before the setting existed |

Which harness a chat runs is **not** recorded: it is read from `program`'s file name, so a
record cannot disagree with what is about to be started. Only a harness charter has
measured a resume for is resumed (`crates/charter-core/src/harness.rs`, which carries the
same values as `charter/harness/`); a Codex chat has no `resume` to record at all, because
Codex reports its id only through a hook, inside its first turn (ADR 0024).

---

### Top-level markers, gates and ledgers

### `chat-turns/<chat>`
- **Format:** empty file; **the mtime is the value**
- **Status:** **stable** — written by the hooks (Python) on every tool call and read by the
  frame panel to animate "this chat is working". The canonical hook-writes/frame-reads pair.
- **Written by:** `charter/inflight.py:507` (`turn_begin`, `touch_for`),
  `charter/inflight.py:527` (`turn_bump`, `os.utime`), removed `charter/inflight.py:543`;
  callers `charter/hooks.py:5971`, `charter/hooks.py:6177`, `charter/hooks.py:8699`
- **Read by:** `charter/inflight.py:587` (`working_chats`),
  `charter/inflight.py:474` (`turn_stamp` — one `stat` of the directory),
  `charter/frame/panel.py:657`, `charter/frame/slots.py:5060`
- **Git:** gitignored
- **Encoding:** the file name is the chat id, refused unless it survives `_safe_name`
  unchanged (`charter/inflight.py:454`). Entries older than 10 min
  (`TURN_STALE_SECONDS`, `charter/inflight.py:415`) are deleted on read.

### `dispatch-inflight/<agent>.<random>.json`
- **Format:** JSON `{"agent": str, "kind": str, "ts": float}`, no newline
- **Status:** **stable** — written by the dispatch hook, read by the status line and the
  frame panels in other processes.
- **Written by:** `charter/inflight.py:246` (`start`, `tempfile.mkstemp` + `json.dump`);
  caller `charter/hooks.py:7954`. Also `kind="clone"` (`charter/commands.py:606`),
  `"gl-refresh"` (`charter/commands.py:1027`), `"action"`
  (`charter/frame/actions.py:370`)
- **Read by:** `charter/inflight.py:180` (`live_records`), `charter/statusline.py:1834`,
  `charter/frame/panel.py:580`, `charter/frame/slots.py:2573`
- **Removed by:** `charter/inflight.py:290`/`:305` (`finish`); anything older than 24 h
  (`PRUNE_SECONDS`, `charter/inflight.py:61`) is unlinked on read
- **Git:** gitignored
- **Encoding caution:** the file is created by `tempfile.mkstemp`, i.e. **0600 but not
  through `config`**; the name is `<safe agent name, ≤64 chars>.<mkstemp tail>.json`
  (`charter/inflight.py:107`, `:244`). `kind` defaults to `"dispatch"` when absent
  (`charter/inflight.py:103`).

### `commit-gate/<sid>`
- **Format:** plain text, a small decimal integer (countdown), no newline
- **Status:** **internal** — a per-session cooldown counter for one nudge, written and read
  only by `hooks`. Deleted ⇒ the next prompt may nudge once more.
- **Written by:** `charter/hooks.py:8322` / `charter/hooks.py:8324` (reset to
  `_COMMIT_COOLDOWN` = 3, `charter/hooks.py:8262`)
- **Read by:** `charter/hooks.py:8320`
- **Git:** gitignored; filename is the sanitised session id (`charter/hooks.py:8319`)

### `dispatch-commit.lock`
- **Format:** empty file, used with `flock(LOCK_EX)`
- **Status:** **stable** — a cross-process mutex around committing the dispatch record; any
  process that commits plane memory must take it.
- **Written/locked by:** `charter/hooks.py:8209`
- **Git:** gitignored; deleted ⇒ recreated, but concurrent committers stop serialising.

### `guard-seen.json`
- **Format:** JSON object, `sort_keys=True`, trailing `\n`
- **Status:** **stable** — written by the guard handler and read by `charter doctor` in
  another process; it is the evidence that the guard is actually wired.
- **Written by:** `charter/guardseen.py:180` (`mark`), called from `charter/hooks.py:6222`
- **Read by:** `charter/guardseen.py:283` (`last`), `charter/doctor.py:2002`,
  `charter/doctor.py:2466`
- **Git:** gitignored (`charter/guardseen.py:38`)

| Field | Type | Required | Meaning | Status | Source |
|---|---|---|---|---|---|
| `ts` | str, ISO-8601 UTC, seconds precision | yes (a record without it reads as absent) | when the guard last fired | stable | `charter/guardseen.py:168`, check `charter/guardseen.py:286` |
| `harness` | str \| null | yes | harness registry name | stable | `charter/guardseen.py:168` |
| `source` | `"plugin"` \| `"settings"` | yes | which declaration dispatched it | stable | `charter/guardseen.py:48`, `charter/guardseen.py:50`, decided at `charter/guardseen.py:55` |
| `claude_config_dir` | str \| null | only for Claude Code | `$CLAUDE_CONFIG_DIR` in use | stable | `charter/guardseen.py:62`, written `charter/guardseen.py:176` |

Only the **latest** sighting is kept (whole-file overwrite).

### `mcp-approved.json`
- **Format:** JSON `{"<persona>": ["<sha256 hex>", …]}`, `indent=2`, `ensure_ascii=False`,
  trailing `\n`; the list is sorted
- **Status:** **stable** — an operator consent record; read by the persona renderer in every
  later process. Machine-local and deliberately not committed (`charter/mcpseen.py:42`).
- **Written by:** `charter/mcpseen.py:264` (`approve`), from
  `charter persona … --approve-mcp` (`charter/commands_persona.py:2029`)
- **Read by:** `charter/mcpseen.py:241` (`_read`) → `approved` (`charter/mcpseen.py:250`),
  `charter/persona.py:779`
- **Git:** gitignored
- **Encoding:** the fingerprint is `sha256(consent line)` (`charter/mcpseen.py:236`); the
  per-persona set is **replaced**, never merged. Not present in the live plane.

### `agent-personas.json`
- **Format:** JSON object `{"<agent id>": "<persona>"}`, `sort_keys=True`, no newline
- **Status:** **stable** — written by one hook event (dispatch) and read by a later one to
  attribute a sub-agent's tools to a persona; it crosses processes.
- **Written by:** `charter/hooks.py:8098` (`_agent_map_remember`)
- **Read by:** `charter/hooks.py:8105` (`_agent_map_lookup`)
- **Git:** gitignored
- **Encoding:** capped at 200 entries, oldest dropped (`charter/hooks.py:8096`); agent ids
  match `\bagentId:\s*([0-9a-f]{6,})` (`charter/hooks.py:8076`).

### `plane-push.json`
- **Format:** JSON object, `indent=2`, no trailing newline
- **Status:** **stable** — written by a **detached** background pusher that has no caller to
  tell, and read by `doctor` later (`charter/planegit.py:213`).
- **Written by:** `charter/planegit.py:280` (`record_push`); **deleted** when the push
  succeeded (`charter/planegit.py:277`)
- **Read by:** `charter/planegit.py:297` (`push_record`), `charter/planegit.py:340`
- **Git:** gitignored

| Field | Type | Meaning | Status | Source |
|---|---|---|---|---|
| `outcome` | str, one of `pushed`/`branched`/`stranded`/`failed`/`conflict`/`unreachable` | what the push did; a record without it reads as absent | stable | `charter/planegit.py:190`–`:195`, `:300` |
| `branch` | str | branch charter tried to advance | stable | `charter/planegit.py:281` |
| `landed` | str \| null | the branch it actually reached | stable | `charter/planegit.py:281` |
| `url` | str \| null | PR/MR url | stable | `charter/planegit.py:282` |
| `detail` | str | git's own words | stable | `charter/planegit.py:282` |
| `head` | str | the sha being pushed | stable | `charter/planegit.py:282` |
| `at` | float epoch | when | stable | `charter/planegit.py:282` |

### `ws-edit-nudge/<sid>-<workspace>`
- **Format:** one byte, `1`
- **Status:** **internal** — "this session was already nudged about this workspace". Deleted
  ⇒ one extra nudge. Written and read only by `hooks`.
- **Written by:** `charter/hooks.py:7656`; existence checked `charter/hooks.py:7654`
- **Git:** gitignored
- **Encoding:** key is `f"{session}-{ws}"` with every char outside `[A-Za-z0-9._-]`
  removed (`charter/hooks.py:7652`) — **ambiguous by construction** (see the Appendix).
  Only written for a **live** workspace (`charter/hooks.py:7810`).

### `ws-autosave/<workspace>`
- **Format:** plain text, `str(time.time())`, no newline; the mtime is what is actually read
- **Status:** **internal** — a 90-second debounce for the Stop-hook auto-save. Deleted ⇒ at
  most one extra commit attempt.
- **Written by:** `charter/commands_workspace.py:1179` (marker path
  `charter/commands_workspace.py:1171`)
- **Read by:** `charter/commands_workspace.py:1173` (mtime only)
- **Git:** gitignored; only ever written when `[memory] share` is not `local`

### `workspace-tab-order`
- **Format:** plain text, one workspace name per line, trailing newline per line
- **Status:** **stable** — the operator's tab order, written by the frame and read by every
  later frame/palette process.
- **Written by:** `charter/workspace.py:1023` (`record_tab_order`, `replace_for` — atomic)
- **Read by:** `charter/workspace.py:1060` (`tab_order`); removed by
  `charter/workspace.py:1079`
- **Git:** gitignored
- **Encoding:** `"".join(f"{n}\n" for n in names)`; names failing `valid_name` are dropped
  on read (`charter/workspace.py:1063`).

### `workspace-arrivals/<workspace>`
- **Format:** empty file; existence is the payload
- **Status:** **stable** — one process records the arrival, another (the frame/status line)
  reads and clears it.
- **Written by:** `charter/workspace.py:1163` (`record_arrival`, `touch_for`)
- **Read by:** `charter/workspace.py:1198` (`arrivals`), cleared `charter/workspace.py:1224`,
  all forgotten `charter/workspace.py:1238`
- **Git:** gitignored; the name must satisfy `valid_name` (`charter/workspace.py:1127`)

### `unrecorded/<sha256(realpath(tree))[:32]>.json`
- **Format:** JSON `{"errno": "<errno name or number>", "says": "<strerror>"}` + `\n`
- **Status:** **stable** — written by the snapshot path and read by a later command/status
  render to explain why a tree could not be recorded.
- **Written by:** `charter/workspace.py:2977` (`_note_unrecorded`, atomic); removed when the
  write succeeds (`charter/workspace.py:2974`)
- **Read by:** `charter/workspace.py:2988` (`unrecorded_reason`)
- **Git:** gitignored
- **Encoding:** filename derivation `hashlib.sha256(os.path.realpath(tree))[:32]`
  (`charter/workspace.py:2959`) — note it uses `mkdir_for`, not `private_mkdir`.

### `locks/harness-wiring-<digest16>.lock`
- **Format:** empty file, `flock(LOCK_EX)`
- **Status:** **stable** — serialises harness wiring across processes.
- **Written/locked by:** `charter/wiring.py:963` (path `charter/wiring.py:959`)
- **Git:** gitignored
- **Encoding:** digest = first 16 hex of `sha256(json.dumps({**profiletrust.fingerprint(p),
  "name": p.name}, sort_keys=True))` (`charter/wiring.py:957`)

### `active-workspace` (legacy)
- **Format:** plain text
- **Status:** **internal/dead** — derived (`charter/config.py:804`) and read by nothing in
  this tree; kept so old files do not error. Deleting it changes nothing.

### `active-persona`
- **Format:** plain text, persona name + `\n`
- **Status:** **stable** — the plane-wide persona pointer used only when there is neither a
  session nor a terminal id (`charter/persona.py:1529`); read by `charter/persona.py:1222`.
- **Git:** gitignored

---

### `cache/` — derived data with a TTL

All five are regenerated on demand; deleting any of them costs one slower render or one
extra network/git call. They are **internal** by the rule, but every one of them is written
by one process and read by another (the status line, the frame, a background refresher), so
a Rust reader that only *reads* them is safe while a Rust writer must keep the key and TTL
semantics below.

### `cache/repostate.json`
- **Format:** JSON object keyed by absolute repo path → `{"dirty": bool, "tracked_dirty":
  bool, "ahead": int, "behind": int, "ts": float}`; one line, no trailing newline
- **Status:** **internal** — a 5-second TTL cache of `git status --porcelain=v1 --branch`
  (`_STATE_TTL`, `charter/statusline.py:817`). Deleted ⇒ the next render shells out to git.
- **Written by:** `charter/statusline.py:844` (`_repo_states`)
- **Read by:** `charter/statusline.py:825`; the whole file is rewritten on any change
- **Git:** gitignored. Values: `charter/statusline.py:902`

### `cache/glstate.json`
- **Format:** JSON object keyed by absolute repo path → `{"branch": str, "ts": float,
  "change": int|null, "ci": str|null, "sigil": str}`
- **Status:** **internal** — forge (CI / open change) cache. Served for up to 2 h
  (`DISPLAY_TTL`, `charter/glstate.py:21`), refreshed after 5 min (`REFRESH_TTL`,
  `charter/glstate.py:22`). Deleted ⇒ the CI column is blank until a refresher runs.
- **Written by:** `charter/glstate.py:150` (`_save`), from the detached
  `charter gl-refresh` (`charter/glstate.py:288`)
- **Read by:** `charter/glstate.py:141` (`load`), `charter/glstate.py:171` (`read_for`),
  and `gather.scan`
- **Git:** gitignored; an entry whose `branch` no longer matches is ignored
  (`charter/glstate.py:176`).

### `cache/glstate.refreshing`
- **Format:** plain text, the refresher's pid (or empty when done)
- **Status:** **internal** — spawn lock; **mtime carries the age**. Deleted ⇒ at worst a
  duplicate refresher.
- **Written by:** `charter/glstate.py:88` (`_write_lock`), cleared `charter/glstate.py:136`
- **Read by:** `charter/glstate.py:106` (`_read_lock`), liveness via `os.kill(pid, 0)`
  (`charter/glstate.py:119`)

### `cache/update.json` and `cache/update.checking`
- **Format:** `update.json` — JSON `{"latest": str, "ts": float, "head": str}` (one line);
  `update.checking` — empty file whose **mtime** is the spawn cooldown
- **Status:** **internal** — deleted ⇒ one more version check. `latest` is the newest
  released version, `head` the upstream dev sha (dev channel only).
- **Written by:** `charter/update.py:467` (`fetch_and_store`), lock touched
  `charter/update.py:506`
- **Read by:** `charter/update.py:119` (`load`), `charter/update.py:331` (`newer_head`),
  `charter/update.py:351` (`newer_than`), `charter/update.py:500`
- **Git:** gitignored; refresh at most daily (`REFRESH_TTL`, `charter/update.py:53`)

### `cache/update-baseline`
- **Format:** plain text, a version string, no newline
- **Status:** **stable** — it is what the *news* range is computed from across upgrades, i.e.
  a later, different charter reads what an earlier one wrote. Deleted ⇒ the news range
  degrades, never the update (`charter/commands_update.py:131`).
- **Written by:** `charter/commands_update.py:129` (`_stamp_baseline`)
- **Read by:** `charter/commands_update.py:120` (`read_baseline`)
- **Git:** gitignored

### `cache/vaulthealth.json`
- **Format:** JSON object keyed by vault name → `{"ok": bool, "detail": str, "ts": float}`
- **Status:** **internal** — 60-second TTL (`_VAULT_TTL`, `charter/statusline.py:1650`).
  Deleted ⇒ the next render asks the provider again.
- **Written by:** `charter/statusline.py:1691`
- **Read by:** `charter/statusline.py:1677`
- **Git:** gitignored. **`detail` is provider text and can name paths/accounts** — it is the
  one cache entry a UI must treat as possibly sensitive.

### `cache/harness-wiring.json`
- **Format:** JSON object keyed by a sha256 hex → `{"state": "wired"|"unwired", "detail":
  str, "fix": str, "checked_at": float, "stamp": {"<abs path>": [mtime_ns, size] | null}}`,
  `indent=2`, trailing `\n`
- **Status:** **internal** — remembered wiring verdict; 24 h TTL (`MAX_AGE`,
  `charter/wiring.py:89`) **and** invalidated when any stamped file changed
  (`charter/wiring.py:861`). Deleted ⇒ the selector re-checks (slower, correct).
- **Written by:** `charter/wiring.py:890` (`remember`)
- **Read by:** `charter/wiring.py:838` (`_read_cache`), `charter/wiring.py:853` (`cached`)
- **Git:** gitignored; key = `sha256(json.dumps({**profiletrust.fingerprint(p), "name":
  p.name, "cwd": str(cwd)}, sort_keys=True))` (`charter/wiring.py:770`)

---

### State charter keeps **outside** the plane

* `$CHARTER_CONFIG_HOME` → `$XDG_CONFIG_HOME` → `~/.config`, then `charter/reporting-consent`
  — a plain text file whose **existence** is the Reporter's consent to open upstream issues
  (`charter/report.py:462`, `charter/report.py:465`, granted `charter/report.py:475`).
  **stable** (operator-visible, deleted by hand to withdraw), per *machine*, not per plane:
  one consent covers every plane the machine works on.
* No other **state** in this area is written outside the plane, though charter does write
  elsewhere: a news probe writes `$TMPDIR/charter-probe-<pid>` (`charter/news.py:1329`).
  Harness-side files
  (`~/.claude/...`, codex/opencode homes) belong to the config/harness area; this area only
  *stamps* them in `cache/harness-wiring.json`.

### Environment variables that move or key this state

| Variable | Effect | Source |
|---|---|---|
| `CHARTER_HOME` | **Replaces the state directory outright** — every file in this section moves, verbatim, no migration | `charter/config.py:42`, `charter/config.py:110` |
| `CHARTER_ROOT` | Picks the plane (hence `<root>/.charter`); a bad value raises rather than falling back | `charter/root.py:20` |
| `CHARTER_SESSION_ID` | Names `sessions/<sid>.*`, `commit-gate/<sid>`, `ws-edit-nudge/<sid>-…`, the trace bucket, and inside a frame it is the **chat id** that names `frame/<chat>/` and `chat-turns/<chat>` | `charter/session.py:65`, shadowing explained `charter/session.py:46` |
| `CLAUDE_CODE_SESSION_ID` | Fallback for the above | `charter/session.py:66` |
| `TERM_SESSION_ID` / `TMUX_PANE` / `STY` / `SSH_TTY` (then `ttyname`) | Name `terminals/<tid>.*` | `charter/session.py:75`–`:79`, `charter/session.py:111` |
| `CHARTER_WORKSPACE` | Overrides the resolved workspace **without writing anything**; also the `identity` pin read per chat | `charter/workspace.py:550`, `charter/frame/state.py:1616` |
| `CHARTER_PERSONA` | Same, for personas | `charter/persona.py:1260` |
| `CHARTER_HARNESS` | Which harness the registry reports; stored per chat in `frame/<chat>/identity` | `charter/harness/registry.py:46`, `charter/commands_frame.py:3058` |
| `CHARTER_WORKTREES` | Moves worktrees (not state) | `charter/config.py:82` |
| `CHARTER_NO_BACKGROUND_CHECKS` | Suppresses the spawners that write `cache/glstate.*` and `cache/update.*` | `charter/util.py:382`, gates at `charter/glstate.py:209`, `charter/update.py:491` |
| `CLAUDE_CONFIG_DIR` | Recorded into `guard-seen.json` | `charter/guardseen.py:62` |
| `CLAUDE_PLUGIN_ROOT` | Decides `guard-seen.json`'s `source` field (`plugin` vs `settings`) | `charter/guardseen.py:55` |
| `CLAUDE_PID` | Adopting a harness pid into `frame/<chat>/harness.pid` | `charter/hooks.py:6084` |
| `CHARTER_CONFIG_HOME` / `XDG_CONFIG_HOME` | Move `reporting-consent` | `charter/report.py:462` |
| `EDM_HOME` / `EDM_WORKSPACE` / `EDM_PERSONA` | Legacy names, warned about only | `charter/legacyenv.py:39` |

---

### What the tmux frame and the status line read that a **hook** wrote

One process writes each of these and a different one reads it, which is what makes them
stable to charter. It is also the shape of the problem the app has: Python's hooks keep
writing a session's state, and the app has to learn the same facts. It does **not** inherit
this surface file by file — `frame/` is the tmux frame's own (the ruling above) — so where a
row below names a `frame/<chat>/` file, the app needs its own answer to the same question,
and the row says what that question is.

| Written by (Python hook) | File | Read by |
|---|---|---|
| `sessionstart` → `toolgate.snapshot` (`charter/hooks.py:7620`) | `sessions/<sid>.tools`, `sessions/<sid>.gate` | the PreToolUse guard, `charter persona` |
| `sessionstart` → `_record_harness_session` (`charter/hooks.py:6102`) | `frame/<chat>/session`, `session.durable`, `session.adopted`, `harness.pid`, `conversation` | frame panels, `charter reopen`, tab menu |
| every hook → `notify.plane_changed` (`charter/frame/notify.py:132`) | `frame/<chat>/version` **and** `frame/<chat>/gather.json` | `charter/frame/panel.py:802` (the repaint loop) |
| `_turn_begin`/`_turn_bump` (`charter/hooks.py:5971`, `:6177`) | `chat-turns/<chat>` (mtime) | `charter/frame/panel.py:657`, `charter/frame/slots.py:5060` |
| `pretooluse-dispatch` (`charter/hooks.py:7954`) | `dispatch-inflight/*.json` | `charter/statusline.py:1834`, `charter/frame/panel.py:580` |
| the guard (`charter/hooks.py:6222`) | `guard-seen.json` | `charter/doctor.py:2002` |
| `charter statusline` (fed the harness payload) | `sessions/<sid>.usage` | `charter/statusline.py:735` → frame panels (the `ctx %` exists nowhere else) |
| `charter ws use` in the chat's shell | `sessions/<sid>.workspace`, `sessions/<sid>.lock` | every charter process in that chat |

Two of these are *not* keyed the same way: `.usage` is keyed on **Claude Code's** session id
out of the payload, while everything frame-side is keyed on the **chat id**
(`$CHARTER_SESSION_ID`). A chat's context gauge therefore needs a
chat → harness-session mapping; `frame/<chat>/session` is where the tmux frame keeps its
copy, and an app that does not read `frame/` needs one of its own.

---

## Appendix: what this survey found in the code

Recording the format meant reading every writer and reader. These are the things
that surprised the survey: stale docs, latent divergences, and writes that are not
atomic where their neighbours are. **Nothing here was fixed** — the Python charter is
frozen (spec decision 16), and a rebuild has to reproduce the behaviour as it is, not
as it was meant to be. They are recorded so the rebuild copies them deliberately and
so each one can be filed on its own merits.

### In the plane root

1. **`[harness] default` has two readers with two vocabularies.**
   `instance.harness_of` accepts only a registry `cli_name` and records anything else as
   `refused` (`charter/instance.py:3088`), while `profiles.derive` treats the same key as
   naming *any* profile, including one only `charter.local.toml` declares
   (`charter/profiles.py:318`). `doctor` papers over it by checking the refused value against
   the profile set (`charter/doctor.py:390`). `docs/control-plane.md:96` documents it as
   "which row bare `charter`'s profile selector starts on" and lists only the three harness
   words. A Rust reader has to implement both readings. Flagged as **stable** either way.
2. **`workspaces/.gitkeep` is ignored-negated and anchored on, but never created** by `init`
   or `reinit` (measured). Whether the app should create it is a question for the workspaces
   area; the anchor line matters to `.gitignore` splicing either way.
3. **`charter.toml` is rewritten non-atomically** (`p.write_text`, `charter/instance.py:441`)
   with no lock, while every `.charter/` writer goes through `config.replace_for`. Two
   concurrent `persona default` / `version bump` runs can interleave. Marked stable; noting the
   write discipline because a second implementation writing the same file needs to know
   charter does *not* hold a lock.
4. **`.charter/harness-profiles-launched.json` is read-modify-written whole with no lock**
   (`charter/profiletrust.py:172`). Its own module documents that it is not a boundary
   (`charter/profiletrust.py:18`). Marked **stable** because a second process reads it and
   it gates command execution — confirm that is the classification the doc wants for a
   `.charter/` file.
5. **`instance.SCHEMA` vs `workspace.STRUCTURE_VERSION`** are deliberately never compared
   (`charter/instance.py:33`). Only the plane number refuses. Worth stating in the assembled
   doc so a Rust reader does not gate on the workspace number.
6. **`[[forge]] version`** appears in a code comment as an example of a key `_set_key` must not
   clobber (`charter/instance.py:398`), but no forge code reads a `version` key. It is an
   example, not a setting, and the survey found no reader for it.
7. **`config.GROUP`/`EXCLUDE` are "the first `[[forge]]` block's"** (`charter/config.py:728`,
   `charter/instance.py:148`) while `discover` asks per block (`charter/commands.py:120`). Two
   meanings of one word in one file; both are live.
8. **The empty-inventory skeleton has no `note` key** (`charter/inventory.py:74`) while the
   saved document always does (`charter/inventory.py:308`). A strict reader must treat `note`
   as optional.
9. **`charter docs` exits 1 on an empty inventory** (`charter/commands.py:220`) and also
   exits 1 when the README roster could not be refreshed (`charter/commands.py:231`) even
   though `docs/topology.md` was written. Not a config-format issue, but it affects any
   fixture generator that checks exit codes.

### In workspaces

1. **`change.record_landing` has no caller in `charter/`.** `charter/change.py:156` is a
   complete landing-log writer (`config.open_for`, `json.dumps(sort_keys=True)`), and the
   suite calls it (`tests/_changerepo.py:122`, `tests/test_change_surface.py:573`) but the
   product does not: the only caller of the landing log is `commands_change._append_landing`
   (`charter/commands_change.py:1092`, called at `charter/commands_change.py:1501`), which
   uses `contain.json_line` and a raw `os.open(..., 0o644)`. The two agree on the line's
   fields and key order but differ in escaping (`ensure_ascii=True` only in the live one)
   and in file mode dispatch. A Rust writer should follow `_append_landing` — and deleting
   `record_landing` as dead would take the behaviour those tests pin with it. Flagged, not
   fixed.
2. **The brief says `refs/` holds `README.md` and `repos.json`.** There is no `repos.json`
   under a workspace's `refs/`. `repos.json` is `inventory/repos.json`
   (`charter/config.py:783`). `refs/` holds the generated `README.md` and whatever the
   operator drops in.
3. **`.charter-generated` is stable**, although only charter reads it: a *different
   process* (a later launch, `doctor`, `reinit`) does, and deleting it is not harmless —
   every generated file then reads as `foreign` and is never refreshed or withdrawn again.
4. **`.charter/workspace-tab-order` and `workspace-arrivals/` are stable**, and the survey
   first had them as internal because they are regenerated at the next launch
   (`charter/workspace.py:1066`, `charter/workspace.py:1229`). Every frame process on the
   plane reads them, which is what the rule turns on; the regeneration is what deleting one
   costs, and the entries say so.
5. **Two different manifest orderings.** A manifest charter creates has
   `name, description, repos, updated_at, updated_by, charter_generated`; one written by
   `snapshot`/`fork` keeps whatever order the document on disk had and appends new keys
   (`fork` inserts `forked_from`). A byte-identical Rust writer has to preserve the order it
   read rather than impose a canonical one. `charter_generated` is always last because it is
   assigned after the copy (`charter/workspace.py:1611`).
6. **`updated_by` has two sources** — `$USER` for automatic writes and `git config user.name`
   for `snapshot`/`fork` — so the same workspace's manifest can alternate between two
   spellings of the same person. Intentional per `charter/workspace.py:1620`, but worth
   recording in the spec.
7. **Local vs UTC time in one store.** A memory's filename prefix is local time and its body
   stamp is local; every other timestamp in the area is UTC. `memstore.memory_date` reads the
   body first and the filename second (`charter/memstore.py:150`), so the two must agree —
   they do only because both come from the same local `now`.
8. **`charter_generated` digest input uses Python's default JSON separators.** A Rust
   implementation emitting `{"a":1}` instead of `{"a": 1}` produces a different digest and
   every manifest reads as the operator's. This is unwritten anywhere but in the code
   (`charter/workspace.py:1540`).
9. **`_live_block` and `_ws_meta_paths` are two lists of the same set** in two modules, held
   together only by `tests/test_todos_are_committed.py` (`charter/workspace.py:1390`,
   `charter/commands_workspace.py:1094`). A second implementation should derive both from
   one list.
10. **The LIVE block is written non-atomically** (`gi.write_text`,
    `charter/workspace.py:1418`) where every other committed file charter writes goes through
    `config.replace_for`. A kill mid-write truncates the plane's `.gitignore`.
11. **Legacy migrations a Rust reader will meet:** `repos/` → `workspaces/`
    (`charter/workspace.py:53`) and `.edm-structure` → `.charter-structure`
    (`charter/workspace.py:4477`, `charter/workspace.py:4494`). Both are best-effort renames
    performed on read.
12. **`workspaces/.gitkeep` is an anchor that `charter init` never creates.** The line
    `!/workspaces/.gitkeep` is written into `.gitignore` (`charter/commands.py:1091`) and is
    the literal insertion point for the LIVE block (`charter/workspace.py:1414`), but no
    command writes the file itself — measured on a fresh `charter init`.

### In personas and memory

1. **`.charter/persona-state/trace/<session>.jsonl` — stable or internal?** Marked stable
   (written by hooks, read by `charter trace`/`persona recall` in other processes), but it
   is machine-local, gitignored and losing it costs only history — but the status line
   reads it in another process, which is what the rule turns on.
2. **`.charter/sessions/<sid>.persona` / `terminals/<tid>.persona` / `active-persona`** —
   written by `persona.py`, but the directories belong to the workspaces area. Someone must
   decide which section owns them so they are not documented twice or dropped.
3. **`.charter/mcp-approved.json`** — written by `mcpseen.py`, but
   `persona.py` is its only consumer and it decides whether a generated agent carries the
   vault wrapper. Overlaps the secrets agent.
4. **`personas/_dispatch` vs `inflight`** — `charter/inflight.py` notes that `_dispatch`
   records a dispatch when it *finishes*; `.charter/dispatch-inflight/` is a separate
   (gitignored) store, documented in the `.charter/` section.
5. **Docs vs code — `persona-state/log/<name>.jsonl`.** `charter/persona.py:15` (module
   docstring) still advertises "an activity log (`log/<name>.jsonl`)"; there is none —
   `charter/persona.py:2458` says so, and activity lives in `trace/`. Docstring is stale.
6. **Docs vs code — frontmatter table.** `docs/personas.md:112`-`:123` lists only `role`,
   `vault`, `delegate-when`, `tools`, `agent-tools`, `extends`, `uses`, `activity`. The
   code reads eight more (`name`, `description`, `agent-description`, `disallowed-tools`,
   `skills`, `draft`, `dispatch-isolation`, plus `routing`/`routes-to`/`borrows`, which are
   documented in later sections) and passes through `model`, `color`, `memory`.
7. **Docs vs code — `charter persona use` help.** `charter/cli.py:1658` says it "writes
   `.charter/active-persona`"; it writes that file only when there is neither a session id
   nor a terminal id (`charter/persona.py:1529`). In a normal session it writes the two
   pointers instead.
8. **Slug truncation can leave a trailing `-`.** `charter/memstore.py:26`-`:28` strips `-`
   *before* `[:48]`, so a 48-char cut mid-word keeps the hyphen: a memory titled
   "1097 is worse than the issue says: F2 detach ran the wrong command" is filed as
   `1097-is-worse-than-the-issue-says-f2-detach-ran-.md`. Harmless,
   but a byte-identical writer must reproduce it (not fixed here).
9. **No atomic writes anywhere in this area.** `persona.md`, `.claude/agents/<name>.md`,
   memory files and `MEMORY.md` are all plain `write_text`/`open`; the only concurrency
   defence is `O_APPEND` in the two jsonl stores and an flock around the dispatch *commit*
   (`charter/hooks.py:8206`). `MEMORY.md` is explicitly expected to drift and is reconciled
   by `index_drift` (`charter/memstore.py:217`).
10. **`_skills` rows are never committed by charter**, unlike `_dispatch`
    (`charter/hooks.py:8189` has no skill equivalent), although both are committed paths. So
    on a `share = "push"` plane the skill tally lags behind the dispatch tally. Possibly
    deliberate, possibly an omission.
11. **`_render_agent` reads `meta.get("vault")` for the MCP wrapper (`charter/commands_persona.py:877`)
    but `persona.vault_of(name)` for the credential prose (`:1067`).** `mcp_render_entry`
    normalises `none` via `mcp_vault`, so behaviour is right; the two spellings are still a
    latent divergence if `vault:` is unset and a tagged vault exists (the MCP path would see
    no vault, the prose would see the tagged one).
12. **Front-door personas get `.gitkeep` but no `MEMORY.md`/`refs/README.md`**
    (`charter/commands.py:2678`-`:2680`) while `persona create` gets the opposite
    (`charter/persona.py:2265`). Two scaffolds for one layout — a reader (and `doctor`'s
    index check) sees two shapes.

### In the vaults and the harness wiring

1. **Two different JSON encodings for the two vault-file providers.** `plain-file` writes
   insertion order (`charter/secrets/plain_file.py:91`); `reference` writes `sort_keys=True`
   (`charter/secrets/reference.py:194`). Both are 0600 `.json` files under
   `.charter/vaults/` with the same naming rule, so a byte-identical writer must branch on
   the provider. Deliberate or accidental is not stated anywhere.
2. **The reference provider chmods after writing** (`charter/secrets/reference.py:194`-`195`
   — `write_text` then `os.chmod`), which is exactly the window
   `PlainFileProvider._write_private` was rewritten to close (#437,
   `charter/secrets/plain_file.py:42`). A reference file holds no value, but it is the same
   pattern the codebase documents as a defect. Not fixed here; flagged.
3. **`charter secret set` never creates `fingerprint.key`; `charter secret get` does.**
   Measured. Any fixture that wants the key must run a masking read.
4. **`_plugin_dispatches_guard` always asks about `~/.claude`** even under
   `$CLAUDE_CONFIG_DIR` (`charter/commands.py:1230`), while `doctor` follows the
   variable. The code names this as a known divergence pending "per-profile wiring task 4".
   A second implementation must copy the asymmetry, not the variable.
5. **Whether `<plane>/opencode.json` should be marked stable-committed is decided by
   charter's own output, not by `.gitignore`** — nothing ignores it and `guard` prints
   "These files are committed". Confirmed by reading `_GITIGNORE_BASELINE`; no explicit
   statement in code that it is *meant* to be committed.
6. **`~/.config/opencode/command/charter.md` is create-only** (`charter/harness/opencode.py:982`)
   while the shim and the context file are refreshed. A command file from an older charter
   is never updated and nothing reports it stale — unlike the shim, which has `unvouched`.
   Possible gap; not fixed.
7. **`ensure_instructions` writes an absolute path into a machine-global config**
   (`charter/harness/opencode.py:682`). Moving `$XDG_CONFIG_HOME` leaves a dead entry, and
   nothing prunes it. Flagged, not fixed.
8. **Marker values are `str | list[str]`** (`charter/workspace.py:2440`). A consumer that
   assumes `str` will mis-read a plane killed mid-write. Worth stating explicitly in the
   doc.
9. `.charter/cache/harness-wiring.json` is marked **internal**
   (one module writes and reads it, safe to delete). It is borderline — two *processes*
   (the selector and a later selector run) read it, and a chat can write it, which is why
   `cached()` re-validates every field. If the doc's rule is "another process reads it", it
   would make it stable; the front matter's cache ruling is why it is not.
10. `.charter/unrecorded/<hash>.json` — same borderline: written by one module, read by
    `doctor` in a *different* process (`charter/workspace.py:2984` `unrecorded_reason`). I
    marked it internal because it is a diagnostic that regenerates; a stricter reading of
    the rule makes it stable.

### In `.charter/`

1. **`docs/control-plane.md:868` disclaims any format stability for `.charter/frame/`**
   ("no format version and never will … may change shape in any release"). The survey
   raised this as a conflict with an app that reads plane files; the ruling in "How to read
   it" settles it the other way — the app replaces the tmux frame rather than reading its
   state, so the disclaimer stands untouched. Recorded because the next person to want a
   fact that lives only in `frame/` will meet it: that fact has to be promoted here first,
   and `control-plane.md` amended in the same change.
2. **Nothing guarantees the `sessions/` sweep runs.** `_prune` unlinks any file in
   `sessions/` and `terminals/` past 30 days, `.ask-pending` included
   (`charter/workspace.py:881`-`:889`) — the survey's first reading of this was wrong, and
   the leave-behind on a declined ask is deliberate and tested, not a leak
   (`charter/workspace.py:875`-`:879`, #290). What is true is that the sweep only runs from
   `set_active`, so a plane whose operator does not switch workspaces never sweeps: 80
   markers had accumulated on the plane this was written against.
3. **`ws-edit-nudge/<sid>-<ws>` keys are ambiguous.** The key is
   `re.sub(r"[^A-Za-z0-9._-]", "", f"{session}-{ws}")` (`charter/hooks.py:7652`) — session
   `a` + workspace `b-c` and session `a-b` + workspace `c` collide. Harmless (one nudge),
   but a Rust reimplementation must copy the *exact* derivation to stay compatible.
4. **`dispatch-inflight` files are written by `tempfile.mkstemp`, not through `config`**
   (`charter/inflight.py:244`), so they bypass `open_for`/`STATE_FILE_MODE`. They come out
   0600 anyway, but they are the one writer in this area outside the dispatch. Is that
   deliberate?
5. **`unrecorded/` uses `config.mkdir_for`, not `private_mkdir`** (`charter/workspace.py:2976`)
   — equivalent today (the path is under the state dir, so `mkdir_for` dispatches to
   private), but it is the only state writer relying on the dispatch rather than saying
   what it means.
6. **Is `active-workspace` dead?** `config.py:804` derives it and nothing in the package
   reads or writes it. If the app should ignore it, say so in the spec; if any older
   charter still writes it, the app will see a file this doc calls dead.
7. **Where does `sessions/<sid>.persona` belong** — this area (it is a `sessions/` file) or
   the personas section, which documents them in full; the entries here are the
   `.charter/` view of the same files.
8. **`persona-state/trace/<sid>.jsonl` is read by the status line**
   (`charter/statusline.py:2078`) even though `persona-state/` is the personas section's.
   The "recorded ✎N" chip on the footer depends on it, so the app needs that file's format
   too — flagging the cross-area dependency.
9. **`cache/vaulthealth.json:detail` carries provider prose** that can include paths and
   account hints (visible in the live plane). If the app surfaces cache contents verbatim,
   that field needs the same handling as any vault-adjacent string.
10. **`frame/<chat>/brief` is written with no trailing-newline normalisation**
    (`charter/frame/state.py:2566`) while every sibling appends `\n`. A byte-identical
    writer must not "fix" it.
11. **Marker-file ordering is load-bearing in at least one place:** `.gate` must be touched
    *before* `.tools` (`charter/toolgate.py:808`). Any Rust writer that reorders them
    reopens #443. The survey did not enumerate every order dependency (the
    `session`/`session.durable`/`session.adopted` trio is the likely second one,
    `charter/frame/state.py:1023`).
12. **`frame/probe-1/` on the plane this was written against** is a `<prefix>-<pid>`-shaped
    frame id, not a chat id, and holds only `gather.json` + `version`. `frame_id()` gives
    the shape and `charter frame-probe` (`charter/news.py:1052`, `cmd_probe` at
    `charter/commands_frame.py:599`) is where the name plausibly comes from, but no writer
    in this tree mints `probe-1` itself — most likely an older release left it. A reader
    enumerating `frame/` should expect directory names it cannot account for.
