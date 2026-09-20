# The Rust charter does not read the frame's launch record, and an operator on a frame-driven plane gets one wrong answer per chat

Python's workspace ladder has nine rungs. The fifth is the tmux frame's launch record —
`.charter/frame/<chat>/workspace`, written by `charter/frame/state.py:1384` when the frame
launches a chat and read back by `for_frame` (`charter/workspace.py:114`), where it sits above
the per-terminal pointer and below the per-session one.

charter-app's `charter` ports every rung but that one.

**The Rust charter does not read `.charter/frame/**`, and therefore has no frame rung.**
`docs/plane-format.md` rules that directory is the tmux frame's and that this binary "neither
reads nor writes there"; the app replaces that frame rather than inheriting its state. Reading
the record would mean reading state the format forbids it to touch, and the app writes no frame
record of its own — so the rung would be one nothing on this side can ever set. It is left out,
named in `crates/charter-core/src/active.rs`'s ladder table as *not ported*, and pinned by the
differential scenario `workspace-the-frames-launch-record-is-a-rung-in-python-and-not-here`.

## Where the two implementations can actually disagree

Not in most of a frame. Inside one, `$CHARTER_SESSION_ID` holds the frame's chat id (ADR 0019),
both implementations key `.charter/sessions/<sid>.workspace` on that same string, and the
session pointer outranks the frame record in Python. So every rung above the frame record
agrees, and the answer is the same.

They can differ in exactly one state: **the session pointer is absent and a frame record is
present.** That is a chat the tmux frame launched in which nobody has since run
`charter workspace use`. There, Python reads the launch workspace. The Rust charter falls
through to the per-terminal pointer, then `workspaces/.default`, then `[workspace] default` —
and on a plane that has nominated neither, to the built-in `default`.

The window is one launch wide. It closes the first time that chat selects a workspace, because
`charter workspace use` writes the session pointer, which is the rung *above* the frame record
and is read identically by both.

## What an operator on a frame-driven plane actually sees

A decision recorded without its consequence is half a record, so here is the consequence, in
the order an operator meets it.

**The wrong workspace is reported, not refused.** `charter workspace current` in that chat
prints `default` where charter printed the workspace the frame launched. The frame's own panels
keep showing the workspace they were launched for, because they are Python and read their own
rung — so the window and the binary inside it disagree, and the window is the one the operator
is looking at.

**A write lands in the wrong store, and says so only in the path it prints.**
`charter ws remember`, `charter ws todo` and `charter vision` resolve through the same ladder.
On that chat they write under `workspaces/default/` instead of under the workspace whose panels
are on screen. Nothing refuses, because by the ladder nothing is wrong: `default` is a legal
answer that a legal rung gave.

**A read comes back thin.** `charter recall` with no flags is how a harness opens a session. On
that chat it searches `default`'s memory and todos, so the digest the chat starts with is a
different workspace's — usually an empty one. An agent that is handed nothing behaves as though
there was nothing, which is the failure this is worth recording for.

**The rung it falls to is the one charter deliberately outranked.** This is the sharper half.
The per-terminal pointer is keyed on the first of `$TERM_SESSION_ID`, `$TMUX_PANE`, `$STY` and
`$SSH_TTY` that is set. Inside a frame that is a pane *charter* created, or the terminal the
whole frame was launched from and every pane in it inherited — neither of which is the chat.
`for_frame` puts the frame record above that rung for precisely this reason. Leaving the rung
out therefore does not drop to a quieter answer; on a recycled pane id it can read a pointer
that belonged to something else, which is a wrong workspace rather than a default one.

**The repair is one command, and it is permanent for that chat.** `charter workspace use <name>`
writes the session pointer. From then on both implementations answer from it, in that chat, for
as long as the chat lives.

## What bounds it

- The window is one launch wide, and any `workspace use` closes it.
- The app writes no frame record at all, so a chat the *app* started has no frame rung for
  either implementation to read: it sets `CHARTER_SESSION_ID` per chat, so the session pointer
  always decides. This is a hazard of the migration's mixed planes, not of the app.
- It closes entirely when the tmux frame retires at M4, at which point nothing writes
  `.charter/frame/**` and the rung has no subject in either implementation.

## The alternative not taken

Honour the frame record for the migration's duration and drop it at M4.

It is kept here rather than dismissed, because it is one flip of an existing scenario if
practice disagrees with this ruling: the divergence already has a differential scenario and a
CLI test naming the answer, so adding the rung is an edit to `active.rs` and an inversion of
two notes, not a design.

It was not taken because the reading it requires is the one `docs/plane-format.md` forbids, and
a binary that reads a directory it has declared out of bounds has no rule left — the next
reader of frame state has the precedent and not the prohibition. Weighed against a window one
launch wide with a one-command repair, the boundary is worth more than the rung.

## How it is pinned

- `workspace-the-frames-launch-record-is-a-rung-in-python-and-not-here`, in
  `tests/differential/run.py`, carries the divergence as a `stdout_differs` note. That note
  **fails the day the two agree**, so it cannot outlive the difference it records.
- `the_tmux_frames_launch_record_is_not_a_rung_here`, in `crates/charter-cli/tests/active.rs`,
  asserts *which* answer this side gives. The differential says only that Python answers
  something else, and an inequality is satisfied by any wrong answer.
- The ladder table at the top of `crates/charter-core/src/active.rs` carries the rung as a row
  marked *not ported*, so a reader counting rungs finds the gap named rather than missing.

## What this rules out

- Any read of `.charter/frame/**` from the Rust core, the CLI or the app — including a
  read-only one "just for the workspace".
- A write of a frame record by the app, to make the rung settable. The directory is the tmux
  frame's; a second writer is how two implementations come to disagree about a file.
- Silently promoting the per-terminal pointer to cover the gap, or keying it on anything else
  inside a frame. The pointer's id is the hazard described above, not the fix for it.
- Closing the divergence by making `charter workspace current` guess from the panels. Nothing
  on the plane records which chat a pane belongs to on this side; that is the same missing fact,
  asked in a way that looks answerable.
