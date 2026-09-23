# A panel is a declared contribution, and a chart is not a row

**DRAFT — this needs the operator's sign-off before anything is built on it.** Nothing below is
settled. An agent on this project has claimed a sign-off it did not have; this line is here so
that the next reader checks the file rather than a brief.

The operator's goal, in his words, is a *"100% pluggable app"*, and his question was direct:
*"is anyone can create plugin like this components?"* — meaning the window's side panels. The
answer on 2026-09-23 was **no**, read off the tree rather than remembered:
`crates/charter-core/src/extension.rs`'s `Manifest` let an extension contribute `themes: Vec<Theme>`
and declare a `program` that is hashed, named in the prompt and **never run**; the panels were
hardcoded React in `app/src/Panels.tsx`, fed by named fields of one Tauri command.

He was offered the choice between building the panel changes he asked for that evening as more
hardcoded React, or defining the contract first with those panels as its first consumers. **He
chose the contract.** This record is that contract.

The work is charter-app's. The record is here because `0001`–`0042` are here, and because this
extends [ADR 0041](0041-a-plugin-is-a-subprocess-or-charter-has-no-plugins.md)'s vocabulary —
splitting the two would leave 0041's four properties in one repository and the second thing they
govern in another. ADR 0031 and ADR 0041 both made the same move for the same reason. Every path
below (`crates/charter-core/…`, `app/src-tauri/…`, `app/src/…`) is in `diazoxide/charter-app`.

## Where this extends ADR 0041, and where it does not contradict it

Said plainly, because the brief for this record asked for it plainly.

**It extends 0041's decision 2 by exactly one entry, on 0041's own terms.** That decision's
minimum viable capability set is two things: *contribute a theme* (declarative data against a
closed vocabulary) and *contribute a named palette command that runs one round trip per
deliberate human action*. The second needs the executor. This record adds a **third** that needs
nothing: *contribute a panel*, which is declarative data against a closed vocabulary, in exactly
the sense the theme is. It is the same kind of thing as the first entry, not a weakened version
of the second.

**It contradicts nothing in 0041, and the one place it comes close is worth naming.** 0041's
capability table says of the DOM and the window's pixels: **"No, ever — A theme reaches
appearance as data. Code never reaches the tree charter draws consent prompts into."** A panel
plainly puts something in that tree. The distinction this record relies on is the one that
sentence itself draws: *a theme reaches appearance as data*. A panel reaches the tree as data
too — a typed value charter parses and re-emits, never markup, never a selector, never a path.
If that distinction is judged too fine, then this record is wrong and the honest consequence is
that **a stranger's extension cannot contribute a panel at all**, which is a defensible answer
and is the one the operator should be able to give.

**It relies on 0041's stage 1 being real.** `extension.rs` is 0041's item 2 — *an extension
registry with no executor* — and its `charter_runs_nothing` test pins that nothing there spawns
anything. Everything below is designed so that a panel is a thing that list can hold without the
list acquiring an executor.

**It does not touch 0041's gate.** Items 2, 3, 4, 5, 6 and 8 stand exactly as written. In
particular the tool guard is still one blanket `exit 2` with three of six stages wired to
nothing. A panel is not a runtime and shipping one does not spend any part of that gate — which
is precisely the argument for shipping it: it is item 2's list growing a second entry, and item 2
is the thing 0041 says to build *first*.

## What a panel is, minimally

A **title**, an **ordering**, and a **body**.

```
Panel  = { id, title, order, mark, blocks[], from }
Block  = List { rows[], empty } | Note { text, tone }
Row    = { key, text, note?, mark, tone, detail?, runs? }
Detail = Text(string) | Persona(name)
Empty  = { headline, body?, offer? }
Mark   = todo | persona | repo | piece | note | trouble | dot
Tone   = plain | default | trouble
```

That is the whole of it. `crates/charter-core/src/panel.rs` is that type and its parser.

### It draws from a declared vocabulary, not arbitrary markup

This was the sharpest open question and it has the clearest answer. **A stranger's extension
supplies a value, and charter decides what that value looks like.** The alternative — an
extension supplies markup — is refused, and the refusal is ADR 0041's, already written: the DOM
is the tree charter draws consent prompts into, and code never reaches it.

The vocabulary being closed is not decoration on that refusal, it is the enforcement of it. Three
consequences fall out that a markup-based design cannot have:

