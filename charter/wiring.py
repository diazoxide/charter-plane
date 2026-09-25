"""Is a harness profile wired — does charter's guard actually run in the folder it names?

A profile exists to point a harness at another config folder, and **every kind loses
charter's wiring when its folder moves**. Measured 2026-09-11 and again on 2026-09-12
against claude 2.1.269, codex-cli 0.147.0 and opencode 1.18.23, in throwaway folders:

* Claude Code under an empty `$CLAUDE_CONFIG_DIR` has no charter plugin at all — not even
  "enabled but not installed" — because the `charter` marketplace is known only to the
  folder it was added in.
* Codex under an empty `$CODEX_HOME` has no plugin, no hook trust and no
  `shell_environment_policy.set`.
* opencode under a throwaway `$XDG_CONFIG_HOME` has no shim, loads no plugin, and its
  shells get no `$CHARTER_HARNESS`.

So a chat started on such a profile *looks* guarded and is not, which is the failure this
module exists to stop. **A profile that is not wired is wired, not refused, where charter
can do it alone** (ruling 47): a launch that finds a DEFINITE unwired answer runs the same
install `charter harness install <name>` runs, says in one line what it installed where,
asks again, and goes on (:func:`wired_or_refusal`). Where charter cannot — an UNKNOWN, a
profile it may not act for, an install that failed, and Codex, whose hook trust only a
person inside a Codex session can grant — it refuses and prints the fix, **built-ins
included** (ruling 10): `charter codex` on a plane where nobody wired Codex refuses where it
used to start, because a chat that looks guarded and is not is the same failure whichever
profile started it. That narrows #857's rule ("installing software because some unrelated
command ran") rather than breaking it: the launch of that very harness is the related
command, and the line says so where the operator is looking.

**Wiring is detected by ASKING the harness under the profile's own environment**, never by
reading the profile's variable names. One account can be reached through variables that do
or do not move the plugin — `$XDG_DATA_HOME` moves opencode's login and leaves its plugins
where they are — so a rule written from variable names is a rule about the wrong thing.
`claude plugin list --json` and `opencode debug config` follow the environment they are
given; Codex's three marks are all in one file.

**Nothing is asked of a profile charter may not run yet** (ruling 1). A probe runs the
profile's own command, so it passes the same two checks a launch does first: git would not
carry `charter.local.toml`, and the operator approved this command (`profiletrust`).

**An unknown is never a pass** (ADR 0009, ruling 12). A probe that times out, exits
non-zero, answers something unparseable, or reads a file a chat left in a shape the harness
never writes, refuses the launch with a sentence naming the probe to run by hand. No flag
launches a profile unguarded.

**Nothing here runs on a hook path** (ruling 11). A probe costs 137-718 ms and writes into
the folder it asks about; `hooks/hooks.json` fires `charter doctor --preflight` at every
session start, and that mode builds no profile row and calls nothing here.

**A launch never trusts the cache** (review B2, ruling 21). :func:`cached` is for the
selector's rows and nothing else: the file sits under `.charter/`, which no path guard
covers (ADR 0014 — a path pattern is host policy), so a chat can write it, compute its key,
and date an entry ahead. :func:`wired_or_refusal` always probes.

**What a :class:`Wiring` carries is escaped and never clipped.** Every surface that shows
one bounds it its own way (ruling 45): a refusal sentence with a fixed marker, a `doctor`
row by saying how much it hid — and a row cannot count what was already cut before it saw it.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shlex
import shutil
import time
import tomllib
from pathlib import Path
from typing import Callable, Mapping, NamedTuple

from . import config, contain, plugincache, profiles, util
from .harness import claude_code, codex, opencode

#: The three answers. `UNKNOWN_STATE` rather than `UNKNOWN`, because `plugincache.UNKNOWN`
#: is a sentinel object and these are strings that end up in a JSON cache.
WIRED, UNWIRED, UNKNOWN_STATE = "wired", "unwired", "unknown"

#: The launcher refusal kind this module produces. Callers branch on the KIND and never on
#: the text (ruling 27): a sentence gets reworded, and a comparison against one is a guard
#: that stops guarding on the day it does.
KIND_WIRING = "wiring"

#: Under `config.STATE_DIR`.
CACHE = "cache/harness-wiring.json"

#: How long a remembered answer may be reused by the selector. Both bounds matter: without
#: the lower one, an entry a chat dated into the future passes the age test forever.
MAX_AGE = 24 * 3600

#: The key prefix Codex writes its hook-trust ledger under, per plugin.
CODEX_TRUST_PREFIX = f"{plugincache.PLUGIN_ID}:hooks/hooks.json:"

#: The handler of charter's GUARD — `charter hook pretooluse`, the hook on `Bash` that
#: refuses a command. **A trusted hook is not a trusted guard**: Codex asks about each hook
#: separately, and neither an approved SessionStart reconcile nor an approved `Task|Agent`
#: dispatch hook (`pretooluse-dispatch`, a `pre_tool_use` hook too) says anything about
#: whether this one runs before a shell command (ruling 7 — "charter's guard actually
#: runs"). Named by HANDLER and not by position: Codex keys trust by
#: `<event>:<group>:<hook>` within the installed plugin's own `hooks/hooks.json`, and a
#: position is a fact about one version of that file (:func:`_codex_guard_keys`).
CODEX_GUARD_HANDLER = "pretooluse"

#: Where Codex keeps an installed plugin, under its home: `plugins/cache/<marketplace>/
#: <plugin>/<version>/` (D4, codex-cli 0.147.0).
CODEX_PLUGIN_CACHE = Path("plugins") / "cache"

#: How a Codex plugin is installed, pinned against codex-cli 0.147.0 by running it
#: (D4, 2026-09-12): `codex plugin` has add / list / marketplace / remove and no `install`.
#: Printed with `CODEX_HOME=` in front of it, never run — it installs software into an
#: account folder, and running this command IS the consent for the one line charter writes.
CODEX_COMMANDS = (("codex", "plugin", "marketplace", "add",
                   "https://github.com/" + plugincache.MARKETPLACE_SOURCE),
                  ("codex", "plugin", "add", plugincache.PLUGIN_ID))
#: The step no command can take: Codex asks a person, in a session, to trust each hook.
CODEX_APPROVE = "start codex once and approve charter's hooks when it asks"

#: What a refusal sentence repeats of a detail or a fix: a PATH's budget, because both name
#: paths and a clipped path is one the reader cannot act on — and still a fixed number,
#: because a budget the input can grow is not a budget (`contain.DISPLAY_LIMIT`).
SAID_LIMIT = contain.PATH_DISPLAY_LIMIT

# Every sentence says the rule worked and names the fix in the same breath (CONTEXT.md,
# *A refusal is the rule working*). No "charter:" prefix — each caller says it its own way,
# the way `launcher`'s own texts do. Every profile-derived value is contained first
# (ruling 35): `charter.local.toml` is a file a chat can write, and a `\r` or an ESC in a
# command could redraw the line above to show a harmless command while another one runs.
NOT_WIRED = ("profile '{name}' is not wired — {detail}, so a chat on it would run without "
             "charter's guard. Nothing was started. Wire it: {fix}")
CANNOT_TELL = ("charter could not ask {kind} whether profile '{name}' is wired ({detail}), "
               "so it will not start it unguarded. Nothing was started. Run "
               "charter harness install {name}, or check by hand: {probe}")
#: The launch tried the install and a step of it did not do what it does (ruling 47). It
#: names what the install said, because that is the one thing `charter harness install`
#: run by hand would add — and then names that command, which prints the whole of it.
COULD_NOT_WIRE = ("profile '{name}' is not wired, and charter could not wire it — {said}. "
                  "Nothing was started. Wire it by hand: {fix}")

#: The one line a launch says when it wired a profile (ruling 47; no "charter:" prefix,
#: each caller's own). Software went into somebody's folder, so it says what and where;
#: and a launch whose own install found the work already done says THAT, because two
#: launches of one unwired profile at once are serialised (:func:`_serialised`) and the
#: second one installed nothing.
WIRED_NOW = "wired '{name}' — installed {what}"
WIRED_FOUND = "wired '{name}' — {what} was already in place"

#: `doctor`'s hint on a row the next launch will wire: the fix first, because a clipped
#: row keeps its head (ruling 45), then the fact that pressing Enter is also the fix.
NEXT_LAUNCH_WIRES = "{fix} — or start it: the next launch installs {what} itself"

#: The install statuses that are charter reporting what it DID. Everything else —
#: `unvouched`, `unavailable`, `unknown`, `failed`, `refused`, `malformed`, `doubled`, and
#: any status a harness adds later — is a fault a launch refuses on (ruling 47) and `init`
#: warns about (`commands._WIRED_NOTES`, pinned equal). Listed this way round so a new
#: status fails loud rather than quiet. :data:`WROTE` is the half that changed a file.
WROTE = frozenset({"created", "installed", "refreshed", "added"})
DID = WROTE | {"present", "current"}

CODEX_POLICY_BY_HAND = (
    "{path} already has a [shell_environment_policy] table without charter's line, and "
    "charter does not edit TOML it did not write — nothing was changed. Add this line "
    'inside that table:\n  set = {{ CHARTER_HARNESS = "codex" }}\n'
    'or, if the table already has a `set`, add CHARTER_HARNESS = "codex" to it.')

#: A Codex config a chat left in a shape Codex itself never writes. Unknown, not unwired:
#: charter cannot say what Codex makes of it, and a guess in either direction is a guess.
CODEX_SHAPE = "{path} holds {key} as something other than a table, which Codex never writes"

#: Most specific first. Claude Code 2.1.269 resolves `enabled` itself — measured
#: 2026-09-12, every listed entry of one plugin id carries the same effective value, merged
#: local > project > user at the probe's own cwd — so this order decides nothing today. It
#: is here for the day that stops being true, and it is the order that fails CLOSED between
#: install records: a local-scope record that reads disabled outranks a user-scope one that
#: reads enabled (ruling 28).
_SCOPE_ORDER = ("local", "project", "user")


class Wiring(NamedTuple):
    """What was asked, what it answered, and what to do about it."""

    #: WIRED | UNWIRED | UNKNOWN_STATE.
    state: str
    #: What was asked and what it answered — escaped, never clipped (see the module).
    detail: str
    #: The command that would fix it; ``""`` when wired. Escaped, never clipped.
    fix: str


class Answer(NamedTuple):
    """What a launch is told by :func:`wired_or_refusal`: whether it may go on, and what
    charter installed on the way — two fields, because "it may start" and "software went
    into a folder" are both things the operator is owed a sentence about."""

    #: Why the profile may not start, or ``""`` when it may.
    refusal: str
    #: :data:`WIRED_NOW` or :data:`WIRED_FOUND` when this call wired the profile; ``""``
    #: when it had nothing to install — which is every launch of a wired profile.
    wired: str


