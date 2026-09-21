# charter takes the behaviour and keeps the look

The operator opened charter-app's start-chat dialog on 2026-09-21 and found the harness picker
reading `claudeclaudeclaudebuilt-indefault`. He proposed integrating **MUI**, and cited the rule
that is priority 2 of `CLAUDE.md` in both repos:

> **Robustness through standard practice.** Use mature, standard tools the way they are meant to
> be used. Never build custom tooling where a standard tool exists.

He is right about the rule and right that the app is breaking it. **What was argued against, and
what he then decided against, is Material specifically.** The decision is **headless primitives
with charter's own visual language**: charter takes the standard solution for *behaviour* —
label association, focus containment, roving tabindex, menus, keyboard navigation — and keeps
hand-written CSS for *appearance*.

## What the bug actually was, because it is not what it looks like

This has to be got right first, because the obvious reading — *"the dialog was hand-rolled
markup with no label/control association, and a component library would have associated them"* —
is **false**, and the decision is worse if it rests on it.

`app/src/StartChat.tsx` builds the picker out of `<fieldset>`, `<legend>`, `<label>` and
`<input type="radio">`, and every input is *wrapped* by its label. That is implicit association,
it is valid HTML, and it works. The controls are native and standard.

What is missing is **CSS**. A profile row is five spans inside one label —

```jsx
<span className="who">{row.name}</span>
<span className="what">{row.kind}</span>
<code className="where">{row.shown}</code>
<span className="from">{row.source}</span>
{row.is_default && <span className="what">default</span>}
```

— and `app/src/App.css` has no rule for `.profiles`, `.personas`, `.who`, `.what`, `.where` or
`.from`. Unstyled inline spans with no separator render as one run of text, and the label's
accessible name is that same run. `claude` + `claude` + `claude` + `built-in` + `default` is
`claudeclaudeclaudebuilt-indefault`, on screen and to a screen reader, for the same reason.

**So a component library would not have prevented this bug**, and this record does not claim it
would. MUI's `FormControlLabel` would have shipped the spacing; so does one flex rule. The row
was not built out of the wrong parts — it was built and then never dressed. **The fix for it is
a visual language written down and applied, which is exactly the half this decision keeps in
charter's own hands.** Anything that names this ADR as the fix for the start-chat picker is citing
the wrong record.

## What IS missing, measured

The dialog that triggered this is standard. The window around it is not, and this is the
evidence the decision actually rests on — read off the tree on 2026-09-21:

- **Four dialogs declare `aria-modal="true"` and nothing traps focus in any of them.**
  `StartChat`, `QuitWarning`, `ApprovePlane` and `Palette` each carry `role="dialog"
  aria-modal="true"`. `Tab` walks straight out of all four into the window behind, which
  `aria-modal` has just told every assistive technology is inert. Two of them `autoFocus` a
  button on open; only `Palette` restores focus to what had it when it closes. A declared modal
  that is not modal is worse than an undeclared one: the promise is machine-readable and wrong.
- **Three tablists implement none of the tabs pattern.** `Projects`, `Workspaces` and `Tabs` are
  `role="tablist"` with `role="tab"` children — all three named by
  [ADR 0036](0036-the-workspace-is-an-axis-again-projects-workspaces-chats.md). There
  is no roving `tabIndex`, no arrow-key handler anywhere outside `Palette`'s list, and no
  `role="tabpanel"`. Every tab is its own tab stop, so at fifty chats reaching the pane means
  fifty presses of `Tab`, and the arrow keys a screen-reader user is told will work do nothing.
- **The one keyboard list that exists is hand-written.** `Palette.tsx` has its own
  `ArrowDown`/`ArrowUp` handling and its own focus save/restore. It works. It is also the only
  one, and it is the shape every menu added from here would be copied from.

That is three instances of "we built the control ourselves", one of them badly, one of them not
built at all. Priority 2 does not permit a fourth.

## Why not Material

Three arguments, in the order they carry weight. Priority 2 settles *that* a standard solution
is taken; none of these is an argument for building anything, only for which standard solution.

**1. Material is a phone-first design language, and this is not a phone.** The reference the
operator gave for this whole product is **Zed**, by name —
[ADR 0033](0033-a-plane-is-a-project-and-a-window-may-hold-several.md) records the same reference
deciding the project tab. charter-app is a terminal emulator with fifty sessions in it, a
three-deep tablist stack, a repo strip and a footer whose own ADR budgets it in *columns* —
[ADR 0019](0019-the-frame-owns-the-surface.md)'s `slots._bottom` drops whole fields when it runs
out of width. Material's density, its touch targets, its elevation and its type scale are all correct
for the product it was designed for and all wrong for this one. Adopting it means fighting it on
every surface, which is the failure mode priority 2 exists to prevent: a standard tool used the
way it is *not* meant to be used buys none of the robustness it was taken for.

**2. The cold-start budget has no slack to spend.**
[ADR 0026](0026-the-apps-stack-is-locked-by-what-m0-measured.md) locked the stack against measured
limits and records the one that is missed: cold start is **2 s** in the spec, met on macOS at p50
370 ms, and **missed on Linux at 25 s** where the desktop portal cannot start (charter-app#24,
accepted and recorded as an amendment to 0026).

