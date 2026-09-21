# The window is four regions, and what has no region is named

[ADR 0036](0036-the-workspace-is-an-axis-again-projects-workspaces-chats.md) gave the workspace
its axis back and left a question it had to open: **if the workspace strip is the axis, what is
the left sidebar for?** The sidebar was listing every workspace with its full vision text — the
same axis the strip above it had just been given, drawn twice, one of them a tablist that ADR 0036
had to demote in the same breath. The operator asked the question directly. This record is his
answer, taken on 2026-09-21.

**Four regions, and each one holds a kind of thing rather than a list of features.**

| region | holds |
| --- | --- |
| **Left sidebar** | a repo / worktree **explorer** — the selector *within* a workspace, because one workspace holds several repos and several worktrees |
| **Right sidebar** | personas, todos, the **needs-you queue**, alerts |
| **Bottom bar** | repo git state, worktrees, pipelines (CI) |
| **Centre** | the terminal panes |

## The reading, which is this record's and not his words

The operator specified the table. He did not give a rule for it, and one is offered here so the
next surface has somewhere to go rather than landing wherever there is room: **the left is
navigation, the bottom is state.** The left is where you go to change what you are looking at;
the bottom is where you read what is true and do not touch it. The right is neither — it is what
is asking for you, which is why the needs-you queue and the alerts sit together there.

**This is an interpretation and it is marked as one. If it is wrong, the table stands and the rule
is corrected.** A rule inferred from four rows is exactly the kind of thing that hardens into a
decision nobody made, which is how ADR 0036 and
[ADR 0029](0029-the-pane-footer-is-blanked-by-default-and-a-chat-may-keep-it.md) each came to be
written after the fact. Writing it down as inference is the only way it can be argued with.

The reading does have a visible seam, and naming it is better than hiding it: **worktrees appear
in two regions.** On the left they are what you select; on the bottom they are what git says
about them. Under "left navigates, bottom reports" that is consistent. Under any other reading it
is a duplication of exactly the kind this record exists to remove, and it is the first thing to
re-examine if the rule turns out to be wrong.

## What the left sidebar was, and why it had to change

Read off `app/src/Sidebar.tsx` on 2026-09-21: it renders every workspace as a button, each with
`<p className="vision">{ws.vision}</p>` and every chat under it. Its own doc comment already
argues the boundary — *"This is a listing, not the axis"* — and ADR 0036 already made it stop
being a `role="tablist"`. That was the correct minimum at the time and it does not go far enough:
a listing of the axis, under the axis, with the long-form vision text of every workspace in it,
is still the strip's question answered a second way in more words.

**The workspace listing is not what the left is for.** What the left gets instead is the level
ADR 0036's three strips do not reach. Projects, workspaces and chats are three tablists; a
workspace holds **several repos and several worktrees**, and nothing in the window selects one.
The plane already knows them — `workspace_repos` and `worktree_list` are Tauri commands today
and `Panels.tsx` draws their git state read-only, on the right. The explorer is the selector
those facts have never had.

## What the right sidebar already holds, and what it does not

