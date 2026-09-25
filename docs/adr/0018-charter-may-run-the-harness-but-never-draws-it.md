# Charter may run the harness, but never draws it

ADR 0015 settled where charter sits relative to a harness it lives *inside*: "Charter
targets harnesses, not one host. It keeps only the policy the current harness cannot
express… where a harness's ceiling is lower, `charter doctor` names the deficit by name."
That ADR's whole shape assumes charter is a guest — a hook, a status line, a plugin —
running inside a process someone else started.

`charter <harness>` inverts the relationship it describes. Charter is no longer only the
guest; for this command it is the process that **starts** the harness, in a frame it
composes around it — the harness in the middle, charter's own panels on the edges. That is
a second question ADR 0015 never had to answer, and answering it wrong twice — first by
guessing wrong about what the boundary even is — is why it gets its own record rather than
a paragraph appended to that one.

## The candidate that looked obvious

The natural instinct, having already built `charter/tui.py` and a status line, is to keep
going: read the harness's own stdout, parse its escape sequences, draw the whole frame with
one renderer charter owns end to end. A spike built exactly that — a Textual widget backed
by `pyte`, a terminal-in-a-terminal, running `claude` and `opencode` inside it.

It worked. Both harnesses rendered correctly. That is precisely why this had to be settled
by measurement rather than argument: a design that fails outright is easy to reject, and
this one did not fail.

## What was measured

darwin, Python 3.14.4, `textual` 8.2.8, `pyte` 0.8.2, tmux 3.7c, a 150×42 frame, one
agent-shaped corpus (an ordinary Claude Code session's own output, replayed).

| | Textual + pyte | tmux, end to end |
| --- | --- | --- |
| throughput | **1.85 MB/s** | **25.2 MB/s** |
| parse alone | 2.4 MB/s (0.9 MB/s with scrollback enabled) | ~37 MB/s |

Rendering itself was never the bottleneck on either side — Textual's own paint measured
7.2 ms/frame, a 138 fps ceiling nowhere close to being reached. The gap is the parse:
`pyte` interpreting the harness's escape sequences in Python, against tmux's own C parser
doing the identical job roughly fifteen times faster, and scrollback made `pyte` alone
almost three times slower again. Two implementations of the same well-specified problem —
one already correct and shipped in every environment charter runs on, one freshly written
in the language charter happens to be written in.

**Both arms rendered `claude` and `opencode` correctly.** This was a cost decision, not a
feasibility one — the kind of decision measurement resolves and argument alone does not,
because "which one is faster" and "which one is right" are different questions and only
the spike could answer the first.

## The half a benchmark cannot show

Speed is the half that is measurable in an afternoon. The half that is not: what the
Textual/pyte widget was, and was not, at the moment it was measured. It drew text. It did
not draw a cursor. Still owed, unwritten: mouse, scrollback beyond raw buffer access,
bracketed paste, OSC sequences, wide characters, and `?2026` (synchronized output) — each
one a real terminal behaviour a real coding-agent session produces, and each one a place
`pyte` could silently render something subtly wrong rather than fail loudly. `pyte` itself
was last released 2023-11-12 — a terminal parser is exactly the kind of code where a
one-cell drift in cursor math shows up as a garbled screen months later, on somebody else's
terminal, and the library that would need patching is not actively maintained.

This project ships `dependencies = []` — every dependency is a promise to keep re-checking,
by hand, forever. Owning a terminal emulator would mean owning the correctness of
`\x1b[?2026h`, of double-width CJK glyphs, of an OSC 8 hyperlink escape, indefinitely,
in a widget that at 120 lines had implemented perhaps a third of what a real one needs —
against tmux, which has already solved this problem, ships on every machine charter already
requires, and needs nothing from charter to keep solving it.

## The decision

**tmux composes the rectangles and does every part of terminal emulation. Charter draws
only its own panels — the edges — and never touches the harness's own pane: never reads
its output, never parses its escape sequences, never decides what a cursor or a colour
means inside it.** `charter/frame/tmuxctl.py` is the one module in the codebase allowed to
shell out to `tmux`, precisely so this boundary has exactly one place it could be crossed
by accident.

Read the other direction, the same rule is ADR 0015's boundary, moved: that ADR drew the
line at what a harness can express and let charter's own reach change harness by harness.
This one draws a line at what charter *runs*, and keeps that line fixed regardless of which
harness is on the other side of it — the frame is identical whether the pane inside it is
`claude`, `codex`, or a command charter has never met (`charter frame -- <cmd>`), because
charter never has to understand what is in that pane to draw around it.

## Consequences

* Charter's frame code needs no terminal-emulation dependency at all — `dependencies = []`
  survives this feature.
* The floor for `charter <harness>` is tmux's own version (3.2 for the frame's menu, 3.3
  for its resize-recovery hook — `charter/frame/tmuxctl.py`), not a Python library's
  release cadence.