- **A panel cannot say *where*.** There is no `side`, no `region`, no `width`, no `class`, no
  `style`. `order` is a hint charter sorts by. This is 0041's property 3 — *charter chooses the
  consumer* — and it is what stops a contributed panel from covering, displacing or imitating a
  consent surface.
- **A panel cannot name a file.** A mark is a word out of a list of seven, which charter maps to
  a glyph it already ships. 0041's third crossing is *a reference to a file* — a font, an image,
  an `@import` — and an icon is exactly the shape that invites one.
- **A key charter did not publish is refused, not ignored.** An unknown field fails the whole
  extension with the field named. This is harsher than the theme's rule, which drops an unknown
  token with a reason, and the difference is deliberate: a theme's unknown token costs a colour,
  where a panel's unknown key is a contribution the operator was shown in the consent prompt and
  then did not get. Silence in the safe direction is what trains an operator to stop reading.

The cost, stated: **a panel cannot do something somebody will want**, and the answer will be to
widen the vocabulary rather than to admit markup. That is 0041's own consequence about themes,
inherited on purpose, and the statistics question below is its first real test.

### Where its data comes from

The brief for this record put it as *"today `workspace_panels` answers with everything at once; a
contributed panel cannot be in that call."* The second half is half right and the correction
matters, because it decides the command shape.

**The thing a contributed panel cannot be is a *field*.** `Panels` names `todos` and `personas`;
there is no field for a panel nobody has written yet and no honest way to add one. A **list** has
room for every contributor. The round trip was never the problem.

So: `workspace_panels` grows `contributed: Vec<Panel>` and `Panels.tsx` draws that and nothing
else. One command, because **focusing a workspace has 100 ms** (ADR 0026) and this is the command
that has to answer inside it; a call per panel would be N round trips for what is one directory
listing.

**And a contributed panel needs no round trip of its own, which is a fact about stage 1 rather
than a design preference.** With no executor there is nothing to ask:

- an **extension's** panel is *declared*, so its rows are in the manifest, and the manifest was
  read and hashed when the registry was surveyed;
- **charter's own** panels are *produced*, from the plane read the command already does.

Extension panels are surveyed **once per window** and not once per workspace focus, because a
survey re-hashes every installed extension's whole directory — 0041's named cost of
fingerprinting code, widened by charter-app#152 from the declared list to the tree. An extension
is machine state and never travels in a plane (0041's decision 3), so one survey serves every
project a window holds.

**The day an executor lands, a panel that wants live rows asks its extension, and that is a
second call made when the panel is drawn.** It is stage 2's to design, and it is not needed for
anything in this record.

### What it can do

**Rows run catalogue offers, by id, or they run nothing.** `app/src/actions.ts` is the one list of
what charter can do — the palette, the bar's buttons and every context menu are views of it — and
a panel that invented its own verbs would be a second catalogue, which is the defect that list
exists to prevent. So a row names a catalogue row by id, the window looks it up, and an id the
catalogue has stopped offering draws no button rather than a dead one.

**And a contributed row may not carry one.** This is the load-bearing refusal in the record.

> There is no executor. A contributed panel is a declaration the window renders, not code it
> runs. A row that ran a charter verb on a click would be the first thing in charter that
> executes on an extension's say-so, through a path with no hook, no prompt and no grant — which
> is ADR 0041's *"a second door beside the one being built"*, opened by a panel.

An extension that declares `runs` is refused by name, with that sentence, rather than having the
field dropped.

### What is refused

A panel runs with the operator's authority in his window. What it cannot reach:

| Surface | Grantable to a contributed panel? |
| --- | --- |
| Arbitrary markup, a selector, a stylesheet, a `url()` | **No, ever.** ADR 0041's DOM row. |
| Where it goes — region, side, width, order among charter's own by fiat | **No.** `order` is a hint charter sorts by; charter's own break ties first. |
| A file — an icon, a font, an image | **No.** A mark is a word out of a closed list. |
| A charter verb on a row or an empty state | **No, in stage 1.** No executor; see above. |
| A card that reads the plane | **No.** A declared card is the row's own words. |
| Live rows | **No, in stage 1.** Declared rows only, read at survey time. |
| Unbounded rows, text, or panels | **No.** 8 panels, 500 rows, 1 KiB per row, 8 KiB per card. |
| Control characters in anything drawn | **No.** Refused, not stripped — see below. |

**And one refusal that is not about execution at all.** 0041 keeps *deception* apart from *code
execution* and a panel is where the two most easily get confused. A row is words on the operator's
screen. It can lie, and no parser stops it. What this record does about that is narrow and
stated: charter draws the contributing extension's id on the panel (0041 item 5 — *show what is
in force, after approval and not only at it*), the vocabulary cannot say *where* so a panel
cannot cover a consent surface, `runs` is refused so a lie cannot be wired to an action, and
control characters are refused rather than stripped — because what a control character does is
make two different strings look identical on screen, which is the half of deception that no
escaping helps with. What is left is the same class as a theme that paints *needs you* like idle,
and it is the install-time decision's to carry. 0041 says that in three places and this makes
four.

