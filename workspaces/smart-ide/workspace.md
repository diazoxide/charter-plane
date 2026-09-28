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
- Q27 (2026-09-27): a harness started at the plane root from a terminal IS a plane-root session (SI-1b #505 as built) — matches the operator's original "master space where a harness runs at plane root". The default-workspace rungs no longer answer for a session standing in the plane outside every workspace.
- Q25/Q26/Q28/Q29 (2026-09-27, operator agreed): curation on Codex via raw+1s-quiet ready rule (#509), opencode refused with measured reason; release as 0.4.0 (#508, operator tags); built-in curation prompts are one-liners naming the skill, persona lint warns when a prompt would collapse into a paste placeholder in any harness; a pending prompt is dropped as soon as the operator types into that chat.
- SI-8 Smart close, round 1 (2026-09-27, operator agreed): a **session record** = summary (goal, done, decisions, open, how to resume) + the harness session id, never the raw transcript; one file per record at workspaces/<ws>/sessions/<date>-<slug>.md + sessions/index.md (plane-root chats → plane-level sessions/); follows the workspace's LIVE/LOCAL; workspace.md gets a one-line `## Sessions` pointer to the index, and the skill folds durable decisions/terms/vision changes into their sections; clicking Smart close SENDS the prompt (own ADR, unlike curation's never-sent), skill `smart-close` for every harness; the skill's last step `charter session saved <path>` signals the app over the hook socket, which closes the tab; mid-turn → wait for Stop; timeout (~5 min) or error → tab returns to normal, never closes without a record; closing tab shows amber tint + slow pulse (static under reduced motion), menu "Cancel smart close", typing cancels; close dialog: Smart close (primary) / Close / Cancel, Close default when ≤1 turn.
- SI-8 round 2 (2026-09-28, operator agreed): (Q9) a Sessions panel per workspace lists records — open as a view tab, and Resume on the harness's own conversation id (if still held) with the record in its briefing; (Q10) every harness's conversation id is written back from hook reports (codex, opencode, Claude after /clear) — also fixes relaunch-resume; (Q11) send by state: Waiting → paste+Enter now; Running → queue until Stop; needs-you → refuse (answer first); never-prompted/Unknown → only Close; (Q12) v1 per-chat only, quit/close-workspace unchanged; (Q13) briefing gets one line "Last session: <title> — sessions/<file>"; (Q14) record = frontmatter (title, date, chat, persona, harness, conversation id, workspace, branches/pieces) + Goal/Done/Decisions/Open/How to resume, written via a validating `charter session record` verb that updates the index and sends the saved signal. Fact correction: the session-start briefing does NOT inject workspace.md.

## Glossary

<!-- Task/domain vocabulary so a teammate or a fork isn't lost: `term` — definition. -->

_Nothing yet._

## Log

Chronological "what was done" lives in the task memo — `memory/notes.md`
(append with `charter workspace note "…"`).
