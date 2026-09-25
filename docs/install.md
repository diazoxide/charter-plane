# Install

> **charter-cp is no longer maintained — charter is now a desktop app:
> https://github.com/diazoxide/charter/releases.** 0.62.2 is this package's last release:
> `charter update` installs nothing, and the dev channel below has nothing to follow.

**One command installs charter.**

```bash
uv tool install charter-cp
```

That is the CLI, and the CLI is the front door: it is what sits on your `PATH`, what every
hook charter declares shells out to, and what writes `.claude/settings.json`. Claude Code's
charter plugin is the *second* artifact, and you do not install it by hand — `charter init`
installs it for the plane it creates, and `charter doctor --fix` installs it for a plane
that already exists. The inverse shape, a plugin that bootstraps a CLI, would have to guess
at a Python environment it does not own.

Nothing installs itself. `init` and `doctor --fix` are the only two commands that install
anything, and both are commands you typed; `charter workspace list` will never install
software as a side effect of answering a question.

## Paste this into Claude Code

Installed and checked, without looking anything up:

```
Install charter (https://github.com/diazoxide/charter-plane) for me:

1. Run `uv tool install charter-cp`. charter needs Python 3.11+, which uv can
   fetch for me; fall back to pipx or pip only if uv is missing.
2. Run `charter doctor` and show me the output. Its `plugin install` row will read
   "no control plane here — nothing to install it for" (or, with no `claude` CLI on
   PATH, "no `claude` on PATH — no Claude Code plugin here"). Both are expected: the
   plugin is installed per control plane, and there is no plane yet.
3. Do NOT run `charter init` — tell me what it would create and let me pick the
   directory first. `charter init` is what installs the plugin, for the plane it
   creates.

Then tell me to restart this session once the plane exists, so the plugin's hooks load.
```

Step 3 is not caution for its own sake: `charter init` makes the directory it runs in a
control plane, writing `charter.toml` and scaffolding `personas/`, `inventory/` and
`workspaces/` (see [control-plane.md](control-plane.md)). Run from an unrelated project by
accident, it would quietly convert it — so the prompt stops before the step that writes
into your working directory, and hands the choice back to you.

The manual steps below are the same install, written out. Reach for them when you want to
know exactly what is happening, or when the prompt does something you did not expect.

## 1. The CLI

```bash
uv tool install charter-cp     # installs the `charter` command
```

