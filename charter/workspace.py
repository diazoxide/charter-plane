"""Workspaces: isolated, per-task environments of repo clones.

A **workspace** is a named directory under ``workspaces/`` holding one task's clones
(each repo on whatever branch that task needs): ``workspaces/<workspace>/<repo>``.
Different parallel tasks use different workspaces and must never be mixed.

Which workspace a command acts on is resolved by precedence:

1. an explicit ``--workspace`` flag,
2. the ``$CHARTER_WORKSPACE`` env var (set at session launch → hard per-session
   isolation for parallel agents; empty or only whitespace is unset, not a rung —
   :func:`from_environment`, #1055),
3. the **per-Claude-session** pointer (``.charter/sessions/<id>.workspace``),
4. the **per-terminal** pointer (``.charter/terminals/<id>.workspace``) — a terminal
   pane survives closing/reopening Claude, so a pane keeps its own workspace,
5. otherwise ``default``.

``charter workspace use`` writes the per-terminal *and* per-session pointers (never a
shared/global one), so selecting a workspace in one pane never leaks into another.
A SessionStart hook (``workspace _reconcile``) seeds a reopened session's pointer
from its terminal's, so the status line stays in step with commands.

Secrets are deliberately *not* part of this — vaults are cross-workspace.
"""

from __future__ import annotations

import contextlib
import datetime
import errno
import fnmatch
import hashlib
import json
import os
import re
import shutil
import stat
import threading
import time
from pathlib import Path
from typing import NamedTuple

from . import config, contain, instance, util

_SESSION_MAX_AGE = 30 * 86400  # prune per-session pointers older than this
_LEGACY_ROOT = config.ROOT / "repos"  # the pre-rename clone root


def _ensure_layout() -> None:
    """One-time migration: the clone root was renamed ``repos/`` → ``workspaces/``.
    If an old ``repos/`` still exists and the new dir doesn't, move it. Best-effort."""
    try:
        if _LEGACY_ROOT.exists() and not config.WORKSPACES_DIR.exists():
            _LEGACY_ROOT.rename(config.WORKSPACES_DIR)
    except OSError:
        pass


def _session_id(explicit: str | None = None) -> str | None:
    """This session's id, or ``None`` — see :mod:`charter.session`, which owns it."""
    from . import session as _session
    return _session.current(explicit)


def _session_file(sid: str) -> Path:
    return config.SESSIONS_DIR / f"{sid}.workspace"


def for_session(sid: str) -> str | None:
    """The workspace explicitly chosen FOR *sid*, or ``None`` if nobody chose one.

    The per-session pointer rung of :func:`resolve`, asked about a session that is not
    necessarily this process's — which is the whole reason it is public. Inside a charter
    frame the frame **is** the charter session (`docs/frame.md`, ADR 0019), so
    `charter workspace use <name>` typed at the agent writes this file under the FRAME's
    id — and that decides what every `charter` command in that frame's own shell acts on.

    **It does NOT decide what the frame's panels draw, and it did until #791.** That was
    the documented mechanism behind "it moves the panels too", and what made it work was
    this file being a rung of `frame/state.own_workspace` — which since #733 is also what
    decides a chat's MEMBERSHIP of a workspace. So the command re-homed the chat:
    measured, `charter workspace use gamma` typed inside `alpha.1` took it out of `alpha`'s
    roster, made it invisible to the chat beside it in the same tmux session, and put
    `gamma`'s chats on its bar where `cmd_chat` refuses them. Spec §4j settles which of the
    two has to give: a chat belongs to its workspace for life, so what a pointer moves is
    the session's work and never the chat's identity.

    **Refusing the command inside a frame was the alternative, and #791 rejected it on
    evidence**: the only test for "inside a frame" is `session.current()`, and every agent
    spawned from a frame inherits `$CHARTER_SESSION_ID` — so the refusal would fire on
    agents doing ordinary CLI work in isolated worktrees. Nothing here changed; the reader
    that stopped asking was `own_workspace`. **#936 then refused it after all, by another
    route and with no frame test**: a chat's lock is its launch record (:func:`launch_lock`),
    so `set_active` refuses an unforced switch out of it. That is right for an inherited id
    too. The pointer a sub-agent's `workspace use` writes is this file under its PARENT
    chat's id, and the sub-agent's own work goes by the tree it stands in or by
    `--workspace`, neither of which writes here.

    Still public, still read by :func:`chosen` and :func:`source`, and still keyed on an id
    handed in rather than resolved — the caller is not always the session being described.
    Asking this directly is what keeps that a property rather than a spelling: the
    alternative was reading :func:`source`'s human-facing label and matching the string
    ``"session"``, which is a sentence written for a status line, not an API.

    Name-checked like every other rung that hands a value to :func:`workspace_dir`'s join.
    The ``val and`` in front of it is a None-guard rather than a second name check —
    :func:`_read` answers ``None`` for a missing or empty file, and `valid_name` takes a
    string.
    """
    val = _read(_session_file(sid)) if sid else None
    return val if val and valid_name(val) else None


def for_frame(sid: str | None) -> str | None:
    """The workspace the frame *sid* names was LAUNCHED for, or ``None``.

    A rung of :func:`chosen`, and the answer to #524. Inside a charter frame
    ``$CHARTER_SESSION_ID`` holds the FRAME's id (`session.current`'s own docstring says
    so, and ADR 0019 is why), so "this session's id" and "the frame this session is
    running inside" are the same string — which is what makes the launcher's recorded
    answer readable from here at all. Outside a frame the id names a conversation, there
    is no frame directory under it, and this answers ``None``.

    **Why a rung and not a hook.** #524's own framing was that the session-start hook is
    where this lands — `hooks.sessionstart` already picks a workspace and writes the
    per-session pointer, and a framed harness is the one caller with a recorded answer it
    does not consult. But the issue's own third constraint rules that out as the
    mechanism: *a non-Claude harness has no session-start hook at all*, and neither does
    a bare `charter ws current` typed into the frame's shell. A hook would fix the
    harness charter ships hooks for and leave every other one re-resolving. A rung in the
    ladder itself needs no harness cooperation, so it degrades to nothing rather than to
    a wrong answer.

    Its POSITION is the reconciliation #524 says charter cannot leave silent, and it is
    the same one `frame/state.workspace_for` already spells for the panels:

    * **Below the per-session pointer.** `charter workspace use <name>` typed inside the
      frame writes that pointer under the frame's id, so an operator's explicit choice
      still wins **for this session's own commands** — the direction #517 asks for. The
      launcher's answer is a SEED, never a pin: handing the harness `$CHARTER_WORKSPACE`
      would have ranked the launch above every pointer and above the tree a sub-agent
      stands in. What the pointer no longer moves is the frame's PANELS (#791): that read
      goes through `frame/state.own_workspace`, which is also what decides a chat's
      membership of a workspace, and a command deciding a chat's identity is what §4j
      forbids. This rung's position is unaffected — the two readers were always different
      functions, and only one of them stopped asking. Since #936 an unforced `ws use
      <other>` in a chat is refused by the chat's lock (:func:`launch_lock`), so inside a
      chat this pointer outranks the rung below only when somebody passed `--force`. That
      is still an explicit choice for this session's commands, and they still act on it.
    * **Above the per-terminal pointer.** That rung is not merely absent inside a frame,
      it is *wrong*: it is keyed on `$TMUX_PANE`, and the harness's pane is one charter
      created — not the operator's terminal, whose pointer it would otherwise read or
      (on a recycled pane id) mistake for its own. Same for the declared default below
      it: both answer for the asking process, and the record is here to outrank exactly
      those two.

    Name-checked through `frame/state.frame_workspace`, which owns that guard for this
    value; ``None`` covers a frame launched by a charter predating the record, a corrupt
    file, and every process that is not in a frame.

    **The empty-id refusal below is a COST guard, and a deletion sweep is right that
    nothing observable depends on it.** Deleted, this still answers ``None`` —
    `contain.child` refuses a falsy name and `frame_workspace` degrades — so it is kept
    for what it avoids rather than for what it decides: this rung sits on :func:`resolve`,
    which the status line calls on every turn, and without it a session-less call pays a
    module import, a path resolution and a failed `read_text` to learn what one boolean
    already knew. The contract is pinned (`for_frame(None) is None`); the shortcut is
    not, deliberately, because a test that could tell the two apart would be asserting the
    shortcut rather than the answer.
    """
    if not sid:
        return None
    try:
        from .frame import state as _state
        return _state.frame_workspace(sid)
    except Exception:
        # A rung, on the path every command takes to answer "where am I". It reports what
        # it can read and never becomes the reason a command cannot run.
        return None


def _terminal_id(explicit: str | None = None) -> str | None:
    """This terminal PANE's id, or ``None`` — see :func:`charter.session.terminal`,
    which owns it. Kept as a module-level name because it is the seam tests patch to
    simulate a pane-less shell, and because `persona` asks the same question: two
    copies of the WINDOWID lesson is one copy too many."""
    from . import session as _session
    return _session.terminal(explicit)


def _terminal_file(tid: str) -> Path:
    return config.TERMINALS_DIR / f"{tid}.workspace"


def _read(f: Path) -> str | None:
    try:
        val = f.read_text().strip()
        return val or None
    except Exception:
        return None


def valid_name(name: str) -> bool:
    """Can *name* name a workspace? **The one place that answers this.**

    Delegates to :func:`instance.workspace_name_ok` rather than keeping a second regex
    here, because ``[workspace] default`` is read during ``config``'s bootstrap — before
    this module can be imported — and two copies of the rule are how a reading site and a
    creation site come to disagree (:mod:`charter.contain`).
    """
    return instance.workspace_name_ok(name)


def _unreadable(fn) -> bool:
    """Run a filesystem predicate, treating "I am not allowed to look" as "no".

    ``pathlib`` does NOT count ``EACCES`` among the errors it swallows — only ENOENT,
    ENOTDIR, EBADF and ELOOP — so ``(d / ".git").is_dir()`` *raises* on a directory the
    process cannot enter. It raises on Linux and returns False on macOS, which is how a
    suite green on a laptop goes red on CI.

    Every caller here is asking "is there a checkout at this path", and the honest answer
    for a directory we cannot read is no. Raising instead means one unreadable directory
    anywhere under ``workspaces/`` takes down every caller that scans it — including the
    status line, whose failure mode is a blank footer on every turn.
    """
    try:
        return fn()
    except OSError:
        return False


def is_git_repo(path: Path) -> bool:
    return _unreadable(lambda: (path / ".git").exists())


def is_tree(path: Path) -> bool:
    """A working tree of either provenance — a clone (``.git`` is a directory) or a
    linked worktree (``.git`` is a file). :func:`is_clone` deliberately excludes the
    second; this is for callers that only need "is there a checkout here"."""
    return _unreadable(lambda: (Path(path) / ".git").exists())


def git_dir(root: Path) -> Path | None:
    """The real git directory of the checkout at *root*, or ``None`` if there is none.

    ``<root>/.git`` is a DIRECTORY in a clone and a FILE reading ``gitdir: <path>`` in a
    linked worktree — the same distinction :func:`is_clone` draws on purpose. Anything
    that needs to WRITE into git's own directory has to resolve the second form, because
    treating `<root>/.git/` as a directory does not fail loudly there: `mkdir -p` happily
    creates `.git/info/` *beside* the `.git` file's parent and git reads none of it.
    """
    dot = root / ".git"
    if _unreadable(lambda: dot.is_dir()):
        return dot
    try:
        text = dot.read_text()
    except (OSError, UnicodeDecodeError):
        return None
    for line in text.splitlines():
        if line.startswith("gitdir:"):
            g = Path(line.split(":", 1)[1].strip())
            if not g.is_absolute():
                g = root / g
            return g if _unreadable(lambda: g.is_dir()) else None
    return None


def git_exclude_file(root: Path) -> Path | None:
    """The ``info/exclude`` git actually READS for the checkout at *root*.

    The COMMON directory's, which for a linked worktree is not its own gitdir. Git treats
    ``info/`` as shared between a repo and its worktrees, so a pattern written to
    ``.git/worktrees/<name>/info/exclude`` is read by nobody: measured on git 2.x — the
    file stays listed as untracked there, and the identical pattern in the main repo's
    ``.git/info/exclude`` hides it in the worktree. ``commondir`` is the pointer git
    itself leaves for this, holding a path relative to the worktree's gitdir (``../..``).

    That asymmetry is also why removal is not "delete the directory": a worktree's
    exclude file lives OUTSIDE the workspace, in a repo `shutil.rmtree` never reaches —
    see :func:`unwire_guests`.
    """
    g = git_dir(root)
    if g is None:
        return None
    try:
        common = (g / "commondir").read_text().strip()
    except (OSError, UnicodeDecodeError):
        common = ""
    if common:
        # No absolute/relative branch: `Path("/a/.git/worktrees/x") / "/elsewhere"` IS
        # `/elsewhere`, so joining answers both spellings and a branch here would be one
        # the deletion sweep could remove without changing an answer. `normpath` rather
        # than `resolve` because `commondir` is git's own `../..` and resolving would
        # also follow symlinks, which `config.use` deliberately does not.
        g = Path(os.path.normpath(g / common))
    return g / "info" / "exclude"


def is_clone(path: Path) -> bool:
    """A real clone, not a worktree. Git itself draws the line: a clone's ``.git`` is a
    DIRECTORY, a linked worktree's ``.git`` is a FILE pointing at the shared gitdir. So a
    worktree can never be miscounted as a cloned repo — no bookkeeping required.

    A ``.git`` charter cannot `stat` is no clone here; :func:`read_clones` asks the same
    :func:`_directory` and names it instead (#1043)."""
    return _directory(path / ".git")[0] is True


def workspace_dir(name: str) -> Path:
    return config.WORKSPACES_DIR / name


def exists(name: str) -> bool:
    """Whether *name* is a workspace this plane HAS — a fact about the filesystem, now.

    **Named because it is asked on a REPAINT path, where the answer changes under the
    reader** (#752). A frame is long-lived by definition, and `charter workspace remove`,
    a `git clean`, a teammate's pull and a plain `mv` all take a workspace out from under
    one that is drawing it. `frame/slots._repos` asks this the way it asks
    `gather.unreadable`: of the filesystem, at the moment the pane is drawn, rather than
    inferring absence from a scan that came back empty — which is a different claim, and
    drawing the two the same is what #512 already cost this pane once.

    **The name check is part of the predicate and not the caller's job, and that is what
    is new here.** The same question was spelled inline in `frame/leave.plan` (`homeless`)
    and in `commands_frame._reopen_one`'s `· workspace was missing`, and both are fed from
    `state.own_workspace`, which name-checks every rung it returns — so a bare
    `workspace_dir(ws).is_dir()` was safe *there* because of something true one call up.
    The pane's name comes from `state.workspace_for`, whose LAST rung is a bare
    :func:`resolve` handing back `$CHARTER_WORKSPACE` stripped and otherwise untouched.
    Measured: with ``CHARTER_WORKSPACE=..`` that value reaches the renderer verbatim, and
    ``WORKSPACES_DIR / ".."`` is the plane root — a directory, so a filesystem-only
    predicate answers *present* for a name that is not a workspace and can never be one,
    and the pane goes on drawing it. :func:`valid_name` is therefore asked FIRST, and a
    name it refuses is absent by definition: no `ensure` will make it, so there is nothing
    for the join to be right about.

    Never creates and never raises: :func:`ensure` is the creator, the one caller that must
    not write is the renderer, and :func:`_unreadable` is what keeps a `workspaces/` charter
    is not allowed to look into from taking down a panel — the same reason every other
    predicate in this module goes through it, said for a caller whose failure mode is a
    dead pane rather than a blank footer.
    """
    return valid_name(name) and _unreadable(lambda: workspace_dir(name).is_dir())


def from_path(path=None) -> str | None:
    """The workspace whose working tree *path* is inside, or ``None``.

    A workspace's trees live at known places — `workspaces/<ws>/<repo>/…` for a fleet
    clone, `<worktrees-root>/<ws>/<repo>/<piece>/…` for a worktree — so standing in one
    IS the answer to "which workspace am I in", and it is an answer no pointer can
    contradict. You cannot be in two directories at once, which is exactly the property
    the pointers lacked: a session that had never chosen anything inherited another
    session's choice through a shared terminal key.
    """
    from . import worktree
    try:
        here = Path(path or os.getcwd()).resolve()
    except (OSError, RuntimeError):
        return None

    loc = worktree.locate(here)          # (workspace, repo, piece) — handles both roots
    if loc:
        return loc[0]
    try:
        parts = here.relative_to(Path(config.WORKSPACES_DIR).resolve()).parts
    except (ValueError, OSError, RuntimeError):
        return None
    # `workspaces/<ws>` alone is the container, not a tree — only a repo inside it counts.
    return parts[0] if len(parts) >= 2 else None


def contains(name: str, path) -> bool:
    """Whether *path* is inside workspace *name*'s own subtree — #867.

    **The isolation boundary as a containment question, which is a different one from
    :func:`from_path`.** That function asks "which workspace's *tree* is this", and
    answers ``None`` for ``workspaces/<ws>`` itself, deliberately: the workspace directory
    is the container and not a repo, and a status line naming a workspace for a path with
    no repo in it would be claiming a tree that is not there. This asks the question a
    *boundary* has to answer, where the container counts — so it is that predicate plus the
    directory itself, rather than a loosening of it.

    Used by `commands_frame._restore_root`, to decide whether a recorded cwd is one a
    restore may keep, and by `frame/leave.plan`, so the quit preview promises the same
    thing the restore then does. Spelled once for `_launch_root`'s reason: it was about to
    be the same three lines twice, in two modules that must not come to disagree.

    **A prefix test on `workspaces/<ws>/` would be wrong**, and that is why this delegates
    rather than joining paths. A worktree lives at ``<[plane] worktrees>/<ws>/<repo>/…``,
    outside ``workspaces/`` entirely, and is every bit as much that workspace's own tree as
    a clone is; `from_path` already tries both roots (`worktree.locate`), and a second
    reading here would be a second answer to go stale.

    Resolved on both sides, like :func:`contain.within_data`: a recorded cwd came off
    `os.getcwd()`, which returns a path with the links already walked, while
    ``WORKSPACES_DIR`` is joined from the plane root as configured — and on macOS a plane
    under ``/var/folders`` is reached through a link to ``/private/var``. Comparing the two
    as text answers *outside* for a path that is plainly inside.

    Never creates and never raises, like every predicate here: an unresolvable path is
    simply not contained. **`from_path` is inside the guard and not in front of it**, which
    is the difference between promising that and merely intending it — it catches
    ``(OSError, RuntimeError)`` and `Path.resolve` raises `ValueError` on a path with an
    embedded NUL, which is a value a hand-edited `reopen.json` can carry to both callers.
    """
    if not valid_name(name) or not path:
        return False
    try:
        if from_path(path) == name:
            return True
        return os.path.realpath(path) == os.path.realpath(workspace_dir(name))
    except (OSError, ValueError):
        return False


def clone_of(path=None) -> tuple[str, str] | None:
    """``(workspace, repo)`` when *path* is inside a **clone**, else ``None``.

    The clone counterpart to `worktree.locate`, and deliberately exclusive of it: a path
    inside a worktree answers ``None`` here, so a caller asking both questions can never
    record the same directory twice under two identities.

    ``None`` for the plane root, which is the point — the root already carries an alert
    whose entire message is *work belongs in a workspace clone*, and marking who is present
    there would decorate the thing charter is telling you to stop doing. ``None`` too for
    ``workspaces/<ws>`` itself, which is a container rather than a tree.

    Path arithmetic only, no git and no subprocess: this is reached from a hook that fires
    every turn and from the status line's render path.
    """
    from . import worktree
    try:
        here = Path(path or os.getcwd()).resolve()
    except (OSError, RuntimeError):
        return None
    if worktree.locate(here):
        return None
    try:
        parts = here.relative_to(Path(config.WORKSPACES_DIR).resolve()).parts
    except (ValueError, OSError, RuntimeError):
        return None
    if len(parts) < 2:
        return None
    # A dotted second segment is charter's own furniture (`.worktrees/`), never a repo.
    # `worktree.locate` catches those whose layout it knows; this catches the rest rather
    # than inventing a repo called `.worktrees`.
    if parts[1].startswith("."):
        return None
    return parts[0], parts[1]


#: A committed, deliberately-chosen fallback workspace — `workspaces/.default`.
#:
#: NOT the "last active workspace" pointer #124 rejected, and the distinction is the whole
#: argument. That one is IMPLICIT: written by every `workspace use`, changing under sessions
#: that never asked, which is the failure `_terminal_id` was hardened against ("an id that is
#: wrong in the sharing direction is worse than no id"). This is EXPLICIT: set once by a
#: human, stable, and read only when every other rung has missed. `charter persona default`
#: is exactly this shape and already ships.
DEFAULT_FILE = ".default"


def default_file() -> Path:
    return config.WORKSPACES_DIR / DEFAULT_FILE


def declared_default() -> str | None:
    """The workspace nominated by `charter workspace default`, or ``None``.

    **Gated like every other committed file charter reads a name out of.** This dotfile is
    ordinarily committable (see :func:`set_declared_default`), so the value is a
    teammate's, and `resolve()` hands whatever it returns to `workspace_dir()`, which joins
    it onto ``workspaces/``. Unguarded, ``../../esc`` here made `workspace current`,
    `workspace vision` and `read_manifest` report content from outside the plane (#442).
    `valid_name` is the same rule `persona.default_persona` keeps for its own twin.

    Two checks, not one, because they answer different questions. `file_refusal` is about
    the *path*: this rung is read by `resolve()` on every status-line paint, so a FIFO
    committed at ``workspaces/.default`` would hang the paint rather than cost it a value.
    `valid_name` is about the *name* inside it. Neither stands in for the other.

    Never raises: a hook may cost a session its briefing and never its turn.
    """
    f = default_file()
    if contain.file_refusal(f):
        return None
    try:
        val = f.read_text().strip()
    except OSError:
        return None
    return val if val and valid_name(val) else None


def set_declared_default(name: str) -> None:
    """Nominate *name*. Raises ``ValueError`` for a name :func:`declared_default` would
    refuse to read back — writing a value the reader discards is a setting that silently
    does nothing, which is worse than an error."""
    name = name.strip()
    if not valid_name(name):
        raise ValueError(
            f"invalid workspace name '{name}' "
            "(use letters, digits, '.', '_', '-'; must not start with a dot)"
        )
    # A fixed name directly under `workspaces/`, which the default ignore rule
    # (`/workspaces/*/*`) does not match — so it is an ordinarily committable path, and a
    # link there redirects this write (#349).
    d = contain.writable(default_file())
    d.parent.mkdir(parents=True, exist_ok=True)
    d.write_text(name + "\n")


def clear_declared_default() -> bool:
    """Remove the nomination: ``True`` when a file was removed, ``False`` when there was none.

    Any other ``OSError`` from the unlink PROPAGATES. This swallowed every one, so the command
    could not tell "removed" from "nothing to remove" from "could not remove", and printed
    "Cleared" for all three — with `workspaces/` read-only, over a file still there that
    sessions went on landing on (#955, ADR 0013). A failed unlink removes nothing, so there
    is no partial state for the caller to read back: the exception is the whole account."""
    try:
        default_file().unlink()
    except FileNotFoundError:
        return False
    return True


def from_environment() -> str | None:
    """The workspace ``$CHARTER_WORKSPACE`` names, or ``None`` when it names none (#1055).

    **Stripped, and what is left empty is unset.** :func:`chosen` used to take the variable
    as its top rung whenever it was set and strip it only after that, so a value of
    whitespace chose ``""`` and hid every rung below it: the tree you stand in, the session
    and terminal pointers, the frame and the nominated default. :func:`resolve` then fell to
    the built-in `default`, :func:`source` named the variable as what decided, and the
    SessionStart nudge skipped asking, because the variable counted as a hard pin.
    `export CHARTER_WORKSPACE=$(…)` over a command that printed only a space or a tab leaves
    exactly that, and nobody chose it. Empty was already unset —
    `commands_frame._frame_identity_env` launches every chat with ``CHARTER_WORKSPACE=`` —
    and this is that rule one character further, the one `persona.from_environment` applies
    to ``$CHARTER_PERSONA`` (#1048) and `frame.state.workspace_for` already applied to this
    variable. A name inside the whitespace is that name.

    The one reading of the variable. Every rung that ranks it and every sentence that says
    it outranks something asks this, because a second copy is how the ladder and the warning
    about it came to disagree about ``" "``.
    """
    return os.environ.get("CHARTER_WORKSPACE", "").strip() or None


def blank_in_environment() -> bool:
    """``$CHARTER_WORKSPACE`` is set to whitespace and nothing else, so
    :func:`from_environment` ignored it (#1055).

    Worth saying because the operator's export is broken, and resolution going on through the
    rungs below hides that from them. Empty is not reported: it is what a frame launches every
    chat with when the launch pinned nothing, so it would be said in every chat about an
    export nobody wrote.
    """
    return bool(os.environ.get("CHARTER_WORKSPACE")) and from_environment() is None


def resolve(explicit: str | None = None, session_id: str | None = None,
            cwd=None) -> str:
    """Active workspace by precedence: ``--workspace`` → ``$CHARTER_WORKSPACE`` → **the
    tree you are standing in** → per-session pointer → **the frame you are inside**
    (:func:`for_frame`) → per-terminal pointer → ``default``.

    The cwd sits above the pointers because it cannot be wrong: a workspace's trees live
    at paths that name the workspace, so being inside one is not a hint about which
    workspace is active, it is the fact. The pointers remain for the case with no tree to
    stand in — a shell at the plane root.

    ``cwd`` names *whose* directory that rung should read, and exists because the process
    asking is not always the session being described. A status line is the case: Claude
    Code runs the hook and passes the session's directory in the payload, so a renderer
    reading ``os.getcwd()`` would answer for the hook. Callers that ARE the session — every
    CLI command — leave it unset and get the process cwd, which is the same fact.

    The whole ladder lives in :func:`chosen`; this is that answer with the built-in
    fallback underneath it. Two functions, one ladder — see :func:`chosen` for why the
    difference between them is the question #518 is about.
    """
    return chosen(explicit, session_id, cwd) or config.DEFAULT_WORKSPACE