def _whole(value) -> str:
    """*value* escaped for a terminal and not clipped (ruling 35; see the module docstring)."""
    return contain.readable(value, contain.NO_CLIP)


def said(text: str) -> str:
    """A :class:`Wiring` field bounded for a SENTENCE, with contain's fixed marker.

    Its own clip rather than `contain.readable` again: the field is escaped already, and a
    second pass would double every backslash the first one wrote (`\\u001b` would read as
    `\\\\u001b`). Ruling 45: a sentence may keep the fixed marker; a row must count.
    """
    return text if len(text) <= SAID_LIMIT else text[:SAID_LIMIT] + "..."


def _install_fix(p: profiles.Profile) -> str:
    """The one sentence every "wire it with charter" answer ends in."""
    return f"charter harness install {_whole(p.name)}"


def _typed(p: profiles.Profile, argv, *, cwd=None) -> str:
    """*argv* as an operator would paste it: `cd` first when *cwd* matters, then the
    profile's variables, then the words — **each one shell-quoted, then escaped**.

    Quoted because a home with a space in it, or a `;`, is a fix that cannot be pasted
    otherwise; escaped after the quoting and not before, because the escape is for the
    terminal the line is shown on and the quoting is for the shell it is pasted into.
    The variables as the launch EXPANDS them: a quoted `~` is a directory named `~`.
    """
    pieces = [] if cwd is None else ["cd", shlex.quote(str(cwd)), "&&"]
    pieces += [f"{name}={shlex.quote(value)}"
               for name, value in sorted(profiles.expanded_env(p).items())]
    pieces += [shlex.quote(str(word)) for word in argv]
    return _whole(" ".join(pieces))