* Charter's panels stay simple by construction: a top/bottom strip is one line, measuring
  its own pane and repainting whole on every change charter's own hooks report — there is
  no cursor, no scrollback, no input focus for charter's own code to get subtly wrong,
  because none of that is charter's to draw.
* The harness's own pane keeps every terminal behaviour it already has, including ones
  charter has never heard of, because tmux is already handling it and charter never gets
  between the harness and the terminal it is actually talking to.
* A future feature that genuinely needs to read the harness's own output (say, to react to
  what it printed) needs its own measurement and its own ADR — this one settles rendering,
  not observation, and conflating the two is how a boundary like this erodes one convenient
  exception at a time.

## Amendment, 2026-09-01: charter reads that pane at two moments, and draws in it at none

The bullet above asked for a measurement and its own record before charter read the
harness's pane. **The measurement showed charter was already reading it**, and had been
since #384 — so what follows is a correction to this ADR's own description of the code
rather than a new permission granted to it.

`commands_frame._pane_last_words` runs `tmux capture-pane -p -S -` on the harness pane on
**both** launch paths, and its docstring records the 3.7c measurement that put it there: a
registered harness whose binary is missing produced *zero bytes* of output and exit 127, and
that capture is the only thing that turns it into a sentence. §4f of
`docs/superpowers/specs/2026-08-30-charter-opens-like-an-ide.md` then asked for a second
read: tmux history dies with its session, so quitting a plane discards every visible
transcript, and *"less invasive"* cannot mean that.

So the rule is stated as it actually holds, rather than as a prohibition with two
undocumented exceptions:

**tmux composes the rectangles and does every part of terminal emulation. Charter draws only
its own panels — the edges — and never draws in the harness's own pane, never parses its
escape sequences, and never decides what a cursor or a colour means inside it. It READS that
pane at exactly two moments, both of which are moments the pane is about to stop existing:**

1. **a harness that died before the frame was drawn** (`_pane_last_words`) — the only chance
   to say anything at all, because nothing is ever drawn on that path;
2. **a chat being stopped by `charter: quit`** (`_capture_transcript`) — bounded to the last
   2,000 lines and 512 KB, written to that chat's own file under `.charter/frame/`, and
   **offered on the way back rather than replayed**. `F2 → chat: previous transcript` opens
   it in a pager in a window of its own; the reopened harness's pane starts clean.

**Both exceptions are bounded by the same property, and it is the property that keeps this a
boundary rather than a preference: charter reads only what is about to be destroyed, and
writes nothing back.** The two failures this ADR was written against — owning a terminal
parser, and drawing where tmux draws — are untouched by either. Nothing here parses an
escape sequence: `-e` keeps them and `-N` keeps the trailing spaces `-e` alone trims, and the
bytes go to a file and to `less -R`, both of which understand them better than charter would.

**What is still refused, sharpened rather than repeated.** Reading that pane to *react* to
what it printed — a hook on its output, a parse of its state, a decision made from its
content — is still a different feature and still needs its own measurement and its own
record. The distinguishing question is now written down so the next reader does not have to
infer it: *does charter read this pane at a moment it is ending, and does it write nothing
back?* Two yeses is this amendment. Anything else is a new one.

**Measured cost, because "capture it" is not free.** One 200-column pane at charter's shipped
`history_limit = 50000` took the shared tmux server from 3.7 MB to **130 MB**, and
`capture-pane -p -S -` pipes that whole history through charter's own process. That is why
the capture asks tmux for the last N lines (`-S -2000`) rather than for everything and
trimming afterwards: the bound belongs where the memory is. Verified on tmux 3.7c and at the
3.2 floor.