Lead with [`uv`](https://docs.astral.sh/uv/) for a concrete reason, not a preference:
charter requires **Python ≥ 3.11** (it leans on stdlib `tomllib`, which is 3.11+ only), and
stock macOS ships 3.9. `uv tool install` can fetch and manage a suitable Python for you;
`pipx` and `pip` both require one to already be on your `PATH`.

Alternatives, once you have a 3.11+ Python:

```bash
pipx install charter-cp        # installs the `charter` command
pip install charter-cp
```

Or run it without installing anything:

```bash
uvx --from charter-cp charter <cmd>
```

> **The package is `charter-cp`; the command is `charter`.** PyPI would not allow
> `charter` as a project name, so the distribution carries a suffix — but everything you
> type, and everything in the docs, is `charter`.

### What charter reaches on its own, and how to stop it

charter starts refreshes in the background, so that nothing you look at waits on the
network:

- **`charter _version-check`**: no longer started, since 0.62.2. It was one GET of PyPI's
  metadata for `charter-cp` and, on the [dev channel](#4-the-dev-channel--gone-in-0622),
  one of `main`'s head from GitHub. charter-cp has no newer release to find, so nothing
  starts it. `charter version bump` still asks PyPI when you run it.
- **`charter gl-refresh`**: `gh` or `glab` over every clone in the workspace, for the open
  change and CI columns, cached in `.charter/cache/glstate.json`.

The status line, the frame's gather and SessionStart start them when their cache is stale.
On an offline machine, in a CI job, or anywhere you would rather charter did not reach PyPI
or your forge unasked, switch both off:

```bash
export CHARTER_NO_BACKGROUND_CHECKS=1
```

**It is on whenever it holds more than whitespace, `0` and `false` included.** You are asking
charter not to reach the network, and a word it did not recognise must not read as
permission. Unset the variable, or set it empty, to turn the refreshes back on.

With it on, neither refresh starts and neither touches `.charter/cache/`. Commands you run
yourself are not background refreshes, and they still reach the network: `charter update`,
`charter version bump`, `charter gl-refresh`. What reads the caches shows only what is
already there. The version chip has no `↑`, a clone that was never refreshed shows no change
or CI state, and `charter version` says the newer-charter question was not checked instead
of calling you up to date:

```
• not checked: $CHARTER_NO_BACKGROUND_CHECKS is set, so charter does not ask in the background. `charter update` asks when you run it.
```

Set it where every charter process inherits it: your shell profile, or the job's
environment. A frame's panels are started by a tmux server with the environment that server
started with, so a server already running when you exported it does not have it. A profile's
`env` cannot carry it, because charter refuses `CHARTER_*` names there (see
[control-plane.md](control-plane.md#what-is-refused-and-the-fix)).

## 2. The Claude Code plugin — charter installs it

This repo also ships as a Claude Code plugin — `.claude-plugin/plugin.json` +
`hooks/hooks.json` — and you do not type the commands for it:

```bash
charter init          # creates a control plane, and installs the plugin for it
charter doctor --fix  # installs it into a plane that already exists
```

**Per plane, at `project` scope, and that is a feature rather than an accident.** Claude
Code keeps a cache holding every version of a plugin at once, so a plane's pinned version
is the plugin's and not the binary's: two planes on one laptop can sit on different
charters without fighting. A machine-wide install would collapse that to one version, and
would put charter's hooks into repositories you never pointed charter at.

`charter doctor` reports the plugin's absence on its own `plugin install` row and names
`charter doctor --fix` as the remedy. It **warns** rather than failing: a plane that
declares `charter hook pretooluse` in its own `.claude/settings.json` is guarded with no
plugin at all, and a CLI-only install is supported — `charter clone`, `charter persona
show` and the rest work with no plugin anywhere.

The same row says so when the plugin is installed and **disabled**, because an installed
plugin loads nothing until it is enabled. charter will not enable it for you — `claude
plugin enable charter@charter --scope project` is yours to run, since turning a plugin off
is a choice and charter does not revert a deliberate edit.

**`harness profiles` and `profile <name>`.** The first row reads this machine's
`charter.local.toml` and says how many profiles charter found, or why one was refused, or
that git would commit the file. After it comes one row per profile charter would offer —
every profile you declared, plus a built-in for each harness whose program is installed —
answering whether charter's guard actually runs in the config folder that profile names.
A yellow row names `charter harness install <name>`, which is the same command a refused
launch prints. They are probed concurrently, each with its own timeout, and a probe that
raises costs that row and nothing else. A profile you have not approved yet is not probed —
its row says so and names `charter <name>`, which shows the command and asks — and neither
is any profile while git would commit `charter.local.toml`. A row too long for the table
says how much it left out (`… +12 not shown`) rather than stopping mid-word.

**The SessionStart hook runs `charter doctor --preflight`**, which is the same preflight
with two things left out: it probes no profile and makes no git call for one. A probe is a
subprocess that writes into somebody's account folder, and the hook's whole budget is 20
seconds. So the `profile <name>` rows appear only when you run `charter doctor` yourself.
(Codex trusts hooks by their hash, so Codex users approve that hook once more after this
release — its command changed.)

**Which Claude Code config folder these rows answer for.** `$CLAUDE_CONFIG_DIR` points Claude
Code at another folder — the usual way to run a second account — and Claude Code then keeps
that folder's own plugins, settings and `.claude.json`. Run `charter doctor` from the shell you
start Claude Code from, so it sees the same variable.

- **Follow `$CLAUDE_CONFIG_DIR`:** `plugin install` and `plugin files` (they ask `claude
  plugin list`), `plane-root guard`, `guard seen`, `session root` and `mcp`. With the variable
  unset they read `~/.claude` and `~/.claude.json`.
- **Do not follow it:** `personas`, which still looks for a persona's skills under
  `~/.claude/plugins` and `~/.claude/skills`. And `charter reinit`, deliberately: it writes the
  plane's committed `.claude/settings.json`, which every folder's sessions read, so whether it
  writes the guard hook is decided by `~/.claude` whatever your shell says.
- **A guard sighting counts only for the folder it ran under.** `plane-root guard` and `guard
  seen` stay yellow for a sighting from another folder, one recorded before charter kept the
  folder, or one that names no harness charter knows (`$CHARTER_HARNESS` unset or misspelled,
  and no plugin), and each says which case it is. A Bash command in a Claude Code session on
  the folder you use clears the first two. For the third, set `$CHARTER_HARNESS` to
  `claude-code`, `codex` or `opencode` — `charter reinit` writes it into
  `.claude/settings.json` — and a session started after that names its harness.
- **An empty or relative `$CLAUDE_CONFIG_DIR` is reported on both guard rows**, whatever the
  sightings. Claude Code resolves it against its own working directory, which charter cannot
  see, so nothing can be compared with it. Set it to an absolute path; running a command
  changes nothing there.
- **Three narrower Claude Code settings are not followed**, so with any of them set these rows
  read the wrong file:
  - `$CLAUDE_CODE_PLUGIN_CACHE_DIR` moves the installed-plugin list out of the config folder.
    `plane-root guard` and `guard seen` still read `<config folder>/plugins/installed_plugins.json`.
  - `$CLAUDE_CODE_USE_COWORK_PLUGINS` renames `plugins/` to `cowork_plugins/` and
    `settings.json` to `cowork_settings.json`. The guard rows still read the ordinary names.
  - `$CLAUDE_CODE_CUSTOM_OAUTH_URL` renames `.claude.json` to `.claude-custom-oauth.json`.
    `mcp` still reads `.claude.json`.

By hand, if you would rather, or if `charter doctor --fix` could not (an old `claude`, no
network):

```bash
claude plugin marketplace add diazoxide/charter-plane
claude plugin install charter@charter --scope project
```

Or inside a session: `/plugin marketplace add diazoxide/charter-plane`, then `/plugin install
charter@charter`. Consult Claude Code's own `claude plugin --help` if that flow has moved
on since this was written.

The plugin loads on the **next** session, so restart after installing. Upgrading the CLI
does not upgrade the plugin — they are two artifacts with two version numbers, pinned to
each other, so `claude plugin update charter@charter` is its own step, and skew between
them is normal rather than exceptional. `charter doctor` **refuses** on skew, with a row
naming the exact command; charter's hooks only **warn**, at session start and nowhere else.
That asymmetry is deliberate: a hook that hard-failed on a version mismatch would brick
every tool call in the session, turning a cosmetic difference into an outage. A plugin
*newer* than the CLI says so loudly at session start; an older one is quietly supported.

The plugin supplies the pieces that only make sense running *inside* a Claude Code
session: injecting the active persona's memory at session start, the `PreToolUse` guard
that enforces the [one-credential rule](git-policy.md), the record-memory nudges, and the
Stop-hook auto-save. **The plugin ships no Python of its own** — every hook it declares
shells out to the `charter` CLI you installed in step 1, which is why the CLI is the
artifact you install and the plugin is the one it installs for you.

## 3. opencode and Codex

Each harness gets **one installed artifact**, the same way Claude Code does. Nothing is
written into the repos you work in.

**Only Claude Code's artifact is one charter installs for you, and the difference is
scope.** The Claude Code plugin is installed per project, so `charter init` installing it
touches exactly the plane you asked charter to create. Codex's wiring lives only in
`~/.codex/config.toml` — a machine-global file, in force for every repository on the
machine — so charter writes it only when you run `charter harness install codex`, where
running the command *is* the consent. `charter doctor` reports the gap and stops there;
one documented one-time edit is a smaller cost than charter silently rewriting a
machine-wide config, and unlike the plugin that file is not something a charter upgrade
has to keep in lockstep.

**opencode — `charter init` does it.** The plugin goes to `~/.config/opencode/plugin/`
(`$XDG_CONFIG_HOME` is honoured), which opencode reads for every project, along with a
`/charter` command and the session context it reads at startup. `charter doctor`'s
`harness` row reports it, and `charter reinit` reinstalls if you ever delete it.

Earlier charters wrote a plugin into every clone and worktree instead, because opencode
does not search parent directories for *project* plugins. It does read the config dir, so
that was a lot of files in other people's repositories answering a question that did not
need asking. If you have `.opencode/` directories lying around in clones, they are inert
and safe to delete.

**Codex — the plugin, plus one line.** Codex installs the same plugin charter ships for
Claude Code, through `codex plugin`. That covers every hook. The one thing a plugin cannot
do is tell a shell which harness it is, so:

```bash
charter harness install codex
```

writes exactly that into `~/.codex/config.toml`:

```toml
[shell_environment_policy]
set = { CHARTER_HARNESS = "codex" }
```

If it finds hooks declared in that file it **refuses and says so**. An earlier charter
wrote them there before the plugin route was known, and both sets are trusted and both
run — charter fires twice on every SessionStart, UserPromptSubmit and Bash call. Nothing
is wrong; everything is doubled, which is harder to notice. Delete charter's block from
`config.toml` and keep the plugin.

## 4. The dev channel — gone in 0.62.2

Up to 0.62.1 a plane could declare `[update] channel = "dev"`, and `charter update` then
installed `git+https://github.com/diazoxide/charter@main`. That repository was renamed
`diazoxide/charter-plane`, its `main` no longer holds this package, and `diazoxide/charter`
is now the desktop app, so 0.62.2 removed the
install path and switched the update check off on both channels. The key is still read and
still accepted; it no longer changes what `charter update` does, which is print that
charter-cp is no longer maintained and install nothing.

## First control plane

```bash
mkdir my-control-plane && cd my-control-plane
charter init --forge github --owner my-org
charter doctor
charter discover
charter clone some-repo
charter claude            # or charter opencode, or charter codex
```

`--forge` is `gitlab` (the default) or `github`; `--owner` is the GitLab group or GitHub
org/user whose repos this control plane tracks. Run inside an existing git repo, `init`
also *offers* to clone that repo into your first workspace — accept with `charter init
--clone-this-repo`, because work happens in a workspace, never in the plane root.

`discover` and `clone` go through the forge's own CLI — `gh` for GitHub, `glab` for
GitLab — which nothing above installs and which must be authenticated. `charter doctor`
checks the CLI and its login for each forge `charter.toml` declares, and GitLab's when the
file declares none.

`charter claude` needs two more things nothing above installs. `claude` itself has to be on
your `PATH`: without it no frame is drawn, and charter says the binary is not installed and
exits 127. And the frame needs tmux, because it is a tmux screen; of tmux, only its absence
stops a launch — below 3.2 the frame still starts. `charter opencode` and `charter codex`
need their own binaries the same way. `charter claude --probe` says whether a frame can run
here without starting one; [frame.md](frame.md) is the rest. If you ran `charter init` from
inside a Claude Code session, restart that session first — the plugin loads at the next one.

Bare `charter` opens a chat at the profile selector and starts nothing until you pick a
row. `init` writes no `[harness] default`; it is optional, and it chooses which row the
cursor starts on — one key in `charter.toml`, and `claude` is the built-in profile of
Claude Code ([control-plane.md](control-plane.md#default--bare-charter)):

```toml
[harness]
default = "claude"
```