def environment(p: profiles.Profile) -> dict[str, str]:
    """The environment *p*'s command would be exec'd with, for a probe to run under.

    `launcher.environment` and not a second merge of the same three things: a probe that
    asked under a different environment than the launch would use is asking about a session
    nobody is about to start. ``framed=True`` because that is the merge that drops nothing —
    the unframed one removes `$CHARTER_SESSION_ID`, and `util.run`'s ``env`` is an overlay
    that cannot express a removal anyway.

    Imported at call time. `launcher` imports this module at the top, and ruling 43 keeps
    profile code off every `charter hook …` process's import path.
    """
    from .frame import launcher

    return launcher.environment(p, os.environ, framed=True)


def probe_argv(p: profiles.Profile) -> list[str]:
    """What charter runs to ask *p*'s harness whether it is wired — ``[]`` for Codex, whose
    three marks are a file read, and for a kind charter has no check for."""
    kind = _KINDS.get(p.harness)
    if kind is None or not kind.probe:
        return []
    return [*profiles.expanded_command(p), *kind.probe]


def by_hand(p: profiles.Profile) -> str:
    """The probe as an operator would type it: the profile's variables, then the command —
    or, for a kind whose answer is a file, the command that shows that file."""
    argv = probe_argv(p)
    if argv:
        return _typed(p, argv)
    return _whole(shlex.join(["cat", str(codex.config_path(environment(p)))]))


def _not_asked(p: profiles.Profile) -> tuple[str, str]:
    """Why charter may not run *p*'s command to ask it anything — ``("", "")`` when it may.

    ``(sentence, fix)``. **The same two checks a launch makes before its own**, in the same
    order (ruling 1, and the Global Constraint *No profile's command runs before that
    profile passes the ignored check and the trust check*): a probe IS a run of the
    profile's command, and there are four callers of it — the launcher, the selector,
    `harness install` and `doctor`. A gate each of them has to remember is a gate one of
    them will not, and the thing it lets through is a command out of a file a chat can
    write.

    **The ignore check first**: an approved profile in a file git would commit is still a
    declaration charter has refused, and a record saying the operator once approved it says
    nothing about the file it now sits in. Built-ins skip both — their command is charter's
    own, out of the registry.

    The sentence is Task 3's own and the launcher's own, never a paraphrase: nothing asks
    here, so an unapproved profile is told what an open nobody is at is told
    (:data:`profiletrust.UNATTENDED`).
    """
    from . import profiletrust
    from .frame import launcher

    if p.source == profiles.BUILTIN:
        return "", ""
    name = contain.readable(p.name)
    check = profiles.ignore_check(config.ROOT)
    if check.reason:
        return launcher.IGNORED.format(name=name, why=check.reason), check.fix
    state = profiletrust.approval_needed(p)
    if state:
        return (profiletrust.UNATTENDED.format(name=name, state=state),
                f"charter {_whole(p.name)}")
    return "", ""


def detect(p: profiles.Profile, *, cwd) -> Wiring:
    """Ask *p*'s harness, under *p*'s environment, whether charter's guard runs there.

    *cwd* is the directory the chat would start in — Claude Code resolves `enabled` there,
    and an install record is bound to the directory it was installed from, so this is not a
    detail that can be defaulted.

    Never cached and never memoised: the whole point of :func:`cached` living beside this
    is that only one of them may start a chat. A profile :func:`_not_asked` stops is an
    UNKNOWN whose detail is that sentence — charter did not look, which is not a pass.
    """
    why, fix = _not_asked(p)
    if why:
        return Wiring(UNKNOWN_STATE, why, fix)
    return _asked(p, cwd=cwd)


def _asked(p: profiles.Profile, *, cwd) -> Wiring:
    """:func:`detect` past its gate: the kind's own question, and nothing that raises.

    **Never a traceback** (A1): the config files and answers read here are the profile's,
    and a profile is a file a chat can write. `ValueError` is what a NUL byte in a path or
    an environment value raises out of `stat`, `open` and `exec` alike, so it is the one
    exception every kind can meet that is not already its own UNKNOWN.
    """
    kind = _KINDS.get(p.harness)
    if kind is None:
        # A kind charter has no wiring check for is an UNKNOWN and therefore a refusal, not
        # a pass: the day a kind joins the registry without one, this is the row that says so.
        return Wiring(UNKNOWN_STATE, f"charter has no wiring check for {_whole(p.kind)}",
                      _install_fix(p))
    try:
        return kind.ask(p, Path(cwd), environment(p))
    except ValueError as e:
        return Wiring(UNKNOWN_STATE,
                      f"charter could not ask under this profile's environment "
                      f"({_whole(e)})", _install_fix(p))


def wired_or_refusal(p: profiles.Profile, *, cwd, root: Path) -> Answer:
    """Wire *p* if charter can, then answer: why *p* may not start, or that it may — and
    what was installed on the way. **The one home for every launch path** (ruling 47): the
    check before tmux, the pane before its `exec`, a reopen, a handoff. One function, so no
    path wires and another refuses over the same folder.

    Always a fresh probe (review B2), and the gate first: a profile charter may not run a
    command for (:func:`_not_asked`) is told why in the launcher's and Task 3's own words,
    and nothing is asked or written for it. Then:

    * **WIRED** — nothing to say, ``Answer("", "")``.
    * **UNKNOWN** — refused with its own sentence (ruling 12), and **never installed
      over**: "charter could not look" is not "charter looked and the guard is absent", and
      installing over an unknown state is how a second copy appears (`plugincache.install`
      keeps the same rule for `init`).
    * **UNWIRED** — the kind's own wire runs (:func:`_wire`, what `charter harness install`
      runs), one launch at a time per profile (:func:`_serialised`), and the folder is asked
      again. Wired now: the fresh answer is remembered for the selector's next paint and the
      launch goes on, with one line about what went where. Still not: a refusal — naming
      what the install said where a step of it faulted (:data:`COULD_NOT_WIRE`), else the
      fresh probe's own sentence, which for Codex is Codex's own steps. **Never remembered
      as wired on a guess**: what is remembered is what the second probe said.

    A3 holds — a start pays two probes — because the install happens at the FIRST probe
    that sees UNWIRED, and the second finds the folder wired. Codex is the exception by
    construction: charter writes its part and the second probe still says unwired, because
    hook trust is granted only inside a Codex session.
    """
    why, _fix = _not_asked(p)
    if why:
        return Answer(why, "")
    w = _asked(p, cwd=cwd)
    if w.state != UNWIRED:
        return Answer(sentence(p, w), "")
    # UNWIRED is a kind's own answer, so the kind is in the table: an unknown kind is an
    # UNKNOWN (`_asked`) and returned above.
    kind = _KINDS[p.harness]
    with _serialised(p):
        did = _wire(p, root)
        again = _asked(p, cwd=cwd)
    remember(p, cwd=cwd, w=again)
    name = contain.readable(p.name)
    if again.state == WIRED:
        what = kind.installs(environment(p))
        line = WIRED_NOW if any(status in WROTE for status, _d in did) else WIRED_FOUND
        return Answer("", line.format(name=name, what=what))
    faults = [f"{status}: {detail}" for status, detail in did if status not in DID]
    if faults:
        return Answer(COULD_NOT_WIRE.format(name=name, said=said("; ".join(faults)),
                                            fix=said(again.fix or _install_fix(p))), "")
    return Answer(sentence(p, again), "")


