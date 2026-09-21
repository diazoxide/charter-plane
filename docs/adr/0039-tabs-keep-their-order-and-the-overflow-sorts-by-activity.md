# Tabs keep their order, and the overflow sorts by activity

[ADR 0036](0036-the-workspace-is-an-axis-again-projects-workspaces-chats.md) made the chat strip
show one workspace's chats and fixed the four defects the operator found at fifty
(charter-app#130). It left the strip's *behaviour over time* undecided: whether a tab may move,
what happens when there are more than fit, and whether anything can be kept where it is. The
operator settled all three on 2026-09-21.

- **Fixed tab order.** Tabs do not reorder themselves.
- **One row, and a show-more overflow menu for what does not fit.** The menu is sorted by **last
  activity**.
- **Pinning at all three levels** — project, workspace and chat.

## Fixed tab order

**A tab that moves under the cursor breaks aiming.** An operator going back to the chat that was
third from the left goes there with their hand, not by reading; a strip that re-sorts on activity
turns every click into a read. This is what browsers do, and it is the one interaction convention
in this window that every user already has.

**This ratifies what the code does rather than changing it.** `app/src/tabs.ts` holds
`order: number[]`, appends on open (`[...tabs.order, id]`), removes on close, and never otherwise
touches it; ADR 0036's per-workspace view is a filter over that same list. So there is nothing to
build, and that is precisely why it is worth a record: the tempting change is small, it is
"helpful", and it will be proposed the first time somebody has fifty tabs and cannot find one.
The answer is that finding is the palette's job (charter-app#48) and aiming is the strip's, and
they are not the same job on the same surface.

## One row, and an overflow menu sorted by activity

**This reverses a decision ADR 0036 took explicitly, and the reversal has to be argued rather
than slipped in.** ADR 0036 says, in its own words:

> **A scrollbar and not an overflow menu**, deliberately: the palette already lists every chat by
> name with a search and a ranking over it (charter-app#48), and the sidebar lists every
> workspace's chats, so a menu on the strip would be a third answer to "which chats are there"
> beside two that exist and are better.

That reasoning was sound on its own terms and two of its three premises have moved:

1. **The sidebar is no longer one of the two answers.**
   [ADR 0038](0038-the-window-is-four-regions-and-what-has-no-region-is-named.md) re-purposes the left
   sidebar as a repo/worktree explorer. The listing of every workspace's chats goes with it. So
   the count is not "a third answer beside two" — it is a second beside one.
2. **A scroller is not an answer to "which chats are there" at all.** It is an answer to "can I
   reach the ones I cannot see", and only if you already know to look. The tabs past the edge are
   not merely un-clicked, they are un-*enumerated*: there is no affordance that says how many
   there are. A show-more control is the first thing on the strip that says "there are more".
3. **The palette premise is unchanged and remains the strongest argument against this.** It does
   list every chat, with search and ranking, and it is better at finding than any menu will be.

So the honest statement of the decision is: **the menu is not a find surface, and if it is built
as one it should not have been built.** It is the affordance that says the strip is not showing
everything, and the shortest path to the few tabs that scrolled off. The palette stays the way
you find a chat you cannot see.

**Sorted by last activity — there, and nowhere else.** This is the same rule as the fixed order,
from the other side. Activity-sorting is right where it helps you find something you cannot see
and wrong where it moves something you are aiming at. The menu is a list you read; the strip is a
surface you aim at. One rule, two opposite behaviours, and the boundary is whether the thing
moves under your hand.

**"Last activity" does not exist as data today**, and whoever implements this has to produce it
before they can sort by it. Read off the tree on 2026-09-21: `chatState.ts` holds
`bySession: Record<number, State>` and `needsYou: number[]`, the `Moved` event carries
`plane`, `session`, `state`, `needs_you` and `queue`, and `OpenChat` has no timestamp of any
kind. Nothing anywhere records *when*. The needs-you queue is ordered oldest-first, which is the
closest thing that exists and is not the same fact. This is a new field, and the place it belongs
is the core that already pushes `chat-moved` — an ordering computed in the window would restart
at every launch and disagree between two windows on one plane.

## Pinning at all three levels

The operator asked for this explicitly: a project, a workspace and a chat can each be pinned.
Nothing in charter-app pins anything today.

Each level stores its pin somewhere different, and the three places are already decided by other
records:

- **A project** is a plane, and which planes this machine knows is machine state outside every
  plane ([ADR 0034](0034-charter-keeps-a-little-state-outside-every-plane.md),
  `crates/charter-core/src/machine.rs`). A project pin belongs there. That module's doc comment
  says **"Three things, and nothing else"** and then lists them; a pin is a fourth. **This needs
  an amendment to ADR 0034 rather than a quiet extra field**, because the "nothing else" is the
  whole reason a file outside the plane was allowed to exist at all.
- **A workspace** is a plane fact, in `charter.toml` and the directories beside it, committed and
  travelling with the clone. So a workspace pin written to the plane is **shared with everyone who
  clones it** — which may be exactly right (a plane saying which workspace matters) or exactly
  wrong (one operator's arrangement imposed on the next). **This record does not rule**, and
  whoever implements it is deciding it: if a pin is a personal arrangement it cannot live in
  `charter.toml`, and if it is a plane's own emphasis it must.
- **A chat** has no home on the plane at all. ADR 0036 states it: *"nothing on the plane records a
  chat"*, and what relates a chat to a workspace is the directory it works in. The only record of
  a chat is the app's own `.charter/app/reopen.json` (`crates/charter-core/src/reopen.rs`), which
  is per-plane, per-app, and versioned — `VERSION: u32 = 1`, and a record of any other version is
  ignored whole. **A chat pin is therefore an app record and a format version bump**, not a plane
  fact, and a pin that survives a relaunch survives only because that file did.

**Three levels is three storage decisions, and none of them is the same as another.** A design
that treats "pin" as one feature will discover this in review.

## The measured constraint the implementation inherits

**The `+` stays outside any scroller, and outside any overflow collapse.** As the strip's last
child it scrolled away with the tabs, and the scenario run measured exactly that:
`app/e2e/specs/panes.e2e.ts` opens fifty sessions by pressing `New tab` in a loop, and it could
not press it partway through (charter-app#130, fixed in charter-app#131). The comment above
`<div className="adding">` in `PlaneView.tsx` records the reason.

**A show-more menu is the same hazard wearing different clothes.** The failure was not "the
scroller ate the button" — it was "the always-wanted control was inside the thing that hides
controls". A menu that collapses the strip's tail can eat the `+` the same way, and the e2e run
is the thing that will notice.

## What is left open

- **Whether the row still scrolls.** The operator said one row with a show-more menu. If the menu
  is what makes the hidden tabs reachable, ADR 0036's scroller has done its job and may go; if
  both stay, there are two overflow mechanisms on one strip. Not ruled, and worth ruling before
  it is built.
- **Whether a pinned tab is exempt from overflow.** It is what pinning means in every browser
  that has it, and the operator did not say. If it is not exempt, pinning a chat buys only a
  marker.
- **Whether the three strips behave alike.** ADR 0036 made projects, workspaces and chats all
  scroll. This record's operator statement is about tabs; applying it to all three is the obvious
  reading and is not what he said.

## What was rejected

- **Activity-sorted tabs.** The thing this record exists to refuse. It is genuinely useful right
  up to the moment you reach for a tab you have reached for a hundred times.
- **Two rows of tabs.** Cheap, and it defers the problem by exactly one row. It also costs a row
  of the centre region permanently, in a window that already carries three tablists above the
  panes.
- **A scroller alone**, as ADR 0036 decided. Argued above: it makes hidden tabs reachable and
  never says they exist.
- **The palette as the only overflow.** The status quo plus a scroller, and the position ADR 0036
  took. It is still the best *find* surface and it is still not an affordance on the strip.
- **Most-recently-used tab order, browser-tab-switcher style.** Rejected with activity-sorting,
  and for the same reason: it is the same moving target with a different trigger.

## Consequences, including the ones that cost something

- **ADR 0036's overflow bullet is superseded in part.** Its `+`-outside-the-scroller rule stands
  and is reinforced here. Its "a scrollbar and not an overflow menu" no longer holds, and the
  premise that changed is the sidebar's job, which ADR 0038 changed.
- **The core grows a timestamp per chat.** `chat-moved` is pushed on every hook and every exit,
  at fifty live sessions. A field on an event that already fires is cheap; a new event is not.
- **Three pins, three stores, and one of them needs another ADR amended.** ADR 0034's "three
  things, and nothing else" is a boundary that was argued for, and adding to it is a decision
  about the machine-state file rather than about tabs.
- **A pinned chat outlives the thing it pins, or it does not.** `reopen.json` restores chats at a
  launch; a pin on a chat that did not come back is a dangling pin, and the file's own rule is
  that an unreadable or version-mismatched record reads as "nothing to put back". A pin has to
  disappear with it.
- **The menu is the fourth surface in this window that needs keyboard behaviour**, after three
  tablists and four dialogs. [ADR 0037](0037-charter-takes-the-behaviour-and-keeps-the-look.md)
  decided it comes from a headless primitive and not from a fourth hand-written `ArrowDown`
  handler. This is the first thing built under that rule, so it is the test of it.