def chosen(explicit: str | None = None, session_id: str | None = None,
           cwd=None) -> str | None:
    """The workspace something actually **chose**, or ``None`` when nothing did.

    :func:`resolve`'s ladder, minus its last rung. ``None`` means every rung came back
    empty and `resolve` is about to answer :data:`config.DEFAULT_WORKSPACE` — which is not
    a decision anybody made, it is the name charter falls back to when there is nothing to
    read. That difference is the whole of #518: `charter <harness>` "resolves a workspace
    silently", and the launch worth interrupting with a picker is exactly the one where
    nobody had chosen.

    **One ladder, asked twice — not two ladders that agree today.** `resolve` used to walk
    the rungs itself and this function would have been a second walker; that is the shape
    this module already warns about in :func:`valid_name` (one rule, two copies, and the
    reading site and the deciding site drift apart). A rung added here reaches `resolve`
    for free, and a picker that fired on a launch `resolve` had an answer for would be a
    prompt in front of a decision already made.

    :func:`source` remains a third walker: it answers a different question (a human label
    for a status line, including *why* nothing chose), and folding it in here would make
    this return a sentence. Its rungs must mirror these — that was already true before
    this split and is unchanged by it.

    ``declared_default()`` counts as a choice: somebody nominated it (#193). The built-in
    below it does not, and that is the one rung this function drops.
    """
    if explicit:
        return explicit
    env = from_environment()
    if env:
        return env
    here = from_path(cwd)
    if here:
        return here
    sid = _session_id(session_id)
    if sid:
        val = _read(_session_file(sid))
        if val:
            return val
    # The frame this session is running inside, if it is running inside one (#524). Below
    # the pointer above — an operator's `ws use` outranks a launch — and above the two
    # rungs below, which answer for the ASKING PROCESS and inside a frame are therefore
    # about the wrong terminal. See :func:`for_frame` for the whole reconciliation.
    framed = for_frame(sid)
    if framed:
        return framed
    tid = _terminal_id()
    if tid:
        val = _read(_terminal_file(tid))
        if val:
            return val
    # Below both pointers, above the built-in. What this replaces is not a considered
    # answer — it is a literal `default` workspace nobody chose either — so slotting a
    # nominated one here does not make workspaces less per-task; it makes the FALLBACK
    # something a human picked, and lets `default` go back to meaning "nobody ever chose"
    # (#193, unparking #124 on its own stated trigger: a terminal in common use that
    # supplies no pane id).
    declared = declared_default()
    if declared:
        return declared
    return None


def source(explicit: str | None = None, session_id: str | None = None,
           cwd=None) -> str:
    """Human label for where the active workspace came from (for display).

    Takes ``cwd`` for the same reason :func:`resolve` does, and must be called with the
    same one: a header that named the workspace from the session's directory and the
    *reason* from the process's would explain the answer by naming a rung that did not
    decide it.
    """
    if explicit:
        return "--workspace"
    if from_environment():
        return "$CHARTER_WORKSPACE"
    if from_path(cwd):
        return "cwd"      # must mirror `resolve`'s order, or the status line explains
                          # the active workspace by naming a source that did not decide it
    sid = _session_id(session_id)
    if sid and _read(_session_file(sid)):
        return "session"
    if for_frame(sid):
        return "frame"
    tid = _terminal_id()
    if tid and _read(_terminal_file(tid)):
        return "terminal"
    if declared_default():
        return "declared default"
    # Say WHY nothing answered, not just that nothing did. The operator's complaint was
    # "why are you in default workspace again?" — a surface asserting an answer with no
    # reason, twice, where reconstructing it meant reading `resolve`. ADR 0013's second
    # rule, aimed at the line people read every turn.
    if not _terminal_id():
        return "default (no pane id — nothing persists between sessions)"
    return "default (nothing selected)"


def _trace(event: str, session_id: str | None, **fields) -> None:
    """Record one workspace-selection event, best-effort.

    `persona.set_active` has recorded `persona-use` since the trace existed; the function
    that writes both workspace pointers AND the session lock recorded nothing, so "who
    moved my workspace" could only ever be answered from the pointer files themselves —
    which say what they hold and never who wrote it, when, or why. #254 is what that costs:
    two investigations, two confident wrong conclusions, settled in the end by a harness
    transcript charter cannot rely on existing.

    Swallows everything. Observability must never break the thing it observes, and a
    selection that failed because its own audit line failed would be the worst possible
    trade.
    """
    try:
        from . import session as _session, trace as _trace_mod
        _trace_mod.record(event, session=_session.current(session_id), **fields)
    except Exception:
        pass


def _lock_file(sid: str) -> Path:
    return config.SESSIONS_DIR / f"{sid}.lock"


def launch_lock(session_id: str | None = None) -> str | None:
    """The workspace this session's CHAT was launched for, which is its lock, or ``None``
    when this session is not a chat (#936).

    **A chat's lock is its launch record, not a file anybody writes.** Until #936 a chat was
    locked only when the operator PICKED at launch: `commands_frame._pin_workspace` writes
    the lock and returns early otherwise (#518). So a chat launched with `--workspace`, from
    a pointer, or by a reopen had no lock at all. Charter's own SessionStart told every such
    chat to run `charter workspace use <name>`, and there it SUCCEEDED: the chat's commands
    moved to the other workspace, the frame kept drawing it in its own, and `workspace use
    <own>` to undo that was refused as locked to the new one. A picked chat was refused the
    same advice. Two launch paths, two outcomes, one sentence recommending both.

    `frame/state.own_workspace` is the answer because it already is the one ladder for
    "which workspace does this chat belong to": the pin it was launched under, then what the
    launch resolved (#733, #791). §4j settles that a chat belongs to its workspace for life.
    Read and never written, so #518's "a launch that resolved silently … must keep writing
    none" holds to the letter, and a picked chat and a silent one hold the same lock.

    **Keyed on the id `session.current` answers, which every sub-agent inherits.** That is
    why #794 rejected refusing `workspace use` inside a frame, and it is why refusing is
    right. The pointer a sub-agent's `workspace use` writes lands under that same id, its
    PARENT chat's, so a sub-agent that succeeded would move the chat it serves. The routes a
    sub-agent does its work by write no pointer and are untouched: the tree it stands in
    (the cwd rung outranks every pointer) and `--workspace` per command.

    ``None`` for a session that is not a chat, because no frame directory exists under its
    id and both rungs of `own_workspace` answer nothing. ``None`` for no session at all
    too, answered by `contain.segment_ok` refusing the empty name; a second guard here would
    be one no test can turn red.
    """
    from .frame import state as _state
    return _state.own_workspace(_session_id(session_id))


def is_locked(session_id: str | None = None) -> str | None:
    """The workspace this session is **locked** to, or ``None`` if it has no lock yet.

    A lock is what forbids switching *mid-session*: once set, ``set_active`` refuses
    to move to a different workspace unless ``force=True``.

    **Two sources, and a chat's launch outranks the file** (#936). Inside a frame the lock
    is the workspace the chat was launched for (:func:`launch_lock`), whether or not anyone
    picked it. Outside one it is the file ``workspace use``/``create --use`` wrote, keyed by
    the session id, so every new session starts unlocked and gets to choose afresh.

    The launch comes first because the file under a chat's id can disagree with it only
    after a forced switch. If the file won, that chat could not go home: `workspace use
    <own>` would be refused as locked to the workspace it was forced into, which is the undo
    #936 measured failing. With the launch first, leaving the chat's workspace takes
    `--force` every time and returning to it takes nothing."""
    sid = _session_id(session_id)
    if not sid:
        return None
    return launch_lock(sid) or _read(_lock_file(sid))


def unlock(session_id: str | None = None) -> bool:
    """Drop this session's lock FILE (an explicit escape hatch). Returns True if one was
    cleared. Used by ``workspace unlock``; ``set_active(..., force=True)`` re-locks.

    A chat's lock is not that file, so this cannot release it. :func:`is_locked` answers a
    chat's launch record first (:func:`launch_lock`, #936), and ``workspace unlock``
    refuses inside a chat rather than report a release that did not happen."""
    sid = _session_id(session_id)
    if not sid:
        return False
    f = _lock_file(sid)
    if f.exists():
        f.unlink()
        return True
    return False


def set_active(name: str, session_id: str | None = None, force: bool = False,
               terminal_id: str | None = None) -> str:
    """Select ``name`` for THIS pane/session only, and **lock** the session to it.

    Writes a **per-terminal** pointer (keyed by a stable terminal id, so the pane
    keeps this workspace across closing/reopening Claude) and a **per-session**
    pointer (so the status line, which only knows the session id, agrees). Writes no
    global default, so selecting a workspace in one pane never changes another.

    **Session lock:** if this session is already locked to a *different* workspace,
    the switch is refused and ``"locked"`` is returned (nothing is written) — unless
    ``force=True``. Confirming a workspace locks the session to it, so the workspace
    can't be swapped out from under a running task. Returns the scope
    (``session`` | ``terminal`` | ``none``) on success, or ``"locked"`` when refused.

    **``terminal_id=""`` writes no terminal pointer, and that is not a micro-option — it
    closes #411 one caller over.** A frame's own switcher (`frame/switch.py`) runs as a
    ``run-shell`` child of charter's private tmux server, and that server is SHARED: its
    environment belongs to whichever launcher happened to start it, possibly days ago, in
    another terminal. :func:`_terminal_id` reads `$TERM_SESSION_ID`/`$TMUX_PANE`/`$STY`/
    `$SSH_TTY` out of that environment, so a switch inside frame B would otherwise write
    the pointer for the terminal that launched frame A — moving a workspace in a terminal
    nobody touched. Passing the empty string says "this process has no terminal to speak
    for", which is the truth there. ``None`` (the default) keeps today's behaviour for
    every ordinary caller: `charter workspace use` IS the terminal it is typed in."""
    locked = is_locked(session_id)
    if locked and locked != name and not force:
        _trace("workspace-refused", session_id, workspace=name, locked_to=locked)
        return "locked"
    config.private_mkdir(config.STATE_DIR)
    tid = _terminal_id() if terminal_id is None else terminal_id
    if tid:
        config.private_mkdir(config.TERMINALS_DIR)
        config.write_for(_terminal_file(tid), name + "\n")
    sid = _session_id(session_id)
    if sid:
        config.private_mkdir(config.SESSIONS_DIR)
        config.write_for(_session_file(sid), name + "\n")
        config.write_for(_lock_file(sid), name + "\n")  # confirming = locking
    _prune()
    _trace("workspace-use", session_id, workspace=name,
           scope=("terminal" if tid else "session" if sid else "none"),
           forced=True if force and locked and locked != name else None)
    # The scope is the REACH of what was written, so it names the longest-lived pointer
    # that actually landed — and the terminal one outlives the session one. These used to
    # be assigned in sequence, so the session branch overwrote the terminal branch and
    # every caller was told `session`. `_scope_note` reads persistence out of this value,
    # so a pane that HAD kept its workspace across restarts was told it had not, and a
    # shell with no pane id at all was told it had, which is the direction that costs
    # someone their selection with nothing having said so.
    return "terminal" if tid else "session" if sid else "none"


def reconcile(session_id: str | None = None, terminal_id: str | None = None) -> str | None:
    """On session start: if this Claude session has no pointer yet but its terminal
    pane does, copy the pane's selection into the session pointer — so the status
    line (which only knows the session id) shows the workspace the pane was on before
    Claude was reopened. Returns the seeded workspace, or None."""
    sid = _session_id(session_id)
    if not sid or _read(_session_file(sid)):
        return None
    tid = _terminal_id(terminal_id)
    val = _read(_terminal_file(tid)) if tid else None
    if val:
        config.private_mkdir(config.SESSIONS_DIR)
        config.write_for(_session_file(sid), val + "\n")
        # The one pointer write nobody typed. If any write is ever going to look as though
        # it came from nowhere, it is this one — so it says where it came from.
        _trace("workspace-seeded", session_id, workspace=val, **{"from": "terminal"})
    return val


def _prune() -> None:
    """Drop every per-session pointer past the cutoff — the DIRECTORY, not a list of names.

    This enumerated five suffixes (`*.workspace`, `*.lock`, `*.configver`, `*.memnudge`,
    `*.usage`) and read as an exhaustive list of the marker family while being nothing of
    the kind. Three families were missing by the time anyone looked: `*.ask-pending`,
    `*.route-pending` (`hooks`) and `*.persona` (`persona`, in both directories). The
    allowlist drifted three times, and a reader adding a fourth marker type had nothing
    telling them this list needed editing.

    The list is gone rather than three names longer, because a fourth drift is otherwise
    just a matter of time — a family added tomorrow is now covered the day it is written.
    Both directories are charter's own state and hold nothing but per-session and
    per-terminal pointers, so there is no member for which keeping it past the cutoff is
    the right answer. Files only: a directory in here is not a pointer, and unlinking is
    not the tool for one.

    Pruning `*.ask-pending` was checked against its readers rather than assumed safe — a
    declined ask deliberately leaves its marker behind, and that asymmetry is what makes
    "asked N, approved M" countable (#290). Nothing globs these suffixes: every reader
    (`_ask_mark_take`, `_route_mark_take`, `_route_mark_clear`) addresses one file by exact
    ids, and the tally itself lives in the trace store, which this does not touch.
    """
    cutoff = time.time() - _SESSION_MAX_AGE
    for d in (config.SESSIONS_DIR, config.TERMINALS_DIR):
        if not d.exists():
            continue
        for f in d.iterdir():
            try:
                if f.is_file() and f.stat().st_mtime < cutoff:
                    f.unlink()
            except OSError:
                pass


def list_workspaces() -> list[str]:
    """Directory names under ``workspaces/`` that are workspaces (not stray clones).

    :func:`read_workspaces`' first half, so it is one answer on every interpreter (#1043): an
    entry charter cannot `stat` is left out, where `Path.is_dir` raised for it on 3.11–3.13."""
    return read_workspaces()[0]


def uncheckable_workspaces() -> list[tuple[str, int | None]]:
    """The names under ``workspaces/`` that :func:`list_workspaces` leaves out because the
    filesystem will not say whether they are directories at all, each with the errno the check
    met.

    `Path.is_dir` answers False for a symlink loop, so a workspace directory that is one is not
    listed, and `workspace reinit --all` walked the rest and printed "Up to date — nothing to do"
    about a plane it had not looked at all of (#1028, ADR 0013). A caller that reports on every
    workspace names these; the listing itself stays as it is, because the status line and every
    other reader of it are asking which workspaces they can open, and these cannot be."""
    return [(d.name, code) for d, code in read_workspaces()[1]]


def read_workspaces() -> tuple[list[str], list[tuple[Path, int | None]]]:
    """:func:`list_workspaces` and :func:`uncheckable_workspaces` from ONE listing — the
    workspace names, and beside them every directory under ``workspaces/`` whose kind the
    filesystem will not tell, with its errno (#1043).

    A caller that reports on every workspace — each `doctor` row that lists them — asks this, so
    it cannot count what it read and name what it did not from two reads that disagree. A
    ``workspaces/`` that cannot be listed raises (:func:`read_directory`)."""
    _ensure_layout()

    def keep(d: Path) -> tuple[bool | None, int | None]:
        if d.name.startswith("."):
            return False, None  # charter's own (`.worktrees/`), never a workspace
        is_dir, code = _directory(d)
        return (is_dir and not is_clone(d)), code

    found, unread = read_directory(config.WORKSPACES_DIR, keep)
    return [d.name for d in found], unread


def read_workspaces_aloud() -> tuple[list[str], list[tuple[Path, int | None]]]:
    """:func:`read_workspaces`, having said on stderr, in :func:`cannot_check_workspace`'s
    words, each workspace it could not look at.

    For a command that shows the operator the plane's workspaces — `workspace list`, `status`,
    `sync --all`, `recall --all`, `workspace optimize` over all of them, `guard ask`'s mirror,
    `reinit --all` (#1043). `list_workspaces` leaves such a workspace out: on 3.14 it always did,
    and on 3.11–3.13 it raised instead, so each of those commands would now pass over it without
    a word on every interpreter. A caller only looking a name up, or asking which workspaces it
    can open (the status line, the frame's tabs), keeps :func:`list_workspaces`."""
    names, unread = read_workspaces()
    for d, code in unread:
        util.err(cannot_check_workspace(d.name, code))
    return names, unread


def _tab_order_file() -> Path:
    """Where this plane records the order its workspaces tab strip draws (#923).

    **Directly under `STATE_DIR`, beside `active-workspace`, `sessions/` and
    `terminals/`** — plane-scoped, per developer, gitignored, machine-written, and
    outliving any one chat.

    **NOT under `.charter/frame/<fid>/`, and that placement IS the fix.** #903 put it
    there, where `frame.state`'s opening line says everything is per frame and never
    global, and where `frame.state.reap` deletes it with the chat that wrote it. So every
    chat had an order of its own — and switching workspaces switches chats, which is how
    the operator met a different frozen order after every switch. The strip draws a
    plane-wide list, so its order is a plane-wide fact and lives at plane scope.
    `frame.state.NO_FORMAT_PROMISE` says the same thing from the other end: that tree is
    scratch charter may reshape in a patch release, which is no place for the one record
    every frame on the plane reads.

    **A function rather than a `config.derive` entry**, which is `frame.state._root`'s
    shape and `frame.gather._cache_file`'s: a state path spelled by the one module that
    reads and writes it. `config.derive` holds what several modules share — the roster
    directories, the session and terminal pointers — and this is read here and nowhere
    else. It stays isolated in tests for the same reason `_root()` does: `config.STATE_DIR`
    is read at CALL time, so `config.use()` repointing it moves this with it, and it is
    never bound at import.

    Neither committed nor `charter.toml`: a machine's reading of which workspaces were in
    use, rewritten whole at the next launch, and nothing a hand maintains.
    """
    return Path(config.STATE_DIR) / "workspace-tab-order"


def record_tab_order(names: list[str]) -> None:
    """Write down the order THIS PLANE draws its workspace tabs in (#923).

    **The order of the roster :func:`list_workspaces` answers, kept next to it**, because
    it is a fact about the same thing: which workspaces this plane has, and — since #903 —
    which of them the operator has been in lately. `frame/switch._by_use` decides the
    order and this holds it still; the split is `persona.by_use`'s (#882), one noun over.

    **Plane-scoped, and that is what #923 is.** #903 wrote this under
    `.charter/frame/<fid>/`, which is per-chat by construction — `frame.state`'s opening
    line — so every chat had an order of its own, seeded from the recency at the moment
    that chat first painted. Switching workspaces switches chats, so the operator met a
    different frozen order after every switch: *"feeling that each switch is opening new
    window."* Two chats of the SAME workspace disagreed. The strip draws a plane-wide list
    and now reads a plane-wide order, so every frame draws the identical columns.

    **Written once per plane launch, by whichever process first asks**, and
    :func:`forget_tab_order` is the other half — `frame.state.reap` calls it when a plane
    is left with no frame state at all, so the next launch decides afresh. Neither "once
    ever" nor "once per repaint" is the rule, and both were considered: once-ever ossifies
    (a workspace made next month sorts last for good), and re-deciding while a frame is
    open is the live reordering `slots._cuts` and `chats.of_workspace` both refused with a
    measurement. Once per launch is #903's own intent — still while you are looking at it,
    fresh when you come back.

    **An ORDER and never a roster.** `list_workspaces` decides which names exist, so a line
    here for a workspace that has since been deleted draws nothing and a workspace created
    since is appended by `switch._by_use`; there is no rewrite on change, which is what
    stops a stale line resurrecting a directory that has gone.

    One name per line, `config.replace_for` (#894, #893): this is read on a panel's render
    path and inside the `frame-resize` child, so a reader must never see half of it. Never
    raises — a full filesystem costs the plane its held order, which it recomputes on the
    next paint, and never a traceback out of a strip.
    """
    try:
        # `private_mkdir` and not `mkdir_for`: this writer names its own state path rather
        # than being handed one, which is the split `config.mkdir_for` documents. On a
        # plane whose `.charter/` does not exist yet — a first launch — the write below
        # would otherwise answer `ENOENT` and the order would be recomputed on every paint.
        f = _tab_order_file()
        config.private_mkdir(f.parent)
        config.replace_for(f, "".join(f"{n}\n" for n in names))
    except OSError:
        return


def tab_order() -> list[str]:
    """The order this plane draws its workspace tabs in, or ``[]`` when none is recorded.

    ``[]`` is the ordinary answer exactly once per plane launch — the first ask, before
    :func:`record_tab_order` has run — and it is also what an unreadable or truncated file
    answers. The caller's degrade for both is the same and is why they are not told apart:
    compute the order again, which is what this file was written from.

    **Name-checked on the way out**, like every other name charter reads off disk and joins
    onto a path (:func:`declared_default`, `frame.state.frame_workspace`). These names go
    on to a `workspace_dir()` join and onto a tab a click switches to, and #442 is what an
    unchecked one in that position already cost. An empty line is dropped by that check on
    its own terms — `valid_name("")` is already False — so there is no `if line` in front
    of it for no input to make observable.

    Stripped both ends, for `frame.state.chrome`'s reason: the file is one name per line,
    and a line is what lies between two newlines rather than what a hand left beside one.

    **`ValueError` beside `OSError`, and it is `UnicodeDecodeError` by its base class.**
    This file is charter's own UTF-8, but it is a file on a disk: a write torn by a full
    filesystem, or a hand that saved it in another encoding, reaches here as bytes
    `read_text` cannot decode. That is a `ValueError`, not an `OSError`, and it would come
    out of a panel's render path.

    **No `contain.file_refusal` in front of it**, where :func:`declared_default` has
    one, and the difference is whose file it is. `workspaces/.default` is ordinarily
    committable, so the thing at that path may be a teammate's — or a FIFO, which would
    hang the status line's every paint rather than cost it a value. This lives under
    `STATE_DIR`, which is 0700, per developer and never committed: what is there is what
    this process's own charter put there, and the name check is the floor that remains.
    """
    try:
        lines = _tab_order_file().read_text().splitlines()
    except (OSError, ValueError):
        return []
    return [n for n in (line.strip() for line in lines) if valid_name(n)]


def forget_tab_order() -> None:
    """Drop the recorded tab order, so the next ask decides it again (#923).

    **The end of a plane launch, spelled where the order lives.** `frame.state.reap` is
    charter's one observer of "this plane has no frame state left" and calls this from
    there; it already reaches one directory over for `_forget_session`, and this is that
    same shape for a plane-scoped file rather than a per-frame one.

    Missing is the ordinary case and not an error: a plane that has never drawn a strip,
    and a plane whose last frame already took the file. Never raises, for the same reason
    :func:`record_tab_order` does not — this runs inside a reap on a launch path.
    """
    try:
        _tab_order_file().unlink()
    except OSError:
        pass


def _arrivals_dir() -> Path:
    """Where this plane records which workspaces a handoff landed in and nobody has looked
    at yet — **a directory, and one file per mark.**

    **Beside `workspace-tab-order`, for every one of :func:`_tab_order_file`'s reasons.**
    It is plane-scoped (every frame on the plane draws the same mark, and the mark clears
    for all of them at once — `commands_frame._switch_client`), per developer, gitignored,
    machine-written, and it outlives any one chat: the chat that ran `charter handoff` may
    end long before the operator looks at what it opened, and a mark that died with it
    would be a workspace nothing points at.

    **A directory rather than one file listing the names, and that is a concurrency fix
    rather than a taste.** One file made every writer a read-modify-write over the whole
    set, and the plane runs many charter processes at once: measured with two real threads,
    two handoffs landing together left ONE mark, a handoff landing while a switch cleared
    brought the cleared mark back, and a switch clearing while a handoff landed lost the
    new one. A lost mark is precisely the invisibility this record exists to end.

    The alternative was a lock, and it was refused: a plane is shared by many processes
    that can be killed at any moment, so a stale lock file nothing clears is a worse
    failure than the one it fixes — and it would still be a fix by timing. One file per
    name makes recording and clearing **independent operations on different paths**, so
    there is no interleaving to get wrong. The mark IS the file's existence; the file is
    empty.

    **A set and not a log.** Nothing reads *when* a workspace arrived — the mark is drawn
    or it is not — and a timestamp nothing reads is the field ADR 0011 refuses. The empty
    file says so: there is nowhere for a field nothing reads to go.
    """
    return Path(config.STATE_DIR) / "workspace-arrivals"


def _arrival_mark(name: str) -> Path | None:
    """The file whose existence IS *name*'s mark, or ``None`` for a name that cannot be
    one.

    **The name check is here and it is load-bearing**, which is the one thing the
    single-file shape did not need: a name is now joined onto a path, so an unchecked one
    is `..` or an absolute path reaching out of `STATE_DIR` — #442 exactly, arriving
    through a record instead of through a directory listing. :func:`valid_name` is the same
    rule the callers already hold their names to, asked again here because this is where
    the join happens.
    """
    return _arrivals_dir() / name if valid_name(name) else None


def record_arrival(name: str) -> bool:
    """Mark *name* as a workspace a handoff landed in, until somebody looks at it.
    ``True`` when the mark is there afterwards.

    One empty file, created with `config.touch_for` for its mode (0600). `private_mkdir`
    first, for :func:`record_tab_order`'s reason — a plane whose `.charter/` does not exist
    yet.

    **`touch_for` and NOT `replace_for`, and the difference is a measured ceiling rather
    than a preference.** An atomic replace writes a temp file beside the target and renames
    it, and that temp name is the target's plus a suffix — so a workspace name within four
    characters of `NAME_MAX` made a temp name past it, `ENAMETOOLONG`, and a workspace that
    could be created and could never be marked. Nothing needs the atomicity here: the mark
    IS the file's existence, its content is empty, and there is no half-written state of
    nothing for a reader to catch. Creating it directly removes the temp name and the
    ceiling with it.

    **Touches no other name**, which is the whole of :func:`_arrivals_dir`'s concurrency
    argument: a second handoff landing in the same millisecond writes a different path, and
    a switch clearing another workspace unlinks a third. Re-recording a name that is
    already marked touches the identical empty file.

    **It does not raise and it does not go quiet either.** A failure here is a handoff that
    opened a chat nobody will be pointed at, which is the one outcome this whole record
    exists to prevent, so the answer is reported back rather than swallowed —
    `commands_handoff` says so on the operator's own screen. A name that cannot be a
    workspace is `False` for the same reason it is refused at the join: it marks nothing.
    """
    f = _arrival_mark(name)
    if f is None:
        return False
    try:
        config.private_mkdir(f.parent)
        config.touch_for(f)
    except OSError:
        return False
    return True