def would_install(p: profiles.Profile, w: Wiring) -> str:
    """What a launch of *p* would install for the answer *w* — `charter@charter into
    <folder>` — or ``""`` for an answer a launch would not install over.

    The selector's word for a row that starts rather than refuses, and `doctor`'s for a
    hint that says the next launch is also the fix. Three things have to hold, and each is
    a case that stays refused without it: the answer is a definite UNWIRED; the kind's
    wire can finish on its own (Codex's cannot — trust is a person's, inside a session);
    and the fix charter named IS the install, because for a plugin that is installed and
    disabled, or a foreign file in opencode's realm, the install answers `present` and
    changes nothing (review 7's loop), so the row keeps the sentence with the fix that does.
    """
    kind = _KINDS.get(p.harness)
    if (kind is None or not kind.automatic or w.state != UNWIRED
            or w.fix != _install_fix(p)):
        return ""
    return kind.installs(environment(p))


def hint(p: profiles.Profile, w: Wiring) -> str:
    """*w*'s fix for a `doctor` row — with the fact that the next launch installs it too,
    where that is true (:func:`would_install`). `doctor` itself probes and never installs
    (ruling 11), so the sentence is about the launch and not about the row."""
    what = would_install(p, w)
    return NEXT_LAUNCH_WIRES.format(fix=w.fix, what=what) if what else w.fix


def sentence(p: profiles.Profile, w: Wiring) -> str:
    """*w* said as a refusal of *p* — ``""`` when it is wired. For a caller that already
    holds an answer and must not pay for a second probe to word it (`harness install`)."""
    name = contain.readable(p.name)
    if w.state == WIRED:
        return ""
    if w.state == UNWIRED:
        return NOT_WIRED.format(name=name, detail=said(w.detail), fix=said(w.fix))
    return CANNOT_TELL.format(kind=contain.readable(p.kind), name=name,
                              detail=said(w.detail), probe=said(by_hand(p)))


# --------------------------------------------------------------------------- #
# Per kind                                                                     #
# --------------------------------------------------------------------------- #


def _claude(p: profiles.Profile, cwd: Path, env: Mapping[str, str]) -> Wiring:
    """Claude Code: `claude plugin list --json`, run as *p* would run `claude`.

    Two facts out of the same answer, and they are resolved differently — measured
    2026-09-12 on 2.1.269 in throwaway folders:

    * the ENTRIES are install records, listed whatever the cwd, each bound to the directory
      it was installed from (`plugincache.covers`);
    * `enabled` is the EFFECTIVE `enabledPlugins` value for the plugin id resolved at the
      probe's own cwd — local over project over user — and every entry of that id carries
      the same value.

    So the probe is given *cwd*, and charter reads no settings file of its own (ruling 36's
    "unless"): a disable written ONLY to `<cwd>/.claude/settings.local.json`, and only to
    `<cwd>/.claude/settings.json`, each flipped the listed entry to `enabled: false` beside
    an enabled user-scope install. A second reader would answer for a different merge than
    the binary's, and a wrong UNWIRED refuses a chat that would have been guarded.

    **An install covering the PLANE covers a chat in that plane's workspace** (D3). `charter
    init` installs at project scope for the plane root, and a chat's directory is
    `workspaces/<ws>/` — a different `projectPath`, which `covers` alone reads as not this
    plane's. It is safe to count because of the fact above and only because of it: the
    `enabled` on that record is what the binary resolved at *cwd*, so a plane install the
    chat's own directory disables reads as disabled here
    (`test_a_plane_install_the_chats_directory_disables_is_not_wired`).
    """
    folder = claude_code.config_home(env)
    entries = plugincache.covering_entries(cwd, root=config.ROOT, env=dict(env),
                                           command=profiles.expanded_command(p))
    where = f"{_whole(folder)} for {_whole(cwd)}"
    if entries is plugincache.UNKNOWN:
        return Wiring(UNKNOWN_STATE,
                      f"claude plugin list --json could not be read in {where}",
                      _install_fix(p))
    if not entries:
        return Wiring(UNWIRED, f"{plugincache.PLUGIN_ID} is not installed in {where}",
                      _install_fix(p))
    best = min(entries, key=lambda e: _SCOPE_ORDER.index(e.get("scope"))
               if e.get("scope") in _SCOPE_ORDER else len(_SCOPE_ORDER))
    scope = _whole(best.get("scope"))
    if best.get("enabled") is True:
        return Wiring(WIRED,
                      f"claude plugin list: {plugincache.PLUGIN_ID} enabled at {scope} "
                      f"scope in {where}", "")
    # NOT `charter harness install`: `plugincache.install` answers `present` for an install
    # that exists, so pointing back at it would print a fix that changes nothing and loops
    # — review 7's objection, one harness over.
    #
    # `--scope local`, run FROM the chat's directory, because that is the enable measured
    # to undo every disable that reaches it (claude 2.1.270, 2026-09-13, throwaway folders):
    # a `false` in `<dir>/.claude/settings.local.json`, in `<dir>/.claude/settings.json`,
    # and — in a git plane — in the plane root's `settings.local.json`. `--scope project`
    # and `--scope user` each exited 1 over a local disable and changed nothing, which is
    # review 7's loop again; and a scope-less enable run from anywhere else writes where
    # the chat does not read.
    fix = _typed(p, [*profiles.expanded_command(p), "plugin", "enable",
                     plugincache.PLUGIN_ID, "--scope", "local"], cwd=cwd)
    return Wiring(UNWIRED,
                  f"{plugincache.PLUGIN_ID} is installed at {scope} scope and reads as "
                  f"disabled in {where}", fix)


