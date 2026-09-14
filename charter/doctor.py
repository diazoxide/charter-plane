"""Environment preflight checks for a control plane (``charter doctor``).

Read-only: verifies the tools and auth a developer needs *before* they try to
discover or clone, and prints exact remediation steps for anything missing.
Nothing here changes the system.
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import os
import platform
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from . import contain, gitstate, inventory, tui, util
from .forge.gitlab import GitLabForge

OK, WARN, FAIL = "ok", "warn", "fail"

_SYMBOL = {OK: ("32", "✓"), WARN: ("33", "!"), FAIL: ("31", "✗")}


def _color() -> bool:
    return sys.stdout.isatty()


@dataclass
class Result:
    name: str
    status: str
    detail: str = ""
    hint: str = ""

    def render(self, name_w: int = 0) -> str:
        """One preflight row. *name_w* is the NAME column's width for the whole table.

        ``{self.name:<16}`` was the constant #600 names, and it is a guess about content
        in a report where three checks (`credential paths`, `workspace clones`,
        `plane-root guard`) already sit exactly on it — so the next check named one
        character longer pushes its detail right of every other row's and the column stops
        being a column. `cmd_doctor` states the width from :func:`name_width`, which asks
        the checks rather than guessing.

        **The width is a floor, never a cap.** `tui.pad` truncates, and a check name cut
        in half is a failure the reader cannot go and look up (#589's readability probe is
        the whole reason that distinction is written down). So a name wider than the
        stated column pushes its own row instead — loud, and in the direction that keeps
        the value readable — and :func:`name_width` plus its pin is what stops that from
        being how the table normally renders.

        A row rendered with no width stated is as wide as itself, which is what a single
        `Result` printed on its own should be.

        **A hint is a remedy, so a green row has none and does not print one.** ``→`` in
        this table means *do this*; there is nothing to do about a check that passed, and a
        column of green arrows is how the yellow ones stop being read. A fact a passing row
        still needs to state goes in :attr:`detail`, on a ``↳`` continuation line — the
        shape `check_harness` uses for its capability ceilings.

        That rule is only safe while it is loud, and for one release it was not:
        `check_frame` passed a note as a hint on the OK path and it was silently discarded
        on every healthy machine (#856). That particular note said a frame was blanking
        Claude Code's footer and went with the footer in #895, but the rule it cost is the
        one that matters: `TestAGreenRowKeepsNothingBack` holds every check to it, so the
        next row to try this fails the suite rather than losing a sentence.
        """
        code, glyph = _SYMBOL[self.status]
        if _color():
            glyph = f"\033[{code}m{glyph}\033[0m"
        line = f"  {glyph}  {tui.pad(self.name, max(name_w, tui.column('', [self.name])))}" \
               f"{self.detail}".rstrip()
        if self.hint and self.status != OK:
            line += f"\n        → {self.hint}"
        return line


#: Why a check that could not RUN is a warning rather than a tick (#171).
#:
#: "not checked" is the absence of information, not evidence of health — and a green glyph
#: over it is read as the latter by anyone scanning the column, which is how the whole class
#: this audit came from works. Two of these sites already carried the comment "a check that
#: silently does nothing is worse than no check" and then returned OK anyway; the principle
#: was right and the status contradicted it.
#:
#: WARN, never FAIL: `cmd_doctor` exits non-zero only on FAIL, and an unreadable tree or a
#: git that timed out is not "you cannot work" — it is "charter cannot tell you either way".
_NOT_CHECKED_HINT = ("This check could not run, so its silence means nothing. Re-run "
                     "`charter doctor` — if it persists, the reason above is the thing to fix.")


def _beside_unread(result: Result, unread) -> Result:
    """*result*, saying beside its verdict every path the row could not check, with what clears
    each (ADR 0009) — and never OK while one stands.

    Beside and not instead: the verdict is still true of what was read (#1014). One spelling for
    every row that lists workspaces (#1043), so a path one row names is named the same in the
    next. *unread* is ``(path, errno)`` pairs, each path inside the plane."""
    from . import config as _config
    from . import workspace as _workspace
    if not unread:
        return result
    named = [p.relative_to(_config.ROOT).as_posix() for p, _ in unread]
    # `workspace.cannot_check`, the clause a command prints as a sentence (#1084), so the two
    # cannot drift apart.
    cannot = "; ".join(_workspace.cannot_check(p, code) for p, code in unread) + "."
    return Result(result.name, WARN if result.status == OK else result.status,
                  detail=f"{result.detail}; {', '.join(named)} cannot be checked",
                  hint=f"{result.hint}   {cannot}" if result.hint else cannot)


def _first_line(text: str) -> str:
    text = (text or "").strip()
    return text.splitlines()[0] if text else ""


#: Kept in sync with `requires-python` in pyproject.toml — a test pins the two together.
MIN_PYTHON = (3, 11)


def check_python() -> Result:
    ok = sys.version_info >= MIN_PYTHON
    return Result(
        "python3",
        OK if ok else FAIL,
        detail=platform.python_version(),
        hint="" if ok else f"Python {'.'.join(map(str, MIN_PYTHON))}+ is required.",
    )


def check_git() -> Result:
    if not shutil.which("git"):
        return Result("git", FAIL, hint="Install git: xcode-select --install (macOS) or brew install git.")
    return Result("git", OK, detail=_first_line(util.run(["git", "--version"], check=False).stdout))


def check_git_identity() -> Result:
    """A commit needs a resolvable identity. ``commit_push`` (behind reactive memory,
    workspace snapshots, and `charter save`) shells out to git with ``check=False`` and
    swallows a failed commit — it's called from hooks/background paths that must never
    break a turn — so a machine with no ``user.name``/``user.email`` configured would
    silently lose memories/notes/dispatch tallies with nothing said about it. This check
    is that missing visibility, not a new failure mode."""
    name = _first_line(util.run(["git", "config", "--get", "user.name"], check=False).stdout)
    email = _first_line(util.run(["git", "config", "--get", "user.email"], check=False).stdout)
    if name and email:
        return Result("git identity", OK, detail=f"{name} <{email}>")
    missing = ", ".join(k for k, v in (("user.name", name), ("user.email", email)) if not v)
    return Result(
        "git identity",
        FAIL,
        detail=f"not set: {missing}",
        hint='Run: git config --global user.email "you@example.com" && '
             'git config --global user.name "Your Name"  — otherwise a commit (memory, '
             "workspace notes, dispatch tallies) silently never happens.",
    )


#: Per-CLI install hint — used when the control plane declares (or defaults to) a
#: forge whose CLI isn't installed. Keyed by `Forge.cli`, so a new forge kind only
#: needs an entry here, not a new check function.
_INSTALL_HINT = {
    "glab": "brew install glab  (see https://gitlab.com/gitlab-org/cli)",
    "gh": "brew install gh  (see https://cli.github.com/)",
}


def declared_or_default_forges() -> list:
    """The forges THIS control plane actually declares (`[[forge]]` blocks in its own
    ``charter.toml``, re-read fresh against the CURRENT ``config.ROOT`` — same
    discipline as ``commands._instance_load_root``, so a test that redirects
    ``config.ROOT`` after import sees what IT declared, not the real process's stale
    module-level config), de-duplicated by ``(kind, host)``.

    Falls back to a single default :class:`GitLabForge` when none are declared — the
    shape every control plane had before multi-forge support existed, and still what a
    fresh `charter init` (or a legacy single-forge control plane) produces. Before this
    (FINDING I3), `check_forge_cli`/`check_forge_auth` hardcoded `GitLabForge()`
    unconditionally, so a GitHub-only control plane got a `glab` FAIL — a real tool,
    just the wrong one, with a fix (`brew install glab`) that does nothing for a
    control plane that never touches GitLab at all.

    Never raises: a malformed `[[forge]]` block is a config mistake `doctor`'s own
    `check_control_plane_config` already surfaces separately — this just skips it
    rather than taking preflight down.

    Thin wrapper over `forge.registry.declared_or_default` — the same resolution a
    generated persona sub-agent's wording now uses (`commands_persona._render_agent`),
    so `doctor`'s forge checks and a sub-agent's prose can never drift apart on what
    this control plane's forge set actually is."""
    from . import config as _config
    from .forge import registry
    return registry.declared_or_default(_config.ROOT)


def check_forge_cli(forge=None) -> Result:
    forge = forge or GitLabForge()
    cli = forge.cli
    if not shutil.which(cli):
        hint = _INSTALL_HINT.get(cli, f"Install {cli}.")
        return Result(cli, FAIL, hint=f"Install {cli}: {hint}.")
    return Result(cli, OK, detail=_first_line(util.run([cli, "--version"], check=False).stdout))


def check_forge_auth(forge=None) -> Result:
    forge = forge or GitLabForge()
    cli = forge.cli
    if not shutil.which(cli):
        return Result(f"{cli} auth", FAIL, hint=f"Install {cli} first, then run: {cli} auth login.")
    try:
        proc = util.run([cli, "auth", "status", "--hostname", forge.host], check=False,
                        timeout=CHECK_TIMEOUT)
    except util.ProcTimeout as e:
        return Result(f"{cli} auth", WARN, detail=f"timed out after {e.seconds:g}s",
                      hint=f"`{cli} auth status` did not answer — the forge may be "
                           f"unreachable, or a credential helper is waiting on input.")
    blob = (proc.stdout or "") + (proc.stderr or "")
    if "Logged in" in blob:
        summary = next(
            (ln.strip() for ln in blob.splitlines() if "Logged in" in ln),
            "authenticated",
        )
        return Result(f"{cli} auth", OK, detail=summary)
    return Result(
        f"{cli} auth",
        FAIL,
        detail=_first_line(blob),
        hint=f"Run: {cli} auth login  (pick {forge.host}; choose TOKEN/HTTPS — charter "
             "never uses SSH for git).",
    )


def check_ssh() -> Result:
    """Golden rule 0: **one credential — per forge** — each repo's OWN forge's token over
    HTTPS (glab for GitLab, gh for GitHub, …). SSH is deliberately NOT used, so this no
    longer probes for a key (that was a contradictory hard requirement). Instead it
    verifies every repo in scope carries ITS forge's token-only git policy
    (`gitpolicy.forge_for` resolves which forge per repo)."""
    from . import config as _config, gitpolicy, workspace as _workspace
    scope, unseen = gitpolicy.scan(_config.ROOT, _config.WORKSPACES_DIR)
    drift = {r: gitpolicy.check(r) for r in scope}
    bad = {r: d for r, d in drift.items() if d}
    # A directory under `workspaces/` charter cannot look into (ADR 0009, #942 final review):
    # whether it is a clone cannot be told, so it is named with what clears it — never raised out
    # of doctor, as it was on 3.11–3.13, and never left out of the count without a word.
    # Worded for the cause the check actually met (#942 closing verification): restoring read
    # access does nothing for a symlink loop.
    #
    # `workspaces/` itself is among them when it could not be listed (#987), and is named as
    # itself: `<parent>/<name>` is how a clone reads, and for this directory it put the plane's
    # own folder name in front. It is then the only entry — nothing under it was reached.
    listing = Path(_config.WORKSPACES_DIR)

    def named(p: Path) -> str:
        return f"{p.name}/" if p == listing else f"{p.parent.name}/{p.name}"

    cannot = ("   " + "; ".join(
        f"{named(p)} cannot be checked — {_workspace.uncheckable_fix(code, p)}"
        for p, code in unseen) + "." if unseen else "")
    if not bad:
        if unseen:
            what = (named(listing) if [p for p, _ in unseen] == [listing]
                    else f"{len(unseen)} director(ies) under workspaces/")
            return Result("git auth", WARN,
                          detail=f"token-only across {len(scope)} repo(s); {what} cannot be "
                                 f"checked",
                          hint=cannot.lstrip())
        return Result("git auth", OK,
                      detail=f"token-only across {len(scope)} repo(s) (each forge's own "
                             f"HTTPS token; no SSH/signing)")
    # `charter git-policy --apply` deliberately no-ops for an UNMANAGED-forge repo (no
    # host to resolve a policy for) — telling a developer to run it for exactly THAT
    # repo is a permanently un-actionable hint. Split the two failure modes so the hint
    # stays honest either way.
    unmanaged = [r for r, d in bad.items() if d == [gitpolicy.UNMANAGED_FORGE]]
    fixable = [r for r in bad if r not in unmanaged]
    names = ", ".join(r.name for r in list(bad)[:3]) + (" …" if len(bad) > 3 else "")
    if unmanaged and not fixable:
        hint = (f"{len(unmanaged)} repo(s) have an unrecognised forge — `charter "
                f"git-policy --apply` deliberately no-ops for these (there's no policy to "
                f"apply for a host it can't identify). Declare the host under [[forge]] in "
                f"charter.toml to bring them under management, then re-run.")
    elif fixable and not unmanaged:
        hint = "Apply the single-credential policy to every clone: charter git-policy --apply"
    else:
        hint = (f"charter git-policy --apply fixes {len(fixable)} drifted repo(s); "
                f"{len(unmanaged)} more have an unrecognised forge and need a [[forge]] "
                f"declaration in charter.toml first — --apply alone won't touch those.")
    return Result(
        "git auth",
        WARN,
        detail=f"{len(bad)}/{len(scope)} repo(s) not token-only: {names}",
        hint=hint + cannot,
    )


def check_control_plane_config() -> Result:
    """``charter.toml`` failed to parse (malformed TOML, or a format version this charter
    cannot place). ``config`` swallows the exception so the CLI stays usable (see
    ``config.CONFIG_ERROR``); this is where a user would look to find out why.

    **The hint differs by which failure it was**, because only one of them is survivable.
    Malformed TOML is a file the operator edits, and charter carries on with empty defaults
    while this row names it. A plane declaring a format version from the future is not
    survivable and charter does not carry on at all (`config.PLANE_REFUSAL`, `cli.main`) —
    promising a fallback there would describe behaviour that no longer exists. The
    ``schema`` row carries the detail; this one must simply stop lying about what happens
    next.

    A DIFFERENT, narrower failure lives one level down: the file parses fine but one
    ``[[forge]]`` block doesn't (a typo'd ``kind``, a missing field). ``registry.
    known_forges`` already keeps every host that DID resolve (a bad block no longer
    discards its good siblings — see ``charter/forge/registry.py``), but that recovery
    must not go silent: this is where it's surfaced, so a developer actually finds out a
    declared host isn't covered instead of the guard just quietly covering less."""
    from . import config as _config
    from .forge import registry

    if _config.CONFIG_ERROR is not None:
        return Result(
            "charter.toml",
            FAIL,
            detail=_first_line(_config.CONFIG_ERROR),
            hint=("charter refuses to operate on this plane at all — see the `schema` row. "
                  "`charter update`, then re-run.") if _config.PLANE_REFUSAL else
                 ("Fix or remove charter.toml, then re-run. Falling back to empty "
                  "group/exclude/workspace defaults until it does."),
        )
    # A committed `[plane] worktrees` that points outside the plane is IGNORED rather than
    # honoured (`config.worktrees_root_for`, #339) — and a setting silently ignored is a
    # plane whose declared layout is not the layout it has. This is the only place that
    # can say so; the resolver itself runs inside `derive`, where there is nobody to tell.
    from . import contain, instance as _instance
    # Parsed ONCE, for both of the silently-ignored-key rows below. `CONFIG_ERROR` is None
    # by the branch above, so this normally cannot raise — but `doctor` is the command
    # somebody runs when charter is already misbehaving, and a row that raises reports on
    # nothing at all.
    try:
        _cfg = _instance.load(_config.ROOT)
    except Exception:
        _cfg = {}
    why = contain.plane_adjacent_refusal(_config.ROOT, _instance.worktrees_of(_cfg))
    if why:
        return Result(
            "charter.toml",
            WARN,
            detail="[plane] worktrees points outside the plane and is being ignored",
            hint=f"{why}. Worktrees are in the default layout "
                 f"(workspaces/<ws>/.worktrees/) until the key is fixed or removed; "
                 f"$CHARTER_WORKTREES sets a per-machine root without editing the file.",
        )
    _forges, forge_errors = registry.known_forges_report(_config.ROOT)
    if forge_errors:
        shown = "; ".join(forge_errors[:3]) + (" …" if len(forge_errors) > 3 else "")
        return Result(
            "charter.toml",
            WARN,
            detail=f"{len(forge_errors)} [[forge]] block(s) failed to resolve",
            hint=f"{shown} — those hosts are NOT covered by the one-credential guard or "
                 f"git-policy until fixed (other declared/default hosts still are).",
        )
    # A committed `[harness] default` naming something charter cannot launch degrades to no
    # default at all (`instance.harness_of`) — and that renders as argparse's usage message,
    # which is exactly what a plane declaring nothing gets. So bare `charter` on a plane with
    # a typo behaves as though the key were absent, the same silently-ignored-setting shape
    # the `[plane] worktrees` branch above is about.
    #
    # **And since the profile selector this is the ONLY reader that says so** (ruling 18).
    # The bare launch used to refuse over the value; it now opens the selector, which lists
    # what this machine actually has and marks no row — because taking a launch away over a
    # name is worse than showing the list the name is missing from, and because a cursor on
    # nothing would leave Enter with nothing to do. That moves the whole of the reporting
    # here, to the command an operator runs when something reads as absent.
    #
    # Read from `instance.load` rather than `config.HARNESS`, the way the worktrees branch
    # reads `instance.worktrees_of`: this row is about the FILE, and `derive` already ran
    # before anybody could have fixed it.
    # **A profile is a name this key may hold** (ruling 43, and the spec's *`default` only
    # preselects*). `instance.harness_of` compares the value against the launchable KINDS
    # alone — `config.derive` reads nothing from `charter.local.toml`, so it cannot know the
    # profiles — and a `default` naming a declared profile therefore arrives here as
    # "refused" when it is nothing of the kind. `profiles.current()` is the one reader that
    # knows, memoised per process and already paid for by the `harness profiles` row above.
    from . import profiles as _profiles

    _refused = _instance.harness_of(_cfg).get("refused")
    if _refused and _refused not in _profiles.current().profiles:
        return Result(
            "charter.toml",
            WARN,
            detail=f'[harness] default = "{_refused}" is not a harness charter can launch',
            hint=f"Bare `charter`'s profile selector marks no row for it and opens on the "
                 f"first one that can run — which is also what a plane that declares no "
                 f"default gets, so the key currently reads as absent. Name one of: "
                 f"{', '.join(_instance.launchable_harnesses())}, or any profile "
                 f"charter.local.toml declares. `charter <profile>` is unaffected.",
        )
    # A committed `[[frame.component]]` arrangement charter cannot draw is refused WHOLE
    # (`instance.component_arrangement`, #535) and degrades to the frame `[frame] slots`
    # describes — which is byte-identical to the frame a plane that wrote no arrangement
    # gets. So the third silently-ignored setting in a row, and here for the two above's
    # reason: `docs/frame.md` told the operator they would "see your whole arrangement not
    # take effect", and there was nothing to see (#738). The launch itself deliberately
    # prints nothing — `commands_frame.frame_ready`'s docstring measures why a warning 86
    # bytes before tmux's alternate screen is worse than silence — so this row and
    # `charter frame-probe` are the whole surface.
    #
    # Read from `instance.frame_of` on the file parsed above, not from `config.FRAME`,
    # which is the `[harness] default` branch's rule for its reason: this row is about the
    # FILE. Reached only on a plane that actually wrote the key — the resolver answers
    # `None` for every other one, which is every plane charter ships with — so no correct
    # configuration can put this row in the yellow (#371's rule: a guard that fires on
    # working setups gets switched off and then protects nothing).
    _no_arrangement = _instance.frame_of(_cfg).get("components_refused")
    if _no_arrangement:
        return Result(
            "charter.toml",
            WARN,
            detail="[[frame.component]] is refused; the frame is drawing `[frame] slots`",
            hint=_instance.refused_arrangement_message(_no_arrangement),
        )
    if not _config.HAS_CONTROL_PLANE:
        # NOT ok. Every check below reports green against a plane that does not exist —
        # `personas: none defined`, `vaults: none configured` — so a session with no
        # personas, no vault and memory written into a scratch directory reads as a
        # healthy one. This row is the only place that can say otherwise, and saying it
        # in the OK column is what made the worktree failure invisible.
        return Result("charter.toml", WARN, detail=f"no control plane found (cwd: {_config.ROOT})",
                      hint="`charter init` here, or cd into a plane, or set $CHARTER_ROOT. "
                           "Every check below is reporting on a plane that does not exist.")
    # Name the plane unconditionally. Nothing else printed WHICH plane is bound, so a
    # stale $CHARTER_ROOT, a nested plane and a rootless cwd all looked identical to a
    # correct setup.
    return Result("charter.toml", OK, detail=f"parsed cleanly ({_config.ROOT})")


def check_control_plane_schema() -> Result:
    """Structural drift, from ``charter.instance.drift``: baseline top-level directories
    (personas/, inventory/, workspaces/) a control plane is expected to have. This is
    the *detect* half of the same stamp/detect/heal pattern ``workspace reinit`` already
    proves for a single workspace's layout — lifted one level up to the whole control
    plane, healed by ``charter reinit`` — surfaced here so a stale control plane is
    visible without running ``reinit`` first.

    **And, first, the refusal.** This row is named after the number, so it is where anyone
    who has just read a refused command looks next. Until #913 it reported ``up to date
    (schema 1)`` over a plane declaring schema 99 — ``drift`` only counts directories, and
    a plane from the future has all three — so the one row that could have named the
    declared version said the opposite of the truth. FAIL rather than WARN because every
    other command now stops outright: a row scoring a hard stop as a warning is a row
    disagreeing with the tool it reports on."""
    from . import config as _config, instance as _instance

    if not _config.HAS_CONTROL_PLANE:
        return Result("schema", OK, detail="no control plane found")
    if _config.PLANE_REFUSAL:
        return Result(
            "schema",
            FAIL,
            detail=_first_line(_config.PLANE_REFUSAL),
            hint="charter refuses to operate on a plane whose format version it cannot "
                 "place, rather than guess at a layout it has been told it does not "
                 "understand. `charter update` is the way out; every other command "
                 "declines until it runs.",
        )
    found = _instance.drift(_config.ROOT)
    if not found:
        return Result("schema", OK, detail=f"up to date (schema {_instance.SCHEMA})")
    return Result(
        "schema",
        WARN,
        detail=f"{len(found)} issue(s): " + "; ".join(found),
        hint="Run: charter reinit  (creates what's missing; never touches existing content).",
    )


def _git_in(root: Path, *args: str):
    """One read-only git question about ``root``, never raising on a non-zero exit.

    Timed out like every other check: the plane root is normally a small local repo, but
    a plane on a stalled network mount makes `git status` hang, and the SessionStart hook
    has a budget — a check that eats it prints nothing at all (see `CHECK_TIMEOUT`)."""
    return util.run(["git", "-C", str(root), *args], check=False, timeout=CHECK_TIMEOUT)


def _plane_default_branch(root: Path) -> str | None:
    """This repo's default branch, or ``None`` when charter cannot honestly say.

    Asked in order of decreasing authority:

    1. ``refs/remotes/origin/HEAD`` — the *remote's own* answer, recorded by `git clone`.
       It is the only source that is a fact rather than a guess, so it is consulted
       first: a plane whose default is `trunk` can easily still carry a stale local
       `main`, and guessing before asking would warn about the correct branch.
    2. A local ``main`` or ``master``, in that order. Needed because a plane is very often
       `git init`-ed and then given a remote by hand (`charter init` does not clone), and
       that never writes ``origin/HEAD`` — without this fallback the branch half of the
       check would be silent on most real planes.

    ``None`` when neither answers, and the caller must then say nothing about branches.
    Naming a default charter has not discovered would fire a warning at every session of
    a plane whose only sin is calling its branch something else, and a preflight that is
    permanently yellow is one people stop reading (`check_memory_indexes` records the
    same concern for the same reason)."""
    ref = _git_in(root, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    remote_head = ref.stdout.strip()
    if ref.returncode == 0 and remote_head:
        # `--short` renders it as `origin/main`, not `main`.
        return remote_head.split("/", 1)[1] if remote_head.startswith("origin/") else remote_head
    for guess in ("main", "master"):
        if _git_in(root, "rev-parse", "--verify", "--quiet",
                   f"refs/heads/{guess}").returncode == 0:
            return guess
    return None


def _stranded_push(root) -> tuple[str, str] | None:
    """A ``(finding, action)`` for a memory commit whose push did not reach `origin`, or
    ``None`` — the surface for `planegit.record_push` (#373).

    The reactive memory push runs detached with ``/dev/null`` for stdout and stderr, so it
    has no caller to tell when a protected default branch refuses it. It writes down what
    happened instead, and this is where that gets read: `doctor` runs from SessionStart,
    which is the surface ADR 0008 already chose for everything else about the plane root.

    **The record is checked, not believed.** A file saying "this did not land" is only true
    until somebody lands it, and a warning that cannot clear itself is one people learn to
    scroll past — which is the failure ADR 0008 spent its whole second half on. So the
    recorded commit is tested against the world: once it is an ancestor of the tracked
    upstream, the condition is over whatever the file still says. `planegit.is_spent` is
    that test, asked here rather than spelled out here because the PUSHER asks the same
    question (it decides whether an open pull request's branch may still be advanced) and
    two answers to "is this record still live" is how a warning nobody can clear and a
    branch reused after its pull request merged both arrive. It is a local ref read, never
    a fetch, because this runs from a hook that must not reach the network — which is why
    the runner is passed in as `_git_in`, under this check's own timeout budget.

    ``unreachable`` is not reported, and as of the #373 review it is not RECORDED either —
    see `planegit.push_head`. A plane with no origin on a forge charter knows has a
    CONFIGURATION to fix, which `commit_push` already says out loud at the moment it
    happens; a guard here would be the second line of defence for something that is now
    impossible, and the first one failed precisely because it was written as a guard
    somewhere else instead of as the rule itself.

    Never raises: the caller is a preflight check, and `push_record` already degrades a
    malformed file to ``None`` rather than to an exception.
    """
    from . import planegit

    rec = planegit.unlanded(lambda a: _git_in(root, *a))
    if not rec:
        return None
    landed, url, branch = rec.get("landed"), rec.get("url"), rec.get("branch") or "main"
    # WHY it did not land is in git's own words in the record, and nowhere else — the
    # background pusher's stderr went to /dev/null. Naming the file is what gives that
    # field a reader; doctor's own text stays constants (ADR 0009), so nothing a remote
    # said is interpolated into this line.
    where = f" What the remote said is in {planegit.push_record_path()}."
    if rec.get("outcome") == planegit.BRANCHED and landed:
        # It IS on the remote — under another name, waiting for a pull request. Naming the
        # branch matters because the remedy is completely different from the stranded case:
        # nothing is at risk, something is unfinished.
        open_it = f"Open it: {url}" if url else "Open a pull request for it."
        return (f"a memory commit went to '{landed}', not {branch}",
                f"'{branch}' requires a pull request, so charter pushed {landed} "
                f"instead. {open_it}")
    # Nothing reached the remote. The HAZARD is named, not merely the fault, because
    # `git reset --hard origin/<branch>` is the standard move on noticing a divergence and
    # it deletes this commit without a trace — the specific way #373's memories were lost.
    # A reader told only "it is unpushed" runs exactly that command next.
    #
    # Describing it is not preventing it, and since #401 something does prevent it:
    # `hooks._plane_root_reset_reason` refuses that command in the plane root while the
    # commits it would delete are on no remote. This row stays exactly as it was. The guard
    # only fires when someone types the command, and it deliberately measures a narrower
    # thing than this row reports — `--soft`/`--mixed` and an unstage go through, and so
    # does everything from a shell charter is not inside. Saying it here is still the only
    # way the operator hears about a stranded commit BEFORE reaching for the reset.
    return ("a memory commit was committed but never pushed",
            f"Push it with `charter save` before anything runs `git reset --hard "
            f"origin/{branch}` in {root}, which would delete it silently.{where}")


def check_plane_root() -> Result:
    """Is anyone working in the plane root?

    The plane root — the directory holding ``charter.toml`` — holds the control plane:
    personas, inventory, workspaces, config, and nothing anyone is meant to edit or
    switch branches in. Work happens in a workspace's clones. Nothing in the filesystem
    enforces that (ADR 0008), and the failure it invites is invisible in exactly the
    surface a user would check: two sessions both sitting in the root share one working
    tree and one HEAD and thrash each other's branches, while charter reports two
    different workspaces and lists no tree that would hint at why. Observed rather than
    theorised — six branches in one session, and a `git checkout main` in the root that
    silently reverted in-flight work out of the tree.

    This is the replacement for `check_embedded_worktrees`, which went with the embedded
    plane shape (ADR 0007). That check guarded a hazard specific to a shape that no
    longer exists; deleting it without a successor would leave the *new* failure mode
    unwatched in the file built to watch for failure modes.

    WARN, never FAIL. FAIL is doctor's "you cannot work" list — it is what makes
    `charter doctor` exit non-zero, which is what makes the SessionStart wrapper print
    the preflight-failed banner — and a root being worked in is a smell that gets
    expensive later, not a broken plane. ADR 0008 chose signal over refusal on purpose,
    and this is that signal at the moment acting on it is still cheap.

    Never raises: this runs from the SessionStart hook, and is the command you run
    *because* something is wrong. The exceptions caught are narrow (a missing/unusable
    git, a root that cannot be read, git not answering in time) rather than a bare
    ``except``, for the reason `check_memory_indexes` records: a broad catch there once
    swallowed a `NameError` and reported OK, and a check that silently does nothing is
    worse than no check.
    """
    from . import config as _config

    name = "plane root"
    if not _config.HAS_CONTROL_PLANE:
        # No plane, no plane root. `check_control_plane_config` already says so loudly;
        # a second row repeating it is noise.
        return Result(name, OK, detail="no control plane found")

    root = Path(_config.ROOT)
    try:
        top = _git_in(root, "rev-parse", "--show-toplevel")
        toplevel = top.stdout.strip()
        if top.returncode != 0 or not toplevel:
            # `charter init` in a fresh directory does not run `git init` — that is the
            # README's own 60-second path. No history, no branch to be on, no dirt.
            return Result(name, OK, detail="not a git repository")
        # `.resolve()` on both sides or this comparison lies: macOS hands out temp and
        # home paths through symlinks (`/var` → `/private/var`), and git always answers
        # with the physical path.
        if Path(toplevel).resolve() != root.resolve():
            # A `charter.toml` in a subdirectory of some larger repo: that repo is not
            # the plane's. Its branch is whatever that project is working on and its dirt
            # is that project's work in progress, so reporting on it would warn every
            # session about a state that is entirely correct.
            return Result(name, OK, detail=f"not its own repository (inside {toplevel})")

        head = _git_in(root, "symbolic-ref", "--quiet", "--short", "HEAD")
        # Non-zero means detached — asked this way rather than `rev-parse --abbrev-ref`,
        # which answers the literal string "HEAD" and so reads as an ordinary branch name
        # right up until it is compared against the default.
        branch = head.stdout.strip() if head.returncode == 0 else None
        default = _plane_default_branch(root)
        # `--untracked-files=no` deliberately. Memory defaults to `share = "local"` —
        # written to disk and never committed — so every plane a few days old carries
        # untracked files under `personas/*/memory/`. Counting those would put this row
        # permanently in the yellow, which costs the two findings that do matter.
        #
        # Read for its EXIT STATUS as well as its output (#917). This was the one rc-blind
        # line in a function that checks every other git call it makes — `--show-toplevel`,
        # `symbolic-ref`, both `rev-list`s and `@{upstream}` all branch on `returncode` —
        # and an empty answer from a `git status` that failed produced `✓ plane root  clean
        # on main`. The surrounding `try` already turned a TIMEOUT into an honest "not
        # checked"; a non-zero exit deserves the same sentence, and `_NOT_CHECKED_HINT`
        # exists to say why a tick over an unrun check is the wrong glyph.
        status = _git_in(root, "status", "--porcelain", "--untracked-files=no")
        if status.returncode != 0:
            return Result(name, WARN,
                          detail=f"not checked (git status exited {status.returncode})",
                          hint=_NOT_CHECKED_HINT)
        dirty = [ln for ln in status.stdout.splitlines() if ln.strip()]
        # How far the root has drifted behind its upstream. Read from the ALREADY-FETCHED
        # remote ref — never a live query, because this runs from the SessionStart hook and
        # must not reach the network. `@{upstream}` fails cleanly on a root with no
        # tracking branch (a plane `git init`-ed by hand), which is not a fault.
        behind = _git_in(root, "rev-list", "--count", "HEAD..@{upstream}")
        behind_n = int(behind.stdout.strip() or 0) if behind.returncode == 0 else 0
        # And how far it has run AHEAD, which is the other half and the one #373 is about.
        # A root drifts behind because nobody works in it; it can only get ahead because
        # something committed here and the push did not land. Read the same way, from an
        # already-fetched ref, for the same reason.
        ahead = _git_in(root, "rev-list", "--count", "@{upstream}..HEAD")
        ahead_n = int(ahead.stdout.strip() or 0) if ahead.returncode == 0 else 0
        upstream = _git_in(root, "rev-parse", "--abbrev-ref", "@{upstream}")
        upstream_ref = upstream.stdout.strip() if upstream.returncode == 0 else ""
        stranded = _stranded_push(root)
    except (util.ProcTimeout, OSError) as e:
        return Result(name, WARN, detail=f"not checked ({e})",
                      hint=_NOT_CHECKED_HINT)

    findings, actions = [], []
    if branch is None:
        findings.append("detached HEAD")
        actions.append(f"Put the root back on a branch: git -C {root} checkout "
                       f"{default or '<your default branch>'}.")
    elif default and branch != default:
        findings.append(f"on {branch}, not {default}")
        actions.append(f"Put the root back: git -C {root} checkout {default}.")
    if dirty:
        findings.append(f"{len(dirty)} uncommitted file(s)")
        actions.append("Commit control-plane content with `charter save`.")
    # A FINDING, unlike the drift counts below, because it is not a resting state: it says a
    # write charter was asked to make did not arrive, and it clears itself the moment the
    # commit reaches the remote.
    if stranded:
        findings.append(stranded[0])
        actions.append(stranded[1])
    # Said in the DETAIL and never as a finding: a root behind its upstream is the normal
    # resting state of a directory nobody works in, so warning about it would put this row
    # permanently in the yellow — the cost this check already refuses to pay for untracked
    # memory files. But `clean on main` is a statement about the working TREE that reads as
    # one about the plane, and a root drifts behind precisely BECAUSE nobody works in it:
    # every change arrives through a workspace clone and a PR, and nothing pulls the root.
    # Observed three times in one session, twice acting on a stale checkout.
    #
    # Appended to BOTH paths. The first version put it only on the clean one, so a root
    # that was dirty *and* behind said nothing about being behind — and those two states
    # share a cause, since the same neglect that leaves memory files uncommitted is what
    # leaves the checkout stale. It stayed silent on the one occasion it mattered: a plane
    # three commits behind, holding the fix for the bug being debugged, reporting only its
    # uncommitted file.
    #
    # "at last fetch" is not hedging. The number is read from a ref that is only as current
    # as the last fetch, and presenting it as a live reading would be the failure ADR 0013
    # names — in the check whose whole job is to report state honestly.
    drift = (f", {behind_n} behind {upstream_ref or 'upstream'} at last fetch"
             if behind_n else "")
    # Stated alongside `behind`, and for the sharper version of the same reason. `clean on
    # main` over a root three commits AHEAD of its remote is not merely incomplete — it is
    # the sentence that made `git log <tag>..main` look authoritative while three real
    # commits sat between them, and turned "nothing to release" into an honest-looking
    # wrong answer (#373). Unlike `behind`, this is never the resting state of a directory
    # nobody works in, so it costs no permanent yellow to say.
    #
    # The count and nothing more. An earlier draft appended "and unpushed", which is a
    # different claim and is FALSE in the commonest case that reaches here: after a
    # protected-branch rejection the commit is on the remote under `charter/<sha>`, so the
    # root is ahead of `main` and the commit is pushed. Whether anything is at risk is the
    # finding's job, which knows; the drift clause only knows the two counts. Rule 1 of
    # ADR 0013, in the row whose whole job is reporting state honestly.
    if ahead_n:
        drift += f", {ahead_n} ahead of {upstream_ref or 'upstream'} at last fetch"
    if not findings:
        return Result(name, OK, detail=f"clean on {branch}{drift}")
    # Where the work belongs is said ONCE, after the per-finding actions. Saying it per
    # finding printed the same "move it into a workspace clone" clause twice in a row
    # that fires with both findings at once — which is the common case, since whoever
    # branched in the root is also editing in it.
    return Result(
        name, WARN, detail=", ".join(findings) + drift,
        hint=" ".join(actions) + " Anything that is not control plane belongs in a "
             "workspace clone — charter workspace create <task>, then charter clone "
             "<repo>; the plane root is one working tree every session shares.",
    )


def check_harness_profiles(*, preflight: bool = False) -> Result:
    """This machine's harness profiles, as `charter.local.toml` declares them now — and
    whether git would carry that file.

    Through `profiles.current()`, the one reader (ruling 43): it reads the file as it is now,
    and applies the refusals every surface sees, a name that clashes with a command included.

    The git check lives here and not in `profiles.current()` because a person runs `doctor`.
    **`charter doctor --preflight` — what the SessionStart hook runs — skips it** (re-review
    N8): every git call on a hook path is paid at every session start, and what is left
    costs one file read, so a refused profile and a missing `default` are still reported
    there. `profiles.ignore_check` never raises, so one slow git costs this row and nothing
    more: `_checks` builds every row in one list with no per-check guard.

    Each state's hint is that state's own fix (F3): `charter reinit` adds the ignore line, and
    that fixes a committable file only. WARN rather than FAIL even for a tracked file: its
    profiles are refused, so nothing runs.
    """
    from . import config as _config, profiles

    name = "harness profiles"
    # Read first, whatever git says, the way `charter harness list` does: the ignore check
    # answers from git without opening the file, and a row that skipped the read on a
    # committable file would be the one surface that reached the operator's own profiles with
    # no read the suite's guard could see (`tests/_planeguard`, ruling 43).
    profile_set = profiles.current()
    check = profiles.IgnoreCheck("", "") if preflight else profiles.ignore_check(_config.ROOT)
    if check.reason:
        return Result(name, WARN, detail=check.reason, hint=check.fix)
    names = ", ".join(profile_set.profiles)
    refused = profile_set.refused
    if refused:
        return Result(name, WARN,
                      detail=f"{len(refused)} refused: "
                             f"{', '.join(r.name or r.source for r in refused)}",
                      hint=refused[0].reason)
    if profile_set.default_refused is not None:
        return Result(name, WARN,
                      detail=profiles.DEFAULT_REFUSED.format(value=profile_set.default_refused,
                                                             names=names),
                      hint=profiles.DEFAULT_FIX.format(names=names))
    return Result(name, OK, detail=f"{len(profile_set.profiles)} profile(s): {names}")


def check_profile_wiring(*, preflight: bool = False) -> list[Result]:
    """One row per profile the selector would list: does charter's guard run in the folder
    that profile names?

    **No probe on a hook path** (ruling 11). `preflight=True` returns no rows and calls
    nothing: a probe costs 137-718 ms per profile and writes into that profile's config
    folder, and the SessionStart hook's whole budget is 20 s. Only a `charter doctor` a
    person types probes.

    **A profile charter may not run a command for is never probed** (ruling 1), and there
    are two reasons it may not: git would carry `charter.local.toml` — the `harness profiles`
    row above says why, with the fix — or the operator has not approved this command
    (`profiletrust`). Its row says which and names what to run; asking the harness would
    mean running a command out of a file a chat can write. `wiring.detect` keeps the same
    gate for itself, so a row that forgot to ask would still not probe.

    Concurrently, because the answers are independent and each is a subprocess: measured on
    this plane, three declared profiles and three built-ins add well under the 2 s budget
    ruling 11 sets. Each probe keeps its own `plugincache.LIST_TIMEOUT`.

    **A row's exception costs that row, not the report** — `check_plugin_install`'s
    catch-all shape. A `claude` that segfaults for one profile must not take the other rows,
    or the checks after them, down with it.

    Every row is bounded by :func:`_counted` and never by a bare ``...`` (ruling 45): these
    are rows an operator acts on, and a fix clipped without saying so reads as the whole fix.
    """
    from . import config as _config, profiles, wiring

    if preflight:
        return []
    rows = wiring.listed()
    # ONE git call however many profiles are declared, and none for a plane that declares
    # none — the same lock-free `git status` the `harness profiles` row makes.
    ignored = (profiles.ignore_check(_config.ROOT)
               if any(p.source != profiles.BUILTIN for p in rows)
               else profiles.IgnoreCheck("", ""))
    out: list[Result] = []
    with cf.ThreadPoolExecutor(max_workers=4) as pool:
        held = {p.name: _not_probed(p, ignored) for p in rows}
        answers = {p.name: pool.submit(wiring.detect, p, cwd=_config.ROOT)
                   for p in rows if held[p.name] is None}
        for p in rows:
            name = _profile_row_name(p)
            if held[p.name] is not None:
                detail, hint = held[p.name]
                out.append(Result(name, WARN, detail=_counted(detail), hint=_counted(hint)))
                continue
            try:
                w = answers[p.name].result()
            except Exception as e:                      # noqa: BLE001 — one row, not the run
                # Contained (ruling 35): an exception's text is whatever the code that raised
                # it put there, and here that is a path or an argv built from the profile.
                out.append(Result(name, WARN, detail=_counted(contain.readable(
                    f"{type(e).__name__}: {e}", contain.NO_CLIP)), hint=_NOT_CHECKED_HINT))
                continue
            if w.state == wiring.WIRED:
                out.append(Result(name, OK, detail=_counted(w.detail)))
            elif w.state == wiring.UNWIRED:
                out.append(Result(name, WARN, detail=_counted(w.detail),
                                  hint=_counted(w.fix)))
            else:
                out.append(Result(name, WARN, detail=_counted(w.detail),
                                  hint=_NOT_CHECKED_HINT))
    return out


def _not_probed(p, ignored) -> tuple[str, str] | None:
    """``(detail, hint)`` for a profile whose command charter may not run, else ``None``.

    Both already escaped: the only profile-derived text in either is the name, contained
    whole so :func:`_counted` can say how much of it a row hid.
    """
    from . import profiles, profiletrust

    if p.source == profiles.BUILTIN:
        return None
    if ignored.reason:
        return ("not probed — git would carry charter.local.toml, so every profile in it is "
                "refused (the harness profiles row says why)", ignored.fix)
    state = profiletrust.approval_needed(p)
    if state:
        return (f"{state}, and not approved yet — charter asks before it runs a command it "
                f"has not been shown", f"charter {contain.readable(p.name, contain.NO_CLIP)}")
    return None


#: What a doctor row says about what it hid (ruling 45): `contain.counted`, the one helper
#: for it — the profile selector's rows count with the same one, because it is the same
#: promise to the same operator. An ellipsis marks a cut and not its size, and on a row
#: whose hint is a command to run, a reader cannot tell a clipped command from a whole one
#: without the size. Named here as well, so every row below still reads as one of doctor's.
_counted = contain.counted


def _profile_row_name(p) -> str:
    """A profile's row name — one spelling, because :func:`profile_row_names` sizes the
    column from exactly these strings and a row whose name differed would push its own row."""
    return f"profile {_counted(contain.readable(p.name, contain.NO_CLIP))}"


def profile_row_names(*, preflight: bool = False) -> list[str]:
    """The names :func:`check_profile_wiring` will produce, without probing anything.

    The same reader (`wiring.listed`), so `check_names` and `run_all` cannot disagree about
    how many rows there are — the pin `_FIXED_CHECK_NAMES` already keeps for every other
    check, applied to a list this plane's own `charter.local.toml` decides.
    """
    from . import wiring

    if preflight:
        return []
    return [_profile_row_name(p) for p in wiring.listed()]


def check_index_lock() -> Result:
    """A ``.git/index.lock`` left in the plane's own repository — noticed *before* a save
    runs into it.

    #917 is what happens when nothing does. The operator's lock had been there for
    twenty-three hours, through however many sessions, and the first thing to look at it
    was the `charter save` it broke — which then reported the tree clean and said nothing
    about the file. A preflight row is where a fact like that belongs: it costs one `stat`
    on a path charter can work out without a subprocess (`gitstate.git_dir_of` asks the
    filesystem first), and it turns a silent trap into a line an operator reads at the top
    of the session.

    **A lock is not a fault, so a lock is not automatically a warning.** git takes one for
    every write to the index; catching a legitimate `git commit` mid-flight and painting
    the preflight yellow for it would be a false alarm on healthy behaviour, and a
    permanently-yellow row is one people stop reading (`check_memory_indexes` records the
    same concern for the same reason). A fresh lock is reported on an OK row — stated, on
    the `↳` continuation `Result.render` gives a detail, because a green row keeps nothing
    back.

    **Zero bytes and hours old is different, and it is a WARN.** git creates the lock,
    writes the new index into it, and renames it over the old one, so a lock that never
    grew is one whose writer died before writing anything — a crash, not contention, and
    something only a person can clear. WARN and not FAIL: `cmd_doctor` exits non-zero on
    FAIL, and a stale lock is "the next save will refuse", not "you cannot work".

    charter names it and stops there. The `rm` is the operator's, after the `ps` — see
    `gitstate` for why that division is not a formality.
    """
    from . import config as _config

    name = "index lock"
    if not _config.HAS_CONTROL_PLANE:
        return Result(name, OK, detail="no control plane found")
    root = Path(_config.ROOT)
    try:
        lock = gitstate.for_repo(root, timeout=CHECK_TIMEOUT)
    except (util.ProcTimeout, OSError) as e:
        return Result(name, WARN, detail=f"not checked ({e})", hint=_NOT_CHECKED_HINT)
    if lock is None:
        return Result(name, OK, detail="none held on the plane's index")
    if not lock.crashed:
        return Result(name, OK, detail=f"held now — {lock.size} byte(s), "
                                       f"{gitstate.age_phrase(lock.age)} old; a git is "
                                       f"probably writing")
    return Result(
        name, WARN,
        detail=f"{lock.path} — {lock.size} byte(s), {gitstate.age_phrase(lock.age)} old",
        hint="A git process crashed here and left the index locked; every `charter save` "
             "and `git add` in this plane will refuse until it is gone. Check nothing "
             "holds it (ps -eo pid,lstart,command | grep '[g]it'), then remove it "
             f"yourself: rm -f {lock.path}  — charter never removes a lock.",
    )


def session_root() -> Path:
    """The directory the HOST resolves this session's project settings against (#851).

    **Not the plane, and that is the whole point.** `config.ROOT` comes from
    `root.find_root`, which walks UP from the working directory until it finds a
    `charter.toml` — so it lands on the plane from anywhere inside it, which is exactly
    right for identity. **Project settings do not walk up**: `.claude/settings.json` is read
    from the session's own directory and nowhere above it, which is the rule this function
    exists to serve — every settings row below reads what it returns. A chat launched at
    `workspaces/<ws>/` — where the `+` button and every workspace tab put one — therefore
    reads none of the plane's settings, while `doctor` read all of them and reported the
    plugin enabled and the guard wired over a session that had neither.

    This paragraph used to say agents, skills and commands were read the same way. They are
    not: `.claude/agents/` and `.claude/skills/` walk up and stop at the git root, and
    `CLAUDE.md` walks up and is not git-bounded at all — measured on Claude Code 2.1.259 and
    declared on `Harness.layer`, which is where every part of that answer now lives (#879).
    Charter has measured no rule for `.claude/commands` and this therefore claims none.
    Settings are the only artefact this function answers for, and the only one it should:
    which of the rest reach a directory is `check_session_layer`'s question, resolved
    against that directory's real git root rather than stated in prose here.

    ``os.getcwd()`` is the evidence available, and it is the right evidence rather than a
    stand-in: doctor runs *inside* the session it is reporting on, so the directory this
    process is standing in is the directory the host resolved settings against.
    ``$CLAUDE_PROJECT_DIR`` is exported to hook commands only — measured, not assumed: it
    is absent from a session's own shell, so a `charter doctor` the agent or the operator
    types would read nothing from it.

    Deliberately NOT `root.tree_of`. That function answers "am I in a linked worktree of
    the plane's repo" and answers ``None`` for ``workspaces/<ws>/<repo>`` **on purpose**
    (its own docstring says so, and `nested_plane_in` exists because widening it would be
    wrong). The question here is neither of those: it is "which directory is this session
    rooted in", which no plane-relative derivation can answer.

    Falls back to the plane if the cwd cannot be read at all — a process whose working
    directory was deleted out from under it. A preflight row must render something.
    """
    from . import config as _config
    try:
        # Already canonical: the kernel resolves symlinks on the way out of `getcwd`, so
        # this compares cleanly against a resolved plane without a second syscall that
        # could itself raise.
        return Path(os.getcwd())
    except OSError:
        return _canonical(Path(_config.ROOT))


def _canonical(p: Path) -> Path:
    """*p* with symlinks resolved, or *p* itself when it cannot be.

    **One call site, deliberately.** The first draft resolved both sides of the comparison
    in :func:`session_is_the_plane`, and the deletion sweep charged both — each was
    individually deletable with the suite still green, because they masked each other and
    because a Linux runner's ``/tmp`` needs no normalising either way. Only one of them was
    ever load-bearing: `os.getcwd` hands back the physical path already, so the SESSION
    side has nothing to normalise, while `config.derive` stores ROOT exactly as it was
    handed in — a plane reached through a symlink (macOS's ``/var`` → ``/private/var``, a
    symlinked checkout, `config.use` in a test) keeps that spelling.

    So the plane is the side that needs it, and this is where it happens. Resolving a path
    can raise `OSError` (an unreadable ancestor) or `RuntimeError` (a symlink loop), and a
    preflight row must render something rather than traceback.
    """
    try:
        return p.resolve()
    except (OSError, RuntimeError):
        return p


def session_is_the_plane() -> bool:
    """Is this session rooted at the plane, so that the plane's ``.claude/`` is in force?

    The plane is canonicalised before comparing and the session is not, because only the
    plane can be spelled two ways — see :func:`_canonical`. Without it a plane whose path
    runs through a symlink answers "not the plane" for a session standing in the very
    directory it resolved, and every row below would report a divergence that is not there.
    """
    from . import config as _config
    return session_root() == _canonical(Path(_config.ROOT))


def _settings_files(root: Path | None = None, folder: Path | None = None) -> list[Path]:
    """The settings the HOST actually resolves, in the order it reads them.

    One list, used both for a directly-declared hook and for `enabledPlugins`, so the two
    halves of "is it wired" can never disagree about which files are in force.

    *root* defaults to :func:`session_root` — the directory this session is rooted in, not
    the plane (#851). A caller that is asking about a **specific** file rather than about
    this session names its own root: `commands._ensure_guard_hook` is about to write the
    PLANE's `settings.json` and must read the plane's `enabledPlugins`, whatever directory
    the operator happened to be standing in when they typed `charter reinit`.

    **The local file is read in two places, and this listed one** (Claude Code 2.1.267,
    measured for #942; documented from 2.1.211): the session's own directory, and the git
    root — the main checkout, for a linked worktree. A workspace directory sits inside the
    plane's repository, so a hook or a plugin declared only in the plane's
    `settings.local.json` IS in force in a workspace chat, and every row built on this list
    said it was not. Appended after the session's own copy so the order the rows already
    print in is unchanged, and not at all where the root is the directory itself — the
    guard row counts declarations, and one file listed twice would read as declared twice.

    **The user half is the config folder Claude Code is using, not ``~/.claude``** (#969).
    `$CLAUDE_CONFIG_DIR` moves it — a second account is the usual reason — and a session
    under that folder never opens ``~/.claude/settings.json``. Reading it anyway credited
    the session with a guard hook and an `enabledPlugins` entry it did not have. *folder*
    names another folder for the one caller that must not follow the shell — see
    :func:`_claude_folder`. The repository's local file is unaffected by it: that one is
    found from the checkout, so it is the same file whichever config folder is in use.
    """
    here = Path(root) if root is not None else session_root()
    files = [here / ".claude" / "settings.json", here / ".claude" / "settings.local.json"]
    top = _local_settings_root(here)
    if top is not None and top != _canonical(here):
        files.append(top / ".claude" / "settings.local.json")
    files.append(_claude_folder(folder) / "settings.json")
    return files


def _local_settings_root(here: Path) -> Path | None:
    """Where Claude Code keeps `.claude/settings.local.json` for a session at *here*.

    The git common directory's parent when that directory is a `.git` — the repository root
    for a clone and the MAIN checkout for a linked worktree, which is measured: a `deny` in
    the main checkout's local file applies to a session in the worktree. `--show-toplevel`
    for a repository whose git directory lives elsewhere (`--separate-git-dir`), where the
    common directory's parent is not the checkout at all.

    ``None`` outside a repository, and where the root is the home directory — the docs'
    own case for the file staying beside the shared one. Never raises: this is read from
    the SessionStart hook, and a git that cannot answer costs only the extra entry.
    """
    try:
        res = _git_in(here, "rev-parse", "--path-format=absolute", "--git-common-dir")
        if res.returncode != 0:
            return None
        common = Path(res.stdout.strip())
        if common.name == ".git":
            top = common.parent
        else:
            res = _git_in(here, "rev-parse", "--show-toplevel")
            top = Path(res.stdout.strip())
    except (util.ProcTimeout, OSError):
        return None
    top = _canonical(top)
    return None if top == _canonical(Path.home()) else top


def _claude_folder(folder: Path | None) -> Path:
    """*folder*, or the Claude Code config folder in use when none is named (#969).

    Every `doctor` row asks about the folder in use. `commands._plugin_dispatches_guard`
    names ``~/.claude`` instead, because `charter reinit` writes the plane's committed
    `.claude/settings.json` — read by the sessions of every config folder — and a committed
    file must not change with one person's shell.
    """
    from .harness import claude_code as _claude_code

    return Path(folder) if folder is not None else _claude_code.config_home()


def _settings_docs(root: Path | None = None, folder: Path | None = None) -> list[dict]:
    """Every settings document the host resolves from *root*, parsed, unreadable ones dropped.

    One reader for :func:`_settings_files`, because two of them drifted once already: the
    hook half read the files as TEXT and the plugin half as JSON, and a `charter hook
    pretooluse` line inside a comment-shaped string would have counted for one and not the
    other. Anything asking a *structured* question about the session's settings asks here.

    A file that is absent, unreadable or not a JSON object is simply not in the list.
    "The host would read nothing from it" is the same answer in all three cases, and a
    checker that treated a malformed file as a declaration would report a layer that is
    not there.
    """
    out: list[dict] = []
    for p in _settings_files(root, folder):
        try:
            doc = json.loads(p.read_text())
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        if isinstance(doc, dict):
            out.append(doc)
    return out


def _enabled_plugin_ids(root: Path | None = None, folder: Path | None = None) -> set[str]:
    """Plugin ids the host has ENABLED. Installed is not enabled (#177)."""
    out: set[str] = set()
    for doc in _settings_docs(root, folder):
        for pid, on in (doc.get("enabledPlugins") or {}).items():
            if on:
                out.add(pid)
    return out


def _plugin_declaring_guard(root: Path | None = None,
                            folder: Path | None = None) -> str | None:
    """An ENABLED Claude Code plugin whose own ``hooks.json`` dispatches the guard.

    ``CLAUDE_PLUGIN_ROOT`` is set only for the plugin's OWN processes, so a `charter doctor`
    a human runs in a terminal never sees it — even where the plugin is enabled and the
    guard demonstrably fires. Checking the env var alone cries wolf on exactly the planes
    that ARE protected.

    But **installed, enabled and wired are three different states, and only the third
    protects anything** (#177). 0.31.1 accepted the first and printed a tick over a plane
    where `git checkout -b` in the root succeeded: the plugin was installed and *disabled*,
    so nothing dispatched the hook. That is #168's own category error — verifying a proxy
    instead of the fact — committed while fixing #168.

    Deliberately NOT version-checked, against #177's suggestion. A plugin supplies only the
    WIRING; the handler is whatever ``charter`` is on PATH. The reporting plane's plugin was
    0.29.1, from before the guard existed, and its ``hooks.json`` still dispatches
    ``charter hook pretooluse`` — which would have run today's CLI, guard included, had it
    been enabled. Requiring a minimum plugin version would warn on planes that are genuinely
    protected, which is the cry-wolf failure 0.31.1 was itself fixing. A plugin too old to
    wire ``pretooluse`` at all is already excluded by reading its hooks.json rather than its
    version.

    Read from ``installed_plugins.json`` rather than globbed out of the plugin cache: the
    cache keeps every version ever fetched, so a stale copy would answer for a plugin since
    removed. The manifest is what the host actually installed.

    *root* is the directory whose ``enabledPlugins`` to believe, defaulting to
    :func:`session_root`. ``enabledPlugins`` is a settings key like any other, so it is
    scoped to the directory the host read it from — a plugin enabled in the plane's
    ``settings.json`` is not enabled for a chat rooted at ``workspaces/<ws>/`` (#851). A
    caller writing a specific file names that file's directory instead.

    *folder* is the Claude Code config folder whose plugins and user settings to believe,
    defaulting to the one in use (#969); see :func:`_claude_folder` for the caller that names
    ``~/.claude`` instead.
    """
    enabled = _enabled_plugin_ids(root, folder)
    if not enabled:
        return None
    # The manifest of the config folder Claude Code is USING (#969). This read
    # `~/.claude/plugins/installed_plugins.json` while `plugin install` asked `claude plugin
    # list`, which follows `$CLAUDE_CONFIG_DIR` — so one report said the plugin was not
    # installed for this plane and, rows earlier, that the guard it carries was wired. Under
    # that folder no charter hook ran at all: installed somewhere else read as installed here.
    manifest = _claude_folder(folder) / "plugins" / "installed_plugins.json"
    try:
        doc = json.loads(manifest.read_text())
    except (OSError, ValueError):
        return None
    for pid, entries in (doc.get("plugins") or {}).items():
        if pid not in enabled:
            continue
        for entry in entries or []:
            path = (entry or {}).get("installPath")
            if not path:
                continue
            hooks_json = Path(path) / "hooks" / "hooks.json"
            try:
                if "charter hook pretooluse" in hooks_json.read_text():
                    return pid
            except (OSError, UnicodeDecodeError):
                continue
    return None


def _named(items: list[str]) -> str:
    """*items* as English — ``a``, ``a and b``, ``a, b and c``."""
    if len(items) < 2:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _discovery_rules() -> tuple[list[str], list[str]]:
    """Which parts of charter's layer are read from the session's own directory, and which
    walk up — as the **harnesses** declare them, never as a sentence in this file.

    Read from `Harness.layer` so that `session root` and `session layer` narrate one set of
    rules from one source. They did not, and #879 is what that cost: this row said the host
    reads "project settings, agents, skills and commands from the session's own directory
    and does not walk up", while the row printed directly under it — added one pull request
    later, from a measurement against Claude Code 2.1.259 — said `.claude/agents` and
    `.claude/skills` **do** walk up and stop at the git boundary. Both rows described the
    same binary; only one of them had measured it. An operator in a workspace clone reading
    both was told their agents and skills were out of reach on the line above the line that
    said they were not.

    Prose was the wrong shape for it rather than merely the wrong words. Two rows narrating
    one discovery rule from two independent sources is the drift this file already refuses
    on the harness side — `check_session_layer` says the rules live on the harness *"and the
    day a fourth harness is registered it would silently be reported under Claude Code's
    rules"*. This row was that failure with the harness list of one.

    ``commands`` is dropped rather than reworded. Charter has measured no discovery rule for
    `.claude/commands`, so no `LayerPart` names it, so this row cannot: under-claiming is the
    direction that cannot mislead, which is `_search_dirs`'s reasoning about an unmeasured
    walk boundary.

    **A harness charter has not met answers for nothing**, and both lists come back empty
    for it. `check_session_layer` refuses to report an unregistered runtime under Claude
    Code's rules; reporting it here instead would be the same borrowed answer one row up.

    `dict.fromkeys` and not a set, for `check_session_layer`'s reason: string hashing is
    randomised per process, so a set would order this sentence differently from one run to
    the next.
    """
    from .harness import registry as _registry

    current = _registry.current()
    live = _registry.get(current)
    if current and live is None:
        return [], []
    harnesses = [live] if live else _registry.all()
    # `h.layer` and not `h.layer or ()`, and the distinction is which side of charter the
    # value comes from. `Harness.layer` is a class attribute charter declares — `tuple[
    # LayerPart, ...] = ()` on the base, a tuple on all three registered harnesses — so an
    # `or ()` in front of it guards a shape charter itself guarantees one file away: a
    # branch nothing can reach, which the deletion sweep charged as a survivor and was right
    # to. A fallback in front of somebody ELSE's answer is a different thing and stays; this
    # was one in front of charter's own. `check_session_layer` reads the attribute bare too.
    parts = [p for h in harnesses for p in h.layer]
    return (list(dict.fromkeys(p.what for p in parts if not p.walks)),
            list(dict.fromkeys(p.what for p in parts if p.walks)))


def check_session_root() -> Result:
    """Which directory answered for the settings rows — and whether it is the plane (#851).

    Every row below that reads `.claude/settings.json` reads :func:`session_root`'s, and
    when that is not the plane the operator will go and look at the plane's file, find the
    guard declared in it, and conclude doctor is broken. So the divergence is stated once,
    up front, in the vocabulary charter already uses for it: **the plane is identity, the
    directory you are standing in is artifacts** (`config.in_tree`, `docs/control-plane.md`
    → *What follows the plane, and what follows the tree*).

    **And the rules it names come from :func:`_discovery_rules`, not from a sentence here**
    (#879). This row told an operator that agents and skills are read from the session's own
    directory and do not walk up; the `session layer` row, printed on the very next line,
    told them the opposite and was right. See `_discovery_rules` for why the fix is a shared
    source rather than better words. What is left in this row's own voice is the one thing
    it owns — which directory answered — and the walking half is handed to `session layer`
    unanswered, because whether the walk arrives is a question about this directory's git
    root and that row is the one that resolves it.

    **A fact, never a verdict — OK even when the two differ.** A chat rooted in a workspace
    is the designed workflow: the `+` button and every workspace tab put one there, and a
    row that warns on the normal case is a row operators learn to skip — the failure
    `check_memory_indexes` and `check_harness` each record in their own docstrings.
    Whatever is actually *missing* because of the divergence warns on its own row, where it
    can name its own remedy; this one supplies the reason those rows read the way they do
    (ADR 0013).

    **Trust is deliberately not asked here, and that is a real gap rather than an
    oversight.** Claude Code gates hook execution on the directory being trusted,
    globally, whatever declared it — so "the plugin is enabled here" and
    "charter's hooks actually run here" are two different questions, and an untrusted
    directory answers yes to the first and no to the second. That belongs to
    `check_guard_seen`, which already answers dispatch from evidence (a guard that ran)
    rather than from configuration, and which says in its own docstring why no amount of
    reading configuration can see it. Naming a directory as trusted by reading Claude Code's
    ``.claude.json`` — which is not even ``~/.claude.json`` once `$CLAUDE_CONFIG_DIR` moves it
    (#969) — would be one more proxy in the family this row is fixing.
    """
    from . import config as _config

    name = "session root"
    here = session_root()
    if not _config.HAS_CONTROL_PLANE:
        return Result(name, OK, detail=f"{here} — no control plane found")
    if session_is_the_plane():
        return Result(name, OK, detail=f"{here} — the plane")
    from .harness import claude_code as _claude_code

    cwd_only, walking = _discovery_rules()
    lines = [f"{here} — not the plane ({_config.ROOT})"]
    # The folder the rows below actually read, not a spelling of the default one (#969):
    # under `$CLAUDE_CONFIG_DIR` they read that folder, and naming `~/.claude/` here would
    # send the operator to check a file no row consulted.
    user_folder = f"{util.short_path(_claude_code.config_home())}/"
    if cwd_only:
        lines.append(f"the host reads {_named(cwd_only)} from the session's own directory "
                     f"and does not walk up, so the plane's .claude/ is not in force for "
                     f"them — the rows below read {here}/.claude/ and {user_folder}")
    else:
        lines.append(f"the rows below read {here}/.claude/ and {user_folder}, not the "
                     f"plane's")
    if walking:
        # Said here, in the row that would otherwise be read as "none of it reaches",
        # and said WITHOUT an answer: whether the walk actually delivers anything from
        # this directory depends on where its git root is, and `session layer` is the row
        # that resolves that against the real filesystem. Two rows answering it would be
        # #879 again in the other direction.
        lines.append(f"{_named(walking)} DO walk up, as far as the git root — which of "
                     f"them reach here is the `session layer` row below, not this one")
    lines.append(f"the plane is still this session's identity: personas, the vault, "
                 f"memory and workspaces resolve to {_config.ROOT} from anywhere inside "
                 f"it")
    return Result(name, OK, detail="\n        ↳ ".join(lines))


def _git_root_of(here: Path) -> Path | None:
    """The git repository *here* stands in, or ``None`` when it is in none.

    **A linked worktree answers with the WORKTREE**, not with the main clone, and that is
    the answer both callers want: git's own boundary is the unit an agent runtime's
    upward search stops at, and it is the unit trust is inherited to (#859).

    Never raises and never blocks: this runs from the SessionStart hook, so it is timed
    out like every other git question in this file (`_git_in`), and a repository charter
    cannot interrogate answers ``None`` rather than a traceback.
    """
    try:
        res = _git_in(here, "rev-parse", "--show-toplevel")
    except (util.ProcTimeout, OSError):
        # The same two `check_plane_root` catches, for the same two reasons: `util.run`
        # raises `ProcTimeout` on a stalled network mount, and a missing or unusable
        # `git` reaches here as an OSError from the exec itself. Narrow rather than
        # `Exception`, per `check_memory_indexes`: a broad catch there once swallowed a
        # `NameError` and reported OK. `ProcError` is not among them — `_git_in` passes
        # `check=False`, so a non-zero exit comes back as a result and is read below.
        return None
    top = res.stdout.strip()
    if res.returncode != 0 or not top:
        return None
    return _canonical(Path(top))


def check_session_layer() -> Result:
    """Can a session started HERE see charter's layer? (#869, #859)

    An operator opened a chat in a workspace directory, found no skills, no agents and no
    plugin, and **no row said why**. Every row was individually telling the truth: the
    artefacts are discovered by different rules, so no single one of them could carry the
    answer, and *"charter is set up"* was never one fact. Measured on Claude Code 2.1.259:

    * ``.claude/settings.json`` — the session's own directory, **no walk-up**.
    * ``.claude/agents/`` and ``.claude/skills/`` — walk up, **stopping at the git root**.
    * ``CLAUDE.md`` — walks up and is **not** git-bounded, so it arrives almost anywhere.

    That last rule is why such a chat reads as half-configured rather than as empty:
    charter's prose reaches it and none of charter's machinery does. The row says so — in
    the harness's own words, beside the walking rule it contrasts with.

    **About the LAYER, not the plugin, so `check_guard_wired`'s reasoning stays intact.**
    That check argues — rightly — that *"Whether the plane runs as a plugin is an
    implementation detail. Whether the guard fires is the fact the operator needs"*, and
    nothing here reopens it. This row never reports on a plugin; it reports on what a
    session standing in this directory can reach, which is a different question with a
    different answer, and the guard keeps its own two rows.

    **The rules live on the HARNESS, never here** (`base.LayerPart`, `Harness.layer`).
    Written into this function they would be the hardcoded-literal-per-harness failure
    `harness/registry.py` exists to end, and the day a fourth harness is registered it
    would silently be reported under Claude Code's rules — verifying a proxy instead of
    the fact, which is #168, #177, #261 and #851 in one line. A harness charter writes no
    in-repo layer for says where its layer comes from instead (`Harness.layer_note`), and
    one charter has never measured says exactly that rather than borrowing an answer.

    **A fact, never a verdict.** `check_session_root`'s discipline, for its reason: a chat
    can be rooted in a directory that reaches none of this and be exactly where it belongs
    — a clone charter has not wired yet, or one whose harness charter declares no layer
    parts for — so a row that warned there is a row operators learn to skip, the cry-wolf
    failure `check_memory_indexes` and `check_harness` each record. (This used to say
    charter writes nothing inside `workspaces/<ws>/<repo>/`. It does now: #870 writes the
    layer there and #868 made what it carries every harness's own. The argument is
    unchanged — the row reports what a session would find, and it is `workspace layer` that
    warns when what charter wrote has gone stale or vanished.) Whatever is genuinely missing AND fixable warns on
    its own row, where it can name its own remedy: `workspace layer` for a generated file
    that has gone stale or vanished, `plane-root guard` for the guard.

    **Trust is a CONDITION, not a verdict (#859).** The harness gates hook execution on
    the directory being trusted, globally — the gate takes no argument saying which
    settings source declared it — so *"a file this session reads declares
    `charter hook pretooluse`"* and *"the guard will fire here"* are two facts, and an
    untrusted directory answers yes to the first and no to the second. Charter asks the
    question it **owns**: trust is inherited up to the git root, so a directory with a git
    root of its own needs its own acceptance. That comes from `git rev-parse
    --show-toplevel` and no host-private state. Claude Code's ``.claude.json`` is deliberately not
    read — a missing project entry there means *never opened* just as readily as
    *refused*, and reading absence as refusal would warn at planes that are fine, which is
    the failure two other checks in this file already record. Weaker than a verdict on
    purpose: it names a condition, and it cannot be wrong in the direction that matters.

    It also says why `guard seen` cannot stand in. `guardseen` state lives under
    `config.STATE_DIR`, so that row answers **per plane**: a guard that fired in the plane
    last week still shows a recent sighting for a session rooted in a clone where nothing
    has ever dispatched.
    """
    from . import config as _config
    from .harness import base as _base
    from .harness import registry as _registry

    name = "session layer"
    here = session_root()
    if not _config.HAS_CONTROL_PLANE:
        return Result(name, OK, detail=f"{here} — no control plane found")

    current = _registry.current()
    if current and _registry.get(current) is None:
        # `check_harness` already warns about the unregistered runtime itself. What must
        # not happen here is answering for it anyway: charter has not measured how this
        # thing finds anything, and reporting Claude Code's rules over it would be a
        # confident sentence about a binary nobody has run a probe against.
        return Result(name, OK,
                      detail=f"{here} — charter has no record of how {current} finds an "
                             f"in-repo layer, so this row has nothing to say about it")

    # The running harness when something names one; every registered harness otherwise.
    # A `charter doctor` typed in a plain terminal has no harness to report for, and
    # picking one would be a guess — so it answers for each, which is also the only
    # rendering that shows an operator what a *different* harness would find here.
    # No `if current` guard. `registry.get` already answers ``None`` for a name that is
    # None (`KINDS.get(name or "")`), so the guard could never decide anything — the
    # deletion sweep charged it as a survivor and was right: an equivalent mutant and dead
    # code are the same finding.
    live = _registry.get(current)
    harnesses = [live] if live else _registry.all()

    bound = _git_root_of(here)
    plane_bound = _git_root_of(Path(_config.ROOT))
    # Its OWN git root — not merely "a git root". `workspaces/<ws>/` is a plain directory
    # inside the plane's repository, so it rides the plane's acceptance and must not be
    # warned about; a clone at `workspaces/<ws>/<repo>` and a linked worktree do not.
    own_repo = bound is not None and bound != plane_bound

    lines = [f"{here} — what a session started here would find in the repo"]
    gated = []
    for h in harnesses:
        if not h.layer:
            lines.append(f"{h.name}: " + (h.layer_note or
                                          "charter has not measured how this harness finds "
                                          "an in-repo layer"))
            continue
        if h.trust_gate:
            gated.append(h)
        bits = []
        for part in h.layer:
            if _base.part_reaches(part, here, bound):
                bits.append(f"{part.what} ✓")
            else:
                bits.append(f"{part.what} ✗ — {part.why}")
        lines.append(f"{h.name}: " + "; ".join(bits))

    # Said once, after the per-harness lines, and only where a harness has a MEASURED
    # gate. Repeating it per harness would put a sentence about Claude Code's trust model
    # under opencode's name, which is the kind of borrowed answer this row refuses above.
    if own_repo and gated:
        # Registration order, deduplicated — `dict.fromkeys` and NOT a set, which has no
        # order a reader or a test can rely on: string hashing is randomised per process,
        # so two harnesses naming two gates would render this sentence differently from
        # one run to the next. Registration order rather than alphabetical because that is
        # the order `registry.all` hands them over and the order every other harness
        # listing in charter prints.
        what = " / ".join(dict.fromkeys(h.trust_gate for h in gated))
        lines.append(
            f"trust: {bound} is a git root of its own, so it carries its own trust "
            f"acceptance — until that is given, {what} do not run here whatever any "
            f"settings file declares. `guard seen` cannot answer it: that state lives "
            f"under {_config.STATE_DIR}, so it is per PLANE and a sighting there says "
            f"nothing about this directory")

    return Result(name, OK, detail=("\n        ↳ ".join(lines)))


def check_guard_wired() -> Result:
    """Can `charter hook pretooluse` actually be invoked? (#168)

    The plane-root branch guard (#157) lives in that handler. If nothing is wired to call
    it, no branch move is ever refused — and `check_plugin_skew` printed a green
    ``✓ not running under the Claude Code plugin`` over exactly that state. **The absence
    of a protection rendered as health**, at the moment it mattered most: someone upgrades
    to get the guard, runs `doctor` to confirm the upgrade, sees all green, and reasonably
    believes they are protected.

    Whether the plane runs as a plugin is an implementation detail. Whether the guard fires
    is the fact the operator needs, so this reports the guard and `check_plugin_skew` keeps
    answering its own separate question about version skew.

    Reachable means ANY of: running under the plugin, or `charter hook pretooluse` declared
    in the plane's ``.claude/settings.json``, its ``.claude/settings.local.json``, or the
    user settings of the config folder Claude Code is using — ``$CLAUDE_CONFIG_DIR/
    settings.json`` when that is set, ``~/.claude/settings.json`` otherwise (#969). All
    four, because a plane that IS wired and gets warned every session teaches people to
    ignore the row — the failure `check_memory_indexes` already records.

    It asserts that specific handler rather than "some hook exists": a plane wiring only
    `sessionstart` is unprotected while looking configured, which is this issue again one
    level down.
    """
    from . import config as _config

    name = "plane-root guard"
    if not _config.HAS_CONTROL_PLANE:
        return Result(name, OK, detail="no control plane found")

    from . import guardseen as _seen

    # A Claude Code config folder that cannot be compared — empty, relative, or with no home to
    # resolve it from — turns every answer below into a guess: the plugin list and the user
    # settings this row reads resolve against doctor's working directory, not Claude Code's,
    # and no sighting can vouch for that folder. So it is said first, whatever the sightings,
    # with the one remedy that changes it (the #970 re-review: this row read "nothing has fired
    # here yet" there, and its "run a Bash command" hint could never clear it).
    standing = _seen.folder_standing()
    if standing.folder_in_doubt:
        return Result(name, WARN, detail=f"not checked — {standing.doubt}", hint=standing.hint)

    # `commands._ensure_guard_hook` asks the SAME question through the same function.
    # Reading different evidence is how a writer and a checker disagreed about "wired"
    # and left the guard declared twice — and enabled is not dispatched (#177).
    plugin = ("Claude Code plugin" if os.environ.get("CLAUDE_PLUGIN_ROOT")
              else _plugin_declaring_guard())

    declared = []
    for p in _settings_files():
        try:
            if "charter hook pretooluse" in p.read_text():
                declared.append(p)
        except (OSError, UnicodeDecodeError):
            continue

    if plugin and declared:
        # Not broken — doubled, which is why nobody finds it: two denials for one command
        # read as one stubborn denial. 0.43.1 stopped `init` writing this; planes wired
        # before it still carry the copy, and charter will not delete from a file that is
        # the operator's and git-tracked.
        where = ", ".join(str(p) for p in declared[:2])
        return Result(name, WARN,
                      detail=f"declared twice — the {plugin} dispatches it, and so does "
                             f"{where}",
                      hint=f"charter runs `hook pretooluse` once per declaration, so every "
                           f"Bash call is guarded twice. Remove the charter `hooks` block "
                           f"from {where} and keep the plugin — or disable the plugin and "
                           f"keep the block. charter does not edit that file for you.")
    if plugin:
        if plugin == "Claude Code plugin":
            # `$CLAUDE_PLUGIN_ROOT` means this very process was launched by the plugin, so
            # its hooks are demonstrably live. Nothing to qualify.
            return Result(name, OK, detail="wired (Claude Code plugin)")
        # ENABLED is not LOADED (#261). A plugin's hooks are loaded by the harness at
        # session start, so a plugin installed mid-session — or one whose duplicate
        # settings block was just removed on this check's own advice — is declared for the
        # NEXT session while this one holds no declaration at all. The reporter branched
        # the plane root in that window and nothing refused it.
        #
        # Reaching the handler is the only proof available, which is what `guardseen`
        # exists to record; a sighting from THIS plugin is that proof.
        if _seen.last_source() == _seen.PLUGIN:
            # ...and only for the Claude Code config folder it ran under (#969).
            # `$CLAUDE_CONFIG_DIR` moves the manifest and settings this row just read, so a
            # guard that fired yesterday under `~/.claude` says nothing about a session under a
            # second account's folder — where the plugin can be installed and not yet loaded,
            # #261's window reached from a new direction. `guardseen.folder_standing`, read at
            # the top of this row, is the one place that decides it, for `guard seen` too.
            if standing.doubt is None:
                return Result(name, OK,
                              detail=f"wired (enabled plugin {plugin}) — and it has fired here")
            # Something DID fire from the plugin, so "nothing has fired here yet" would be
            # false beside `guard seen`; and it cannot vouch for this folder, so a tick would
            # be false too. Neither a pass nor a claim that nothing fired (ADR 0009): the row
            # says which of the two it cannot tell, in `guardseen`'s words.
            return Result(
                name, WARN,
                detail=f"enabled plugin {plugin} declares it and a guard has fired from it, "
                       f"but {standing.doubt}. Until a guard fires under the folder in use, "
                       f"nothing shows the plugin is loaded there",
                hint=standing.hint)
        return Result(
            name, WARN,
            detail=f"enabled plugin {plugin} declares it, but nothing has fired here yet — "
                   f"a plugin's hooks load at session start, so this is wired for the NEXT "
                   f"session and THIS one may be unguarded",
            hint="Restart the session (or run a Bash command through it and re-check). If "
                 "you just removed a duplicate `hooks` block on this check's advice, that "
                 "was right — but it was the declaration this session actually had.")
    if declared:
        return Result(name, OK, detail=f"wired ({declared[0]})")
    # The remedy has to name a file THIS session reads. `charter reinit` writes the PLANE's
    # `.claude/settings.json`, and for a chat rooted at `workspaces/<ws>/` the host never
    # reads that file — so the old hint would have been followed, believed, and left the
    # session exactly as unguarded (#851). That is this row's own defect one level down: a
    # remedy that looks like a fix and is not.
    if not session_is_the_plane():
        from . import config as _config
        from .harness import claude_code as _claude_code

        here = session_root()
        # The user settings file of the folder in use (#969). Under `$CLAUDE_CONFIG_DIR`
        # a declaration in `~/.claude/settings.json` reaches no session at all, so naming
        # that file would be a remedy that is followed, believed, and changes nothing.
        user_settings = util.short_path(_claude_code.config_home() / "settings.json")
        return Result(
            name, WARN,
            detail=f"pretooluse is not wired — branch moves in the plane root are NOT "
                   f"refused, and nothing declares it in {here}",
            hint=(f"This session is rooted at {here}, not the plane ({_config.ROOT}), and "
                  f"the host does not walk up — so the plane's .claude/settings.json never "
                  f"reaches here, wired or not. `charter reinit` writes THAT file, so it "
                  f"would not change this session. Declare `charter hook pretooluse` under "
                  f"hooks.PreToolUse in {here}/.claude/settings.json, or in {user_settings}, which "
                  f"every session on that Claude config folder reads — or install the "
                  f"Claude Code plugin."))
    hint = ("The 0.30.0 guard only fires through `charter hook pretooluse`.  "
            "→ charter reinit  (wires it into .claude/settings.json), or "
            "install the Claude Code plugin.")
    folder = _claude_folder(None)
    if folder != Path.home() / ".claude":
        # `charter reinit` decides from `~/.claude` whatever the shell says, because it writes
        # a committed file every folder's sessions read (#969, `commands.
        # _plugin_dispatches_guard`). So under another folder the first remedy above writes
        # nothing whenever `~/.claude` already has the plugin — followed, believed, and
        # changing nothing (#851). Said here, and the remedy that does act on this folder named.
        hint += (f" This session uses the Claude Code config folder "
                 f"{util.short_path(folder)}, and `charter reinit` still decides from "
                 f"~/.claude: it writes nothing if the plugin is installed there. `charter "
                 f"doctor --fix` run from this shell installs the plugin for this folder.")
    return Result(name, WARN,
                  detail="pretooluse is not wired — branch moves in the plane root are "
                         "NOT refused",
                  hint=hint)


def check_harness() -> Result:
    """Which harness this is, and every capability it cannot carry (ADR 0015).

    Charter enforces the same invariants on every harness; what differs is what it can
    *offer*. A missing offer looks exactly like a broken install from the outside — which
    is `check_guard_wired`'s lesson one level up — so each ceiling is named here rather
    than left to be discovered.

    Reported as OK even when the list is long. A ceiling is a fact about the harness, not
    a fault in the plane, and a row that warns every session for something the operator
    cannot fix teaches them to ignore the column.
    """
    from .harness import registry as _harness

    name = "harness"
    current = _harness.current()
    if not current:
        return Result(name, OK, detail="not running inside a harness")
    if _harness.get(current) is None:
        # An empty deficit list here would mean "charter knows of no gaps", and charter
        # knows nothing at all about this runtime — the same sentence rendering two
        # opposite facts. Registered harnesses are the ones whose ceilings have been
        # checked against the binary; anything else is unverified by definition.
        return Result(name, WARN,
                      detail=f"{current} — charter has no record of this harness",
                      hint=(f"Charter enforces what it can here, but nothing has verified "
                            f"which surfaces {current} carries. Register it in "
                            f"`charter/harness/registry.py` (KINDS) with its own deficits, "
                            f"or unset $CHARTER_HARNESS if it was set by mistake."))
    live = _harness.get(current)
    stale = live.stale_wiring() if live else ""
    if stale:
        from . import __version__

        # The remedy is whatever the HARNESS says it is — one sentence, from the one
        # function that composes it (`opencode.unvouched`). This hint used to end
        # "→ charter reinit" on its own authority, and `charter reinit` answered "Up to
        # date — nothing to do": an operator who followed this row was told the plane was
        # fine by the command the row sent them to. `wiring_remedy` and not `upgrade`
        # because `upgrade` writes on the way to the same sentence, and doctor diagnoses.
        remedy = live.wiring_remedy()
        return Result(name, WARN,
                      detail=f"{current} — its plugin is {stale}; charter is "
                             f"{__version__}",
                      hint=("A plugin charter did not write is still a file where a "
                            "working one belongs — 0.40.0's guard never fired, a current "
                            "stamp over a changed body is the same silence with a "
                            "reassuring first line, and a plugin loaded beside charter's "
                            "shares the globals its guards call through. charter reports "
                            "these, never overwrites them."
                            + (f"\n        → {remedy}" if remedy else "")))
    gaps = _harness.deficits(current)
    if not gaps:
        return Result(name, OK, detail=current)
    def _line(d):
        # The remedy sits on the ceiling it answers, not in a footnote: a limit stated and
        # left there reads as "nothing can be done", and the operator stops looking.
        fix = f"  → {d.remedy}" if d.remedy else ""
        return f"        ↳ {d.key}: {d.detail}{fix}"

    listed = "\n".join(_line(d) for d in gaps)
    plural = "" if len(gaps) == 1 else "s"
    return Result(name, OK, detail=f"{current} — {len(gaps)} capability ceiling{plural}\n{listed}")


def check_frame() -> Result:
    """Can `charter <harness>` compose a frame here? (ADR 0018)

    Its own check, sitting beside `check_harness` rather than inside its deficit list:
    tmux is a prerequisite of the FRAME, not a ceiling of any harness, and filing it
    under `check_harness` would tell the reader their harness is limited when it is not
    — `tests/test_doctor_absent_is_not_health.py` already draws exactly that line for a
    check that renders green over something it never actually looked at, and the
    opposite error (naming a harness limit that is not real) is the one `check_harness`'s
    own docstring guards against.

    WARN, never FAIL: `cmd_doctor` exits non-zero only on FAIL, and a machine with no
    tmux — or one too old to meet `tmuxctl.FLOOR` — can still do every bit of charter's
    core work; discover, clone, and run any harness with `--no-frame`. Only `charter
    <harness>` without that flag is affected, and both remedies are named here rather
    than left to be discovered in `docs/frame.md`.

    This row and `charter frame-probe` are also the ONLY places the frame's standing
    capability ceilings are reported at all. They used to be `util.warn` calls inside
    `cmd_launch`, printed microseconds before tmux switched the operator's terminal to
    the alternate screen, where nobody could read them — see
    `commands_frame.frame_ready`'s own docstring for the measurement and the argument.
    Every fact is answerable without starting anything: `tmuxctl.version()` and
    `config.FRAME["slots"]`.

    **Three ceilings, collected rather than branched (#387).** The third —
    `tmuxctl.RESIZE_HOOK_FLOOR`, above `FLOOR` — was reported by neither this row nor
    `frame_ready`, so an operator on tmux 3.2 passed the floor, read a green tick here,
    and had no resize recovery. Written as one list because that is now three
    independent conditions over two version thresholds and a config value, and the
    nested-`if` shape this replaced already had to repeat the slot ceiling in two
    branches to stay honest.

    **A fourth thing used to ride here and does not any more (#895).**
    `_statusline_suppressed_note` appended a `↳` line saying *this session's status line is
    intentionally blank, the frame is drawing instead* (ADR 0019). Charter no longer wires
    a status line into Claude Code, so on every plane charter sets up there is no footer
    for a frame to blank — and the note asked only "am I inside a live frame", which meant
    it would have gone on telling every framed session that a surface it does not have was
    being suppressed. A sentence that is true of nothing is worse than silence: it sends
    the reader looking for a footer to un-blank. The suppression itself is untouched —
    `statusline.a_frame_owns_this_surface` still refuses to draw into a frame, which is
    still right for anyone who wires `statusLine` by hand — only doctor's narration of it
    is gone.
    """
    from . import config
    from .frame import slots as frame_slots, tmuxctl

    name = "frame"
    v = tmuxctl.version()
    if v is None:
        return Result(name, WARN, detail="tmux not found",
                      hint="charter <harness> needs tmux to compose a frame — brew "
                           "install tmux (or your package manager). Without it, "
                           "charter <harness> --no-frame still runs the harness bare.")
    ceilings = []
    if v < tmuxctl.FLOOR:
        # Not "the hotkey palette is disabled" — nothing disables it. `cmd_launch` warns
        # and continues, and `conf_text` emits the bind unchanged; what is actually at
        # risk below the floor is that the bind opens nothing and that the pane-scoped
        # exit-code hooks may not install. `below_floor_message` is the one place that
        # sentence lives, so this row and `--probe` cannot drift apart.
        ceilings.append(tmuxctl.below_floor_message(v))
    if v < tmuxctl.RESIZE_HOOK_FLOOR:
        ceilings.append(tmuxctl.below_resize_hook_message(v))
    missing = frame_slots.unimplemented(config.FRAME["slots"])
    if missing:
        ceilings.append(commands_frame_no_renderer(missing))
    detail = f"tmux {v[0]}.{v[1]}"
    if ceilings:
        return Result(name, WARN, detail=detail, hint=" ".join(ceilings))
    return Result(name, OK, detail=detail)


def commands_frame_no_renderer(missing: list[str]) -> str:
    """`commands_frame.no_renderer_message`, imported lazily.

    A module-level `from .commands_frame import no_renderer_message` would make every
    `charter doctor` import the whole launcher (and, through it, `harness`, `workspace`
    and `frame.palette`) to print one row; the import lives inside a function for the same
    reason `check_frame`'s own `tmuxctl` import does.
    """
    from .commands_frame import no_renderer_message
    return no_renderer_message(missing)


def _read_text(p) -> str:
    """A settings file's text, or ``""`` when it cannot be read. A file charter is not
    allowed to open is not evidence of anything, and a preflight row must render whatever
    it finds rather than raise on it."""
    try:
        return p.read_text()
    except (OSError, UnicodeDecodeError):
        return ""


def check_guard_seen() -> Result:
    """Has a guard ever actually RUN here, and under which harness?

    A sibling of `check_guard_wired`, not a replacement, for the reason that check is itself
    a sibling of `check_plugin_skew`: *"Whether the plane runs as a plugin is an
    implementation detail. Whether the guard fires is the fact the operator needs"* — two
    facts, two rows, so neither can hide behind the other. Declared and dispatched are just
    as separate: a plane root was switched between branches four times and committed to,
    unguarded, while `check_guard_wired` would have reported a tick throughout. The
    declaration was real. Nothing dispatched it.

    **An age, never a verdict.** A plane worked in from a plain terminal has no dispatch and
    is fine; a plane whose guard last fired weeks ago under a harness you have since stopped
    using is the incident. Charter supplies the date and the harness and lets the reader
    draw that line (ADR 0013).

    Silent on a plane nobody has worked in yet — nothing could have dispatched there, and a
    warning on day one is how a row stops being read.
    """
    from . import guardseen as _seen

    name = "guard seen"
    rec = _seen.last()
    standing = _seen.folder_standing()
    if standing.folder_in_doubt:
        # Whatever the sightings — none, a plane nobody has worked in, another harness's —
        # because the remedy is the folder, and every other branch of this row ends in "run a
        # Bash command", which records one more sighting nothing can be compared with (the
        # #970 re-review). The age is kept when there is one: it is still true.
        seen = (f"last ran {_seen_age(rec.get('ts'))} ago under "
                f"{rec.get('harness') or 'an unnamed harness'}, but " if rec else "")
        return Result(name, WARN, detail=f"{seen}{standing.doubt}", hint=standing.hint)
    if rec:
        at = _seen_age(rec.get("ts"))
        where = rec.get("harness") or "an unnamed harness"
        # An age under another Claude Code config folder is not an age of anything in this
        # one (#969). Green here sat under the guard row's warning and told the reader the
        # guard had just run for them. `guardseen.folder_standing` decides it, for this row
        # and for `plane-root guard` alike: a sighting from a registered harness other than
        # Claude Code has no folder to be wrong about and passes through, and one that names no
        # harness, or a name charter has no record of, is unknown and says so.
        if standing.doubt is not None:
            detail = f"last ran {at} ago under {where}, but {standing.doubt}"
            # A settings declaration in the folder the sighting DID run under is still there.
            # It is in a file this folder's sessions never open, and saying it is gone — the
            # branch below — would send the reader looking for an edit nobody made. Said only
            # where it is true: the sighting came from settings, and that file declares it.
            if (_seen.last_source() == _seen.SETTINGS and standing.elsewhere
                    and "charter hook pretooluse" in _read_text(
                        Path(standing.elsewhere) / "settings.json")):
                detail += (f"; its declaration is still in "
                           f"{util.short_path(Path(standing.elsewhere) / 'settings.json')}, a "
                           f"file sessions on the folder in use never read")
            return Result(name, WARN, detail=detail, hint=standing.hint)
        # A sighting is evidence for the declaration that PRODUCED it and for no other. The
        # settings block that fired minutes ago can have been deleted since — on this
        # command's own duplicate-guard advice — and "last ran 0m ago" then invites the
        # reader to conclude the surviving declaration is working (#261). An unrecorded
        # source predates the field and stays unqualified: unknown is not suspect.
        src = _seen.last_source()
        settings_declare = any("charter hook pretooluse" in _read_text(p)
                               for p in _settings_files())
        # Narrow deliberately: `settings` is also what a Codex or opencode dispatch records,
        # and those declarations live in files this check never reads (`~/.codex/config.toml`),
        # so "no settings file declares it" alone would warn at planes that are wired fine.
        # The reported case is specific — the settings block was removed in favour of a
        # plugin — so the plugin has to be the thing that survived it.
        if src == _seen.SETTINGS and not settings_declare and _plugin_declaring_guard():
            return Result(
                name, WARN,
                detail=f"last ran {at} ago under {where}, but from a settings declaration "
                       f"that is no longer there",
                hint="That sighting is not evidence for whatever declares the guard now. "
                     "Run a Bash command in a fresh session and re-check.")
        return Result(name, OK, detail=f"last ran {at} ago under {where}")
    if not _seen.plane_has_been_used():
        return Result(name, OK, detail="plane not worked in yet")
    return Result(name, WARN,
                  detail="no guard has ever run in this plane",
                  hint="Charter's guards reach a session through its harness, so work done "
                       "outside one is unguarded and says nothing about it. If you work "
                       "here through a harness, it is not wired: -> charter reinit")


def _seen_age(ts) -> str:
    from datetime import datetime, timezone

    from . import pieces as _pieces

    try:
        when = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return "?"
    return _pieces.since(when, datetime.now(timezone.utc))


def check_nested_plane() -> Result:
    """Is the plane charter resolved sitting inside ANOTHER plane's ``workspaces/``? (#140)

    `charter.toml` is tracked, so every clone of a plane is a plane, and `charter clone`
    puts clones exactly where an outer plane keeps them. Standing in one, every command
    silently operates on the inner plane — its own vault registry, its own workspace
    pointers, its own `workspaces/`.

    Reported rather than resolved. The ambiguity is genuine: sometimes the inner plane is
    the one you mean, since charter's own dogfooding clones charter into a workspace and
    that clone is a plane you might legitimately manage. Changing `ROOT` resolution is the
    most invasive change available in this codebase and would guess for you; naming it ends
    the silence, which is the actual complaint — the failure is invisible in both
    directions, so nothing tells you the outer plane never saw your command.

    ADR 0013's second rule, applied: a divergence charter can see, charter names.

    WARN, never FAIL: the inner plane works perfectly. It is simply, probably, not the one
    you meant.
    """
    from . import config as _config
    from . import root as _root

    name = "nested plane"
    if not _config.HAS_CONTROL_PLANE:
        return Result(name, OK, detail="no control plane found")
    try:
        outer = _root.enclosing_plane(Path(_config.ROOT))
    except OSError as e:
        return Result(name, WARN, detail=f"not checked ({e})",
                      hint=_NOT_CHECKED_HINT)
    if outer is None:
        # Standing in a nested clone no longer reaches here: `find_root` hops outward
        # through `workspaces/`, so ROOT is already the outer plane and there is nothing to
        # warn about. Say which plane answered anyway — the hop is a correction charter
        # made on the operator's behalf, and ADR 0013's second rule covers charter's own
        # corrections too.
        origin = getattr(_config, "NESTED_ORIGIN", None)
        if origin is not None and origin != _config.ROOT:
            return Result(name, OK,
                          detail=f"standing in {util.short_path(origin)}, acting on "
                                 f"{util.short_path(_config.ROOT)}")
        return Result(name, OK, detail="not nested")
    # Reached only when $CHARTER_ROOT refused the hop, which is the one state where the
    # inner plane really does take the writes.
    return Result(name, WARN,
                  detail=f"pinned inside {util.short_path(outer)}'s workspaces/",
                  hint=("$CHARTER_ROOT points at a plane nested in another one, so vaults "
                        "and workspace pointers go to the inner plane and the outer never "
                        "sees them. Without the override charter would resolve to "
                        f"{util.short_path(outer)}.  → unset CHARTER_ROOT to use it"))


def _ask_rules() -> list | None:
    """`permissions.ask` from the settings THIS SESSION reads — ``None`` when unreadable.

    The session's project settings, not the plane's (#855, the same defect as #851 one
    check over). `permissions` is a host settings key like any other, so the host resolves
    it from the session's own directory and does not walk up. Reading the plane's file
    instead was wrong in both directions for a chat rooted at ``workspaces/<ws>/``: it
    reported the plane's `ask` rules as shadowing a persona's declared tools when they never
    reach that session, and it could not see a rule in the session's own settings that
    genuinely does. This row exists to say *why* pre-approved tools started prompting
    (ADR 0014), so an answer read out of a file the host never opened sends the reader
    hunting in the wrong place.

    Still the project settings file alone, as before — widening to `settings.local.json` and
    `~/.claude/settings.json`, which also carry `permissions`, is a second change and is not
    this one.
    """
    p = session_root() / ".claude" / "settings.json"
    if not p.exists():
        return []
    try:
        doc = json.loads(p.read_text())
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(doc, dict):
        return None
    perms = doc.get("permissions")
    if not isinstance(perms, dict):
        return []
    ask = perms.get("ask")
    return ask if isinstance(ask, list) else []


def _declared_binaries() -> dict[str, set[str]]:
    """``{binary: {persona, …}}`` — every tool any persona declares, and who declares it."""
    from . import persona as _persona
    out: dict[str, set[str]] = {}
    for name in _persona.list_personas():
        try:
            for tool in _persona.effective_tools(name) or ():
                out.setdefault(tool, set()).add(name)
        except Exception:
            continue
    return out


def shadowed_tools(rules) -> set[str]:
    """Declared persona tools that *rules* would force a prompt for.

    Matching is deliberately coarse — the first token inside ``Bash(...)``, plus the blanket
    forms ``Bash`` and ``Bash(*)`` which match everything. Charter is not re-implementing
    the host's matcher; it is answering "would this obviously shadow a tool", and a coarse
    answer that is right about `Bash(kubectl *)` is worth more than a precise one nobody
    maintains.
    """
    declared = _declared_binaries()
    if not declared:
        return set()
    hit: set[str] = set()
    for raw in rules or ():
        if not isinstance(raw, str):
            continue
        rule = raw.strip()
        if rule in ("Bash", "Bash(*)", "*"):
            return set(declared)
        if not rule.startswith("Bash(") or not rule.endswith(")"):
            continue
        inner = rule[len("Bash("):-1].strip()
        head = inner.split()[0] if inner.split() else ""
        head = head.rstrip("*")
        if head and head in declared:
            hit.add(head)
    return hit


def check_ask_rules() -> Result:
    """An `ask` rule that shadows a tool a persona declares.

    ADR 0014 puts pattern-shaped policy in the host's `permissions`, which creates exactly
    one interaction charter must not leave silent: *"a matching ask rule still prompts even
    when the hook returned `allow` or `ask`"*. So `toolgate` can return `allow` for a
    binary the active persona declares and the operator is prompted anyway — the persona's
    tools quietly stop being pre-approved, with nothing naming the cause. That is the
    looks-wired-but-isn't shape this repo has paid for twice (#177, #197).

    It never suggests deleting the rule. The rule is the operator's policy and is probably
    deliberate; charter names the consequence and leaves the choice (ADR 0013).
    """
    name = "ask rules"
    rules = _ask_rules()
    if rules is None:
        return Result(name, WARN, detail="settings.json not readable",
                      hint=_NOT_CHECKED_HINT)
    if not rules:
        return Result(name, OK, detail="none")
    try:
        hit = shadowed_tools(rules)
    except Exception as e:
        return Result(name, WARN, detail=f"not checked ({e})", hint=_NOT_CHECKED_HINT)
    if not hit:
        return Result(name, OK, detail=f"{len(rules)} rule(s), none shadow a persona tool")
    declared = _declared_binaries()
    who = sorted({p for t in hit for p in declared.get(t, ())})
    return Result(name, WARN,
                  detail=f"{', '.join(sorted(hit))} prompt(s) despite being declared by "
                         f"{', '.join(who)}",
                  hint="An ask rule outranks a PreToolUse allow, so charter's persona "
                       "tool-gate cannot pre-approve these. That may be exactly what you "
                       "want — this names it so the prompts are not a mystery.")


def _reinit_target(root: Path | None) -> str | None:
    """The workspace `charter workspace reinit` would repair to fix *root*'s layer — or
    ``None`` when no `reinit` writes this directory at all. A *root* of ``None`` — no git
    root, for :func:`_local_layer_clause` — is no directory, so it matches none.

    `reinit(name)` writes `workspaces/<name>` and each guest checkout inside it
    (`workspace.wire_harnesses`), and nothing else. So a session in `docs/`, in
    `personas/<p>/`, at the plane root, or in a deep directory *inside* a checkout is one
    `reinit` cannot help — Claude Code reads settings from the session's own directory
    (#855), and `reinit` does not write that directory. Naming the command there sends the
    operator to run something that provably cannot clear the row.

    This subsumes the plane-root case rather than guarding it separately: the plane root is
    not a workspace directory, so it answers ``None`` by the same rule as every other
    directory `reinit` does not write.
    """
    from . import workspace as _workspace

    try:
        names = _workspace.list_workspaces()
    except OSError:
        # The LISTING, guarded separately from each entry below. Its `try` sits inside the
        # loop, so an unreadable `workspaces/` raised straight past it, out of this function
        # and out of `charter doctor` — the whole command, not one row (#982 review round 2b).
        return None
    # One worktree listing per repository across every workspace: `guest_trees` asks git for a
    # workspace's pieces (#951), which is what lets a chat in one be told `reinit` reaches it.
    with _workspace.worktree_answers():
        for name in names:
            try:
                if root == _workspace.workspace_dir(name).resolve():
                    return name
                if any(root == tree.resolve() for tree in _workspace.guest_trees(name)):
                    return name
            except OSError:
                continue
    return None


def _how_to_fix(missing: list, plane: dict, plane_local: dict) -> str:
    """The middle sentence of this row's hint: what would actually put the rule in force for a
    chat rooted here. One of three, and the third names no command at all.

    *plane* is the plane's shared file and *plane_local* its local one, each as the row's own
    dry run reads it. They are kept apart because `reinit` carries them to different
    directories — see :func:`_local_layer_clause`.

    Charter writes these settings in exactly two kinds of place — the plane root, and a
    workspace's or checkout's own root — while Claude Code reads them from the session's
    EXACT directory (#855). So for a chat rooted anywhere else (`docs/`, `personas/<p>/`, a
    deep directory inside a checkout) there is no command that puts the rule in force, and
    `charter guard ask` is as inert there as `charter workspace reinit` was before round 1
    stopped naming it: measured, all three rows unchanged after running it. The row is still
    right to warn — the rule genuinely is not in force for that chat, which is what this row
    exists to surface — so what changes is the advice. **A hint with no command beats a hint
    with a command that does nothing** (#982 review round 2).

    Charter is deliberately NOT made to write settings into arbitrary directories to rescue
    the old advice: that is scope creep into directories charter does not manage.
    """
    from . import config as _config

    root = session_root()
    # The plane root is settled FIRST, and without reading `workspaces/` at all: `guard ask`
    # writes here, so the answer cannot depend on whether some other directory is readable.
    # Asked after the stale clause, an unreadable `workspaces/` decided it (#982 round 2b).
    try:
        at_plane_root = root == _config.ROOT.resolve()
    except OSError:
        # Cannot tell where this chat is standing, so take the answer that can only be
        # USELESS and never WRONG. `guard ask` is the right advice at the plane root and
        # merely inert elsewhere; the no-command sentence is false at the plane root, where
        # `guard ask` works — and a false sentence is believed, while an inert one costs a
        # minute (#982 review rounds 2 and 2b).
        at_plane_root = True
    if at_plane_root:
        return "Add it: charter guard ask 'charter handoff *'"
    stale = _stale_layer_clause(missing, plane)
    if stale:
        return stale
    # Before `guard ask` below, and before the sentence that says nothing can put the rule in
    # force: inside a checkout, a rule the plane holds only locally is one `reinit` puts in
    # force, and `guard ask` would write it into the shared file everybody gets (#1031).
    local = _local_layer_clause(missing, plane_local)
    if local:
        return local
    if _reinit_target(root) is not None:
        return "Add it: charter guard ask 'charter handoff *'"
    # Unwired, and the two states read differently. A sentence here makes a claim about a
    # DIFFERENT directory, so it may only say what is true in every state it can be read from
    # — including a workspace whose own layer is behind, which is the state this whole row
    # exists to surface (#982 review round 2). Hence no enumerated guarantee: from here
    # charter cannot see which workspaces are current.
    where = ("charter writes these settings at the plane root and at a workspace's or "
             "checkout's own root, and a chat reads them from the directory it starts in")
    if any(plane.get(h.name) == "present" for h in missing):
        return ("It cannot be put in force for a chat rooted in this directory: " + where +
                ". A chat started in the plane root is gated; charter gates a workspace or a "
                "checkout once it has written the rule there, and this row says so in any "
                "whose layer is behind")
    # `guard ask` is NOT inert here: run from anywhere inside the plane it writes the plane's
    # own settings, and the plane root and every workspace go clean afterwards — measured. It
    # simply cannot gate a chat rooted HERE, which is what the second half says.
    return ("Add it: charter guard ask 'charter handoff *' — that gates a chat started in the "
            "plane root, and reaches workspaces and checkouts by mirroring into them. It "
            "cannot gate a chat rooted in this directory: " + where)


def _stale_layer_clause(missing: list, plane: dict) -> str:
    """The sentence naming `charter workspace reinit` when that is the command that fixes this
    row — or ``""``.

    A session standing in `workspaces/<ws>/` reads that directory's settings and nowhere else
    (#855), so the gate can be missing there while the plane holds it. That is not a plane
    with no rule: nothing needs adding, the layer here is behind, and telling the operator to
    `charter guard ask` would have them write a rule the plane already has.

    Three things must all hold, because each one on its own names a command that does not
    work (#982 review round 1):

    * `reinit` must write THIS directory — :func:`_reinit_target`;
    * the harness actually MISSING the rule must be one whose layer `reinit` carries here. A
      harness that generates no workspace files is one `reinit` copies nothing for, so with
      only opencode lacking the rule the answer is silence, not a command that cannot help.

      **No real plane reaches that branch today, and it is kept deliberately.** Every harness
      but Claude Code is judged against `config.ROOT`, so "missing here" already implies
      "missing at the plane" and the `present` test below has already said no. It is the code
      form of the defect this round fixed — naming a command that does nothing for the harness
      that is actually stale — and the day another harness generates workspace files, deleting
      it turns the clause back into advice that cannot work with nobody left to remember why.
      Its test reaches it with a CONSTRUCTED shape (a patched `workspace_files`), so a passing
      test here is not evidence that any plane exercises it: read it as a fail-safe, not as
      coverage, and do not let a deletion sweep nominate it (#982 review round 1);
    * the plane must hold the rule **by the row's own test** — `apply_ask_rule` against
      `config.ROOT`, the same reading, one root over. `restrictive_rules` was a second
      predicate over `ask`+`deny` flattened, and it disagreed: a plane that DENIES
      `charter handoff` held no ask rule and the clause fired anyway.

    *plane* is that reading, taken in the row's own `try` so ONE `OSError` handler covers both
    roots. There is deliberately no handler of its own here: a harness whose settings raise
    takes the whole row to not-checked before this is reached, and the `except` that used to
    sit here was measured dead — every harness answers `unsupported` or a status for an
    unreadable or malformed file rather than raising (#982 review round 1).
    """
    target = _reinit_target(session_root())
    if target is None:
        return ""
    for h in missing:
        if not h.workspace_files():
            continue
        if plane.get(h.name) == "present":
            return (f"The plane already holds it for {h.name}, so this directory's layer is "
                    f"behind — nothing to add, only to refresh: charter workspace "
                    f"reinit {target}")
    return ""


def _local_layer_clause(missing: list, plane_local: dict) -> str:
    """The sentence naming `charter workspace reinit` when the plane's LOCAL file holds the rule
    and the checkout this chat is in has not been given a copy of it — or ``""``.

    :func:`_stale_layer_clause`'s question about the other file, and a different question,
    because `reinit` carries the two files to different places (`workspace.wire_harnesses`):

    * the shared file (:meth:`Harness.workspace_files`) into a workspace directory and each
      checkout in it, read by Claude Code from the session's own directory only;
    * the local file (:meth:`Harness.checkout_files`) into a checkout ONLY, read at the git
      root as well — so a copy at a checkout's root is in force for a chat anywhere inside it.

    So this asks about the session's GIT ROOT, not its own directory. Before #1031 the row
    named `charter guard ask` at a checkout's root, which writes the SHARED file and changes
    what everybody on the repository gets when the operator chose a local rule; and deeper in,
    it said the rule could not be put in force at all, when one `reinit` does.

    The git root is matched against :func:`_reinit_target` as it is, workspace directories
    included, and can only ever match a checkout: a directory under `workspaces/` that is its
    own git root is a stray clone, not a workspace (`workspace.list_workspaces`). That is also
    why #1024's plane-side reading stays shared-only for :func:`_stale_layer_clause` — a
    workspace directory gets no local file — while this one reads the local file apart.

    The two conditions per harness are the same pair as the shared clause's, for its reasons:
    `reinit` must carry a local file for that harness at all, and the plane's local file must
    hold the rule by the row's own dry run, not merely exist.
    """
    held = [h.name for h in missing
            if h.checkout_files() and plane_local.get(h.name) == "present"]
    if not held:
        return ""
    target = _reinit_target(_local_settings_root(session_root()))
    if target is None:
        return ""
    return (f"The plane's local settings already hold it for {', '.join(held)}, so this "
            f"checkout's copy of them is behind — nothing to add, only to refresh: charter "
            f"workspace reinit {target}")


def _local_ask_rule(h, root: Path, pattern: str) -> tuple[str, str] | None:
    """Claude Code's answer from the `.claude/settings.local.json` files it reads for a session
    at *root* — ``("present" | "malformed", detail)``, or ``None`` when neither decides.

    The shared file is not the only place the rule is in force, and charter itself writes the
    other one: `charter guard ask --local` at the plane root, `reinit` into a checkout. Read
    only the shared file, this row warned in both of those places that a rule charter had just
    written was missing (#986). The two places are measured rather than assumed
    (:data:`claude_code.CHECKOUT_LOCAL_SETTINGS`): the session's own directory, and the git
    root :func:`_local_settings_root` finds — which is why a workspace directory, inside the
    plane's repository, is prompted by the plane's local rule with no copy of its own.

    Asked here and NOT inside `apply_ask_rule`: that is `charter guard ask`'s writer too, and a
    writer that counted a local rule as present would skip writing the shared one somebody
    asked for. Through the writer's own dry run all the same, so "present" and "malformed" mean
    exactly what they mean for the shared file.

    Every harness is asked, and only Claude Code answers: opencode and Codex say `unsupported`
    to a local rule before reading anything, which decides nothing. The two places are Claude
    Code's measurement, so a harness that grows a local file needs its own before this reads
    for it.

    The first file that decides wins, in the order listed. A malformed one therefore answers
    not-checked even when a later file holds the rule: whether the host still reads the
    rest past a file it cannot parse is not measured, and an answer that can only be useless is
    the one this row takes (see `_how_to_fix`).
    """
    top = _local_settings_root(root)
    for where in (root, *([top] if top is not None else [])):
        status, detail = h.apply_ask_rule(where, pattern, local=True, dry_run=True)
        if status in ("present", "malformed"):
            return status, detail
    return None


def check_handoff_gate() -> Result:
    """Does a `charter handoff` wait for the operator's yes here? (chat handoff)

    A handoff's brief becomes a new chat's first message and runs with the operator's
    authority, and the consent is the harness's own `ask` rule for `charter handoff *`,
    which `charter init` writes. So a missing rule is a warning carrying the command that
    adds it — never a repair. Removing the rule is the operator's decision (ADR 0013); this
    row says that, and charter does not put the rule back.

    **Each harness is asked through its own writer**, `apply_ask_rule(dry_run=True)` — the
    write path minus the write — so this row and `charter guard` cannot disagree about what
    "present" means. Claude Code is asked about :func:`session_root`, the directory whose
    settings the host actually reads (#855); the others about the plane, where their rules
    live. A file charter cannot parse or read is a not-checked warning and never "missing":
    telling someone to add a rule to a file charter could not open sends them to edit
    something broken.

    A passing row still names, per harness, what no rule can do: where charter's hook has
    nothing to read a sub-agent or an unattended run from, its `handoff-gate` deficit says so
    on a `↳` line — the shape `check_harness` uses for a ceiling.
    """
    from . import config as _config
    from .commands import HANDOFF_ASK_PATTERN
    from .harness import registry as _harness

    name = "handoff gate"
    rows = []
    plane: dict[str, str] = {}
    plane_local: dict[str, str] = {}
    for h in _harness.all():
        root = session_root() if h.name == _harness.CLAUDE_CODE else _config.ROOT
        try:
            status, detail = h.apply_ask_rule(root, HANDOFF_ASK_PATTERN, dry_run=True)
            if status == "added":
                # Only when the shared file has not decided: it is read first, so a malformed
                # one stays not-checked whatever the local file holds.
                status, detail = (_local_ask_rule(h, root, HANDOFF_ASK_PATTERN)
                                  or (status, detail))
            # The same reading one root over, for the stale-layer clause. Taken HERE so a
            # single `except OSError` covers both roots: a second handler around a second
            # call was measured dead, because every harness answers rather than raising for
            # an unreadable or malformed file (#982 review round 1).
            #
            # The SHARED file only, deliberately, even though the row above counts the local
            # one (#986). This answers "would `reinit` carry the rule here", and `reinit`
            # carries the plane's local rules into a checkout and never into a workspace
            # directory — counted here, the clause would name `reinit` in a workspace
            # directory where it writes nothing that prompts.
            plane[h.name] = h.apply_ask_rule(
                _config.ROOT, HANDOFF_ASK_PATTERN, dry_run=True)[0]
            # The local file, read apart for that reason, for the clause that asks about a
            # checkout's copy of it (#1031). Inside this `try` for the one above's: the only
            # raise is `Path.exists` under a `.claude/` charter cannot enter, and the shared
            # reading beside it is under that directory too.
            plane_local[h.name] = h.apply_ask_rule(
                _config.ROOT, HANDOFF_ASK_PATTERN, local=True, dry_run=True)[0]
        except OSError as e:
            # The settings loaders test `Path.exists` outside their own `try`, and on a file
            # under a directory charter may not enter that raises on Python 3.11-3.13 (3.14
            # answers False) — measured. Unreadable is not missing, and a raise here would
            # take the whole preflight down with it.
            return Result(name, WARN,
                          detail=f"{h.name}'s settings could not be read ({e}) — charter "
                                 f"cannot tell whether `charter handoff` asks first",
                          hint=_NOT_CHECKED_HINT)
        rows.append((h, status, detail))
    broken = next((detail for _h, status, detail in rows if status == "malformed"), None)
    if broken:
        return Result(name, WARN,
                      detail=f"{broken} is not valid — charter cannot tell whether "
                             f"`charter handoff` asks first",
                      hint=_NOT_CHECKED_HINT)
    missing = [h for h, status, _detail in rows if status == "added"]
    if missing:
        # `reinit` INSTEAD of `guard ask`, never both: one sentence telling the operator to
        # add a rule and then that they already have it is a sentence that cannot be acted on
        # (#982 review round 1). And in a directory charter does not wire, neither — see
        # :func:`_how_to_fix`.
        how = _how_to_fix(missing, plane, plane_local)
        return Result(name, WARN,
                      detail="no ask rule for `charter handoff` under "
                             f"{', '.join(h.name for h in missing)}",
                      hint="A handoff's brief becomes a new chat's first message and runs with "
                           "your authority; this rule is the prompt that asks you first, and "
                           f"on Claude Code it asks under bypassPermissions too. {how}. "
                           "Removing it is your choice — this row says so, and charter does "
                           "not put it back.")
    present = [h.name for h, status, _detail in rows if status == "present"]
    gaps = [f"        ↳ {h.name}: {d.detail}" for h, _status, _detail in rows
            for d in h.deficits if d.key == "handoff-gate"]
    return Result(name, OK, detail="\n".join([f"asks first under {', '.join(present)}", *gaps]))


#: The skills the plugin ships. A constant rather than a directory listing because the CLI
#: is installed from a wheel that contains no `skills/` — that directory belongs to the
#: plugin artifact. A test asserts this equals the repo's `skills/`, so the two cannot part
#: company without the suite saying so.
SHIPPED_SKILLS = frozenset({"secrets", "working-in-a-clone", "persona", "browser", "update",
                            "handoff"})


def _is_charter_checkout(root) -> bool:
    """True when *root* is a clone of charter itself.

    Structural, and deliberately so: the marker is charter's own source tree sitting beside
    a `pyproject.toml` that names the distribution. Nothing here depends on how this
    process was installed, which is what the previous test got wrong.
    """
    from pathlib import Path

    root = Path(root)
    if not (root / "charter" / "docsrc.py").is_file():
        return False
    try:
        return "charter-cp" in (root / "pyproject.toml").read_text()
    except OSError:
        return False


def shadowed_knowledge(root) -> dict[str, list[str]]:
    """A plane's own pages and skills that cover something charter already ships.

    Returns {"skills": [...], "docs": [...]} — names only, sorted.

    Empty when the plane *is* charter's own checkout. Its `docs/personas.md` is the very
    page `docs show personas` serves; reporting that as a shadow of itself would make the
    check noise on the one machine most likely to run it.

    That test asks what the ROOT is, not where `docsrc` happened to read from. Keying it on
    `docsrc.source()` looked equivalent and was not: `source()` prefers the packaged copy,
    so it only matched for someone running `python3 -m charter` from the clone. Every
    contributor also has `uv tool install charter-cp` — the README says to — and for them
    the exemption missed and doctor reported all eight of charter's own pages as shadows of
    themselves. Exactly the noise this paragraph promises to prevent.
    """
    from pathlib import Path

    from . import docsrc

    root = Path(root)
    if _is_charter_checkout(root):
        return {"skills": [], "docs": []}

    skills = sorted(
        d.name for d in (root / ".claude" / "skills").glob("*")
        if d.is_dir() and (d / "SKILL.md").is_file() and d.name in SHIPPED_SKILLS
    )
    topics = set(docsrc.topics())
    docs = sorted(
        p.stem for p in (root / "docs").glob("*.md") if p.stem in topics
    )
    return {"skills": skills, "docs": docs}


def check_shadowed_knowledge() -> Result:
    """A plane keeping its own copy of something charter ships.

    This is the failure that produced the check. A plane carried a `setup` skill telling
    engineers to authenticate over SSH and add an SSH key — months after the rule became
    token-only-over-HTTPS and charter's own guard began denying exactly that. Nine skills
    there were in some stage of the same rot. Every one of them looked wired, and nothing
    compared any of them to the CLI they described.

    Drift runs both ways, which is why this reports rather than resolves: the same plane's
    persona page had grown sections upstream never received. A copy is not automatically
    wrong — it is automatically *unwatched*, and that is the whole finding.

    So, like `check_ask_rules`, it never says delete. A plane may be deliberately overriding
    charter's guidance with something org-specific, and that is the operator's call
    (ADR 0013). Charter names what is being shadowed and what it costs.
    """
    name = "shadowed docs"
    # `_config`, imported here, the way every other check in this module reads the root.
    # A bare `config` was never bound in this scope, so this check raised NameError on
    # every single invocation and the `except` below rendered it as a benign environment
    # warning — a mechanism that looks wired and is not, inside the check written to find
    # exactly that (ADR 0014).
    from . import config as _config
    try:
        hit = shadowed_knowledge(_config.ROOT)
    except Exception as e:  # noqa: BLE001 - a preflight line must never be the thing that fails
        return Result(name, WARN, detail=f"not checked ({e})", hint=_NOT_CHECKED_HINT)

    parts = []
    if hit["skills"]:
        parts.append("skill(s) " + ", ".join(hit["skills"]))
    if hit["docs"]:
        parts.append("docs/" + ", docs/".join(f"{d}.md" for d in hit["docs"]))
    if not parts:
        return Result(name, OK, detail="none — charter's own knowledge is not duplicated here")

    return Result(name, WARN, detail=" · ".join(parts) + " duplicate what charter ships",
                  hint="A local copy wins over charter's and is not compared to it, so it "
                       "drifts in both directions unwatched — behind on a feature it never "
                       "learned about, ahead with sections upstream never received. Read "
                       "the shipped one with `charter docs show <topic>`; keep yours only "
                       "where it says something charter's does not.")


def check_workspace_clones() -> Result:
    """Clones that are behind their upstream — in EVERY workspace, not just the active one.

    `doctor` reported a healthy machine while a clone in a non-active workspace sat seven
    commits behind `origin/main`. `sync` defaults to the active workspace, which was empty,
    so it reported success having done nothing (#156). Both were locally truthful and
    jointly misleading, because neither was scoped to the thing that was out of date — and
    a stale clone is not inert, it is what a session reads if it happens to work there.

    **Read from remote-tracking refs; never fetched.** This runs from the SessionStart hook
    and must not reach the network, exactly as `check_plane_root` reads the root's own drift.
    The honest consequence, and it belongs in the output rather than only here: the check can
    **under**-report — origin moving is invisible until something fetches — but it can never
    invent staleness. That is the acceptable direction of failure, and the same discipline
    ADR 0009 sets for error text.

    Only *behind*. A clone with no upstream cannot be behind anything, and one that is
    **ahead** has unpushed work — a different condition, with a different remedy, that
    `sync` would not fix. Reporting either here would send the reader to the wrong command
    and put the row permanently yellow on ordinary planes, which costs the findings that
    matter (`check_memory_indexes` records the same concern).

    WARN, never FAIL: a stale clone is a thing to know, not a broken machine.
    """
    from . import config as _config
    from . import workspace as _workspace

    name = "workspace clones"
    if not _config.HAS_CONTROL_PLANE:
        return Result(name, OK, detail="no control plane found")

    behind: list[str] = []
    unseen: list[tuple[Path, int | None]] = []
    total = 0
    try:
        # Asked with what could not be told beside it (#1043): `list_workspaces` alone left a
        # workspace charter cannot `stat` out, so the row was OK over it on 3.14, and `clones`
        # alone left out a clone whose `.git` it cannot `stat`, which `gitpolicy.scan` names.
        workspaces, unseen = _workspace.read_workspaces()
        looked_for = len(workspaces) + len(unseen)
        unread_ws = len(unseen)
        for ws in workspaces:
            try:
                found, unstatted = _workspace.read_clones(ws)
            except OSError as e:
                # One workspace charter cannot list is named, and the others are still read
                # (#1014) — `gitpolicy.scan`'s shape. Left to the `except` below, it cost the
                # whole row and hid a stale clone one workspace over: #156's blind spot, from
                # one `chmod`. `workspaces/` itself still costs the whole row there, since
                # nothing under it could be counted. No interpreter split reaches this line:
                # the listing refuses on 3.11–3.14 alike.
                unseen.append((_workspace.workspace_dir(ws), e.errno))
                unread_ws += 1
                continue
            unseen.extend(unstatted)
            for clone in found:
                total += 1
                # `@{upstream}` fails cleanly where there is no tracking branch, which is
                # not a fault — see the docstring.
                r = _git_in(clone, "rev-list", "--count", "HEAD..@{upstream}")
                if r.returncode != 0:
                    continue
                n = int(r.stdout.strip() or 0)
                if n:
                    behind.append(f"{ws}/{clone.name} ({n} behind)")
    except (util.ProcTimeout, OSError, ValueError) as e:
        # Narrow, per `check_memory_indexes`: a broad catch here once swallowed a NameError
        # and reported OK, and a check that silently does nothing is worse than no check.
        return Result(name, WARN, detail=f"not checked ({e})",
                      hint=_NOT_CHECKED_HINT)

    # What could not be listed is named beside whatever the rest said, with what clears it
    # (ADR 0009), and the row is never OK while it stands: "none behind" is only true of the
    # workspaces that were read.
    if not behind:
        if unseen:
            return _beside_unread(
                Result(name, WARN, detail=f"{total} clone(s) across {looked_for - unread_ws} of "
                                          f"{looked_for} workspace(s), none behind"), unseen)
        if not total:
            return Result(name, OK, detail="no clones in any workspace — nothing to check")
        return Result(name, OK, detail=f"{total} clone(s) across all workspaces, none behind")
    return _beside_unread(Result(
        name, WARN,
        detail=", ".join(behind[:4]) + (", …" if len(behind) > 4 else ""),
        hint=("→ charter sync --all  (plain `sync` only touches the ACTIVE "
              "workspace, which is how this stays hidden)  "
              "Counted from what the last fetch recorded, so it can under-report "
              "— never a live query, this runs at SessionStart.")), unseen)


def _mirrored_restrictions() -> dict[str, int]:
    """How many of the plane's `ask`/`deny` rules ride in each generated file, by path.

    Asked of every registered harness (`Harness.restrictive_rules`) rather than read out of
    `.claude/settings.json` here: which of the plane's policy travels is a fact about a
    harness's own config format, and a literal in this file is the
    hardcoded-literal-per-harness failure `harness/registry.py` exists to end.

    **Keyed by generated path**, so `check_workspace_harness` counts only what rides in the
    rows it names: a checkout's local file holds up only the plane's local rules, and a
    missing agent file holds up none. The first version counted every rule the plane had and
    printed the sentence beside any finding at all.

    A harness that cannot answer costs the SENTENCE and never the row. The findings are what
    the operator acts on; this only decides whether one more clause is printed beside them,
    so degrading to "say nothing extra" is the direction that cannot mislead. Narrow, per
    `check_memory_indexes` — a broad catch here once swallowed a `NameError` and reported OK.
    """
    from .harness import registry as _registry

    counts: dict[str, int] = {}
    for h in _registry.all():
        try:
            rules = h.restrictive_rules() or {}
        except (OSError, ValueError):
            continue
        for rel, found in rules.items():
            counts[rel] = counts.get(rel, 0) + len(found)
    return counts


def check_workspace_harness() -> Result:
    """Does every workspace still carry charter's layer, and is it the current one? (#850)

    A chat launched in `workspaces/<ws>/` gets its settings from that directory and
    nowhere else — Claude Code does not walk up for them — so the generated
    `.claude/settings.json` there is the whole of whether that chat has a plugin and a
    `$CHARTER_HARNESS`. It is generated from the plane's own settings, so it
    goes stale the moment the plane's do, and nothing else notices.

    **Since #942 it is also the whole of whether the plane's `ask` and `deny` rules are in
    force there**, which is why the hint names that consequence rather than leaving the
    reader to infer it from a filename. A stale plugin list is a poorer chat; a stale
    restriction is a force-prompt rule that does not prompt, and the operator was told it
    applied to everyone on the repo.

    **Regenerate and compare** (`workspace.harness_layer`), which is
    `persona lint --only stale`'s test rather than a second notion of staleness — see that
    function for why a stored diff answers the wrong question.

    **Reads, never writes.** This runs from the SessionStart hook, and a check that healed
    what it found would report every workspace current by having just made it so.

    **The two harnesses that cannot isolate are NAMED, not omitted.** Their config is
    machine-global, so a per-workspace answer has nowhere to live; printing one row for
    Claude Code and nothing for them reads as three ticks, which is the failure
    `base.Deficit` exists to prevent. They sit in the detail rather than in the hint,
    because they are a standing property of those harnesses and not something to go and
    fix — `charter harness list` is where the full sentence lives.

    WARN, never FAIL: a workspace without the layer is a chat that will be poorer than it
    should be, not a broken machine — and `charter workspace reinit` is one command.
    """
    from . import config as _config
    from . import workspace as _workspace

    # One worktree listing per repository for the whole run (review round 4): the check reads
    # every workspace, and a hung git cost 5 s per checkout without it.
    unread: list[tuple[Path, int | None]] = []
    with _workspace.worktree_answers():
        return _beside_unread(_workspace_harness_result(_config, _workspace, unread), unread)


def _workspace_harness_result(_config, _workspace, unread: list) -> Result:
    """:func:`check_workspace_harness`' body, inside its one :func:`workspace.worktree_answers`
    block. Adds to *unread* each directory under `workspaces/` whose kind it cannot tell, which
    the caller says beside whichever verdict this returns (#1043) — one clause for its many
    returns rather than one at each."""
    name = "workspace layer"
    if not _config.HAS_CONTROL_PLANE:
        return Result(name, OK, detail="no control plane found")

    gaps = ", ".join(h for h, _d in _workspace.harness_deficits())
    # A finished clause rather than a bare list of names, for `Deficit.detail`'s own
    # reason: the *why* is the harness's, and two names with no verb beside them read as
    # a failure.
    # NOT "config is machine-global", which is what this said and is false of opencode:
    # an `opencode.json` at the repository ROOT is read. What is true of both, and is the
    # whole of what this aside claims, is that a workspace DIRECTORY is not a place either
    # of them reads config from — so the conclusion survived the correction and only the
    # reason had to go. The `why` belongs to the harness anyway (`Deficit.detail`,
    # `charter harness list`); two names with no verb beside them read as a failure, and
    # a verb charter invented for them read as a fact.
    aside = (f"  ({gaps}: a workspace directory is not a config scope for them, so it "
             f"cannot diverge — charter harness list)" if gaps else "")

    findings: list[tuple[str, str, str]] = []
    total = 0
    try:
        names, unstatted = _workspace.read_workspaces()
        unread.extend(unstatted)
        for ws in names:
            rows = _workspace.harness_layer(ws)
            total += len(rows)
            for rel, status in rows:
                # `harness-edited` is current: the harness added its own approvals to a
                # file charter mirrored, and every rule charter put there is still in it.
                # Warning on it would fire in every clone anybody ever approved anything in.
                if status in ("ok", "harness-edited"):
                    continue
                findings.append((ws, rel, status))
        held = _workspace._held_files()
    except (OSError, ValueError) as e:
        # Narrow, per `check_memory_indexes`: a broad catch here once swallowed a
        # NameError and reported OK, and a check that silently does nothing is worse than
        # no check.
        return Result(name, WARN, detail=f"not checked ({e})", hint=_NOT_CHECKED_HINT)

    if held:
        # Ahead of "nothing to mirror", which would be false here: the plane declares
        # something charter cannot read, and every workspace is keeping its last good copy
        # of it. The first version withdrew those copies and then printed exactly that
        # sentence over a workspace that had just lost `enabledPlugins`, `env` and `deny`.
        # In the harness's own order and undeduplicated: the one harness that holds files
        # names each plane file once, shared first, so a sort or a set here decided nothing
        # a case could see — the deletion sweep charged `sorted` for exactly that.
        sources = ", ".join(held.values())
        return Result(name, WARN,
                      detail=f"not valid JSON: {sources} — every workspace keeps its last "
                             f"good copy of what charter mirrors from it{aside}",
                      hint="Fix that file. charter mirrors nothing new from it while it does "
                           "not parse, and never withdraws what it mirrored before over a "
                           "file it cannot read.")
    if not findings:
        if not total:
            return Result(name, OK,
                          detail=f"nothing to mirror — the plane declares no plugin, env "
                                 f"or ask/deny rule of its own{aside}")
        return Result(name, OK,
                      detail=f"{total} generated file(s) across all workspaces, "
                             f"all current{aside}")
    # No leading arrow — `Result.render` writes one. `check_workspace_clones` carries its
    # own and therefore prints two; that is a wart rather than the convention (76 of the
    # 77 hints in this file start with the command), and not one to copy.
    statuses = {status for _ws, _rel, status in findings}
    # Every state is led by what clears it (review rounds 4 and 5, R4), and `reinit` leads only
    # when it is what clears them all: a hint that leads with a command that changes nothing is
    # the tick that stops a reader. It clears a missing, stale or unwanted file — but not one in a
    # checkout whose record cannot be published, where it writes nothing either.
    def tree_of(ws: str, rel: str) -> tuple[str, str]:
        # One reading for both sets, and `checkout_row`'s: a piece's row is
        # `.worktrees/<repo>/<piece>/…` or an absolute path (#951), so its first segment names no
        # checkout, and every piece in a workspace read as one — an unrecorded marker in one kept
        # `reinit` from leading the hint over a missing file in another. A row of the workspace
        # directory's own belongs to no checkout.
        row = _workspace.checkout_row(ws, rel)
        return ws, str(row[0]) if row else ""

    stuck = {tree_of(ws, rel) for ws, rel, status in findings if status == "unrecorded"}
    reinit_clears = any(status in ("missing", "stale", "unwanted") and tree_of(ws, rel) not in stuck
                        for ws, rel, status in findings)
    first: list[str] = []
    if "unrecorded" in statuses:
        # Ruling H (review round 4): the launch works around this — it writes nothing it could
        # not record first, and keeps every line — and only a person can clear it. The reason is
        # the errno that publish failed with (review round 5, R5), never a guess from a mode bit.
        # What clears it follows that errno (#942 final review): a full disk or a read-only mount
        # has no write access to restore.
        refused = dict.fromkeys(
            f"{os.path.join(ws, _workspace.checkout_label(ws, row[0]))}: "
            f"{_workspace.unrecorded_fix(row[0], 'that checkout')}"
            for ws, rel, status in findings if status == "unrecorded"
            for row in [_workspace.checkout_row(ws, rel)])
        first.append("An 'unrecorded' marker is one charter could not publish, so it writes "
                     "nothing there it could not record first and keeps every exclude line it "
                     "had. What clears it: " + "; ".join(refused) + ".")
    if "unreadable" in statuses:
        # Never "remove it" (#942, review rounds 2 and 3): charter cannot see what is in the file.
        first.append("An 'unreadable' path is one charter cannot read: it is left exactly as it "
                     "is, and restoring read access to it clears this.")
    if "unaccounted" in statuses:
        # Ruling G (#942, review round 3): charter keeps every line it cannot prove unneeded,
        # and says what it could not account for instead of ticking over it. Asked of every
        # finding's checkout and printed once each (review round 4): checkouts sharing one
        # exclude share its reasons, and a filter to the `unaccounted` rows only was a way of
        # not printing them twice that the dedupe now is.
        why = dict.fromkeys(reason for ws, rel, _status in findings
                            for row in [_workspace.checkout_row(ws, rel)] if row
                            for reason in _workspace.unaccounted(row[0]))
        first.append("An 'unaccounted' exclude block is still hiding a path charter cannot prove "
                     "it no longer needs, and keeps hiding it until it can: " + "; ".join(why) + ".")
    if "unlisted" in statuses:
        # #1072: a clone whose worktrees git could not list, so every piece of it went unchecked —
        # no layer, no repair, no row — and this check was green over them. `reinit` clears none of
        # it, so it leads with what does, `gitpolicy.scan`'s remedy for a path it cannot read.
        cannot = dict.fromkeys(
            f"{os.path.join(ws, _workspace.checkout_label(ws, row[0]))}: "
            f"{_workspace.unlisted_fix(row[0])}"
            for ws, rel, status in findings if status == "unlisted"
            for row in [_workspace.checkout_row(ws, rel)] if row)
        first.append("An 'unlisted' .git/worktrees is a clone whose worktrees git could not list, "
                     "so none of them was checked or given charter's layer. What clears it: "
                     + "; ".join(cannot) + ".")
    # #1072: the opposite failure, and only the operator can clear it. A clone and its worktrees
    # share one exclude, so the line for one checkout's file would hide an untracked file of yours
    # at that path in another. Charter leaves the line out: a shared file it wrote shows, and a
    # machine-local one is not written. Asked of every finding's checkout, as `unaccounted` is,
    # and printed whenever one has a reason rather than only beside an `unhidden` row: one row
    # carries one status, and a block both `unaccounted` and `unhidden` reads `unaccounted` — its
    # file of yours must still be named. Deduped: checkouts sharing one exclude share a reason.
    shown = dict.fromkeys(reason for ws, rel, _status in findings
                          for row in [_workspace.checkout_row(ws, rel)] if row
                          for reason in _workspace.unhidden(row[0]))
    if shown:
        first.append("An exclude line left out because it would also hide a file of yours "
                     "('unhidden') leaves a shared file charter wrote showing in that checkout's "
                     "`git status`, and a machine-local one ('withheld') unwritten: "
                     + "; ".join(shown) + ".")
    rest: list[str] = []
    if "tracked" in statuses:
        # Charter never writes a `.charter-generated` git tracks — its own is per-checkout and
        # gitignored — so a tracked one is committed content, and its digests are not charter's
        # word about which files are charter's. Charter ignores it and keeps its own record; the
        # committed one is the checkout owner's to remove.
        rest.append("A 'tracked' marker is a `.charter-generated` git tracks in that checkout. "
                    "Charter never writes one git tracks, so it is not charter's record: charter "
                    "ignores its contents and keeps its own. Remove it from that checkout if it "
                    "is not meant to be committed there.")
    if "harness-behind" in statuses:
        # Its own sentence, and never "remove it": the approvals in that file are the
        # harness's, and the advice that suits a file somebody else wrote destroys them.
        # True of a file charter wrote, of one that was there before charter ever was, and of
        # charter's own write whose record is gone (#942, review rounds 2 and 3).
        rest.append("A 'harness-behind' file is a checkout's local settings file charter cannot "
                    "vouch for as its own write: the harness saves its approvals into that file, "
                    "so charter never rewrites or merges into it, and the plane's machine-local "
                    "rules it lacks are not in force there. Keep it, and add the rule to it by "
                    "hand if that checkout needs it.")
    if "foreign" in statuses:
        # Never "remove it" (review round 5, R2 and R5). In a checkout the file is somebody's own
        # work in their own repository, and it stays hidden while it is there — so the one thing
        # to say is how to commit it on purpose, as a condition, never as advice.
        mine = dict.fromkeys(row[1] for ws, rel, status in findings if status == "foreign"
                             for row in [_workspace.checkout_row(ws, rel)] if row)
        rest.append("A 'foreign' file holds content charter did not write: charter never "
                    "overwrites it, and in a checkout it stays hidden while it is there"
                    + "".join(f" — if this is your own file and you mean to commit it: "
                              f"git add -f {inner}" for inner in mine)
                    + ("" if mine else "."))
    counts = _mirrored_restrictions()
    behind = sum(n for key, n in counts.items()
                 if any(rel == key or rel.endswith(f"/{key}")
                        for _ws, rel, _status in findings))
    if behind:
        # The consequence, not the file. `charter guard ask` says a rule "applies to
        # everyone on this repo", and a chat at `workspaces/<ws>/` reads its own settings
        # file and nothing above it — so a generated file that is stale, missing or foreign
        # is a force-prompt rule that is not in force where the guarded command gets typed
        # (#942). Named only when a row it names carries such rules: a sentence about rules
        # beside a missing agent file sends the reader looking for something that is not
        # there, which is the cry-wolf failure `check_harness` records.
        #
        # "MAY not", because this counts the rules riding in those files and not the ones a
        # given file is short of. A workspace can be stale over `enabledPlugins` alone with
        # every rule already in place, and a row that flatly declared the guard down there
        # would be wrong in the direction that costs a reader their trust in it.
        rest.append(f"The plane's {behind} ask/deny rule(s) ride in these generated files, "
                    f"so where one is not current a chat in that directory may not be "
                    f"prompted or refused by them.")
    if reinit_clears and not first:
        hint = "   ".join([f"charter workspace reinit --all{aside}", *rest])
    else:
        if reinit_clears:
            first.append("charter workspace reinit --all clears the rest.")
        hint = "   ".join([*first, *rest]) + aside
    detail = [f"{os.path.join(ws, rel)} ({status})" for ws, rel, status in findings]
    return Result(name, WARN,
                  detail=", ".join(detail[:4]) + (", …" if len(detail) > 4 else ""),
                  hint=hint)


#: The optional prompt before every cross-repo landing, named by :func:`check_changes` and
#: **never written by charter**.
#:
#: **`--local` is load-bearing in that line, not a convenience.** `charter guard ask`
#: writes the plane's *committed* `.claude/settings.json` by default; `--local` writes the
#: gitignored `.claude/settings.local.json` instead. Consent that travels in a commit
#: enrols a whole team on one person's click, which is exactly why ADR 0003 put reporting
#: consent in user-level config and out of `charter.toml`. A team that genuinely wants the
#: prompt for everybody drops the flag — a decision, made once, visible in a diff.
#:
#: **Charter names it and does not run it** (ADR 0017): both answers are legitimate, and a
#: tool that settles a legitimate choice by writing a line while nobody is looking has made
#: the decision for the operator. Because Claude Code matches on the full command string,
#: the prompt it writes shows *which change and which repo*.
#:
#: There is deliberately no second consent gate behind it either. A prompt the agent
#: satisfies by running one more command is theatre, and an operator who is prompted
#: constantly rubber-stamps within a day — which the security assessment already named as
#: worse than no gate. The floor that matters is `hooks._release_floor_reason`, which
#: denies an unattended landing outright.
LANDING_PROMPT = "charter guard ask --local 'charter change land *'"


def check_changes() -> Result:
    """Cross-repo changes whose records and git disagree — ADR 0013's rule 2.

    *"A divergence charter can see, charter names."* Five of them, all in
    `commands_change.divergences` and `commands_change.stray_branches`: a member landed
    outside charter (so there is no `Charter-Change` trailer and no merge sha, and
    `charter change revert` cannot reach it), a declared landing the default branch no
    longer contains, a declared landing on a commit carrying no trailer, a member that
    landed while a blocker had not, and a member's branch name sitting in a clone that is
    a member of no change.

    **FAIL, not WARN**, and that is the whole of ADR 0013: *"WARN is not a surface. A
    divergence worth naming under rule 2 is worth FAIL."* `cmd_doctor` exits non-zero only
    on FAIL, and that exit code is the only thing that makes the SessionStart wrapper
    print — a partial cross-repo landing nobody is told about is the state this entire
    surface exists to prevent.

    **Every workspace, not just the active one** — `check_workspace_clones`' own finding
    (#156): a change is a per-workspace store, and the one that is half-landed is rarely
    the one you are standing in.

    **Read from what is already on this disk; never fetched.** This runs from SessionStart
    and must not reach the network. The honest consequence, and it belongs in the output
    rather than only here: the check can **under**-report — a merge somebody else pushed is
    invisible until something fetches — but it can never invent a divergence. That is the
    acceptable direction of failure and the same discipline ADR 0009 sets for error text.

    The OK row names :data:`LANDING_PROMPT`, which is the one place charter tells an
    operator that the prompt exists. It is on the OK row rather than in a hint because a
    `hint` renders only when the status is not OK, and a plane whose changes are all clean
    is exactly the plane where the question *"do I want a prompt before each landing?"* is
    worth asking.
    """
    unread: list[tuple[Path, int | None]] = []
    return _beside_unread(_changes_result(unread), unread)


def _changes_result(unread: list) -> Result:
    """:func:`check_changes`' body. Adds to *unread* each directory under `workspaces/` whose
    kind it cannot tell, which the caller says beside whichever verdict this returns (#1043):
    `list_workspaces` alone dropped it, and the row was OK on 3.14 over changes it never read."""
    from . import change as _change
    from . import commands_change as _cc
    from . import config as _config
    from . import workspace as _workspace

    name = "changes"
    if not _config.HAS_CONTROL_PLANE:
        return Result(name, OK, detail="no control plane found")

    found: list[str] = []
    unreadable: list[str] = []
    total = 0
    try:
        names, unstatted = _workspace.read_workspaces()
        unread.extend(unstatted)
        for ws in names:
            # The `changes/` it could not list is named beside the verdict, not read as none
            # (#1084).
            records, refused, missed = _change.read_all(ws)
            unread.extend(missed)
            total += len(records)
            for slug, complaint in refused:
                unreadable.append(f"{ws}/{contain.readable(slug)}: {complaint}")
            for rec in records:
                for line in _cc.divergences(ws, rec):
                    found.append(f"{ws}/{rec['change']}: {line}")
            for line in _cc.stray_branches(ws):
                found.append(f"{ws}: {line}")
    except (util.ProcTimeout, OSError, ValueError) as e:
        # Narrow, per `check_memory_indexes`: a broad catch here once swallowed a NameError
        # and reported OK, and a check that silently does nothing is worse than no check.
        return Result(name, WARN, detail=f"not checked ({e})", hint=_NOT_CHECKED_HINT)

    # A record that did not parse is its own answer and is NOT folded in with the
    # divergences: "charter cannot read this file" and "git disagrees with this file" send
    # the reader to two different places, and one count covering both would send them to
    # neither. It is still a FAIL — a change nobody can read is a change nobody can land.
    if unreadable:
        shown = "; ".join(unreadable[:3])
        if len(unreadable) > 3:
            shown += f" (+{len(unreadable) - 3} more)"
        return Result(name, FAIL, detail=f"unreadable record(s): {shown}",
                      hint="Fix the file the message names — the key set is closed at both "
                           "ends, so an unknown or missing key is named rather than "
                           "ignored. `charter change list` prints the same complaint.")
    if found:
        shown = "; ".join(found[:3])
        if len(found) > 3:
            shown += f" (+{len(found) - 3} more)"
        return Result(name, FAIL, detail=shown,
                      hint="Charter cannot stop a browser and does not pretend to — this "
                           "is the half that makes the guard honest. Read from what is "
                           "already fetched, so it can under-report and never invent. "
                           "`charter change show <slug>` is the whole picture.")
    if not total:
        return Result(name, OK, detail="none")
    return Result(name, OK,
                  detail=f"{total} change(s), none divergent · optional prompt before "
                         f"each landing: {LANDING_PROMPT}")


def check_inventory() -> Result:
    """Can this plane clone anything?

    Asked of `inventory.repos()` rather than the file's own count, because a plane can
    clone its own repo without ever running `discover` — the root's `origin` says what it
    is (`inventory.plane_repo`). `discover` is therefore optional, and a plane that can
    reach the repo it was made for is not missing anything.

    Warning regardless would be the permanently-yellow preflight `check_memory_indexes`
    records the case against — and the nag is expensive in its own right: on a personal
    account `discover` enumerates every repo the owner has, and writes that listing into
    a tracked `inventory/repos.json`. Telling someone to publish sixty repos to silence a
    row about the one they already have is worse advice than saying nothing.
    """
    n = inventory.load().get("count", 0)
    if n:
        return Result("inventory", OK, detail=f"{n} repos mapped")
    if inventory.repos():
        return Result("inventory", OK,
                      detail="not built — this plane's own repo is clonable without it")
    return Result("inventory", WARN,
                  detail="empty, and this plane's own repo could not be derived",
                  hint="Run: charter discover  (builds inventory/repos.json).")


def check_vaults() -> Result:
    # Kept non-fatal: no vaults is a perfectly valid state, and this check runs
    # from the SessionStart hook — it must never block a session.
    from .secrets import base, registry

    try:
        vs = registry.vaults()
    except base.VaultError as e:
        return Result("vaults", WARN, hint=str(e))
    if not vs:
        return Result("vaults", OK, detail="none configured")
    bad, no_identity, timed_out = [], [], []
    # The loose-directory report, collected as (path, mode) rather than scraped out of
    # `health()`'s sentence (#471). `_loose_dir_note` deliberately does not set `healthy`
    # False — a directory another account can list is not an unreachable vault, and this
    # check runs from the SessionStart hook where it must not hold up a session — so the
    # only way it reaches an operator through `doctor` is a note on the green line. Keyed
    # by resolved path: several vaults normally share `.charter/`, and one directory is one
    # `chmod`, not one per vault.
    loose: dict = {}
    for name in vs:
        try:
            prov = registry.provider_for(name)
            # A vault that declares the identity it is read through, whose variable is
            # not set, is broken in a way `health()` cannot see: `op` answers with "no
            # items" or a permission error, so it reads as an empty or misconfigured
            # vault rather than as a missing credential. Separated from `bad` because
            # the fix is `export`, not anything about the vault.
            prov.env_overlay()
            healthy, _detail = prov.health()
            for d, mode in prov.loose_dirs():
                loose[str(d)] = (d, mode)
        except util.ProcTimeout:
            # `op` reaching a desktop app that is waiting on a biometric prompt looks
            # exactly like a hang. Naming it beats inheriting the caller's whole budget.
            timed_out.append(name)
            continue
        except base.VaultError as e:
            if "is unset" in str(e):
                no_identity.append(name)
                continue
            healthy = False
        if not healthy:
            bad.append(name)
    # Deepest first, matching the order `charter vault list` prints, and on EVERY return
    # below rather than only the green one: a vault that times out or has no identity is a
    # different problem, and a loose state directory does not stop being one while it is
    # being fixed. Dropping the note on those paths is how it would come back to being
    # reported only in conditions nobody is in.
    loose_note = base.loose_dir_note(
        sorted(loose.values(), key=lambda pm: len(Path(pm[0]).parts), reverse=True))

    def _with_note(*parts: str) -> str:
        return "; ".join([p for p in parts if p])

    if timed_out:
        return Result("vaults", WARN, detail=_with_note(f"{len(vs)} configured", loose_note),
                      hint=f"timed out reading: {', '.join(timed_out)} — the provider CLI "
                           f"did not answer within {CHECK_TIMEOUT:g}s (1Password waiting on "
                           f"a biometric prompt looks exactly like this).")
    if no_identity:
        srcs = []
        for n in no_identity:
            srcs += [f"${s}" for s in (vs[n].get("config", {}).get("env") or {}).values()]
        return Result("vaults", WARN, detail=_with_note(f"{len(vs)} configured", loose_note),
                      hint=f"identity variable unset for: {', '.join(no_identity)} — "
                           f"export {', '.join(sorted(set(srcs)))} (charter will not fall "
                           f"back to an ambient token; that would read the vault as "
                           f"someone else)")
    if bad:
        return Result("vaults", WARN, detail=_with_note(f"{len(vs)} configured", loose_note),
                      hint="not reachable: " + ", ".join(bad))
    # Says what was actually checked, and nothing more. This line used to read "all
    # healthy", which is a claim about resolution that nothing here tests: `health()`
    # asks whether the vault is REACHABLE and how many items it holds, and deliberately
    # never resolves — `vault list` and `doctor` call it routinely, and resolving would
    # hit 1Password every time and could prompt for re-auth.
    #
    # Issue #55: "6 configured, all healthy" printed minutes apart from every resolution
    # through those vaults failing. Both were true. A reference can point at an item that
    # no longer exists while the vault holding it is perfectly reachable — and `doctor` is
    # the command you run BECAUSE something is wrong, so a green line about the broken
    # subsystem does not merely fail to help, it steers you away from the cause. It cost
    # the reporter forty minutes mid-incident.
    # Named on the green line rather than raised to a WARN, and that is the whole
    # judgement. A committed `vaults.json` deciding which path on this machine is a vault
    # is worth an operator's eye once (#331) — but pointing `--file` outside the plane is
    # a SUPPORTED configuration that `commands_secrets` recommends by name, so warning
    # about it every session start would be a check crying wolf at a working plane, which
    # this file has already paid for twice (#171, #55). State it; do not resolve it.
    notes = [loose_note] if loose_note else []
    outside = registry.shared_files_outside_plane()
    if outside:
        notes.append(f"vaults.json points outside the plane: {', '.join(outside)}")
    malformed = registry.malformed_shared()
    if malformed:
        notes.append(f"vaults.json entries ignored (not an object): {', '.join(malformed)}")
    detail = f"{len(vs)} reachable (references not resolved)"
    return Result("vaults", OK, detail="; ".join([detail, *notes]),
                  hint="Resolve them for real: charter vault verify")


#: Entry count at which a memory index is worth curating. Not a cap and not a
#: truncation point — charter injects a bounded digest, so a long index costs
#: nothing at session start. It is a nudge toward `charter persona optimize`.
_INDEX_LINES_WARN = 150


def check_version_lock() -> Result:
    """`[charter] version` vs what is installed.

    Opt-in: a control plane that pins nothing is a perfectly normal state and
    reports OK, not a nag. When it does pin, drift is a WARN rather than a FAIL —
    this runs from the SessionStart hook, and charter must never make its own
    tooling the reason someone cannot work (being offline is not a defect).
    """
    from . import __version__, config as _config, instance as _instance
    try:
        locked = _instance.locked_version(_instance.load(_config.ROOT))
    except Exception as e:
        return Result("version lock", WARN, detail=f"not checked ({e})",
                      hint=_NOT_CHECKED_HINT)
    if not locked:
        return Result("version lock", OK, detail="not pinned")

    from . import channel, update
    if channel.is_dev():
        # BEFORE either comparison below. On a plane following `main` both answer the wrong
        # question: equal numbers said "plugin in sync" or "CLI in sync" for a plane session
        # start refuses (a dev build prints the number of the release it was built from), and
        # unequal ones named a plugin update or the shared-install note, both of which move
        # the plane toward the pin (#1018). WARN, as drift is here, for this docstring's
        # reason. The words are `pin_beside_dev`'s, which every other surface prints.
        conflict, ways, _brief = update.pin_beside_dev()
        return Result("version lock", WARN,
                      detail=f"pinned {locked} on a plane following `{update.DEV_BRANCH}`: "
                             f"{conflict}",
                      hint="; ".join(ways))
    # The pin is measured against the PLUGIN, because the plugin is the only part of
    # charter that is genuinely per-plane: Claude Code installs it per project, out of a
    # cache holding every version side by side. Measuring it against the machine-global
    # binary is what made the pin unhonourable — no plane can own that binary, so the drift
    # it reported had no fix that did not break another plane (#127).
    plugin = update.plugin_version_here()
    if plugin is not None:
        if plugin == locked:
            return Result("version lock", OK, detail=f"pinned {locked}, plugin in sync")
        return Result("version lock", WARN,
                      detail=f"pinned {locked}, plugin here runs {plugin}",
                      hint=f"Run: {update.PLUGIN_SYNC_CMD}  (this project only — a plugin "
                           f"is installed per project, so no other plane moves)")

    # Not running under the plugin: a `charter` typed in a terminal cannot see which plugin
    # version serves this project. Say that, and compare what CAN be seen — but never call
    # the machine-global CLI "this plane's version", which is the conflation #127 is about.
    if locked == __version__:
        return Result("version lock", OK,
                      detail=f"pinned {locked}, CLI in sync (plugin not visible from here)")
    # "To move THIS plane only" is the harness's answer, not one command for everybody.
    # Naming the Claude Code plugin here told every opencode and Codex reader — and every
    # bare terminal, which is what this branch IS — to run a command belonging to a
    # harness they are not in. Same defect as `cmd_version_sync`'s, same fix.
    from . import harness as _harness

    h = _harness.get(_harness.current())
    # `dry_run`: this row only needs the sentence. The real call moves the artifact, and
    # under opencode that rewrote the global plugin every project loads, from a check the
    # SessionStart hook runs (#1039). `version sync` and `update` are where it moves.
    status, detail = h.upgrade(_config.ROOT, dry_run=True) if h else ("absent", "")
    move = (f". To move THIS plane only: {detail}" if status == "manual"
            else f". {detail}" if status == "absent" and detail
            else "")
    return Result("version lock", WARN,
                  detail=f"pinned {locked}, CLI is {__version__}",
                  hint=f"{update.SHARED_INSTALL_NOTE}{move}")


def check_news_adoption() -> Result:
    """What this version brought that this plane has not taken up.

    The only surface besides `charter update` where a suggestion reaches somebody. NOT the
    session-start hook: each probe is real work, and running every one of them on every
    session start is the cost `update.py` exists to keep off the status line's clock.

    WARN rather than OK for pending entries, and WARN rather than FAIL: an un-adopted
    feature is not a broken plane (`cmd_doctor` exits non-zero only on FAIL), but a green
    tick over "there are three things here for you" is a row nobody ever reads twice.
    """
    from . import news

    try:
        entries = news.released()
    except Exception as e:
        return Result("news", WARN, detail=f"not checked ({e})", hint=_NOT_CHECKED_HINT)
    pending, unchecked = [], []
    for e in entries:
        status, _why = news.probe(e)
        if status == news.PENDING:
            pending.append(e)
        elif status == news.UNKNOWN:
            unchecked.append(e)
    if not pending and not unchecked:
        return Result("news", OK, detail="nothing to adopt")
    bits = []
    if pending:
        bits.append(f"{len(pending)} not adopted here")
    if unchecked:
        # Named separately, never folded into the count. "Could not tell" and "you do not
        # have it" are different answers, and merging them is how a probe that quietly
        # stopped working reads as a feature you keep declining.
        bits.append(f"{len(unchecked)} unchecked")
    return Result("news", WARN, detail=", ".join(bits),
                  hint="See them: charter news --pending")


def check_memory_indexes() -> Result:
    """Every memory base's MEMORY.md must agree with the files beside it.

    A dangling link makes `charter recall` surface a hit nobody can read; an
    unindexed file is a memory the index — and therefore the SessionStart digest
    — never mentions. Neither needs a concurrency bug to happen: MEMORY.md is
    append-heavy and edited by many agents and humans at once, so a merge
    resolved by taking one side drops the other's line while its file survives.
    That is exactly how both showed up in a real control plane.

    WARN, never FAIL: drift is a hygiene problem, and doctor's blockers list means
    "you cannot work" — an out-of-step index does not stop you cloning a repo.
    (An earlier version of this note justified the same choice with "this runs from
    the SessionStart hook, which must never block a session". It does not: `hooks.py`
    never imports this module. Right conclusion, wrong reason.)
    """
    from . import config, memstore, persona, workspace

    bases = []
    # What was not read, named beside the verdict. It opens with the directories under
    # `workspaces/` whose kind charter cannot tell (#1043): `list_workspaces` alone dropped them,
    # and their bases with them, so the row was OK on 3.14 over a plane it had not read.
    unread: list[tuple[Path, int | None]] = []
    try:
        for name in persona.list_personas():
            bases.append((name, persona.memory_dir(name)))
        bases.append((config.SHARED_PERSONA, persona.memory_dir(config.SHARED_PERSONA,
                                                                shared=True)))
        names, unread = workspace.read_workspaces()
        for name in names:
            bases.append((f"ws:{name}", workspace.memory_dir(name)))
    except OSError as e:
        # Only an unreadable/absent tree is tolerated. A broader `except` here once
        # swallowed a NameError and reported OK — a check that silently does
        # nothing is worse than no check.
        return Result("memory indexes", WARN, detail=f"not checked ({e})",
                      hint=_NOT_CHECKED_HINT)

    dangling = unindexed = 0
    worst = []
    large = []
    # WHICH KIND of base drifted, not just how much. The hint used to name
    # `charter persona optimize` for every base including `ws:` ones, whose loop never
    # touches a workspace — so it ran cleanly, fixed nothing, and left the drift reading as
    # repaired. A remediation hint that silently no-ops is worse than no hint at all.
    unindexed_kinds: set[str] = set()
    large_kinds: set[str] = set()
    refused = []
    unread_bases = 0
    for label, mem_dir in bases:
        # Asked through `workspace._existence`, not `Path.exists`, which gave two wrong answers
        # for a base inside a workspace at mode 000 (#1014). On 3.11–3.13 it raised, and
        # returning `not checked` for that hid every other base with it. On 3.14 it answers
        # False, so the base was skipped as absent and then counted among the consistent ones —
        # as was a base that is a symlink loop, on every interpreter. A base charter cannot
        # check is named, and the rest are still read.
        there, code = workspace._existence(mem_dir, follow=True)
        if there is False:
            # Not there THROUGH a link is not nothing there (#1043). A `memory/` that is a link to
            # nothing was skipped as absent, so the refusal below never met the one base it is
            # for — a dangling link out of the plane. Asked of the link itself.
            there, code = workspace._existence(mem_dir)
        if there is None:
            unread.append((mem_dir, code))
            unread_bases += 1
            continue
        if not there:
            continue
        # LISTED before anything is read from it (#1043). `Path.glob` answered an empty list for
        # a directory it may not read, so `memstore.files` said "no memories" of a base at mode
        # 000 or 333 and the drift below described a store nobody had listed: consistent, or its
        # indexed memories dangling. A link to nothing lists as nothing and goes on. Listed the
        # way `memstore.files` lists (#1084), so a base at mode 666 — listable, its memories not
        # `stat`-able — is named here too, rather than read as an index charter will not touch.
        missed = memstore.read_files(mem_dir)[1]
        if missed:
            unread.extend(missed)
            unread_bases += 1
            continue
        # Asked FIRST, and reported on its own terms. A refused index answers "nothing is
        # listed", which is what an empty base answers too — so without this the drift
        # numbers below describe a store charter is declining to touch as though it were
        # merely untidy, and point `optimize` at a repair that cannot run (#349).
        why = memstore.index_refusal(mem_dir)
        if why:
            refused.append(f"{label}: {why}")
            continue
        d = memstore.index_drift(mem_dir)
        if d["dangling"] or d["unindexed"]:
            dangling += len(d["dangling"])
            unindexed += len(d["unindexed"])
            if d["unindexed"]:
                unindexed_kinds.add("workspace" if label.startswith("ws:") else "persona")
            worst.append(f"{label} ({len(d['dangling'])} dangling, "
                         f"{len(d['unindexed'])} unindexed)")
        # Growth signal. An index only ever appends, so a long-lived persona's grows
        # without bound and nothing says so — you have to already suspect you need
        # `persona optimize`. Not truncation: charter injects a bounded digest at
        # SessionStart, so nothing is silently dropped. Just a nudge to curate.
        n = memstore.index_size(mem_dir)
        if n >= _INDEX_LINES_WARN:
            large.append(f"{label} ({n} entries)")
            large_kinds.add("workspace" if label.startswith("ws:") else "persona")

    def row(status: str, detail: str, hint: str = "") -> Result:
        # Every verdict below is about the bases that were read, so each one says beside it
        # which were not, with what clears each (ADR 0009) — and none of them is OK while one
        # is unread. Said after the finding rather than instead of it: the finding is still
        # true of the bases it describes (#1014).
        return _beside_unread(Result("memory indexes", status, detail=detail, hint=hint), unread)

    if refused:
        # Ahead of drift and growth because it outranks them: those are hygiene, this is a
        # committed file redirecting charter's own writes, and the remedy is to fix that
        # file rather than to run any curation command.
        return row(WARN,
                   detail=f"{len(refused)} index(es) charter will not touch",
                   hint="; ".join(refused[:2]) + (", …" if len(refused) > 2 else "")
                        + "  → this is a defect in a committed file: replace the link "
                          "with a real MEMORY.md")
    if not worst and not large:
        return row(OK, detail=f"{len(bases) - unread_bases} base(s) consistent")
    hint = ", ".join(worst[:4]) + (", …" if len(worst) > 4 else "")
    if unindexed:
        for kind in sorted(unindexed_kinds):
            hint += f"  → charter {kind} optimize --all --apply  (links unindexed files)"
    if dangling:
        hint += "  → a dangling link is proposal-only: prune it, or write the memory it names"
    if large:
        if hint:
            hint += "  "
        hint += ("large: " + ", ".join(large[:4]) + (", …" if len(large) > 4 else "")
                 + "".join(f"  → charter {k} optimize <name>" for k in sorted(large_kinds))
                 + "  (curate; growth is not a defect)")
    if not worst:
        return row(WARN, detail=f"{len(large)} large index(es)", hint=hint)
    return row(WARN, detail=f"{dangling} dangling, {unindexed} unindexed", hint=hint)


def check_front_door() -> Result:
    """The plane's declared default persona still names a persona that exists.

    Both rungs that can declare one — ``charter.toml``'s ``[persona] default`` and the
    legacy ``personas/.default`` — validate their value and resolve to ``None`` when the
    persona was renamed or deleted. That resolution is right (no identity beats a broken
    one) and it used to be the whole response: the plane silently lost its front door, and
    every surface that would have shown one simply showed nothing.

    Silence is how ``personas/.default`` came to ship, test green, and be adopted by
    nobody. The replacement does not get to inherit it.

    WARN, never FAIL, on the same reasoning as :func:`check_personas`: doctor's blockers
    mean "you cannot work", and a plane with no persona still clones, still reaches its
    forge, still runs.
    """
    from . import config, instance as _instance, persona
    name = "front door"
    try:
        declared = _instance.default_persona_of(_instance.load(config.ROOT))
        legacy = (config.PERSONAS_DIR / ".default")
        legacy_name = legacy.read_text().strip() if legacy.exists() else ""
    except Exception as e:
        return Result(name, WARN, detail=f"not checked ({e})", hint=_NOT_CHECKED_HINT)

    # charter.toml first: it is the rung that wins, so it is the one whose breakage
    # actually costs the plane its identity.
    for value, where in ((declared, "charter.toml [persona] default"),
                         (legacy_name, "personas/.default")):
        if not value:
            continue
        if persona.def_path(value).exists():
            return Result(name, OK, detail=f"'{value}' via {where}")
        return Result(
            name, WARN,
            detail=f"{where} names '{value}', which is not a persona — this plane has no "
                   f"front door and every session starts with no identity",
            hint=f"charter persona default <name>  (or `charter persona create {value}`)")

    # Nothing declared. Legitimate — charter never invents a front door — but on a plane
    # that HAS personas it is worth saying once, here, that the roster block can never
    # fire: the level is read from the acting persona, and there is none. Said in doctor
    # rather than on every prompt, because a plane may mean exactly this.
    try:
        others = [n for n in persona.list_personas() if not n.startswith("_")]
    except Exception:
        others = []
    if others:
        return Result(name, OK,
                      detail=f"none declared — {len(others)} persona(s) exist, so routing "
                             f"advice is inert (no acting persona means no `routing:` level)",
                      hint="charter persona default <name>")
    return Result(name, OK, detail="none declared")


def check_persona_grant() -> Result:
    """The ACTIVE persona is broken, and is still auto-approving tools (#343).

    `toolgate.decide` asks the active persona what its tools are and never asks whether
    the persona is well-formed. `charter persona lint` calls it broken; the gate honours
    it anyway. Two checks read one file, answer different questions about it, and only one
    of them sits on the path that removes a prompt.

    **Why this reports rather than revokes.** #343's own suggested direction (1) — have
    the gate ignore a persona with non-empty ``structural_errors`` — was measured before
    being declined, in `tests/test_broken_persona_still_grants.py`. After #342 it closes
    nothing: `load()` returns None for a reference that is not a name, so a broken
    reference contributes no tools at all, and what survives is the persona's own
    ``tools:`` plus what a reader of those same files would compute. Revoking that would
    take away a grant the operator wrote by hand and give back no containment.

    It would also take it away **silently**, which is the part that decided it. The gate's
    production output path emits nothing when `decide` declines — a lost grant looks
    exactly like a persona that never declared the tool, and the operator gets an
    unexplained prompt with nothing to connect it to the typo that caused it. Reporting is
    the half that can be done without that cost, and the half that was actually missing.

    Deliberately separate from :func:`check_personas`, which reports the roster's health
    and would say "4 with error(s)" whether or not any of them were the acting identity.
    The pairing is this check's whole content: *this* persona, *these* binaries, right
    now. Silent when the active persona is well-formed — the `tools:` grant is the
    designed behaviour (#329) and a check that fired on it would be noise on every plane.

    The mirror of :func:`check_ask_rules`, which names the case where a persona's tools
    quietly *stop* being pre-approved. This one names where they quietly keep going.
    """
    name = "persona grant"
    from . import persona
    try:
        active = persona.resolve_active()
        if not active:
            return Result(name, OK, detail="no active persona")
        issues = persona.structural_errors(active)
        if not issues:
            return Result(name, OK, detail=f"'{active}' is well-formed")
        tools = sorted(persona.effective_tools(active))
        if not tools:
            # Broken but granting nothing — `check_personas` already reports the break,
            # and saying it twice in different words is how a preflight stops being read.
            return Result(name, OK, detail=f"'{active}' is broken but grants no tools")
    except Exception as e:
        # Only ever advisory. A check that crashes the preflight over a persona file is
        # worse than the divergence it reports.
        return Result(name, WARN, detail=f"not checked ({e})", hint=_NOT_CHECKED_HINT)
    why = "; ".join(m for _level, m in issues[:2])
    return Result(name, WARN,
                  detail=f"'{active}' is broken and still auto-approves "
                         f"{', '.join(tools)}",
                  hint=f"{why}  → charter persona lint {active}  (the gate reads this "
                       f"persona's tools whether or not it loads cleanly, so a prompt you "
                       f"expected to see may not appear)")


def check_personas() -> Result:
    """Roster config health — `persona lint` across every persona, summarised.

    `lint` could always find a dangling ``extends:``, an inheritance cycle, or a
    charter naming a skill no sub-agent can invoke; nothing ever ran it. It was in no
    hook and in no other command, so it reported drift only to someone who already
    suspected drift. This is the check running by itself, in the preflight a developer
    already runs.

    One line, not a per-persona dump: the detail names what is wrong and the hint
    points at `charter persona lint`, which has room to explain. WARN, never FAIL —
    doctor's blockers list means "you cannot work", and an untidy persona does not stop
    you cloning a repo or reaching the forge.

    Affordable only because :func:`persona._installed_skills` is memoised: the walk it
    performs is ~27ms and `lint` calls it once per persona, which is what made a
    13-persona sweep cost 364ms.
    """
    from . import persona
    try:
        names = persona.list_personas()
    except Exception as e:
        return Result("personas", WARN, detail=f"not checked ({e})",
                      hint=_NOT_CHECKED_HINT)
    if not names:
        return Result("personas", OK, detail="none defined")

    errors: dict[str, int] = {}
    warns: dict[str, int] = {}
    drafts: list[str] = []
    for n in names:
        try:
            issues = persona.lint(n)
            if persona.is_draft(n):
                drafts.append(n)
        except Exception:
            # A persona charter is a file humans edit; a malformed one must not take
            # down the command you run *because* something is wrong.
            errors[n] = errors.get(n, 0) + 1
            continue
        for level, _msg in issues:
            (errors if level == "error" else warns)[n] = \
                (errors if level == "error" else warns).get(n, 0) + 1

    if not errors and not warns:
        return Result("personas", OK, detail=f"{len(names)} persona(s), all clean")

    bits = []
    if errors:
        bits.append(f"{len(errors)} with error(s): {', '.join(sorted(errors))}")
    if drafts:
        bits.append(f"{len(drafts)} draft: {', '.join(sorted(drafts))}")
    soft = sorted(set(warns) - set(drafts))
    if soft:
        bits.append(f"{len(soft)} with warning(s): {', '.join(soft)}")
    return Result("personas", WARN, detail=" · ".join(bits),
                  hint="charter persona lint  (per-persona detail and how to fix each)")


def check_vault_registry_divergence() -> Result:
    """The two halves of the vault registry, disagreeing about the same vault.

    `registry.load_registry` layers local over shared **per field**, so where both halves
    define one, the local value is what every read resolves through — silently, and while
    `vault list` reports the scope as `both` and says nothing more. The failure it produces
    is an empty vault rather than an error: `secret get` reports the key missing,
    `vault verify` finds no references, and `check_vaults` stays green because reachability
    is not resolution.

    FAIL rather than WARN, per ADR 0013: `cmd_doctor` exits non-zero only on FAIL, and that
    exit code is the only thing that makes the SessionStart wrapper print. A divergence
    worth naming is worth failing for.

    :data:`LOCAL_ONLY_KEYS` are excluded by construction — an account pin layered over a
    shared entry is the design working, not a fault.
    """
    from .secrets import base, registry

    try:
        # Through `usable_vaults`, which is the same drop rule `load_registry` applies —
        # not a raw read. Reading the halves raw did two wrong things at once (#363): it
        # counted entries the merged view had already dropped, one line below the `vaults`
        # check that named them as ignored, and it handed this loop the malformed entry
        # itself. A non-empty string is truthy, so `shared[name] or {}` did not catch it
        # and `.get` raised `AttributeError` — out of a preflight that has no per-check
        # guard, so one hand-edited line in a committed file cost the whole briefing.
        # That is #347's mechanism exactly, in the check next door to the one it fixed.
        shared = registry.usable_vaults(registry.load_shared())
        local = registry.usable_vaults(registry.load_local())
    except base.VaultError as e:
        return Result("vault registry", WARN, hint=str(e))

    clashes = []
    for name in sorted(set(shared) & set(local)):
        s, l = shared[name] or {}, local[name] or {}
        for key in ("provider", "persona"):
            sv, lv = s.get(key), l.get(key)
            if sv is not None and lv is not None and sv != lv:
                clashes.append(f"{name}.{key}: shared {sv!r}, local {lv!r}")
        sc, lc = s.get("config") or {}, l.get("config") or {}
        for key in sorted(set(sc) & set(lc)):
            if key in registry.LOCAL_ONLY_KEYS or sc[key] == lc[key]:
                continue
            clashes.append(f"{name}.{key}: shared {sc[key]!r}, local {lc[key]!r}")

    if not clashes:
        if not shared and not local:
            # Claiming "the halves agree" when neither half holds anything is an agreement
            # nothing was compared to reach — the exact wording `check_plugin_skew` already
            # warns about in this file ("it must not claim agreement it hasn't checked").
            return Result("vault registry", OK,
                          detail="no vaults registered — nothing to compare")
        # DISTINCT vaults, not entries summed. A vault declared in both halves — the very
        # case this check is about — is one vault, and `len(shared) + len(local)` called
        # it two. "Entries" was the word doing the hiding: a reader looking at a vault
        # registry counts vaults, so the plural has to be the thing being counted (#363).
        n = len(set(shared) | set(local))
        return Result("vault registry", OK,
                      detail=f"shared and local halves agree "
                             f"({n} vault{'' if n == 1 else 's'})")
    shown = "; ".join(clashes[:3])
    if len(clashes) > 3:
        shown += f" (+{len(clashes) - 3} more)"
    return Result("vault registry", FAIL, detail=shown,
                  hint="the local half shadows the shared one field by field, so these "
                       "resolve through the local value. Re-publish to clear it: "
                       "charter vault add <name> --provider <p> … --share --force")


def _plugin_ids(root: Path) -> tuple[str, str]:
    """``(plugin, marketplace)`` — see :func:`hooks.plugin_ids`, which owns this now that
    the hook surface prints the same upgrade instructions. Two copies could disagree about
    what to type, which is the one thing this string exists to get right."""
    from . import hooks
    return hooks.plugin_ids(root)


def check_plugin_skew() -> Result:
    """`charter` ships as two artifacts — the CLI (pip/uv) and the Claude Code plugin
    (``.claude-plugin/plugin.json`` + ``hooks/hooks.json``) — with two version numbers.
    ``hooks.skew_message`` is the loud guard a running hook speaks through; this is the
    same check surfaced in `doctor`, for a developer who just wants to ask directly.

    Only meaningful inside a Claude Code session with the plugin installed: Claude Code
    sets ``CLAUDE_PLUGIN_ROOT`` for the plugin's own processes (including a `charter
    doctor` a hook or the agent runs), pointing at the installed plugin's own directory.
    A bare `charter doctor` from a plain terminal (no plugin, pip/uv install only) has
    nothing to compare against — that's a normal, fully-supported way to run charter, so
    this stays OK rather than warning about a plugin that was never installed."""
    from . import hooks

    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not root:
        return Result("plugin", OK, detail="not running under the Claude Code plugin")
    manifest = Path(root) / ".claude-plugin" / "plugin.json"
    try:
        plugin_version = json.loads(manifest.read_text()).get("version")
    except (OSError, ValueError):
        return Result("plugin", WARN, detail="plugin manifest unreadable",
                      hint=f"expected a readable plugin.json at {manifest}")
    msg = hooks.skew_message(plugin_version)
    if msg:
        # FAIL, not WARN. A plugin NEWER than the CLI can dispatch `charter hook <name>`
        # for a handler this CLI does not have, so the hook simply does not run — the
        # guard looks installed and is not. `cmd_doctor` exits 1 only on FAIL, and that
        # exit code is what makes the SessionStart wrapper (`out=$(charter doctor) ||
        # printf …`) print anything at all; at WARN the message reached nobody through
        # either surface.
        return Result("plugin", FAIL,
                      detail=f"v{plugin_version} (CLI v{hooks.MIN_PLUGIN_VERSION})", hint=msg)
    # `skew_message` is one-directional — silent for an equal OR older plugin — so "matches"
    # was printed for a plugin many versions behind. It stays OK (an older plugin wires
    # fewer hooks, which is benign, unlike a newer one dispatching handlers this CLI lacks)
    # but it must not claim agreement it hasn't checked. A charter that reported "v0.1.0
    # matches the installed CLI" against a v0.13.1 CLI is how the drift stayed invisible.
    if plugin_version == hooks.MIN_PLUGIN_VERSION:
        return Result("plugin", OK, detail=f"v{plugin_version} matches the installed CLI")
    # The advice goes in `detail`, not `hint`: `Result.render` drops the hint entirely
    # when the status is OK, so guidance written there would be invisible while looking
    # shipped — which is the failure ADR 0013 is about, and it would be an unusually poor
    # place to commit it.
    #
    # Both steps, in order, because "upgrade it" did not upgrade anything. The marketplace
    # is a git clone advertising whatever it last fetched, so without refreshing it first
    # `plugin update` finds the installed version already current and correctly does
    # nothing; and `update` defaults to `user` scope while the plugin is usually installed
    # per project, which fails outright rather than silently. Observed together: a plugin
    # two minor versions behind, with `doctor` run repeatedly throughout.
    plugin_name, marketplace = _plugin_ids(Path(root))
    # Version lag on its own is not a finding — an older plugin that still dispatches every
    # handler behaves identically, and warning about it would train people to scroll past
    # the row, which costs the case below. What matters is whether `hooks/hooks.json`
    # actually invokes what this CLI ships: a handler the manifest never names simply does
    # not run, and the tally it would have written reads as empty rather than absent (#306).
    #
    # WARN, not FAIL: nothing is broken, and `cmd_doctor` exits non-zero only on FAIL, which
    # would turn a benign lag into a blocked preflight. Reaching the session is not this
    # row's job either — `hooks.stale_plugin_message` rides out as `systemMessage` at
    # sessionstart, because a WARN here prints through no surface at all (see the FAIL
    # branch above, which records exactly that).
    stale = hooks.stale_plugin_message(Path(root))
    upgrade = (f"`claude plugin marketplace update {marketplace}` (skip it and the next is "
               f"a no-op), then `claude plugin update {plugin_name}@{marketplace} --scope "
               f"<project|user, see: claude plugin list>`")
    if stale:
        missing = sorted(set(hooks._HANDLERS) - (hooks.dispatched_handlers(Path(root)) or set()))
        return Result("plugin", WARN,
                      detail=f"v{plugin_version} (CLI v{hooks.MIN_PLUGIN_VERSION}) — not "
                             f"dispatching {', '.join(missing)}",
                      hint=f"those handlers ship with this CLI and never run here. {upgrade}")
    return Result("plugin", OK,
                  detail=f"v{plugin_version} (CLI v{hooks.MIN_PLUGIN_VERSION}) — older "
                         f"plugin, dispatching every handler. Upgrade: {upgrade}")


#: What to type when the Claude Code plugin is missing. One string, because `doctor`'s row
#: and `init`'s warning must never disagree about the remedy — and because the remedy is
#: now a charter command rather than three lines of `claude plugin …` the reader has to
#: copy correctly (#881).
PLUGIN_FIX_CMD = "charter doctor --fix"


def check_plugin_install() -> Result:
    """Is charter's own Claude Code plugin installed for THIS plane — and if not, the one
    command that installs it (#881).

    A third question about the plugin, beside the two rows that already exist, and the
    split is the same one `check_guard_wired` records: *installed*, *enabled* and *wired*
    are different states. `check_plugin_skew` compares version numbers and answers nothing
    at all outside a plugin process; `check_plugin_freshness` compares the installed files
    with the marketplace clone. Neither says *there is no plugin here* — freshness reports
    that as a green ``the charter plugin is not installed here``, which is true and is read
    as health.

    **WARN and never FAIL.** `cmd_doctor` exits non-zero only on FAIL, and that exit code
    is what makes the SessionStart wrapper print — so a FAIL here would put a red preflight
    in front of every CLI-only install, which `docs/install.md` supports and CI uses. It
    would also be wrong about protection: a plane that declares `charter hook pretooluse`
    in its own `.claude/settings.json` is guarded with no plugin at all, and
    `check_guard_wired` is the row that answers whether the guard fires. This row answers
    whether the artifact charter can install for you is there.

    **Scoped to this plane, not to the machine.** `plugincache.installed_for` refuses a
    project-scoped install belonging to somebody else's checkout, because reading one as an
    answer here would print "installed" over a plane with no plugin — #168's own defect in
    a new row.

    Silent, green and specific where there is no `claude` at all: an opencode or Codex
    plane has no Claude Code plugin to be missing, and `check_harness` already states what
    each harness cannot carry.
    """
    name = "plugin install"
    try:
        return _plugin_install(name)
    except Exception as e:
        # The row-level guard `check_plugin_freshness` carries, for the same reason:
        # `_checks()` is an eager list literal with no per-check guard, so ONE raising
        # check returns no rows at all — and `hooks/hooks.json` renders a non-zero `charter
        # doctor` as "charter preflight failed - fix before working:" at every SessionStart.
        return Result(name, WARN, detail=f"not checked ({e})", hint=_NOT_CHECKED_HINT)


def _plugin_install(name: str) -> Result:
    """The body of :func:`check_plugin_install`, which owns the story and the guard."""
    from . import config as _config, plugincache

    if not plugincache.available():
        return Result(name, OK, detail="no `claude` on PATH — no Claude Code plugin here")
    if not _config.HAS_CONTROL_PLANE:
        # The plugin is installed per PROJECT, so without a plane there is no directory to
        # install it for. Not a fault: `charter doctor` outside a plane is a supported way
        # to preflight a machine.
        return Result(name, OK, detail="no control plane here — nothing to install it for")
    entry = plugincache.installed_for(_config.ROOT)
    if entry is plugincache.UNKNOWN:
        return Result(name, WARN,
                      detail="not checked (could not read `claude plugin list --json`)",
                      hint=_NOT_CHECKED_HINT)
    if entry is not None:
        # **Installed is not enabled, and only enabled loads anything** (#177). `claude
        # plugin list --json` carries `enabled`, and a tick over an installed-but-disabled
        # plugin is exactly the failure 0.31.1 shipped and `check_guard_wired` was written
        # to stop: the absence of a protection rendered as health.
        #
        # Absent rather than False is read as enabled. An older `claude` that does not emit
        # the field would otherwise have every plane told its plugin is off — inventing a
        # problem out of a missing key, which is the opposite error and just as expensive.
        #
        # **Reported, never fixed**, and `--fix` deliberately does not enable it. Somebody
        # disabling a plugin is a choice, and charter does not revert a deliberate edit —
        # the rule `commands._ensure_guard_hook` exists to keep. The row says what is not
        # happening;
        # the operator decides.
        if entry.get("enabled") is False:
            return Result(
                name, WARN,
                detail=f"{entry.get('id')} is installed ({entry.get('scope')} scope) and "
                       f"DISABLED — an installed plugin loads nothing until it is enabled, "
                       f"so charter's hooks do not run here",
                hint=f"Run: claude plugin enable {entry.get('id')} --scope "
                     f"{entry.get('scope')}  (charter does not enable it for you: if you "
                     f"turned it off on purpose, this row is only telling you what that "
                     f"costs). The plugin loads at the NEXT session.")
        return Result(name, OK,
                      detail=f"{entry.get('id')} installed ({entry.get('scope')} scope)")
    return Result(
        name, WARN,
        detail="charter's Claude Code plugin is not installed for this plane, so none of "
               "its hooks run here — no session context, no plane-root guard, no auto-save",
        hint=f"Run: {PLUGIN_FIX_CMD}  (installs `{plugincache.PLUGIN_ID}` at "
             f"{plugincache.INSTALL_SCOPE} scope from `{plugincache.MARKETPLACE_SOURCE}`; "
             f"`charter init` does the same thing on a fresh plane). The plugin loads at "
             f"the NEXT session, so restart afterwards.")


def check_plugin_freshness() -> Result:
    """Is the INSTALLED plugin the same FILES as the marketplace clone it came from?

    `check_plugin_skew` above compares version numbers, and between releases that number is
    frozen by design — so it reports agreement it has not checked. Measured on one machine
    while this was written: installed cache and marketplace clone both saying ``0.51.0``,
    45 files apart, ``skills/secrets/SKILL.md`` and ``skills/browser/SKILL.md`` among them,
    and `claude plugin update charter@charter` correctly answering *already at the latest
    version*. Hooks are unaffected — they invoke the ``charter`` on ``PATH`` — but skills
    are text the model loads, so a stale one is wrong instructions delivered confidently.

    **The severity is different on the two channels, and that is not hedging.** The
    marketplace clone tracks ``main``, which Claude Code re-fetches on its own, so *some*
    drift is the steady state for every stable plane from the day after a release onward.
    Warning about it would put a permanent yellow row in front of everyone whose only
    honest fix is "wait for the next release" — the cry-wolf failure this module's
    comments keep returning to, and the one that costs the rows that matter. So:

    * **dev channel** — WARN. The plane asked to track ``main`` and its plugin is not; that
      is a gap between what was declared and what is installed, with a command that closes
      it.
    * **stable channel** — OK, with the drift and the command named in ``detail``. Not
      ``hint``: `Result.render` drops the hint entirely at OK, so guidance written there
      would be invisible while looking shipped. The row still says the true thing, which is
      the live gap — today nothing anywhere does.

    Never FAIL. `cmd_doctor` exits non-zero only on FAIL, and that exit code is what makes
    the SessionStart preflight print; a plugin whose skills are a week old is not a reason
    to shout at every session start on every plane.
    """
    name = "plugin files"
    try:
        return _plugin_freshness(name)
    except Exception as e:
        # The row-level guard every network-touching check here already has, for the
        # reason `doctor._checks()` makes unavoidable: it is an eager list literal with no
        # per-check guard, so one raising check returns NO rows at all — and
        # `hooks/hooks.json` renders a non-zero `charter doctor` as "charter preflight
        # failed - fix before working:" at every SessionStart. `plugincache` returns
        # rather than raises on every path it owns; this is the belt for the paths it
        # does not.
        return Result(name, WARN, detail=f"not checked ({e})", hint=_NOT_CHECKED_HINT)


def _plugin_freshness(name: str) -> Result:
    """The body of :func:`check_plugin_freshness`, which owns the story and the guard."""
    from . import channel, config as _config, plugincache

    dev = channel.is_dev()
    if not plugincache.available():
        return Result(name, OK, detail="no `claude` on PATH — no Claude Code plugin here")
    entry = plugincache.installed_charter_plugin(_config.ROOT)
    if entry is plugincache.UNKNOWN:
        # NOT the green "not installed" below. An older `claude` that does not understand
        # `--json` answers here, and that is the population most likely to be running a
        # stale plugin — reporting a tick over it is the #171 defect exactly.
        return Result(name, WARN,
                      detail="not checked (could not read `claude plugin list --json`)",
                      hint=_NOT_CHECKED_HINT)
    if entry is None:
        return Result(name, OK, detail="the charter plugin is not installed here")
    install_path = entry.get("installPath")
    clone = plugincache.marketplace_clone(entry["id"].split("@", 1)[1])
    if not isinstance(install_path, str) or clone is None:
        return Result(name, WARN,
                      detail="not checked (could not locate the install or its marketplace)",
                      hint=_NOT_CHECKED_HINT)
    mine = plugincache.content_hash(install_path)
    theirs = plugincache.content_hash(clone)
    if mine is None or theirs is None:
        return Result(name, WARN, detail="not checked (the plugin surface is unreadable)",
                      hint=_NOT_CHECKED_HINT)
    if mine == theirs:
        return Result(name, OK, detail=f"matches the marketplace clone ({mine[:7]})")
    shown = plugincache.differing(install_path, clone)
    which = ", ".join(shown) + (" …" if len(shown) >= 3 else "")
    fix = "charter update" if dev else (
        f"`charter update` on the dev channel refreshes it; on stable the released "
        f"plugin is what pairs with the released CLI, so the fix is the next release")
    if dev:
        return Result(name, WARN,
                      detail=f"installed {mine[:7]}, marketplace {theirs[:7]} — {which}",
                      hint=f"this plane tracks the dev channel and its plugin does not. "
                           f"A version-keyed `claude plugin update` cannot see this, "
                           f"because both sides say v{entry.get('version')}. Run: {fix}")
    return Result(name, OK,
                  detail=f"installed {mine[:7]}, marketplace {theirs[:7]} — {which}. "
                         f"Both say v{entry.get('version')}, so `claude plugin update` "
                         f"reports nothing to do; {fix}")


#: Launcher basenames charter itself removed, so it can name the replacement instead of
#: merely reporting the absence. `bin/edm` and its `bin/charter` forwarding shim went with
#: the rename; a `charter` on PATH is what took over from both.
_REMOVED_SHIMS = ("edm", "charter")


def _claude_json() -> Path:
    """Claude Code's user-level config — where `mcpServers` registrations live, both the
    user-scoped ones and the per-project ones under `projects`.

    The file of the config folder Claude Code is using, not ``~/.claude.json`` (#969):
    measured on 2.1.268, with `$CLAUDE_CONFIG_DIR` set Claude Code writes `.claude.json`
    inside that folder, so the servers a second account registers are there and the home
    file's are not launched at all. `claude_code.global_config_file` owns the rule."""
    from .harness import claude_code as _claude_code

    return _claude_code.global_config_file()


def _vault_in_args(args) -> str | None:
    """The vault a ``charter secret exec <vault> …`` invocation opens, or ``None``.

    Read off the args rather than assumed, because it is the difference between advice that
    works and advice that half-works: a launcher charter merely *starts* has no plane to
    resolve, while one that opens a vault must find the plane holding it. Advice that
    applies to every entry is read as boilerplate and then not read at all.
    """
    if not isinstance(args, list):
        return None
    flat = [a for a in args if isinstance(a, str)]
    for i in range(len(flat) - 2):
        if flat[i] == "secret" and flat[i + 1] == "exec" and not flat[i + 2].startswith("-"):
            return flat[i + 2]
    return None


def _registered_launchers(doc: dict) -> list[tuple[str, str, list]]:
    """``(server name, command)`` for every **stdio** MCP server the host has registered.

    Both scopes, because checking only the top level would miss most real registrations —
    project-scoped servers are the common case. Every container is type-checked on the way
    down: `.claude.json` is a large harness-owned file (124KB of caches and counters on the
    machine that reported #197) whose shape charter does not control, and one odd value
    must not take the whole preflight down.
    """
    scopes = [doc.get("mcpServers")]
    projects = doc.get("projects")
    if isinstance(projects, dict):
        for body in projects.values():
            if isinstance(body, dict):
                scopes.append(body.get("mcpServers"))
    out: list[tuple[str, str, list]] = []
    for servers in scopes:
        if not isinstance(servers, dict):
            continue
        for name, entry in servers.items():
            # An SSE/HTTP server has a `url` and no `command`. Absence of a launcher is
            # not a missing launcher.
            if isinstance(entry, dict) and isinstance(entry.get("command"), str):
                out.append((str(name), entry["command"], entry.get("args") or []))
    return out


def _launcher_missing(command: str) -> bool:
    """True only when the path is **known** absent.

    An unreadable parent directory makes the answer unknown rather than negative, and
    `pathlib` reports that differently per platform — it raises EACCES on Linux and returns
    False on macOS, which has taken this repo's CI red twice. An ambiguous answer must
    never become a FAIL, so uncertainty resolves to "not missing".
    """
    try:
        return not Path(command).exists()
    except OSError:
        return False


#: Paths a charter command causes to exist that carry credential material, with the command
#: that (re-)ignores each. ADR 0017: charter ignores what carries credentials; everything
#: else it states and leaves to the plane. Grown by adding a row — a path that is merely
#: generated, or merely noisy, does not belong here and gets a sentence in some command's
#: output instead.
CREDENTIAL_PATHS = (
    (Path(".playwright-cli"), "traces and snapshots of authenticated runs",
     "charter browser install"),
)


def check_credential_paths() -> Result:
    """Credential-bearing paths charter created, that git would still take.

    `charter browser install` writes the ignore line, so a plane that runs it today is fine.
    This is for the ones that are not: a plane that installed the lane *before* that landed,
    or whose line lost a merge. Nothing else would say so — the directory appears only once a
    trace or snapshot is written, well after the command that caused it, and it reads as
    ordinary untracked noise right up until `git add -A` commits it. A trace records network
    requests with their headers and bodies, so tracing a bridged login puts the credential on
    disk in a file nothing in the transcript points at.

    That is the shape #278 was actually about. The missing `.gitignore` line was the symptom;
    the cost was every plane working the same thing out again, in silence, and this is the
    half that reaches planes charter has already touched.

    FAIL, not WARN: `vault add` already exits non-zero for the identical condition —
    credential material inside the plane that git would take — and two answers to one
    question is worse than either.

    Only paths that EXIST are considered. Most planes never open a browser, and a row that is
    permanently yellow on an ordinary machine costs the findings that matter
    (`check_workspace_clones` records the same concern).
    """
    from . import config as _config

    name = "credential paths"
    if not _config.HAS_CONTROL_PLANE:
        return Result(name, OK, detail="no control plane found")

    exposed: list[tuple[str, str, str]] = []
    checked = 0
    for rel, what, fix in CREDENTIAL_PATHS:
        target = Path(_config.ROOT) / rel
        if not target.exists():
            continue
        ignored = util.git_ignores(_config.ROOT, target)
        if ignored is None:
            # Not a repository. Nothing to commit to, so no risk to report — reporting one
            # would be inventing a finding, which is the direction ADR 0009 forbids.
            return Result(name, OK, detail="plane is not a git repository")
        checked += 1
        if not ignored:
            exposed.append((str(rel), what, fix))

    if not exposed:
        return Result(name, OK,
                      detail=f"{checked} present and gitignored" if checked
                      else "none present")

    first = exposed[0]
    detail = ", ".join(f"{p}/ — {what}" for p, what, _ in exposed)
    return Result(name, FAIL,
                  detail=f"{detail}: git would take {'them' if len(exposed) > 1 else 'this'}",
                  hint=f"`{first[2]}` adds the line (it is idempotent, and re-running it is "
                       f"safe). Committing this publishes a live credential to everyone with "
                       f"the clone — see ADR 0017.")


def check_mcp_launchers() -> Result:
    """An MCP server whose launcher does not exist can never start — and says nothing.

    This is #197. The `edm`->`charter` rename removed `bin/edm` and its forwarding shim,
    and every MCP server registered as ``bin/edm secret exec <vault> … --exec -- <server>``
    began failing with ENOENT. Claude Code does not surface that: the tools are simply
    absent. A persona lost its whole toolset mid-investigation and rerouted through
    cloudflared + Kibana before anyone worked out why. Nothing in charter read
    `~/.claude.json` before this, so the breakage was invisible everywhere it happened.

    **Absolute paths only.** A bare `npx` resolves against the PATH of whoever launches the
    server, which is not the PATH charter runs under; calling that missing would be charter
    asserting something about an environment it cannot see — the guess ADR 0009 forbids,
    and how `doctor` cried wolf in 0.31.1 and #177. An absolute path that does not exist is
    a fact, and it is the fact that classifies every instance of this failure, not just the
    one that was reported.

    **FAIL, not WARN**, for the reason `check_plugin_skew` chose it: `cmd_doctor` exits
    non-zero only on FAIL, and that exit code is what makes the SessionStart wrapper print
    anything at all. A WARN would reproduce the defect it diagnoses — a real breakage that
    reached nobody.
    """
    path = _claude_json()
    try:
        doc = json.loads(path.read_text())
    except FileNotFoundError:
        # A machine that never registered an MCP server is healthy, not unknown.
        return Result("mcp", OK, detail="no MCP servers registered")
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        # Named by the path actually read (#969): the file moves with `$CLAUDE_CONFIG_DIR`,
        # and a row that always says `~/.claude.json` sends the reader to the wrong file.
        return Result("mcp", WARN,
                      detail=f"{util.short_path(path)} unreadable ({_first_line(str(exc))})",
                      hint=_NOT_CHECKED_HINT)
    if not isinstance(doc, dict):
        return Result("mcp", WARN, detail=f"{util.short_path(path)} is not an object",
                      hint=_NOT_CHECKED_HINT)

    registered = _registered_launchers(doc)
    checkable = [(n, c, a) for n, c, a in registered if os.path.isabs(c)]
    broken = [(n, c, a) for n, c, a in checkable if _launcher_missing(c)]
    if not broken:
        # "0 launcher(s) resolve" was shown for a plane whose only server had just been
        # repaired onto a bare command. Zero were CHECKED and none were broken; printing
        # the first as though it were a count of what resolves reads as "nothing is
        # registered", which is a different claim about a different fact.
        if not registered:
            return Result("mcp", OK, detail="no MCP servers registered")
        if not checkable:
            # Every registered launcher is a bare command, resolved against the PATH of
            # whoever starts it — which charter cannot see, and so does not claim to have
            # checked. Saying how many exist keeps that honest without inventing a verdict.
            return Result("mcp", OK,
                          detail=f"{len(registered)} server(s), none on an absolute path")
        return Result("mcp", OK, detail=f"{len(checkable)} launcher(s) resolve")

    hints = []
    for name, command, args in broken:
        if Path(command).name in _REMOVED_SHIMS:
            # Charter removed this one, so it knows what replaced it. Naming the
            # replacement turns a diagnosis into a one-line fix.
            fix = (f"{name}: {command} is gone (the edm→charter rename removed that shim) "
                   f"— set this server's command to `charter`, leaving its args unchanged")
            vault = _vault_in_args(args)
            if vault:
                # The half of the advice that was missing. The old command was an absolute
                # path into a particular umbrella; a bare `charter` resolves its plane from
                # the LAUNCHING directory, and an `mcpServers` entry at the top level of
                # the config folder's `.claude.json` is user-scope — it launches for every project, most of
                # which are not that plane. The server then starts, fails to find the vault,
                # and the tools are missing again, silently, exactly as before.
                fix += (f". It opens vault `{vault}`, so also set CHARTER_ROOT in this "
                        f"server's `env` to the plane holding that vault — a user-scope "
                        f"server has no directory to resolve one from")
            hints.append(fix)
        else:
            # No claim about WHY it went missing: charter did not remove it and does not
            # know. It reports the fact and the two ways out.
            hints.append(f"{name}: {command} does not exist, so the server cannot start — "
                         f"repoint its command or remove the registration")
    return Result("mcp", FAIL,
                  detail=f"{len(broken)} of {len(checkable)} launcher(s) missing: "
                         + ", ".join(n for n, _, _ in broken),
                  hint="; ".join(hints))


#: Seconds a single preflight check may take before it is reported as timed out rather
#: than waited on. `gh api`, `glab api` and `op` all reach the network or a desktop app; a
#: 1Password session needing re-auth stalled the whole SessionStart preflight for its 20s
#: budget and then printed NOTHING, because results were collected before any were shown.
CHECK_TIMEOUT = 5.0


def iter_all(*, preflight: bool = False):
    """Yield each :class:`Result` as it completes.

    A generator rather than a list because `cmd_doctor` collected everything before
    printing a single line: a preflight killed by its hook timeout emitted no diagnosis at
    all, not even the checks that had already passed. Streaming turns a mystery stall into
    "got as far as `vaults`, then stopped" — which names the culprit without charter
    having to guess at it.
    """
    for r in _checks(preflight=preflight):
        yield r


def _checks(*, preflight: bool = False):
    """Order: cheap/local checks first, network checks last. The forge cli/auth pair is
    NOT fixed (it used to be exactly one hardcoded GitLab pair) — it's one pair PER
    FORGE this control plane actually declares (`declared_or_default_forges`), so a
    GitHub-only control plane sees `gh`/`gh auth`, never a `glab` FAIL with no real fix
    (FINDING I3)."""
    results = [check_python(), check_git(), check_git_identity()]
    for forge in declared_or_default_forges():
        results.append(check_forge_cli(forge))
        results.append(check_forge_auth(forge))
    results += [check_ssh(), check_control_plane_config(),
                check_harness_profiles(preflight=preflight),
                *check_profile_wiring(preflight=preflight),
                check_control_plane_schema(),
                check_plane_root(), check_index_lock(),
                check_session_root(), check_session_layer(),
                check_harness(), check_frame(), check_guard_wired(), check_guard_seen(), check_nested_plane(),
                check_workspace_clones(), check_workspace_harness(), check_changes(),
                check_inventory(), check_vaults(),
                check_vault_registry_divergence(), check_version_lock(),
                check_memory_indexes(), check_personas(), check_persona_grant(),
                check_front_door(),
                check_news_adoption(),
                check_ask_rules(), check_handoff_gate(),
                check_shadowed_knowledge(),
                check_credential_paths(),
                check_mcp_launchers(), check_plugin_install(), check_plugin_skew(),
                check_plugin_freshness()]
    return results


#: Every name a check in :func:`_checks` produces that does not depend on this plane's
#: forges, in the order `_checks` runs them. The forge cli/auth pair belongs at index 3
#: and is spliced in by :func:`check_names`, because which forge that is is a property of
#: the control plane rather than of this list.
#:
#: **A second spelling of something the checks already say, and it is here because the
#: alternative forecloses something.** `Result.render` needs the column's width before the
#: first row is drawn, and `cmd_doctor` is written to draw each row as its check lands —
#: deliberately, so a preflight killed by its hook timeout names where it stopped instead
#: of printing nothing at all. Sizing the column from the results would mean collecting
#: every check before drawing one, which is exactly the shape streaming replaced.
#:
#: That streaming is **not delivered today**, and the honest note is worth more than the
#: convenient one: :func:`_checks` is an eager list literal, so `iter_all` yields from a
#: run that has already finished and `cmd_doctor` prints its rows all at once. Sizing from
#: the results would therefore cost nothing *right now* — and would silently make the
#: streaming fix unavailable to whoever writes it. This costs a list instead.
#:
#: So the names are stated ahead of the run and **pinned by equality** against what
#: `run_all` actually produces — the same discipline `MIN_PYTHON` has against
#: `pyproject.toml`: a check renamed, added or removed fails that test on the commit that
#: does it. Unpinned this would be a list that rots into a wrong width; pinned, it cannot.
_FIXED_CHECK_NAMES = (
    "python3", "git", "git identity",
    # ← the forge cli/auth pair is spliced in here, see `check_names`
    "git auth", "charter.toml", "harness profiles", "schema", "plane root", "index lock",
    "session root", "session layer",
    "harness", "frame",
    "plane-root guard", "guard seen", "nested plane", "workspace clones",
    "workspace layer", "changes",
    "inventory", "vaults", "vault registry", "version lock", "memory indexes",
    "personas", "persona grant", "front door", "news", "ask rules", "handoff gate",
    "shadowed docs",
    "credential paths", "mcp", "plugin install", "plugin", "plugin files",
)

#: The row the per-profile rows follow, in `_FIXED_CHECK_NAMES` and in `_checks`. A name
#: rather than an index, so renaming the row above them moves them with it or fails loudly.
_PROFILE_NAMES_AFTER = "harness profiles"

#: Where the forge pair goes in `_FIXED_CHECK_NAMES` — after `git identity`, which is
#: where `_checks` runs it. A number rather than a marker entry so the tuple holds only
#: names and the pin below compares like with like.
_FORGE_NAMES_AT = 3


def check_names(*, preflight: bool = False) -> list[str]:
    """Every name this plane's preflight will print, **without running a single check**.

    The profile rows are spliced after `harness profiles`, the forge pair's shape, because
    which profiles this plane has is a property of one machine's `charter.local.toml` rather
    than of this list — and `preflight` removes them, the way it removes them from the run.

    The forge pair is asked of `declared_or_default_forges` — the same call `_checks`
    makes, so the two cannot disagree about which forge this plane declares. A GitHub-only
    plane sizes for ``gh``/``gh auth`` and a GitLab one for ``glab``/``glab auth``, rather
    than for whichever of them somebody wrote down.
    """
    pair = []
    for forge in declared_or_default_forges():
        pair += [forge.cli, f"{forge.cli} auth"]
    names = (list(_FIXED_CHECK_NAMES[:_FORGE_NAMES_AT]) + pair
             + list(_FIXED_CHECK_NAMES[_FORGE_NAMES_AT:]))
    # `in` before `index`, because a test that stands in for `_FIXED_CHECK_NAMES` to prove
    # the column is measured rather than guessed replaces the whole tuple — and a splice that
    # raised there would take the width down over a row it was not asked about.
    if _PROFILE_NAMES_AFTER not in names:
        return names
    at = names.index(_PROFILE_NAMES_AFTER) + 1
    return names[:at] + profile_row_names(preflight=preflight) + names[at:]


def name_width(*, preflight: bool = False) -> int:
    """The NAME column of `charter doctor`, measured in cells from the names it holds.

    In cells rather than characters because cells are what a terminal lays out — the unit
    `tui.column` measures every other table in this package with. Every check name is
    ASCII today, so the two agree and this looks like a distinction without a difference;
    it is the same distinction that drew an 8-glyph CJK name 8 columns wide of every other
    row in `persona stats` (#508), and it is not something to get right later.
    """
    return tui.column("", check_names(preflight=preflight))


def run_all(*, preflight: bool = False) -> list[Result]:
    """Every check, collected. Kept for callers that want them all at once (`--json`,
    tests); `iter_all` is what an interactive preflight should use."""
    return list(iter_all(preflight=preflight))
