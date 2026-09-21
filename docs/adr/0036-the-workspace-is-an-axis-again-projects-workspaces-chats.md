# The workspace is an axis again: projects, workspaces, chats

The operator opened charter-app for the first time on 2026-09-21 and could not work out what a
tab was. His words:

> what is top level TABs? is it workspace?? or just general space? i cant get, where is
> workspace selector? as in current charter TUI - top level tab is workspace, and sessions are
> under workspace.

He is right to be confused, and this is a defect rather than a misunderstanding. In the tmux
frame the app replaces, **the top-level tab was the workspace** and the sessions lived under it;
that is the shape every day of charter's use so far has trained. In the port the top level
became the project ([ADR 0033](0033-a-plane-is-a-project-and-a-window-may-hold-several.md)) and
the workspace became a heading in the sidebar.

**Nobody decided that.** ADR 0033 argues at length for the project as a top-level tab and never
mentions what happens to the axis the frame already had there; the workspace is not in its
"what this costs" and not in its "what was rejected". The axis was lost in the transposition —
exactly the way the pane footer's behaviour was lost, which
[ADR 0029](0029-the-pane-footer-is-blanked-by-default-and-a-chat-may-keep-it.md) had to go back
and decide after the fact. This record is that decision, taken by the operator on 2026-09-21
after being shown three options.

## What the code did, measured

In `app/src/PlaneView.tsx`, before this record:

- `const [focused, setFocused] = useState<string>()` held a workspace name, and the only thing
  that set it was `Sidebar`'s `onFocus` and a fallback to `sidebar.workspaces[0]?.name`.
- What that name reached was exactly two things: `Panels plane workspace={focused}`, the
  read-only right-hand side, and `startIn` — the directory a new chat is started in, which is
  the only thing that files a chat under a workspace at all, because nothing on the plane
  records a chat.
- The chat strip drew `tabs.order`: **every chat in the project**, whatever workspace it was
  working in.
- `actions.ts` already listed a `workspace.focus:<name>` row per workspace. The palette could
  focus a workspace. It changed which panels were drawn and where the next chat would start,
  and nothing else moved.

So the workspace was not passive by design; it was an input to two features with no surface of
its own. The sidebar drew it as a `role="tablist"`, which promised a selection the rest of the
window did not honour.

## The decision

**Three levels, three strips.**

```
┌─ projects ───────────────────────────┐
│ [charter] [volaticloud] [umbrella] + │
├─ workspaces ─────────────────────────┤
│ [ide] [showcase] [default] [fleet]   │
├─ chats in `ide` ─────────────────────┤
│ [3 steward] [7 release] [12 forge] + │
└──────────────────────────────────────┘
```

**Projects are unchanged.** ADR 0033 stands whole: a project is a plane, a window may hold
several, switching between them is navigation and never a teardown, the registry and the
machine-level window set are as ADR 0034 describes them, and every open still goes through the
trust gate of [ADR 0035](0035-a-plane-is-untrusted-until-the-operator-opens-it.md). Nothing here
adds a way into a plane or a way past that gate.

**The workspaces of the project in front are a strip**, in the plane's own order, and focusing
one is the axis the frame had. It is the same `workspace.focus:<name>` row the palette already
listed — one place an action is written down, which is `actions.ts`'s founding rule — drawn as a
strip as well as browsed in the palette.

**The chat strip shows the focused workspace's chats.** Which workspace a chat is in is the
plane's answer: what relates a chat to a workspace is the directory it works in, read off the
sidebar the core builds. It is deliberately **not** a field recorded on the tab, because a copy
of the plane's answer is a second answer that nothing invalidates when the plane changes under
it. The one exception is the chat charter has just started, for the tick before the plane is
read again: charter chose that directory, so it knows.

Four rules fall out, and each of them is a way the axis could have been half-built:

- **Focusing a workspace brings one of ITS chats to the front** — the one that was in front
  there last — and a workspace with no chats puts nothing in front. Leaving another workspace's
  chat on screen under an empty strip would be the app drawing a chat the strip says is not
  there.
- **Nothing is ended and nothing is torn down.** A workspace the operator is not looking at
  keeps every chat it has running, exactly as a project behind another one does. This is the
  operator's own reason for wanting the arrangement at all, and it is the same guarantee, one
  scope down.
- **Bringing a chat forward from anywhere else brings its workspace with it.** The palette's
  `Switch to tab` rows and the needs-you queue both show a chat by bringing its tab to the
  front, and that chat can be in any workspace. The invariant is: the tab in front is always on
  the strip that is drawn.
- **Chats working outside every workspace get a strip of their own.** The sidebar has always
  shown them rather than dropping them; a strip per workspace has to have somewhere to put them
  or scoping the chats makes them unreachable, which is the defect being fixed rather than one
  to introduce.