def _codex(p: profiles.Profile, cwd: Path, env: Mapping[str, str]) -> Wiring:
    """Codex: three marks in `$CODEX_HOME/config.toml`, and it needs all three (ruling 7).

    The plugin declares the hooks, the policy line is the only thing that can tell a Codex
    shell which harness it is, and **a hook Codex has not trusted is inert** — so a plugin
    nobody approved is installed and does nothing, which reads exactly like wired to
    anything that stops at the plugin table.

    The trust rule is the measured one, not the planned one. `trusted_hash` cannot be
    recomputed from the plugin's `hooks/hooks.json`: the command string, the hook object as
    JSON in three spellings, the whole matcher group and the joined commands were all tried
    against a real hash on 2026-09-12 and none matched. And Codex writes an entry per hook
    **lazily**, as each first fires — the operator's own wired home held 12 of the plugin's
    18 keys — so "an entry for every hook key" would call a wired machine unwired. What is
    left is honest and weaker, and `docs/harnesses.md` says so: charter's GUARD hook
    (:data:`CODEX_GUARD_HANDLER`, at the position the installed plugin gives it) was
    approved in this home at least once.

    The home is the one charter can see. One a wrapper script exports on its way to `codex`
    is invisible here, and the docs state that limit.
    """
    path = codex.config_path(env)
    where = _whole(path)
    fix = _install_fix(p)
    try:
        doc = tomllib.loads(path.read_text())
    except FileNotFoundError:
        doc = {}
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        return Wiring(UNKNOWN_STATE, f"{where} could not be read ({_whole(e)})", fix)
    guards = _codex_guard_keys(path.parent)
    if isinstance(guards, str):
        return Wiring(UNKNOWN_STATE, guards, fix)
    marks = _codex_marks(doc, guards)
    if isinstance(marks, str):
        return Wiring(UNKNOWN_STATE, CODEX_SHAPE.format(path=where, key=marks), fix)
    plugin, policy, trusted = marks
    missing = []
    if plugin.get("enabled") is not True:
        missing.append(f"{plugincache.PLUGIN_ID} is not an enabled plugin")
    if policy.get("CHARTER_HARNESS") != codex.NAME:
        missing.append('shell_environment_policy.set has no CHARTER_HARNESS = "codex"')
    if not guards:
        missing.append(f"no copy of {plugincache.PLUGIN_ID} under "
                       f"{_whole(path.parent / CODEX_PLUGIN_CACHE)} places charter's guard "
                       f"hook, so there is no guard to trust")
    elif not trusted:
        missing.append("no guard hook of charter's is trusted — approve them in a codex "
                       "session")
    if not missing:
        return Wiring(WIRED, f"{where}: plugin enabled, harness named, "
                             f"{len(trusted)} trusted guard hook(s)", "")
    if policy.get("CHARTER_HARNESS") == codex.NAME:
        # Charter's own half is already written, so what is left is Codex's own commands and
        # a trust prompt only a person can answer. Naming `charter harness install` here
        # would name the command that has already done everything it can — review 7's
        # objection is about a fix that changes nothing, and this is the same fix one mark
        # further on.
        steps = codex_steps(path.parent)
        fix = f"{'; '.join(steps[:-1])}; then {steps[-1]}"
    elif "shell_environment_policy" in doc:
        # `codex.install()` answers `present` for ANY `[shell_environment_policy]` table,
        # so `charter harness install` here would print a fix that changes nothing.
        fix = CODEX_POLICY_BY_HAND.format(path=where)
    return Wiring(UNWIRED, f"{where}: " + "; ".join(missing), fix)


def _codex_guard_keys(home: Path):
    """The trust-ledger keys that are charter's guard in *home* — or why charter could not
    read where the guard is.

    Read out of the INSTALLED plugin's `hooks/hooks.json`, because that file is what Codex
    numbers its `<event>:<group>:<hook>` keys against: charter's own `hooks.json` has moved
    groups between releases (0.42.0 had three `PreToolUse` groups, 0.60.0 has four), so a
    hard-coded index is right for one version and silently names the dispatch hook in
    another. A key is the guard when its hook runs :data:`CODEX_GUARD_HANDLER`.

    Every cached version must agree, and a key only one of them calls the guard is not one:
    Codex can keep an older copy beside the current one, and charter cannot tell which of
    them it numbered the ledger by — so the rule is the one that fails closed. No copy at
    all is an empty set, which reads as nothing to trust; a copy charter cannot read is an
    UNKNOWN, because it may be the one that places the guard.
    """
    marketplace = plugincache.PLUGIN_ID.split("@", 1)[-1]
    plugin = plugincache.PLUGIN_ID.split("@", 1)[0]
    root = home / CODEX_PLUGIN_CACHE / marketplace / plugin
    try:
        # No `sorted`: the copies are intersected, and an intersection has no order.
        versions = [d for d in root.iterdir() if d.is_dir()]
    except (FileNotFoundError, NotADirectoryError):
        return frozenset()
    except (OSError, ValueError) as e:
        return f"{_whole(root)} could not be read ({_whole(e)})"
    found = []
    for version in versions:
        f = version / "hooks" / "hooks.json"
        try:
            doc = json.loads(f.read_text())
        except FileNotFoundError:
            found.append(frozenset())
            continue
        except (OSError, UnicodeDecodeError, ValueError) as e:
            return f"{_whole(f)} could not be read ({_whole(e)})"
        found.append(_guard_positions(doc))
    return frozenset.intersection(*found) if found else frozenset()


def _guard_positions(doc) -> frozenset:
    """Every `<prefix><event>:<group>:<hook>` in a plugin `hooks.json` whose command runs
    :data:`CODEX_GUARD_HANDLER`. Codex spells the event in snake case (`PreToolUse` →
    `pre_tool_use`, measured on its ledger). Anything not in the file's documented shape
    places no guard."""
    from . import hooks

    events = doc.get("hooks") if isinstance(doc, dict) else None
    out = set()
    for event, groups in (events.items() if isinstance(events, dict) else ()):
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", str(event)).lower()
        for g, group in enumerate(groups if isinstance(groups, list) else ()):
            entries = group.get("hooks") if isinstance(group, dict) else None
            for h, hook in enumerate(entries if isinstance(entries, list) else ()):
                command = hook.get("command") if isinstance(hook, dict) else None
                if (isinstance(command, str)
                        and CODEX_GUARD_HANDLER in hooks._HOOK_CMD_RE.findall(command)):
                    out.add(f"{CODEX_TRUST_PREFIX}{snake}:{g}:{h}")
    return frozenset(out)


