# The pane footer is blanked by default, and a chat may keep it

ADR 0018 drew a line charter has kept since: **charter may run the harness, but never draws
it.** ADR 0019 then answered a second question — what happens when charter draws the plane
*twice* on one screen — and decided that inside a live tmux frame the panels are the surface
and `charter statusline` prints an empty line.

charter-app blanks the footer inside every pane it opens. **That was never decided.** It
arrived when `charter statusline` was ported to Rust: the port read ADR 0019, found the same
picture with tmux taken out — the app draws the workspace's repos, their branches, their dirt
and their CI in panels, and a chat is a terminal in the same window — and transposed the rule.
The port said so, in as many words, in its own module documentation. Nobody argued with it,
and a transposition became the product's behaviour.

It is a defensible transposition. It is also a product decision made by a port, which is what
makes it worth a record rather than a comment.

## First, what the blank line actually costs

This has to be got right before anything is argued on top of it, because the obvious framing
— *"charter blanks the harness's own footer, and the harness's footer carries things charter
does not show: context left, model, mode"* — is **false**, and this ADR is written down partly
so nobody has to rediscover that.

`charter statusline` **is** Claude Code's `statusLine` command. There is one such line and one
occupant of it. When charter prints an empty line, Claude Code is being told there is nothing
to show; it does not fall back to a status line of its own. ADR 0019 measured exactly that and
wrote it into its consequences:

> **A framed Claude Code session has no context/cache gauge on any surface.** The status line
> is where `ctx NN%` and `cache NN%` were drawn, and it is now blank inside a frame.

Those gauges are *charter's* — zone 3 of charter's own footer. So the choice in a pane is
between **charter's footer** and **nothing**. Nothing about the harness's own presentation is
being suppressed or restored, and the setting this ADR decides cannot give an operator back
context, model or mode, because charter's Rust footer does not draw them yet either (M2.18
draws zone 1 and says in the body which surfaces it does not draw).

## The honest argument against the old default

ADR 0019's premise is that suppression *removes a duplicate*: the plane's state is already on
this screen, drawn by charter, and drawing it again teaches the reader to stop reading it. One
difference between a frame and the app attacks that premise directly.

**A frame held one harness. This window holds fifty.** In a frame, the panels and the
suppressed footer described the same session — same workspace, same persona, same repos — so
the second one really was the first one again. In the app there is one set of panels and up to
fifty chats, and the panels describe the **focused** workspace while a chat's footer describes
the workspace **that chat** resolves to. For any chat that is not the focused one, those are
not the same fact, and calling the footer a duplicate of the panels is calling two different
answers one answer.

There is a second, weaker point worth stating because it will be raised. ADR 0018 says charter
never draws the harness, and `statusLine` is the one place a harness *invites* charter inside
its own rectangle. That cuts both ways: printing an empty line is charter declining the
invitation, which is if anything more 0018-compliant than filling it. So 0018 is not an
argument against the blank — but it is a reason the blank is not obviously wrong either, and
the decision cannot be read off either ADR.

The counter-argument is real too, which is why this was close. A pane in a fifty-chat window is
small; the app's panels already carry the workspace, the repos and the alerts; and a footer
repeating them in every pane is the noise ADR 0019 was written about. The first release of the
tmux frame was reported as *"nothing delivered"* partly because the same facts were on screen
four times over.

## The decision

**The blanking stays, as the DEFAULT. A chat may be started drawing charter's footer in its
own pane, and that choice belongs to the chat and to nothing larger.**

Decided by the operator on **2026-09-20**, asked directly, with three answers on the table:
keep the blank, reverse it, or make it a setting. He chose the setting. This ADR records that
it was a choice and not an obvious one — the argument above is why it was put to him at all.

* **Default blank**, so no pane moves under anybody on an upgrade, and a record written before
  this decision — which has no such field — brings every chat back exactly as it behaved when
  it was written.
* **Per chat**, chosen in the picker beside the profile and the persona, carried into the
  chat's environment as `CHARTER_FOOTER=show`, and written into `.charter/app/reopen.json` so
  a relaunch brings the choice back with the chat.
