# A plugin is a subprocess, or charter has no plugins

The operator decided on 2026-09-22 that charter-app becomes a pluggable platform with a plugin
runtime that runs third-party code. The recommendation given was *not now*; the decision went the
other way and is not re-litigated here. What was agreed alongside it is that **the threat model
gates the runtime**, and this is that model. It says where third-party code may run, what it may
reach, how it is installed and trusted, why a theme is not any of those things, and — numbered at
the end — what has to be true before a line of runtime ships.

The work is charter-app's. The record is here because `0001`–`0040` are here and a decision about
charter's trust boundary kept in the other repository would split the sequence; ADR 0031 made the
same move for the same reason. Every path below (`crates/charter-core/…`, `app/src-tauri/…`,
`app/src/…`) is in `diazoxide/charter-app` and every bare `#nnn` is an issue there.

**Nothing in this record is implemented.** It is a gate, written before the thing it gates, which
is the only order in which a gate is worth anything.

## The irony is load-bearing, so it goes first

charter-app's whole M3 milestone is a guard that stands between a model and a credential. Its
state today, read off the tree rather than remembered:

- `charter hook pretooluse` is **one switch**. `crates/charter-cli/src/main.rs`'s `is_a_tool_hook`
  answers every word in the `pretooluse`/`posttooluse` namespace with exit 2 — which a harness
  reads as *block* — and `crates/charter-cli/tests/hook.rs` pins that behaviour.
