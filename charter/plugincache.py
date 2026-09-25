"""The installed Claude Code plugin versus the marketplace clone it came from.

``claude plugin update charter@charter`` compares **version strings**, and charter's plugin
version moves exactly once per release. The marketplace, meanwhile, is a git clone of
``main`` that Claude Code re-fetches on its own — so between releases the clone advances
and the installed copy does not, both keep saying ``0.51.0``, and the update command
correctly reports there is nothing to do. Measured on one machine at the time this was
written: 45 files differing, ``skills/secrets/SKILL.md`` and ``skills/browser/SKILL.md``
among them.

**The staleness that bites is the skills.** ``hooks/hooks.json`` invokes ``charter hook …``
— the *command*, resolved from ``PATH``, i.e. the ``uv tool`` install — so hook behaviour
follows the CLI and not the plugin's bundled copy of ``charter/*.py``. Skills are different:
they are text the model loads, and a stale one is wrong instructions delivered confidently.

Three callers, one mechanism:

* `doctor.check_plugin_freshness` compares by CONTENT, which is the question a version
  string cannot answer.
* `commands_update` force-refreshes on the dev channel, where a version-keyed update can
  never see the change.
* `commands.cmd_init` and `charter doctor --fix` INSTALL it (#881), so that installing
  charter installs charter and the operator types one command rather than three. Those two
  entry points and no other: :func:`install` says at length why nothing may reach it as a
  side effect of an unrelated command.

**Everything here talks to `claude plugin … --json`, never to Claude Code's files.**
``~/.claude/plugins/installed_plugins.json``, ``known_marketplaces.json`` and the cache
layout are internals charter does not own; `update.plugin_version_here` already carries
the lesson (``bin/edm`` bet on an internal path and broke silently, #197). ``claude plugin
list --json`` and ``claude plugin marketplace list --json`` are documented CLI surfaces
that answer the same questions, and they cost ~0.2s each.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

from . import util

#: How long a `claude plugin … --json` READ may take, in seconds.
#:
#: **Equal to `doctor.CHECK_TIMEOUT`, and a test pins the two together.** These reads run
#: inside a `doctor` check, and `doctor` runs as a SessionStart preflight whose whole hook
#: budget is 20s — so a per-call budget of 15s, made twice, was 30s against 20s. The first
#: version of this constant cited that 20s budget in its own comment while exceeding it,
#: which is exactly the mistake `CHECK_TIMEOUT` exists to make impossible. Measured cost is
#: 0.22s and 0.27s; the number only matters in the pathological case, which is the only
#: case it is for.
LIST_TIMEOUT = 5.0

#: The mutating half is a different budget because it is a different job: `marketplace
#: update` fetches from GitHub and `install` copies a repository-sized tree. It runs from
#: `charter update` — a command a person typed and is waiting on — never from a check.
REFRESH_TIMEOUT = 120

#: "I could not look", as distinct from "there is nothing installed".
#:
#: Not the same answer, and `doctor` renders them differently: an absent plugin is a green
#: row (CLI-only is a supported install), while a `claude plugin list` that could not be
#: read is a WARN carrying `_NOT_CHECKED_HINT`. Collapsing them into one ``None`` put a
#: green *"the charter plugin is not installed here"* in front of anyone whose `claude` is
#: too old to understand `--json` — precisely the population most likely to be running a
#: stale plugin, and precisely the defect the #171 audit removed everywhere else ("a check
#: that silently does nothing is worse than no check").
#:
#: A sentinel compared with ``is``, rather than a third return type: the same shape
#: `hooks.dispatched_handlers` uses to keep the same distinction.
UNKNOWN = object()

#: The directories a Claude Code plugin actually LOADS, and therefore the only ones whose
#: drift means anything.
#:
#: charter's marketplace entry is ``"source": "./"`` — the whole repository is copied into
#: the cache, ``tests/`` and ``docs/`` and all — so hashing the copy wholesale would report
#: a test-file edit as a stale plugin. That is not a stricter check, it is a noisier one:
#: `doctor`'s own comments keep returning to the point that a row which warns about
#: something benign trains people to scroll past the row, which costs the case that
#: matters. These five are the surface Claude Code reads.
#:
#: ``commands`` and ``agents`` are listed although charter ships neither today. A plugin
#: directory added later is loaded by the host whether or not this tuple was updated, and
#: the cost of naming it now is nothing (a missing entry is skipped); the cost of not
#: naming it is a category of drift this module reports as clean.
PLUGIN_SURFACE = (".claude-plugin", "hooks", "skills", "commands", "agents")

#: What a plugin id may look like before it is allowed near an argv.
#:
#: These values are read out of `claude plugin list --json` — a machine's own output, not
#: a committed file, so this is a narrower hazard than `charter.toml`'s. It is still input.
#: `util.run` takes a list and never a shell string, so the shell is not the exposure; the
#: exposure is an element that begins with ``-`` and is read by `claude` as a FLAG rather
#: than as the plugin to uninstall. This alphabet has no leading dash and no whitespace.
_PLUGIN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}@[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

#: The scopes `claude plugin install|uninstall --scope` accepts. A closed set for the same
#: reason `instance.UPDATE_CHANNELS` is one: the value reaches an argv, and matching it
#: against constants charter wrote means nothing read from anywhere is ever passed through.
_SCOPES = ("user", "project", "local")

#: The marketplace-side half of the same rule.
_MARKETPLACE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

#: The one plugin id charter recognises as its own — see :func:`installed_charter_plugin`
#: for why this is exact rather than `charter@<any marketplace>`. Both halves are the
#: ``name`` in charter's own ``.claude-plugin/plugin.json`` and ``marketplace.json``, and
#: `tests/test_plugin.py` already pins those two to each other.
PLUGIN_ID = "charter@charter"

#: What ``claude plugin marketplace add`` is given — the GitHub ``<owner>/<repo>`` charter
#: is published from, which is how a marketplace comes to be called ``charter`` at all.
#:
#: ``diazoxide/charter-plane`` since 0.62.2, the name the repository was renamed to; the old
#: name ``diazoxide/charter`` is now the desktop app's repository. The plane repository's
#: ``main`` no longer carries ``.claude-plugin/``, so ``marketplace add`` fails there and
#: `install` reports the failure with its manual fallback. That is the chosen behaviour: a
#: failed add names what went wrong, where the old name would have registered the app's
#: repository as charter's marketplace.
#:
#: A literal rather than something read at runtime, because the wheel does not ship
#: `.claude-plugin/`: `[tool.hatch.build.targets.wheel] packages = ["charter"]`, so a CLI
#: installed from PyPI has no manifest to read this out of. `tests/test_plugin_install.py`
#: pins it to `pyproject.toml`'s own `Repository` URL instead, so the day charter moves
#: house the suite fails rather than every stranger's first install.
MARKETPLACE_SOURCE = "diazoxide/charter-plane"

#: The scope charter installs its own plugin at, and NOT ``user``.
#:
#: The README states the consequence and it is the whole reason a plane pins the plugin's
#: version rather than the binary's: *"two planes on one laptop can sit on different
#: charters without fighting"*. A machine-global install collapses that — one version for
#: every plane on the machine — and it also puts charter's hooks into repositories nobody
#: pointed charter at, which is #857's category exactly.
INSTALL_SCOPE = "project"


#: The program every read here runs, when the caller names none. A profile names its own
#: (`["/opt/claude-wrap"]`, a pinned binary), and a wrapper script's answer is the one that
#: matters for a chat that will be started through it.
DEFAULT_COMMAND = ("claude",)


def available(command: tuple[str, ...] | list[str] = DEFAULT_COMMAND,
              path: str | None = None) -> bool:
    """True when *command*'s program is on *path* — this process's `PATH` when ``None``.
    False is an ordinary answer, not a fault — charter supports opencode and Codex, and a
    plane on either has no Claude Code plugin to be stale.

    *path* is the `PATH` the command will actually be run under. A profile may set its own
    in `env`, and the launcher looks its command up on that one (`launcher.refusal`); a
    probe that looked on this process's instead would refuse a profile the launch would
    have found, and call the harness "could not be asked" when it was never looked for."""
    return bool(shutil.which(command[0], path=path))


def _claude_json(args: list[str], cwd=None, timeout: float = LIST_TIMEOUT, *,
                 env: dict | None = None, command=DEFAULT_COMMAND):
    """Run ``claude plugin <args> --json`` and parse it. ``None`` on any failure.

    ``None`` and ``[]`` are different answers and both are load-bearing downstream: "I
    could not look" must never render as "there is nothing installed", which is the
    confidently-wrong output `hooks.dispatched_handlers` documents at length. See
    :data:`UNKNOWN` for how the caller keeps that distinction.

    **Every way out is a return, never a raise**, and that is not defensive padding — it
    is what stops one row taking the whole preflight down. `doctor._checks()` builds its
    results with an eager list literal and has no per-check guard, and `hooks/hooks.json`
    renders a non-zero `charter doctor` as *"charter preflight failed - fix before
    working:"* at every SessionStart. A `claude` that does not return therefore printed
    **zero rows** and a scary line, which is the precise failure `iter_all`'s streaming and
    :data:`~charter.doctor.CHECK_TIMEOUT` were introduced to prevent.

    Three exceptions get out of `util.run` and all are real:

    * `util.ProcTimeout` — a `claude` that hangs. `util.run` raises it regardless of
      ``check``, so ``check=False`` does not cover it.
    * `OSError` — `shutil.which` in :func:`available` and the exec here are two moments,
      and a `claude` removed between them is a `FileNotFoundError` that would otherwise
      reach the crash reporter.
    * `ValueError` — below.
    """
    if not available(command, path=(env or {}).get("PATH")):
        return None
    try:
        proc = util.run([*command, "plugin", *args, "--json"], cwd=cwd, check=False,
                        timeout=timeout, env=env)
    except (util.ProcTimeout, OSError, ValueError):
        # `ValueError` is a NUL byte in the argv, the cwd or an environment value, which
        # `exec` refuses before anything runs — and a profile is a file a chat can write.
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout or "")
    except (ValueError, TypeError):
        return None


def _our_entries(*, env: dict | None = None, command=DEFAULT_COMMAND, cwd=None):
    """Every ``claude plugin list`` row that IS charter's plugin, or :data:`UNKNOWN`.

    *cwd* is not a nicety. Measured 2026-09-12 on 2.1.269: the rows are install records and
    are listed whatever the directory, while each row's ``enabled`` is the EFFECTIVE
    ``enabledPlugins`` value for the id resolved at the working directory — local over
    project over user. So a caller that wants to know whether charter runs in a particular
    directory has to ask from it. Today's callers pass none and keep this process's own,
    which is what they have always asked.

    Split out of :func:`installed_charter_plugin` when :func:`installed_for` needed the
    same rows asked a different question. One reader, because two of them would eventually
    disagree about which rows count as charter's — and the id check below is the only thing
    standing between `charter doctor --fix` and a plugin that is not charter's to touch.
    """
    entries = _claude_json(["list"], cwd=cwd, env=env, command=command)
    # ONE test, and it used to be two. `_claude_json` answers `None` for every way a read
    # can fail, and the line above it — `if entries is None: return UNKNOWN` — was carried
    # here from `installed_charter_plugin` and is strictly subsumed by this one: `None` is
    # not a list either, and both returned the same sentinel. The deletion sweep found it
    # as a survivor no test could tell from its own absence, which is the honest name for a
    # branch nothing can reach. What the two spellings meant is preserved here: "could not
    # read" and "`--json` answered something that is not a list of rows" are the same
    # answer — nothing is known — and neither is "there is nothing installed".
    if not isinstance(entries, list):
        return UNKNOWN
    ours = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        pid = e.get("id")
        # Equality against a module constant, and NOT also `_PLUGIN_ID_RE` — which used to
        # sit on the line above and became dead the moment this narrowed to one id. An
        # equality test against a constant is strictly stronger than any pattern: what
        # survives it IS the constant. The regex was kept for a while as "defence in
        # depth", which is the honest name for a check no test can distinguish from its own
        # absence; `refresh_argvs` still applies it, because that function takes an id from
        # a caller rather than producing one.
        if pid != PLUGIN_ID:
            continue
        if e.get("scope") not in _SCOPES:
            continue
        ours.append(e)
    return ours


def _same_dir(a, b) -> bool:
    """Do two paths name the same directory? ``False`` for anything unresolvable.

    `Path.resolve` is what makes ``/var/…`` and ``/private/var/…`` the same answer on
    macOS, which is not a test-only concern: a plane under ``/tmp`` is a symlinked path in
    every terminal on that machine.
    """
    if not isinstance(a, str) or not isinstance(b, (str, Path)):
        return False
    try:
        return Path(a).resolve() == Path(b).resolve()
    except (OSError, RuntimeError, ValueError):
        return False


def covers(entry: dict, project) -> bool:
    """Does this install of charter's plugin apply to a session rooted at *project*?

    ``user`` scope is machine-wide and covers everything. ``project`` and ``local`` are
    bound to the directory they were installed from, so an install belonging to somebody
    else's checkout is **not** an answer for this plane — and reading it as one is how
    "already installed" would be printed over a plane with no plugin at all, which is
    `check_guard_wired`'s #168 defect wearing a different row.
    """
    if entry.get("scope") == "user":
        return True
    return _same_dir(entry.get("projectPath"), project)


def installed_for(project, *, env: dict | None = None, command=DEFAULT_COMMAND):
    """The charter plugin install that covers *project* — or :data:`UNKNOWN`, or ``None``.

    :func:`installed_charter_plugin` answers a different question and keeps answering it:
    *which install may charter refresh*, where every project-scoped install points at the
    same versioned cache directory, so any one of them will do. This one answers *is this
    plane covered*, where they are not interchangeable at all.
    """
    ours = _our_entries(env=env, command=command)
    if ours is UNKNOWN:
        return UNKNOWN
    for e in ours:
        if covers(e, project):
            return e
    return None


def covering_entries(project, *, root=None, env: dict | None = None,
                     command=DEFAULT_COMMAND):
    """EVERY install of charter's plugin that applies to a session in *project*, asked from
    *project* — or :data:`UNKNOWN`. Beside :func:`installed_for`, which answers with the
    first one it finds.

    Every one of them, because this machine lists user, project and local entries side by
    side and the caller decides between them (review 6); the first that `covers` is an
    arbitrary choice among answers that can disagree.

    *root* is the PLANE, and it is why this is not `installed_for` with a loop.
    `charter init` installs at project scope for the plane root, while a chat stands in
    `workspaces/<ws>/` — a different `projectPath`, which `covers` alone reads as somebody
    else's checkout. Charter mirrors the plane's `enabledPlugins` into that directory
    (`claude_code.WORKSPACE_KEYS`), so the record that covers the plane is the one that
    answers for the chat, and the `enabled` this returns was resolved by the binary in
    *project* itself (D3, measured 2026-09-12).
    """
    ours = _our_entries(env=env, command=command, cwd=project)
    if ours is UNKNOWN:
        return UNKNOWN
    return [e for e in ours
            if covers(e, project) or (root is not None and covers(e, root))]


def install_argvs(scope: str = INSTALL_SCOPE,
                  source: str = MARKETPLACE_SOURCE,
                  *, command=DEFAULT_COMMAND) -> list[list[str]] | None:
    """The two commands that put charter's plugin on a machine, in order.

    ``None`` if *scope* is not one charter will install at, so a caller cannot run half a
    sequence against a value charter would not have built an argv from — the discipline
    :func:`refresh_argvs` already keeps.

    **The order is the mechanism**, and it is the fact this repository used to keep in
    prose: `tests/test_docs.py` pinned *"installing from a marketplace that has not been
    added fails"* against the README's paste-in block. The README no longer types these
    commands, so the assertion moved here, onto the code that runs them.

    ``-y`` on the install because charter runs it non-interactively; `claude` requires it
    when stdout is not a TTY and would otherwise refuse rather than prompt.
    """
    if scope not in _SCOPES:
        return None
    if not isinstance(source, str) or not source or source.startswith("-"):
        return None
    return [
        [*command, "plugin", "marketplace", "add", source],
        [*command, "plugin", "install", PLUGIN_ID, "--scope", scope, "-y"],
    ]


def _step(argv: list[str], cwd, *, env: dict | None = None) -> tuple[bool, str]:
    """Run one `claude plugin` step. ``(ok, why)``, never raising — same reasons as
    :func:`force_refresh`, which this sits beside."""
    try:
        proc = util.run(argv, cwd=cwd, check=False, timeout=REFRESH_TIMEOUT, env=env)
    except (util.ProcTimeout, OSError) as e:
        return False, str(e) or type(e).__name__
    if proc.returncode != 0:
        why = (proc.stderr or proc.stdout or "").strip().splitlines()
        return False, (why[-1][:200] if why else f"exit {proc.returncode}")
    return True, ""


def install(project, scope: str = INSTALL_SCOPE, *, env: dict | None = None,
            command=DEFAULT_COMMAND) -> tuple[str, str]:
    """Install charter's own Claude Code plugin for *project*. ``(status, detail)``.

    Five statuses, because five different things are true and only one of them is a fault:

    * ``present`` — an install already covers *project*. Nothing runs.
    * ``installed`` — charter added the marketplace and installed the plugin.
    * ``unavailable`` — no `claude` on PATH. An opencode or Codex plane, or a terminal
      with no Claude Code at all; a perfectly ordinary state and never an error.
    * ``unknown`` — `claude plugin list --json` could not be read. **Nothing is installed
      on a guess.** An older `claude` that does not understand `--json` is the population
      this is for, and installing over an unknown state is how a second copy appears.
    * ``failed`` — a step ran and did not succeed.

    **Only ever called for the thing it installs for** — `charter init`, `charter doctor
    --fix` and `charter harness install`, each a command a person typed, and since ruling 47
    the launch of a profile whose own config folder lacks the plugin
    (`wiring.wired_or_refusal`), where the plugin is what makes that chat a guarded one.
    Nothing here may be reached as a side effect of `charter workspace list`: installing
    software because some UNRELATED command ran is #857's surprise, and the same reason
    charter refuses to write `~/.claude/settings.json` unasked.
    """
    # The PATH the steps below will run under, as `_claude_json` asks it (A2): a profile
    # whose program lives only on its own `PATH` is installed for, not called unavailable.
    if not available(command, path=(env or {}).get("PATH")):
        return "unavailable", (f"`{command[0]}` is not on PATH, so there is no Claude "
                               f"Code to install a plugin into")
    entry = installed_for(project, env=env, command=command)
    if entry is UNKNOWN:
        return "unknown", ("could not read `claude plugin list --json`, so charter does "
                           "not know what is installed and will not install over it")
    if entry is not None:
        return "present", (f"{entry.get('id')} is already installed "
                           f"({entry.get('scope')} scope)")
    argvs = install_argvs(scope, command=command)
    if argvs is None:
        return "failed", f"{scope!r} is not a scope charter will install at"
    add, put = argvs
    cwd = str(project) if project is not None and Path(project).is_dir() else None
    added, why_add = _step(add, cwd, env=env)
    ok, why = _step(put, cwd, env=env)
    if ok:
        return "installed", f"{PLUGIN_ID} installed at {scope} scope"
    # The marketplace step is allowed to fail and the install still to be attempted: a
    # marketplace that is ALREADY registered is the common way `add` exits non-zero, and
    # refusing to continue there would make the second install on a machine impossible.
    # So the install's own failure is the verdict — and when the step before it failed too,
    # that is said, because "already registered" and "offline" fail identically here and
    # the reader needs to know a second command was also unhappy.
    if not added:
        return "failed", (f"`{' '.join(put)}` failed: {why}. `{' '.join(add)}` failed "
                          f"first ({why_add}) — an already-registered marketplace fails "
                          f"that way harmlessly, so read the install error above it.")
    return "failed", f"`{' '.join(put)}` failed: {why}"


def installed_charter_plugin(prefer_project=None):
    """The installed charter plugin entry — or :data:`UNKNOWN`, or ``None``.

    **Three answers, because there are three states**, and the middle one is the whole
    point:

    * an entry — charter's plugin is installed and charter is willing to act on it;
    * :data:`UNKNOWN` — `claude plugin list --json` could not be read. An older `claude`
      that does not understand ``--json``, a hang, a `claude` removed from PATH mid-call,
      malformed output. Nothing is known.
    * ``None`` — the list was read and charter's plugin is not in it. CLI-only is a
      supported install (`docs/install.md`), so this is an ordinary, green state.

    *prefer_project* picks between several. charter's plugin is normally installed at
    ``project`` scope, once per project, and every one of those installs points at the SAME
    versioned cache directory — so refreshing any of them repopulates the cache for all of
    them. Which one is chosen therefore does not change the outcome; it changes which
    project's `claude plugin` invocation performs it, and running it against the plane you
    are standing in is the least surprising choice.

    The returned entry has the two fields that reach an argv already validated — an entry
    charter would refuse to act on is not returned at all, so no caller has to remember to
    check.

    **Only ``charter@charter``.** `docs/install.md` says `claude plugin marketplace add
    diazoxide/charter-plane`, and the name a marketplace registers under is the one its own
    `marketplace.json` declares — ``charter`` — so that is the id anyone who followed the
    documentation has. Matching `charter@<anything>` instead would let charter UNINSTALL a
    plugin called `charter` published by somebody else's marketplace, which is not
    charter's to touch. A plugin outside that id reads as "not installed" here, which is
    the honest answer: charter cannot identify it as its own.
    """
    ours = _our_entries()
    if ours is UNKNOWN:
        return UNKNOWN
    if not ours:
        return None
    if prefer_project is not None:
        want = str(Path(prefer_project).resolve())
        for e in ours:
            got = e.get("projectPath")
            if isinstance(got, str) and str(Path(got).resolve()) == want:
                return e
    return ours[0]


def marketplace_clone(name: str) -> Path | None:
    """Where the marketplace named *name* is cloned, or ``None``.

    Its one caller in `doctor` splits *name* off :data:`PLUGIN_ID`, so it is a constant by
    the time it arrives. Checked anyway, because that is a fact about today's callers and
    not about this function: it is reachable on its own, and a path built from an unchecked
    name is a path.
    """
    if not isinstance(name, str) or not _MARKETPLACE_RE.fullmatch(name):
        return None
    rows = _claude_json(["marketplace", "list"])
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict) or row.get("name") != name:
            continue
        loc = row.get("installLocation")
        if isinstance(loc, str) and loc:
            p = Path(loc)
            return p if p.is_dir() else None
    return None


def content_hash(root) -> str | None:
    """A stable digest of the plugin surface under *root*, or ``None`` if it cannot be read.

    Path and bytes both go into the digest, so a file that is renamed, added or deleted
    changes it as surely as an edited one does. Entries are sorted, so two trees that hold
    the same files hash the same regardless of directory-iteration order. Symlinks are not
    followed and directories are walked with :meth:`Path.rglob`, which does not.
    """
    root = Path(root)
    if not root.is_dir():
        return None
    h = hashlib.sha256()
    try:
        for rel in sorted(_surface_files(root)):
            h.update(rel.encode("utf-8"))
            h.update(b"\0")
            h.update(hashlib.sha256((root / rel).read_bytes()).digest())
    except OSError:
        return None
    return h.hexdigest()


def _surface_files(root: Path) -> list[str]:
    """Every plugin-surface file under *root*, as POSIX relative paths."""
    out = []
    for name in PLUGIN_SURFACE:
        base = root / name
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if p.is_file() and not p.is_symlink():
                out.append(p.relative_to(root).as_posix())
    return out


def differing(installed, clone, limit: int = 3) -> list[str]:
    """Up to *limit* surface paths that differ between the two trees, for the report line.

    The hash says *whether*; this says *which*, and a doctor row that names
    ``skills/secrets/SKILL.md`` is the difference between a number a reader distrusts and
    a fact they can go and look at.
    """
    installed, clone = Path(installed), Path(clone)
    try:
        left, right = set(_surface_files(installed)), set(_surface_files(clone))
    except OSError:
        return []
    out = []
    for rel in sorted(left | right):
        if len(out) >= limit:
            break
        if rel not in left or rel not in right:
            out.append(rel)
            continue
        try:
            if (installed / rel).read_bytes() != (clone / rel).read_bytes():
                out.append(rel)
        except OSError:
            out.append(rel)
    return out


def refresh_argvs(plugin_id: str, scope: str) -> list[list[str]] | None:
    """The three commands that force the installed plugin back into step, in order.

    ``None`` if either input fails its check, so a caller cannot run a partial sequence
    against a value charter would not have built an argv from.

    The order is the mechanism, verified end to end rather than reasoned about:

    1. ``marketplace update`` — advance the clone. Skip it and the reinstall faithfully
       re-copies the same stale content.
    2. ``uninstall`` — the install step is a no-op against an already-installed plugin
       (measured: *"Plugin is already installed"*, cache untouched), so this is what makes
       step 3 do any work at all.
    3. ``install`` — which re-copies the marketplace clone over the versioned cache
       directory, sentinel edit and all.

    ``-y`` on both mutating steps because charter runs them non-interactively; `claude`
    requires it when stdout is not a TTY and would otherwise refuse rather than prompt.
    """
    if not isinstance(plugin_id, str) or not _PLUGIN_ID_RE.fullmatch(plugin_id):
        return None
    if scope not in _SCOPES:
        return None
    marketplace = plugin_id.split("@", 1)[1]
    return [
        ["claude", "plugin", "marketplace", "update", marketplace],
        ["claude", "plugin", "uninstall", plugin_id, "--scope", scope, "-y"],
        ["claude", "plugin", "install", plugin_id, "--scope", scope, "-y"],
    ]


def force_refresh(prefer_project=None) -> tuple[bool, str]:
    """Re-copy the marketplace clone over the installed plugin. ``(ok, detail)``.

    ``(False, …)`` covers every way this can decline, and each of them is a real state a
    charter user is in rather than a defensive branch: no `claude` on PATH (opencode or
    Codex), no charter plugin installed (CLI-only, which `docs/install.md` supports), and
    a `claude plugin` call that failed.

    **This is not a rollback-capable operation.** The uninstall step is what makes the
    install step do anything, so a failure between them leaves the plugin **uninstalled**
    for that scope. That is the one outcome that must not be reported as a generic command
    failure: the returned detail leads with what the operator now has and the command that
    restores it, because by the time this runs the CLI has already been replaced and the
    harness artifact already moved — the operator is several steps in, and a line naming
    only the argv that failed leaves them to work out that a plugin went missing.

    **It never raises.** `_refresh_plugin` promises "best-effort, never fatal", and that
    promise was false while `util.run` here was unguarded: `ProcTimeout` at 120s, or a
    `claude` removed from PATH between :func:`available` and the exec, propagated out
    through `_update_dev` and `cmd_update` — turning a plugin that could not be refreshed
    into an update that ends in a traceback, after the install it was reporting on
    succeeded.
    """
    if not available():
        return False, "the `claude` CLI is not on PATH, so there is no plugin to refresh"
    entry = installed_charter_plugin(prefer_project)
    if entry is UNKNOWN:
        return False, ("could not read `claude plugin list --json`, so charter does not "
                       "know what is installed and will not uninstall anything")
    if entry is None:
        return False, "no charter plugin is installed here (`claude plugin list`)"
    argvs = refresh_argvs(entry["id"], entry["scope"])
    # Unreachable through `installed_charter_plugin`, which already refuses an entry it
    # would not act on — and kept anyway, because the alternative is `refresh_argvs`
    # returning `None` into a `for argv in None`. Two checks of one rule is the cheap
    # failure; one check that a refactor moves is the expensive one.
    if argvs is None:
        return False, "the installed plugin's id or scope is not one charter will act on"
    cwd = entry.get("projectPath") if entry.get("scope") == "project" else None
    if cwd is not None and not Path(cwd).is_dir():
        cwd = None
    uninstalled = False
    for argv in argvs:
        try:
            proc = util.run(argv, cwd=cwd, check=False, timeout=REFRESH_TIMEOUT)
        except (util.ProcTimeout, OSError) as e:
            return False, _failed(argv, str(e) or type(e).__name__, uninstalled, argvs[2])
        if proc.returncode != 0:
            why = (proc.stderr or proc.stdout or "").strip().splitlines()
            return False, _failed(argv, why[-1][:200] if why else f"exit {proc.returncode}",
                                  uninstalled, argvs[2])
        if argv is argvs[1]:
            uninstalled = True
    return True, f"{entry['id']} reinstalled from the marketplace clone"


def _failed(argv: list[str], why: str, uninstalled: bool, reinstall: list[str]) -> str:
    """The detail line for a refresh that stopped part-way.

    Two different sentences for two different states, because they need two different
    things from the reader. Before the uninstall, nothing has changed and the failed
    command is the whole story. After it, the plugin is GONE for that scope and the reader
    needs the command that brings it back before they need to know which step broke.
    """
    if not uninstalled:
        return f"`{' '.join(argv)}` failed: {why}"
    return (f"the plugin is now UNINSTALLED — `{' '.join(argv)}` failed ({why}). "
            f"Restore it: {' '.join(reinstall)}")