def _codex_marks(doc: dict, guards: frozenset):
    """``(plugin table, policy set, trusted guard keys)`` out of *doc* — or the dotted KEY
    that has a shape Codex never writes. A trusted key counts only if it is one of
    *guards*.

    Every level is checked for being a table before it is read, because each is a line a
    chat can write: `plugins."charter@charter" = true` parses, and so does a trust entry
    that is a string. Read without the check either one is an `AttributeError` in a
    launch; read with it, it is an UNKNOWN that says which key (A1).
    """
    def table(parent: dict, key: str, shown: str):
        got = parent.get(key, {})
        return got if isinstance(got, dict) else shown

    plugins = table(doc, "plugins", "plugins")
    if isinstance(plugins, str):
        return plugins
    plugin = table(plugins, plugincache.PLUGIN_ID, f'plugins."{plugincache.PLUGIN_ID}"')
    if isinstance(plugin, str):
        return plugin
    policy_table = table(doc, "shell_environment_policy", "shell_environment_policy")
    if isinstance(policy_table, str):
        return policy_table
    policy = table(policy_table, "set", "shell_environment_policy.set")
    if isinstance(policy, str):
        return policy
    hooks = table(doc, "hooks", "hooks")
    if isinstance(hooks, str):
        return hooks
    ledger = table(hooks, "state", "hooks.state")
    if isinstance(ledger, str):
        return ledger
    trusted = []
    for key, entry in ledger.items():
        # Only the guard's own entries are read. A prefix test used to stand here, and
        # membership in *guards* implies it — every guard key is built on the prefix — so it
        # was a second spelling of the same filter; another hook's entry, in any shape, says
        # nothing about the guard.
        if key not in guards:
            continue
        if not isinstance(entry, dict):
            return f'hooks.state."{_whole(key)}"'
        if isinstance(entry.get("trusted_hash"), str) and entry["trusted_hash"]:
            trusted.append(key)
    return plugin, policy, trusted


def codex_steps(home) -> list[str]:
    """:data:`CODEX_COMMANDS` with ``CODEX_HOME=`` in front of each, then
    :data:`CODEX_APPROVE`. One line per step, each one pasteable on its own.

    A list, so no caller has to split a sentence back into steps — a home whose name holds
    the separator would come apart in the wrong place (A11). Printed and never run: they
    install software into an account folder and end in a trust prompt only a person can
    answer, and charter's own consent rule is that running the command IS the consent.
    """
    prefix = f"CODEX_HOME={shlex.quote(str(home))}"
    return [_whole(f"{prefix} {shlex.join(argv)}") for argv in CODEX_COMMANDS] + [CODEX_APPROVE]


def _opencode(p: profiles.Profile, cwd: Path, env: Mapping[str, str]) -> Wiring:
    """opencode: `debug config`, and all three marks (ruling 26).

    The entry has to name charter's shim, the shim's bytes have to be charter's, **and no
    foreign plugin may share its realm**. The third is not tidiness. opencode imports the
    whole plugin directory into ONE module realm and hands every plugin the same globals:
    reproduced against 1.18.21 and the real shim, a byte-perfect `charter.ts` beside
    `plugin/aaa_boot.ts` containing ``Object.hasOwn = () => false`` turns every guard lookup
    into `undefined`, so a vault read routes to the Bash guard and is allowed — while
    `shim_is_charters` says True throughout (`opencode.foreign_plugins`, ADR 0015's
    amendment). Measured 2026-09-12: `debug config` lists the foreign file too.

    `unvouched()` is not the test either — it answers ``()`` when the shim is missing, so an
    entry naming a deleted file would read as wired.
    """
    home = opencode.global_dir(env)
    fix = _install_fix(p)
    argv = probe_argv(p)
    asked = _whole(shlex.join(argv))
    where = _whole(home)
    try:
        proc = util.run(argv, check=False, env=dict(env), timeout=plugincache.LIST_TIMEOUT)
    except (util.ProcTimeout, OSError) as e:
        return Wiring(UNKNOWN_STATE, f"{asked} did not answer ({_whole(e)})", fix)
    if proc.returncode != 0:
        return Wiring(UNKNOWN_STATE, f"{asked} exited {proc.returncode}", fix)
    try:
        doc = json.loads(proc.stdout)
    except (ValueError, TypeError):
        return Wiring(UNKNOWN_STATE, f"{asked} answered something that is not JSON", fix)
    entries = doc.get("plugin") if isinstance(doc, dict) else None
    if isinstance(entries, str):
        entries = [entries]
    want = _resolved(home / opencode.SHIM_PATH)
    named = any(_resolved(_unprefixed(e)) == want for e in (entries or [])
                if isinstance(e, str))
    if not named:
        return Wiring(UNWIRED, f"opencode loads no plugin from {where}", fix)
    if not opencode.shim_is_charters(home):
        return Wiring(UNWIRED, f"{where}/{opencode.SHIM_PATH} is not the file charter "
                               f"writes — charter cannot vouch for it", fix)
    foreign = opencode.foreign_plugins(home)
    if foreign:
        return Wiring(UNWIRED,
                      f"{where}/{opencode.PLUGIN_DIR} also holds "
                      f"{_whole(', '.join(foreign))}, which shares one module "
                      f"realm with charter's shim", "remove it, or move it out of "
                                                   f"{where}/{opencode.PLUGIN_DIR}")
    return Wiring(WIRED, f"opencode debug config: {opencode.SHIM_PATH} under {where}, and "
                         f"nothing else in its realm", "")


def _unprefixed(entry: str) -> str:
    """A `plugin` entry as a path. Measured: opencode answers `file:///…` and keeps the
    un-resolved spelling, so both halves of the comparison are resolved below."""
    return entry[len("file://"):] if entry.startswith("file://") else entry


def _resolved(p) -> str:
    try:
        return str(Path(p).resolve())
    except (OSError, RuntimeError, ValueError):
        return str(p)


# --------------------------------------------------------------------------- #
# The cache — the selector's rows, and never a launch                          #
# --------------------------------------------------------------------------- #