**A workspace tab says how many chats are over there, and how many of them are asking for you.**
Scoping the chats hides forty of them behind a strip nobody is looking at, and the one thing an
operator must never lose is "something needs you". This is the mark the project tabs already
carry one scope up, for the same reason.

**The sidebar keeps listing every workspace and what each holds, and stops being a tablist.**
The strip is the axis; the sidebar is the listing, and the only place the operator can see every
workspace's chats at once. Two tablists for one axis is two answers to "which workspace am I
in" — the drift `actions.ts` exists to prevent.

## What was rejected

- **Keep one strip and make the sidebar a filter.** The cheapest by far: the chat strip stays as
  it is and the sidebar dims what is not in the focused workspace. Rejected because it is the
  state the app is already in, drawn more emphatically: the top-level tab is still the project
  and the workspace is still something that happens in a panel. It also does not fix the strip,
  which is the thing that breaks at fifty chats.
- **Workspace tabs with the project in a switcher.** Closest to the tmux frame, and the reason
  it lost is ADR 0033: the operator asked for Zed's shape by name, because eight projects is
  eight things to arrange and the thing an operating system gives you to arrange is a window.
  Demoting the project to a dropdown would reopen a decision that was taken on its own evidence.
- **A single strip of `workspace/chat` pairs.** One strip, every chat, each labelled with its
  workspace. It is not an axis at all: it is a naming convention, and at fifty chats it is fifty
  entries with a longer label.

## The consequence for the chat strip

The operator hit the chat strip at about fifty chats and found four defects
([charter-app#130](https://github.com/diazoxide/charter-app/issues/130)), and this record is
where the first of them is half answered: a workspace rarely holds fifty, so scoping the chats
takes most of the pressure off the strip. **Only most of it.** A strip still has to behave when
it overflows, and the projects and workspaces strips overflow too, so the four are fixed on
their own terms:

- **Overflow that is reachable.** Every strip scrolls, nothing in it is squeezed to nothing, and
  the tab in front is brought into view whenever the front changes — from the strip, from the
  palette, from the queue. **The `+` is not in the scroller**: as the strip's last child it
  scrolled away with the tabs, so the way to open the fifty-first chat was to go looking for the
  button, which is the same defect as an unreachable tab on the one control that is always
  wanted. **A scrollbar and not an overflow menu**, deliberately: the palette
  already lists every chat by name with a search and a ranking over it (charter-app#48), and the
  sidebar lists every workspace's chats, so a menu on the strip would be a third answer to
  "which chats are there" beside two that exist and are better.
- **A tab carries something an operator recognises**: `3 steward`, not `3`. A number is what a
  chat is called to charter. The persona is known at the moment a tab opens on both paths — the
  picker carries the operator's choice, and a chat put back at a launch carries its own — so it
  is never filled in later. The chat's own name is kept beside it, because that is what the core
  is told and what a split's chat is called.
- **The `×` is inline with the title**, which also stops the strip being two rows tall.
- **The words say that a close ends the chat.** `close_session` ends the program and takes the
  chat off the board. That is correct and it does not change — but `Close tab 3` reads as "hide
  this", and with fifty tabs and no undo an operator tidying up ends fifty live harnesses on
  that reading. The row is now `End chat 3 steward`, and it carries a note — "Ends the program
  it runs. There is no undo." — drawn beside the row in the palette and as the tooltip of the
  button that is only a glyph. The pane close and the project close say the same, for the same
  reason. **The behaviour is made legible, not different**: no confirmation stands between the
  operator and a close, because the price of one is fifty dialogs for the operator this is meant
  to protect.

## Consequences

- The window has three tablists, and every query for a tab in the app and in the scenario tests
  has to say which. They are named `Projects`, `Workspaces` and `Tabs`; the sidebar's list of
  workspaces is no longer among them.
- Closing a tab brings forward the tab beside it **in its own workspace**, and nothing when its
  workspace held nothing else. Reaching across to another strip would move the operator to a
  workspace they did not ask for.
- A window that has not read the plane yet shows every chat on one strip rather than none.
  Nothing knows which workspace a chat is in until the plane has been read, and hiding running
  chats is worse than showing them all for a moment.
- **Creating a workspace is not on the strip.** There is no `+`, because the Rust charter has no
  command that makes a workspace yet; the strip will grow one when it does. A `+` that opened
  nothing would be worse than its absence.
- The palette still lists every chat in the project, not only the focused workspace's. It is the
  find-anything surface, and narrowing it to the strip would make a chat in another workspace
  unfindable — which is what running it would then fix by focusing that workspace.