- Three of six stages are in the tree and **each one is wired to nothing, deliberately**.
  `shellseg.rs` ("This module is stage 1 and is wired to nothing"), `heredoc.rs` and
  `shellwrap.rs` ("stage 2 of six and is wired to nothing"), `leakguard.rs` ("This is stage 3 of
  six and is wired to nothing"). Each header gives the same reason: the first partial
  implementation to flip the switch turns fail-closed into
  allow-everything-except-the-part-that-is-ported, so the switch moves in the last PR and nowhere
  earlier.
- #92 measured the size of what is left: A7 alone has a transitive closure of **60 definitions and
  2,138 lines**, 41 of them (68%) shared with the leak guard.

So charter-app is at its safest on this axis precisely because the guard has never run. A plugin
runtime would put third-party code inside the process that is going to host that guard, and it
would do it through a path that has no hook in it at all: a plugin does not call a tool, so
`pretooluse` never sees it, whatever stage it reaches. **A plugin is not a thing the tool guard
can be extended to cover. It is a second door beside the one being built.** That is the sentence
this record exists to make un-forgettable, and it is why the finished guard is item 2 of the gate
rather than a nice-to-have.

## Four existing records, and what they actually say

Each of the four this decision rests on was re-read for this document. Three say what the brief
for this work said they say. One does not, and the difference matters.

**[ADR 0022](0022-a-harness-profile-belongs-to-one-machine.md) — a harness profile is
machine-local so that a committed file cannot decide how a chat launches.** Correct, and the
reason is worth quoting because it transfers wholesale: *"Between pressing `+` and `os.execvpe`
there is no harness permission prompt, no tool call a guard could deny, nothing that shows a
human the words about to be run."* A plugin contributing a palette command is exactly that, one
level up: a click, and something runs.

One thing the summary of 0022 leaves out, and it cuts against the simple reading. **The
2026-09-15 amendment made a launch a writer of code into a config folder.** Where a profile's
probe finds a definite unwired answer, the launch now installs `charter@charter` into the
folder that profile names — no second question, because *"the approval prompt already stands for
the command, and a second yes about the plugin would be asking permission to enforce the rule."*
So the precedent is not "charter never installs anything". It is: charter installs exactly the
thing that makes a chat guarded, into exactly the folder an approved profile names, and says one
line about it. A plugin install is the opposite case on both halves — it is not the guard, and the
folder is charter's own.

**[ADR 0035](0035-a-plane-is-untrusted-until-the-operator-opens-it.md) — a plane is untrusted
until the operator opens it, and the trust record fingerprints what it contributes.** Correct, and
this is the shape to follow. Read off the code rather than the record: `layer.rs:63` is
`const WORKSPACE_KEYS: [&str; 2] = ["enabledPlugins", "env"]` and `layer.rs:71` is
`const RESTRICTIVE: [&str; 2] = ["ask", "deny"]`; `machine.rs`'s `Contribution` fingerprints those
two travelling keys, the restrictive rules, and the programs `.charter/app/reopen.json` would
start, with `starts` and `profiles` held apart *because only one of them is a grant*.

Two corrections. First, **`enabledPlugins` is Claude Code's plugin list, not charter's.** The word
"plugin" is already spoken for inside this exact threat model and inside the exact dialog a
charter plugin would have to appear in. A first-open prompt that says *this project enables 3
plugins* and *this machine has 2 plugins installed*, meaning two unrelated things, is a consent
surface that has stopped being read. Whatever charter's own extension is called, it is not called
a plugin in that dialog.

Second, **the approval path 0035 describes has two open defects, and a plugin trust record built
on it inherits both**:

- **#112** — `layer::readable_text` is an unbounded `read_to_string` with no `O_NOFOLLOW`, and
  `Contribution::of` calls it against a *stranger's* plane at approval time. A FIFO there blocks
  the approval before the app has a window; a symlink at the exact leaf is followed.
- **#123** — the contribution shown in the dialog and the record `put_back` executes are **two
  separate reads**. A write between them is executed without having been shown. The issue names
  its own fix: `Contribution::of` already reads the record, so handing back the bytes it read
  closes the window by construction.

Both are bounded by 0035's own limit — the fingerprint is *"not a defence against an agent that
set out to forge the fingerprint"* — and neither is a reason to distrust the gate. They are a
reason not to copy it before they are closed.

**[ADR 0028](0028-containment-checks-a-path-and-does-not-hold-it.md) — containment checks a path
and does not hold it; the race is accepted and named.** Correct. The paragraph that matters here
is not the measurement, it is the re-opening clause:

> A confined agent would be in the model, and charter does not have one. The honest version of the
> third answer is conditional: the race is out of scope *because* nothing in charter makes an agent
> less privileged than charter itself. The moment something does … this decision is the first thing
> that has to be re-opened.

A plugin runtime is that moment, arriving from the other direction. The whole proposition of a
plugin boundary is that a plugin is *less* privileged than charter. If that is true, then the
accepted race stops being an accident nobody can exploit without already having the operator's
shell: it becomes a way for a confined principal to have charter write charter's own bytes to a
path the plugin chose. Whether the boundary is real enough to trip that clause is the single
sharpest question about anything below, and the answer in this record is that it is **not real
enough yet** — see the honesty paragraph under decision 1.

**[ADR 0031](0031-windows-gets-charters-guards-or-it-gets-no-charter.md) — a guard that cannot be
expressed on a platform refuses rather than degrades.** The rule is right and this record leans on
it hard. **But 0031 is marked `DRAFT — this needs the operator's sign-off before anything is built
on it`, and the decision in it is described by its own text as a proposal.** Citing it as settled
would be citing a proposal as a precedent, which is how a record acquires authority nobody granted
it. So its sign-off is item 1 of the gate. The evidence in it is measured and stands whatever
happens to the decision; the decision does not yet.

## Decision 1 — plugin code runs in a subprocess, over a protocol

The five candidates, and what a compromised plugin reaches under each. The surface every one of
them is measured against is `app/src-tauri/src/lib.rs`'s `collect_commands![…]`: **forty
commands**, among them `send_input` (keystrokes into any chat's pty), `watch_session` (every byte
any chat produces), `worktree_remove` and `worktree_merge`, `start_chat`, `approve_plane`,
`pin_chat`, `quit`.

**The main webview — ruled out.** A plugin there reaches all forty, because Tauri's IPC has no
per-caller identity *inside* one webview: `app/src-tauri/capabilities/default.json`
grants `core:default`, `opener:default` and `notification:default` to the window, and charter's
own commands are reachable by anything executing in it. The only thing keeping foreign script out
of that window today is `tauri.conf.json`'s
`"csp": "default-src 'self'; style-src 'self' 'unsafe-inline'"`, and a plugin is local by
construction — loading one is the precise thing that CSP exists to prevent, done deliberately. DX
is the best of the five and the isolation is zero, which is the combination this repository's
priority order is most likely to mistake for a good trade.

**A Web Worker — ruled out, and the reason is written down because this is the cheap answer
everybody reaches for.** A worker has no DOM. It has the same origin, and `invoke` works from it.
So it isolates a plugin from the surface that does not matter (pixels) and not at all from the
surface that does (the forty commands). It would *read* as isolation to every later reviewer while
being a naming convention. A boundary that looks like one and is not is worse than no boundary,
which is 0022's sentence about a chat that looks guarded and is not, applied to a process.

**A second Tauri webview — ruled out as "the protocol, plus a browser".** This one is real: Tauri
capabilities are per-window, so a plugin window can be granted a different permission set. But
capabilities gate *Tauri's* plugin permissions, not charter's own `#[tauri::command]`s, which are
registered on the app and would each need a gate written by hand — which is the protocol, written
in a harder place. Meanwhile a second WebKit view costs memory against ADR 0026's limits for the
benefit of a boundary that still has to be hand-built inside it.

**WASM with an explicit import surface — right eventually, wrong first.** It is the only option
that makes the capability list *enforced by construction*: no ambient authority, no syscalls, an
import table that is the grant. Two costs. DX is the worst of the five, and DX is priority 1 here
(ADR 0025): a plugin author compiles a toolchain, a stack trace is an offset, and `println!`
debugging needs a host function before it works. And — the part that is usually missed — WASM
gives you the *enforcement* of a capability list for free and **none of the design of it**. The
hard problem below is deciding what the capabilities are; WASM does not help with that and cannot
be adopted until it is answered. It is the right answer for the day a plugin must be fast and
hot-reloadable, and that day is not the first day.

**A subprocess speaking a protocol — the recommendation.** Four reasons, in this repository's own
priority order:

1. **DX (priority 1).** A plugin is a program. It runs in a terminal, takes a debugger, prints to
   its own stderr, and its whole conversation with charter is a log a human can read. Every other
   option debugs worse, and an isolation model nobody can debug gets routed around — which is the
   failure mode this decision is most exposed to.
2. **Standard practice (priority 2).** LSP, DAP and MCP are all this shape. The repository's own
   rule is *never build custom tooling where a standard tool exists*, and a line-delimited
   request/response over a local socket is the most standard thing in this space.
3. **The machinery is already here, guards included.** `hookwire` binds a unix socket and sets it
   `0600` (`hookwire.rs:292`), inside a directory created `0700` at creation rather than
   chmod-ed afterwards, with a review-found defect already fixed there (the earlier version
   created the directory at the umask and discarded the result of tightening it). And its Windows
   arm is **already a refusal** — `bind` and `send` return `Unsupported`, because Rust's standard
   library exposes no `AF_UNIX` there and a socket file has no mode bit to set. That is ADR 0031's
   rule already applied once, in the exact code a plugin channel would reuse.
4. **The OS supplies the part charter cannot write.** The workspace is `unsafe_code = "forbid"`, so
   a Windows DACL is out of reach today (0031, #98) and so is anything else that needs a raw
   syscall. A process boundary is the one boundary charter gets without writing `unsafe`.

What it costs, stated: a round trip instead of a call, and one process per plugin. The nearest
measured number in the tree is `hookwire`'s own — *"the 1.8 ms the whole hook call was measured
at"* — and that is a different shape of call, one line in one direction with no answer. **A plugin
round trip is unmeasured**, and measuring it is a precondition of fixing the protocol, not
something to do afterwards. It is affordable because a plugin is not on the terminal's hot path;
and the day a plugin *wants* the hot path, the answer is to refuse, not to move it in-process.

### The honesty paragraph, which is the most important one here

**A subprocess does not confine a plugin below the operator.** It runs as the same user, with the
same filesystem, the same network and the same ability to `exec`. It can read `.charter/vaults/`,
write the machine store, and edit `charter.local.toml` without asking charter for anything. The
protocol bounds **what charter will do on the plugin's behalf**; it does not bound what the plugin
can do itself.

Everything in decision 2 is therefore a statement about charter's own conduct, not a cage. Saying
otherwise would be the exact error `SECURITY.md` refuses to make about the vault guard — *"a
guard against mistakes, not an attacker with shell access as your user"* — and `profiletrust.rs`
refuses to make about its own record. Real confinement is a sandbox: Seatbelt on macOS, seccomp or
Landlock on Linux, AppContainer on Windows. Each is a platform-specific piece of work, at least
one of them needs `unsafe` or a vetted crate, and none of them is costed. Until one exists, **a
plugin is trusted code that charter is polite to**, and the trust decision at install time is
carrying the entire weight. That is why decision 3 is long and decision 2 is short.

## Decision 2 — the capability surface, enumerated honestly

"Grantable" below means *charter will do this for a plugin that asked and was approved*. It never
means *a plugin cannot do this otherwise*; see the paragraph above.

| Surface | What it is, in the code | Grantable? | What a grant means |
| --- | --- | --- | --- |
| The DOM, the window's pixels | one webview, `app/src/` | **No, ever** | A theme reaches appearance as data. Code never reaches the tree charter draws consent prompts into. |
| Tauri commands, as a set | the forty in `collect_commands!` | **No** | There is no grant called "the commands". Each is its own grant or it is not one. |
| A chat's output bytes | `watch_session` | Yes, **per chat**, revocable, visible while live | The highest-value grant in the table: a transcript carries whatever the operator pasted in. Never per plane, never standing. |
| Typing into a chat | `send_input` | Yes, but **not in the minimum set** | A keystroke into a shell with the operator's hands' authority. Per chat, time-bounded, shown while held. |
| The plane on disk | `plane.rs`, `workspaces.rs`, `personas.rs` | Not as "the plane" | A plugin gets what the protocol hands it. "Read the plane" is not a capability, it is the absence of one. |
| The machine store | `machine.rs`, `$CHARTER_CONFIG_HOME/charter/` | **No, at any level** | It is where charter records *what it may open without asking*. A write there is a forged approval for a project, which is a program that starts at the next launch. |
| `.charter/app/reopen.json` | `reopen.rs` | **No, at any level** | `reopen.rs` says it: *"a way to have a command run at every later launch — before any window, with nothing to click"*, and `program`, `args` and `cwd` are **not checked at all**. |
| Harness profiles | `charter.local.toml`, `profiletrust.rs` | **No** | ADR 0022's entire argument. A plugin that can write a profile has written a command line. |
| The harness environment | `layer.rs` `WORKSPACE_KEYS` | **No** | ADR 0022 measured where it lands: *"A variable set on the harness process reaches the shell the model runs."* 0022 already refuses `KEY`/`TOKEN`/`SECRET`/`PASSWORD` in a profile's own `env`. |
| The network | — | **Declared, not granted** | charter cannot enforce it on a subprocess. It is shown in the prompt as a claim the plugin makes about itself, and the record must say that it is a claim. |
| Vaults | `.charter/vaults/` | **Absent** | Not "denied". There is no capability name for it and there must not be one, because a name is a thing a later grant can be attached to. |

**The machine store and `reopen.json` are execution inputs, and the record proves it.** #129 was a
test suite writing 49 chats into the operator's live plane, because `plane::find_root` walking up
from a test process answered with the real plane; the fix (#132) is a compile-time fence that
panics if a resolved, opened, read or written plane — or the machine store — is outside
`$CHARTER_PLANE_FENCE`. A fence exists for those paths because writing them is running something.
Nothing a plugin is granted may touch either.

**The minimum viable capability set is two things, and neither is a capability in the runtime
sense:**

1. **Contribute a theme** — declarative data against a closed vocabulary. See below.
2. **Contribute a named palette command that, when the operator invokes it, sends one request to
   the plugin and displays the text that comes back.** This is the smallest thing that is
   executable at all: no ambient read, no standing subscription, one round trip per deliberate
   human action, and an answer that lands in a surface charter controls.

Everything else waits for a plugin that exists and wants it, and the want is written down before
the capability is. A capability invented for a hypothetical plugin is a grant nobody audited
against a real use.

## Decision 3 — how a plugin is installed and trusted

**A plugin never travels in a plane.** ADR 0022's argument applies one level up and applies
*harder*. A harness profile at least has to survive the approval prompt before it runs; a plugin
that contributed a palette command would run on a click, which is the very gap 0022 opens with. A
`[plugin.<name>]` table in `charter.toml` is refused by name, exactly as
`[harness.<name>]` is. This also settles the collision noted above: a project cannot bring a
charter extension with it, so the trust dialog's two uses of the word "plugin" never appear in the
same list.

**A plugin is machine state, and it has to argue for that.** ADR 0034's rule is that a fact may
live outside every plane *only when it is about the operator or the machine and is false inside
any one plane*, with "four things, and nothing else" — and ADR 0040 already made it five by
arguing rather than appending. A plugin list is the **sixth** and here is its argument: which
plugins this machine has, and what the operator approved each to do, is about the machine, is
false inside any one plane, and passes 0034's own test — *deleting this file must cost the
operator their arrangement and their approvals and nothing else*. It does, provided **a plugin's
own data never lives in the store**. A plugin is re-installable by name; its state is its own
problem, kept wherever it likes, and charter's store holds a path, a fingerprint and an approval.

**Installed by path, by the operator, from nowhere.** No registry, no marketplace, no fetch by
name. The moment charter resolves a plugin name over the network it owns a supply chain, and
priority 2 (standard practice) has no standard answer for that which fits a tool with one
operator. `charter harness add` was rejected in 0022 on the grounds that *"a chat can run a
command as easily as it can edit a file, so the command could never stand for the operator's
approval of what it wrote"*; the same sentence forbids `charter plugin install <name>` as a
consent step. What stands for consent is the prompt, and nothing else.

**Trust is 0035's shape, with one difference that costs something.** Show what it contributes, ask
once per human per machine, remember the fingerprint, re-ask when what it contributes changes. The
difference: **0035 fingerprints configuration and this fingerprints code.** A plugin's path is not
its contents, so the fingerprint has to be a hash of the executable and of every file it declares,
checked at each launch. That is real work at startup for a real reason — a plugin that rewrites
itself after approval is the attack this whole record is about — and the cost is named here rather
than discovered when the app gets slower.

**Every unreadable state means ask.** `profiletrust.rs`'s opening rule, word for word: a missing
file, a malformed one, an entry that is not a fingerprint, a link, a FIFO, a planted giant — each
reads as "no record", never as approval. *Treating silence as a yes is the one state this record
exists to keep out.*

**And it is not a boundary**, for the reason both `profiletrust.rs` and 0035 state about
themselves: a chat that can write the record can forge it. What the ask closes is the accident, the
plugin installed to see what it did, the one whose update changed what it contributes. It is the
difference between code that ran unseen and code that was read out loud first, and nothing here
should be built as though it were more.

## Themes are the first extension point, and a theme is not a plugin

A theme is declarative data with no executable surface: a file of semantic tokens that charter
turns into CSS custom properties and into xterm's theme object — which today is hard-coded, one
literal, at `app/src/SessionPane.tsx:54`:
`theme: { background: "#181818", foreground: "#d8d8d8" }`. It is the ideal first extension point
because it has a bounded vocabulary charter already owns, a real consumer on day one, and nothing
to isolate.

**What makes a declarative extension safe is four properties, and it is safe only while it has all
four:**

1. **The vocabulary is closed and charter decides it.** The extension fills in values for names
   charter published; it cannot introduce a name.
2. **The value space is not a program.** A colour, a number, a member of an enumeration. Nothing
   whose evaluation is an action.
3. **charter chooses the consumer.** charter decides that this token becomes that CSS custom
   property and that xterm field. The theme never names a destination.
4. **charter parses and re-emits, never interpolates.** A token's text is read into a typed value
   and a fresh string is written out from that value. The theme's bytes never reach a stylesheet.
   An unknown or malformed entry is dropped with a reason and the default stands.

**The line a plugin crosses when it stops being data** — three crossings, each of which turns
property 4 or property 1 into a lie, and each of which will be proposed by somebody reasonable:

- **A value that reaches a CSS context charter did not choose.** `url(…)` inside a token is a fetch
  from the app's origin, which is the CSP's whole job. Parse-and-re-emit is the rule that makes
  this unreachable rather than filtered; a blocklist of CSS functions is the version of this rule
  that fails.
- **Any way of saying *where*.** A selector, a rule, a media query, an element name. A theme says
  what a semantic token is worth. The moment it says where a token applies it is choosing
  charter's layout, and there is no bounded vocabulary left to check against.
- **A reference to a file.** A font path, a background image, an `@import`. Every one of them is a
  read of a path the extension chose, which is a capability wearing a theme's clothes.

**And one that is not obvious: a theme is data and it is still an input to a decision.** A theme
that paints the *needs you* state the same as idle hides a chat that is waiting. A theme that makes
the refusal button in the first-open dialog look like the accept button is an attack on a consent
prompt, delivered entirely in legal data. So the closed vocabulary has a floor: **the consent
surfaces and the state colours are charter's, not the theme's**, and a contrast minimum is
enforced on what the theme does get. A declarative extension is safe from *code execution* by
construction; it is not automatically safe from *deception*, and those are different properties
that this document keeps apart.

## What to build first, and none of it needs the runtime

This is the most useful part of the record. Each item is worth shipping on its own merits, and
each one is something the runtime would otherwise have to invent badly while under pressure.

1. **Theme-as-data**, with the closed vocabulary, the parse-and-re-emit rule, the consent surfaces
   excluded, and the contrast floor. Already being built; this record only adds the four properties
   and the three crossings.
2. **An extension registry with no executor.** One place that answers *what has contributed what to
   this window*, populated at first only by charter's own built-ins and by themes. Every later
   decision here needs that list to exist, and building it now means the first plugin is not also
   the thing that invents it.
3. **Close #112 and #123.** The trust path is the foundation the plugin trust record would be poured
   on. Both are useful without any plugin and both are mandatory with one, and #123's fix is
   plumbing that already has its shape written in the issue.
4. **Finish the tool guard: stages 4, 5 and 6, with the switch in the last PR.** Gate item, not a
   backlog entry. Shipping a plugin runtime while `pretooluse` answers exit 2 to everything means
   running third-party code in a process whose own guard has never executed a line in anger.
5. **Show what is in force, after approval and not only at it.** ADR 0035 shows a project's
   contribution in the dialog and nothing shows it afterwards. A `doctor` row and a window
   affordance that lists the plugins enabled, the environment set, and the extensions loaded is
   the surface every later trust decision is read on.

## The gate: what has to be true before a line of runtime ships

Falsifiable, so that "are we ready" is a checklist and not a conversation.

1. **ADR 0031 is signed off.** It is a `DRAFT` today. Refuse-rather-than-degrade is the rule that
   stops the plugin boundary from being silently absent on a platform, and it cannot be the
   backstop while it is a proposal.
2. **The tool guard is wired.** Stage 6 landed and `is_a_tool_hook`'s blanket exit 2 replaced by
   the real guard.
3. **#112 and #123 are closed**, and the plugin trust record reuses the fixed path rather than
   copying the current one.
4. **A named plugin exists that wants a capability the theme vocabulary cannot express**, and that
   capability is written down — in this sequence — before the runtime that serves it.
5. **The protocol refuses, per platform, every capability it cannot express there.** ADR 0031's
   rule, applied to the new surface, with `hookwire`'s Windows arm as the worked example.
6. **The trust record passes `profiletrust`'s test**: every unreadable state asks, and each of
   those states has a test that has been *seen to go red* with the guard removed — this
   repository's own standard, and the one it keeps missing.
7. **The subprocess's confinement is decided** — a sandbox, or explicitly not one, in writing. If
   not, **ADR 0028 is re-opened in the same PR**, because a plugin is the confined principal whose
   arrival 0028 names as the trigger for re-opening it.
8. **The plugin round trip is measured** against ADR 0026's limits before the protocol is fixed.
   `hookwire`'s 1.8 ms is a one-way line, not a round trip, and is not a substitute.

## What was rejected

- **The main webview, because it is easy.** It is forty commands and a deliberate hole in the CSP.
- **A Web Worker as isolation.** It isolates the DOM and not the command surface, and it would read
  as a boundary to every later reviewer.
- **A second Tauri webview.** Capabilities gate Tauri's permissions, not charter's commands; the
  gate still has to be written, now inside a browser.
- **WASM first.** Worst DX of the five against priority 1, and it enforces a capability list it
  cannot help design. It stays the right answer for later.
- **A plugin travelling in a plane.** ADR 0022's argument, one level up, where the click has even
  less in front of it.
- **A registry or marketplace.** charter would own a supply chain, and `charter plugin install`
  could no more stand for approval than `charter harness add` could.
- **A capability called "the plane" or "the filesystem".** Those are the absence of a capability
  model, named as though they were one.
- **Calling a theme a plugin.** It has no executable surface, it needs none of this machinery, and
  bundling them would hold a safe thing behind an unsafe one's gate.
- **Deferring the threat model until a plugin exists.** The threat model is the gate, and a gate
  built after the thing it gates is a description.

## Consequences

- **The first plugin is slower than a function call and nobody has measured by how much.** Stated
  as an open number rather than an estimate; gate item 8.
- **A subprocess is a second process to start, supervise and reap**, in an app whose session
  lifecycle is already the hardest part of it. `Planes`, `Chats` and the hook socket all learned
  this the expensive way, and a plugin host is a fourth thing with the same failure modes.
- **A plugin can do everything the operator can, and charter's grants are charter's manners.**
  Until a sandbox exists, the install-time decision carries the whole weight, and this record says
  so in three separate places on purpose.
- **The fingerprint is a hash of code, checked at each launch**, so a plugin makes launches slower
  in proportion to how many there are. ADR 0035's fingerprint reads two settings keys; this one
  reads an executable.
- **A theme cannot do something somebody will want**, and the answer will be to widen the
  vocabulary rather than to admit a rule, a selector or a path. The three crossings are written
  down so that widening it is a decision with a name on it.
- **The machine store grows a sixth kind of entry**, and ADR 0034's rule is narrower for it: the
  next one has to argue against five precedents instead of four.
- **charter-app now has a decision it has not implemented.** That is the point, and the risk is the
  ordinary one for such a record — that the first implementer reads the recommendation and not the
  gate. The gate is numbered so that skipping an item is visible.