def arrivals() -> frozenset[str]:
    """The workspaces a handoff landed in that nobody has looked at yet.

    `frozenset()` for a plane that has never had a handoff — the ordinary answer, and the
    directory simply is not there — and for one whose record cannot be listed. One degrade
    for both, because the caller's answer is the same either way: draw the strip with no
    marks. A panel that threw out of `render` loses its pane.

    **Name-checked on the way out as well as on the way in**, which is not the same check
    twice: :func:`_arrival_mark` holds what charter WRITES, and this holds what is THERE —
    a hand, an editor's backup file, or a `.DS_Store` can put a name in this directory that
    charter never wrote, and these names go on to be matched against a strip.
    `valid_name("")` is already False, so there is no separate emptiness test.

    Only `OSError` is caught, and the absence of `ValueError` beside it is deliberate:
    nothing here decodes a file. `os.listdir` answers names the OS gave, undecodable bytes
    included, as surrogate-escaped `str` — which :func:`valid_name` refuses on its own
    terms, the alphabet being ASCII.

    **The listing is a local and the return is a set of NAMES, which is :func:`tab_order`'s
    shape and not a style choice.** `tests/_statedirscan.py` reads a function's return
    expression to decide whether that function hands back a PATH, and a one-liner
    `frozenset(e.name for e in os.listdir(_arrivals_dir()))` says a state path outright —
    so `arrivals` was classified as a state-path function, which taints every parameter its
    result is passed into and, through `_choose_workspace`'s picker, reported four
    unrelated `mkdir`s in this file as unrouted state writers. The scan was right about the
    shape: what comes back here is names, and the text now says so.
    """
    try:
        found = os.listdir(_arrivals_dir())
    except OSError:
        return frozenset()
    return frozenset(n for n in found if valid_name(n))


def clear_arrival(name: str) -> None:
    """Drop *name*'s arrived mark — somebody has looked at that workspace.

    One `unlink`, and **it touches no other name**: a handoff landing in another workspace
    at the same instant writes a different path and survives, where the single-file shape
    would have had one of the two writers overwrite the other's set.

    **Writes nothing when the name is not marked**, and that is now a property of the
    operation rather than a guard in front of it: `unlink` on a path that is not there
    raises `FileNotFoundError` and changes nothing — not the directory, not another mark's
    mtime. That matters because this runs on the switch, focus and attach paths, which is
    every time any terminal on this plane arrives anywhere.

    Missing directory, missing mark and a name that cannot be a workspace are one case for
    the same reason: none of them is a mark to remove.
    """
    f = _arrival_mark(name)
    if f is None:
        return
    try:
        f.unlink()
    except OSError:
        return


def forget_arrivals() -> None:
    """Drop every arrived mark — :func:`forget_tab_order` one file over, and called from
    the same branch of `frame.state.reap`.

    A plane that goes cold has no frame left that could be drawing a mark, and the operator
    who comes back to it is not owed a look at something they can no longer see was ever
    marked. Missing is the ordinary case; never raises, for the reason
    :func:`forget_tab_order` does not — `ignore_errors` is `rmtree`'s spelling of it.
    """
    shutil.rmtree(_arrivals_dir(), ignore_errors=True)


def clones(name: str) -> list[Path]:
    """The repo clones inside a workspace (``memory/`` and ``refs/`` are not clones —
    they have no ``.git`` — so this naturally excludes them)."""
    _ensure_layout()
    wd = workspace_dir(name)
    if not wd.exists():
        return []
    return sorted(d for d in wd.iterdir() if is_clone(d))


def read_clones(name: str) -> tuple[list[Path], list[tuple[Path, int | None]]]:
    """:func:`clones`, and beside them every directory in the workspace whose ``.git`` charter
    cannot `stat`, with its errno (#1043) — the entries `gitpolicy.scan` names and
    :func:`is_clone` answers "no clone" for. A workspace that cannot be listed raises
    (:func:`read_directory`)."""
    _ensure_layout()
    return read_directory(workspace_dir(name), lambda d: _directory(d / ".git"))


def repo_trees(ws: str) -> list[Path]:
    """Every repo this workspace works in — its clones, and nothing else.

    The one list anything asking "which repos am I on?" should use — the status line's
    rows and `gl-refresh`'s fetch targets both come from here, so a repo can never be
    drawn without its forge state having been fetched, or fetched without being drawn.
    Splitting that decision in two is what left a tree with a permanently empty CI column:
    it was rendered from one list and refreshed from another.

    The **plane root is deliberately not here**, and its absence is a decision rather than
    an oversight. The root is a git repo — personas carry committed memory, and a plane's
    own repo usually lives on a forge — but it is the plane, not a repo you work in.
    Listing it beside a workspace's clones would invite exactly the thing charter is trying
    to stop: two sessions editing one working tree while reporting two workspaces.

    Note what that does NOT buy: not listing the root does not prevent anyone working in
    it. That gap is why the status line and `doctor` warn about a dirty or off-branch root
    (docs/adr/0008).
    """
    return clones(ws)


def legacy_flat_clones() -> list[Path]:
    """Git repos sitting directly under ``workspaces/`` (pre-workspace layout).

    Through :func:`read_directory`, as :func:`read_clones` asks one level down (#1043):
    `Path.is_dir` raised on 3.11–3.13 for an entry charter cannot `stat`, which ended
    `charter status` in a traceback. Such an entry is named by :func:`read_workspaces_aloud`,
    and is no clone this can report."""
    _ensure_layout()
    return read_directory(config.WORKSPACES_DIR, lambda d: _directory(d / ".git"))[0]


def ensure(name: str) -> Path:
    """Create the workspace directory **and its baseline structure**; return its path.

    `scaffold` used to be called only by create/live/restore/fork, so a workspace born via
    `charter clone` or `charter workspace use` got a bare directory — and then the status
    line showed `⚠ reinit` on every turn, phrased as post-upgrade drift, for a workspace
    that had just been created correctly. The README's own quickstart ends that way.

    Scaffolding here rather than at each call site because "the directory exists" and "the
    directory is a workspace" were two different states with nothing keeping them in step;
    `needs_reinit` is meant to detect a plane left behind by an older charter, not one
    charter made a moment ago.
    """
    if not valid_name(name):
        raise ValueError(
            f"invalid workspace name '{name}' "
            "(use letters, digits, '.', '_', '-'; must not start with a dot)"
        )
    _ensure_layout()
    wd = workspace_dir(name)
    wd.mkdir(parents=True, exist_ok=True)
    try:
        scaffold(name)
    except Exception:
        pass          # best-effort: a workspace you can use beats one that failed to exist
    return wd


# --------------------------------------------------------------------------- #
# workspace memory + refs — a private, per-task journal beside the task's clones #
# (local/gitignored, like the clones; distinct from persona memory, which is the #
# shared, committed knowledge of a *role*).                                       #
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# workspace manifest — the COMMITTED, shareable setup: which repos on which      #
# branches. Clones stay gitignored; this + memory/ are tracked, so a workspace   #
# becomes a reproducible team artifact (`restore` rebuilds it from here).        #
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# live vs local workspaces. LOCAL (default) = fully private: clones, memory, and #
# manifest all gitignored, nothing committed. LIVE (opt-in) = shareable: its      #
# workspace.json + memory/ are un-ignored (via a managed .gitignore block) so the #
# commit/sync/auto-save flow applies. Liveness is recorded in that block, so it's #
# git-visible and travels with the control plane.                                  #
# --------------------------------------------------------------------------- #
_LIVE_BEGIN = "# >>> charter live workspaces (managed by `charter workspace live`) >>>"
_LIVE_END = "# <<< charter live workspaces <<<"


def _gitignore() -> Path:
    return config.ROOT / ".gitignore"


def live_workspaces() -> set[str]:
    """Names of workspaces marked LIVE (their un-ignore lines are in the managed block)."""
    try:
        text = _gitignore().read_text()
    except OSError:
        return set()
    out, inblock = set(), False
    for line in text.splitlines():
        s = line.strip()
        if s == _LIVE_BEGIN:
            inblock = True
        elif s == _LIVE_END:
            inblock = False
        elif inblock:
            m = re.match(r"!/workspaces/([^/]+)/workspace\.json", s)
            if m:
                out.add(m.group(1))
    return out


def is_live(name: str) -> bool:
    return name in live_workspaces()


def _live_block(names) -> str:
    """The managed .gitignore block un-ignoring every LIVE workspace's shareable paths.

    Each path is listed twice — the directory and its contents — because un-ignoring
    ``…/memory`` alone re-includes the directory entry and none of the files inside it.
    ``todos`` needs the same pair: a shared task list is one of the better reasons to make
    a workspace LIVE at all, and without a line here the list would simply never travel,
    which is the quietest way this could fail.

    ``changes`` needs the pair **and a third line that re-ignores ``changes/log``**, and
    that asymmetry is the whole design of the store rather than an exception to it. A
    change record holds intent — which repositories, which branch in each, which must land
    first, which was excluded and why — and intent is exactly what a teammate needs and git
    cannot derive. ``changes/log/<host>.jsonl`` holds the opposite: a past-tense
    declaration carrying merge shas, per host, appended without a lock, and it is committed
    **never**, for the same reason ``pieces/`` is not. Re-ignoring works only because its
    parent was re-included two lines above — git cannot re-include a file whose parent
    directory is excluded — which is why the three lines are written together here rather
    than as a rule someone reconstructs.

    The names are literals rather than ``change.DIRNAME``/``LOG_DIRNAME`` because
    :mod:`charter.change` imports this module; ``tests/test_todos_are_committed.py`` pins
    them against those constants, which is the same job an import would have done and the
    one that also catches ``_ws_meta_paths`` drifting away from this list.
    """
    lines = [_LIVE_BEGIN]
    for n in sorted(names):
        lines += [f"!/workspaces/{n}/workspace.json", f"!/workspaces/{n}/workspace.md",
                  f"!/workspaces/{n}/memory", f"!/workspaces/{n}/memory/**",
                  f"!/workspaces/{n}/todos", f"!/workspaces/{n}/todos/**",
                  f"!/workspaces/{n}/changes", f"!/workspaces/{n}/changes/**",
                  f"/workspaces/{n}/changes/log/"]
    lines.append(_LIVE_END)
    return "\n".join(lines)


def _write_live_block(names) -> None:
    """Rewrite the managed block for exactly *names*, creating it if absent."""
    gi = _gitignore()
    text = gi.read_text() if gi.exists() else ""
    block = _live_block(names)
    if _LIVE_BEGIN in text:
        text = re.sub(re.escape(_LIVE_BEGIN) + r".*?" + re.escape(_LIVE_END), block,
                      text, flags=re.DOTALL)
    elif "!/workspaces/.gitkeep\n" in text:
        text = text.replace("!/workspaces/.gitkeep\n", "!/workspaces/.gitkeep\n" + block + "\n", 1)
    else:
        text = text.rstrip("\n") + "\n" + block + "\n"
    gi.write_text(text)


def refresh_live_block() -> None:
    """Regenerate the managed block from the workspaces that are already LIVE.

    Idempotent, and it changes no workspace's liveness — it only brings the block up to
    the paths this version of charter shares. A plane made LIVE before `todos/` existed
    has a block listing four paths per workspace and nothing re-runs `set_live` on its
    own, so without this the list silently never travels for exactly the people who
    adopted the feature earliest.
    """
    _write_live_block(live_workspaces())


def set_live(name: str, live: bool) -> bool:
    """Mark a workspace LIVE (un-ignore its manifest+memory) or LOCAL (re-ignore).
    Returns True if the liveness changed. Rewrites the managed .gitignore block."""
    names = live_workspaces()
    if (name in names) == live:
        return False
    names = names | {name} if live else names - {name}
    _write_live_block(names)
    return True


def _rename_active_pointers(old: str, new: str) -> None:
    """Repoint any per-session/per-terminal pointer + lock whose value is ``old`` to
    ``new``, so a renamed workspace stays the active/locked one for its session."""
    for d in (config.SESSIONS_DIR, config.TERMINALS_DIR):
        if not d.exists():
            continue
        for f in list(d.glob("*.workspace")) + list(d.glob("*.lock")):
            try:
                if f.read_text().strip() == old:
                    config.write_for(f, new + "\n")
            except OSError:
                pass


def _rename_frame_records(old: str, new: str) -> list[str]:
    """Repoint any frame that says it is in ``old`` — :func:`_rename_active_pointers`'
    rule applied to the records that decide a chat's MEMBERSHIP rather than a session's
    work, which is the half #795 found missing. Answers the chats that moved, so the
    command can say how many: a rename that silently re-labels four running conversations
    is a thing the operator who typed it is entitled to see happen.

    The two are deliberately separate walks over separate directories rather than one
    generic sweep, because they answer different questions and are read by different code:
    a pointer says which workspace a session's `charter` commands act on, and
    `.charter/frame/<fid>/` says which workspace a CHAT is in. `frame/state.rename_workspace`
    owns the second — it is the module that writes those records, knows which of them are
    rungs of `own_workspace`, and has to bump each frame's version so its panels repaint.
    Imported here rather than at module scope: `frame.state` reads this module back.
    """
    from .frame import state as fstate
    return fstate.rename_workspace(old, new)


def rename(old: str, new: str) -> list[str]:
    """Rename a workspace: move its directory (clones + memory + refs come along),
    update the manifest ``name``, move its liveness (gitignore block) if live, repoint
    active pointers/lock, and repoint every chat that says it is in it (#795).
    Filesystem-level; the caller commits the tracked move for a LIVE workspace. Assumes
    the caller validated old exists / new is free. Answers the chats that followed."""
    was_live = is_live(old)
    workspace_dir(old).rename(workspace_dir(new))
    m = read_manifest(new)
    if m:
        m["name"] = new
        write_manifest(new, m)
    if was_live:
        set_live(old, False)
        set_live(new, True)
    _rename_active_pointers(old, new)
    return _rename_frame_records(old, new)


def manifest_path(name: str) -> Path:
    return workspace_dir(name) / "workspace.json"


def read_manifest(name: str) -> dict:
    """The committed manifest ({name, description, repos:[{name,branch}], …}), or {}.

    Gated like :func:`read_charter`, and for the same reason: `workspace.json` is committed,
    and this is where `restore` and `fork` learn which repos to clone."""
    p = manifest_path(name)
    if contain.dir_refusal(p.parent) or contain.file_refusal(p):
        return {}
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


#: The key charter stamps into a manifest it wrote, holding the digest of everything else
#: in the document.
#:
#: :data:`GENERATED_MARKER`'s rule in the one spelling this file can carry. That marker is a
#: SIDECAR because the document it describes belongs to Claude Code, and an unknown key in
#: it would be charter making a claim on somebody else's schema. `workspace.json` is
#: charter's own document, so there is no such claim to make — and a sidecar could not do
#: this job anyway: everything beside a manifest is gitignored and the manifest itself is
#: COMMITTED, so a teammate who pulls the plane would get the file and none of charter's
#: bookkeeping, and every shared manifest would read as hand-written on every machine but
#: the one that wrote it.
#:
#: A digest rather than a flag, for `_charter_owned`'s reason: a file whose content no
#: longer matches what charter wrote is the operator's now, and the writers nobody asked
#: for leave it completely alone.
MANIFEST_MARKER = "charter_generated"


def _manifest_body(doc: dict) -> str:
    """The text :data:`MANIFEST_MARKER` is the digest OF — the document without it.

    One function, so the stamp and the check are not two spellings of "the same content";
    :func:`content_digest` records what that costs when they drift. Canonical (sorted keys)
    rather than the bytes on disk, so re-indenting a manifest by hand does not take it away
    from charter while every value in it is still charter's.
    """
    return json.dumps({k: v for k, v in doc.items() if k != MANIFEST_MARKER},
                      sort_keys=True)


def manifest_owner(name: str) -> str:
    """Whose manifest is on disk: ``"absent"``, ``"charter"``, or ``"operator"``.

    The ownership question #884 turns on. charter creates this file and maintains its
    membership, and it must never overwrite one somebody else wrote — so "there is no
    manifest" and "there is one charter did not write" have to be different answers.

    **Present-but-unreadable answers ``"operator"``, never ``"absent"``.** A file charter
    cannot parse is emphatically not one charter wrote, and treating it as absent would
    make the automatic writers create a fresh manifest over exactly the hand-made file this
    rule exists to protect.
    """
    p = manifest_path(name)
    try:
        if not p.exists():
            return "absent"
    except (OSError, ValueError):
        # `exists()` raises on a path holding a NUL (ValueError) and can raise EACCES on
        # Linux, where pathlib does not swallow it — `_unreadable`'s case, answered the
        # cautious way: something is there that charter cannot account for.
        return "operator"
    doc = read_manifest(name)
    # `isinstance` and not a truth test: `read_manifest` hands back whatever JSON the file
    # holds, and `[]` is valid JSON. A committed file is an untrusted file (`restore`'s own
    # comment says so), and the digest is not a secret — anybody editing this by hand can
    # compute a matching one — so a list here would reach `.get` and take the command down
    # rather than being told it is the operator's.
    if isinstance(doc, dict) and doc.get(MANIFEST_MARKER) == content_digest(
            _manifest_body(doc)):
        return "charter"
    return "operator"


def write_manifest(name: str, data: dict) -> None:
    """Replace *name*'s manifest with *data*, stamped as charter's.

    The DELIBERATE writer — `snapshot`, `fork`, `rename` — which is why it asks
    :func:`manifest_owner` nothing: an operator who types `charter workspace snapshot` is
    asking for this file to be rewritten, and #884's rule is about the writes nobody asked
    for. Those are :func:`scaffold_manifest` and :func:`record_members`, and they check.
    """
    ensure(name)
    _write_manifest(name, data)


def _write_manifest(name: str, data: dict) -> None:
    """:func:`write_manifest` without the `ensure` — the writer this module calls, because
    `ensure` scaffolds and scaffolding is what calls this.

    **Atomic**: `config.replace_for`, the call `state.bump` and `gather.save` make, for a
    reason a committed file sharpens — one of this file's readers is `git add`, so half a
    manifest is not a glitch somebody re-runs past, it is half a manifest a teammate pulls.
    It writes through `config.write_for` for `state.bump`'s stated reason: ``os.replace``
    carries the SOURCE's mode onto the target, so the dispatch has to happen on the file
    that is moved rather than the one it lands on — and that is also why the temp file is
    not `tempfile.mkstemp`'s, whose 0600 would land on a file in the operator's own git
    tree. The temp NAME carries this writer's pid, which is #893: `ensure` scaffolds a
    manifest and `record_members` rewrites one, and two commands doing that at once for one
    workspace used to share a single ``workspace.json.tmp``.

    `contain.writable` first and by itself: a manifest path redirected out of the plane by a
    symlink is refused here rather than followed (#328), and the refusal RAISES, because
    every caller of this is on a command path where a write that quietly did nothing would
    print a tick over a fact nobody recorded.
    """
    p = contain.writable(manifest_path(name))
    doc = dict(data)
    doc[MANIFEST_MARKER] = content_digest(_manifest_body(doc))
    config.replace_for(p, json.dumps(doc, indent=2) + "\n")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _author() -> str:
    """Who charter records as having last touched a manifest, WITHOUT a subprocess.

    `commands_workspace._git_user` asks `git config user.name`, which is the better answer
    and costs a child process. This one runs from :func:`ensure`, which a tab press reaches
    with no operator waiting and which this module has never started a process from — so
    the cheap reading is the right one here. The field is provenance rather than identity,
    and `snapshot` restamps it with git's answer the moment anybody pins a branch.

    ``"unknown"`` rather than an absent field or an empty string, which is what
    `_git_user` answers too: a shell with no `$USER` is ordinary (a `cron`, a container),
    and a manifest field somebody has to guess the meaning of is worse than one that says
    nobody knows.
    """
    return os.environ.get("USER") or "unknown"


def _membership_rows(name: str) -> list[dict]:
    """The workspace's repos as MEMBERSHIP — a name each, and deliberately no branch.

    #884: recording a branch here would record whatever happens to be checked out at that
    instant, which for a workspace mid-work is a scratch branch — and a scratch branch
    written into a teammate's restore target is confidently wrong where an empty one is
    honestly empty, with `snapshot` there to fill it the moment an operator means to.

    It is also exactly where ADR 0010 draws its line. A branch in this file carries
    `snapshot`'s enforce-push promise — *"a manifest branch is only meaningful if it's
    actually on the remote"* — and a writer that runs without being asked can make no such
    promise, so it records the half of the file that needs none.
    """
    return [{"name": d.name} for d in clones(name)]


def scaffold_manifest(name: str) -> None:
    """Create the workspace's manifest if it has none. Never touches one that is there.

    #884: the file is committed *precisely so a teammate can restore someone else's
    workspace*, and while `snapshot` was its only writer it existed wherever somebody
    happened to run that command — 5 of 17 workspaces on the plane this was measured on. A
    file designed to be shared cannot be an opt-in side effect, so a workspace has one from
    birth and its presence is an invariant rather than a coincidence.

    A new workspace's manifest says ``repos: []``, which is a true and useful statement:
    this workspace exists, it is called *name*, and it has no repos yet. `repos` is one
    field among several rather than the point of the file. A workspace that already has
    clones when this first runs — every workspace the backfill reaches, via
    `charter workspace reinit` — records them as membership, unpinned
    (:func:`_membership_rows`).

    **Swallows its own failures.** `scaffold` runs from :func:`ensure`, which a tab press
    reaches with nobody waiting, and the components after this one in `scaffold` still have
    to run: a manifest that could not be written leaves the workspace exactly as it was, and
    `structure_status` goes on reporting the file missing, which is the honest answer and
    the one `charter workspace reinit` acts on.
    """
    try:
        if manifest_owner(name) != "absent":
            return
        _write_manifest(name, {"name": name, "description": "",
                               "repos": _membership_rows(name),
                               "updated_at": _now(), "updated_by": _author()})
    except (OSError, ValueError, contain.Refused):
        return


def record_members(name: str, repos) -> str:
    """Record *repos* as members of *name*'s workspace. Returns what happened —
    ``"unchanged"``, ``"recorded"``, ``"operator"`` or ``"blocked"``.

    The auto-update half of #884: membership is a fact about the workspace, so a repo
    cloned into one changes the manifest, and a manifest that learns its own membership
    only when somebody runs `snapshot` describes the workspaces nobody shared.

    **Additive, and that is a measurement rather than a shortcut.** Absence from disk does
    not mean a repo was removed: `restore --on-demand` deliberately leaves every recorded
    repo uncloned, and `restore` itself skips the ones this machine cannot reach
    (*"Partial access is normal"*). A reconcile against the directory would therefore erase
    the restore target of the teammate this file exists for, on their first launch, and
    their next `charter save` would push the erasure. Removal is recorded by
    `charter workspace snapshot`, which sets the list outright because an operator asked it
    to.

    **Never a branch** — see :func:`_membership_rows`.

    ``"operator"`` for a manifest charter did not write, which is left byte for byte alone.
    The caller says so rather than this deciding for them: a clone that could not be
    recorded is a fact the person at the keyboard can act on (`snapshot` rewrites the file
    deliberately), and swallowing it would make the invariant quietly untrue.
    """
    if manifest_owner(name) == "absent":
        # `ensure` gives every workspace a manifest, so getting here means the creating
        # write failed (a `workspaces/` nobody can write into) and a clone has since
        # succeeded. Through the one constructor rather than a second shape of "a fresh
        # manifest" assembled here — two of those drift, and the drift is invisible until
        # a field one of them omits is read.
        scaffold_manifest(name)
    owner = manifest_owner(name)
    if owner != "charter":
        return "operator" if owner == "operator" else "blocked"
    doc = read_manifest(name)
    # Rows that are not rows are dropped rather than crashed on. A committed manifest is an
    # untrusted document and the digest is not a secret, so `repos: [1, 2, 3]` with a
    # matching stamp is a file somebody can hand this plane.
    rows = [r for r in (doc.get("repos") or []) if isinstance(r, dict) and r.get("name")]
    have = {str(r["name"]) for r in rows}
    add = [n for n in dict.fromkeys(str(r) for r in repos) if n and n not in have]
    if not add:
        return "unchanged"
    # Sorted, so the committed file has one row order however the rows arrived — a clone,
    # a snapshot and a backfill all produce the same diff for the same membership.
    doc["repos"] = sorted(rows + [{"name": n} for n in add], key=lambda r: str(r["name"]))
    doc["updated_at"] = _now()
    doc["updated_by"] = _author()
    try:
        _write_manifest(name, doc)
    except (OSError, ValueError, contain.Refused):
        return "blocked"
    return "recorded"


def merge_repo_rows(manifest_rows, disk_rows) -> tuple[list[dict], list[str]]:
    """Union of what a workspace RECORDED and what it actually HAS.

    charter has two answers to "which repos are in this workspace" and they are both
    right about different questions. `status` and `workspace list` scan the directory:
    always current, never portable. The manifest is a **snapshot**: portable and
    committed, but written only by `charter workspace snapshot`, which deliberately
    refuses while a repo has unpushed work so a recorded branch can actually be restored.

    Nothing reconciled them, and `fork` read the manifest alone. So a workspace with nine
    clones and no snapshot reported nine repos everywhere a human looked and inherited
    zero — issue #81, observed live with the whole point of forking a task environment
    silently defeated.

    Taking the union rather than picking a winner is what keeps both cases working: a
    workspace nobody snapshotted still forks its clones, and a teammate who has just
    cloned the plane — with no repos on disk at all — still inherits from the snapshot.

    Where both know a repo, the **manifest's** branch wins: it was recorded under
    `snapshot`'s guarantee that the branch was pushed, where the disk only knows whatever
    happens to be checked out now.

    Returns ``(rows, disk_only)`` — rows sorted by name, and the names whose BRANCH came
    off the disk rather than out of a snapshot, which the caller reports rather than
    silently passing off as snapshotted.

    **Membership without a branch does not count as recorded, and since #884 that is the
    ordinary case.** Every manifest charter writes itself lists the workspace's repos with
    no branch, so keying this on "is the repo in the manifest" would have made `fork` stop
    saying *"their branch is whatever is checked out now, which may not be pushed"* about
    exactly the repos that sentence is true of. What the caller is warning about is the
    provenance of the BRANCH, so that is what is asked.
    """
    by_name: dict[str, dict] = {}
    for r in disk_rows or []:
        n = str(r.get("name") or "").strip()
        if n:
            by_name[n] = {"name": n, "branch": r.get("branch") or "HEAD"}
    disk_only = set(by_name)
    for r in manifest_rows or []:
        n = str(r.get("name") or "").strip()
        if not n:
            continue
        pinned = str(r.get("branch") or "").strip()
        if pinned:
            disk_only.discard(n)
        by_name[n] = {"name": n,
                      "branch": pinned or by_name.get(n, {}).get("branch") or "HEAD"}
    return [by_name[n] for n in sorted(by_name)], sorted(disk_only)


def memory_dir(name: str) -> Path:
    return workspace_dir(name) / "memory"


def refs_dir(name: str) -> Path:
    return workspace_dir(name) / "refs"


def notes_file(name: str) -> Path:
    return memory_dir(name) / "notes.md"