def _key(p: profiles.Profile, cwd) -> str:
    """What makes this the same question as the one that was asked: the profile as the
    operator approved it (`profiletrust.fingerprint` — its NAME rides beside it, because the
    record is keyed by name and this is not), and the directory it was asked about."""
    from . import profiletrust

    return hashlib.sha256(json.dumps(
        {**profiletrust.fingerprint(p), "name": p.name, "cwd": str(cwd)},
        sort_keys=True).encode()).hexdigest()


def _claude_stamps(env: Mapping[str, str], cwd: Path) -> list[Path]:
    """The config folder's two files, and every settings file that can reach *cwd*.

    **Every directory from *cwd* up to the plane root, inclusive** (A6). Measured on claude
    2.1.270 (2026-09-13): in a git plane, a disable in the ROOT's `settings.local.json`
    reads as disabled in `workspaces/<ws>/` below it — so a stamp of the chat's own
    directory alone would keep answering `wired` after the plane root changed. Stamping a
    file that turns out not to reach is only a spurious miss; missing one that does is a
    display that stays green.
    """
    folder = claude_code.config_home(env)
    return [folder / "plugins" / "installed_plugins.json", folder / "settings.json",
            *(d / ".claude" / name for d in _up_to_the_plane(cwd)
              for name in ("settings.json", "settings.local.json"))]


def _up_to_the_plane(cwd: Path) -> list[Path]:
    """*cwd*, then each parent up to and including `config.ROOT` — or *cwd* alone when it is
    not inside the plane. Resolved, because `os.getcwd()` answers `/private/var/…` for a
    plane `config.ROOT` spells `/var/…` on macOS.

    One filter and no "outside the plane" branch: a parent is kept only when it IS the root
    or lies below it, and no parent of a directory outside the plane — its own parent
    included — is either. The branch that used to say so first answered the same list for
    every input, and the sweep was right that nothing could tell it from its absence."""
    try:
        here, root = Path(os.path.realpath(cwd)), Path(os.path.realpath(config.ROOT))
    except ValueError:
        return [Path(cwd)]
    return [here, *(d for d in here.parents if d == root or root in d.parents)]


def _codex_stamps(env: Mapping[str, str], cwd: Path) -> list[Path]:
    """The config file, and the plugin cache directory whose versions place the guard."""
    home = codex.config_path(env).parent
    marketplace = plugincache.PLUGIN_ID.split("@", 1)[-1]
    plugin = plugincache.PLUGIN_ID.split("@", 1)[0]
    return [codex.config_path(env), home / CODEX_PLUGIN_CACHE / marketplace / plugin]


def _opencode_stamps(env: Mapping[str, str], cwd: Path) -> list[Path]:
    home = opencode.global_dir(env)
    return [home / opencode.PLUGIN_DIR, home / opencode.SHIM_PATH, home / "opencode.json"]


def _stamp(p: profiles.Profile, cwd) -> dict:
    """``{path: [mtime_ns, size] | None}`` for the files whose change accompanied every flip
    of this kind's answer (D2). `.claude.json` is deliberately absent: the probe itself
    writes it, so stamping it would invalidate the entry the probe just wrote."""
    kind = _KINDS.get(p.harness)
    out = {}
    for path in ([] if kind is None else kind.stamped(environment(p), Path(cwd))):
        try:
            st = path.stat()
            out[str(path)] = [st.st_mtime_ns, st.st_size]
        except (OSError, ValueError):
            # Absent is a state like any other: a shim that appears has to be a miss.
            out[str(path)] = None
    return out


