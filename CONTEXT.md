# charter

charter is a control plane for agent development: it holds the personas, workspaces and
repos a team works through, and enforces the invariants that keep parallel work from
colliding. It has no model and makes no judgements about the *content* of work — every
term below describes something charter can observe or enforce without understanding it.

## Language

### The plane

**Plane**:
The control plane — the directory holding `charter.toml`, its personas, inventory,
workspaces and config. Not a place work happens (ADR 0008).
_Avoid_: root, repo, home

**Project**:
A plane, in the words the desktop app puts on a menu: "Open Project…" opens a directory that
has, or will get, a `charter.toml`, and the top-level switcher is a plane switcher (ADR 0033).
The same thing under a second name, deliberately — a project that was not a plane would be the
embedded shape ADR 0007 deleted, returning. Never a *workspace*, which is why that entry has
carried `_Avoid_: project` since this glossary was written.
_Avoid_: workspace, repo, folder

**Opener**:
What a window shows when it has no plane: the recent planes and a way to open or create one.
Reached whenever charter is started other than from a terminal standing inside a plane —
a double-clicked app has `/` for a working directory and resolves no plane at all (ADR 0034).
_Avoid_: welcome screen, launcher, start page

**Trusted plane**:
A plane whose path this operator has opened once and approved on this machine, remembered
outside every plane (ADR 0034) as a fingerprint of what was approved rather than as a path
(ADR 0035). Until then a plane is *untrusted*: its committed settings would choose the
harness's plugins and set its environment, and its reopen record would start programs, before
anybody had read either. Not a boundary — an approved plane is in force in full, and a chat
that can edit the plane can edit what charter reads from it.
_Avoid_: safe, verified, sandboxed

**Harness**:
The agent runtime charter runs inside — Claude Code, opencode, Codex. Charter enforces the
same invariants on every harness; what differs is what it can *offer*, and `charter doctor`
names each gap rather than leaving it to be found (ADR 0015).
_Avoid_: host, client, runner, IDE, platform

**Harness profile**:
A named way to launch one harness kind — its kind, its command, its environment — declared
in the plane's `charter.local.toml`, which charter keeps out of git because a profile's
command runs on a click with no permission prompt in between. Every registered kind is also
a profile named after itself. Never an *alias*, which is a shell feature charter never sees,
and not an *account*: a profile need not be a different one (ADR 0022).
_Avoid_: alias, account

**Kind**:
Which harness program a profile launches, written as the word typed after `charter`:
`claude`, `codex`, `opencode`. `$CHARTER_HARNESS` still holds the registry's name for it —
`claude-code` — because hooks compare that value; the profile's own name rides beside it in
`$CHARTER_HARNESS_PROFILE`.
_Avoid_: type, flavour

**Profile selector**:
What a new chat's pane shows before any harness has run in it; the harness starts in that
pane once a profile is picked. Not the workspace *picker*, which runs before tmux exists
because a workspace is a tmux session and charter has to know which one first.
_Avoid_: menu, dropdown, picker

**Host**:
A forge host — `github.com`, a self-hosted GitLab. Never the agent runtime: both senses of
this word were load-bearing at once until ADR 0015 split them.
_Avoid_: harness, server, remote

**Workspace**:
An isolated per-task working context, owning clones of the repos that task touches. The
task is the unit: one workspace, one task — so a workspace running N pieces in parallel is
what "a fleet" describes, and charter stores no such thing separately.
_Avoid_: project, session, environment, fleet

**Clone**:
A repo a workspace owns, on disk under that workspace.
_Avoid_: checkout, copy

**Worktree**:
An additional working tree over a clone's object store, living outside every clone so that
build tools cannot recurse into it and `git clean` inside the clone cannot destroy it.
_Avoid_: branch dir, tree

**Persona**:
A role — Release Engineer, Forge Integration Engineer — with its own charter, memory and
vault. A persona is *who does the work*, never a queue of work (ADR 0005).
_Avoid_: agent, bot, owner, worker

**Todo**:
Workspace-scoped intent that expires: it stops being true the moment it is done or
abandoned, which is why it lives beside memory rather than inside it (ADR 0004).
_Avoid_: task, ticket, item

