# The control plane: `charter.toml`

A **control plane** is any directory marked by a `charter.toml` file. `charter` finds it
by walking up from your current directory — the same contract git, cargo, and npm use —
so once you're anywhere inside one, every command just works. There is nothing else
special about the directory: no required name, no fixed location. `charter init` creates
one from nothing (see the README's quickstart).

A fresh `charter init` writes the minimal file:

```toml
schema = 1

[[forge]]
kind = "gitlab"

[memory]
share = "local"

[persona]
default = "steward"
```

That last key is the plane's **front door** — the persona a session adopts when nobody has
chosen one. `init` also scaffolds it: one generic `personas/steward/persona.md` you own and
can rename, rewrite or delete. Name it something else with `charter init --front-door ops`,
or skip it entirely with `--no-front-door`; either way charter's own code knows only *that*
a plane may declare a default, never which one. If the plane already has personas, `init`
scaffolds nothing — it creates only what is absent.

The generated charter declares `routing: advise`, so once a second persona exists the front
door sees the roster on work-shaped prompts. See `charter docs show personas`.

## Every key, in full

```toml
# Layout version this file was written for. `charter` refuses to run against a
# schema NEWER than it understands (upgrade the CLI instead of guessing); it has no
# problem reading an OLDER schema. Omit it and 1 is assumed.
schema = 1

# Optional. The persona a session adopts when nothing else selects one — this plane's
# front door. `charter persona default <name>` writes it. Overridden per developer by
# `charter persona use`, `$CHARTER_PERSONA` and `--persona`; a name that no longer exists
# resolves to no persona at all, and `charter doctor` says so.
[persona]
default = "steward"

# Optional. Only needed to move worktrees off their default location.
[plane]
worktrees = "../plane.worktrees" # Where worktrees live. A relative path resolves against
                                  # this file's directory; $CHARTER_WORKTREES overrides it.
                                  # Default: per-workspace, under
                                  # workspaces/<ws>/.worktrees/ — see "Where worktrees
                                  # live" below.
                                  # This file is committed and `git worktree add` creates
                                  # directories here, so the value must land inside the
                                  # plane or in a single sibling of it (the shape above).
                                  # Anywhere further afield is ignored and `charter doctor`
                                  # says so; $CHARTER_WORKTREES — your machine, your
                                  # choice — is not restricted.

# One [[forge]] block per code-hosting forge this control plane tracks. A single-forge
# control plane (the common case) declares exactly one; see "Mixed-forge" below for more
# than one. Each block is independent — its own owner, host, and excludes.
[[forge]]
kind = "gitlab"                  # "gitlab" | "github". Default: "gitlab".
group = "my-org"                 # the GitLab group (or GitHub org/user) this forge tracks.
                                  # `owner` is accepted as a synonym — see "group vs owner" below.
host = "gitlab.com"              # optional: a self-hosted forge's host (GitLab Enterprise,
                                  # GitHub Enterprise Server). Default: the forge's own public
                                  # host (gitlab.com / github.com). See docs/forges.md.
                                  # A bare hostname, optionally :port — no scheme, no path,
                                  # no "@". It widens the SSH guard's deny set and becomes
                                  # the `url.https://<host>/.insteadOf` that
                                  # `charter git-policy --apply` writes, so a block whose
                                  # host is not a hostname is skipped and reported.
exclude = ["this-control-plane"] # repo names never written into the inventory — typically
                                  # the control plane's own repo, so `discover` doesn't list
                                  # itself as a clone target.

# How far a written memory (persona or workspace) travels by default. See "Memory
# posture" below — this is the single most consequential default in this file.
[memory]
share = "local"                  # "local" | "commit" | "push". Default: "local".

# The workspace selected when none is active yet (no --workspace, no $CHARTER_WORKSPACE,
# no prior `charter workspace use`).
[workspace]
default = "default"              # Default: "default".

# Which row bare `charter`'s profile selector starts on. Opt-in; absent, it starts on the
# first row that can run. `default` is the only key read here. Harness profiles — a command and an environment
# each — live in charter.local.toml, which is never committed, and a [harness.<name>]
# table in this file is refused. See "[harness] — profiles, and the default" below.
[harness]
default = "claude"               # "claude" | "opencode" | "codex" — the word you would
                                  # have typed after `charter`. No default: charter does
                                  # not pick one for you. A name it does not know is
                                  # REPORTED, not ignored — see "Bare `charter`" below.

# Which charter this plane tracks. Opt-in; absent, you track published releases.
[update]
channel = "stable"               # "stable" | "dev". Default: "stable". A CLOSED set:
                                  # anything else is not sanitised, it is discarded, and
                                  # the plane stays on "stable". See "The dev channel"
                                  # below and docs/install.md.
```

### `group` vs `owner`

GitLab calls the thing a repo lives under a **group**; GitHub calls it an **org** (or a
personal **user** account). `charter` accepts either key name in a `[[forge]]` block —
`group` and `owner` mean the same thing — so you can use whichever reads naturally for
the forge in question. If a block sets both, `group` wins. `charter init --owner <name>`
always writes the field as `owner`, since it works for either forge kind.

## One shape

A control plane is its own directory, and a workspace holds **clones** — one per repo the
task touches, each of which can carry worktrees. That is the only arrangement.

charter used to have a second one, `shape = "embedded"`: charter installed *inside* the
single codebase it served, where a workspace held worktrees of the plane's own root rather
than clones. It was removed — see [ADR 0007](adr/0007-one-plane-shape.md) — because every
plane exercised exactly one of the two, so the other was carried on trust. An existing
`shape` key is simply ignored.

`charter init` therefore produces the same plane wherever it runs. Being inside a git repo
no longer changes what you get; it changes only what init *offers*, which is to clone that
repo into your first workspace:

```
$ charter init --forge github --owner acme
✓ Initialized control plane (schema 1) → charter.toml, personas/, …
• You are standing in the git repo 'myapp'. Work happens in a workspace, not in the plane
  root — clone it into the first one:
      charter init --clone-this-repo
```

That is an offer, not a prompt: charter never reads stdin (it runs inside hooks, where
blocking would hang the turn), so the second command *is* the acceptance — the same shape
`charter report` uses for consent. Run it and you get `workspaces/default/myapp/`, cloned
from the repo you are standing in and pointed at the same `origin` it has; ignore it and
the plane is complete as it stands. Either way the control plane itself is identical, and
nothing is written to your repo's git state.

### The plane root is not a place to work

The directory holding `charter.toml` holds the control plane — personas, inventory,
workspaces, config — and nothing you edit. Work happens in a workspace's clones.

Nothing in the filesystem enforces that, which is why it is worth stating. The plane root
is a real git repo, and `charter init` is documented as something you run inside your
existing repo. charter no longer *lists* it as one of your repos, but not listing a tree is
not the same as preventing work in it: two sessions that both sit in the plane root share
one working tree and one HEAD, and will thrash each other's branches while charter reports
two different workspaces.

So the status line warns when the plane root is dirty or off its default branch, and
`doctor` checks the same thing at session start. See
[ADR 0008](adr/0008-the-plane-root-is-not-a-work-tree.md) for why those are warnings rather
than refusals.

### Where worktrees live

Worktrees normally sit at `workspaces/<ws>/.worktrees/<repo>/<piece>` — deliberately
**outside every clone**, so that nx, jest and maven never recurse into them and a
`git clean -xfd` inside a clone cannot destroy live work.

That default is right whenever a workspace holds clones, which is always. It matters
because the failure it avoids is quiet: put worktrees anywhere a build tool globs from and
the tree answers a root-level glob with several copies of itself. Measured in a layout that
made that mistake — 214 test files discoverable from one root, 142 of them duplicates.
`.gitignore` hides that from git and from nothing else; pytest, jest, nx, tsc and every IDE
indexer read the working tree directly.

Set `[plane].worktrees` (or `$CHARTER_WORKTREES`) to put them somewhere else. Only the
worktrees move — `workspaces/<ws>/memory/` and `refs/` stay inside the plane, because they
are a few KB of text and `charter workspace live` exists precisely to un-ignore them so a
team can commit them.

Relocating an existing worktree means rewriting git's own `gitdir` pointer, and
`git worktree move` is the command that does it correctly — changing this setting never moves
one for you. The one move charter makes is `charter workspace rename`: the workspace's
directory under the root is named after it, so the rename moves that directory too and
relinks every worktree in it ([workspaces.md](workspaces.md)).

### What a workspace is

A workspace is **a set of working trees** — one task's code, kept apart from every other
task's. It gets them by cloning: `charter workspace create feature-x`, then `charter clone`
the repos that task touches. `default` is an ordinary workspace like any other.

```
$ charter workspace create feature-x
✓ Workspace 'feature-x' ready (LOCAL …) → workspaces/feature-x/
✓ Working tree → ../app.worktrees/feature-x/app/feature-x
  enter:  cd ../app.worktrees/feature-x/app/feature-x && claude
  Being in that directory IS this workspace — no pointer needed.
```

Its branch is the workspace name unless you pass `--branch`.

A solo user with one repo used to be able to `charter init` and carry on working in that
repo, because `default` *was* the plane root. It no longer is (ADR 0007), so their path is
`charter init --clone-this-repo` — the offer above — and then work in
`workspaces/default/<repo>/`.

**Selecting a workspace with no tree is refused**, because it would put you on the same
files as every other workspace — the thing workspaces exist to prevent. `charter workspace
create <name>` gives it one.

### The directory you are in decides the workspace

A workspace's trees live at paths that name it — `workspaces/<ws>/<repo>/` for a fleet
clone, `<worktrees-root>/<ws>/<repo>/<piece>/` for a worktree — so **being inside one is
the answer**, ahead of any pointer:

```
--workspace → $CHARTER_WORKSPACE → the tree you are standing in → session → terminal → default
```

You cannot be in two directories at once, which is precisely the property the pointers
lacked: a session that had never chosen anything could inherit another session's choice.
`charter workspace current` reports `via cwd` when the directory decided it.

### Working inside a worktree

`charter.toml` is a tracked file, so if the repo you are working in is itself a control
plane, every worktree cut from it checks out a copy — which makes each worktree *look* like
its own control plane. It is not: a worktree is a view of a repo, not a repo.

So the plane's identity follows the **main working tree**. Standing anywhere inside a
worktree, `charter` resolves the plane to the repo the worktree belongs to, and personas,
the vault, workspaces and memory all stay attached to it. Without that they resolved into
the worktree itself — a directory `git worktree remove` deletes, taking any memory written
there with it — and the status line rendered `repos 0`, because a linked worktree's `.git`
is a file rather than a directory.

`$CHARTER_ROOT` is never redirected, so pointing it at a worktree is the escape hatch if
you genuinely want a plane of its own there.

#### What follows the plane, and what follows the tree

Identity is not the only question a command asks, and the two answers differ:

| | Follows the **plane** (the main tree) | Follows the **tree you are standing in** |
|---|---|---|
| what | who this plane is, and what only this machine knows | committed content on a branch |
| examples | the persona roster, the vault, the MCP approval record, memory, workspaces, `.charter/` | generated files — `charter persona sync-agents` reads `personas/` and writes `.claude/agents/` |
| why | a worktree is a view of a repo, so identity must not fork per worktree; a memory written into one is deleted with it | the artifact belongs to the commit, and the commit belongs to the branch |

So `charter persona sync-agents` run inside a worktree regenerates **that worktree's**
`.claude/agents/` from **that worktree's** `personas/`, and says so; the plane's own copy
changes when the branch merges. Reads that answer *for the plane* — `charter persona lint`,
and the news `check:` probes asking whether this plane has adopted something — keep
answering for the plane.

Before that split was drawn, `sync-agents` edited tracked files in the main clone from
inside a worktree: a write into a tree the caller does not own, with no conflict and no
message, while other workers held their own worktrees over the same clone.

### Nested planes

`charter` takes the **innermost** `charter.toml` above your working directory — the rule
git, cargo and npm use — with **one exception, and charter builds the shape it covers.** A
plane clones repos into its workspaces, and a cloned repo may itself carry a `charter.toml`,
since `charter init` is run inside existing repos. Taking the innermost marker there landed
you in a *different* control plane: different personas, a different vault, and memories
written somewhere you did not choose.

So when a plane sits inside another plane's `workspaces/`, resolution hops **outward** to
the enclosing one, and keeps hopping until nothing encloses it — the plane that actually
holds the vault wins. The hop is allowed only through an enclosing plane's own
`workspaces/`: a stray `charter.toml` in `~` does not swallow every plane beneath it.
`$CHARTER_ROOT` still wins outright, and is the escape hatch when you genuinely mean the
inner one.

Charter is not quiet about the hop. The status line names both planes and the
`$CHARTER_ROOT` export that pins you to the inner one, and **`charter save` refuses**
outright rather than committing a tree you are not standing in — that being the one command
whose whole job is to stage everything under the plane it resolved:

```
✗ Refusing to stage all of /…/plane — you are standing in /…/plane/workspaces/dev/charter,
  a control plane of its own under that plane's workspaces/. …
•   your own work:   git -C /…/workspaces/dev/charter add -A && git -C /…/workspaces/dev/charter commit
•   the plane's own: run `charter save` from /…/plane
•   you really do mean this plane: CHARTER_ROOT=/…/workspaces/dev/charter charter save
```

Only the unbounded stage refuses: memory, the dispatch tally, the workspace manifest and the
version pin name plane-state files, and those keep reaching the plane from inside a clone.

## A self-hosted example

A GitLab Enterprise instance behind your own domain, excluding the control plane itself
from the inventory:

```toml
schema = 1

[[forge]]
kind = "gitlab"
host = "gitlab.internal.acme.com"
group = "platform"
exclude = ["charter-control-plane"]

[memory]
share = "commit"

[workspace]
default = "default"
```

## Mixed-forge: tracking GitLab and GitHub together

A control plane isn't limited to one forge. Declare a `[[forge]]` block per forge and
`charter discover` queries each in turn, merging the results into one
`inventory/repos.json`. This is the non-obvious case — most control planes need only one
block — but it's fully supported:

```toml
schema = 1

# Internal platform repos, on a self-hosted GitLab.
[[forge]]
kind = "gitlab"
host = "gitlab.example.com"
group = "platform-team"
exclude = ["legacy-monolith"]

# Open-source repos, on github.com.
[[forge]]
kind = "github"
owner = "acme-oss"

[memory]
share = "commit"
```

Repos are exposed under their **bare name** (the final path segment) everywhere —
`charter clone api`, not `charter clone gitlab:platform-team/api` — so every command
keeps working unchanged. If two forges (or two blocks of the same kind — e.g. two GitHub
orgs) happen to expose a repo with the same bare name, `charter discover` refuses to
guess: it names both candidates and tells you to either qualify the name
(`github:api` vs `gitlab:api`) when cloning, or exclude one via that block's `exclude`.
Full detail, including exactly which collisions can and can't be qualified away:
`docs/forges.md`.

## Memory posture: `[memory].share`

Every persona and workspace can write **memory** — durable notes recorded with
`charter persona remember` / `charter workspace remember`. Where those notes end up is
controlled by one setting, `[memory].share`, with three modes:

| Mode | What happens |
| --- | --- |
| `local` | The memory file is written to disk and nothing else. It never enters git, never leaves the machine. |
| `commit` | The file is `git add`ed and committed **locally** (secret-scanned first) — it becomes part of your history, but is never pushed. |
| `push` | Committed, then pushed to `origin` in the background, so it reaches the shared repo moments after it's written. |

**The default is `local`**, and that default is deliberate: a stranger who just ran
`charter init` has not decided yet whether this control plane's notes should be shared
with a team, and the failure mode of guessing wrong runs only one direction — publishing
an agent's working notes to a remote nobody reviewed. Defaulting to `push` (or even
`commit`, which still commits to *your* history) would mean the very first memory an
agent records, before anyone has looked at what it's about to write, could already be on
its way to a shared remote. `local` costs nothing but a manual `charter persona
memory-sync` (or flipping `share` once a team actually wants to see this control plane's
notes) later. Every reactive commit path (`charter persona remember`, `charter workspace
remember`, the SessionStart dispatch tally) re-checks this value and falls back to
`local` on anything it doesn't recognise — a typo in this file fails *safe*, not loud.

## `[workspace].default`

The workspace name `charter` resolves to when nothing else has selected one — no
`--workspace` flag, no `$CHARTER_WORKSPACE`, no prior `charter workspace use` in this
session or terminal pane. Defaults to `"default"` (and `default` always exists — `charter
clone` creates it on first use). See `docs/personas.md`'s sibling in spirit, workspaces,
for the full precedence chain.

**A workspace name, not a path.** This file is committed, so the value is whoever last
edited it — and charter joins it onto `workspaces/`. It must therefore be a name `charter
workspace create` would mint (letters, digits, `.`, `_`, `-`; not starting with a dot).
Anything else degrades to `"default"`, the same way a `[frame]` key charter cannot make
sense of degrades to its shipped value. The committed `workspaces/.default` file, written
by `charter workspace default`, is held to the identical rule.

## `[charter].version` — pinning the CLI

**Opt-in.** Absent, charter does nothing: you track whatever you have installed. Present,
this control plane pins one charter version and every machine conforms to it — shared the
way a lockfile is.

```toml
[charter]
version = "0.7.1"
```

| Command | What it does |
| --- | --- |
| `charter version` | Shows installed / locked / latest, and the exact next command |
| `charter version sync` | Installs the locked version on this machine |
| `charter version bump [--to X] [--push]` | Moves the pin, after verifying the target installs |

**It is exact, not a floor — so it downgrades.** Pinning a team back to a known-good
release is precisely the case the pin exists for. `charter version sync --cli` performs it.

**The pin must be an exact `X.Y.Z`.** It becomes the right-hand side of a pip requirement,
`charter-cp==<pin>`, where a wildcard (`0.*`), a range (`>=0.47`) or a dist-name would also
be accepted — and would resolve to whatever is published, which is the one thing a lock
exists to prevent. Anything else is refused by name rather than installed.

**Auto-conformance runs once per session, and only upwards.** The `SessionStart` hook
installs the locked version when it is *newer* than what is running, and says so:

```
⬢ charter: auto-updated 0.7.1 → 0.8.0 to match this control plane's lock.
  The next `charter …` call uses it.
```

A pin **older** than what is running is reported and not installed:

```
⬢ charter: this control plane pins 0.7.1, which is OLDER than the 0.8.0 you are
  running. charter did not install it: a downgrade replaces the binary that enforces
  the credential guard with one that knows less, and session start has nobody to ask.
```

`charter.toml` is committed, so the pin is data a teammate can change — and an unattended
downgrade past a fix would re-open it on every teammate's next session. An upgrade can only
add guards; a downgrade can only remove them, so only one of the two directions happens by
itself. The pin-back stays one deliberate command, run by the person who read the message.

That wording is literal — a running process cannot replace itself mid-call, so *this*
invocation finishes on the old build and every later `charter …` in the session uses the
new one.

It never runs on the plane render and never mid-turn: the install replaces the binary
enforcing the credential guard, and a session boundary is the only safe moment for that.

**A failed auto-update never blocks you.** Offline, no `uv`, or a pin that does not exist
— charter warns, names the manual command, and the session proceeds on whatever is
installed. Being on a plane is not a defect. The drift stays visible in `charter doctor`
until it is resolved.

**Bumping is deliberate, because it is team-wide.** `charter version bump` installs and
verifies the target *before* writing the lock, so you cannot pin colleagues to a build you
have not run; `--push` commits and pushes, and everyone conforms on their next session.
charter only ever *shows* you that command — it never bumps on its own.

**With no `--to`, it pins what PyPI tells that same command.** If PyPI does not answer, it
refuses and asks for `--to`. It does not fall back to the cached reading `charter version`
shows, which can be days old and older than the charter you are running. Before #937 it
did fall back, and a failed request installed that older release over the running one and
pushed it to the team as the pin. If PyPI answers with a release older than the charter you
are running, it refuses too, before installing or writing anything. To pin a team back to an
older release, name it: `charter version bump --to X.Y.Z`.

On a plane that declares the [dev channel](install.md#4-the-dev-channel--gone-in-0622),
`charter version` never suggests this command, because a pin and the dev channel cannot
both be declared. It names `charter update` instead, and so does `charter version sync` on
a plane there that pins nothing. `charter version bump` itself refuses on such a plane,
`--to` or not. It refuses before asking PyPI, installing anything or writing the lock, and
names the two ways out: drop `[update] channel = "dev"`, or keep no `[charter] version`. Before
#947 it wrote the pin, and with `--push` every teammate's session start then refused the plane.

A plane there can still carry a pin: one written before #947, one typed by hand, one from an
older charter. That is one refused state, and every command that reads it prints the same
conflict and the same two ways out:

```
$ charter version sync --cli
✗ refusing to sync this control plane: a `[charter] version` pin and `[update] channel = "dev"` ask for two different charters. Nothing was installed.
•   to follow a pinned release, drop `[update] channel = "dev"` from the plane's `charter.toml`
•   to stay on `main`, keep no `[charter] version` in the plane's `charter.toml` and move this charter onto it:  charter update
```

`charter version sync` refuses with or without `--cli`, before it installs anything or asks
the harness to move this plane's artifact, and exits 1. `charter version` prints the conflict
instead of `conform this machine: charter version sync`, and exits 1 as it does for drift.
Session start installs nothing and says the same, **whether or not the pin equals the version
you are running**. A dev build prints the version of the release it was built from, so equal
numbers do not mean the plane is on the pinned release. `charter doctor`'s `version lock` row
warns with the same conflict and puts both ways out in its hint. The status line has room for
one row, so it prints a short form of the same words:

```
⚠ charter 0.61.0 pin + dev channel: two different charters · charter version
```

Before #1018, `version sync` installed the pinned release over a plane following `main`.
`charter version` and the status line both sent you to that command, and `doctor` named a
plugin update. A pin equal to the running number got nothing at session start, "in sync with
the lock" from `charter version` and `plugin in sync` from `doctor`.

## `[harness]` — profiles, and the default

Two Claude Code accounts, work in one config folder and personal in another, or a Codex
pinned to an older release: charter ran one program per harness, one way, and had no way to
be told otherwise. A shell alias does not help — charter runs the harness with no shell, so
the alias never resolves. A **harness profile** is the way: a kind, a command and an
environment, declared in a file that stays on your machine. The decisions behind the shape
of this, and the reason each one rests on, are
[ADR 0022](adr/0022-a-harness-profile-belongs-to-one-machine.md).

**Every chat now starts through charter's own launcher.** Charter reads the profiles,
refuses the broken ones by name, and keeps the file out of git; `charter claude-work`, bare
`charter`, the `+`, a workspace tab and a reopen all run the profile they name and record
it. A profile this file declares runs once you have seen its command and said so — see
*A new or changed command asks once*, below.

### Profiles live in `charter.local.toml`, never in `charter.toml`

```toml
# charter.local.toml — beside charter.toml, never committed
[harness]
default = "claude-work"                          # optional

[harness.claude-work]
kind = "claude"
command = ["claude"]
env = { CLAUDE_CONFIG_DIR = "~/.claude-work" }

[harness.codex-pinned]
kind = "codex"
command = ["npx", "-y", "@openai/codex@0.140.0"]
```

A profile's command runs on a click, with no harness permission prompt in between. In the
committed file a merged PR, or a chat, could change that command and have it run on every
machine that pulls it. So charter reads profiles only from `charter.local.toml`, and a
`[harness.<name>]` table in `charter.toml` is refused with a pointer to the local file.
`charter.toml`'s `[harness]` keeps `default`; any other key there is ignored, as it always
was. A `default` in the local file wins over the committed one.

**The local file carries `[harness]` and nothing else.** Any other section in it is refused
by name. An ignored file that could override `[[forge]]` — whose hosts steer the
one-credential guard — would change plane policy with no trace in git.

- `kind` — which harness program: `claude`, `opencode` or `codex`, the word you would type
  after `charter`.
- `command` — a list of arguments, never a shell string, because no shell runs it. A leading
  `~` in its first word is expanded, since no shell is there to do it.
- `env` — optional: variables set on the harness, each value's leading `~` expanded.
- The table's name is letters, digits, `_` and `-`, starting with a letter or digit. No dot:
  a dot in a name broke tmux targets once (#695).

**The file stays beside `charter.toml` when `$CHARTER_HOME` moves the state directory.**
What charter keeps about your profiles does move with it: the record of each command you
approved (`harness-profiles-launched.json`) and the wiring cache
(`cache/harness-wiring.json`). A plane whose state directory moved keeps its profiles and
asks about each declared one again on its first launch there.

**Every harness is also a built-in profile named after itself** — `claude` runs `claude`,
with no extra environment — so a plane that declares nothing sees no change. A declared
profile of the same name replaces it, which is how plain `claude` gets pinned. A built-in
cannot be hidden, but a replacement that is refused takes the name with it rather than
letting the built-in stand in: you said how `claude` runs, and running the default in its
place would run the command you replaced.

### What is refused, and the fix

A broken profile is refused alone, by name, and every other profile still loads.
`charter harness list` and `charter doctor` both say which one and why.

| Refused | Why | Fix |
|---|---|---|
| a `kind` charter cannot launch | nothing could start it | `claude`, `opencode` or `codex` |
| a `command` that is not a non-empty list of text | no shell runs it, so `"claude --resume x"` names one program | `["claude", "--resume", "x"]` |
| a `command` whose first word is charter itself | a profile names the harness a chat runs, and charter is not a harness | the harness's own command |
| a name holding a dot or any other character, or named `default` | a dot breaks tmux targets; `default` is the one key under `[harness]` that is not a profile | rename the table |
| a name `charter` already uses — `doctor`, `workspace`, `frame` | `charter doctor` would always be the command, never the profile | rename the table |
| an `env` that is not a table of text | a variable holds text | `env = { NAME = "value" }` |
| an `env` name starting with `CHARTER_` | charter sets those itself, and a profile's own setting would tell charter's hooks the wrong harness or plane | delete the variable |
| an `env` name containing `KEY`, `TOKEN`, `SECRET` or `PASSWORD` | a variable set on the harness reaches the model's shell, as the next section measures | log in inside the harness |
| a key other than `kind`, `command` and `env` | a typo such as `enviroment` would drop `CLAUDE_CONFIG_DIR` and launch the default account without a word | remove or respell it |
| a file that is not valid TOML | nothing in it can be read | fix the file; the built-ins still load |

### A new or changed command asks once

A profile's command runs on a click, and charter starts it with no shell and no harness
permission prompt in between. So the first time charter is asked to run one it shows you
what that is, and asks:

```
charter: profile 'claude-work' is new — it has not run on this machine before.
  command  claude
  env      CLAUDE_CONFIG_DIR=~/.claude-work
run this? [y/N]
```

Anything but `y` or `yes` starts nothing and exits 130. A yes is written down — the profile's
`kind`, `command` and `env`, exactly as the file spells them — and that profile then starts
without a word until one of those three changes. A change asks again, with a `was` line
showing what it ran last time:

```
charter: profile 'claude-work' has changed since it last ran.
  command  /opt/claude-2.1/bin/claude
  env      CLAUDE_CONFIG_DIR=~/.claude-work
  was      CLAUDE_CONFIG_DIR=~/.claude-work claude
run this? [y/N]
```

**Built-ins never ask.** `claude`, `codex` and `opencode` come out of charter's own
registry rather than out of a file, so there is nothing about them a question could catch —
and a question that never carries risk is one you learn to answer yes to without reading. A
profile the file declares under a built-in's name (`[harness.claude]`) is a declaration, and
asks with the rest.

**Why ask at all**, when nothing else charter does stops to. Once `charter.local.toml` is
ignored, an edit to it leaves no diff — no review, no `git status`, nothing on a branch for
anybody to notice. Nothing stops a chat editing your plane's config, and a chat is an agent
with a shell. And the command goes to tmux, so by the time a harness could ask about it,
that harness *is* the command. Codex trusts its hooks by hash for the same reason.

**Where it asks, and where it refuses instead.**

| Opening a chat | What happens |
|---|---|
| `charter claude-work` at a terminal | asks before tmux: a no starts nothing, with no session and no window allocated |
| `charter claude-work --no-frame` | asks on that same terminal, then becomes the harness |
| `charter claude-work --no-frame > log` | refuses — there is nowhere to put the question, and it names the command to run where you can answer |
| the `+`, a workspace tab, the palette's new chat | asks **in the chat's own pane**: the press itself has no terminal, and the pane has one on both ends. A no exits 130 and the window closes |
| `charter reopen`, restoring a recorded plane | refuses that chat by name and leaves it in the record — a reopen has nobody to ask. Run it once yourself, then `charter reopen` again |
| a chat handed off by another chat | refuses before anything is written: no chat directory, no window, no first message |

**Saying yes answers this question and nothing else.** After a yes, every check runs again
from the top before the harness starts — the file is still ignored, the command is still on
`PATH`, the record now matches — and the pane runs all of them once more immediately before
it becomes the harness. A yes is never a way past the check behind it.

**The limit, said plainly.** The record lives in `.charter/harness-profiles-launched.json`,
which is as writable by a chat as `charter.local.toml` is: both sit under paths no guard
covers, and charter does not police paths (that is host policy). So this catches a command
you did not change yourself **unless whatever changed it also forged the record**. It closes
the accident and the careless edit, and it is the difference between a command that ran
unseen and one that was read out loud first. It is not a boundary.

If charter cannot write that record, the launch is refused rather than started: running it
anyway would mean asking you the identical question at the next open, which is not something
you can fix by answering.

### No credentials in a profile

Anything set on the harness process reaches the shell the model runs — measured on Claude
Code, and on Codex, whose default `shell_environment_policy` passed a `*_TOKEN` variable
straight through. A vault reference would change nothing: the key would only rest somewhere
else before landing in the same shell. So a variable named like a credential is refused, and
the refusal names the harness's own login, kept in the config folder the profile already
moves:

- Claude Code: set `CLAUDE_CONFIG_DIR` and run `/login` inside Claude Code.
- Codex: set `CODEX_HOME` and run `codex login`.
- opencode: set `XDG_DATA_HOME` and run `opencode auth login`.

The pattern can refuse an innocent name — `KEYBOARD_LAYOUT` holds `KEY` — and a wrapper
script on `PATH` can still export a key. Charter declines to hold one; it cannot prevent one.

### Kept out of git, and checked

`charter init` writes `/charter.local.toml` into a new plane's `.gitignore`, and
`charter reinit` adds it to a plane made before this existed. The line is not trusted
blindly: `charter harness list` and `charter doctor` ask git, and while git tracks the file
or would commit it, every profile declared there is listed refused, with the reason, and one
line names the fix:

```
refused:
  claude-work: git would commit charter.local.toml, so the profiles in it are refused until it is ignored — charter reinit adds /charter.local.toml to .gitignore.
! to use the profiles in charter.local.toml: charter reinit
```

Each state has its own fix. A committable file needs the ignore line, which `charter reinit`
adds. A tracked file stays refused after the ignore line is added, because the next commit
still carries it — even after `git rm --cached`, until that removal is committed — so its fix
is `git rm --cached charter.local.toml`, commit that removal, then `charter reinit`. A plane
that is not a git repository has nothing to commit to, and passes. Any other answer git cannot
give — git missing, a timeout, an answer it cannot read — refuses too, because an unknown is
not a pass; the fix names the command to run by hand, `git status --ignored --
charter.local.toml`, beside what git said.

The check is one `git --no-optional-locks status`, which takes no `index.lock` from a commit
running beside it. It runs when a person asks — `charter harness list`, `charter doctor` —
and not when charter merely reads its config, and not on a hook path: the SessionStart hook
runs `charter doctor --preflight`, which skips it. `charter doctor`'s `harness profiles` row
warns for each refusal above, with each state's own fix, and for a `default` that names no
profile this machine has.

### The profile is wired

Charter's guard lives in the harness's own config folder, and a profile names another one.
**A profile whose folder does not carry charter's wiring is wired by the launch where
charter can do that alone, and refuses to start where it cannot.** Asking runs the
profile's own command, so it is asked only once you have approved that command — a new
`claude-alt` shows `run this? [y/N]` first. A yes is followed by one line and then the chat:

```
✓ charter: wired 'claude-alt' — installed charter@charter into /Users/you/.claude-alt
```

That is the same install `charter harness install claude-alt` runs, into the folder the
profile names and no other, and charter asks the harness again before it starts anything:
only a folder that now answers *wired* gets a chat. An opencode profile gets its shim the
same way. **Codex does not** — its hooks are trusted only inside a Codex session — so
charter writes its half of the wiring and the launch stops with Codex's own steps:

```
charter: profile 'codex-alt' is not wired — /Users/you/.codex-alt/config.toml: charter@charter
is not an enabled plugin; no copy of charter@charter under … places charter's guard hook, so
there is no guard to trust, so a chat on it would run without charter's guard. Nothing was
started. Wire it: CODEX_HOME=/Users/you/.codex-alt codex plugin marketplace add …
```

**No flag launches one unguarded**, and the rule covers the built-ins: `charter codex` on a
plane where nobody wired Codex refuses this way, and `charter opencode` where `init` never
wrote the shim writes it and starts. A chat that looks guarded and is not is the same
failure whichever profile started it.

A probe that cannot answer — it timed out, exited non-zero, or said something charter could
not read — refuses, prints the probe to run by hand, and installs nothing over the doubt. An
unknown is not a pass. An install that fails refuses too, naming what the install said, and
so does a folder whose fix is not the install (a plugin installed and disabled).

Every launch asks freshly, before tmux and again in the pane — a `+`, a tab, `charter
reopen` and a handoff ask before they open anything, and the pane asks again. The install
happens at the first of those that finds the folder unwired, and the second finds it wired.
A launch never reads the remembered answer under `.charter/`: that file is as writable by a
chat as `charter.local.toml` is, and it exists to draw rows, not to start chats.

What "wired" means per kind, what the launch, `init`, `reinit`, `charter harness install`
and the selector each do about it, and the measured cost of each probe and of the install
are in [harnesses.md](harnesses.md#per-profile--wired-automatically-or-it-refuses).

### `default` — bare `charter`

**Opt-in, and it launches nothing.** Bare `charter` opens a chat at the **profile
selector** and starts a harness only once you pick a row; this key chooses which row the
cursor starts on, and marks it. Absent, the selector opens on the first row that can run.

```toml
[harness]
default = "claude"
```

`charter` is `charter frame --select`. Not "like" it — charter rewrites the command into
that one and runs it, so the workspace picker, `--no-frame`, `--probe`, `--workspace` and
everything else the launcher does are the same behaviours, not a second set of them. Every
subcommand keeps working untouched, `charter claude` included.

The value is the name of a profile: one of the words you would type after `charter` —
`claude`, `opencode`, `codex`, the built-in profiles `charter harness list` shows, read out
of charter's own registry rather than a list in this page — or the name of a profile
`charter.local.toml` declares. A `default` in the local file wins over the committed one,
which is how a machine chooses its own without touching what everybody else pulls.

**A declared profile is a legal value here**: it is the row the selector starts on, and
Enter on it starts that profile, question and all — the first open shows its command and asks
(*A new or changed command asks once*).

**Charter does not pick one for you — it asks.** No default and the selector opens on the
first row that can run. Charter still does not guess *which* harness you meant: not
"whatever is installed" (a machine with two of them has no answer, and the answer would
change the day a colleague installed a third) and not "the one you ran last" (a
machine-local memory deciding what a committed command does). What changed is that the
question is now asked on screen instead of answered by a key.

**A name this machine does not have marks no row, and `doctor` says so.**

```
$ charter doctor
! charter.toml: [harness] default = "clyde" names no profile this machine has — one of:
  claude, codex, opencode.
```

The launch itself no longer refuses over it: the selector lists what this machine actually
has, so a typo shows up as a list with nothing marked rather than as a command that will
not run. `doctor` is where it is named, because that is the reader that can say it without
taking a launch away.

**`charter | head` still prints usage.** Bare `charter` opens a frame only when stdout is
a terminal. Piped or redirected, it prints the usage message and exits 2, which is what it
did before this key existed — so a script that runs `charter 2>&1 | head` to find out
whether charter is installed gets an answer instead of an agent session, and a pipe is no
place to draw a selector either. `charter claude` into a pipe is unaffected: it runs the
harness bare, as it always did.

## `[update].channel` — the dev channel

**Opt-in.** Absent, this plane tracks published releases and nothing below applies.

```toml
[update]
channel = "dev"
```

On `dev`, three things change and nothing else does:

| | `stable` | `dev` |
| --- | --- | --- |
| "newer" means | a higher version is on PyPI | `main`'s head commit is not the one installed |
| `charter update` installs | `charter-cp==<version>` | `git+https://github.com/diazoxide/charter@main` |
| the brand chip (frame top bar, `charter statusline`) | `⬢ charter 0.51.0` | `⬢ charter 0.51.0 dev` |

`charter update` on `dev` also force-refreshes the Claude Code plugin, because a
version-keyed `claude plugin update` cannot see a change that does not move the version —
see [install.md](install.md#the-plugin-needs-forcing-and-only-on-this-channel).

**The value is a closed set of two, not a string.** `charter.toml` is committed: it arrives
from a teammate's machine, and this key decides how charter installs itself. Anything that
is not exactly `"stable"` or `"dev"` is discarded and the plane stays on `stable` — nothing
you can write here is passed through to a URL, a command line, or an argv element. The
repository charter installs from is a constant in charter's own source, and no `charter.toml`
can name a different one.

**Never both this and `[charter] version`.** A pin names a published release a whole team
conforms to; a commit of `main` has no such number, and a dev build carries the *same*
version number as the release it was built from — so a pin would silently reinstall the
published wheel over it at every session start. Declare both and charter installs neither,
and says which two keys disagree.

**Nothing installs itself.** The render nudges when `main` moves; you run `charter
update`.

## Schema drift and healing

`schema` is the plane's **format version**, and the one thing it buys is the ability to
refuse. It is the same contract git states for a program reading a repository it did not
write — *"an implementation which does not understand a particular version advertised by
an on-disk repository MUST NOT operate on that repository"* — and no more than that. It is
not a schema and not a spec: the shape of the files charter writes is charter's own
business and is free to change. The commands are the interface.

So a control plane written by a *newer* charter than the one you have installed is not
operated on. Every command declines with the "upgrade charter" message and exits 1, except
four, each of which is a question about charter rather than a read of the plane's contents:

| still runs | why |
|---|---|
| `charter doctor` | where the refusal is reported — the `schema` row names both versions |
| `charter --version`, `charter version`, `charter _version-check` | which charter is this |
| `charter update` | the only remedy; nothing but a newer charter can understand a newer plane |

`charter init` and `charter reinit` are deliberately **not** exempt: writing into a layout
charter has been told it does not understand is the most damaging guess available to it.
A `schema` charter cannot compare against at all — `schema = "2"`, `1.5`, `true` — is
refused on the same terms as one from the future.

**Omitting `schema` means 1**, not "whatever charter you are running". A plane created
before planes declared a version *is* a version-1 plane, so it stays readable by every
charter forever; reading it as "current" would be the same guess, arrived at through the
number that exists to prevent it.

Going the other way — an *older* control plane opened by a newer charter — is always fine:
newer charter versions can add baseline directories (`personas/`, `inventory/`,
`workspaces/`) a control plane predates, and `charter reinit` creates whatever's missing,
additively, never touching what's already there.

**`schema` and a workspace's own structure version are nested, and only `schema` refuses.**
`charter workspace reinit` repairs a workspace whose interior an older charter laid out;
that is a *repair* number, and a workspace charter can still read is exactly what makes the
repair additive. `schema` is the *refusal* number, and nothing heals it but a newer charter.
The two are never compared against each other.

**`.charter/` carries no such promise, on purpose.** Everything under `.charter/frame/` is
charter's own scratch — per frame, per machine, gitignored, reaped when the frame dies, and
written and read by one charter inside one process tree. It has no format version and never
will: a version is only worth stamping where the writer and the reader can be different
charters. Read it through `charter frame`; the files themselves may change shape in any
release.

## The plane, rendered

`charter statusline` — the whole plane read off disk in one block. **`charter init` does
not wire it into Claude Code's footer** and has not since 0.57.0 (#895): you reach this
render through the frame's panels (`charter claude`), through `charter statusline --watch`
in any spare terminal, through opencode's `/charter`, or by running `charter statusline`
yourself. A `statusLine` key in `.claude/settings.json` still works exactly as it always
did if you write one; charter neither adds it nor removes it.

It is grouped by **scope** — each zone answers exactly one question, and a count always
sits next to the thing it counts:

```
⬢ umbrella-improvements · todo 3 · ws 9                           ← WHERE am I
◫ repos 2/38                    │ ◈ personas 13 · vaults 6 · shared ✎130
├─ easysender-ui-workspace  main  ✗ failed │ ◆ steward ✎2         ← WHAT I'm on × WHO I am
└─ iam-service ⑂2           main  ✓ passed │ ○ devops ✎192 ⚡ 4m
ctx 22% · cache 90% · ⚡ 1 · ⛊1 denied · ✎1 recorded  ⬢ charter 0.10.0   ← THIS session
```

- **Top — identity and navigation.** The active workspace, how many todos it still has
  open (`charter ws todo`), and how many other workspaces exist. Nothing else: the repo
  count describes the left column, the vault count describes the right one, and the
  gauges describe the session, so each lives with what it describes. `todo N` belongs
  here for the same reason — open todos are a property of *this* workspace. It is absent
  when the count is zero, like everything else that would otherwise render every turn.
- **Columns — the Role × Task axes.** Left is the *task* (repos cloned into this
  workspace, their branch, CI and MRs); right is the *role* (the persona roster, each
  chip carrying its memory counts, a `⚡` while it has sub-agents running — with a `?`
  once one has outlived every reasonable expectation — and a vault mark only when its
  vault cannot be used). Personas are global, repos are workspace-scoped — two
  independent axes, two columns.
- **Bottom — this session.** Context and prompt-cache health (`ctx NN%`, `cache NN%`),
  plus counters for what has happened: in-flight sub-agents, guard denials, memories
  recorded, dispatches. Absent entirely when there is nothing to report, so a denial
  appearing there is *news*. The brand and version sit at its right edge.

  `⚡` is the one glyph left on that strip and it means one thing — a dispatch is
  running — the same thing it means on a persona chip. The gauges carry words for
  exactly that reason: the bolt belongs to the fact that renders in two places.
- **Alerts** (a pinned-version mismatch, workspaces needing `reinit`) get their own
  full-width lines above the strip — actionable problems carrying the command that
  fixes them, not telemetry.

Two columns need 131 columns of width; below that everything stacks in the same order.
Nothing here reads the network or shells out to git — it renders every turn.