## The asymmetries, which are findings and not omissions

The brief for this work asked that if charter's own panels need a privilege a stranger's cannot
have, that be written down rather than smoothed over. Three, and all three are the same thing:
**charter is code that is already in the process.**

1. **charter's rows carry `runs`.** A persona row runs `persona.show:<name>`, which is a
   catalogue row the palette and a context menu already run (charter-app#174).
2. **charter's cards may name a consumer that reads the plane.** `Detail::Persona` costs a
   `persona_details` call, and — see below — a memories read. A declared card is `Detail::Text`,
   which reads nothing.
3. **charter's rows get a context menu.** A menu names what a row is *about*
   (`{ on: "persona", persona }`), and there is no way to derive that from a row: a row is words,
   a key and at most a catalogue id. charter's personas panel knows its rows are personas.

None is a property of being charter and none is permanent. Each lifts through a **grant**, not
through a special case: *this extension may offer this catalogue row*, consented per extension
per row. That grant needs the executor, so it is stage 2.

**The one asymmetry that would invalidate the contract is the one that does not exist.** Nothing
charter's own panels do reaches the window through a path a contributed panel does not use.
`Panels.tsx` draws both with the same loop and the same list primitive; the difference is in what
the *values* say, not in how they are drawn. That is what makes the contract testable rather than
aspirational, and it is what the jsdom test *"gives a contributed panel the list primitive"*
exists to hold.

## The list primitive, and why it is in this record

The operator's requests about the todos panel were four:

> *"rows are too long, they are wrapping in 3 lines — should be shortened automatically"*
> *"on clicking we should show full body — like persona description"*
> *"max 10 or 20 todos should be loaded, with scroll inside panel and load more"*
> *"search input should be visible when count is bigger than N"*

…and then: *"same load-more and search for personas will be better to have"*.

That last sentence is what makes this a contract question. Built as four fixes to one panel, the
next panel starts from nothing. **Built as the vocabulary panels draw with, a contributed panel
gets all four without asking** — and that is the test of whether the contract is worth having. If
an extension's panel had needed one line of its own in the renderer to get a search box, the
vocabulary would be advisory rather than a vocabulary.

It has three callers on the day it was written: the todos panel, the personas panel, and a
persona's memories, which is a row's **detail surface** rather than a panel. Two of those are
panels and one is not, which is the useful part: the same primitive serves a panel body and a
larger, searched list one surface in.

## The personas panel as the acceptance test

The operator sharpened this while the work was in flight: *"personas, todos, are pure examples of
plugin"*, and the personas one must carry all of this end to end.

| What he asked for | Does the contract express it? |
| --- | --- |
| **A count on a row** — memories per persona | **Yes.** `Row::note` is a short trailing note; a count is one. charter's own producer writes it, and a contributed panel can write one too. The count is a `read_dir` and no file opens, so it stays on the 100 ms path. |
| **A detail surface from a row that is a list** — a persona's memories | **Yes, for charter.** `Detail::Persona` names a consumer that reads the plane; the memories arrive from `persona_memories` as **rows of the same vocabulary**, so the card's list is the primitive one surface in. **A declared panel gets `Detail::Text`** — asymmetry 2 above. |
| **Search and lazy loading in that surface** | **Yes, for both.** It is the same primitive. A declared panel's rows are paged and searched identically; what it does not get is *live* rows, because that needs the executor. |
| **Statistics, with visualisation, from a button** | **No. See below.** |

The substrate for the memories half already existed and was not rebuilt:
`crates/charter-core/src/memstore.rs` (`read_files`, `read_store`, `Found`) and `recall.rs`. What
was missing was the wire, and that is what `persona_memories` is.

**One thing this raises that is the operator's to rule on.** charter-app#173 chose a *popover* for
the persona card, and its argument was about six short rows that answer *what is this one for*: a
dialog would mark the needs-you queue `aria-hidden`, which ADR 0038 says this region must never
compete with, and a sheet is already the alerts drawer's. **That argument was not made about a
searchable archive**, and the card now holds one. A popover anchored in a 260 px column is a thin
surface for reading memories. It is left as a popover deliberately, because changing it
contradicts a written decision — but #173's reasoning no longer covers the whole of what the card
does, and that is the first thing to attack here.

## Statistics: a chart is not a row, and this is where the contract gives

The three honest answers, and the one taken.

**Rejected — plugins may draw arbitrary markup.** This is not this record's to reject: ADR 0041
already did, and the row is *"No, ever"*. What it costs, said once so nobody has to reconstruct
it: `app/src-tauri/capabilities/default.json` grants the window `core:default`, `opener:default`
and `notification:default`, and charter's own forty `#[tauri::command]`s are reachable by
anything executing in that window; the only thing keeping foreign script out is
`tauri.conf.json`'s CSP, and admitting markup is the precise thing that CSP exists to prevent,
done deliberately. It also gives a stranger's extension the tree charter draws its consent
prompts into.

**Rejected for now — the vocabulary grows a chart primitive.** This is the tempting one and it is
nearly right. A bar chart is a labelled magnitude list: it is already the *shape* of the
vocabulary, charter can draw it from typed numbers, and there is no path from declared data to
markup. It would be `Block::Bars { rows: [{ label, value }] }` and it would be safe.

It is refused **tonight** on ADR 0041's own rule, quoted rather than paraphrased: *"a capability
invented for a hypothetical plugin is a grant nobody audited against a real use."* And the real
use is the thing that shows why the primitive is not the answer:

> **A declared chart is a chart of numbers the extension wrote down at install time.** Statistics
> over a persona's memories change every time a chat remembers something. An extension that can
> only declare its data can only ship stale numbers, and a panel that draws stale numbers under
> the word *statistics* is worse than one that draws nothing.

So the chart block is not the missing piece. **The missing piece is a producer**, and a producer
is code, and code is the executor.

**Taken — the statistics surface is outside this contract, and for a stranger's extension it is
blocked on ADR 0041 stage 2.** Three parts:

1. **For charter's own contributions, nothing blocks it.** charter can compute statistics over
   its own plane today. If the operator wants a persona statistics view drawn by charter, it is
   buildable now and needs no part of this record.
2. **For a contributed panel, it is not expressible, and saying so is the answer.** This is the
   *"if the contract needs the executor, stop and say so"* case, and it is confined to this one
   requirement: everything else the operator asked for — the count, the list, the search, the
   lazy load — the contract expresses today, for charter and for a stranger alike.
3. **The shape it will take, recorded so it is not invented under pressure.** A statistics view is
   a **second surface opened from a row**, which the vocabulary already has a mechanism for:
   `Detail` is a closed set, and a `Detail::Bars` sits beside `Detail::Text` exactly as
   `Detail::Persona` does. So the *surface* is not new. What is new is **where the numbers come
   from**, and that has one honest answer per contributor: charter computes its own; an extension
   is asked, over the protocol, when the surface is opened. Stage 2.

**What this costs, stated rather than discovered.** A plugin author reading *"100% pluggable"*
will build a panel, find it cannot show a chart of anything current, and conclude the panel API
is a toy. That reaction is correct about stage 1 and it is the price of not having an executor.
The alternative — a chart block that can only hold frozen numbers — buys the appearance of the
feature and not the feature, and is the same error as a consent prompt that over-promises, which
0041's amendment already refuses.

## What was rejected

- **Arbitrary markup from an extension.** ADR 0041's DOM row; the CSP exists to stop exactly this.
- **A chart primitive, now.** Safe, and useless without a producer. 0041's rule about capabilities
  invented for hypothetical plugins, applied to the first capability this record was tempted by.
- **Letting a declared row run a catalogue verb.** An executor with nothing behind it.
- **Dropping an unknown key instead of refusing the extension.** The operator consented to a list;
  a key charter ignored is an item on that list he does not get.
- **A command per panel.** 100 ms per workspace focus, and nothing to ask in stage 1 anyway.
- **Keeping `todos` and `personas` as the panel bodies and adding contributions beside them.** Two
  sources for one region, drifting.
- **Deleting `todos`, `personas` and `persona` from `workspace_panels` entirely.** They are facts
  about the workspace that three other surfaces read — the status line counts the todos, the
  catalogue builds a `persona.show:<name>` row per persona. Moving those onto a shape designed for
  *drawing* is the opposite of the separation this record is for. What moved is the drawing.
- **A second piece of window state per panel** for which card is open. It could not exist for a
  panel nobody has written; the state is one row key, `<panel>/<row>`.

## Consequences

- **The vocabulary is now a thing that has to be versioned.** A manifest written against a later
  charter is refused by this one with the unknown key named. That is the right failure and it
  means adding a word to the vocabulary is a compatibility event, which the theme's
  drop-with-a-reason rule let charter avoid.
- **A contributed panel is inert and will disappoint.** It lists what its author wrote down. Every
  interesting panel wants live data, and live data is stage 2. This record's value is that the
  *seam* exists and is proved by two real consumers before the runtime arrives to use it — 0041's
  item 2, one entry further on.
- **charter's own panels now pay a serialisation cost they did not.** Two panels of a handful of
  rows per workspace focus, inside a command that already lists a directory and reads small files.
  Not measured against the 100 ms budget as a delta, and it should be.
- **The region can be crowded by a stranger.** Eight panels per extension, sorted by an `order` the
  extension chooses, including above charter's own. The needs-you queue is *not* a contribution
  and cannot be sorted below one — ADR 0038 says this region must never compete with it, so the
  queue is drawn above every panel and the vocabulary has no way to say otherwise.
- **`#173`'s popover argument no longer covers what the persona card does**, and that is open.
- **The statistics requirement is answered with "not yet, and here is the reason"**, which is a
  worse evening's work than a feature and a better one than an escape hatch.

## Amendment, 2026-09-23: a producer exists, so the chart block does

**This amendment is not a sign-off, and the DRAFT line at the top of this record still stands.**
It records what changed when ADR 0041's stage 2 was built (see that record's amendment of the
same date, and charter-app#212, unmerged when this was written).

**Panels may now be fed by a producer — through a view, and not on the panel's own path.** The
record's rule for *where a panel's data comes from* is unchanged: `workspace_panels` answers in
one call inside the 100 ms a workspace focus has, and a contributed panel is declared. What an
extension answers *live* is a **view**: a surface the operator opens, which charter fills by
asking the extension's program once, through the executor's gate, when it is opened. That is
the *"second surface opened from a row"* the statistics section above named, with one change of
place and one of name:

- **It is opened from a panel's heading, or from inside a card — not declared as a `Detail`.**
  A view says what it is *about* (`panel::Subject`, a closed set of one: `personas`), and
  charter decides where things about that subject are offered. charter's own personas panel is
  about personas, so a view about personas is a button on its heading and a section in each
  persona's card. The extension chose a subject and nothing else — property 3, *charter chooses
  the consumer*, carried to the first contribution that runs.
- **A declared panel cannot claim a subject.** `about` is set only by charter's own producer;
  a manifest that tried would be choosing which of charter's surfaces a stranger's view appears
  on.

**The chart block exists, and only in an answer.** `Block::Chart { title, shape, unit, points }`
— a shape out of `bars | columns`, each point a label, a whole count below 2^32 and a short
note. The objection this record raised stands for a manifest and does not apply to an answer:
*a declared chart is a chart of numbers the extension wrote down at install time*, and a
program asked when the operator opens a view answers with numbers read at that moment. So
`panel::declared` still has no key a chart could arrive in and refuses one by name, and
`panel::answered` accepts one. Everything the vocabulary refused before, it refuses in an answer
too: an unknown key, a control character, a colour, a `runs` on a row, an `offer` on an empty
state. The window draws a chart from theme tokens, scales it itself, writes every label as a
text node, draws it as a list to a screen reader, and animates nothing.

**The first producer, and why its three charts.** `crates/persona-statistics` answers with the
number of memories per persona (bars — *which persona carries this plane's knowledge*), memories
written in each of the last twelve weeks (columns — *is this plane still learning*), and days
since each persona last learned something, quietest first (bars — *which persona has gone
quiet*, which is the one an operator has a next step for). Opened from one persona's card it
answers about that persona first.

**#173's popover, which this record left open, is answered.** The persona card is now a
**non-modal Radix `Dialog` portalled into the centre region** — over the terminals, and nowhere
else. Every reason #173 gave for a popover is kept: not modal, so nothing outside it is
`aria-hidden` and the needs-you queue stays in reach (a jsdom test that goes red with `modal`
removed holds that); not the whole window, which is the alerts drawer's; dismissed by Escape or
a click outside; and still the one piece of window state, so `persona.show:<name>` opens it from
the palette. What it gave up is being anchored to the row. Every other row's card is still the
popover, because six short rows are what a popover is for. **This is a decision made without
the operator**, and it is the one in this amendment most worth his attack.

**The asymmetries are unchanged**, and the reason is now sharper. A view runs code, and still
cannot put a charter verb on a row: what an extension puts in the window is data, whether its
manifest declared it or its program answered it. The grant that would lift that — *this
extension may offer this catalogue row* — needs no new mechanism now; it needs a plugin that
wants it, and none has asked.

**The consequence this record predicted is paid off in part.** *"A contributed panel is inert
and will disappoint"* — a contributed panel still is. A contributed *view* is not: a stranger
can now ship a chart of something current, and the persona statistics view is the proof that
the path works end to end, installed, approved, fingerprinted and asked.

## Amendment, 2026-09-23, later the same day: a tab holds a session or a view

**This amendment is not a sign-off either, and the DRAFT line at the top of this record still
stands.** It records a ruling the operator did make, and the design built on it that he has not
yet ruled on. The work is charter-app#212, unmerged when this was written.

**The sheet above is withdrawn.** The previous amendment called the non-modal sheet *"a decision
made without the operator … the one in this amendment most worth his attack"*, and it was put to
him: where should a persona's card — its memories and the Statistics button — open? Offered the
sheet, a popover, and a tab of its own, **he chose "Its own tab"**, and said why in words that
widen the question past personas:

> *"we dont have other tabs then sessions, and this can be good example for us - that in tabs we
> can have what we want - not only harnesses, so lets have this, and we can for future use tabs
> concept for lot of things.."*

His goal is the *"100% pluggable app"* this record opened with: the todos and the personas are
meant to be pure examples of plugins, and what the core does for them any extension must be able
to do. So what is recorded here is not *the persona card moved*; it is what a tab is.

**1. A tab is a layout of panes, and a pane holds a session or a view.** The pane is what is
generalised, not the tab. A tab stays one thing — a layout — so a view can be split beside a
chat, and every rule a tab already had holds for a tab that shows no chat without a second copy
of it: the fixed order (ADR 0039), pinning, the overflow menu and its `N more`, keyboard reach
through the palette's rows, and splitting and closing the pane in focus. The chat's name lives
on the session a pane shows, so a tab holding only a view has no chat to pretend about — no state
mark, nothing for "the chat in front" to mean, and a close that ends nothing and asks nothing.

**2. A view is named by data, and charter's own views and an extension's take the same path.**
A view is *who draws it, which of theirs, and what it is about*: `{ from: null, view: "persona",
key: "steward" }` for charter's persona view, `{ from: "persona-statistics", view: "statistics",
key: "" }` for an extension's. One command answers both (`open_view`), in this record's
vocabulary and nothing else, and one renderer draws both. **charter's persona view is produced
as `panel::Block`s in Rust** — the definition as notes, the memory count, the memories as a
list — rather than as a component that knows what a persona is; the window cannot tell it from
an extension's view except by whose it is, which it says. That is the operator's test, applied
to charter's own code: nothing the core does for the persona view is a door an extension's view
is refused.

**3. Views are the extension point for tabs.** An approved extension that offers a view gets a
tab when the operator opens it — from a panel's heading, from a view about the same subject
(the Statistics button on a persona's tab), or from the palette — and nothing it declares says
*where*: property 3, carried to a surface the size of the window. A view tab opens on the strip
in front, carries that workspace (it works in no directory to be filed by), and opening the same
view again brings its tab forward rather than drawing a second.

**4. What a view may do at a launch is less than what it may do at a press.** View tabs are in
the plane's reopen record beside the chats, so they come back; the record is writable by
whoever can write the plane's state directory, so **a tab the record put back asks an
extension's program nothing until the operator presses for it**. Opening a persona's tab asks no
extension anything — the Statistics button is the operator's press, and it opens its own tab.
A view whose source has gone (an uninstalled extension, a deleted persona) comes back as a tab
that says so, not as an error. Views start nothing, so they are not part of the trust
fingerprint (ADR 0035).

**What this record does not yet say, and should before a second view kind lands:** whether an
extension may offer a view that is about nothing charter publishes (today every extension view is
about a `Subject`, and `personas` is the only one); whether a view may be split beside a chat by
anything but starting a chat beside it; and what a view that wants to change something — a verb
— would need, which is the `runs` grant this record already describes and nobody has asked for.