_WS_MEM_HEADER = (
    "# {name} — task memory\n\n"
    "One file per memory — a small, programmatically-explorable DB, not a single log to\n"
    "merge-conflict on. Files are timestamp-prefixed, so this index (and the directory) "
    "list chronologically. **Committed + shared** for LIVE workspaces. Write with "
    "`charter workspace remember \"…\"`, search with `charter workspace recall [--query …]`, drop "
    "one with `charter workspace forget <slug>`. Never put secrets here (vault only).\n"
)


def memory_index(name: str) -> Path:
    from . import memstore
    return memstore.index_path(memory_dir(name))


def scaffold_memory(name: str) -> Path:
    """Ensure the memory dir + MEMORY.md index; grandfather a legacy notes.md into the
    index so it stays discoverable. Returns the index path."""
    from . import memstore
    idx = memstore.ensure_index(memory_dir(name), _WS_MEM_HEADER.format(name=name))
    nf = notes_file(name)
    if nf.exists() and "(notes.md)" not in idx.read_text():
        memstore.index_append(idx, "notes.md", "Task memo (legacy)")
    return idx


def scaffold(name: str) -> None:
    """Create a workspace's baseline structure: memory/ (per-file DB + index), refs/, the
    workspace.md charter, the harness layer, and the structure-version marker. Idempotent
    + additive.

    Writes nothing when the workspace directory itself resolves outside the plane — a
    `workspaces/<ws>` committed as a symlink out of the plane would otherwise plant the whole
    baseline wherever it points. This refuses the directory as a whole so the refusal is one
    decision and not a race between several; `_in_the_way` answers for the same directory by
    the same `_inside` test, so `reinit` names what this refuses. Below it, each baseline path
    is judged by `_baseline_answers` (#1037), and the stamp by the kernel.
    """
    if not _inside(config.WORKSPACES_DIR, workspace_dir(name)):
        return
    # Nothing is written for a baseline path that could not be checked or has something in the
    # way — `_baseline_answers`, the one classification `structure_status` hands `reinit` to
    # name each path and this reads to leave it alone, so the two cannot disagree about one path. A `refs/` the
    # filesystem will not answer for (#980) or that is no directory (#1028) made the `mkdir`
    # raise `FileExistsError`; a `memory` that is a file (#1037) made the index write raise
    # `contain.Refused`; and a baseline name that is a symlink (#1037) was written THROUGH,
    # which created a file wherever a committed link pointed.
    clear = {rel: there is not None and blocker is None
             for rel, (_path, there, _code, blocker) in _baseline_answers(name).items()}
    if clear["memory/MEMORY.md"]:
        scaffold_memory(name)
    if clear["refs/README.md"]:
        refs = refs_dir(name)
        refs.mkdir(parents=True, exist_ok=True)
        rr = refs / "README.md"
        # `_exists`, never `Path.exists` (#942 final review): with the workspace's `refs/` at mode
        # 000 that raised on 3.11–3.13, and on 3.14 answered False so the write below raised
        # instead — a traceback out of `workspace reinit` on every interpreter, for a file charter
        # only creates where it is certainly absent. `reinit` names what could not be checked.
        if _exists(rr, follow=True) is False:
            # `create_for`, never `write_text` (#1037): the check above is `lstat` and then this,
            # and a link planted between the two is followed by a plain write.
            config.create_for(rr, f"# {name} — task references\n\nDrop docs, links, and "
                                  f"snippets for this task here (local, gitignored).\n")
    if clear["workspace.md"]:
        scaffold_charter(name)  # workspace.md — the living vision/context/glossary charter
    if clear["workspace.json"]:
        scaffold_manifest(name)  # workspace.json — the committed manifest (#884)
    wire_harnesses(name)    # the harness layer — see `harness_layer`
    # Stamp the layout version, never through a link — the rule every baseline file has
    # (#1037), asked of the open itself rather than of a check before it. `contain.write_refusal`
    # (#1062) refused a link out of the plane and followed one that stays inside it, dangling or
    # not, which `write_text` then created or overwrote. ``O_NOFOLLOW`` refuses a link wherever
    # it points (ELOOP), ``O_NONBLOCK`` a FIFO nobody reads (ENXIO) instead of hanging the
    # launch, and a directory refuses itself (EISDIR); the directory above is the `_inside`
    # test at the top. The marker is local, so a refused stamp costs only the stamp: the
    # workspace re-flags stale, and nothing is written into a tree charter did not choose.
    try:
        fd = os.open(_structure_marker(name),
                     os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_NONBLOCK, 0o666)
    except OSError:
        return
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(str(STRUCTURE_VERSION) + "\n")


# --------------------------------------------------------------------------- #
# the harness layer — what a chat standing in `workspaces/<ws>/` needs to get   #
# charter at all (#850).                                                        #
#                                                                               #
# Claude Code reads project settings from the session's working directory and    #
# does not walk up, so a chat launched there loaded no plugin, ran no status     #
# line and had no `$CHARTER_HARNESS` — while its agents and skills DID arrive,   #
# because those walk up and a workspace directory is not a git boundary. Half a  #
# layer, and the half that was missing is the half that runs.                    #
#                                                                               #
# ADR 0015 deleted a per-tree design of this shape and the caution is real, so   #
# the difference is worth stating: what it deleted wrote the same GLOBAL answer  #
# into every checkout, for a harness that reads one global file anyway. This     #
# writes config that is MEANT to differ per tree, into trees that genuinely      #
# differ. What is re-incurred from that design is the staleness bookkeeping      #
# below and, for a guest checkout only, its `.git/info/exclude` entry.           #
#                                                                               #
# Inside the workspace DIRECTORY that entry is still not needed and still not    #
# written: `/workspaces/*/*` is already in the plane's `.gitignore`              #
# (`_ensure_gitignore`) and the managed LIVE block un-ignores four named paths,  #
# none of them `.claude/`. Nothing generated there can reach a commit.           #
#                                                                               #
# A CLONE is the other half, and it is where the gap is widest (#870).           #
# `workspaces/<ws>/<repo>/` is a repo of its own, so the walk-up that carries    #
# agents and skills into the workspace directory STOPS at the clone's root and   #
# a chat launched there gets none of the layer — not the settings, and not the   #
# personas either. charter writes it anyway, and pays the cost the workspace     #
# directory does not owe: every generated path is registered in that checkout's  #
# `.git/info/exclude`, which is per-checkout, never committed and not itself     #
# tracked. It is the one file a guest may write. charter never touches the       #
# clone's `.gitignore`, never stages anything there, and hides only the exact    #
# paths it generated — see `_charter_owned` for why the block is a list of files #
# rather than a `.claude/` glob.                                                 #
# --------------------------------------------------------------------------- #

#: The charter-owned sidecar recording what charter last generated in a workspace, as
#: ``{relative path: sha256 of the text charter wrote}``.
#:
#: **A sidecar and not a key inside the vendor's JSON**, which is the same reason
#: symlinking `.claude/` was wrong: that file's schema belongs to Claude Code, an unknown
#: key in it is charter making a claim on somebody else's document, and a validator that
#: rejects unknown keys would make charter's bookkeeping a startup failure. `persona
#: sync-agents` can put its marker INSIDE the file it generates because Markdown has a
#: comment syntax; JSON has none, which is precisely why this exists as a file.
#:
#: `.charter-structure` is the precedent for a charter-owned marker file in a workspace,
#: and this sits beside it for the same reason: one directory, one place to look.
GENERATED_MARKER = ".charter-generated"