The needs-you queue is further along than a gap list would suggest, and this record would be
wrong to describe it as absent. `app/src/NeedsYou.tsx` is a real component: it lists every chat
that asked, by name, each a button that brings that chat forward; it names the chats that *can*
be waiting without saying so (`quietOnes`, charter-app#52); and its two empty states are
different claims, deliberately — "Nothing needs you" when every open chat can report, and
"Nothing has said it needs you" when one cannot. `App.tsx` carries the count per project tab and
`PlaneView.tsx` carries it per workspace tab (ADR 0036).

What is true is **where it is**: `<NeedsYou>` is rendered inside `<header className="bar">`, in a
row with the tab strip, the `+`, the split buttons and the plane path. A queue that has to work
at fifty chats is sharing a line with six other things. Moving it to the right sidebar is this
decision; building it is not, because most of it exists.

**Alerts are the opposite case: the surface is assigned and there is nothing to draw.** charter's
footer has an alert row in zone 2 (`charter/statusline.py:_alerts`), and it is not ported —
`crates/charter-core/src/footer.rs` names the omission in the output rather than hiding it:

```
not drawn by this build: repos · personas · alerts · session
```

That line is there on purpose, and its own doc comment gives the reason this record inherits:
*"a footer that silently omitted the alert row would be worse than a sentence, because an
operator reads a footer to find out whether anything needs them, and one that can only ever say
'nothing' is a footer that lies once a week."* **A right sidebar that has an alerts area and no
alert source tells the same lie.** Whoever draws the region draws the sentence until the port
exists.

## What has no region, recorded as open

These are named as gaps, not scheduled as work. Each one is a fact charter already has, or
already computes, with nowhere in the window to be. **None of them is decided by this record**,
and the reason they are in it is that a four-region table is exactly the document a later reader
will use to conclude that anything not in the table was considered and dropped.

- **The `ctx` and `cache` gauges have no home, and the history they need is being written.** The
  gauges are zone 3 of charter's own footer. [ADR 0019](0019-the-frame-owns-the-surface.md)
  recorded the gap for the tmux frame — *"A framed Claude Code session has no context/cache gauge
  on any surface"* — and **that bullet is marked closed by #413**: the frame's top strip draws
  `statusline.recorded_context_gauge` from the recorded history, and `statusline.main` writes the
  harness-session mapping because it is the one process that sees both ids. **charter-app has no
  equivalent closure.** ADR 0029 states the position for the app in as many words: *"charter's
  Rust footer does not draw them yet either."* `footer.rs` draws zone 1 and the sentence above.

  The recording side is alive and the drawing side does not exist. `usage::record` is called from
  `crates/charter-cli/src/statusline.rs`, which is the side effect ADR 0019 exists to protect —
  so the history is accumulating. What is *not* ported is a renderer: `usage::rows_at` is a
  private helper of the writer, called only by `record_turn` to rewrite the file it keeps, and
  it has no caller outside its own module. The app exposes no command for any of it.

  And it is **per-chat** information in a window with fifty chats, which is why it fits no region
  in the table: a gauge in a sidebar describes the focused workspace, and `ctx` describes one
  conversation. The chat's own tab and the pane's corner are the two places suggested. **The
  operator has not ruled, and this record does not rule for him.**
- **Alerts.** Assigned to the right sidebar above; nothing to draw, per the section above.
- **Usage and the token trend.** Same history, a different view of it — the trend over a
  session's turns rather than this turn's percentage. Zone 3. Nothing renders it and, as above,
  no renderer was ported.
- **News, and "an update is available".** `crates/charter-core/src/news.rs` is ported and
  `charter news` works. The app has no command for it, so an operator who never types `charter`
  in a pane is never told an update exists.
- **`doctor`.** `crates/charter-core/src/doctor/` is ported across twelve modules and is CLI
  only. It is the thing an operator reaches for when something is wrong, and in a window whose
  whole premise is not typing `charter`, it is reachable only by typing `charter`.

The app's full command surface was read to check this: thirty-four `#[tauri::command]`
functions, none of them `news`, `doctor`, `usage`, `alerts` or `footer`.

## What was rejected

- **Keep the workspace listing in the left sidebar and add the explorer below it.** The cheapest
  change, and it keeps the duplication that caused the question. The sidebar would then answer
  "which workspace" (already answered by the strip) above "which repo" (answered nowhere), and
  the answered one is the one with the long text.
- **Put the repo/worktree explorer on the right, beside the git state it describes.** Tidy, and
  it collapses the seam named above. Rejected because it makes the right sidebar both the thing
  that asks for you and the thing you navigate with, and the needs-you queue is the one surface
  in this window that must never be competed with.
- **A single collapsible sidebar with panels, Zed-style.** The reference is Zed and Zed does
  roughly this. Rejected for now because it is a different decision — it is about how regions are
  arranged, and there is no agreement yet on what goes in them, which is what this record is.
- **Decide homes for the five gaps now.** Rejected by the operator not ruling. Recording them as
  named gaps is the alternative to either inventing a placement or letting the absence read as an
  intention.

## Consequences, including the ones that cost something

- **The window grows two regions it does not have.** There is no bottom bar and no right sidebar
  today; `Panels.tsx` is a panel and `NeedsYou` is in the header. This is a layout change across
  `PlaneView.tsx`, and every scenario spec in `app/e2e/specs/` finds its elements by role and
  label inside that layout.
- **The left sidebar loses the only place every workspace's chats can be seen at once.** ADR 0036
  gave it that job explicitly — *"the sidebar is the listing, and the only place the operator can
  see every workspace's chats at once"* — and re-purposing the region takes it away. The palette
  lists every chat in the project with a search over it (charter-app#48), and the workspace strip
  carries the per-workspace counts and the needs-you marks. **That is the replacement, and it is
  a genuine loss of the at-a-glance view, not an equivalent.** If it is missed, the honest fix is
  a view of its own, not the vision text coming back.
- **Worktrees are drawn in two regions.** Named above. Consistent under this record's reading and
  a duplication under any other.
- **Four regions plus three tablists is a dense window, and the density is the product.**
  ADR 0026 measured fifty sessions and twenty panes on screen; ADR 0019 budgets its own strips in
  columns. A region that cannot degrade when the window is narrow will be the first thing that
  breaks, and nothing here says how any of them degrade.
- **The five gaps are now a list somebody can close.** That is the point of naming them. It is
  also a list that will be read as a backlog, and it is not one: three of the five (`ctx`/`cache`,
  usage, alerts) need a renderer written before any region can hold them.
