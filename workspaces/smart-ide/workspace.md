# smart-ide

> **Living charter** for this workspace — its north star and shared context.
> Keep it current as the work evolves (edit this file, or `charter workspace vision "…"`).
> It's committed + shared for LIVE workspaces, and a fork inherits it — so anyone
> can pick up the task with full context. Never put secrets here (vault only).

## Vision

Make the charter IDE feel like a finished IDE: a master (plane-root) workspace, harness-driven curation actions (safe-remove / compact-and-improve) from right-click, full CRUD for every object (vaults, personas, todos, workspaces), a smooth harness pane (find, shift+enter, pixel scrolling), plain shell tabs with a harness-launch warning, drag-to-reorder tabs everywhere, and no accidental text selection on chrome.

## Context & decisions

<!-- Key facts, constraints, and design/architecture decisions found while working —
     the durable "why", not a chronological log. Grow this as you learn. -->

Grilling round 1–2 settled (2026-09-26, operator agreed to all recommendations):
- Delivery: one PR per point, order SI-7 → 4 → 6 → 3 → 5 → 1 → 2.
- SI-1: promote the existing "Outside every workspace" pseudo-workspace (app/src/actions.ts `OUTSIDE`) to a permanent, undraggable first icon tab; tooltip "Plane — chats here start at the plane root". Root chats default to persona steward, no workspace quiz. App sets CHARTER_WORKSPACE on every chat it starts (fixes: app never sets it; CLI ignores bare workspaces/<ws> cwd).
- SI-2: curation chat opens in a new tab; prompt is pasted as bracketed paste with NO Enter after the chat's first SessionStart hook report. Never auto-sent. Safe remove runs at plane root; Compact & improve of a workspace runs in it; persona ones at plane root. Not for todos/vaults (model never sees vaults).
- SI-3: vault + button in panel, delete = type-name AlertDialog. Personas: create dialog, remove + safe remove; edit = external editor + harness, no in-app editor. Todos: add / done / delete in panel.
- SI-4: Shift+Enter via attachCustomKeyEventHandler → per-harness newline sequence from the adapter (ESC CR default), verified live. Cmd/Ctrl+F = @xterm/addon-search over the pane buffer. Scrolling: measure first (alt-screen mouse wheel vs xterm scrollback), then smoothScrollDuration/sensitivity.
- SI-5: "New shell" catalogue action; shell tabs get claude/codex/opencode shims on PATH → `charter shell-guard <harness>`: warn, report over hook socket (tab banner "Open as chat"), exec real harness. Never blocks, never parses output.
- SI-6: @dnd-kit/sortable; reorder within pinned/unpinned group, crossing the boundary pins/unpins; order per machine like pins; amend ADR 0039. No drag-out-to-split.
- SI-7: user-select none by default on app chrome; opt in for xterm, inputs, markdown/memory bodies, errors, paths.
- SI-2 reshaped (round 3): **Curation action** = core abstraction: opens a new chat tab with a prompt pre-typed (never sent). Declaring persona runs it; `on:` lists subject kinds (workspace, persona, plane). Declared one file each at personas/<p>/curation/<id>.md (frontmatter label/on/runs-in, body = template); plane-format.md + ADR 0061 first. charter's own ship in the binary, ids `charter/…`, listed first, can't be overridden (clash → lint warning + dropped visibly). Template vars only {subject.kind,name,path} {plane.root}. charter prompts are plain language naming the skill (harness-neutral). Built-ins: Safe remove, Compact & improve, Add a curation action. Persona tab lists + deletes them; CLI `charter persona curation add|list|remove`; right-click "Curate ▸" + palette rows. Glossary: "Curation action" (avoid: action, quick action, macro).

## Glossary

<!-- Task/domain vocabulary so a teammate or a fork isn't lost: `term` — definition. -->

_Nothing yet._

## Log

Chronological "what was done" lives in the task memo — `memory/notes.md`
(append with `charter workspace note "…"`).
