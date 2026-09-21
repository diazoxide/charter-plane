# A pin is an arrangement, so it is machine state and never a plane fact

[ADR 0039](0039-tabs-keep-their-order-and-the-overflow-sorts-by-activity.md) records the
operator's decision that a project, a workspace and a chat can each be **pinned**, and leaves
where each pin is kept to whoever builds it. It named the hard part precisely: *"Three levels is
three storage decisions, and none of them is the same as another."*

The operator ruled the first half of it on 2026-09-22, in one sentence: **a pin is how one
operator likes their window, not a fact about the plane.** This record is that ruling, what
follows from it for each of the three levels, and the amendment to
[ADR 0034](0034-charter-keeps-a-little-state-outside-every-plane.md) it needs — because 0034's
list of what may live outside a plane is closed, on purpose, and a pin is not on it.

## Why not `charter.toml`

ADR 0039 left the workspace pin genuinely open: *"which may be exactly right (a plane saying
which workspace matters) or exactly wrong (one operator's arrangement imposed on the next)."*

It is the second, and the test that settles it is what a `git clone` does with it. A workspace
pin in `charter.toml` is **committed**: it arrives with the clone, on a machine whose operator
never asked for it, and it puts *somebody else's* workspace first on their strip. That is not a
plane telling the truth about itself — the plane already says which workspaces exist and in what
order, and that IS its emphasis. A pin is a second, contradicting emphasis with one person's name
silently on it.

The same test read the other way is what makes this easy: **deleting a pin costs nobody anything
but the person who made it.** A fact whose loss is felt by exactly one operator on exactly one
machine is not a fact about a plane that many machines clone.

And there is a smaller, sharper reason. A pin changes on a click. `charter.toml` is a committed
file an operator also edits by hand and a repository's history is kept of; writing to it every
time somebody pins a workspace turns the plane's own configuration into a UI state file, and the
next `git status` in that plane is dirty for a reason nobody did on purpose.

## Where each of the three goes

**A project pin, and a workspace pin, go in the machine store** (ADR 0034,
`crates/charter-core/src/machine.rs`). That store already holds which planes this machine knows
and how they were arranged in windows; a pin is the same kind of fact one level finer. The
amendment below is what lets it.

**A chat pin goes in the plane's own app record**, `.charter/app/reopen.json`
(`crates/charter-core/src/reopen.rs`), and **not** in the machine store. Three reasons, and the
first is ADR 0034's own words:

- 0034 forbids it in as many words — **"no chat names"** — and the prohibition is not a
  technicality: a chat is numbered per plane, and its number means nothing outside the plane
  that issued it.
- `reopen.json` is already the only record that a chat exists at all. A pin on a chat has to
  disappear when the chat does, and the file that restores chats is the file that can do that
  without a second list to keep in step — which is `Recent.trust`'s rule one scope up.
- It is not shared with a clone either. `.charter/` is out of git, and ADR 0034 itself counts
  `charter.local.toml` and `.charter/` as the plane's machine-local corner. So the operator's
  ruling — a pin is not committed — is honoured there as much as in the machine store.

**ADR 0039 predicted this needs a `reopen.json` version bump, and it does not.** 0039 reasoned
from that file's rule that *"a record of any other version is ignored whole"*, which is true and
is the reason a bump is expensive: every operator's open chats would be dropped at the first
launch after the upgrade, silently, because a version-2 charter would read their version-1
record as "nothing to put back". A bump is owed when a field's **absence cannot be read
honestly**. `pinned`'s absence reads honestly and reads as `false`: a record written before pins
existed describes a plane where nothing was pinned, which is exactly what was true. So the field
is added without a bump, an older charter ignores it, and nobody loses a day's chats to a
version number.

**And this is not a new judgement about that file — it is the one that file already made.**
[ADR 0029](0029-the-pane-footer-is-blanked-by-default-and-a-chat-may-keep-it.md) added
`show_footer` to the same record under the same version, and `reopen.rs`'s doc comment on that
field says why in as many words: *"A record written before ADR 0029 has no such key, and `false`
is both serde's default and the behaviour every such record was written under."* A pin is the
second field to arrive this way, so the rule is written down here rather than left to be
inferred from one instance: **a field whose absence is a true statement about the records that
lack it does not cost a version; one whose absence would be a lie does.**

## The amendment to ADR 0034

ADR 0034 lists four facts and closes with *"Paths, timestamps, trust decisions, window layout.
That is the list."*; `machine.rs` groups the same four into **"Three things, and nothing else"**.
Either count is the same closure, and that closure is the whole reason a file outside every plane
was allowed to exist. It is not weakened by being appended to quietly.

**Amended: there is one more, and it is `how the operator arranged what this file already
names` — which of the remembered planes are pinned, and which workspaces inside them.** That is a
fifth fact in ADR 0034's list and a fourth thing in `machine.rs`'s.

It qualifies under 0034's own rule — *"a fact may live outside every plane only when it is about
the operator or the machine and is false inside any one plane"* — and each half is worth saying
out loud:

- **It is about the operator.** Two people with the same clone pin different things, and neither
  is wrong. That is the definition 0034 gives.
- **It is false inside any one plane**, for the reason above: written into `charter.toml` it
  becomes a claim the plane makes to everyone who clones it, which is a different and untrue
  claim.

**It passes 0034's own test, unchanged.** That test is: *"deleting this file must cost the
operator their arrangement and their approvals and nothing else; every plane must still open,
complete, with everything it had."* A lost pin costs an arrangement — it is the definition of one
— and nothing else. Every plane opens with every workspace it had, in the plane's own order.

**And it does not breach "never plane content", although it looks as though it must.** A
workspace pin stores a workspace **name**, and 0034 says "no workspace names". The distinction
that keeps both true is the one 0034 was actually making: what it forbids is a **copy** of an
answer the plane already gives, because a copy is a second answer that nothing invalidates when
the plane changes. A pin is not a copy. The plane answers "which workspaces exist"; the pin
answers "which of them this operator wants first", which the plane does not answer and, by the
ruling above, must not. The name in the store is a **reference** into the plane — the same kind
of thing as the plane paths the store has always held, and subject to the same rule: it is
checked when it is read, and a reference to something that is no longer there is dropped with a
reason rather than raised.

Two consequences follow immediately and are part of the amendment rather than notes on it:

- **A dangling pin is dropped, and says so.** A pinned workspace that has been renamed or
  removed on disk is a pin with nothing under it. It reads as "no such workspace", the way a
  remembered plane that has gone already does — never as a workspace charter will then draw.
  This is the hazard 0034 already names for trust entries keyed on a path, arriving at the level
  below.
- **A pin cannot put a plane in the store, but it stops one falling out.** The recents list is
  bounded (`MOST_RECENTS`), and losing a pinned project to the sixty-fifth plane opened would
  make pinning meaningless on the machine that most needs it. So the bound is applied to the
  **unpinned** entries: a pinned plane is kept, and pinning is the only thing an operator can do
  to say "not this one". It is still a bound — nothing unbounded is being introduced — and the
  operator can only pin planes they have opened.

## What was rejected

- **A workspace pin in `charter.toml`.** Argued above: committed, and therefore one operator's
  arrangement imposed on everyone who clones.
- **A chat pin in the machine store**, keyed on plane and chat number. It puts a chat name
  outside every plane, which ADR 0034 refuses in as many words, and it creates a second list to
  keep in step with the one that says which chats exist.
- **A fourth store of its own**, holding only pins. It would be a second file with the same
  lifetime, the same mode, the same read-time validation and the same platform refusal as the
  one that exists, differing only in its name — which is the definition of the drift these
  records exist to prevent.
- **A `reopen.json` version bump for the chat pin.** It is what ADR 0039 expected, and the price
  is every operator's open chats at the first launch after the upgrade. A field whose absence
  reads honestly does not need one.
- **Leaving the amendment unwritten and just adding a field.** The whole value of "three things,
  and nothing else" is that the fourth had to be argued for. If it can be appended to, it is not
  a limit; the next field then has a precedent instead of an argument to beat.

## Consequences, including the ones that cost something

- **`machine.rs`'s module docstring says four things now, and this record is why.** The count in
  that comment is load-bearing and has to move with the file rather than after it.
- **Pinning has to be per operator per machine, and a second machine starts unpinned.** That is
  the price of the ruling and it is the same price ADR 0034 already pays for the recents list and
  the approvals: a fresh machine opens the opener with an empty list.
- **Three levels, three stores, and the code cannot treat "pin" as one feature.** ADR 0039
  predicted a design that did would discover it in review; this record is where it is discovered
  instead. Two of the three share a store and the third does not, and the boundary is whether
  the thing being pinned is something the machine store already names.
- **Nothing here changes what a pin DOES on screen.** Whether a pinned tab is drawn first, and
  whether it is exempt from the overflow menu, are ADR 0039's open questions and are not settled
  by deciding where the pin is written down.