This argument must be stated honestly or it will be knocked down in review, so: **the 25 s is a
D-Bus reply timeout, and no JavaScript bundle moves it.** It is not evidence that a component
library costs a second. What it is evidence of is that this app has one limit already breached
on one platform, nothing yet fixing it, and therefore no budget to spend speculatively. ADR 0026
is also the precedent for the shape of that reasoning: it kept `@xterm/addon-webgl` — 113 KB the
shipped build never loads — only because it buys a re-measurable arm. A dependency's weight is
paid for by what it is measured to buy.

**3. Runtime CSS-in-JS would put a measured number back on the table.** charter-app#133
measured the workspace strip's per-workspace counts at **0.022 ms** for ten workspaces and fifty
chats — one eight-hundredth of a 16.7 ms frame — and the conclusion drawn was *not* to add a
`useMemo`, because there was nothing to save. Material's styling engine computes styles during
render. Whether it would cost anything perceptible here is unmeasured, and this ADR does not
pretend otherwise.

**This is therefore not a speed decision, and priority 3 does not decide it** — the sentence is
borrowed from ADR 0026 deliberately, because it applies identically. Priority 3 says *optimise
only against the spec's limits*, and no limit is at stake here. Argument 1 decides it. Arguments
2 and 3 are the reasons not to pay for a decision argument 1 already lost.

## What is accepted

**Behaviour comes from a headless primitive library. Appearance is charter's own CSS.**

The class of choice is what this record decides: an unstyled, accessible primitive set —
**Radix UI or Base UI** — that ships behaviour and no design language. Which of the two is the
implementing agent's, decided by the measured bundle delta, and the choice is a fact to be read
off the merged PR rather than asserted here. The rule does not change either way, which is why
the record is written at the class.

What is taken, concretely, and each of these is an item from the measured list above:

- **Dialogs** — focus containment, focus restore on close, `Escape`, the inert background that
  `aria-modal` is currently promising and not delivering. Four sites.
- **Tabs** — roving `tabindex`, arrow keys, `Home`/`End`, the tab/tabpanel relationship. Three
  tablists, which after ADR 0036 is a permanent feature of the window and not a phase.
- **Menus** — for the overflow menu
  [ADR 0039](0039-tabs-keep-their-order-and-the-overflow-sorts-by-activity.md) decides, which does not
  exist yet and must not be the fourth hand-written keyboard list.
- **Label association** where a control is not already wrapped by its label.

What is not taken: colour, type, spacing, density, elevation, motion, iconography. charter's
look is hand-written CSS and stays that way.

## The trap this decision walks towards, named

**"We style it ourselves" must not become "we build the controls ourselves."** That slide is
how the window got here: three tablists that are `role="tablist"` and nothing else, four modals
that are `aria-modal` and nothing else. Every one of those was a decision to write the markup
and get to the behaviour later, and later did not come. A headless primitive is specifically the
tool that makes the behaviour arrive with the markup, and taking it is only worth anything if
the next control is built on it rather than beside it.

The test is not "did we add a dependency". It is: **the next control that needs focus, arrows or
a menu is not hand-written.** If `Palette`'s arrow handling is still the model the third menu
copies, this ADR bought nothing.

## What was rejected

- **MUI, and any component library that brings a design language.** Argued above. The operator
  proposed it and decided against it the same day, on argument 1.
- **Keep hand-writing everything, and just add the missing CSS.** The cheapest fix for the bug
  actually reported, and it fixes only that bug. It leaves four modals that lie about being
  modal and three tablists that no keyboard can walk, and it is the choice that priority 2
  forbids in as many words.
- **A headless library for the look as well** — an unstyled component set plus a token system
  imported from it. Rejected because the visual language is the part that is charter's, and the
  reference is Zed rather than anything shipped in a package.
- **Nothing, until an accessibility audit says what to buy.** The list above *is* the audit, it
  was read off the tree, and every item on it is a promise the markup already makes.

## Consequences, including the ones that cost something

- **The app grows its first UI dependency that is not a terminal.** `app/package.json` has held
  React, xterm and `react-resizable-panels` and nothing else. ADR 0026 locked the stack against
  measurements; this adds to it, and the bundle delta belongs in the PR that lands it, measured,
  the way 0026 measured the renderer arms. **If the delta is large enough to be felt at cold
  start on the platform that is already 12× over, argument 2 stops being precautionary and this
  decision is reopened.**
- **Two systems now describe one control**: the primitive's behaviour and charter's CSS. A
  primitive that renders an element charter has no rule for produces exactly the defect that
  started this — an unstyled run of text. The visual language has to be written down somewhere a
  new control can be built from, and it is not written down today.
- **The bug that prompted this record is not fixed by this record.** It is a missing stylesheet,
  it is still missing, and it needs its own change. Saying so here is the only way it does not
  get closed as collateral.
- **Retrofitting is four dialogs and three tablists**, all in surfaces that scenario tests drive
  (`app/e2e/specs/`), and a focus trap changes what `Tab` does in every one of those specs. This
  is not a leaf-node dependency addition.
- **`Palette` keeps its own list until something replaces it.** It works, it is tested, and
  rewriting a working keyboard list is not what this decision is for. It stops being the pattern
  to copy; it does not stop being the code that ships.