**News**:
A shipped, per-item note that a version introduced something, carrying an optional probe
for whether this plane has adopted it. Not a changelog: an entry exists to be *acted on*,
and one with nothing to adopt is one line. Staged as `unreleased-<slug>.md` until a release
stamps it, so an entry never names a version that was not true.
_Avoid_: changelog, release notes, announcement

### Chats

**Chat**:
A frame tab: one harness conversation, in one workspace, for life. Its id
(`<workspace>.<n>`) is allocated, handed out once for the life of the plane, and never parsed
for meaning; a reopened chat keeps it. Its workspace is written by the launch that made it —
so a chat cannot be moved to another workspace, only opened in one. It is linked to exactly
one harness session: the id charter handed Claude Code, or the first id Codex or opencode
reported in that start — never a guess.
_Avoid_: session, spawn, sub-session

**Ended tab**:
A chat whose harness has exited — cleanly, by crashing, or killed from outside — whose tab is
still on the strip holding a choice: resume the conversation, start fresh, or close the tab.
It is the one state a chat can be in with no harness running in it and no decision taken yet.
Nothing restarts by itself: every start is an operator's keypress, and neither end of input
nor Ctrl+C is read as an answer. Closing the tab is what ends the chat, and it ends it for
good.
_Avoid_: dead tab, closed chat, zombie

**Title**:
Optional words a person gave a chat, drawn wherever that chat is named to a person — in place
of the id on the strip, and after it everywhere else. **It is never an identity**: every link,
record, kill, reap and claim goes on using the id, and a chat with no title behaves exactly as
one did before titles existed. It is one line of printable text, at most 60 characters, set by
a rename row, by the selector's title row at `+`, or by a handoff brief's first line. Charter
composes Claude Code's session name from it (`<title> · <id>`) and passes that at the next
start or resume — it never types `/rename` into a harness, and Codex and opencode are handed
no name at all.
_Avoid_: name (which is what Claude Code calls the session name charter composes), label,
rename as a noun

**Exit gate**:
The one surface that leaves charter: `F10`, the `F10 close` button at the right end of the
identity row, and the same two rows in `F2`. *Close charter (keep chats running)* detaches
the **presser** and nothing else; *Close charter and stop all chats…* leads to the quit
confirmation and then records and stops every chat of this project. It is never drawn inside
a tmux the operator already had — charter binds no key and draws no button there, and the
rows live in the palette. Its cursor opens on the harmless row in every state.
_Avoid_: exit menu, close dialog, quit menu

**Presser**:
The tmux client that made a gesture — expanded from `#{client_name}` at the keypress, or read
off the panel pane the click bind recorded it on. It is what *Close charter (keep chats
running)* detaches, proven attached to this chat's session on this plane by one listing before
anything is detached. **A presser charter cannot name is not a fallback to every client**: the
row is listed refused with the gesture that works.
_Avoid_: the client, the terminal (unqualified), the current client

**Handoff**:
Opening a chat, here or in another workspace, whose first message is a brief the operator
approved at the harness's own permission prompt (ADR 0021). A handed-off chat never reports
back to the chat that opened it: a caller that needs the answer wanted a sub-agent, which
charter neither gates nor converts.
_Avoid_: spawn, delegation, sub-session

**Brief**:
The self-contained message a handoff carries — the only context the new chat starts with.
It travels as one command-line argument, so any process that can list processes can read it
while the harness starts and it never carries a secret; charter keeps it in the chat's
private state under `.charter/` and never in a committed file.
_Avoid_: prompt, context, instructions

### Parallel work

**Plan**:
The set of piece names a task was divided into, recorded as the workspace's todos. charter
holds no other representation of it, and never judges whether it covers the task (ADR 0012).
_Avoid_: breakdown, decomposition, backlog, assignment

**Piece**:
A unit of one task that exactly one worker owns, and the worktree that holds it. A piece
*is* a worktree — `workspaces/<ws>/.worktrees/<repo>/<piece>` — not a separate record that
points at one. Scoped to a single repo: a task spanning two repos is two pieces.
_Avoid_: task, chunk, shard, work item, unit