def _read_cache() -> dict:
    try:
        doc = json.loads((Path(config.STATE_DIR) / CACHE).read_text())
    except (OSError, UnicodeDecodeError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def cached(p: profiles.Profile, *, cwd) -> Wiring | None:
    """A remembered answer whose stamp still matches, or ``None``. **Display only.**

    The profile selector draws its rows from it and probes on a miss
    (`frame/selector.states`), and picking a row probes again. A launch never reads it (ruling 21):
    this file is as writable by a chat as `charter.local.toml` is, and a chat can compute
    the key, write the stamp and date the entry ahead — which is why the age test has two
    bounds, and why every field is checked for its type before it is believed (A1).
    """
    entry = _read_cache().get(_key(p, cwd))
    if not isinstance(entry, dict):
        return None
    at = entry.get("checked_at")
    if isinstance(at, bool) or not isinstance(at, (int, float)):
        return None
    if not 0 <= time.time() - at < MAX_AGE:
        return None
    if entry.get("stamp") != _stamp(p, cwd):
        return None
    got = [entry.get(field) for field in ("state", "detail", "fix")]
    if got[0] not in (WIRED, UNWIRED, UNKNOWN_STATE) or not all(isinstance(g, str)
                                                                  for g in got):
        return None
    return Wiring(*got)


def remember(p: profiles.Profile, *, cwd, w: Wiring) -> None:
    """Record *w* for *p* at *cwd*. Best effort: a display cache is never worth a row.

    The profile selector calls this on the miss it probes (`frame/selector.states`), and
    `doctor` deliberately does not (a suite reaching `run_all()` would write the cache).

    **Only a definite answer is kept.** An UNKNOWN is a fact about one probe — a
    `plugincache.LIST_TIMEOUT`, an answer that would not parse — and not about the folder: remembered,
    it would refuse the selector's row for all of :data:`MAX_AGE`, and Enter on a refused
    row never reaches the launch's fresh probe. So a row whose last probe could not tell is
    asked again on the next draw.
    """
    if w.state not in (WIRED, UNWIRED):
        return
    doc = _read_cache()
    doc[_key(p, cwd)] = {"state": w.state, "detail": w.detail, "fix": w.fix,
                         "checked_at": time.time(), "stamp": _stamp(p, cwd)}
    path = Path(config.STATE_DIR) / CACHE
    try:
        config.private_mkdir(path.parent)
        config.write_for(path, json.dumps(doc, indent=2) + "\n")
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Installing                                                                   #
# --------------------------------------------------------------------------- #


def install(p: profiles.Profile, root: Path) -> list[tuple[str, str]]:
    """Wire *p*'s kind under *p*'s own environment. ``(status, label)`` pairs, `Harness.wire`'s
    shape with every label contained — or one ``("refused", why)`` when charter may not act
    for *p* at all.

    The gate is :func:`detect`'s, and it is here for detect's reason: an install runs the
    profile's own command (`claude plugin install`) or writes into the folder its `env`
    names, and a file git would commit is never acted on.

    Codex is the one that cannot be finished from here, and that is a fact about Codex
    rather than a gap: charter writes the `shell_environment_policy` line — the one thing
    the plugin cannot write, because it is what tells a Codex shell which harness it is —
    and the plugin install and the hook approval are Codex's own commands, which the
    unwired answer after it names with `CODEX_HOME=` in front.
    """
    why, _fix = _not_asked(p)
    if why:
        return [("refused", why)]
    return _wire(p, root)


def _wire(p: profiles.Profile, root: Path) -> list[tuple[str, str]]:
    """:func:`install` past its gate: the kind's own wire, and nothing that raises. The
    one thing a launch that found a definite UNWIRED runs (:func:`wired_or_refusal`), so
    `charter harness install` and the launch cannot install two different ways."""
    kind = _KINDS.get(p.harness)
    if kind is None:
        return [("unavailable", f"charter has no wiring for {_whole(p.kind)}")]
    try:
        # Contained HERE, once, for every caller: a label is a path built out of the
        # profile's own `env` — a file a chat can write — and both `harness install` and
        # `init` print it to a terminal (ruling 35).
        return [(status, _whole(label)) for status, label in kind.wire(p, root, environment(p))]
    except ValueError as e:
        return [("failed", f"charter could not wire under this profile's environment "
                           f"({_whole(e)})")]


@contextlib.contextmanager
def _serialised(p: profiles.Profile):
    """One launch installs into *p*'s folder at a time.

    Measured 2026-09-15 (claude 2.1.272, two `marketplace add` + `plugin install` sequences
    at once into one empty `CLAUDE_CONFIG_DIR`): both exited 0, one installed and the other
    answered "already installed", and both manifests parsed with one entry — a clean sample,
    and one sample. The lock is what makes it the rule: a second launch of the same unwired
    profile waits here, and its own install then finds the first one's work in place
    (:data:`WIRED_FOUND`) instead of racing a clone of 7-18 seconds into the same folder.

    `flock`, under `.charter/`, keyed by the profile as approved — two launches of one
    profile on one plane share it; closing the file releases it. **Best effort**, like the
    cache beside it: a state directory charter cannot write is a launch that installs
    unserialised, not one that refuses over a lock file.
    """
    import fcntl
    from . import profiletrust

    digest = hashlib.sha256(json.dumps({**profiletrust.fingerprint(p), "name": p.name},
                                       sort_keys=True).encode()).hexdigest()[:16]
    lock = Path(config.STATE_DIR) / "locks" / f"harness-wiring-{digest}.lock"
    with contextlib.ExitStack() as stack:
        with contextlib.suppress(OSError):
            config.private_mkdir(lock.parent)
            fcntl.flock(stack.enter_context(config.open_for(lock, "w")), fcntl.LOCK_EX)
        yield


def _claude_wire(p: profiles.Profile, root: Path, env: dict) -> list[tuple[str, str]]:
    return [plugincache.install(root, env=env, command=profiles.expanded_command(p))]


def _codex_wire(p: profiles.Profile, root: Path, env: dict) -> list[tuple[str, str]]:
    return [codex.install(env=env)]


def _opencode_wire(p: profiles.Profile, root: Path, env: dict) -> list[tuple[str, str]]:
    return opencode.OpenCodeHarness().wire(root, env=env)


# What each kind's wire puts where — the object of "installed …" in the launch's one line,
# of "Enter installs …" on a selector row and of `doctor`'s hint. Each folder is contained:
# it is built out of the profile's own `env` (ruling 35).


def _claude_installs(env: Mapping[str, str]) -> str:
    return f"{plugincache.PLUGIN_ID} into {_whole(claude_code.config_home(env))}"


def _codex_installs(env: Mapping[str, str]) -> str:
    return (f"charter's line (CHARTER_HARNESS = \"{codex.NAME}\") into "
            f"{_whole(codex.config_path(env))}")


def _opencode_installs(env: Mapping[str, str]) -> str:
    return f"charter's shim {opencode.SHIM_PATH} into {_whole(opencode.global_dir(env))}"


class _Kind(NamedTuple):
    """Everything this module knows about one harness kind, in one row (C: one table in
    place of four `p.harness ==` ladders, which had to agree and were free not to)."""

    #: The words after the profile's command that ask; ``()`` when the answer is a file.
    probe: tuple[str, ...]
    #: ``(profile, cwd, env) -> Wiring``.
    ask: Callable[[profiles.Profile, Path, Mapping[str, str]], Wiring]
    #: ``(env, cwd) -> paths`` whose change can flip the answer.
    stamped: Callable[[Mapping[str, str], Path], list[Path]]
    #: ``(profile, root, env) -> (status, label) pairs``.
    wire: Callable[[profiles.Profile, Path, dict], list[tuple[str, str]]]
    #: ``env -> "what into where"``: what :attr:`wire` puts in the folder *env* names.
    installs: Callable[[Mapping[str, str]], str]
    #: Can :attr:`wire` finish on its own, so that a launch wires rather than refuses
    #: (ruling 47)? False for Codex: its hook trust is granted only inside a Codex session,
    #: so charter writes its part and the launch still stops with Codex's own steps.
    automatic: bool


_KINDS: dict[str, _Kind] = {
    claude_code.NAME: _Kind(("plugin", "list", "--json"), _claude, _claude_stamps,
                            _claude_wire, _claude_installs, True),
    codex.NAME: _Kind((), _codex, _codex_stamps, _codex_wire, _codex_installs, False),
    opencode.NAME: _Kind(("debug", "config"), _opencode, _opencode_stamps, _opencode_wire,
                         _opencode_installs, True),
}


def listed() -> list[profiles.Profile]:
    """Every profile a selector would show, in the order `charter harness list` shows them.

    Declared profiles always — one whose command is not installed is still a row, because it
    is still somebody's declaration and `doctor` is where they find out; a built-in only
    when its program is installed, because a row about a harness this machine does not have
    is a row nobody can act on. One reader, so `doctor.check_names` and
    `doctor.check_profile_wiring` cannot disagree about how many rows there are — the pin
    `_FIXED_CHECK_NAMES` already keeps for every other check.
    """
    read = profiles.current()
    order = list(profiles.builtins())
    rows = [p for p in read.profiles.values()
            if p.source != profiles.BUILTIN
            or shutil.which(profiles.expanded_command(p)[0]) is not None]
    return sorted(rows, key=lambda p: (p.name not in order,
                                       order.index(p.name) if p.name in order else 0,
                                       p.name))