* **One word turns it on.** Anything else in that variable — inherited from the shell the app
  was launched from, left over, hand-edited into the record — reads as the default, because a
  surface the operator never picked is worse than no surface. The name and the value are both
  constants in the launcher, so nothing a chat or a record can write reaches the environment
  charter builds.

## Why it lives there, and not in the three other places it could have

This is the part that will be re-proposed, so it is argued rather than asserted.

**Not `charter.toml`.** That file is committed and plane-wide. ADR 0022 already refuses to let
a committed file decide how a chat launches on a machine — a merged pull request would move it
for everyone who pulls — and "plane-wide" is the wrong shape for a choice about one pane.

**Not a harness profile in `charter.local.toml`.** That file *is* where this machine's operator
settings live, and it was the closest rival. It loses on granularity: a profile is shared by
every chat started on it, so two panes on one profile could never differ. It also loses on
subject. A profile says what program runs and with what environment; this says what the
operator wants to look at. Charter's own `CHARTER_`-prefixed names are refused in a profile's
`env` (ruling 14), so the variable cannot be set there even by hand — which is deliberate, not
incidental: it keeps one answer to "what turned this chat's footer on".

**Not a switch on a running pane**, which is what "per-panel toggle" sounds like it should
mean. Claude Code runs its `statusLine` command as a subprocess and hands it the environment
the harness itself was `exec`'d with. That environment is fixed at the exec. A switch on a live
chat would therefore appear to work and would not — and a control that lies is worse than a
control that is only offered where it can be honoured. So it is asked once, where the chat is
started, and the checkbox says *this chat only, and only from its next start*.

**So it lives where this chat's profile and persona already live**: picked in the dialog, put
on the chat's environment by `start::environment`, recorded beside them in the app's own
record. No new configuration file, no new protocol, and nothing an operator has to learn a
second location for. `docs/plane-format.md` carries the new record field.

## What would have to change for the default to flip

Recorded so that a later reversal is an argument against these conditions rather than a
re-litigation of taste. Any of them alone is a case; none of them is true today.

* **The panels learn to answer per chat.** The strongest argument against the default is that
  the footer says which workspace *this* chat is on and the panels say it only for the focused
  one. Put a chat's own workspace on its pane — a title, a strip, anything charter draws — and
  the footer is a duplicate again, and the default is clearly right.
* **Charter's footer grows what only it can show.** Zones 2 and 3 are not drawn by this build:
  the alert row, the persona chips with vault health, `ctx`/`cache`. An alert is the one thing
  an operator reads a footer for, and a pane that can show one while the panels are scrolled
  away is worth more than the row it costs. When those land, the balance moves the other way.
* **It is measured that operators turn it on.** If most chats are started with the box ticked,
  the default is wrong and the ticking is a tax. The app records the choice per chat, so this
  is answerable from the record rather than by argument.
* **A footer command learns to read something mutable.** If `charter statusline` ever asks the
  app rather than reading its own environment — over the hook socket it already connects to —
  then an honest per-pane toggle becomes possible, and the "asked once, at the start" shape in
  this ADR is no longer forced. That is a protocol change with its own cost, and this ADR does
  not pretend to have made it.

## Consequences

* **`charter statusline` gains a rung, and it is not one of ADR 0019's four.** The four rungs
  answer "is this invocation drawing into the app". The new one answers "did this chat ask not
  to be blanked", and it is asked first: it is one environment lookup against a socket
  `connect`, and an operator who has said *draw it* is owed the same answer whether or not the
  app's socket happens to be up at that instant.
* **Nothing changes for a chat that did not ask**, including every chat already recorded. The
  variable is absent rather than set to a second word, so there is no value to unset and no way
  for an old record to mean something new.
* **The record grew a field**, and a record is a file anyone who can write the plane's state
  directory can write. It is held to the same rule as `profile` and `persona`: one word charter
  itself writes, and everything else is the default. It reaches no command line — the launcher
  emits a constant name and a constant value, or nothing.
* **ADR 0019 is not amended.** Inside a tmux frame the status line is still charter's own
  surface drawn twice, and nothing here touches that. What this narrows is the
  *transposition* — the app is not a frame, its window is not one session, and the rule it
  inherited is now a default with a name on it.