## Amendment, 2026-09-12: before the `exec`, that pane is charter's own

Harness profiles put a charter process in the pane. `charter frame-launch --profile <name>`
is what tmux now starts in every chat pane, and it becomes the harness by `os.execvpe`
replacing itself with the profile's command (`charter/frame/launcher.py`). Before that
happens, charter may write on that screen, and there are exactly three things it writes.

**A refusal** — the local file became committable since the pre-tmux check, the command is
not on `PATH`, the `execvpe` itself raised — goes into the pane, and where somebody is at
the keyboard the launcher **holds the pane open until they press Enter.**

**A question** is the second, and it is the only one of the three that READS from the pane
as well as writing to it. A profile whose command or environment is new or has changed
since it last ran is not refused where somebody is in front of it: the launcher prints what
it would run and reads one line, `run this? [y/N]` (`charter/profiletrust.py`, and the
plan's *A new or changed command asks once*). A no starts nothing and exits on the
workspace picker's own cancel code, saying nothing more — the operator has just answered.
Where the question cannot be answered it is a refusal instead, which is the bound below.

**A claim to a chat that cannot be proven** is the third, and it is not a refusal either:
the launch goes ahead. `launcher.framed_chat()` asks tmux whether this process's own pid is
the `#{pane_pid}` of a live pane belonging to the chat it was handed, because `$TMUX_PANE`
and `$CHARTER_SESSION_ID` are inherited by a model's tool shell and prove nothing. A claim
that does not check prints one line saying so and returns `None`, and the launcher then runs
as a launch with **no frame** — it records nothing for that chat, which is the point of the
proof. Silently downgrading would cost a chat its session id and its resume id with nothing
said, so the sentence goes where the person watching is: the pane the harness is about to
take over.

All three are charter writing in a chat's pane — and the question reads from it too — which
the rule above says it never does. The rule is right and this is not an exception to it,
because of *when*: **no harness has ever run in that pane.** The `exec` has not happened —
or it was attempted and raised, which leaves the same pane with the same charter process in
it and no harness either way — so there is no
harness process, no output of its own on that screen, nothing to draw over and nothing to
parse. Every failure this ADR was written against needs a harness on the other side of the
pane to occur at all — owning a terminal parser, deciding what somebody else's cursor means,
painting over somebody else's frame — and none of them is reachable before the process that
would produce them exists.

**The distinguishing question, in the same shape as the one above:** *has a harness ever run
in this pane, and is charter's own process still the one in it?* No and yes is this
amendment. Anything else is the rule as written: the instant `execvpe` succeeds the pane is
the harness's, `state.record_launch` says so, and nothing charter owns writes there again.

**Why the refusal cannot simply be printed and exited on, which is the whole reason this is
a decision and not a detail.** Measured 2026-09-11 on tmux 3.7c and at the 3.2 floor, 40
runs, in the pull request that shipped this launcher
([#981](https://github.com/diazoxide/charter-plane/pull/981)): `_launch`'s eager
`#{pane_dead_status}` ask completes **6-14 ms** after the start while a Python launcher's
first line runs at **19-22 ms**, so the ask is almost always too early to catch a refusal —
and by the time anything else could look, the chat-teardown hook has killed the window.
`_pane_last_words` answered `[]` in all 40 runs on charter's own server. (Almost: a loaded
CI runner once let the ask land after the launcher had refused and exited, and the refusal
was lost — [#1067](https://github.com/diazoxide/charter-plane/issues/1067). An unattended launch
now reads the record whether or not that ask found the pane dead.) A refusal printed
and exited on is a refusal nobody reads: the window carrying it is gone before the sentence
can be collected. So the pane has to hold it, and holding it is the part that needs this
record.

**Bounded, and each bound is checkable from outside.**

* **Only while no harness has ever run in that pane** — the distinguishing question above,
  and not the pair this amendment first wrote, *only a refusal, and only before the `exec`*.
  Each half of that pair is wrong exactly once: an unproven chat prints a line that is **not
  a refusal**, and an `execvpe` that RAISES prints its refusal **after** the exec was
  attempted. Neither leaves a harness in the pane, which is why the rule survives both and
  the pair did not. The bound is checkable from outside because there is one moment it
  turns: `state.record_launch`, written the instant the pane stops being charter's.
* **Three kinds of line, and charter wrote every one.** A refusal, plus `press Enter to
  close this chat.` where the pane waits; the approval prompt, which is the profile's
  command and environment on rows of their own and then `run this? [y/N]`; or the one line
  an unproven chat prints before launching anyway. No escape sequences of charter's own, no
  panel, no layout, and never a fourth thing later.
* **The prompt is escaped AND whole, and those are two promises.** Every byte of it outside
  printable ASCII comes out as a reversible escape (`contain.escaped`, ruling 35), because
  it comes from a file a chat can write and an ESC in it could redraw the question to show
  one command while another is approved. And **nothing is clipped**: a sentence bounds what
  it quotes, because a sentence ends in a remedy that a long value would push off the
  screen, but a prompt exists to be read before it is answered, and a command approved with
  its tail unseen is what the ask is against. It wraps. The refusal sentences are the other
  kind of surface: they quote a profile's name only to say which one, and bound it with
  `contain.readable`'s fixed `...` marker, as every refusal Task 2 shipped does. A row the
  operator chooses or approves from — a selector row, a doctor row — says how much it kept
  back; the prompt never has to.
* **The question is asked only where it can be answered.** Both of the pane's ends must be a
  terminal (`profiletrust.can_ask`), and the open must be an attended one. A pane that fails
  either test is refused with a sentence rather than asked, because a question nobody can
  answer is a chat that never starts and never says why — which is the same failure the wait
  below is bounded against, one moment earlier.
* **Every refusal the pane SAYS is recorded, and only the WAIT is conditional.**
  `_refused_in_pane` writes the sentence into the chat's state directory on every path it
  runs (`state.record_launch`), the attended one included, where the launch that opened the
  chat reports it. What an attended open adds is the wait — and that needs two conditions
  rather than one: the open must be ATTENDED **and** the pane's stdin must be a terminal,
  because `_wait_for_the_operator` returns at once when `sys.stdin.isatty()` is false. So an
  attended launcher run out of a pipe prints and exits, and a reopen, a handoff or a
  background open never stops at all.
* **A decline is the one exception, and it is not a hole.** `cmd_frame_launch` returns on it
  before `_refused_in_pane` runs, so nothing is said in the pane and nothing is written under
  the chat. Both are right: the operator answered this question themselves a moment ago and
  was told `charter: nothing started.` as they did, so there is no sentence they have not
  read. On charter's own server nobody reads the record for it either: a decline is
  reachable only from an ATTENDED open, and `_await_the_launcher` is asked only by an
  unattended one. **In an operator's tmux it reads worse, and says so here:**
  `_launch_in_operator_tmux` reads the record whether or not the open was attended, so a
  decline there that races the eager check, or a press whose streams are `/dev/null`,
  reports the window gone with charter's unknown-death code rather than "nothing started".
  That is a less exact sentence, not a hole — nothing ran, and the decline was answered on
  the terminal that asked. A refusal charter decided still records; the one the operator
  decided does not need to.
* **A line, not a keystroke.** Waiting on one keypress means putting the pane's terminal
  into raw mode, and a `tcsetattr` from a pane on a Linux CI runner left the launcher killed
  by a signal — an empty `#{pane_dead_status}` — so the refusal went with the window after
  all. The pane's own line discipline does the waiting instead: no mode change, nothing to
  restore, nothing of the terminal's state for charter to get wrong.
* **Reading the harness is untouched.** This amendment adds a WRITE before the harness
  exists, and one READ OF THE KEYBOARD — a line off the pane's stdin, through its own line
  discipline — which is not a reading of the pane at all: there is no output on that screen
  but charter's own, and nothing is parsed. The two reads of the harness's pane that the
  2026-09-01 amendment allows are unchanged, and charter still never reads this pane to
  react to what a harness printed in it.

Recorded here rather than in the records task that closes this phase, because the code that
relies on it shipped in the same pull request
([#981](https://github.com/diazoxide/charter-plane/pull/981); the rule is *an ADR amendment ships
with the code that first relies on it*, `docs/superpowers/plans/2026-09-11-harness-profiles.md`,
Task 6): otherwise `main` carries an unqualified prohibition while the code contradicts
it, and the only thing telling a reader otherwise is a spec they have no reason to open.

*Corrected 2026-09-12 by that records task, against the shipped
`charter/frame/launcher.py`: the unproven-chat line named as one of the things charter
writes there, the `execvpe`-that-raised case covered, "only before the `exec`" replaced by
the distinguishing question, the wait's two conditions both stated, the record separated
from the wait, and the measurement cited where a reader can open it.*

*Extended 2026-09-12 by the task that added the approval
([#992](https://github.com/diazoxide/charter-plane/pull/992)), under the same rule: the launcher
now ASKS in that pane as well as writing in it, so the question is named as the second thing
it writes, its containment and the two conditions for putting it are bounded, and the read
it makes is distinguished from the two reads of a harness's pane the 2026-09-01 amendment
allows.*

## Amendment, 2026-09-12: that pane's first screen is a surface, not a line

The amendment above bounded what charter writes in a chat's pane before the `exec` at *three
kinds of line, and charter wrote every one* — a refusal, the approval prompt, or the line an
unproven chat prints — and said *no escape sequences of charter's own, no panel, no layout,
and never a fourth thing later*. The profile selector is the fourth thing, and it is none of
those lines: it is a whole `frame/overlay.Surface`, painted over the alternate screen, with the pane's
terminal in raw mode, for as long as somebody takes to choose (`charter/frame/selector.py`,
`charter frame-launch --select`).

**The distinguishing question does not move.** *Has a harness ever run in this pane, and is
charter's own process still the one in it?* No and yes — the same answer the refusal gives,
and for the stronger reason: at the selector nothing has been attempted at all. There is no
harness process, no output of its own on that screen, nothing to draw over and nothing to
parse, and every failure this ADR was written against needs a harness on the other side of
the pane to occur.

**What changes is the bound on the WRITE, and only that.** The old bound counted lines
because the only things charter had to say there were lines. The bound is now what the
pane is FOR before the `exec`:

* **Charter's own surfaces only, and charter's own surface means `frame/overlay.py`.** The
  selector is `palette.Palette` over profile rows — the same modal loop, the same
  containment, the same one key that always leaves, that `F2` and the tab menu run in a pane
  split off a harness. Nothing else may be drawn here: not a panel, not a layout, not a
  second surface charter wrote somewhere else to a different contract.
* **The approval is not a second surface.** Enter on a new or changed profile hands the
  terminal back (`palette.own_the_tty` restores its mode) and the launch asks with the
  prompt the amendment above bounds — escaped, whole, `run this? [y/N]` — exactly as
  `charter <profile>` does in a terminal. A one-line surface heading could not hold that
  command whole, and a prompt a `y` answers must never be clipped.
* **A row says how much it hid.** A selector row carries a command or a reason out of a file
  a chat can write, so the surface cuts each column to the pane with `… +N not shown`
  (`overlay.Surface.says_what_it_hid`) rather than a bare ellipsis — the promise a `doctor`
  row makes, in the same helper (`contain.counted`).
* **It ends the moment a harness exists.** `os.execvpe` replaces this process, and from
  that instant the pane is the harness's and the rule above is unqualified again. A pane
  whose harness later EXITS closes as it always did and never comes back to the selector
  — going back would be charter drawing in a pane a harness has run in, which is the rule
  and not an exception to it.
* **No escape hatch, because the thing it escapes to is not there.** `F12` hands the
  keyboard back to the harness; in this pane there is no harness to hand it to, so the
  selector's footer does not offer it and `Esc` closes the chat instead.
* **Reading is still never.** This amendment, like the last, adds a WRITE before the
  harness exists. Charter reads this pane at the two moments the 2026-09-01 amendment
  allows and at no others, and it never reads it to react to what a harness printed.

**The cost this takes on, measured rather than stated.** `palette.own_the_tty` puts the
pane's terminal into raw mode, which the previous amendment deliberately avoided: a
`tcsetattr` from a launcher pane on a Linux CI runner was measured leaving the process
killed by a signal, and that is why the refusal's wait is a line read rather than a
keypress. The difference is what the pane is doing: the refusal's pane is one the chat
teardown is already killing, and the selector's is a live chat window nothing is tearing
down — the same arrangement `charter frame-palette --pane` has run in on every supported
tmux since 0.52. Measured here, on a real server with real keystrokes and nothing patched
inside the pane (`tests/test_a_new_chat_starts_at_the_profile_selector
.TheSelectorOnARealServer`): the selector paints, a real Enter picks a row and the launcher
`exec`s the harness keeping its pid, on tmux 3.7c **and on the Linux runner CI uses**. Raw
mode in a live chat pane is settled.

**What that measurement also found, and what charter does about it.** A cancelled pane —
one that leaves raw mode and exits rather than `exec`ing — comes back on Linux dead with
BOTH `#{pane_dead_status}` and `#{pane_dead_signal}` empty, and its window is still listed a
minute later, with `remain-on-exit on` and both `pane-died` hooks read back present. So
charter does not leave the cancel to that hook: **Esc closes its own window**, through
`frame/tmuxctl.py` like every other tmux call charter makes
(`frame/launcher._close_the_cancelled_chat`) — and only the window of the pane tmux PROVES is
this process, `#{pane_pid}` equal to its pid, never one a record or an inherited
`$TMUX_PANE` names. An earlier shape that trusted those closed an operator's session from a
test run inside a live chat; `kill-window -t ''` kills the active window. That is this amendment's bound met rather than
stretched — the pane is charter's while no harness has run in it, and closing the window it
is drawing in is the last thing it does with it. The hook is untouched and is still the
answer for a harness that dies.

## Amendment, 2026-09-15: a harness exit is no longer final — the pane that emptied offers a choice

The 2026-09-12 selector amendment ended on *"A pane whose harness later EXITS closes as it
always did and never comes back to the selector — going back would be charter drawing in a
pane a harness has run in"* (:335-337). The operator ruled otherwise: **no harness exit
destroys a chat.** Ctrl+C stays exactly as each harness defines it, because a chat is
protected by what charter does after an exit and not by taking a key away — which is the
consequence at :96-98, read as written.

**The distinguishing question moves from the past tense to the present.** It was *has a
harness ever run in this pane, and is charter's own process still the one in it?* It is now:
**is a harness process in this pane right now?** No, and the pane is charter's again — before
the first `exec`, and after any exit. Yes, and the rule is unqualified: charter draws nothing
there and reads it only at the two moments of the 2026-09-01 amendment. That is checkable
from outside rather than asserted: tmux lists the pane `#{pane_dead}` before charter touches
it, and `ended` is claimed before any respawn.

**What charter puts there after an exit, and nothing else.**

* A **clean exit** respawns the pane into the profile selector — a `frame/overlay.py` surface
  bounded exactly as the selector already is, with one extra row, resume.
* A **crash** leaves the dead pane untouched. tmux keeps the harness's last lines on its own
  screen (`remain-on-exit`), and the choice opens in a drawer pane split beside it. Charter
  does not draw in the dead pane at all.
* `charter frame -- <cmd>` is not a harness: its window closes at exit as it always did, and
  its exit code goes back to the caller.

**Bounded, and each bound is checkable.**

* **Charter restarts nothing by itself.** Every harness start after an exit is an operator's
  Enter on a row. No timer, no retry, no automatic resume; an ended tab nobody switches to
  stays ended, and neither end of input nor Ctrl+C is ever read as a choice.
* **Charter never types into a harness.** No `send-keys`, no `/rename`, no `/resume`. A
  resume is an argument at the `exec` (`--resume`, `resume`, `-s`), and a title reaches
  Claude Code as `--name` at the next `exec`.
* **Charter reads nothing to decide.** Which presentation to draw is chosen from the exit
  code the `pane-died[0]` hook wrote and from the link charter recorded, never from what the
  harness printed. The last lines stay because charter leaves that pane alone, not because it
  reads them.
* **Charter acts on a pane only as a listing proves it.** Every respawn, split and kill
  targets the pane id that ONE listing on the chat's own server reported under this chat and
  this plane; a respawn never passes `-k`, so tmux itself refuses a pane whose harness is
  still running.
* **The launch's own early death is unchanged.** A harness dead before its chat was drawn is
  reported and its window closed, as #384 requires — the ended step does nothing at all for a
  chat that carries no `drawn` mark.

*Recorded in the pull request whose code first relies on it (ruling 44).*