**Claim**:
One worker's exclusive ownership of a piece, established by that worker creating the piece's
worktree. Git is what makes it exclusive, and the claimant is always the creator — a piece
created for somebody else is not claimed by anyone.
_Avoid_: lock, lease, reservation, assignment

**Declaration**:
A statement only the worker can make, because it is a judgement rather than a fact on disk.
An outcome is the only declaration there is.
_Avoid_: report, update, signal

**Observation**:
Something charter can see without being told — that a piece's worktree exists, that a
worker was alive at some moment. Observations are never judgements, which is why charter
may record one about a worker that never speaks to it, and why it may not conclude anything
from their absence (ADR 0009).
_Avoid_: check, probe, ping

**Worker**:
One live session holding one piece. Distinct from a persona (the *role* it may be acting
as) and from an agent (a *generated sub-agent definition*, which `charter report` counts by
name) — three things the same word used to cover.
_Avoid_: agent, sub-agent, runner, bot

**Outcome**:
What a worker declares became of its piece: `done`, or `abandoned` with a reason. An outcome
is a statement git cannot make on its own — commits and branches show what a piece *left
behind*, never whether the worker considered itself finished.
_Avoid_: result, status, state, report

**Silence**:
A piece with a claim and no outcome. Not a third outcome but the absence of one, and the
shape every undeclared failure takes — denial, timeout, or a killed session alike. Silence
has an *age*, which is the only thing charter says about it: the cause is never inferred.
_Avoid_: stuck, failed, timed-out, orphaned, dead

## Prose

The glossary governs words; this governs sentences. It is written down because docs drift
gradually — no single paragraph looks wrong, and a year later the README sells instead of
explaining. Every rule below is a pattern already in these docs, recorded so the next
person or session can follow it without having read all of them first.

**Name the failure, not the feature**:
A heading says what went wrong often enough to get built around — "Two sub-agents that need
the same repo" — and the body answers it. A reader recognises their own bad afternoon in a
failure; nobody recognises themselves in "Worktrees".
_Avoid_: Features, Key benefits, Capabilities, any heading that is only a noun

**Make every claim checkable**:
Reach for the number, the path, the flag, the file mode: "plaintext JSON at file mode 0600"
carries what "stored securely" does not. A sentence that could move to another project's
README unchanged is carrying no information.
_Avoid_: secure, robust, powerful, seamless, blazing, simply, just, easily

**State the limit at full volume**:
What a thing does not do belongs in the same breath as what it does. "The vault is not a
password manager" is the sentence that earns the rest of that section its trust. A
limitation the reader discovers alone was concealed, however honestly it was omitted.
_Avoid_: note that, please be aware, a caveats section at the end

**Explain the why — the what is already on screen**:
A paragraph beside a command earns its place by naming the failure that command prevents,
never by restating it. The same rule governs code comments, which is why the good ones read
as records of things that went wrong.
_Avoid_: This command will, As you can see, In other words

**Describe the reader's day, not the abstraction**:
"Two features and a hotfix means three sets of branches, and if they share a checkout you
spend the day stashing" — second person, concrete nouns, an afternoon the reader has had.
An abstraction says the same thing while being impossible to disagree with.
_Avoid_: workflow, productivity, overhead, friction, streamline, leverage, empower

**A refusal is the rule working**:
Where charter denies something on purpose, say so plainly and name the fix in the same
breath. A reader who does not know the rule reads the denial as a bug and files it.
_Avoid_: error, failure, blocked — for anything charter did deliberately

**Never tell the reader how to feel**:
The evidence goes on the page and the reader draws the conclusion. No exclamation marks, no
promise that something is easy.
_Avoid_: !, amazing, incredible, you will love, it is that simple

One rewrite, for calibration:

> **✗** charter provides powerful workspace isolation, seamlessly enabling developers to
> effortlessly manage concurrent tasks and boost productivity.

> **✓** Two features and a hotfix means three sets of branches across a shifting set of
> repos, and if they share a checkout you spend the day stashing. A workspace is one
> directory of clones per task, each repo on its own branch.