def content_digest(text: str) -> str:
    """The hash the marker records for one generated file.

    Named and public because the writer and the ownership test must not be two spellings
    of "the same content" — a marker written one way and read another reports every file
    charter wrote as somebody else's, which is the direction that costs work.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_workspace_dir(path) -> bool:
    """Is *path* one of THIS plane's workspace directories?

    The boundary the whole mechanism draws, asked in one place. A clone under a workspace
    (`workspaces/<ws>/<repo>/`) answers **no** — it is somebody else's repo — and so does
    the plane root, whose `.claude/settings.json` is user-owned, git-tracked and governed
    by the never-repair restraint `commands._ensure_guard_hook` records.

    :func:`valid_name` is asked first for :func:`exists`' reason: ``WORKSPACES_DIR / ".."``
    is the plane root, so a parent-directory comparison alone answers *yes* for a name
    that is not a workspace and can never be one.
    """
    p = Path(path)
    if not valid_name(p.name):
        return False
    # NO `try` around the comparison. `PurePath.__eq__` is a string compare on the
    # normalised parts — it never touches the filesystem, so it cannot raise `OSError`,
    # and a catch there is a branch nothing can reach. Measured against a NUL byte, a lone
    # surrogate, 4000 slashes and the empty string: every one answers `False` rather than
    # raising. The deletion sweep found the narrowed catch as a survivor and was right.
    return p.parent == config.WORKSPACES_DIR


def harness_deficits() -> list[tuple[str, object]]:
    """``(harness name, Deficit)`` for every registered harness that cannot isolate.

    A workspace DIRECTORY is not a config scope for them, so per-workspace divergence is
    not buildable there — Codex reads no project config file at all, and opencode's is keyed
    to the repository root, which every workspace under the plane shares. Reported rather
    than skipped in silence: `base.Deficit` exists for exactly
    this — *"a capability that is simply missing reads as a broken integration"* — and a
    report showing one row for the harness that can and nothing for the two that cannot
    would be read as three ticks.
    """
    from .harness import base as _base
    from .harness import registry as _registry

    out: list[tuple[str, object]] = []
    for h in _registry.all():
        gap = next((d for d in h.deficits if d.key == _base.WORKSPACE_SCOPE), None)
        if gap is not None:
            out.append((h.name, gap))
    return out


def _cowritten() -> frozenset[str]:
    """Every registered harness's :attr:`Harness.cowritten` — generated paths the harness
    also writes into itself, which charter keeps hidden and never rewrites once edited.

    ``getattr`` rather than the attribute: a stand-in harness that declares none must mean
    none, not an `AttributeError` out of every guest wire.
    """
    from .harness import registry as _registry

    return frozenset(p for h in _registry.all() for p in getattr(h, "cowritten", ()))


def _held_files() -> dict[str, str]:
    """``{generated relpath: source}`` for every source a registered harness cannot read now.

    See :meth:`Harness.held_files`: charter keeps what is on disk at those paths, neither
    writing nor withdrawing it. A harness that does not answer holds nothing.
    """
    from .harness import registry as _registry

    out: dict[str, str] = {}
    for h in _registry.all():
        member = getattr(h, "held_files", None)
        out.update((member() if member else None) or {})
    return out


def _harness_files(base: Path, which: str = "workspace_files") -> dict[str, str]:
    """:func:`_layer_files`' body, asked of any directory charter is about to write into.

    Takes a path rather than a workspace name because a guest checkout has no name in
    `WORKSPACES_DIR` — and the containment check below is the reason this is one function
    and not two: it is what keeps a harness's ``..`` out of the tree it is joined onto,
    and a copy of it per target is a copy that can drift out of step.

    *which* names the member that answers: :meth:`Harness.workspace_files` for every
    directory charter writes into, :meth:`Harness.checkout_files` as well for a checkout
    with a git root of its own (#942) — so the second question gets this containment rather
    than a copy of it. A harness without the member answers nothing, the way `or {}`
    already treats one answering ``None``.
    """
    from .harness import registry as _registry

    out: dict[str, str] = {}
    for h in _registry.all():
        member = getattr(h, which, None)
        for rel, text in ((member() if member else None) or {}).items():
            # The HARNESS CONTRACT, and only it: a declared relative path may not escape the
            # tree it is joined onto. LEXICAL on purpose — `normpath` collapses `..` without
            # touching the disk, so `../svc/x.json` from `svc/` (which lands back inside) is
            # kept while `../escaped.json` is dropped, and a plane reached through a symlink is
            # judged by the name `config.use` was handed, not one charter resolved
            # (`AWorkspaceRootReachedThroughASymlink`).
            #
            # It deliberately does NOT decide where a committed LINK at a clean name points:
            # a `.claude/settings.json` symlinked out of the checkout has a clean `rel`, so it
            # passes here and is named downstream — `foreign` by `_layer_status`, refused by
            # `_write_whole` — rather than dropped with no row, which once let a guest keep the
            # plane's ask/deny rules out of a chat silently. That containment is `_inside`'s,
            # asked where the path is actually written and read.
            joined = os.path.normpath(os.path.join(str(base), rel))
            nbase = os.path.normpath(str(base))
            if joined != nbase and not joined.startswith(nbase + os.sep):
                continue
            out[rel] = text
    return out


def _layer_files(name: str) -> dict[str, str]:
    """``{relative path: text}`` every registered harness needs inside workspace *name*.

    Nothing here names a harness — the registry is iterated, so a harness added to
    ``KINDS`` is covered the day it is registered, which is the reason
    `harness/registry.py` records for its own existence. A harness that cannot hold
    per-workspace config returns nothing AND declares :data:`base.WORKSPACE_SCOPE`;
    :func:`harness_deficits` is what turns the second half into a sentence.

    A relative path that would escape the workspace is dropped rather than written. The
    harness contract says paths stay inside; a contract nothing enforces is a comment,
    and this is the one place every harness's answer passes through.
    """
    return _harness_files(workspace_dir(name))


def _inherited_files() -> dict[str, str]:
    """``{relative path: text}`` for the plane paths a guest checkout cuts a session off from.

    Which paths those are is every registered harness's own
    :attr:`harness.base.Harness.inherited_paths` — Claude Code's `.claude/agents` and
    `.claude/skills`, opencode's `.opencode/agent`, Codex's `.codex/skills`. **Nothing here
    names any of them**, and that is the whole of #868.
    This function held Claude Code's two as a literal, under a comment stating the limit
    honestly, and an honest limit is still a limit: an operator on opencode or Codex got a
    workspace with none of the plane's agents or skills. The registry answers now, so a
    harness registered tomorrow is carried the day it declares a surface.

    `workspaces/<ws>/` needs none of this and gets none of it. Every one of those paths is
    resolved from a directory inside the plane's own repository — by a walk that stops at
    the git root, or by resolving the repository root itself — so a workspace directory
    already reads the plane's copies, and a second copy would shadow the first
    non-deterministically. `workspaces/<ws>/<repo>/` is a repository of its own, which is
    where all of them stop.

    A 1:1 mirror of what is on disk, for `workspace_files`' reason: `.claude/agents/` is
    generated from `personas/` by somebody else's generator, so re-deriving it here would
    be a second generator that drifts. Read as text and skipped when that fails — a binary
    or unreadable file is not something charter can copy, and it must not take the whole
    layer down with it.
    """
    from .harness import registry as _registry

    out: dict[str, str] = {}
    for sub in _registry.inherited_paths():
        d = config.ROOT / sub
        # `(d, *d.rglob("*"))` — the path ITSELF, then everything under it, because a
        # harness may spell this as one FILE at a repository root rather than as a tree.
        # Every shipped harness spells it as a tree today; half the in-repo surfaces
        # charter has measured are single files, and `rglob` on a file yields nothing at
        # all — so without `d` in front, the next harness to spell it that way would mirror
        # as nothing, silently and with no row anywhere saying so.
        #
        # No `is_dir()` guard and no `is_file()` filter. Reading a directory raises
        # `IsADirectoryError`, reading a path that is not there raises `FileNotFoundError`,
        # and a dangling symlink and a binary file raise too — all of them one answer here,
        # "not text charter can mirror", which the read already gives. A predicate in front
        # of it is a branch the deletion sweep can remove without changing a single answer,
        # which is what makes it noise — and so was the `sorted()` that used to wrap this,
        # for the same reason: every entry is an independent key in a dict, and
        # `_layer_status` sorts what it reports anyway. The sweep found it and was right.
        for f in (d, *d.rglob("*")):
            try:
                text = f.read_text()
            except (OSError, UnicodeDecodeError):
                continue
            rel = f.relative_to(d).as_posix()
            # `d.relative_to(d)` is `.`, so a declared FILE would land at the key
            # `<path>/.` — a path that names nothing, hides nothing, and turns the file
            # into a directory on the way in.
            out[sub if rel == "." else f"{sub}/{rel}"] = text
    return out


def _guest_files(tree: Path) -> dict[str, str]:
    """Everything charter generates inside the guest checkout *tree*.

    The harness layer the workspace directory gets, PLUS what that directory did not need:
    the in-repo paths a git boundary cuts off (:func:`_inherited_files`), and the files a
    harness resolves at the git root (:meth:`Harness.checkout_files`), which the plane's own
    copy already answers for a workspace directory and nothing answers for a clone (#942).

    Two questions, deliberately kept apart. `_harness_files` asks each harness what it
    needs in a directory charter OWNS, and the answer is generated content. This asks which
    of the PLANE's own paths a git boundary cuts off, and the answer is a copy of what is
    on disk. A harness declares both, and neither can be derived from the other: charter
    cannot generate a plane's personas, and it must not mirror a file it generated.
    """
    out = _harness_files(tree)
    out.update(_harness_files(tree, "checkout_files"))
    out.update(_inherited_files())
    return out


def _marker_key_ok(key: str) -> bool:
    """Whether *key* is a name charter could have recorded — a relative path that names a
    file inside the checkout, and nothing else.

    Charter's own keys are relative paths built from a checkout root, so a key that is
    absolute, drive-qualified, or carries a `..` segment could only have come from a hand-
    written or committed marker, and joining it onto the checkout reaches OUTSIDE. One such
    key makes the whole marker untrusted (:func:`_read_marker_at`), for `contain`'s reason:
    a record charter did not write is not evidence about any path.
    """
    # No `isinstance(key, str)`: the one caller hands keys of a `json.loads` object, and JSON
    # object keys are strings — the check could never refuse one.
    if not key or "\x00" in key:
        return False
    if os.path.isabs(key) or os.path.splitdrive(key)[0]:
        return False
    # Backslash as well as `/`: the marker travels in a committed tree, so the machine that
    # wrote a key is not necessarily the one that resolves it (`contain._SEPARATORS`).
    return ".." not in key.replace("\\", "/").split("/")


def _marker_untrusted(base: Path) -> bool:
    """Whether git TRACKS `base/.charter-generated` in the guest checkout *base* — a marker
    charter did not write.

    Charter never writes a marker git tracks — its own is per-checkout and gitignored in
    `info/exclude`, and stays charter's even when that exclude is emptied (still untracked).
    So a TRACKED marker is committed content whose digests are not charter's word about which
    files are charter's: its whole record is dropped. This is the clone-delivered boundary — a
    marker committed in a repository the operator clones arrives TRACKED — and the destructive
    side is defended independently by :func:`_generated_roots`, so a marker that is merely
    present-but-untracked (a `git rm --cached` left in the source tree, which no clone carries)
    still cannot withdraw a file charter never generated.

    Asked of git the way `util.git_path_state` asks it, and only of a checkout with a git root
    of its own — a workspace directory's marker is charter's, gitignored by the plane, and
    needs no git spawn. Memoised per :func:`worktree_answers` block, so a launch or a doctor
    run asks at most once per checkout. `doctor` names it (:func:`guest_layer`).
    """
    if git_dir(base) is None:
        return False
    # Only ask about a marker that is actually there: `git status -- <absent path>` prints
    # nothing and exits 0, which `git_path_state` reads as TRACKED — so an absent marker would
    # answer "tracked" for a checkout that has none. `_exists` is lstat, so a hostile marker
    # LINK counts as there (its node exists) and is asked about.
    if _exists(base / GENERATED_MARKER) is not True:
        return False
    key = os.path.realpath(base)
    cache = getattr(_SCOPE, "tracked", None)
    if cache is not None and key in cache:
        return cache[key]
    answer = util.git_path_state(base, GENERATED_MARKER)[0] == util.TRACKED
    if cache is not None:
        cache[key] = answer
    return answer


def _read_marker_at(base: Path) -> dict:
    """The marker at *base*: ``{}`` when there is none, one charter cannot read — empty, torn,
    not a JSON object, or refused — one git TRACKS, or one holding a key that leaves *base*.

    One answer again since #942 review round 5 (R2). `_marker_or_none` told a record charter had
    lost from one that did not exist, for `_shared_rels`, which let a line go once a record it
    could READ said the path was not charter's. Hiding follows the files that are there now, and
    no record takes a line away, so every caller left asks only what charter may write, withdraw
    or add a line for — where "nothing is charter's" alters nothing.

    **A marker charter cannot have written is not charter's record.** A `.charter-generated`
    git tracks (:func:`_marker_untrusted`), or one whose keys are not the relative in-checkout
    names charter records (:func:`_marker_key_ok`), is committed content: trusting its digests
    is how a guest names a file — its own, or one a link redirects out of the tree — as
    charter's to rewrite or unlink. The whole marker is dropped; charter writes a fresh one
    through the containment check, so nothing is lost that was really charter's. The destructive
    side is defended once more by :func:`_generated_roots`, so even a marker charter does trust
    withdraws only files under charter's own generated tree.
    """
    try:
        doc = json.loads((base / GENERATED_MARKER).read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(doc, dict):
        return {}
    if not all(_marker_key_ok(k) for k in doc):
        return {}
    if _marker_untrusted(base):
        return {}
    return doc


def _read_marker(name: str) -> dict:
    return _read_marker_at(workspace_dir(name))


def _exists(p: Path, follow: bool = False) -> bool | None:
    """Whether *p* is there — ``True`` or ``False`` — or ``None`` when the filesystem will not say.

    Ruling G(e) (#942 review round 3): only `FileNotFoundError` or `NotADirectoryError` from
    `os.lstat` proves a path gone. `os.path.lexists` answers False for EVERY error — EACCES, EIO,
    ESTALE — and `Path.exists` raises on 3.11–3.13 where it answers False on 3.14. Read as
    "gone", one refused lstat during a launch forgot a marker entry for good; raised, one
    unreadable `.claude/` crashed `workspace reinit`.

    *follow* asks through a symlink (`os.stat`): the question "is `workspace.json` there" means
    the manifest behind the link, and a dangling link is a manifest that is not there — the
    blocker `cmd_workspace_reinit`'s tests use (review round 4).
    """
    return _existence(p, follow)[0]


def _existence(p: Path, follow: bool = False) -> tuple[bool | None, int | None]:
    """:func:`_exists`'s answer, and the errno behind a ``None`` — ``(there, code)``.

    The classification lives here alone, and `_exists` is this function with the cause dropped:
    a caller that words what to DO about an unreadable path (`reinit`, through
    `structure_status`) and a caller that only asks whether to write must not answer "is it
    there" from two different reads. The cause is `None` whenever the path was answered for."""
    there, _st, code = _looked(p, follow)
    return there, code


def _looked(p: Path, follow: bool) -> tuple[bool | None, os.stat_result | None, int | None]:
    """:func:`_existence`'s one `stat`, with what it returned — ``(there, stat, code)`` — so a
    caller that asks what KIND of thing is there (:func:`_directory`) classifies the errno the
    same way rather than a second way."""
    try:
        return True, (os.stat if follow else os.lstat)(p), None
    except (FileNotFoundError, NotADirectoryError):
        return False, None, None
    except OSError as e:
        return None, None, e.errno


def _directory(p: Path) -> tuple[bool | None, int | None]:
    """Whether *p*, through a link, is a directory — ``(True|False, None)`` — or ``(None, errno)``
    when the filesystem will not say.

    `Path.is_dir` has no third answer (#1043): for a path charter may not `stat` it raised on
    3.11–3.13 and answered False on 3.14, so a workspace under a `workspaces/` at mode 666 cost a
    doctor row on one interpreter and vanished from it on the other. :func:`_existence`'s
    classification, asked of the mode it read."""
    there, st, code = _looked(p, follow=True)
    return (stat.S_ISDIR(st.st_mode) if there else there), code


def read_directory(d: Path, keep=None) -> tuple[list[Path], list[tuple[Path, int | None]]]:
    """The entries of directory *d* that *keep* keeps, sorted, and beside them each entry *keep*
    could not tell about, with its errno — ``(entries, unread)``.

    *keep* asks one entry and answers ``(True|False, None)`` or ``(None, errno)``, the shape of
    :func:`_existence`; without it every entry is kept. An entry it cannot tell about is unread,
    never dropped as "not one" and never raised (#1043) — the three answers `Path.is_dir` and
    `Path.glob` gave for "could not look" were raise, False and an empty list.

    A *d* that is not there, or is not a directory, has no entries. A *d* that is there and cannot
    be LISTED raises the `OSError`, as `Path.iterdir` does: nothing under it can be counted, so the
    caller names it on its own, apart from any entry (the shape #982 and #987 gave the listing).
    Asked through `Path.iterdir`, which refuses on 3.11–3.14 alike."""
    try:
        entries = sorted(d.iterdir())
    except (FileNotFoundError, NotADirectoryError):
        return [], []
    if keep is None:
        return entries, []
    kept: list[Path] = []
    unread: list[tuple[Path, int | None]] = []
    for p in entries:
        yes, code = keep(p)
        if yes is None:
            unread.append((p, code))
        elif yes:
            kept.append(p)
    return kept, unread


def _stopped_at(p: Path, code: int) -> Path:
    """The shallowest directory above *p* whose own `stat` meets *code* — else *p* itself, whose
    check already met it.

    A check through a symlink fails at the first component that fails, not at the path it asked
    about (#980): with a workspace's `refs/` a loop, `refs/README.md` answers ELOOP, and "fix the
    symlink loop at refs/README.md" sends the reader to a file that is no link at all, while
    `doctor` names `refs/`, where the loop is. A directory that answers anything but *code* is not
    taken for the cause, so a filesystem that changed in between costs precision and never names a
    path that did not fail that way."""
    for q in reversed(p.parents):
        if _existence(q, follow=True) == (None, code):
            return q
    return p


def _in_the_way(p: Path, base: Path) -> tuple[Path, int] | None:
    """The path from *base* down to *p* that stands where the layout needs something else, with
    the errno a create there meets — ``ENOENT`` for a directory that is a symlink whose target
    is gone, ``ENOTDIR`` for a directory that is anything else that is no directory, ``ELOOP``
    for a symlink charter will not follow — or ``None`` when nothing is.

    `_existence` calls *p* gone for the first two (#1028), and truthfully: nothing is at *p*.
    But "gone" is read as "create it", and a create through a link to nowhere or under a file
    raises out of `workspace reinit` — `mkdir(exist_ok=True)` forgives a directory, not a
    name that is there and is none. So "gone because something stands where its directory
    goes" is told apart here, once, for `structure_status` to name and `scaffold` to write
    nothing under. A directory the filesystem will not answer for is not this function's:
    that is `_existence`'s ``None``, and `_stopped_at` names it.

    ``ELOOP`` is #1037, and it is asked with `lstat` because every other question here
    follows the link it is about. A workspace's tree is committed, and git stores a symlink as
    a symlink, so a link in it is something a teammate's commit can put there: `_existence`
    called a link to nowhere at ``refs/README.md`` gone, and `scaffold` wrote the README
    through it, creating a file wherever the link pointed. So a link where a FILE belongs is in
    the way wherever it points, and so is one where a DIRECTORY belongs unless it lands on a
    directory inside the plane's data, which is the link `contain` has always followed and the
    repointed ``refs`` #1028's sentence sends an operator to. *base*, the workspace directory,
    is a directory of the layout too, and a link there must resolve inside ``workspaces/`` —
    `_inside`, the test `scaffold` and the harness layer refuse the whole directory by (#1062),
    so what they refuse is what `reinit` names. ``ELOOP`` because it is what the kernel answers
    an ``O_NOFOLLOW`` open at a link.

    Nothing above *base* is asked. The plane root and the temp directory above it may be links
    for reasons nobody committed (``/var`` is one on macOS), and every caller has already
    reached *base* through them. Walking from the filesystem root also cost a `lstat` and a
    `stat` per component per baseline path, and `structure_status` runs for every workspace on
    each status line render."""
    walk = [base]
    for part in p.parts[len(base.parts):-1]:
        walk.append(walk[-1] / part)
    for q in (*walk, p):
        try:
            link = stat.S_ISLNK(os.lstat(q).st_mode)
        except OSError:
            # ONE clause. Absent (ENOENT) is what a create makes, and unanswered (EACCES) is
            # `_existence`'s `None` for `_stopped_at` to name; neither is in the way. The two
            # clauses this was returned the same `None`, so CI's sweep narrowed either with the
            # suite green: an equivalent pair is one clause. (A file above *q* beneath *base* is
            # returned by the `stat` below one step earlier, so its ENOTDIR never reaches here.)
            return None
        if q is p:
            return (p, errno.ELOOP) if link else None
        try:
            st = os.stat(q)
        except (FileNotFoundError, NotADirectoryError):
            return q, errno.ENOENT  # the name is there (`lstat`) and resolves to nothing
        except OSError:
            return None
        if not stat.S_ISDIR(st.st_mode):
            return q, errno.ELOOP if link else errno.ENOTDIR
        # The workspace directory answers to the test `scaffold` and the harness layer refuse it
        # by (#1062): it must resolve inside `workspaces/`. A directory beneath it follows
        # `contain`'s rule for plane data, so a `refs` repointed at another workspace's still is.
        if link and (not _inside(config.WORKSPACES_DIR, q) if q is base
                     else contain.dir_refusal(q, "write")):
            return q, errno.ELOOP
    return None


def _recorded(marker: dict, rel: str) -> tuple[str, ...]:
    """The digests *marker* vouches for at *rel*: one when settled, several while pending.

    **Silence is not a verdict** (ruling H, #942 review round 4). Before charter rewrites a
    generated file it PUBLISHES that file's entry as a list — every digest the path may hold
    while the write is under way — and settles it to the one digest once the write is done and
    published again. The first version wrote the file and then published its digest, so a
    SIGKILL between the two, or a checkout root the temp file could not be created in, left
    the OLD digest on record beside the new file: read as somebody else's file, its line left
    the block.
    """
    value = marker.get(rel)
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(v for v in value if isinstance(v, str))
    return ()


def _temps_left(dirs) -> bool | None:
    """Whether a file matching :data:`_TEMP_PATTERN` sits in any of *dirs* — ``None`` when one of
    them cannot be listed and none that could be holds one.

    A temp a kill left is charter's own write, and may be a copy of the plane's machine-local
    rules, so its line stays while one is there (review round 5, R1 and R2). A directory that is
    certainly not there holds none (ruling G(e)).
    """
    unsure = False
    for d in dirs:
        try:
            with os.scandir(d) as entries:
                if any(fnmatch.fnmatchcase(e.name, _TEMP_PATTERN) for e in entries):
                    return True
        except (FileNotFoundError, NotADirectoryError):
            continue
        except OSError:
            unsure = True
    return None if unsure else False


def harness_layer(name: str) -> list[tuple[str, str]]:
    """``(relative path, status)`` for every file the harness layer wants — READ ONLY.

    ``"ok"`` · ``"missing"`` · ``"stale"`` · ``"foreign"`` · ``"unreadable"`` ·
    ``"harness-edited"`` · ``"harness-behind"`` · ``"unwanted"`` — see :func:`_layer_status`.

    **Regenerate and compare**, which is `persona lint --only stale`'s test verbatim
    (`commands_persona._agent_sync_issues`) rather than a second notion of staleness. A
    stored diff would answer the wrong question: the generator's own output drifts — the
    plane's status line changes, a plugin is enabled — so what "current" means is whatever
    the generator says *today*, and the only way to know that is to run it.

    **Read only, because `doctor` calls this from the SessionStart hook.** A check that
    writes is not a check: it would report every workspace healthy by having just healed
    it, which is the "looks wired" shape this repo keeps paying for.

    ``foreign`` is the operator's file — content charter cannot vouch for against the
    marker. Charter never repairs it and never overwrites it, the restraint ADR 0015
    settles for an unstamped shim: charter cannot tell a file it wrote before the marker
    existed from one somebody rewrote, and guessing wrong in that direction destroys work.
    """
    with worktree_answers():
        if not _inside(config.WORKSPACES_DIR, workspace_dir(name)):
            # The workspace directory itself resolves outside the plane (a `workspaces/<ws>`
            # committed as a symlink out). Charter reads no layer through it and writes none —
            # doctor names the directory rather than reporting the tree behind the link.
            return [(GENERATED_MARKER, "foreign")]
        rows = _layer_status(workspace_dir(name), _layer_files(name), _read_marker(name))
        for tree in guest_trees(name):
            rows.extend((f"{checkout_label(name, tree)}/{rel}", status)
                        for rel, status in guest_layer(tree))
        rows.extend(_unlisted_rows(name))
    return rows


def _unlisted_rows(name: str) -> list[tuple[str, str]]:
    """One ``unlisted`` row per checkout of workspace *name* whose worktrees git could not list
    (:func:`unlisted`, #1072), for :func:`harness_layer` and :func:`wire_harnesses` alike.

    Labelled ``<checkout>/.git/worktrees``, where git keeps that list, as a checkout's exclude row
    is labelled ``.git/info/exclude``: a row of a checkout's own, so :func:`checkout_row` reads it
    back to that checkout for `doctor` and `reinit` to word what clears it."""
    return [(f"{checkout_label(name, tree)}/.git/worktrees", "unlisted") for tree in unlisted(name)]


def _layer_status(base: Path, want_all: dict[str, str],
                  marker: dict) -> list[tuple[str, str]]:
    """:func:`harness_layer`'s comparison, for one directory. READ ONLY.

    **Two statuses for a path the harness also writes into** (:func:`_cowritten`), because
    the marker's test answers wrong there. Content that matches neither what charter wants
    nor the digest it recorded is not "the operator's file" when the harness appends its own
    approvals to it — and calling it foreign is what dropped a clone's local settings out of
    its exclude block (#942). So: ``harness-edited`` while charter's last write is still what
    the plane wants — the harness only added to it, every rule charter mirrored is still in
    it, and nothing is wrong; ``harness-behind`` once the plane has moved on since (or when
    charter never wrote it) — charter will not merge into a file the harness keeps, so the
    plane's newer rules are not in it.

    ``unwanted`` for a file charter generated, still exactly as written, that nothing
    generates any more (:func:`_unwanted`). The next wire withdraws it; until then a withdrawn
    restriction is still prompting in that directory, and a row that said nothing would say
    the directory is current.
    """
    cowritten = _cowritten()
    rows: list[tuple[str, str]] = []
    for rel, want in sorted(want_all.items()):
        p = base / rel
        # `_exists`, never `Path.exists` (review round 3): that RAISED for an unreadable
        # `.claude/` on 3.11–3.13, crashing `workspace reinit`, and answered "missing" on 3.14.
        # A path that cannot be checked goes on to the read and is `unreadable` there.
        if _exists(p) is False:
            rows.append((rel, "missing"))
            continue
        if not _inside(base, p):
            # A committed link whose target, or whose parent, leaves the base. Charter
            # neither reads through it (the digest on the far end is not evidence the file
            # is charter's) nor writes through it — `foreign`, the state that is left exactly
            # as it is. `_materialise` will not rewrite it and `_write_whole` would refuse it.
            rows.append((rel, "foreign"))
            continue
        try:
            have = p.read_text()
        except (OSError, UnicodeDecodeError):
            rows.append((rel, "unreadable"))
            continue
        if have == want:
            rows.append((rel, "ok"))
        elif content_digest(have) in _recorded(marker, rel):
            # Only content a record LISTS is charter's to overwrite, pending or settled (review
            # round 5, R3). Round 4 also rewrote whatever a pending entry's path held — "half a
            # write" — and so wrote over an operator's hand edit made after a kill. Writes are
            # whole since R1, so there is no half write left to recognise.
            rows.append((rel, "stale"))
        elif rel in cowritten:
            # `harness-edited` only over a SETTLED record of exactly what the plane wants now
            # (R3). A pending entry lists what the file may hold while a write is under way, the
            # new text among it: read as current, an approval the harness saved over an
            # interrupted write settled a file that never received the plane's new `deny`.
            rows.append((rel, "harness-edited" if marker.get(rel) == content_digest(want)
                         else "harness-behind"))
        else:
            rows.append((rel, "foreign"))
    rows.extend((rel, "unwanted") for rel in _unwanted(base, want_all, marker))
    return rows


def _generated_roots(extra=()) -> set[str]:
    """The top-level directory segments charter may generate a file under — the boundary the
    DESTRUCTIVE side of the layer answers to, independent of any marker's digests.

    Charter's own layer always lives under a harness root (`.claude`, `.opencode`, `.codex`),
    so a marker key naming a path outside these — `README.md`, `keep.txt`, `.git/info/exclude`
    — names a file charter never wrote and must never withdraw, whatever digest a committed or
    planted marker records for it. Registry-driven from every harness's
    :attr:`harness.base.Harness.inherited_paths`, plus the root of any currently wanted rel
    (*extra*), so a harness added to the registry is covered the day it declares a surface and
    a plane that declares nothing still recognises `.claude` and its siblings.
    """
    from .harness import registry as _registry
    # `getattr`, like `_cowritten`: a stand-in harness that declares no `inherited_paths` must
    # mean none, not an `AttributeError` out of every withdraw. No `or ()` after it: the
    # attribute is a tuple on `Harness` and every harness, and `registry.inherited_paths()`
    # iterates it with no fallback, so a harness declaring `None` is one the layer already
    # cannot wire.
    roots = {p.split("/", 1)[0]
             for h in _registry.all() for p in getattr(h, "inherited_paths", ())}
    roots |= {rel.split("/", 1)[0] for rel in extra}
    return roots


def _unwanted(base: Path, want_all: dict[str, str], marker: dict) -> list[str]:
    """Files charter generated here, still exactly as written, that nothing generates now.

    READ ONLY — :func:`_withdraw` removes them and :func:`_layer_status` reports them, and
    both ask here so the two cannot disagree about which files those are.

    **Only a path under one of charter's generated roots** (:func:`_generated_roots`): a marker
    charter trusts can still name a file charter never wrote — a `git rm --cached` marker left
    in a source tree reads as untracked, a committed `.gitignore` can hide a planted one — and
    withdrawing on its word deletes the guest's own file. The withdraw only ever reaches
    charter's own generated tree, whatever the digests say.

    **Only while the file still matches the digest charter recorded**, :func:`unwire_guest`'s
    rule verbatim: a file the operator or the harness has since edited is not charter's to
    delete, and unreadable counts as not charter's for the same reason. **Never a held path**
    (:func:`_held_files`): a plane file charter cannot read is not a plane that stopped
    declaring something, and withdrawing over it took every workspace's `enabledPlugins`,
    `env` and `deny` away over a typo.
    """
    held = _held_files()
    roots = _generated_roots(want_all)
    out: list[str] = []
    # Sorted over the MARKER's own order, never over a set. A set iterates in hash order,
    # which for two short paths can happen to be path order, so no test could tell `sorted`
    # from its absence — CI's sweep charged exactly that. The marker's order is whatever
    # the file on disk says (an older charter or a hand edit can write any), and that is
    # the order `cmd_workspace_reinit`'s report must not inherit.
    for rel in sorted(r for r in marker if r not in want_all and r not in held):
        if rel.split("/", 1)[0] not in roots:
            continue
        try:
            if content_digest((base / rel).read_text()) in _recorded(marker, rel):
                out.append(rel)
        except (OSError, UnicodeDecodeError):
            continue
    return out


def wire_harnesses(name: str) -> list[tuple[str, str]]:
    """Materialise the harness layer into workspace *name*. ``(relative path, status)``.

    ``"created"`` · ``"refreshed"`` · ``"present"`` · ``"removed"`` · ``"foreign"`` ·
    ``"blocked"`` · ``"withheld"`` · ``"harness-behind"`` · ``"unreadable"`` (a generated
    path charter cannot read, never folded into ``"foreign"``).

    **Refresh, not create-once.** `ensure_shim`'s restraint was right about the operator's
    files and wrong about charter's own: a plugin generated by 0.40.0 survived every
    upgrade afterwards while `doctor` reported the tree wired (ADR 0015). A file whose
    digest is in the marker is charter's, and charter brings its own files up to date.
    A file whose digest is not is the operator's, and is left exactly as found.

    Called from :func:`scaffold`, so a launch gets it: `commands_frame._launch_root` runs
    `ensure` before the chat's cwd is read. `charter workspace reinit` is the repair.

    Every guest checkout in the workspace is wired too, its rows prefixed with the
    checkout's directory name — see :func:`wire_guest`. Doing it here rather than at a
    second call site is what makes `reinit` the repair for a clone as well: a clone made
    by an older charter, or one whose `info/exclude` somebody emptied, is brought back by
    the command that already exists.
    """
    with worktree_answers():
        if not _inside(config.WORKSPACES_DIR, workspace_dir(name)):
            # A `workspaces/<ws>` that resolves out of the plane (committed as a symlink):
            # writing the layer through it would land the whole thing outside. Refused as one
            # decision, reported `blocked`, and no guest tree behind the link is descended.
            return [(GENERATED_MARKER, "blocked")]
        rows = _materialise(workspace_dir(name), _layer_files(name))
        for tree in guest_trees(name):
            rows.extend((f"{checkout_label(name, tree)}/{rel}", status)
                        for rel, status in wire_guest(tree))
        rows.extend(_unlisted_rows(name))
    return rows


def _withdraw(base: Path, want_all: dict[str, str], marker: dict) -> list[tuple[str, str]]:
    """Remove what charter generated here and no longer generates. ``(rel, "removed")``.

    A generated file only ever ARRIVED until #942, because the one thing charter mirrored
    stopped being wanted only when the plane's whole settings file did. Now the layer
    carries the plane's `ask` and `deny` rules, and a plane that drops its last `--local`
    rule stops wanting a whole generated file — so without this, a restriction could be put
    in force in every workspace and never lifted from any of them. `charter guard` has no
    remove verb; hand-editing the plane's settings is how a rule goes, and a mirror that is
    one-way turns that edit into a lie.

    **Which files** is :func:`_unwanted`'s answer, asked rather than re-derived: content still
    matching the recorded digest, and never a held path. The first version carried its own
    copy of that test and withdrew every workspace's settings over an unparseable plane
    file, which is how two readers of one question come to disagree.
    """
    rows: list[tuple[str, str]] = []
    for rel in _unwanted(base, want_all, marker):
        p = base / rel
        if not _inside(base, p):
            # A marker charter did not write can name a path outside the tree — an absolute
            # key, one that climbs out with `..`, or one a committed link redirects. Charter
            # withdraws only what is inside the checkout it wires; the entry is left on the
            # marker (`_read_marker_at` already treats such a marker as untrusted) and never
            # unlinks a file out there.
            continue
        try:
            p.unlink()
        except OSError:
            # Gone since it was read, or held by a directory that will not let go. It stays
            # in the marker and stays reported `unwanted`, and the next wire tries again —
            # this one runs on a launch path and must not raise out of it.
            continue
        del marker[rel]
        # A `.claude/` left standing with nothing of charter's in it is charter still
        # visible in a directory it has nothing in — `unwire_guest`'s reason, and it
        # matters more in a guest checkout, where that directory is somebody else's repo.
        _prune_empty(p.parent, base)
        rows.append((rel, "removed"))
    # An entry whose file is already gone vouches for nothing, and is forgotten (#942, review
    # round 2). Left in place, a co-written path stayed on the list `_charter_owned` hands the
    # block for ever, hiding nothing and naming a path charter no longer has. A path still
    # wanted is written again below and recorded afresh, so forgetting it first changes nothing
    # there.
    #
    # Gone means PROVED gone (ruling G(e), review round 3). `os.path.lexists` answered False
    # for a refused lstat too, and one EACCES during a launch forgot `settings.json` for good.
    for rel in [r for r in marker if _exists(base / r) is False]:
        del marker[rel]
    return rows


def _materialise(base: Path, want_all: dict[str, str],
                 withhold: frozenset[str] = frozenset(),
                 record_first: bool = False) -> list[tuple[str, str]]:
    """:func:`wire_harnesses`' write loop, for one directory — see it for the contract.

    *withhold* names wanted paths that must not be written this time. :func:`wire_guest`
    passes a checkout's co-written local file when its exclude could not be written: a
    machine-local rule charter cannot hide is one `git add -A` from somebody else's
    repository. Reported ``withheld`` and never ``blocked`` — nothing is in the way at that
    path, and `blocked`'s wording would send the operator looking for an obstruction.

    *record_first* is :func:`wire_guest`'s (ruling H, review round 4): in a guest checkout a
    write whose record cannot be published is NOT made, because the next launch would read the
    old record beside the new file and drop its exclude line. A workspace directory has no
    exclude block, so there a record that cannot be published costs only the record, and the
    layer still lands (`test_a_directory_where_the_marker_goes_does_not_cost_the_layer`).
    """
    marker = _read_marker_at(base)
    before = dict(marker)
    rows = _withdraw(base, want_all, marker)
    writes: list[tuple[str, str]] = []
    published = before
    for rel, status in _layer_status(base, want_all, marker):
        if status == "unreadable":
            # Not `foreign` (#942, review rounds 2 and 3), for any generated path: one state,
            # one name — doctor already called it `unreadable` — and every `foreign` sentence
            # advises removing a file charter only failed to read, which may hold the harness's
            # approvals. Charter says exactly that and leaves the file as it is.
            rows.append((rel, "unreadable"))
            continue
        if status == "foreign":
            # The operator's file, and the marker entry for it stays exactly as it was:
            # charter has not written this path, so it has nothing new to vouch for.
            rows.append((rel, "foreign"))
            continue
        if status in ("ok", "harness-edited"):
            # `harness-edited` is current: every rule charter mirrored is still in the file,
            # and writing charter's text over it would throw away the approvals the harness
            # saved there. A record that does not say what an `ok` file holds is settled on it:
            # pending over a write that finished, or settled by a launch that lost a race to
            # another, whose record then named text the file no longer held — and the plane's
            # next move would have called charter's own file foreign (review round 5). Only an
            # `ok` file's: a `harness-edited` record says exactly this already (R3).
            if rel in marker:
                # A record that already holds this digest is left equal to what was published,
                # so nothing is published for it.
                marker[rel] = content_digest(want_all[rel])
            rows.append((rel, "present"))
            continue
        if status == "harness-behind":
            # Never rewritten and never merged into: the harness keeps that file now.
            rows.append((rel, status))
            continue
        if status == "unwanted":
            # `_withdraw`'s, and already tried above; there is nothing here to write.
            continue
        if rel in withhold:
            rows.append((rel, "withheld"))
            continue
        writes.append((rel, status))
    if writes:
        # **Intent first** (ruling H, review round 4). Every file about to be written is
        # published as PENDING — the digests it may hold while the write is under way — before a
        # byte of it changes, so no kill between the write and its record can leave a file on
        # disk that the record calls somebody else's. Where that publish fails — a checkout root
        # the temp file cannot be created in, a full or read-only disk — nothing is written: a
        # file charter cannot record is a file whose line the next launch would drop.
        intent = dict(marker)
        for rel, _status in writes:
            intent[rel] = list(set(_recorded(marker, rel)) | {content_digest(want_all[rel])})
        refused = _publish_marker(base, intent)
        if refused is not None and record_first:
            _note_unrecorded(base, refused)
            rows.extend((rel, "unrecorded") for rel, _status in writes)
            return rows
        marker = intent
        # What the settle below is compared with (#942 final review): the record this launch
        # published, never the one it read. Compared with the record read at the start, a launch
        # that wrote a deleted file again ended on that very record and skipped the settle, so
        # the pending entry it had just published stayed pending for good — and a pending entry
        # never reads `harness-edited`. In a workspace directory this publish may have failed;
        # the settle then tries again unless every write was blocked, when nothing it wrote needs
        # recording.
        published = dict(intent)
    for rel, status in writes:
        want = want_all[rel]
        try:
            _write_whole(base / rel, want, base)
        except OSError:
            # The entry stays pending and the file holds what it held — whole writes (review
            # round 5, R1) — and the next wire writes it again.
            rows.append((rel, "blocked"))
            continue
        marker[rel] = content_digest(want)
        rows.append((rel, "created" if status == "missing" else "refreshed"))
    if marker == published:
        # Only when something changed. Rewriting the marker on every `ensure` would make a
        # workspace's mtimes move for a call that changed nothing, which is the noise
        # `_ensure_guard_hook` avoids one file over.
        return rows
    refused = _publish_marker(base, marker)
    if record_first:
        # Every entry on disk is still the intent or the record before it, and each of those
        # accounts for what is there now — so the lines stay, and the row says why, with the
        # errno this publish failed with (review round 5, R5). The first that succeeds forgets it.
        _note_unrecorded(base, refused)
        if refused is not None:
            rows.append((GENERATED_MARKER, "unrecorded"))
    return rows


def _inside(base, p) -> bool:
    """True when *p* **and its parent** both RESOLVE inside *base* — the one containment test
    every write, replace, unlink and directory prune charter performs in a checkout or a
    workspace passes through.

    Both are resolved, because a committed tree charter is a guest in decides what its own
    symlinks point at: a `.charter-generated` that is a link, a `.claude/` that is a directory
    link with `settings.json` an ordinary name beneath it, a marker key spelled `../../victim`.
    Resolving *p* alone would still follow a link whose PARENT leaves the base; resolving the
    parent alone would follow a leaf link. :func:`contain.file_refusal` draws the same pair one
    module over, for the read side of the same class (#336, #349).

    Never raises: a path the filesystem cannot resolve is not inside. ``realpath`` resolves a
    tail that is not there lexically, so a link a file is about to be created through is judged
    by where it points, not by whether the file exists yet. `base` itself counts as inside.
    """
    try:
        root = os.path.realpath(base)
        for q in (os.path.realpath(p), os.path.realpath(os.path.dirname(os.fspath(p)) or ".")):
            if q != root and not q.startswith(root + os.sep):
                return False
    except (OSError, ValueError):
        return False
    return True


def _write_whole(path: Path, text: str, base: Path | None = None) -> None:
    """Replace the file at *path* with *text* whole — a temp beside it, fsynced, then one
    ``os.replace`` — or raise and leave it exactly as it was.

    **Every file charter writes in a checkout or its common git directory goes through here**
    (#942 review round 5, R1): the generated files (:func:`_materialise`), the marker
    (:func:`_publish_marker`) and `info/exclude` (:func:`_register_excludes`). Written in place,
    a kill mid-write left a checkout's `settings.local.json` at 68 or 0 bytes, which read as the
    harness's edit — the plane's new `deny` never arrived there, and `doctor` said all current —
    and an `info/exclude` killed after its truncate lost the operator's own lines.

    **The write stays inside *base* or is refused.** *base* is the checkout or workspace this
    write belongs to; a *path* whose resolved target, or whose resolved parent, leaves it
    (:func:`_inside`) is refused with `OSError`, which every caller already renders as
    ``blocked``. Charter is a guest in the tree it wires, and a committed `.charter-generated`
    that is a symlink, or a committed `.claude/` that is a directory link, would otherwise send
    this write wherever the link points — creating a file (and its parents) out there, or
    replacing the file that is there with charter's own. *base* is ``None`` only for
    `info/exclude`, which git's `commondir` puts outside a linked worktree by design and which
    no committed working-tree content can redirect; there a link contained inside the git
    directory is still followed, as `Path.write_text` wrote, and never replaced by a copy.

    The temp is `.charter-generated.<pid>.<rand>.tmp`: beside the target, so the rename is a
    rename; private to this writer, for `config.temp_beside`'s reason (#893); and, in a checkout,
    matching :data:`_TEMP_PATTERN`, which :func:`wire_guest`'s first pass puts in charter's block
    before the first one exists, so a temp a kill leaves stays hidden. `info/exclude`'s own temp is
    written inside the git directory, which no working tree lists, and needs no line.

    Fsynced before the rename: without it a crash just after the rename can publish a file whose
    content never reached the disk. The mode of the file replaced is kept, since `os.replace`
    carries the temp's. The temp is removed when the rename does not happen.
    """
    if base is not None and not _inside(base, path):
        # Refused, not followed: a path that leaves the tree charter may write in is the
        # exploit this guard exists for, and a raise here is `blocked` at every call site.
        raise OSError(errno.EACCES,
                      "refusing to write through a path that leaves the checkout", str(path))
    target = Path(os.path.realpath(path)) if os.path.islink(path) else Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{GENERATED_MARKER}.{os.getpid()}.{os.urandom(6).hex()}"
                           f"{config.TEMP_SUFFIX}")
    try:
        with open(tmp, "x", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(tmp, stat.S_IMODE(os.stat(target).st_mode))
        except FileNotFoundError:
            pass
        os.replace(tmp, target)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _publish_marker(base: Path, marker: dict) -> OSError | None:
    """Publish *marker* at *base* whole, or remove it when it names nothing — the `OSError` when
    the filesystem refused, which the caller must treat as no record published (ruling H) and
    whose errno `unrecorded` names (review round 5, R5); ``None`` when it was published.

    Whole (:func:`_write_whole`; #942, review rounds 2 and 5): truncated in place, a launch
    reading this marker while another wire wrote it could read a prefix or nothing. An empty
    marker is charter still standing in the directory — in a checkout, a file no block names any
    more.
    """
    path = base / GENERATED_MARKER
    try:
        if marker:
            _write_whole(path, json.dumps(marker, indent=2) + "\n", base)
        else:
            # `unlink` never follows a symlink, so a hostile marker LINK is removed at the
            # link node, never through it — no containment needed on this branch.
            path.unlink(missing_ok=True)
    except OSError as e:
        return e
    return None


def _unrecorded_note(tree: Path) -> Path:
    """Where the reason *tree*'s record could not be published is kept: charter's own state
    directory, because the checkout is the place that refused a write."""
    key = hashlib.sha256(os.path.realpath(tree).encode("utf-8")).hexdigest()[:32]
    return config.STATE_DIR / "unrecorded" / f"{key}.json"


def _note_unrecorded(tree: Path, refused: OSError | None) -> None:
    """Keep the errno a publish into guest checkout *tree* failed with, or forget it once one
    succeeded.

    Review round 5, R5: `unrecorded` took its reason from `os.access`, which passes a read-only
    filesystem, a full disk and a quota alike — each a publish that fails in a directory whose
    mode bits allow it. Best effort: a note that cannot be kept costs the reason, never the launch.
    """
    note = _unrecorded_note(tree)
    try:
        if refused is None:
            note.unlink(missing_ok=True)
            return
        config.mkdir_for(note.parent)
        config.replace_for(note, json.dumps({
            "errno": errno.errorcode.get(refused.errno, refused.errno),
            "says": refused.strerror or str(refused)}) + "\n")
    except OSError:
        pass


def unrecorded_reason(tree: Path) -> str:
    """Why charter could not publish guest checkout *tree*'s record — ``"EACCES: Permission
    denied"`` — or ``""`` when no failed publish is on record. READ ONLY."""
    try:
        doc = json.loads(_unrecorded_note(tree).read_text())
        return f"{doc['errno']}: {doc['says']}"
    except (OSError, ValueError, KeyError, TypeError):
        return ""


#: What clears a record publish that failed, by the errno it failed with (#942 final review).
#: "Restore write access" was the advice for every one of them, and a full disk or a read-only
#: mount has no write access to restore. An errno not named here gets no guessed cause.
_UNRECORDED_FIXES = {
    "EACCES": "restore write access to {where}",
    "ENOSPC": "free space on the disk that holds {where}",
    "EROFS": "remount the read-only filesystem that holds {where} read-write",
}


def unrecorded_fix(tree: Path, where: str) -> str:
    """What clears guest checkout *tree*'s failed record publish, worded for *where* and ending
    with its errno — ``""`` when no failed publish is on record. READ ONLY.

    One wording for the chat, `doctor`, `reinit` and `guard ask`, so no two of them can hand a
    reader different remedies for one refusal."""
    reason = unrecorded_reason(tree)
    if not reason:
        return ""
    # By prefix, never by splitting the reason: its first ":" always follows the errno's name, so
    # `partition` and `rpartition` agreed on every reason an OS writes, and no test could tell the
    # two apart (the round-5 deletion sweep).
    fix = next((fix for name, fix in _UNRECORDED_FIXES.items() if reason.startswith(f"{name}:")),
               "fix what stops writes to {where}")
    return f"{fix.format(where=where)} ({reason})"


def uncheckable_fix(code: int | None, path, where: str = "it") -> str:
    """What clears a path charter could NOT check, worded for the errno the check met.

    `ELOOP` names the link, because no permission bit is in the way of a loop and restoring read
    access clears none — the one sentence sent operators to the wrong repair (#942 closing
    verification). Anything else is read as a refusal: charter does not guess a third cause from
    an errno it has not measured, and read access is what clears the refusals it has seen.

    One decision for `doctor` and `reinit`, so the two cannot hand a reader different remedies
    for one unreadable path. *where* is only how the access half points back at the path the
    caller has already named — a row that just printed it says "it", a sentence further from it
    says "that path"."""
    return (f"fix the symlink loop at {path}" if code == errno.ELOOP
            else f"restoring read access to {where} clears this")


def cannot_check_workspace(name: str, code: int | None) -> str:
    """The one sentence for a workspace a command could not look at, worded for the errno.

    `reinit`'s since #1028, for the named form and `--all`; since #1043 also every command that
    shows the operator the plane's workspaces (:func:`read_workspaces_aloud`), so no two of them
    send a reader to different repairs for one directory."""
    wd = workspace_dir(name)
    return (f"workspace '{name}' cannot be checked — charter changes nothing it cannot see; "
            f"{uncheckable_fix(code, wd, wd)}.")


def cannot_check(path: Path, code: int | None) -> str:
    """`doctor`'s clause for a path it could not check — ``<path> cannot be checked — <what
    clears it>`` — with no full stop, so a row can join several.

    The one wording for a directory charter could not look at (#1043): `doctor` joins these
    beside a verdict, and since #1084 a command that searched or listed around one prints it as a
    sentence (:class:`CannotCheck`). *path* is named from the plane's root when it is inside it."""
    try:
        named = Path(path).relative_to(config.ROOT).as_posix()
    except ValueError:
        named = str(path)
    return f"{named} cannot be checked — {uncheckable_fix(code, path)}"


def say_unread(unread) -> None:
    """Print :func:`cannot_check`'s sentence on stderr for each ``(path, errno)`` in *unread* — for
    a command that searched or listed around what it could not read (#1084)."""
    for path, code in unread:
        util.err(f"{cannot_check(path, code)}.")


class CannotCheck(OSError):
    """A reader that has no partial answer to give met a directory it could not look at (#1084).

    Raised where "nothing there" was the answer before — `memstore.files` of a `memory/` it may
    not list, `change.all_for` of such a `changes/` — so no caller can take "could not look" for
    "found nothing" without deciding to. An `OSError`, so a caller that already degrades on one
    still does. Its text is :func:`cannot_check`'s sentence, one per path, which is what the CLI
    prints for a command that lets it through. *unread* is ``(path, errno)`` pairs."""

    def __init__(self, unread: list[tuple[Path, int | None]]):
        path, code = unread[0]
        super().__init__(code, " ".join(f"{cannot_check(p, c)}." for p, c in unread), str(path))
        self.unread = list(unread)

    def __str__(self) -> str:
        return self.strerror


# --------------------------------------------------------------------------- #
# guest checkouts — the layer one directory deeper, hidden in the checkout's     #
# own `info/exclude` (#870). See this section's header comment for the boundary. #
# --------------------------------------------------------------------------- #

#: The delimiters of charter's managed block in a guest checkout's `info/exclude`.
#:
#: Delimited rather than "charter's lines are the ones charter recognises", which is the
#: `_LIVE_BEGIN`/`_LIVE_END` precedent two hundred lines up and the same reason: an
#: operator's own `.claude/settings.json` line, written before charter ever arrived, is
#: indistinguishable from charter's by content alone — and removal would take it with it.
#: The block is what makes the write idempotent AND the removal exact.
_EXCLUDE_BEGIN = "# >>> charter (generated layer — `charter workspace reinit`) >>>"
_EXCLUDE_END = "# <<< charter <<<"

#: The line inside the block, for the person who finds it in a repo they own.
_EXCLUDE_NOTE = ("# Files charter generated in this checkout so a chat here gets the "
                 "plane's layer.\n"
                 "# Listed one by one — charter hides only what it wrote, never a "
                 "directory of yours.\n"
                 "# This file is per-checkout and never committed; nothing your "
                 "teammates clone is affected.")


def guest_trees(name: str) -> list[Path]:
    """Every checkout inside workspace *name* that charter is a GUEST in.

    Clones AND linked worktrees, which is why this is not :func:`clones`. That function
    answers "which repos am I working in", and git's clone/worktree distinction is load
    bearing for it — a worktree must never be counted as a second repo. This one asks
    "where would a chat's cwd be cut off from the plane's layer", and the answer is *any*
    checkout: a worktree's root is a git boundary exactly as a clone's is.
    """
    children = _children(name)
    return children + _pieces(name, children)[0]


def _children(name: str) -> list[Path]:
    """The checkouts directly inside workspace *name* — :func:`guest_trees` without the pieces."""
    try:
        entries = sorted(workspace_dir(name).iterdir())
    except OSError:
        return []
    # No `is_dir()` filter: `git_dir` already answers `None` for a plain file — its
    # `.git` join raises `NotADirectoryError` — so a predicate here would be one more
    # spelling of the same question, and the deletion sweep would be right to take it.
    return [d for d in entries if git_dir(d) is not None]


def unlisted(name: str) -> list[Path]:
    """The checkouts inside workspace *name* whose repository's worktrees git could not list —
    one per repository — so none of those worktrees got charter's layer, a repair or a row (#1072).

    :func:`guest_trees` passes over a listing git cannot give, and that is right for what it
    answers: nothing can be wired where nothing is listed. But passed over in silence, a piece
    `charter wt add` cut kept no plugin and none of the plane's ask/deny rules while `doctor` was
    green and `reinit` said nothing to do — #951's failure, one unreadable directory later. So
    `doctor`, `reinit` and `charter clone` name each of these, with :func:`unlisted_fix`.
    """
    return _pieces(name, _children(name))[1]


def unlisted_fix(tree: Path) -> str:
    """What clears :func:`unlisted`'s *tree*: :func:`uncheckable_fix`'s remedy for the directory
    git keeps its worktrees in, worded for the errno reading it meets now — `gitpolicy.scan`'s
    remedy for a clone it cannot read (#1012), so the commands cannot differ about one path."""
    admin = git_exclude_file(tree).parent.parent / "worktrees"
    # No errno when it reads now and git still gave no list — a git that failed, timed out or could
    # not be run — and `uncheckable_fix` reads that as a refusal, as it reads any errno it has not
    # measured.
    code = None
    try:
        os.scandir(admin).close()
    except OSError as e:
        code = e.errno
    return uncheckable_fix(code, admin, str(admin))


def _pieces(name: str, checkouts: list[Path]) -> tuple[list[Path], list[Path]]:
    """``(pieces, unlisted)``. Every piece's worktree of workspace *name*: a worktree of one of
    *checkouts*' repositories that git lists at ``<root>/<repo>/<piece>``, spelled under the root
    it was found in — and one of *checkouts* per repository whose list git could not give
    (:func:`unlisted`).

    **The half of :func:`guest_trees` its docstring promised and its scan never had (#951).** A
    piece sits two levels below its workspace, at `.worktrees/<repo>/<piece>`, and `.worktrees`
    holds no `.git` of its own; under `[plane] worktrees` or `$CHARTER_WORKTREES` it is outside the
    workspace altogether. So every piece `charter wt add` cut — the directory it tells the worker
    to start a session in — got no layer from a launch, `reinit` or `clone`, and no `doctor` row.

    **Asked of git, the only registry** (`worktree.py`, ADR 0011): a worktree made by hand at the
    layout's path counts, and one removed by hand does not. Not a walk of the root, which would
    take a directory somebody copied for a live worktree. Through :func:`_worktree_list`, so a
    launch or a `doctor` run asks each repository once however many readers want the answer, and
    not at all where the common directory has no `worktrees/` — :func:`_live_trees`' rule, and the
    same ~7 ms a spawn on every launch of a workspace with no pieces.

    A listing git cannot give, and an entry git calls prunable, bare or gone, is passed over —
    nothing is wired there, and the clone's own rows still say what they say. The listing is
    NAMED, though (#1072): a worktree nobody can see is not a worktree that is fine.
    """
    from . import worktree as _worktree

    found: dict[str, Path] = {}
    unlisted_at: dict[str, Path] = {}
    for tree in checkouts:
        # Never `None`: every one of *checkouts* has a git directory, which is all the exclude's
        # answer needs — a test for it here decided nothing (the hand deletion sweep said so).
        common = git_exclude_file(tree).parent.parent
        refused = False
        try:
            os.scandir(common / "worktrees").close()
        except (FileNotFoundError, NotADirectoryError):
            continue
        except OSError:
            # Still asked of git, which may read what charter cannot. But measured on git 2.50.1,
            # a git that cannot read `worktrees/` lists the clone alone and exits 0, so its answer
            # is no evidence the list is whole.
            refused = True
        listed = _worktree_list(tree, common)
        # Exit code too: a git that fails prints its `fatal:` to stderr and nothing to parse, which
        # read as a repository with no pieces. Once per repository, under the first checkout of it:
        # a clone and a worktree of it at the workspace's top level share the one list.
        if refused or isinstance(listed, Exception) or listed.returncode != 0:
            unlisted_at.setdefault(os.path.realpath(common), tree)
        if isinstance(listed, Exception):
            continue
        for entry in _worktree.parse_porcelain(listed.stdout):
            # Under THIS workspace's roots only: another workspace's piece of the same repository is
            # that workspace's to wire and to take away, and `workspace remove` of this one must not
            # strip it.
            at = _piece_at(name, entry["path"])
            # No `prunable` or `bare` test: a worktree git calls prunable has no `.git` that points
            # anywhere, and a bare repository's entry is a git directory with none, so `git_dir`
            # answers both.
            if at is None or git_dir(at[0]) is None:
                continue
            # Keyed by where it is, because two checkouts of one repository — a clone and a
            # worktree of it at the workspace's top level — list the same pieces.
            found[os.path.realpath(at[0])] = at[0]
    # Unlisted in *checkouts*' order, and no `sorted`: `guest_trees` hands them over sorted, and a
    # dict keeps the order its first keys arrived in, so a sort here decided nothing (CI's sweep).
    return sorted(found.values()), list(unlisted_at.values())


def _piece_at(name: str, path) -> tuple[Path, tuple[str, ...]] | None:
    """``(worktree, the parts below it)`` when *path* is one of workspace *name*'s pieces or lies
    inside one — ``None`` otherwise. Path arithmetic only; whether a checkout is there is the
    caller's question.

    The worktree comes back spelled under the ROOT it matched, never as *path* spells it. Git
    records a worktree by its resolved path (measured, git 2.50.1: a piece cut through a linked
    `.worktrees` is listed where the link points), while charter spells a plane as `config.use`
    was handed it — so each root is tried as spelled and then resolved, and the answer is always
    the root's own spelling. That spelling is what :func:`_wired_tree_ok` judges: a piece whose
    root resolves out of its base is found here, and named rather than wired there.

    Per workspace, because only a workspace's own root can be resolved: a `.worktrees` linked out
    of the plane puts the piece's resolved path under no base a plane-wide parse could start from.
    The layout is `worktree.py`'s — ``<root>/<ws>/<repo>/<piece>`` relocated, and
    ``workspaces/<ws>/.worktrees/<repo>/<piece>`` in the plane — and both roots are tried, for
    `worktree.locate`'s reason: a plane that has just declared a relocated root still has
    yesterday's pieces under `.worktrees/`.
    """
    from . import worktree as _worktree

    roots = [workspace_dir(name) / _worktree.DIR_NAME]
    if config.WORKTREES_ROOT is not None:
        roots.insert(0, config.WORKTREES_ROOT / name)
    for root in roots:
        for here, there in ((os.path.normpath(path), os.path.normpath(root)),
                            (os.path.realpath(path), os.path.realpath(root))):
            # `relative_to`, never a string prefix: `.worktrees-old/…` begins with `.worktrees`, and
            # so does another workspace's `<root>/api-old/…` with `<root>/api`.
            try:
                parts = Path(here).relative_to(there).parts
            except ValueError:
                continue
            if len(parts) >= 2:
                return root / parts[0] / parts[1], parts[2:]
    return None


def checkout_label(name: str, tree: Path) -> str:
    """How a row of workspace *name* names its guest checkout *tree*: the path from the workspace
    directory when *tree* is inside it — `svc`, `.worktrees/svc/p1` — and the absolute path of a
    piece under a relocated root, which no path from the workspace spells readably.

    `tree.name` was the label while every guest was a direct child. A piece's name is its own
    directory's alone, so two repositories' `p1` would read as one checkout, and a piece named
    like a clone as that clone. Callers join it with `os.path.join(workspace, label)`, which keeps
    an absolute label as it is. :func:`checkout_row` reads a row back to its checkout.
    """
    inside = os.path.normpath(workspace_dir(name))
    spelled = os.path.normpath(tree)
    if spelled.startswith(inside + os.sep):
        return spelled[len(inside) + 1:]
    return spelled


def _wired_tree_ok(tree: Path) -> bool:
    """Whether *tree* is a guest checkout charter may wire — one that itself resolves inside
    the directory it belongs under: this plane's ``workspaces/``, or the relocated worktree root
    for a piece spelled under that root.

    :func:`guest_trees` lists the children of a workspace directory and follows a symlink, so
    a `workspaces/<ws>/<name>` linked at a repository OUTSIDE the plane is a tree whose own
    root has already escaped. The per-file :func:`_inside` guard inside :func:`_write_whole`
    is relative to *that* root and would pass, so containment has to be asked of the tree
    ROOT as well: charter wires, unwires and reports only a tree genuinely under
    its base. A tree that is not is NAMED by its caller (a wire and a doctor row) and
    never written to.

    **A piece under `$CHARTER_WORKTREES` or `[plane] worktrees` answers to that root (#951)**, which
    is outside `workspaces/` by design. The root and not `<root>/<ws>`, for the reason the plane's
    base is `workspaces/` and not `workspaces/<ws>/.worktrees`: it is the one directory somebody
    vouched for — the person at the machine for the variable, :func:`contain.plane_adjacent` for
    the committed setting, and `config.worktrees_root_for` resolved it — while everything below it
    is directories charter or git made and a link anyone can plant. So a `<root>/<ws>` linked out of
    the root is named, not wired.

    Chosen by how *tree* is SPELLED, and only for a tree spelled outside `workspaces/` — which,
    from every caller, is a piece spelled under the root (:func:`_piece_at`, `worktree.path_for`).
    A root that contains the plane — `$CHARTER_WORKTREES` takes anything, `/` included — must not
    become the base a workspace's own child answers to: a `workspaces/<ws>/<name>` linked out of the
    plane would resolve inside `/` and be wired.
    """
    base = config.WORKSPACES_DIR
    if (config.WORKTREES_ROOT is not None
            and not os.path.normpath(tree).startswith(os.path.normpath(base) + os.sep)):
        base = config.WORKTREES_ROOT
    return _inside(base, tree)


def _charter_owned(base: Path, marker: dict) -> list[str]:
    """The paths under *base* charter generated and STILL recognises, marker included — what
    *base* needs charter's block to list, so a line missing from it is ADDED.

    What goes in the exclude block, and the reason it is a list of files rather than a
    `.claude/` glob: a guest repo may have its own `.claude/`, and hiding a directory
    would hide the operator's files inside it from their own `git status` — charter
    silently making somebody's untracked work invisible in their own repo is a worse
    failure than the untracked noise this exists to prevent.

    A path whose content no record lists is left out, so charter never adds a line for a file
    somebody else wrote. Leaving it out takes no line away, since review round 5 (R2): a line for
    a path that is there stays (:func:`_shared_rels`), so a file charter wrote and somebody then
    rewrote stays hidden, is never overwritten, and `harness_layer` calls it ``foreign``. Empty
    when charter has generated nothing here, so a checkout with an all-foreign layer gets no block
    at all.

    **Except a path the harness also writes into** (:func:`_cowritten`), listed for as long as the
    marker names it, whatever its digest (#942): the harness saving an approval moves the digest
    without making the file anybody else's, and Claude Code adds its own global exclude only where
    the file is not already ignored.
    """
    if not marker:
        return []
    cowritten = _cowritten()
    out: list[str] = []
    for rel in sorted(marker):
        if rel not in cowritten:
            try:
                if content_digest((base / rel).read_text()) not in _recorded(marker, rel):
                    continue
            except (OSError, UnicodeDecodeError):
                # Gone, refused or not text: none of those proves the file is somebody else's
                # now (ruling G, review round 3), and a path listed here adds a line at most.
                pass
        out.append(rel)
    return out + [GENERATED_MARKER]


#: Every temp file :func:`_write_whole` writes through, as a pattern: `.charter-generated.<pid>.
#: <rand>.tmp`, which a process killed between a write and its rename leaves behind. The one glob in
#: charter's block, over a name that is charter's own — and since review round 5 (R1) the one line
#: written without a leading `/`, because a temp is written beside every file charter writes, in
#: `.claude/` and `.claude/agents/` as well as at the checkout root. An operator's own file whose
#: name matches it, `.charter-generated.notes.tmp`, is hidden too (docs/workspaces.md says so).
_TEMP_PATTERN = f"{GENERATED_MARKER}.*{config.TEMP_SUFFIX}"


def _exclude_block(rels: list[str]) -> str:
    """The block listing *rels*, in the order given — :func:`_shared_rels` decides both, the
    temp-file pattern among them, which is written unanchored."""
    if not rels:
        return ""
    return "\n".join([_EXCLUDE_BEGIN, _EXCLUDE_NOTE,
                      *(r if r == _TEMP_PATTERN else f"/{r}" for r in rels),
                      _EXCLUDE_END]) + "\n"


def _block_rels(text: str) -> set[str]:
    """What charter's block in *text* lists now — its temp-file pattern among them, in either
    spelling: anchored, as review rounds 3 and 4 wrote it, reads as the same entry, and the block
    holding it is rewritten unanchored (review round 5, R1)."""
    lines = text.splitlines()
    span = _block_span(lines)
    return ({line.removeprefix("/") for line in lines[span[0] + 1:span[1] + 1]
             if line.startswith("/") or line == _TEMP_PATTERN} if span else set())


def _replace_block(text: str, block: str) -> str:
    """*text* with charter's block replaced by *block* (empty *block* removes it).

    The whole of the idempotence requirement. Appending would duplicate every line on the
    second `ensure`, and an `ensure` runs on every launch — `git status` in the operator's
    repo would stay clean while their `info/exclude` grew without bound.

    An UNTERMINATED block (begin marker, no end) is treated as running to end of file
    and replaced whole. The alternative is to append a second block below it, which is
    the duplication this function exists to prevent, wearing a crash for a hat.
    """
    lines = text.splitlines()
    new = block.splitlines()
    span = _block_span(lines)
    if span is None:
        # Nothing of charter's here and nothing to add: the file is handed back BYTE FOR
        # BYTE rather than re-joined. Re-joining normalises a missing trailing newline,
        # which would make `unwire_guest` rewrite the `info/exclude` of a checkout charter
        # never wired — a write into somebody's repo for no reason at all.
        if not new:
            return text
        out = lines + new
    else:
        out = lines[:span[0]] + new + lines[span[1] + 1:]
    return "\n".join(out) + "\n" if out else ""


def _block_span(lines: list[str]) -> tuple[int, int] | None:
    """``(begin, end)`` — the indexes of charter's first and last block line — or ``None``.

    An unterminated block runs to the end of the file, :func:`_replace_block`'s rule. One
    function for both readers of it, the rewrite and :func:`_shared_rels`' reading of what
    the block holds now, because two spellings of where the block ends are two answers to
    which lines are charter's.
    """
    try:
        i = lines.index(_EXCLUDE_BEGIN)
    except ValueError:
        return None
    return i, next((k for k in range(i + 1, len(lines)) if lines[k] == _EXCLUDE_END),
                   len(lines) - 1)


#: How long `git worktree list` may take: `doctor.CHECK_TIMEOUT`'s value, and
#: `test_git_is_given_doctors_check_timeout` pins the two together. The block is read by doctor's
#: SessionStart check as well as written on every launch, and a 2 s hang cost both 5 s with no
#: timeout at all (review round 3). Not imported from `doctor`, which the launch path must not load.
_GIT_TIMEOUT = 5.0

#: What `git worktree list` must never inherit (ruling G(a)): every variable `git rev-parse
#: --local-env-vars` prints on git 2.50.1, the variables git itself calls repository-local —
#: `test_every_variable_git_treats_as_repository_local_is_withheld` runs that command and holds
#: this list to it. Charter run from a git hook has them exported, `-C <checkout>` does not
#: override them, and the listing answered for the hook's repository; naming them one by one
#: (review round 3's `GIT_DIR`, `GIT_WORK_TREE`) missed `GIT_COMMON_DIR` (round 4).
#:
#: Since #964 every git `util.run` spawns goes without all of that list but its `GIT_CONFIG*`
#: variables, so this adds back only those three — ruling G(a) withheld the whole list here,
#: and #964 did not revisit that. Built on `util.GIT_REPOSITORY_ENV` rather than spelled twice,
#: so the two cannot drift apart.
_GIT_ENV = (*util.GIT_REPOSITORY_ENV, "GIT_CONFIG", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT")

#: The worktree listings asked for so far in this thread's current :func:`worktree_answers`
#: block, by common git directory — ``None`` outside one.
_SCOPE = threading.local()


@contextlib.contextmanager
def worktree_answers():
    """Ask each repository's worktree list at most ONCE for the length of this block — one
    launch, one `doctor` run, one `guard ask` (review round 4).

    The 5 s budget is per call. With git hung for 8 s and three checkouts sharing one common
    directory, a launch asked four times and took 20 s, and doctor's check five times and 25 s.
    The list does not change while charter wires: it adds and removes no worktree. Per block and
    per thread, never across processes or blocks — a later launch asks again. A block opened
    inside another shares the outer one's answers.
    """
    if getattr(_SCOPE, "answers", None) is not None:
        yield
        return
    _SCOPE.answers = {}
    # Git's own listing, per repository, for its two readers: which trees share an exclude
    # (:func:`_listed_trees`) and which pieces a workspace holds (:func:`_pieces`, #951).
    _SCOPE.listed = {}
    # The marker's trust verdict is memoised here too (:func:`_marker_untrusted`):
    # it does not change while charter wires, and asking git once per checkout per block is
    # the same budget the worktree listing already holds itself to.
    _SCOPE.tracked = {}
    # And whether a file at a path is somebody's untracked one (:func:`_yours_untracked`, #1072).
    _SCOPE.untracked = {}
    try:
        yield
    finally:
        _SCOPE.answers = None
        _SCOPE.listed = None
        _SCOPE.tracked = None
        _SCOPE.untracked = None


def _live_trees(tree: Path, exclude: Path) -> tuple[list[Path] | None, str]:
    """``(trees, "")`` — every working tree whose git reads *exclude*, as git lists them — or
    ``(None, why)`` when that list cannot be trusted.

    **Git is the registry**, as it is for `worktree.py`: ``git worktree list --porcelain``,
    parsed by `worktree.parse_porcelain`, so a worktree made by hand counts and one removed by
    hand does not.

    **Trusted only when it can be backed up** (ruling G (a)–(c), review round 3): git answered
    in time with no `GIT_DIR` of the caller's; every entry but a bare repository's names a
    directory holding a `.git`; and none is marked prunable. Git 2.50.1 lists a
    `--separate-git-dir` clone's GIT DIRECTORY as its main worktree, so that clone never
    entered the union; and `charter workspace rename` left git listing the old path as
    prunable, so every launch of another workspace unhid the moved worktree's local file. The
    rename relinks its worktrees now (#963), but one whose relink failed still reads this way.

    **Git is not asked when the common directory has no `worktrees/`.** Git keeps every
    linked worktree's administrative directory there, so without one the only tree is
    *tree* — and a launch wires every checkout in its workspace, at ~7 ms a spawn (measured).
    """
    common = exclude.parent.parent
    admin = common / "worktrees"
    # READ, never only lstat (#942 final review, ruling G's own class). Measured on git 2.50.1: with
    # `worktrees/` unreadable, or one worktree's directory in it, or only that worktree's `gitdir`,
    # `git worktree list` lists the rest and exits 0. The lstat before this passed all three, so
    # charter took git's short list for the whole one and dropped the line a live sibling still
    # needed. What git cannot read there, charter cannot account for. And an error other than "not
    # there" is doubt, never "no worktrees": `os.path.isdir` answered False for an EIO (review
    # round 4, N1's class), and charter took this checkout for the only tree.
    try:
        with os.scandir(admin) as entries:
            names = [entry.name for entry in entries]
    except (FileNotFoundError, NotADirectoryError):
        return [tree], ""
    except OSError:
        return None, f"{admin} cannot be checked — restoring read access clears this"
    for name in names:
        gitdir = admin / name / "gitdir"
        try:
            gitdir.read_bytes()
        except NotADirectoryError:
            # A stray file in `worktrees/`, which git passes over too (measured).
            continue
        except FileNotFoundError:
            # Git leaves that worktree out of its list as well, and says nothing (measured).
            return None, (f"{gitdir} is missing, so git leaves that worktree out of its list — "
                          f"`git worktree repair` from that worktree clears this")
        except OSError:
            return None, f"{gitdir} cannot be checked — restoring read access clears this"
    answers = getattr(_SCOPE, "answers", None)
    key = os.path.realpath(common)
    if answers is not None and key in answers:
        return answers[key]
    answer = _listed_trees(tree, exclude, common)
    if answers is not None:
        answers[key] = answer
    return answer


def _listed_trees(tree: Path, exclude: Path, common: Path) -> tuple[list[Path] | None, str]:
    """:func:`_live_trees`' question to git, asked once per :func:`worktree_answers` block.

    Each reason names what clears it (review round 4): `reinit` clears none of them.
    """
    from . import worktree as _worktree

    asked = f"listing the worktrees that share {exclude}"
    proc = _worktree_list(tree, common)
    if isinstance(proc, util.ProcTimeout):
        return None, (f"git timed out after {_GIT_TIMEOUT:g}s {asked} — a git that answers "
                      f"there in time clears this")
    if isinstance(proc, OSError):
        return None, f"git could not be run {asked} ({proc}) — a git that runs there clears this"
    if proc.returncode != 0:
        return None, f"git exited {proc.returncode} {asked} — a git that answers there clears this"
    trees: list[Path] = []
    for entry in _worktree.parse_porcelain(proc.stdout):
        path = Path(entry["path"])
        if entry["bare"]:
            continue
        if entry["prunable"]:
            # Git's own reason, not charter's guess: "moved or deleted" was said of a worktree
            # that was only unreadable.
            said = entry["prunable"]
            if _exists(path) is False:
                return None, (f"git lists {path} as prunable: {said} — `git worktree repair` from "
                              f"its new place if it moved, `git worktree prune` if it is gone")
            # Charter's own lstat decides "gone", never git's word (review round 5, R5): git calls
            # a worktree it cannot read prunable too, and `git worktree prune` there deletes git's
            # record of a checkout that is still on disk.
            return None, (f"git lists {path} as prunable: {said}, but charter does not find it "
                          f"gone — unreadable: restore access to it")
        if _exists(path / ".git") is not True:
            if os.path.realpath(path) == os.path.realpath(common):
                # Git 2.50.1 lists a `--separate-git-dir` clone's GIT directory as its main
                # worktree, and no listing will ever say where that checkout is.
                return None, (f"git lists {path}, which is not a checkout charter can look into "
                              f"— a separate git dir keeps this line by design; nothing to do")
            return None, (f"git lists {path}, which is not a checkout charter can look into — "
                          f"restoring that checkout, or read access to it, clears this")
        trees.append(path)
    return trees, ""


def _worktree_list(tree: Path, common: Path):
    """``git worktree list --porcelain`` for the repository whose common git directory is
    *common*, asked from *tree* — the finished process, or the `OSError` or `util.ProcTimeout`
    running it raised. Asked at most ONCE per repository per :func:`worktree_answers` block.

    One spawn for two readers (#951): :func:`_listed_trees` asks which trees share an exclude,
    :func:`_pieces` which pieces a workspace holds, and a launch asks both of every repository
    with a worktree — so a copy of this per reader was a second 5 s budget on a hung git, the
    cost review round 4 took out of the first. What either does with a failure is its own.
    """
    listed = getattr(_SCOPE, "listed", None)
    key = os.path.realpath(common)
    if listed is not None and key in listed:
        return listed[key]
    try:
        answer = util.run(["git", "-C", str(tree), "worktree", "list", "--porcelain"],
                          check=False, timeout=_GIT_TIMEOUT, unset=_GIT_ENV)
    except (OSError, util.ProcTimeout) as e:
        answer = e
    if listed is not None:
        listed[key] = answer
    return answer


class _Block(NamedTuple):
    """What charter's block must list, why any line in it could not be let go, and why any line
    *tree* needs was left out (:func:`_yours_untracked`)."""

    rels: list[str]
    unaccounted: list[str]
    #: ``{rel: why}`` for each line left out (#1072): whose file stopped it, and what clears it.
    shown: dict[str, str]


def _wired(t: Path) -> bool:
    """Whether checkout *t* is one charter wires: directly inside a workspace of this plane, or
    holding a charter marker — another plane's included, and one that cannot be checked counted.

    Review round 5 (R2): a line stays while its path is there IN A CHECKOUT CHARTER WIRES. A main
    checkout charter never wired keeps no line by holding a `.claude/settings.local.json` of its
    own, which keeps #870's promise that removing the workspace holding its linked worktree takes
    charter's block out of that repository.
    """
    if Path(os.path.realpath(t)).parent.parent == Path(os.path.realpath(config.WORKSPACES_DIR)):
        return True
    return _exists(t / GENERATED_MARKER) is not False


def _shared_rels(tree: Path, rels: list[str], text: str, exclude: Path,
                 leaving: bool = False) -> _Block:
    """What charter's block in *exclude* (holding *text*) must list once *tree* needs *rels*.

    **One block, every tree's files** (#942, review round 2). A clone and its linked worktrees
    read ONE `info/exclude`, the common git directory's, and each tree rewrote charter's block
    there alone: a worktree wired after its clone wrote the block without the line for the
    clone's harness-edited local file — the plane's private rules plus the operator's grants —
    and removing a workspace that held a worktree of another workspace's clone emptied that
    clone's block outright.

    **A line stays while its path is there** (review round 5, R2), in *tree* or in any other
    checkout charter wires that reads this exclude (:func:`_wired`), whatever any record says.
    Rounds 2 to 4 let a line go once a record said the file was no longer charter's, and each
    round found another way a record says that wrongly — a lost marker, a torn one, a kill
    between a write and its record, and last two launches racing to settle one file, which
    dropped the line for charter's own `.claude/settings.json`, the plane's rules and `env`, into
    somebody else's repository. Hidden while it is there is the safe direction, and a reversible
    one: a file somebody rewrote keeps its line too, charter never overwrites it, `doctor` names
    it ``foreign``, and `git add -f` commits it on purpose.

    *rels* only ever ADDS a line: what charter is about to write, or wrote and still recognises
    (:func:`_charter_owned`). Charter never adds one for a file it did not write.

    **A line leaves only on certainty** (ruling G, review round 3): its path confirmed absent —
    `FileNotFoundError` or `NotADirectoryError` from `os.lstat` — in every such checkout, and not
    in *rels*. It stays while, in any of them, the path cannot be checked, and every line stays
    while :func:`_live_trees` cannot be trusted; both say why in ``unaccounted``, which `doctor`
    prints, and each reason names what clears it (review round 4).

    *leaving* is :func:`unwire_guest`'s: a checkout charter is leaving keeps no line for a file of
    its own the harness does not also write into — a file somebody rewrote is theirs to see on the
    way out. A co-written file that stays keeps its line (:func:`_cowritten`): the harness saves
    into a file it finds already ignored without adding an ignore of its own.

    :data:`_TEMP_PATTERN` is listed whenever *rels* are, so it is in the block before the first
    temp exists (:func:`_write_whole`), and otherwise while a temp is left beside a listed path.

    **A line is never ADDED over a file of yours** (#1072). The line for *tree*'s file hides that
    path in every tree reading this exclude, so where another of them holds an untracked file there
    that charter did not write (:func:`_yours_untracked`), the line is left out: *tree* keeps
    charter's file, showing in its own `git status`, and ``shown`` says whose file stopped it and
    what clears it — or, for a machine-local file (:func:`_cowritten`), :func:`wire_guest` does not
    write it at all, #942's rule for a machine-local file charter cannot hide. Added only — a line
    already in the block is not re-asked, because git answers "ignored" for a path that line
    hides, whoever's file it is.
    """
    current = _block_rels(text)
    need = set(rels)
    if need:
        need.add(_TEMP_PATTERN)
    trees, doubt = _live_trees(tree, exclude)
    here = os.path.realpath(tree)
    others = [t for t in trees or () if os.path.realpath(t) != here]
    wired = [tree, *(t for t in others if _wired(t))]
    cowritten = _cowritten()
    shown: dict[str, str] = {}
    # Every other tree git lists, wired or not: a main checkout outside the plane reads this
    # exclude as surely as a piece does. Never the marker: an untracked `.charter-generated` is
    # charter's even where charter cannot read it (#1062), and `_charter_owned` vouches for none
    # there. The temp pattern names no file `_exists` finds. While the list cannot be trusted there
    # is no tree to ask, and a line is added as before — `unaccounted` already names that doubt.
    for rel in sorted(need - current - {GENERATED_MARKER}):
        mine = next((t for t in others if _yours_untracked(t, rel)), None)
        if mine is not None:
            need.discard(rel)
            # Git's spelling of the other checkout, which is resolved: it is the path git lists,
            # and the one a reader's `git -C` reaches. The checkout wired is named by its caller.
            # A machine-local file is withheld rather than left showing (`wire_guest`), so its
            # sentence says "not written", and what the next `reinit` then does is write it.
            local = rel in cowritten
            shown[rel] = (f"charter's {rel} is not {'written' if local else 'hidden'} there, "
                          f"because {mine / rel} is an untracked file charter did not write and "
                          f"the line hiding charter's would hide it too, through the {exclude} "
                          f"both checkouts read"
                          + (" — and a machine-local file charter cannot hide is one `git add` "
                             "from being committed" if local else "")
                          + f" — commit or move {mine / rel}, and the next `charter workspace "
                            f"reinit` {'writes and hides' if local else 'hides'} charter's")
    # The temp pattern's own parent is the checkout root, and the root is scanned with the rest:
    # leaving that line out of this set left the root unscanned whenever it was the block's last.
    beside = {Path(r).parent for r in current}
    why: list[str] = []
    for rel in sorted(current - need):
        for t in wired:
            if rel == _TEMP_PATTERN:
                there = _temps_left(t / d for d in beside)
            elif leaving and t is tree and rel not in cowritten:
                continue
            else:
                there = _exists(t / rel)
            if there is False:
                continue
            if there is None:
                why.append(f"{t / rel} cannot be checked — restoring read access clears this")
            need.add(rel)
            break
    if trees is None and current - need:
        why.append(doubt)
        need |= current
    ordered = sorted(need - {GENERATED_MARKER, _TEMP_PATTERN})
    if GENERATED_MARKER in need:
        ordered.append(GENERATED_MARKER)
    if _TEMP_PATTERN in need:
        ordered.append(_TEMP_PATTERN)
    return _Block(ordered, why, shown)


def _yours_untracked(t: Path, rel: str) -> bool:
    """Whether checkout *t* holds a file at *rel* that charter did not write and git would show
    as untracked there — one a line for *rel* in the exclude *t* reads would hide (#1072).

    Charter's own is what *t*'s TRUSTED marker vouches for (:func:`_charter_owned` over
    :func:`_read_marker_at`), so a marker git tracks — committed content, #1062 — makes no file
    charter's. Only untracked counts: a tracked file stays in `git status` whatever the exclude
    lists, and one git already ignores is hidden with or without charter's line. A git that cannot
    answer is not taken for "untracked", for the same reason a path that cannot be checked is not
    taken for "there": a git that cannot read *t* shows nothing there to lose from view.
    """
    if _exists(t / rel) is not True:
        return False
    if rel in _charter_owned(t, _read_marker_at(t)):
        return False
    key = (os.path.realpath(t), rel)
    cache = getattr(_SCOPE, "untracked", None)
    if cache is not None and key in cache:
        return cache[key]
    # One `git status` per path per `worktree_answers` block, as the marker's trust verdict is
    # asked: a launch wires every checkout twice over, and each pass would ask again.
    answer = util.git_path_state(t, rel)[0] == util.COMMITTABLE
    if cache is not None:
        cache[key] = answer
    return answer


def _exclude_state(tree: Path, rels: list[str], local=()) -> tuple[str, _Block]:
    """``(status, block)`` for the block in *tree*'s exclude — READ ONLY. Status is ``ok`` ·
    ``missing`` · ``stale`` · ``unreadable`` · ``unaccounted`` — current, and still keeping a line
    charter could not prove unneeded (:func:`unaccounted` says why) — or ``unhidden``: current, and
    leaving out a line *tree* needs because it would hide a file of yours (:func:`unhidden` says
    whose).

    *local* is the machine-local files charter would write into *tree* and has not
    (:func:`_withheld_local`): asked only whether their lines would be left out, so a line that
    would be is named in ``shown``. Never compared, because charter lists no line for a file it has
    not written, and a piece not wired yet must not read `stale` for a line it does not need.

    One reading for :func:`guest_layer`, :func:`unaccounted` and :func:`unhidden`, so a row
    and the reasons printed beside it cannot disagree. Compared against :func:`_shared_rels`, the
    block :func:`_register_excludes` writes: against *rels* alone, a block that rightly holds a
    sibling worktree's line reads `stale` for ever.
    """
    p = git_exclude_file(tree)
    if p is None:
        return "unreadable", _Block([], [], {})
    try:
        text = p.read_text()
    except FileNotFoundError:
        text = ""
    except (OSError, UnicodeDecodeError):
        return "unreadable", _Block([], [], {})
    block = _shared_rels(tree, rels, text, p)
    if local:
        block = block._replace(shown=_shared_rels(tree, [*rels, *local], text, p).shown)
    if _replace_block(text, _exclude_block(block.rels)) != text:
        return ("stale" if _EXCLUDE_BEGIN in text.splitlines() else "missing"), block
    # `unaccounted` first when a current block is both: one row carries one status, and a line kept
    # without proof is the one `reinit` can never clear, while an `unhidden` one clears the moment
    # the operator commits or moves their file.
    if block.unaccounted:
        return "unaccounted", block
    return ("unhidden" if block.shown else "ok"), block


def unaccounted(tree: Path) -> list[str]:
    """Why charter's block in guest checkout *tree*'s `info/exclude` keeps a line it cannot
    prove is still needed — READ ONLY, and empty when every line is accounted for.

    Ruling G's second half (review round 3): keep every line, and let doctor say what could not
    be accounted for. A block kept silently is a block nobody can tell from one that is right.
    """
    return _exclude_state(tree, _charter_owned(tree, _read_marker_at(tree)))[1].unaccounted


def unhidden(tree: Path) -> list[str]:
    """Which of guest checkout *tree*'s files charter left out of its `info/exclude` block, whose
    file of yours stopped each, and what clears it — READ ONLY, empty when nothing was (#1072).

    :func:`unaccounted`'s other half. That one names a line kept without proof; this names a
    line charter would not add, because a clone and its worktrees share the file and the line
    would hide an untracked file of yours in one of the others. Charter's own file stays written
    and shows in *tree*'s `git status` — the plane's ask/deny rules stay in force there — and
    `doctor`, `reinit` and `wt add` say so through this.
    """
    marker = _read_marker_at(tree)
    local = _missing_local(tree, _layer_status(tree, _guest_files(tree), marker))
    return list(_exclude_state(tree, _charter_owned(tree, marker), local)[1].shown.values())


def _missing_local(tree: Path, rows: list[tuple[str, str]]) -> list[str]:
    """The machine-local files (:func:`_cowritten`) *rows* — :func:`_layer_status` for guest
    checkout *tree* — call ``missing``: the ones charter would write there next."""
    cowritten = _cowritten()
    return [rel for rel, status in rows if status == "missing" and rel in cowritten]


def _withheld_local(tree: Path, rows: list[tuple[str, str]], marker: dict) -> dict[str, str]:
    """``{rel: why}`` for each machine-local file charter would write into guest checkout *tree*
    and will not, because its exclude line would hide a file of yours (#1072) — READ ONLY.

    One answer for `doctor`'s row and a chat's banner, so a file :func:`wire_guest` withholds is
    never called ``missing`` there, which reads as "`reinit` writes it" — the one thing `reinit`
    will not do while your file is there."""
    local = _missing_local(tree, rows)
    if not local:
        return {}
    shown = _exclude_state(tree, _charter_owned(tree, marker), local)[1].shown
    return {rel: shown[rel] for rel in local if rel in shown}


def _register_excludes(tree: Path, rels: list[str],
                       leaving: bool = False) -> tuple[str, frozenset[str]]:
    """Write charter's block into *tree*'s `info/exclude`. ``(status, left out)``: status is
    ``created``/``refreshed``/``present``/``blocked``, or ``unhidden`` when the block it wrote or
    found current leaves out a line *tree* needs, and *left out* names those lines' paths
    (:func:`unhidden`), for :func:`wire_guest` to withhold a machine-local one.

    *rels* is what *tree* needs; the block written is :func:`_shared_rels`' — never one
    tree's list alone, for the sibling worktrees reading the same file. *leaving* is passed
    through to it.

    Written whole (:func:`_write_whole`, review round 5, R1): killed after its truncate, an
    in-place write lost every line of the operator's own."""
    p = git_exclude_file(tree)
    if p is None:
        return "blocked", frozenset()
    try:
        text = p.read_text()
    except FileNotFoundError:
        text = ""
    except (OSError, UnicodeDecodeError):
        return "blocked", frozenset()
    block = _shared_rels(tree, rels, text, p, leaving)
    left = frozenset(block.shown)
    new = _replace_block(text, _exclude_block(block.rels))
    # `unhidden` over `created`, `refreshed` and `present`, never over `blocked`: those three all
    # mean "charter's files are hidden now", which is the one thing a line left out makes untrue.
    done = "unhidden" if block.shown else None
    if new == text:
        return done or "present", left
    had = _EXCLUDE_BEGIN in text.splitlines()
    try:
        _write_whole(p, new)
    except OSError:
        return "blocked", left
    return done or ("refreshed" if had else "created"), left


def guest_layer(tree: Path) -> list[tuple[str, str]]:
    """``(relative path, status)`` for the layer in guest checkout *tree* — READ ONLY.

    :func:`harness_layer`'s statuses, plus one row for ``.git/info/exclude``. That row is
    here rather than left as a silent side effect of writing because its absence is the
    *whole* failure this design guards against: the files can all be current and the
    operator still sees charter's noise in their own `git status`. A row nothing reports
    is a guarantee nothing keeps.

    The exclude row is omitted when charter has generated nothing here — there is then
    nothing to hide, and reporting `missing` would demand a block naming no files.
    """
    if not _wired_tree_ok(tree):
        # A workspace child that resolves out of the plane (a symlink to an outside repo).
        # Named as `foreign` so doctor reports it, and read no further — charter looks into
        # only a tree that is genuinely under `workspaces/`.
        return [(GENERATED_MARKER, "foreign")]
    marker = _read_marker_at(tree)
    rows = _layer_status(tree, _guest_files(tree), marker)
    if _marker_untrusted(tree):
        # `_read_marker_at` has already dropped a tracked marker as untrusted, so `marker` above
        # is `{}` and the files read against it as `foreign`/`missing`. Name the marker itself
        # too, so a reader sees WHY: charter never writes a `.charter-generated` git tracks, so a
        # tracked one is committed content whose digests charter will not act on.
        rows.append((GENERATED_MARKER, "tracked"))
    if (any(s in ("missing", "stale", "unwanted") for _rel, s in rows)
            and unrecorded_reason(tree)):
        # Ruling H (review round 4): a launch cannot publish the record a write needs first, so
        # it writes nothing and keeps every line — and says so here, where somebody looks. On the
        # errno the last publish failed with (review round 5, R5), never on `os.access`, which
        # passes a read-only filesystem and a full disk alike. `unwanted` stays (#942 closing
        # verification, which reverted its deletion): a withdrawal the checkout refuses, beside a
        # note an earlier publish left, otherwise led doctor's hint with a `reinit` that clears
        # neither.
        rows.append((GENERATED_MARKER, "unrecorded"))
    owned = _charter_owned(tree, marker)
    status, block = _exclude_state(tree, owned, _missing_local(tree, rows))
    # A machine-local file `wire_guest` withholds over a file of yours (#1072) is not `missing`:
    # that reads as "`reinit` writes it", which it will not while your file is there. The exclude
    # row reads `unhidden` and `unhidden` names whose file, and what clears it.
    rows = [(rel, "withheld" if s == "missing" and rel in block.shown else s) for rel, s in rows]
    # Also where charter owns nothing now but still keeps a line it cannot account for — a
    # marker deleted by hand leaves exactly that, and a row nothing reports is a guarantee
    # nothing keeps (review round 3). And where it owns nothing but withheld its local file.
    if owned or status in ("unaccounted", "unhidden"):
        rows.append((".git/info/exclude", status))
    return rows


def checkout_row(name: str, rel: str) -> tuple[Path, str] | None:
    """``(checkout, path inside it)`` for a :func:`harness_layer` or :func:`wire_harnesses` row of
    workspace *name* naming a file in one of its guest checkouts — ``None`` for a row of the
    workspace directory's own.

    One answer for `doctor`, `reinit` and `guard ask`, which word a checkout's file differently
    from the workspace's (review round 5): only a checkout is somebody else's repository, where a
    file charter did not write is committed with `git add -f`."""
    at = _piece_at(name, os.path.join(workspace_dir(name), rel))
    if at is not None:
        # A piece's row (#951): `.worktrees/<repo>/<piece>/…`, or the absolute path under a
        # relocated root — :func:`checkout_label`'s two spellings, read back by path arithmetic
        # rather than by asking git again for every row a command prints. No `git_dir` test, which
        # the clone's spelling below needs and this one does not: a row of the workspace
        # directory's own never lies under a piece's root.
        return at[0], "/".join(at[1])
    head, _, inner = rel.partition("/")
    tree = workspace_dir(name) / head
    return (tree, inner) if inner and git_dir(tree) is not None else None


def rules_not_in_force(cwd) -> str:
    """One line for a chat rooted in *cwd*: which of the plane's ask/deny rules the harness will
    not apply there, and the one thing that fixes it — ``""`` when every one is in force, or when
    *cwd* is not a workspace directory or inside a checkout in one. READ ONLY.

    Review round 5, R4. Every state that keeps a rule out of a chat — a record charter cannot
    publish, a file somebody rewrote, one the harness keeps, one charter cannot read — was named
    by `doctor` and `reinit` and by nothing the chat sees: a launch into a checkout whose root is
    not writable ran without the plane's newest rule and said nothing where the command gets
    typed. The rules are read out of the file the harness reads, never inferred from a status.
    """
    from . import worktree as _worktree
    from .harness import registry as _registry

    # A chat in a piece's worktree (#951) — the directory `charter wt add` sends a worker into, and
    # under a relocated root not inside `workspaces/` at all. `worktree.locate` names the workspace;
    # :func:`_piece_at` spells the checkout the way every other reader of that piece does.
    located = _worktree.locate(cwd)
    piece = _piece_at(located[0], cwd) if located else None
    if piece is not None and git_dir(piece[0]) is not None:
        ws, tree, where = located[0], piece[0], "this checkout"
        want, marker, refused = _guest_files(tree), _read_marker_at(tree), unrecorded_fix(tree, where)
    else:
        try:
            parts = Path(os.path.realpath(cwd)).relative_to(
                os.path.realpath(config.WORKSPACES_DIR)).parts
        except ValueError:
            return ""
        if not parts or not valid_name(parts[0]):
            return ""
        ws, base = parts[0], workspace_dir(parts[0])
        if len(parts) > 1 and git_dir(base / parts[1]) is not None:
            tree, where = base / parts[1], "this checkout"
            want, marker, refused = (_guest_files(tree), _read_marker_at(tree),
                                     unrecorded_fix(tree, where))
        elif len(parts) == 1:
            tree, where = base, "this workspace"
            want, marker, refused = _layer_files(ws), _read_marker(ws), ""
        else:
            return ""
    riding: dict[str, tuple[str, ...]] = {}
    for h in _registry.all():
        riding.update(h.restrictive_rules())
    gaps: list[str] = []
    rows = _layer_status(tree, want, marker)
    # A machine-local file withheld over a file of yours (#1072). A workspace directory has no
    # exclude, so nothing there is ever withheld and this answers `{}`.
    withheld = _withheld_local(tree, rows, marker)
    for rel, status in rows:
        rules = riding.get(rel, ())
        try:
            text = (tree / rel).read_text()
        except (OSError, UnicodeDecodeError):
            text = ""
        held = {r for h in _registry.all() for r in h.rules_held(text)}
        missing = [r for r in rules if r not in held]
        if not missing:
            continue
        if rel in withheld:
            status, fix = "withheld", withheld[rel]
        elif status in ("missing", "stale") and refused:
            fix = refused
        elif status in ("missing", "stale"):
            fix = f"`charter workspace reinit {ws}` writes them"
        elif status == "unreadable":
            fix = f"restore read access to {rel}"
        else:
            fix = f"add them to {rel} by hand"
        gaps.append(f"{', '.join(missing)} ({rel}, {status}) — {fix}")
    if not gaps:
        return ""
    return (f"⚠ **The plane's ask/deny rules below are NOT in force in {where}** — the harness will "
            f"not prompt for or refuse them here: " + "; ".join(gaps) + ".")


def wire_guest(tree: Path) -> list[tuple[str, str]]:
    """Materialise the layer into guest checkout *tree* and hide it there.

    **The block first, then the files, then the block again** (#942). The first version
    wrote the files and only then the block, so where the block could not be written a
    clone's `.claude/settings.local.json` was on disk and unhidden anyway — a machine-local
    rule one `git add -A` from somebody else's repository. Now every path charter is about to
    own is named before anything is written, and a path the harness co-writes is WITHHELD
    when that fails. The second pass settles the block on what the marker says afterwards: a
    withdrawal takes its line with it, and a checkout left with nothing of charter's loses
    the block altogether — which the first version skipped, because an empty marker read as
    nothing to do.

    The first pass names only paths that are missing, charter's own, or co-written paths
    charter has written before. A wanted path holding somebody's own file is never named,
    even for the length of one call: hiding their untracked work from their own `git status`
    is the failure :func:`_charter_owned` exists to prevent.

    Each pass names what THIS tree needs, and the block written is never that list alone
    (review round 2): a clone and its linked worktrees share the file, so it holds what
    every one of them needs and keeps a co-written line while the file exists in any of
    them — :func:`_shared_rels`.

    A tree that itself resolves out of the plane (a `workspaces/<ws>/<name>` symlinked to an
    outside repository) is not one charter may write to: :func:`_wired_tree_ok`. It is named
    `blocked` — the wire output and `reinit` report it — and nothing is written or hidden in
    it. Charter's per-file guard cannot answer this: it is relative to the tree root, which has
    already escaped.
    """
    if not _wired_tree_ok(tree):
        return [(GENERATED_MARKER, "blocked")]
    want = _guest_files(tree)
    marker = _read_marker_at(tree)
    cowritten = _cowritten()
    # By status, only what is MISSING: a current or stale file of charter's is already in
    # `_charter_owned`, and a current file charter never wrote is not charter's to hide. The
    # deletion sweep found `"ok"` and `"stale"` deciding nothing, and `"ok"` was worse than
    # nothing — it named a file charter does not own for the length of the call.
    ours = {rel for rel, status in _layer_status(tree, want, marker)
            if status == "missing" or (rel in cowritten and rel in marker)}
    # Unordered on purpose: `_shared_rels` sorts every block it writes, so an order here would
    # decide nothing — review round 2's sweep charged the `sorted` this line carried.
    planned = list(ours | (set(_charter_owned(tree, marker)) - {GENERATED_MARKER}))
    first, left = (_register_excludes(tree, planned + [GENERATED_MARKER]) if planned
                   else ("present", frozenset()))
    # A machine-local file whose line was left out over a file of yours is withheld too (#1072):
    # the same rule as an exclude that cannot be written, one path at a time. The shared file and
    # the mirrored agents are still written, so the plane's committed rules reach the piece.
    withhold = frozenset(cowritten) if first == "blocked" else frozenset(cowritten) & left
    rows = _materialise(tree, want, withhold, record_first=True)
    owned = _charter_owned(tree, _read_marker_at(tree))
    # Asked again even after a blocked first pass: an exclude that refused one write refuses
    # the next, so skipping it decided nothing a case could see (the sweep said so).
    second, _left = _register_excludes(tree, owned)
    # One row for the two passes, worst first: `blocked` whichever pass hit it, then a line left
    # out over a file of yours (#1072), then the pass that actually wrote. Two rows would report
    # one file twice.
    status = next((s for s in ("blocked", "unhidden", "created", "refreshed")
                   if s in (first, second)), "present")
    if owned or status != "present":
        rows.append((".git/info/exclude", status))
    return rows


def _prune_empty(d: Path, stop: Path) -> None:
    """Remove *d* and its parents up to (never including) *stop*, while they are empty AND
    resolve inside *stop*.

    A `.claude/agents/` left standing after its last generated file is removed is charter
    still visible in a repo it no longer has anything in.

    :func:`_inside`, the test every removal charter performs passes, so a directory a
    committed link points outside *stop* is never removed even when *d* was reached through
    one.
    """
    # `_inside` alone, and it also stops the walk AT the checkout root. *d* starts at
    # `(stop / rel).parent` for a relative `rel`, so every `d` the walk visits is spelled under
    # *stop* until it reaches *stop* itself — and there `_inside` is false, because a real
    # directory's parent never resolves inside it, or *stop* is a link, which `rmdir` refuses
    # (ENOTDIR). A lexical `stop in d.parents` beside it decided nothing this does not: the
    # deletion sweep found it unpinned, and no input can pin it.
    while _inside(stop, d):
        try:
            d.rmdir()
        except OSError:
            return
        d = d.parent


def unwire_guest(tree: Path) -> list[str]:
    """Remove what charter generated in guest checkout *tree*. Returns the paths removed.

    Only files whose current content still matches the marker: a path the operator has
    since rewritten is theirs, and deleting it would be the same overwrite this design
    refuses, one verb further on.

    **A co-written file that stays keeps its line** (#942). Once the harness has saved its
    own approvals into it the file is not charter's to delete — and taking the block away
    over a file that stays is the same leak as dropping its line: Claude Code adds no global
    exclude for a file that was already ignored when it first wrote there. **So does every
    line another tree of the same repository still needs** (review round 2): a linked
    worktree's `info/exclude` is its clone's, and removing a workspace that held one emptied
    the clone's block.

    A tree that resolves out of the plane (:func:`_wired_tree_ok`) is one charter never wrote
    to, so there is nothing of charter's to take out of it — and following it would delete
    from a repository outside the plane. Nothing removed.
    """
    if not _wired_tree_ok(tree):
        return []
    marker = _read_marker_at(tree)
    roots = _generated_roots(_guest_files(tree))
    removed: list[str] = []
    for rel in sorted(marker):
        p = tree / rel
        if rel.split("/", 1)[0] not in roots:
            # Charter removes only what it could have generated — a path under a harness root
            # (:func:`_generated_roots`). A marker naming a file outside those names one charter
            # never wrote, so unwire never unlinks it, whatever digest the marker records.
            continue
        if not _inside(tree, p):
            # The removal side of `_write_whole`'s rule (`_inside`): a marker naming a path
            # a committed directory link redirects out of the checkout would have this
            # `unlink` follow it and delete the file out there. `_read_marker_at` already
            # drops a marker with an absolute or `..` key, so this closes the one a clean key
            # under a directory symlink leaves open.
            continue
        try:
            # No `is_file()` in front of the read, for `_inherited_files`' reason: a path
            # already gone and a path that is a directory both raise here, and both mean
            # the same thing — charter has nothing of its own to take away.
            if content_digest(p.read_text()) not in _recorded(marker, rel):
                continue
            p.unlink()
        except (OSError, UnicodeDecodeError):
            continue
        removed.append(rel)
        _prune_empty(p.parent, tree)
    try:
        (tree / GENERATED_MARKER).unlink()
        removed.append(GENERATED_MARKER)
    except OSError:
        pass
    # Nothing of this tree's own is needed any more. A co-written file that stays keeps its line
    # by existing, and so does every file another wired checkout still holds — both
    # `_shared_rels`', so the removal and the wire cannot disagree about either. A file of this
    # tree's own left behind for somebody else's rewrite keeps no line: *leaving* (review round
    # 5, R2), which replaced the record of what the deleted marker named.
    _register_excludes(tree, [], leaving=True)
    return removed


def unwire_guests(name: str) -> list[str]:
    """Undo :func:`wire_guest` for every checkout in workspace *name*, before it goes.

    `charter workspace remove` is a `shutil.rmtree`, which takes charter's generated files
    with the workspace and would be the whole story if the exclude block lived inside it.
    For a LINKED WORKTREE it does not: `info/exclude` is the main repo's, somewhere else
    on disk entirely, and rmtree leaves charter's block sitting in a repo that is still
    there — naming paths that no longer exist, in a file the operator did not write and
    now cannot attribute. This is the call that keeps "removing the workspace removes what
    charter added" true for both shapes.
    """
    out: list[str] = []
    # Every tree listed before any is unwired, in one block: the listing asks git once per
    # repository, and the unwiring changes nothing git lists.
    with worktree_answers():
        for tree in guest_trees(name):
            out += [f"{checkout_label(name, tree)}/{rel}" for rel in unwire_guest(tree)]
    return out


def remember(name: str, text: str, title: str | None = None) -> Path:
    """Record one workspace memory as its own timestamp-prefixed file (and index it) — the
    task journal, structured exactly like persona memory. Returns the file path."""
    scaffold_memory(name)
    from . import memstore
    return memstore.write(memory_dir(name), text, title, timestamped=True, index=True)


def note(name: str, text: str) -> Path:
    """`note` is the long-standing verb for the same thing — an alias for remember()."""
    return remember(name, text)


def recall(name: str, query: str | None = None, limit: int = 8,
           unread: list | None = None) -> list[tuple[Path, str, int]]:
    """Search the workspace's memories by keyword, or (no query) list them all
    chronologically. Returns [(path, title, score)].

    A memory directory it could not list goes to *unread*, or raises `CannotCheck` without one
    (`memstore.search`'s rule, #1084)."""
    from . import memstore
    if query:
        return memstore.search([memory_dir(name)], query, limit, unread=unread)
    return [(p, t, 0) for p, t, _tx in memstore.gather([memory_dir(name)], unread)]


def forget_memory(name: str, ident: str):
    """Delete one workspace memory (by slug or filename) and drop its index line.

    Returns the removed path (falsy when nothing matched) so the caller can stage the
    deletion — see `memstore.forget`."""
    from . import memstore
    return memstore.forget(memory_dir(name), ident)


def memories(name: str) -> list[Path]:
    from . import memstore
    return memstore.files(memory_dir(name))


def read_notes(name: str) -> str:
    """Legacy memo text (notes.md), '' if none — kept for pre-v2 workspaces."""
    f = notes_file(name)
    return f.read_text() if f.exists() else ""


# --------------------------------------------------------------------------- #
# workspace charter (workspace.md) — the LIVING, human+agent-readable context: #
# the task's Vision (north star), Context & decisions, and Glossary. Seeded at  #
# creation (ideally with a vision the developer describes), kept current as the #
# work evolves, committed for LIVE workspaces, and inherited by a fork — so     #
# anyone can pick up the task with full context. The append-only chronological  #
# "what was done" log stays in memory/notes.md; this is the curated "why/what". #
# --------------------------------------------------------------------------- #

def charter_file(name: str) -> Path:
    return workspace_dir(name) / "workspace.md"


_VISION_PLACEHOLDER = (
    "_Not set yet — describe the goal: what are we building or fixing, and why? "
    'Set it with `charter workspace vision "…"` (or edit this file)._'
)

_CHARTER_TEMPLATE = """# {name}

> **Living charter** for this workspace — its north star and shared context.
> Keep it current as the work evolves (edit this file, or `charter workspace vision "…"`).
> It's committed + shared for LIVE workspaces, and a fork inherits it — so anyone
> can pick up the task with full context. Never put secrets here (vault only).

## Vision

{vision}

## Context & decisions

<!-- Key facts, constraints, and design/architecture decisions found while working —
     the durable "why", not a chronological log. Grow this as you learn. -->

_Nothing yet._

## Glossary

<!-- Task/domain vocabulary so a teammate or a fork isn't lost: `term` — definition. -->

_Nothing yet._

## Log

Chronological "what was done" lives in the task memo — `memory/notes.md`
(append with `charter workspace note "…"`).
"""


def _replace_md_section(text: str, header: str, body: str) -> str:
    """Replace the body under a ``## <header>`` section (down to the next ``## `` or
    EOF), keeping the header line. Appends the section if it's absent."""
    lines = text.splitlines()
    out: list[str] = []
    i, n = 0, len(lines)
    hdr = re.compile(rf"^##\s+{re.escape(header)}\s*$", re.IGNORECASE)
    replaced = False
    while i < n:
        out.append(lines[i])
        if hdr.match(lines[i]):
            i += 1
            while i < n and not lines[i].startswith("## "):
                i += 1
            out += ["", body.strip(), ""]
            replaced = True
            continue
        i += 1
    result = "\n".join(out).rstrip() + "\n"
    if not replaced:
        result += f"\n## {header}\n\n{body.strip()}\n"
    return result


def scaffold_charter(name: str, vision: str | None = None) -> None:
    """Create workspace.md from the template if missing; if a vision is given, set it."""
    # `read_charter` below already refuses a `workspace.md` that resolves out of the
    # plane; this is the same file, written. A guard on one side of one name is how the
    # write half of #336 stayed open after the read half closed (#349).
    cf = contain.writable(charter_file(name))
    if not cf.exists():
        cf.parent.mkdir(parents=True, exist_ok=True)
        # `create_for` (#1037): `exists()` is False for a dangling link, `writable` follows one
        # that lands inside the plane, and `write_text` then created whatever it named.
        config.create_for(cf, _CHARTER_TEMPLATE.format(
            name=name, vision=(vision.strip() if vision else _VISION_PLACEHOLDER)))
    elif vision:
        set_vision(name, vision)


def set_vision(name: str, text: str) -> None:
    """Set/replace the charter's ## Vision section (creating the charter if needed)."""
    scaffold_charter(name)
    cf = contain.writable(charter_file(name))
    cf.write_text(_replace_md_section(cf.read_text(), "Vision", text))


def read_charter(name: str) -> str:
    cf = charter_file(name)
    # `workspace.md` is committed, and the SessionStart digest reads one per workspace on
    # this plane for its vision line — so an entry that blocks costs every session its
    # briefing, and one that never ends costs more than that (#336).
    #
    # BOTH questions, which is `file_refusal`'s own stated precondition ("a path that is
    # not a link cannot have moved relative to the directory it was listed from, which the
    # caller checked once with `dir_refusal`") and what `persona.definition_refusal` has
    # always asked. Asking only the file half left the variant the file half structurally
    # cannot see: when the DIRECTORY is the link, `workspace.md` inside it is an ordinary
    # regular file with nothing to object to. Measured on 0.51.0 — a committed
    # `workspaces/evil -> ../../esc` with `[workspace] default = "evil"`, a legal workspace
    # name, printed the outside charter through `workspace vision` (#442). Containing the
    # NAME does not contain this; the name was never the wrong part.
    #
    # The fast path in `within_data` is one `lstat` here, because `workspaces/` is itself a
    # data root — so the SessionStart digest pays a syscall per workspace, not a resolve.
    if contain.dir_refusal(cf.parent) or contain.file_refusal(cf):
        return ""
    return cf.read_text() if cf.exists() else ""


def last_active(name: str) -> float | None:
    """When this workspace was last *worked* — a unix timestamp, or ``None``.

    One function, because two questions that sound different are the same one: "when did
    someone last write here" (memory, todos, the manifest, a piece record) and "when did a
    session last select it" (a pointer file naming it). A workspace can be chosen and then
    only read from, and one that reported nothing in that case would look abandoned on the
    exact day somebody was in it.

    Derived at read time from mtimes, never cached: ADR 0011's rule is that the record holds
    only what git cannot know, and "when was this touched" is something the filesystem
    already answers. Best-effort — an unreadable workspace is undated, not an exception.
    """
    d = config.WORKSPACES_DIR / name
    best: float | None = None

    def bump(p: Path) -> None:
        nonlocal best
        try:
            m = p.stat().st_mtime
        except OSError:
            return
        if best is None or m > best:
            best = m

    for f in (d / "workspace.md", d / "workspace.json"):
        if f.exists():
            bump(f)
    for sub in ("memory", "todos", "pieces", "refs"):
        try:
            for f in (d / sub).iterdir():
                bump(f)
        except OSError:
            continue
    try:
        for f in config.SESSIONS_DIR.glob("*.workspace"):
            if _read(f) == name:
                bump(f)
    except OSError:
        pass
    return best


def read_vision(name: str) -> str:
    """The ## Vision section body, or "" if unset/placeholder."""
    m = re.search(r"^##\s+Vision\s*$(.*?)(?=^##\s|\Z)",
                  read_charter(name), re.MULTILINE | re.DOTALL)
    body = (m.group(1).strip() if m else "")
    return "" if body.startswith("_Not set yet") else body


# --------------------------------------------------------------------------- #
# workspace STRUCTURE VERSION — the durable upgrade anchor. A workspace created  #
# by an older version of charter can lack files a newer one expects (workspace.md, #
# refs/, …). We stamp a tiny local marker (.charter-structure) with the layout   #
# version scaffold() produces; a workspace whose marker is missing/older, or that #
# is missing a baseline file, is "stale" and flagged (status line) until          #
# `charter workspace reinit` heals it. To ship a new structural element in future:    #
# create it in scaffold() and bump STRUCTURE_VERSION — every old workspace is then #
# auto-detected and one command upgrades it. The marker is local (regenerated by   #
# scaffold/restore), never committed.                                              #
# --------------------------------------------------------------------------- #

# v3 creates no directory, and that is deliberate. `changes/` is created lazily by the
# first `charter change create` — an always-present, always-empty one would break
# `charter workspace live --off`, whose path list is filtered by existence and relies on
# that filter doubling as a non-emptiness filter. The bump exists so every workspace made
# by an older charter flags itself, `reinit` runs `refresh_live_block()`, and a LIVE
# workspace picks up the three new un-ignore lines. Without it a plane that went LIVE
# before this version keeps a block that never mentions `changes`, and the records simply
# never travel — the same silent half-failure `todos/` had.
# v5 is the backfill #884 asks for, and it is why the manifest is a required component
# rather than only something `scaffold` now writes. 12 of this plane's 17 workspaces
# predate the invariant; without a bump they would go on having no `workspace.json` until
# somebody happened to run `snapshot`, which is the state the issue exists to end. With
# one, each flags itself in the status line and `charter workspace reinit --all` writes
# every missing manifest — membership only, branches unpinned.
STRUCTURE_VERSION = 5  # v2: memory is a per-file DB (MEMORY.md index), not a lone notes.md
                       # v3: the managed .gitignore block shares `changes/` (not its log)
                       # v4: the workspace carries charter's harness layer (#850)
                       # v5: every workspace has a workspace.json, from birth (#884)
_STRUCTURE_MARKER = ".charter-structure"
_LEGACY_STRUCTURE_MARKER = ".edm-structure"   # pre-rename; migrated in place on read


def _structure_marker(name: str) -> Path:
    """The marker path, migrating a pre-rename ``.edm-structure`` the first time.

    Renaming the marker without moving it would silently reset every existing
    workspace to v0: the new name isn't there, so a fully up-to-date workspace
    reads as stale and gets flagged for reinit. Harmless (reinit is additive and
    idempotent) but wrong, noisy, and on a LIVE workspace it manufactures a
    commit. Rename rather than re-stamp, so a genuinely older marker keeps its
    own version instead of being claimed as current.
    """
    d = workspace_dir(name)
    new = d / _STRUCTURE_MARKER
    legacy = d / _LEGACY_STRUCTURE_MARKER
    if not new.exists() and legacy.exists():
        try:
            legacy.rename(new)
        except OSError:
            return legacy          # unreadable/cross-device: still read the old one
    elif new.exists() and legacy.exists():
        legacy.unlink(missing_ok=True)   # both present: the new one already won
    return new


def _required_components(name: str) -> dict[str, Path]:
    """Baseline files every workspace should have — all created idempotently by
    scaffold(). Add to this (and bump STRUCTURE_VERSION) when the layout grows."""
    return {
        "workspace.md": charter_file(name),
        "workspace.json": manifest_path(name),
        "memory/MEMORY.md": memory_index(name),
        "refs/README.md": refs_dir(name) / "README.md",
    }


def structure_version(name: str) -> int:
    """The layout version stamped in the workspace's marker (0 if missing, unreadable, or in the
    way — see :func:`_stamp`)."""
    return _stamp(name)[0]


def _stamp(name: str) -> tuple[int, tuple[Path, int] | None]:
    """``(version, blocker)`` for the structure stamp — the one read of it, for
    :func:`structure_version` and for the ``in_the_way`` row :func:`structure_status` hands
    `reinit` to name. *blocker* is `_in_the_way`'s shape: the path, and the errno a stamp write
    there meets — ``ELOOP`` for a symlink (at the stamp, or a workspace directory `scaffold`
    refuses), ``EISDIR`` for a directory, ``ENXIO`` for any other file that is not a regular one.

    Opened ``O_NOFOLLOW | O_NONBLOCK`` and judged by ``fstat`` (#1074), the rule the stamp's
    write has had since #1051. `read_text` opened a FIFO at the name and waited for a writer
    that never came, so one stray local file froze `reinit` and every status-line render in the
    workspace. A non-blocking open of a FIFO returns at once, and a regular file is the only
    thing read. A link is not read through either, wherever it points: charter never writes the
    stamp through one, so a version read through one is not charter's.

    Asks `_in_the_way` only when the open fails, which on a healthy plane it does not: this runs
    for every workspace on each render, and the open is what today's read already paid for."""
    marker = _structure_marker(name)
    try:
        fd = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        # Absent, a link (``O_NOFOLLOW``'s ELOOP), or unanswered. `_in_the_way` tells a link at the
        # stamp or at the workspace directory from the rest, by `lstat`, as it does for every
        # baseline path.
        return 0, _in_the_way(marker, workspace_dir(name))
    try:
        mode = os.fstat(fd).st_mode
        if not stat.S_ISREG(mode):
            return 0, (marker, errno.EISDIR if stat.S_ISDIR(mode) else errno.ENXIO)
        # A raw read, not `os.fdopen`: that refuses a directory's descriptor by raising, and the
        # stamp is a few bytes, so one read of a page holds all of it.
        return int(os.read(fd, 4096).strip()), None
    except (OSError, ValueError):
        return 0, None
    finally:
        os.close(fd)


def structure_status(name: str) -> dict:
    """{'ok', 'missing': [rel…], 'unreadable': [(rel, path, errno)…], 'in_the_way': [(rel, path,
    errno)…], 'version', 'target'} — is the workspace's on-disk layout current? ``ok`` iff no
    baseline file is missing AND the marker is up to date.

    ``unreadable`` carries the path and the errno the check met, not the rel alone: `reinit` words
    what clears each one (:func:`uncheckable_fix`), and a second `stat` to ask why would be a
    different answer from the one this dict reports. The path is where that errno was met
    (:func:`_stopped_at`), which is the rel's own path unless a directory above it is what fails.

    ``in_the_way`` is a rel that is not there because something that is no directory stands where
    its directory goes (:func:`_in_the_way`, #1028), or whose own name, or a directory's above it,
    is a symlink charter will not follow (#1037). Not ``missing``, for the reason a loop is not:
    `scaffold` writes nothing at it or beneath it, so "missing" would flag a workspace for a
    `reinit` that cannot add the file, and have `reinit` report it added. `scaffold` reads this
    same list to decide what to leave alone."""
    # `_exists`, through symlinks (#942 review round 4): `Path.exists` raised on 3.11–3.13 for a
    # component that cannot be checked, crashing `workspace reinit` before it could say so. A
    # component that cannot be checked is not called missing — scaffolding over it is a write
    # into something charter cannot see — and is listed apart, for `reinit` to name with what
    # clears it (ADR 0009, #942 final review).
    seen = _baseline_answers(name)
    missing = [rel for rel, (_p, there, _code, blocker) in seen.items()
               if there is False and blocker is None]
    # The stamp is a row of `in_the_way` too (#1074), never of `missing`: an absent stamp is the
    # version line's to report, and one that is not a regular file is what `reinit` names instead.
    ver, stamp_blocker = _stamp(name)
    return {"ok": (not missing) and ver >= STRUCTURE_VERSION, "missing": missing,
            "unreadable": [(rel, _stopped_at(p, code), code)
                           for rel, (p, there, code, _blocker) in seen.items() if there is None],
            "in_the_way": [(rel, *blocker) for rel, (_p, _there, _code, blocker) in seen.items()
                           if blocker]
                          + ([(_STRUCTURE_MARKER, *stamp_blocker)] if stamp_blocker else []),
            "version": ver, "target": STRUCTURE_VERSION}


def _baseline_answers(name: str) -> dict[str, tuple[Path, bool | None, int | None,
                                                   tuple[Path, int] | None]]:
    """``{rel: (path, there, errno, blocker)}`` for every baseline path — the one
    classification :func:`structure_status` reports and :func:`scaffold` writes by.

    Apart from `structure_status` because that also reads the structure marker, which `scaffold`
    has no need of: it runs from `ensure` on a launch, and its stamp write is judged by the
    kernel. Both ask `_in_the_way` — this for the baseline paths, `_stamp` for the marker — so a
    link there is one rule, and the marker read never blocks on a FIFO (#1074).
    """
    wd = workspace_dir(name)
    out = {}
    for rel, p in _required_components(name).items():
        there, code = _existence(p, follow=True)
        # Asked of what answered "there" as well as of what answered "gone" (#1037): a link at
        # a baseline name to a file that IS there answers "there" through the link, and is in
        # the way all the same — nothing is written through it, and a link out of the plane
        # there took `scaffold` down with `contain.Refused`.
        out[rel] = (p, there, code, _in_the_way(p, wd) if there is not None else None)
    return out


def needs_reinit(name: str) -> bool:
    """True if an existing workspace's structure is stale (missing files or old marker)."""
    return workspace_dir(name).exists() and not structure_status(name)["ok"]


def reinit(name: str) -> dict:
    """Idempotently bring a workspace up to the current structure — create any missing
    baseline files and stamp the version marker. Additive: never destroys existing
    content. Returns the pre-reinit status (what was missing / the old version), plus
    ``layer`` — the harness-layer rows this call actually wrote.

    **``layer`` is always set, on every path**, and `cmd_workspace_reinit` subscripts it
    rather than carrying a fallback. An early return added above the line that sets it
    would be a `KeyError` in the repair command, which is the loud failure; the fallback
    it replaced made the same mistake print "up to date" over a workspace whose layer had
    just been rewritten.
    """
    before = structure_status(name)
    # The harness layer, written HERE rather than left to `scaffold`'s own call, because
    # the repair has to report what it DID and only the writer knows that: a `.claude`
    # that cannot be made comes back `blocked`, and reading the pre-state instead would
    # have printed "wrote it" over a write that never happened. `scaffold` below re-runs
    # it and gets `present` for everything, which is what idempotent means.
    #
    # Not folded into `ok`: `structure_status` answers "is this workspace's LAYOUT
    # current", which `needs_reinit` and the status line both key off, and a layer that
    # went stale because the plane's settings moved is not a workspace built by an older
    # charter. Two facts, two keys.
    before["layer"] = [(rel, st) for rel, st in wire_harnesses(name) if st != "present"]
    scaffold(name)  # creates memory/refs/workspace.md if missing + stamps the marker
    # Structure is not only what lives inside the workspace directory: which of its paths
    # are SHARED is part of the layout too, and that lives in the managed .gitignore block.
    # A plane made LIVE before `todos/` existed lists four paths per workspace and nothing
    # re-runs `set_live` unprompted — so the upgrade command is where it gets repaired.
    refresh_live_block()
    return before


def banner(active: str, explicit: str | None = None) -> None:
    """Print which workspace a command is acting on — surfaced everywhere so an
    agent always knows its boundary."""
    util.info(f"workspace: {active}  (via {source(explicit)})")
