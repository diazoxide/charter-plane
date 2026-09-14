"""``charter workspace`` commands: create/list/use/current/remove.

Workspaces are isolated per-task environments of repo clones under
``workspaces/<workspace>/``. See :mod:`charter.workspace` for how the active one is
resolved. Agents must operate within a single workspace and never mix them.
"""

from __future__ import annotations

import datetime
import errno
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from . import (change, config, contain, gitpolicy, gitstate, planegit, session, tui, util,
               workspace, worktree)
from .commands import (_cred_flag, _git, _origin_https, cmd_clone, commit_memory_reactive,
                       commit_push)


#: What the VISION column shows for a workspace nobody has written one for. A dash rather
#: than an empty cell for the reason every other `—` on this table is one: a blank reads as
#: a rendering fault. It is also the answer a handoff proposal acts on — a workspace with no
#: vision is never proposed as a target (`docs/handoff.md`), because there is nothing to
#: match the ask against.
NO_VISION = "—"


def _vision_cell(name: str) -> str:
    """*name*'s vision as one table cell: its first non-blank line, escaped, or a dash.

    **The first line only.** `## Vision` is a section and this is a row; what the rest of
    charter already treats as the vision LINE — SessionStart's neighbours digest, and the
    "Where this could run" block — is its first line, and three surfaces disagreeing about
    what a workspace is for is worse than any of them being terse.

    **And the first line plainly, with no `or ""`, no blank-line filter and no strip** —
    three guards the deletion sweep called survivors and was right to. `workspace.read_vision`
    returns a `str` for every input (``""`` for unset, for a placeholder and for a charter
    with no such section) and `.strip()`s the body it returns, so there is no ``None`` to
    fall back from, no leading blank line to skip and no leading space to take. A trailing
    one cannot show either: this is the row's last field and `cmd_workspace_list` rstrips
    the line. Three guards nothing can turn red, and "equivalent mutant" and "dead code" are
    the same finding.

    **Escaped at the render, and NOT clipped.** A vision is committed text a teammate wrote
    and this is a table on a terminal: a newline in one forges a row, and an ANSI sequence
    redraws the screen somebody is reading the table on. `contain.one_line` is charter's
    answer for exactly that shape of field. The clip is what is dropped
    (`contain.NO_CLIP`): this is the trailing, unpadded field, so length costs the table
    nothing — and a model matching an ask against half a sentence is matching against half
    the evidence, which is the whole reason the column exists.

    Never raises. A `workspace.md` charter cannot read costs its row a cell, not the
    listing.
    """
    try:
        first = next(iter(workspace.read_vision(name).splitlines()), "")
    except Exception:
        return NO_VISION
    return contain.one_line(first, limit=contain.NO_CLIP) if first else NO_VISION


def cmd_workspace_list(args) -> int:
    """Every workspace this plane offers, with the active one marked — #745.

    **The always-present workspace is folded in whether or not its directory exists**,
    which is `frame/switch.workspaces`' rule asked at the other surface rather than a
    second one invented here. `workspace.list_workspaces` reads DIRECTORIES, and
    `config.DEFAULT_WORKSPACE` is the rung `workspace.resolve` terminates on — so a plane
    where nobody has selected anything resolves to a name this listing did not contain,
    and the table printed a "you are here" inset with the mark on no row at all:

        Active workspace: default  (via default (nothing selected))

          WORKSPACE  MODE   CLONES  REPOS
          alpha      local  0       —
          beta       local  0       —

    That is #745 read from the CLI side. The report came from the frame — the `F2`
    workspace picker offers `default`, switching to it succeeds, and `charter workspace
    list` then does not list where the frame is standing — but the picker is not what is
    wrong: `charter workspace use default` accepts the same name on a plane that has never
    made one, and says so in as many words, because `workspace.ensure` creates it on
    demand. The disagreement was between the LISTING and everything else.

    **Not created here, and not by `charter init` either**, which is the other half of the
    report and the half this declines. `[workspace] default` names it, so `init` would be
    baking a directory for a value the operator may change in the charter.toml `init`
    itself just wrote — and every route that puts something IN the workspace (`clone`,
    `workspace use`, `workspace create`) already calls `ensure`. A row costs nothing and
    cannot go stale; a directory named after last week's config can.

    A row for it is honest about what it is: `local`, no clones, `—` for repos and `—` for
    a vision, which is exactly what it holds.

    **VISION is the trailing field and REPOS joined the measured columns**, because this is
    the listing a handoff proposal is matched against: the model reads these visions to
    decide which workspace an ask belongs in (`docs/handoff.md`). Until it was here, the
    command an agent is told to run said what each workspace HOLDS and nothing about what
    any of them is FOR. It goes last and unclipped for the reason `_vision_cell` gives —
    nothing after it needs the row to keep its shape, so leaving it whole costs alignment
    nothing.
    """
    active = workspace.resolve()
    # Aloud (#1043): a workspace charter cannot look at is named on stderr rather than left out
    # of the table without a word, and a plane holding one is not "no workspaces yet".
    names, unread = workspace.read_workspaces_aloud()
    fresh = not names and not unread
    if config.DEFAULT_WORKSPACE not in names:
        names = sorted(names + [config.DEFAULT_WORKSPACE])
    if fresh:
        # Still said, because "there is one row and it is the fallback" and "somebody has
        # made a workspace" are different states and the table cannot tell them apart.
        util.info(f"No workspaces yet — '{active}' is the one every plane starts on. "
                  "Create one: charter workspace create <name>")
    print(f"Active workspace: {active}  (via {workspace.source()})\n")
    live = workspace.live_workspaces()
    # `{:<22}` was a guess about a name the operator minted, and `{:<7}` twice over about
    # values charter mints — `:<n` pads a short value and PUSHES a long one, so a workspace
    # named past 22 sent its mode, clone count and repo list somewhere no other row's
    # landed. `str.format` counts characters as well, which is the half no constant can
    # fix: the stale marker appended here is ``" ⚠"``, two characters and three cells, so
    # every flagged row was already drawn one column right of the rest (#508, #592, #600).
    #
    # The numeric column is measured from its values too, for the reason `tui.column`'s
    # own docstring gives — sizing every column this way is what makes the table
    # unpushable by ANY value, rather than by none of the values somebody thought of.
    #
    # Nothing here costs a subprocess: `clones` is a directory listing and `needs_reinit`
    # reads a file, so unlike `status` (#597) there is no reason to draw before measuring.
    heads = ("WORKSPACE", "MODE", "CLONES", "REPOS")
    body = []
    for n in names:
        cl = workspace.clones(n)
        stale = " ⚠" if workspace.needs_reinit(n) else ""
        body.append(("* " if n == active else "  ", n + stale,
                     "live" if n in live else "local", str(len(cl)),
                     ", ".join(d.name for d in cl) if cl else "—",
                     _vision_cell(n)))
    widths = [tui.column(h, [row[i + 1] for row in body]) for i, h in enumerate(heads)]

    def line(mark, cells, last: str) -> str:
        return (mark + "".join(tui.pad(c, w) for c, w in zip(cells, widths))
                + last).rstrip()

    # The mark is an INSET, not a column: it is charter's own two-cell "you are here"
    # marker rather than a value measured from anything, which is how `frame.slots` and
    # `persona list` both spell theirs. One padder for the header and the rows, so the
    # two cannot disagree about a width the way a second format string would.
    print(line("  ", heads, "VISION"))
    for row in body:
        print(line(row[0], row[1:5], row[5]))
    stale_names = [n for n in names if workspace.needs_reinit(n)]
    if stale_names:
        util.warn(f"⚠ {len(stale_names)} workspace(s) need reinit ({', '.join(stale_names)}) — "
                  f"bring their structure up to date: charter workspace reinit --all")
    return 0


def cmd_workspace_current(args) -> int:
    name = workspace.resolve()
    print(name)
    # The lock is named relative to what RESOLVED, by the one function every workspace
    # sentence asks (#936). A sub-agent standing in another workspace's tree, or a forced
    # pointer, resolves somewhere the lock is not, and "locked for this session" beside
    # that name claimed a lock on the workspace charter would refuse to switch to.
    lock = _lock_words(name, workspace.is_locked())
    mode = "LIVE (committed + shared)" if workspace.is_live(name) else "LOCAL (private)"
    util.info(f"{mode} · resolved via {workspace.source()}, {lock}")
    # After the rung: resolution went on past the variable without a word, so the rung that
    # decided reads as the operator's choice while their export is what broke (#1055). The
    # value is not echoed; it is whitespace, and a line separator among it would start a
    # line of its own.
    if workspace.blank_in_environment():
        util.warn("$CHARTER_WORKSPACE is set but holds only whitespace, so charter ignored it "
                  "and the rungs below it decided. Unset it, or set it to the workspace you "
                  "meant.")
    vision = workspace.read_vision(name)
    if vision:
        util.info(f"Vision: {vision.splitlines()[0].strip()}")
    else:
        util.info(f'No vision set — describe the goal: charter workspace vision "…"')
    return 0


def cmd_workspace_create(args) -> int:
    try:
        wd = workspace.ensure(args.name)
    except ValueError as e:
        util.err(str(e))
        return 1
    workspace.scaffold(args.name)  # memory/ + refs/ + workspace.md charter beside its clones
    vision = getattr(args, "vision", None)
    if vision:
        workspace.set_vision(args.name, vision)
    live = getattr(args, "live", False)
    if live:
        workspace.set_live(args.name, True)

    tree_path = None
    mode = ("LIVE — charter + manifest + memory committed + shared + auto-saved" if live
            else "LOCAL — private (nothing committed); `charter workspace live` to share")
    util.ok(f"Workspace '{args.name}' ready ({mode}) → {wd.relative_to(config.ROOT)}/")
    if vision:
        util.info(f"Vision recorded → {(wd / 'workspace.md').relative_to(config.ROOT)}")
    else:
        util.info('⬢ No vision yet — ask the developer what this workspace is for, then record it: '
                  'charter workspace vision "<the goal>"  (it seeds workspaces/'
                  f'{args.name}/workspace.md, the living charter a fork inherits).')

    if args.use:
        before = workspace.is_locked()
        scope = workspace.set_active(args.name, force=getattr(args, "force", False),
                                     terminal_id=_terminal_for_selection())
        if scope == "locked":
            util.err(_locked_msg(args.name))
            # Inside a chat the refusal has already named how to work there. "Start a new
            # session, or --force" would contradict it with exactly the two routes a chat's
            # launch lock exists to replace (#936).
            if workspace.launch_lock():
                util.info(f"Workspace '{args.name}' was created.")
            else:
                util.info(f"Workspace '{args.name}' was created; start a new session to use it, "
                          f"or re-run with --force.")
            return 2
        _announce_selection(args.name, scope, workspace.is_locked(), before=before)
        _warn_env_override(args.name)

    if tree_path is not None:
        # The path is the point: charter cannot cd your shell, so selecting the workspace
        # is an instruction rather than an action — the same shape `worktree add` already
        # has. Being INSIDE this directory is what makes it the active workspace
        # (`workspace.from_path`), so no pointer has to agree with anything.
        rel = tree_path if not str(tree_path).startswith(str(config.ROOT)) else tree_path
        util.ok(f"Working tree → {rel}")
        util.info(f"  enter:  cd {rel} && claude")
        util.info(f"  Being in that directory IS this workspace — no pointer needed.")

    if args.repos:
        return cmd_clone(SimpleNamespace(repos=args.repos, workspace=args.name))
    if not args.use and tree_path is None:
        util.info(f"Select it with: charter workspace use {args.name}  "
                  f"(or --workspace {args.name} per command)")
    return 0


def cmd_workspace_use(args) -> int:
    if not workspace.valid_name(args.name):
        util.err(f"invalid workspace name '{args.name}'")
        return 1

    # A typo used to be a one-way door: the name was only validated for SHAPE, so
    # `use fature-x` created `fature-x`, took the session lock, and the correction then
    # hit `✗ Workspace is 🔒 locked to 'fature-x' for this session`. Creating is now
    # deliberate (`--create`), and an unknown name is a question rather than an action.
    # `default` is always selectable, whether or not its directory exists yet — it is
    # documented as "the always-present workspace used when none is selected", and
    # `ensure` creates it on demand. The unknown-name guard below refused it in a plane
    # that had never made one, which is every fresh plane.
    existing = workspace.list_workspaces()
    if (args.name not in existing and args.name != config.DEFAULT_WORKSPACE
            and not getattr(args, "create", False)):
        import difflib
        close = difflib.get_close_matches(args.name, existing, n=3, cutoff=0.6)
        util.err(f"no workspace named '{args.name}'.")
        if close:
            util.info(f"  Did you mean: {', '.join(close)}?")
        elif existing:
            util.info(f"  Existing: {', '.join(sorted(existing))}")
        util.info(f"  Create it: charter workspace use {args.name} --create")
        return 1

    workspace.ensure(args.name)
    before = workspace.is_locked()
    scope = workspace.set_active(args.name, force=getattr(args, "force", False),
                                 terminal_id=_terminal_for_selection())
    if scope == "locked":
        util.err(_locked_msg(args.name))
        return 2
    _announce_selection(args.name, scope, workspace.is_locked(), before=before)
    _warn_env_override(args.name)
    return 0


def cmd_workspace_unlock(args) -> int:
    """Release this session's workspace lock so a different one can be selected.
    The escape hatch for the mid-session switch guard — use sparingly; a fresh
    session is the clean way to pick another workspace.

    **Not inside a chat** (#936). A chat's lock is the workspace it was launched in
    (`workspace.launch_lock`), which is a record and not the file `workspace.unlock` deletes.
    Left to run, this answered "unlocked" in a picked chat and "nothing to unlock" in a silent
    one, beside a lock that refused the very next switch in both. So it refuses, deletes
    nothing, and names the way a chat works elsewhere."""
    held = workspace.launch_lock()
    if held:
        util.err(f"This chat is 🔒 locked to '{held}', the workspace it was launched in, and "
                 f"nothing unlocks that: a chat belongs to its workspace for life. "
                 + _open_a_chat_there())
        return 2
    if workspace.unlock():
        util.ok("Workspace unlocked for this session — `charter workspace use <name>` can switch now.")
    else:
        util.info("No workspace lock was set for this session (nothing to unlock).")
    return 0


def _open_a_chat_there(target: str = "<name>") -> str:
    """How to work in another workspace from inside a chat, said once for every refusal (#936).

    §4j's "a conversation wanted elsewhere is a new chat", made concrete. A workspace's tab
    and `F2 → workspace` both open that workspace, or focus the chat already open there; the
    `+` then opens another chat in it. The last clause is for the caller that can press
    neither, which is a sub-agent: `--workspace` names one workspace for one command and
    writes no pointer, so it moves no chat.
    """
    return ("To work in another workspace, open a chat there: its tab on the workspace strip, "
            f"or F2 → workspace. For one command, pass `--workspace {target}`.")


def _locked_msg(target: str) -> str:
    held = workspace.launch_lock()
    if held:
        # A chat. `unlock` releases nothing here and "start a new session" is not how a chat
        # moves, so neither is offered (#936). `--force` still works and is deliberately not
        # offered either: the split it makes, commands in one workspace and the chat drawn in
        # another, is what charter's own SessionStart used to recommend to every chat.
        return (f"Workspace is 🔒 locked to '{held}', the workspace this chat was launched in. "
                f"Switching its commands to '{target}' would leave the chat itself in '{held}' "
                f"(a chat belongs to its workspace for life). " + _open_a_chat_there(target))
    locked = workspace.is_locked() or "?"
    return (f"Workspace is 🔒 locked to '{locked}' for this session — switching to '{target}' "
            f"mid-session is disabled (never mix workspaces). Start a new session to pick another, "
            f"or force it: `charter workspace use {target} --force` (or `charter workspace unlock` first).")


def cmd_workspace_remove(args) -> int:
    name = args.name
    wd = workspace.workspace_dir(name)
    if not wd.exists():
        util.err(f"no workspace '{name}'")
        return 1

    risky = _work_at_risk(name)
    if risky and not args.force:
        util.err(
            f"Refusing to remove '{name}' — this would discard work: "
            + "; ".join(risky)
            + ". Push/commit first, or pass --force."
        )
        return 2

    # Open todos are REPORTED, never guarded on — see `_work_at_risk` for why they are not
    # in that list. Said here rather than above the guard so the count describes what is
    # actually about to happen, and only when there is something to say: "0 open todos" on
    # every removal is how a line stops being read at all, including on the removal where
    # it mattered.
    from . import todos
    open_todos = todos.count_open(name)
    if open_todos:
        util.warn(f"Discarding {open_todos} open todo(s) with '{name}' — nothing else holds them.")

    # Before the rmtree, never after: charter's generated files go with the directory,
    # but a LINKED WORKTREE's `.git/info/exclude` is the main repo's and lives somewhere
    # else on disk entirely — rmtree would leave charter's block behind in a repo that is
    # still there, naming paths that no longer exist (#870).
    workspace.unwire_guests(name)
    shutil.rmtree(wd)
    util.ok(f"Removed workspace '{name}' and its clones.")
    if workspace.resolve() == name and workspace.source() in ("session", "active-file"):
        # Removing the locked workspace: force past the lock, then re-lock to default.
        workspace.set_active(config.DEFAULT_WORKSPACE, force=True)
        util.info(f"Active workspace reset to '{config.DEFAULT_WORKSPACE}'.")
    return 0


def _relink_worktrees(moves: list[tuple[Path, Path]], new: str
                      ) -> tuple[int, list[tuple[Path, Path | None]], list[tuple[Path, Path]]]:
    """Tell git where the linked worktrees of *new*'s clones are after a rename moved them.

    Answers ``(relinked, left, named)``: how many worktrees git reads as linked both ways after
    the repair, ``(clone, tree)`` for each one it does not — ``tree`` is ``None`` when git could
    not even list the clone's worktrees, so nobody knows which there are — and ``(clone, tree)``
    for every tree the repair named, wherever it is now.

    A rename is a directory move, and both halves of a linked worktree's link are absolute
    paths: the tree's `.git` file names the clone's admin directory, and that directory's
    `gitdir` names the tree back. Moved together, neither was rewritten, so git called a live
    worktree prunable — `git worktree prune` or `gc` would then delete its admin directory
    while it held uncommitted work — and `worktree.list_for` answered "No worktrees." (#963).

    One `git worktree repair <trees…>`, run from the clone at its new place, rewrites both files
    of every moved tree it names. A tree outside the workspace did not move, but its `.git` file
    still names the clone's OLD admin directory, so git inside it fails; the same call mends
    that file too, named or not (measured, git 2.50.1). So every tree the clone links is named,
    and `git -C <clone> worktree repair <tree>` is the one command to print for either kind.

    *moves* is every ``(before, after)`` directory the rename moved: the workspace, and the
    workspace's directory under a worktree root kept outside the plane when there was one
    (#1027). Each *before* is a real path taken BEFORE its move: git records a worktree's real
    path, and the old directory is gone by the time it is compared.
    """
    relinked, left, named = 0, [], []
    for clone in workspace.clones(new):
        # Resolved like every tree git lists, so a printed command names both in one spelling.
        clone = clone.resolve()
        # Git keeps every linked worktree's admin directory here, so without one there is
        # nothing to relink and no reason to spawn — `workspace._live_trees`' same shortcut.
        if not (clone / ".git" / "worktrees").is_dir():
            continue
        listed = _worktrees_of(clone)
        if listed is None:
            left.append((clone, None))
            continue
        trees = []
        for row in listed:
            tree = Path(row["path"])
            # Under none of the moved directories — a worktree outside the workspace, or a piece
            # whose root could not be moved — it stayed where git has it.
            for before, after in moves:
                if tree.is_relative_to(before):
                    tree = after / tree.relative_to(before)
            # A tree git still lists but that is not on disk was gone before this rename. It is
            # not this rename's to repair, and git would only answer "not a valid path" for it.
            if (tree / ".git").is_file():
                trees.append(tree)
        util.run(["git", "-C", str(clone), "worktree", "repair", *map(str, trees)],
                 check=False, unset=workspace._GIT_ENV)
        # Read back rather than trusting the exit code: a repair that reports success over a
        # link git still cannot follow is exactly the success line ADR 0013 forbids.
        # A listing that failed confirms nothing, so every tree is named rather than counted.
        #
        # No `prunable` filter, and that is not an oversight: git prints a linked tree's path
        # from its `gitdir` file and calls it prunable when that file is missing or names a
        # `.git` that is not there. A path it prints that matches a tree whose `.git` file was
        # just seen is therefore never prunable — deleting the filter was measured green on Linux
        # and macOS, and a half-repaired tree is listed at its OLD path, which never matches.
        after = _worktrees_of(clone) or []
        linked_back = {os.path.realpath(r["path"]) for r in after}
        common = os.path.realpath(clone / ".git")
        for tree in trees:
            if (os.path.realpath(tree) in linked_back
                    and _common_dir_of(tree) == common):
                relinked += 1
            else:
                left.append((clone, tree))
        named += [(clone, tree) for tree in trees]
    return relinked, left, named


def _worktrees_of(clone: Path) -> list[dict] | None:
    """Every worktree git lists for *clone*, or ``None`` when git did not answer.

    The clone's own checkout is among them, and is left out by the caller's `.git` FILE test:
    a clone's `.git` is a directory (`workspace.is_clone`'s own line).
    """
    proc = util.run(["git", "-C", str(clone), "worktree", "list", "--porcelain"],
                    check=False, unset=workspace._GIT_ENV)
    return worktree.parse_porcelain(proc.stdout) if proc.returncode == 0 else None


def _common_dir_of(tree: Path) -> str:
    """The object store git inside *tree* reads, as a real path.

    Relative to *tree* when git answers relatively. A git that finds no repository prints
    nothing, which makes this *tree* itself — never a clone's `.git`, so it cannot pass for one.
    """
    proc = util.run(["git", "-C", str(tree), "rev-parse", "--git-common-dir"],
                    check=False, unset=workspace._GIT_ENV)
    return os.path.realpath(tree / proc.stdout.strip())


def cmd_workspace_rename(args) -> int:
    """Rename a workspace: move workspaces/<old>/ → workspaces/<new>/ (clones, memory,
    refs, and manifest come along), fix the manifest name + liveness block, repoint
    the active session/terminal pointer + lock so a renamed active workspace stays
    active, repoint every chat that says it is in the workspace (#795) so none of
    them is orphaned, move the workspace's directory under a worktree root kept outside the
    plane (#1027), and relink every linked worktree of a moved clone (#963). For a LIVE
    workspace, commit the tracked move (manifest + memory) so the rename propagates to the
    team."""
    old, new = args.old, args.new
    if not workspace.valid_name(new):
        util.err(f"invalid workspace name '{new}' (use lowercase letters, digits, . _ -)")
        return 1
    if old == new:
        util.err("old and new names are the same — nothing to rename.")
        return 1
    if not workspace.workspace_dir(old).exists():
        util.err(f"no workspace '{old}'")
        return 1
    if workspace.workspace_dir(new).exists():
        util.err(f"workspace '{new}' already exists — pick another name or remove it first.")
        return 1
    # Asked here, before either directory moves, because a clash found after `workspaces/<old>`
    # moved is a half-renamed workspace. Taken whether or not `<old>` has pieces there: what
    # sits at `<root>/<new>` would read as the renamed workspace's own. `lexists`, because a
    # dangling link is not `exists()` and a directory still cannot be renamed over it.
    if config.WORKTREES_ROOT is not None and os.path.lexists(config.WORKTREES_ROOT / new):
        util.err(f"{config.WORKTREES_ROOT / new} already exists, and it is where the worktrees "
                 f"of a workspace named '{new}' live — pick another name or move it first; "
                 f"nothing was renamed.")
        return 1

    was_live = workspace.is_live(old)
    # Capture the tracked metadata paths BEFORE the move — after it, the old dir is gone
    # and git needs the exact old paths to stage their deletion (the rename half git detects).
    tracked_old: list[str] = []
    if was_live:
        r = _git(["ls-files", "-z", "--", f"workspaces/{old}"], cwd=config.ROOT)
        tracked_old = [p for p in r.stdout.split("\0") if p]

    old_dir = workspace.workspace_dir(old).resolve()
    # A worktree root kept outside the plane names its directories after the workspace too
    # (`worktree.root`), so moving `workspaces/<old>` alone left every piece at `<root>/<old>/…`,
    # where nothing keyed on the new name looks: `wt list` found none and the next `wt add` cut
    # a second worktree beside the first (#1027). Not resolved like `old_dir`, because
    # `config.worktrees_root_for` already hands back a resolved root; and a `<root>/<old>` that is
    # itself a link moves as a link, so git's real paths behind it do not change at all.
    ext = config.WORKTREES_ROOT
    ext_old = ext / old if ext is not None and (ext / old).exists() else None
    moved = workspace.rename(old, new)
    moves = [(old_dir, workspace.workspace_dir(new).resolve())]
    stranded: OSError | None = None
    if ext_old is not None:
        try:
            ext_old.rename(ext / new)
        except OSError as e:
            # Not rolled back, for the reason a relink that did not take is not: the workspace
            # move worked, and undoing it is a second move that can fail the same way. Its pieces
            # stay where they are, and the relink below still follows the clone that moved.
            stranded = e
        else:
            moves.append((ext_old, ext / new))
    if stranded is None:
        util.ok(f"Renamed workspace '{old}' → '{new}' (clones, memory, and manifest moved).")
        if ext_old is not None:
            util.info(f"Its worktrees moved with it: {ext_old} → {ext / new}.")
    else:
        # The OS's own words and no cause of charter's (ADR 0009): a mount point and a directory
        # the operator cannot write both land here. And no ✓ — half a rename is not one (0013).
        util.warn(f"Renamed workspace '{old}' → '{new}' (clones, memory, and manifest moved), "
                  f"but not its worktrees: {ext_old} is still at the old name "
                  f"({stranded.strerror}).")
    relinked, left, named = _relink_worktrees(moves, new)
    if relinked:
        util.info(f"git reads {relinked} linked worktree(s) as linked to their clone at its "
                  f"new place.")
    for clone, tree in left:
        # Named one by one with the command that finishes the job, and the rename is not rolled
        # back: the move itself worked, and undoing it would only put the same links at risk
        # again. What must not happen is the success line above standing for this tree too.
        if tree is None:
            util.warn(f"git could not list the worktrees of {clone}, so none of them was "
                      f"relinked — repair each one that moved: "
                      f"git -C {clone} worktree repair <its new path>")
        else:
            util.warn(f"git does not read {tree} as a worktree of {clone} after the rename "
                      f"— repair it: git -C {clone} worktree repair {tree}")
    if stranded is not None:
        # Moving the directory by hand unlinks every piece in it again, exactly as the rename did
        # (#963), so the command that finishes it relinks each one at the path it will have.
        # Measured, git 2.50.1: after the `mv`, a repair run from the clone naming the new path
        # rewrites both halves of the link.
        finish = [f"mv {ext_old} {ext / new}"]
        by_clone: dict[Path, list[str]] = {}
        for clone, tree in named:
            try:
                rest = tree.relative_to(ext_old)
            except ValueError:
                continue                 # not one of the pieces left behind
            by_clone.setdefault(clone, []).append(str(ext / new / rest))
        finish += [f"git -C {clone} worktree repair {' '.join(trees)}"
                   for clone, trees in by_clone.items()]
        util.warn("Finish the rename: " + " && ".join(finish))
    if moved:
        # #795: the chats came too. A rename that silently re-labels running conversations
        # is one the operator finds out about from a panel; this is the sibling of the
        # "this session's active workspace followed the rename" line below, for the noun
        # that is a chat's identity rather than a session's work.
        #
        # A COUNT and not the ids. Every id in `moved` reached it through `contain.child`
        # (`state.frame_dir`, which every reader in `rename_workspace` goes through), so a
        # `contain.one_line` here would be a guard nothing could turn red — which this repo
        # deletes rather than ships. `new` is `valid_name`-checked at the top of this
        # function.
        util.info(f"{len(moved)} chat(s) in '{old}' followed the rename → '{new}'.")
    if workspace.resolve() == new and workspace.source() in ("session", "active-file"):
        # The lock clause is `_lock_words`', the one `current` prints (#936, review round 3).
        # This wrote "(still 🔒 locked)" itself and asked nothing, and three reachable states
        # made it false: `use gamma --force` in a chat launched in `north` (the lock is
        # `north`), a pointer SessionStart's reconcile seeded (no lock), and `use` then
        # `unlock` (no lock).
        util.info(f"This session's active workspace followed the rename → '{new}' "
                  f"({_lock_words(new, workspace.is_locked())}).")

    # Exit 1 while pieces are left under the old name, after everything else has run: a script
    # that goes on to `wt add` in the renamed workspace would cut the second worktree #1027 is
    # about, and the LIVE commit below is still owed for the move that did happen.
    left_behind = 1 if stranded is not None else 0
    if not was_live:
        util.info(f"'{new}' is LOCAL (private) — nothing committed.")
        return left_behind
    new_rel = _ws_meta_paths(new)
    msg = getattr(args, "message", None) or f"workspace: rename {old} → {new}"
    rc = commit_push(config.ROOT, ["add", "-A", "--", *tracked_old, *new_rel, ".gitignore"], msg)
    return rc or left_behind


def cmd_workspace_default(args) -> int:
    """Nominate the workspace a session lands on when nothing else has decided (#193).

    Mirrors `charter persona default`. The rung sits below the per-session and per-terminal
    pointers and above the built-in `default`, so an explicit choice survives a session
    boundary the way an explicit persona choice does — which matters most on a terminal that
    reports no pane id, where the pointer meant to cover "new session, same terminal" can
    never fire.
    """
    name = getattr(args, "name", None)
    # `--clear` FIRST, as `persona default` has it, and before the name is looked at: it
    # needs none (#955). Below the show branch, the form a person types —
    # `charter workspace default --clear` — printed the current default, exited 0 and
    # removed nothing, so clearing was reachable only by also typing a name nobody checked.
    if getattr(args, "clear", False):
        try:
            removed = workspace.clear_declared_default()
        except OSError as e:
            # The OS's own words beside the path, and no cause of charter's: a read-only
            # `workspaces/` and a directory sitting at that name both land here, and picking
            # one to name is the ADR 0009 failure. The path is what the reader goes to look at.
            util.err(f"could not remove {workspace.default_file()} "
                     f"({e.strerror or e.__class__.__name__}) — the declared default is left "
                     "as it was.")
            return 1
        if removed:
            util.ok("Cleared the declared default workspace.")
        else:
            util.info("No default workspace was declared.")
        return 0
    if not name:
        cur = workspace.declared_default()
        if cur:
            util.info(f"Declared default workspace: {cur}")
        else:
            util.info("No declared default — a session with nothing else selected lands on "
                      f"'{config.DEFAULT_WORKSPACE}'. Set one: charter workspace default <ws>")
        return 0
    # The name FIRST, and separately from "does it exist". `workspace_dir(name).exists()`
    # accepted `../../esc` — the directory is really there, it is simply not a workspace —
    # and wrote it into a committed file every future session reads (#442). "A path that
    # exists" was never the question being asked (the same note `persona.py` keeps at
    # #337). It is asked here as well as in `set_declared_default` because a refusal a user
    # sees has to be a sentence rather than a traceback.
    if not workspace.valid_name(name):
        util.err(f"'{name}' is not a workspace name (letters, digits, '.', '_', '-'; "
                 "must not start with a dot). This file is committed and read on every "
                 "session start, so a value that is not a name is refused here.")
        return 1
    if not workspace.workspace_dir(name).exists():
        util.err(f"no workspace '{name}' (create it: charter workspace create {name})")
        return 1
    workspace.set_declared_default(name)
    util.ok(f"Default workspace set to '{name}' — sessions land here when nothing else "
            f"has decided.")
    util.info("  Committed, so it travels with the plane. It is read LAST, so an explicit "
              "`--workspace`, $CHARTER_WORKSPACE, the tree you are standing in, or a "
              "session/terminal selection all still win.")
    return 0


def cmd_workspace_optimize(args) -> int:
    """Optimize a workspace's memory (one, or ``--all``) — the workspace half of what
    ``charter persona optimize`` has always done for personas.

    The engine was never persona-specific: ``curate.report``/``apply_safe`` take any memory
    directory. Only the wiring was, which left the fastest-growing store in the plane — the
    workspace journal, appended every session and nudged by the memory-cadence hook — with
    no dedupe, no index repair and no stale review.

    Same two tiers as the persona command, deliberately: ``--apply`` performs only the safe
    and reversible ops (collapse exact duplicates, repair the index), and proposals (near-dup
    merges, stale archives) are printed for a human to decide. A read-only run names what
    ``--apply`` would do, because a read-only run that quietly rewrote an index is how
    "read-only" stops meaning anything.
    """
    from . import curate
    # Over every workspace, each one it could not look at is named, not skipped (#1043).
    names = ([args.name] if getattr(args, "name", None)
             else workspace.read_workspaces_aloud()[0])
    if getattr(args, "name", None) and not workspace.workspace_dir(args.name).exists():
        util.err(f"no workspace '{args.name}'")
        return 1
    if not names:
        util.info("No workspaces to optimize.")
        return 0

    apply = getattr(args, "apply", False)
    stale_days = getattr(args, "stale_days", 90)
    total_actions = 0
    for n in names:
        mdir = workspace.memory_dir(n)
        if not mdir.exists():
            continue
        try:
            rep = curate.report(mdir, stale_days=stale_days)
        except workspace.CannotCheck as e:
            # Named, and the next one read (#1084) — `cmd_persona_optimize`'s rule.
            workspace.say_unread(e.unread)
            continue
        if rep["total"] == 0:
            continue
        print(f"\n◆ {n}  ({rep['total']} memories · {len(rep['exact_dups'])} exact-dup "
              f"group(s) · {len(rep['near_dups'])} near-dup pair(s) · {len(rep['stale'])} stale)")
        if apply:
            actions = curate.apply_safe(mdir)
            for a in actions:
                util.ok(f"  auto: {a}")
            total_actions += len(actions)
            if actions:
                rel = str(mdir.relative_to(config.ROOT))
                commit_memory_reactive(
                    [rel], f"workspace({n}): curate — {len(actions)} safe op(s)")
            rep = curate.report(mdir, stale_days=stale_days)
        else:
            pending = curate.pending_auto(rep)
            if pending:
                print("  would auto-apply (re-run with --apply):")
                for a in pending:
                    print(f"    + {a}")
        props = curate.proposals(rep)
        if props:
            print("  proposals (not auto-applied — decide these yourself):")
            for p in props:
                print(f"    ? {p}")
        elif apply:
            util.info("  clean — nothing to propose.")

    if not apply:
        util.info("\nRead-only. Re-run with --apply to auto-apply the safe/reversible ops "
                  "(exact-dup collapse + index repair); proposals always stay manual.")
    elif total_actions == 0:
        util.info("\nNo safe ops to apply — the journal is already tidy.")
    return 0


def _work_at_risk(name: str) -> list[str]:
    """Clones **and worktrees** in the workspace with uncommitted or unpushed work.

    Only that. Open todos are deliberately NOT here, though `remove` reports them: this
    list is what is *unrecoverable*, and a todo is a note about the future, not work that
    ceases to exist. A workspace whose todos were all abandoned is precisely the one worth
    deleting, and making that case demand `--force` would teach the habit of reaching for
    `--force` — which is how a guard stops protecting the commits it exists for.
    """
    out = []
    for d in workspace.clones(name):
        # #917, and the sharpest instance of it in this package: what this list is empty of
        # is what `cmd_workspace_remove` hands to `shutil.rmtree`. Reading a `git status`
        # that FAILED as "no uncommitted changes" makes a clone charter could not look at
        # indistinguishable from one it looked at and found empty — and then deletes it.
        # An unreadable clone is at risk by definition: charter cannot say what is in it.
        dirt = gitstate.read(d)
        if not dirt.known:
            out.append(f"{d.name}: could not be read — {dirt.said}")
            continue
        if dirt.rows:
            out.append(f"{d.name}: uncommitted changes")
            continue
        up = _git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=d)
        if up.returncode == 0:
            ahead = _git(["rev-list", "--count", "@{u}..HEAD"], cwd=d).stdout.strip()
            if ahead and ahead != "0":
                out.append(f"{d.name}: {ahead} unpushed commit(s)")
    return out + _worktrees_at_risk(name)


def _worktrees_at_risk(name: str) -> list[str]:
    """Worktrees of this workspace holding work that removing it would destroy (#91).

    The loop above cannot see these and never could: it iterates `workspace.clones()`,
    which filters on `is_clone` — a clone's ``.git`` is a directory, a linked worktree's is
    a FILE. That exclusion is deliberate and correct for counting repos, and it is exactly
    what left worktrees unguarded while `shutil.rmtree` took them anyway.

    The **rule** differs from the clone rule above, not just the paths. A worktree is at
    risk when it holds commits reachable from no other ref — the work that would actually
    cease to exist — which `charter worktree remove` uses too, so the two guards refuse on
    identical grounds. Keeping them identical is the point: they answer one question, and a
    workspace that removed what a worktree refused to would be the original bug again.

    Not "has no upstream", which is what this was first written as (#91) and then narrowed
    (#104): a parallel agent's piece has no upstream from the moment it is created, so that
    reading refused over pieces with nothing to lose — and a guard that fires on the
    harmless common case teaches the `--force` habit that stops it protecting anything.

    This fires even when the worktree directory lives outside the workspace — a relocated
    ``[plane] worktrees`` root, which `shutil.rmtree` never touches. That is not an
    oversight: a linked worktree keeps its objects in the CLONE's object store, so removing
    the clone destroys those commits whether or not the directory survives.
    """
    base = worktree.root(name)
    try:
        repos = sorted(d.name for d in base.iterdir() if d.is_dir())
    except OSError:
        return []

    out = []
    for repo in repos:
        for wt in sorted(worktree.dirs_for(name, repo)):
            label = f"{repo}/{wt.name}"
            dirt = worktree.dirt(wt)
            if not dirt.known:
                # The same rmtree gate, the worktree half. Said in the shape the
                # `unique_commits` line below has always used — this function already knew
                # how to report "could not be checked" for one of its two questions.
                out.append(f"{label}: could not be checked for uncommitted changes")
                continue
            if dirt.rows:
                out.append(f"{label}: uncommitted changes")
                continue
            alone = worktree.unique_commits(wt)
            if alone is None:
                out.append(f"{label}: could not be checked for unique commits")
            elif alone:
                out.append(f"{label}: {alone} commit(s) that exist nowhere else")
    return out


def _repo_branch(clone) -> str:
    return _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=clone).stdout.strip() or "HEAD"


def _pin(row) -> str:
    """The branch a manifest row pins, or ``""`` for one that pins none.

    Two shapes reach this and both are ordinary. `snapshot` writes ``{"name", "branch"}``,
    because an operator asked for the branches to be captured; everything charter writes on
    its own writes ``{"name"}`` alone (#884). `row['branch']` was a `KeyError` waiting for
    the first manifest charter wrote itself, and one function is what keeps the reading and
    the reporting from disagreeing about which rows have a branch.

    Stripped, so the value the leading-dash guard inspects is the value git is handed:
    ``" -b"`` is not a ref anybody writes and `startswith` says nothing about it, while
    `git checkout` reads the argument it is actually given (#334).
    """
    return str(row.get("branch") or "").strip()


def _git_user() -> str:
    return _git(["config", "user.name"]).stdout.strip() or os.environ.get("USER", "unknown")


def _restore_blockers(name: str) -> list[str]:
    """Repos whose current branch wouldn't restore for another engineer — uncommitted
    work, unpushed commits, or a branch not on the remote at all. The 'enforce push'
    guard: a manifest branch is only meaningful if it's actually on the remote.

    A clone charter could not read blocks too (#917). This list empty is what lets
    `cmd_workspace_snapshot` write a manifest that claims to capture reality; a `git
    status` that failed contributes the same emptiness as one that found nothing, and the
    manifest then asserts a state nobody measured — to another engineer, on another
    machine, who has no way to know it was never checked.
    """
    out = []
    for d in workspace.clones(name):
        dirt = gitstate.read(d)
        if not dirt.known:
            out.append(f"{d.name}: could not be read — {dirt.said}")
            continue
        if dirt.rows:
            out.append(f"{d.name}: uncommitted changes")
            continue
        up = _git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=d)
        if up.returncode != 0:
            out.append(f"{d.name}: branch '{_repo_branch(d)}' isn't pushed to a remote")
            continue
        ahead = _git(["rev-list", "--count", "@{u}..HEAD"], cwd=d).stdout.strip()
        if ahead and ahead != "0":
            out.append(f"{d.name}: {ahead} unpushed commit(s)")
    return out


def cmd_workspace_live(args) -> int:
    """Toggle a workspace between LIVE (shareable — manifest + memory committed/synced/
    auto-saved) and LOCAL (`--off`: private, nothing committed)."""
    name = args.name
    if not workspace.workspace_dir(name).exists():
        util.err(f"no workspace '{name}' (create it: charter workspace create {name})")
        return 1
    if getattr(args, "off", False):
        rel = _ws_meta_paths(name)
        if rel:  # untrack the committed files (keeps them on disk), then re-ignore
            _git(["rm", "-r", "--cached", "-q", "--", *rel], cwd=config.ROOT)
        workspace.set_live(name, False)
        util.ok(f"Workspace '{name}' is now LOCAL (private). Its manifest + memory are no "
                "longer committed. Finalize the untracking: charter save")
        return 0
    workspace.scaffold(name)
    if not workspace.set_live(name, True):
        util.info(f"Workspace '{name}' is already LIVE.")
    else:
        util.ok(f"Workspace '{name}' is now LIVE — manifest + memory are committed + shared + auto-saved.")
    util.info(f"Record its repos: charter workspace snapshot {name}  ·  share: charter workspace save {name}")
    return 0


def cmd_workspace_snapshot(args) -> int:
    """Capture the workspace's repos + branches into the committed manifest
    (workspaces/<name>/workspace.json). Enforce-push: refuse if a repo has
    uncommitted/unpushed work, so the recorded branch fully captures reality."""
    name = getattr(args, "name", None) or workspace.resolve()
    clones = workspace.clones(name)
    if not clones:
        util.err(f"workspace '{name}' has no repo clones to snapshot.")
        return 1
    blockers = _restore_blockers(name)
    if blockers and not getattr(args, "force", False):
        util.err(f"Refusing to snapshot '{name}' — push repo work first so the branch "
                 "captures the real state:")
        for b in blockers:
            util.err(f"  {b}")
        util.info("Commit + push inside each repo, then retry (or --force to snapshot branches as-is).")
        return 2
    m = workspace.read_manifest(name)
    m["name"] = name
    if getattr(args, "description", None):
        m["description"] = args.description
    m.setdefault("description", "")
    m["repos"] = [{"name": d.name, "branch": _repo_branch(d)} for d in clones]
    m["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    m["updated_by"] = _git_user()
    workspace.write_manifest(name, m)
    util.ok(f"Snapshot '{name}' → workspaces/{name}/workspace.json  ({len(m['repos'])} repo(s)):")
    for r in m["repos"]:
        util.info(f"  {r['name']} @ {r['branch']}")
    util.info("Share it with the team: charter workspace save   (commits + pushes manifest + memory).")
    return 0


def cmd_workspace_restore(args) -> int:
    """Rebuild a workspace from its committed manifest — clone each repo and check out
    its recorded branch (all now, or --on-demand). Partial access is normal: repos you
    can't reach are skipped."""
    name = args.name
    m = workspace.read_manifest(name)
    repos = m.get("repos") or []
    if not repos:
        util.err(f"no manifest for '{name}' (workspaces/{name}/workspace.json). "
                 "Pull fresh metadata first: charter workspace sync")
        return 1
    workspace.ensure(name)
    workspace.scaffold(name)  # ensure the local structure (refs/, marker) + stamp version
    util.info(f"Restoring '{name}' — {len(repos)} repo(s) from manifest "
              f"(updated {m.get('updated_at', '?')} by {m.get('updated_by', '?')}).")
    if getattr(args, "on_demand", False):
        for r in repos:
            util.info(f"  on-demand: {r.get('name')} @ {_pin(r) or 'no branch recorded'} "
                      f"(clone when you enter it)")
        util.info("Enter the workspace and clone as you go: charter clone <repo> -w " + name)
        return 0
    # #325/#334/#328 all describe this join and each frames it as another's: #325 claims
    # it as the clone-destination half, #334 disclaims it as "the join #325 already
    # names", and #328's bullet assigns it to #334. Three issues, one line, nobody's — so
    # it is fixed HERE, explicitly, rather than left for whichever ticket closes last.
    #
    # `workspace.json` is committed precisely so a teammate can restore someone else's
    # workspace; that is the feature, and it is what makes every field in it untrusted.
    # `is_git_repo` below is an existence check, never a containment one, so without this
    # a name with parent components selected a repository the operator never named — and
    # `git checkout` plus a CREDENTIALED `git pull` then ran inside it (#334, confirmed on
    # 0.47.2 by the target repository's own reflog).
    wd = workspace.workspace_dir(name)
    contained, refused = [], []
    for r in repos:
        d = contain.child(wd, str(r.get("name") or ""))
        if d is None:
            refused.append(r)
        else:
            contained.append((r, d))
    for r in refused:
        util.err(f"  {str(r.get('name'))!r}: refused — {contain.refusal(str(r.get('name') or ''))}. "
                 f"Fix workspaces/{name}/workspace.json.")
    # Per-entry, never per-file: a manifest is shared and committed, so rejecting the whole
    # thing would let one bad row deny the other eight repos to the whole team — an attack
    # in its own right. `restore` already skips repos it cannot reach and says so.
    repos = [r for r, _ in contained]
    if not repos:
        util.err(f"No usable repos in '{name}'s manifest.")
        return 1
    missing = [r["name"] for r, d in contained if not workspace.is_git_repo(d)]
    if missing:
        cmd_clone(SimpleNamespace(repos=missing, workspace=name))
    ok = 0
    for r, d in contained:
        if not workspace.is_git_repo(d):
            util.warn(f"  {r['name']}: not cloned (no access?) — skipped.")
            continue
        # An UNPINNED row is restored by existing (#884). Every manifest charter writes
        # itself records membership and no branch — a branch here carries `snapshot`'s
        # promise that it is on the remote, and the writers nobody asked for cannot make
        # it — so `restore` has to read a row that has none. Before the forge lookup,
        # because there is nothing to check out and nothing to pull: the clone above is
        # already on whatever the remote calls default, which is what "unpinned" means.
        if not _pin(r):
            util.ok(f"  {r['name']} @ default branch (no branch recorded — "
                    f"`charter workspace snapshot {name}` pins one)")
            ok += 1
            continue
        forge = gitpolicy.forge_for(d)  # THIS clone's own forge — never a hardcoded one.
        if forge is None:
            # Unrecognised host (not a default forge, not declared in charter.toml) —
            # never guess a credential helper for it; skip rather than mis-authenticate.
            util.warn(f"  {r['name']}: origin host isn't a known/declared forge — skipped.")
            continue
        cred = _cred_flag(forge)
        # #334's second half. A branch is a REF, not a path segment — `feature/x` is the
        # convention most teams use — so no name rule applies here and the treatment is
        # argv position instead. Without a guard, a manifest branch beginning with a dash
        # is read by `git checkout` as an option, and `checkout` has options that write:
        # `-b`, `-B`, `--orphan`, `--pathspec-from-file`.
        #
        # A leading dash is the whole check, and `git check-ref-format` is deliberately
        # NOT used: verified against git 2.50.1, `check-ref-format refs/heads/-b` ACCEPTS
        # `-b`, because a leading dash is legal inside a ref. Ref grammar answers a
        # different question than argv safety, and reaching for it here would have cost a
        # subprocess per repo while closing nothing.
        branch = _pin(r)   # the value the guard below inspects IS the one git is handed
        if branch.startswith("-"):
            util.err(f"  {r['name']}: refused branch {branch!r} — a branch read from a "
                     f"committed manifest may not begin with '-', which git would read as "
                     f"an option rather than a ref. Fix workspaces/{name}/workspace.json.")
            continue
        # `--` after the ref, so git cannot reinterpret it as a pathspec even if the guard
        # above is ever loosened. (`checkout -- <x>` means the opposite: it forces the
        # PATHSPEC reading, which is why the separator goes after the branch, not before.)
        if _git(["checkout", branch, "--"], cwd=d).returncode == 0:
            _git([*cred, "pull", "--ff-only"], cwd=d)  # latest of the recorded branch
            util.ok(f"  {r['name']} @ {r['branch']}")
            ok += 1
        else:
            util.warn(f"  {r['name']}: couldn't checkout '{r['branch']}'.")
    util.ok(f"Restored {ok}/{len(repos)} repo(s) into '{name}'.")
    return 0


def cmd_workspace_sync(args) -> int:
    """Pull the control plane so you get every engineer's fresh workspace manifests + memory
    BEFORE working — the control plane is the shared metadata store."""
    root = config.ROOT
    https = _origin_https(root)
    if not https:
        util.warn("origin isn't on a forge charter knows (gitlab.com/github.com/…) — "
                  "pull manually.")
        return 0
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=root).stdout.strip()
    p = _git([*_cred_flag(gitpolicy.forge_for(root)), "pull", "--ff-only", https, branch], cwd=root)
    if p.returncode == 0:
        util.ok("Synced — fresh workspace manifests + memory pulled from the control plane.")
        return 0
    util.warn("Pull wasn't fast-forward (local control-plane changes?). Run `charter save` first, then sync.")
    for ln in (p.stderr or "").splitlines()[-3:]:
        util.warn("  " + ln)
    return 1


def cmd_workspace_save(args) -> int:
    """Commit + push THIS workspace's committed metadata (workspace.json + memory/),
    secret-scanned, via the control plane's own forge — the manual counterpart to the
    debounced auto-save."""
    name = getattr(args, "name", None) or workspace.resolve()
    if not workspace.is_live(name):
        util.err(f"workspace '{name}' is LOCAL (private) — nothing is committed. "
                 f"Make it shareable first: charter workspace live {name}")
        return 1
    rel = _ws_meta_paths(name)
    if not rel:
        util.info(f"workspace '{name}' has no manifest/memory to save yet "
                  "(snapshot it or add a memo first).")
        return 0
    msg = getattr(args, "message", None) or f"workspace({name}): manifest + memory"
    return commit_push(config.ROOT, ["add", "--", *rel], msg)


def _ws_meta_paths(name: str) -> list[str]:
    """A LIVE workspace's shareable paths, as repo-relative strings — what `save`, the
    autosave, `live --off` and `rename` hand to git.

    Must name the same set that `workspace._live_block` un-ignores, and nothing but a test
    enforces that, because the two live in different modules. `todos/` was added to the
    gitignore block and not here, so a LIVE workspace's todo list was visible to git and
    staged by nothing — un-ignoring a path only says it *may* be tracked. See
    tests/test_todos_are_committed.py, which pins the two halves together.

    Filtered by existence deliberately: these go to git as literal paths, and `git rm
    --cached` on one that was never tracked fails the whole call — taking the manifest and
    memory down with a workspace that simply had no todos.

    `changes/` is asked a sharper question than the others, because for it the existence
    filter is not a safe proxy for the one being asked. `todos/` is born with its index and
    is never empty afterwards; a `changes/` can be emptied by `charter change forget`, and
    one holding nothing but the never-committed `changes/log/` is the same case with a
    directory in the way. Both are "exists, nothing tracked", which is exactly the shape
    that fails the whole call. `change.has_records` answers what this list means to ask.
    """
    wd = workspace.workspace_dir(name)
    rel = [str(p.relative_to(config.ROOT))
           for p in (wd / "workspace.json", wd / "workspace.md", wd / "memory",
                     wd / "todos") if p.exists()]
    if change.has_records(name):
        rel.append(str((wd / change.DIRNAME).relative_to(config.ROOT)))
    return rel


def _spawn_pushbg(root) -> None:
    """Fire a detached background push of the workspace's just-committed metadata
    (best-effort) so a slow push never blocks the turn — the same mechanism, for the
    same reason, as `planegit._spawn_bg_push` (`discover`'s own background push of
    HEAD). `util.self_relaunch_argv` (#390) is what keeps the child from importing
    whatever `charter/` package happens to sit under *root* instead of the installed
    package — this always runs with cwd set to the control plane root, which for
    anyone developing charter itself IS a checkout with its own `charter/` package."""
    try:
        subprocess.Popen(util.self_relaunch_argv("workspace", "_pushbg"),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL, start_new_session=True, cwd=str(root))
    except Exception:
        pass


def cmd_workspace_autosave(args) -> int:
    """Internal (Stop hook): debounced, secret-scanned auto-save of the active workspace's
    manifest + memory — a reactive, agent-triggered commit, so it honours the control
    plane's declared ``config.MEMORY_SHARE`` posture (default ``local``: never even commits).
    Under ``commit``/``push`` it commits locally (fast, scoped); under ``push`` it also
    pushes in the BACKGROUND, so a slow push never blocks the turn. Best-effort — never
    raises, never blocks."""
    try:
        from . import instance as _instance
        # Re-clamp defensively — see `instance.clamp_share`: `config.MEMORY_SHARE` is
        # always pre-clamped at import time, but this reactive path must not itself rely
        # on that upstream guarantee.
        share = _instance.clamp_share(config.MEMORY_SHARE)
        if share == "local":
            return 0  # the safe default → this workspace memo stays on disk, never committed
        name = workspace.resolve()
        if not workspace.is_live(name):
            return 0  # LOCAL workspace → private, never auto-committed
        rel = _ws_meta_paths(name)
        if not rel:
            return 0
        # #917: `.stdout.strip()` alone made "nothing pending" and "charter could not ask"
        # the same answer, on the path most likely to meet a real lock — this fires at the
        # end of every turn, in the plane root, alongside `_commit_dispatch` and
        # `commit_memory_reactive`, which is the exact contention `hooks._commit_dispatch`
        # takes its own flock to avoid. An unknown state falls THROUGH to `commit_push`
        # rather than returning here, because `commit_push` is now the thing that says why
        # out loud; returning silently is how a memo stops being saved and nobody learns.
        pending = gitstate.read(config.ROOT, *rel)
        if pending.known and not pending.rows:
            return 0  # nothing pending
        marker = config.STATE_DIR / "ws-autosave" / name
        config.private_mkdir(marker.parent)
        if marker.exists() and time.time() - marker.stat().st_mtime < 90:
            return 0  # debounce: at most once per ~90s per workspace
        # commit locally, scoped + secret-scanned (commit_push refuses a secret → rc 1)
        if commit_push(config.ROOT, ["add", "--", *rel],
                       f"workspace({name}): auto-save memo + manifest", no_push=True) != 0:
            return 0
        config.write_for(marker, str(time.time()))
        if share == "push":
            # detached background push — the turn returns immediately
            _spawn_pushbg(config.ROOT)
    except Exception:
        pass
    return 0


def cmd_workspace_pushbg(args) -> int:
    """Internal: push HEAD to the control plane via its own forge's CLI (the background
    half of autosave, and of every reactive `persona remember`).

    **This used to be a second implementation of the push, and that was #373.** It had its
    own rebase-retry, no protected-branch recognition, and ``return 0`` on every failure —
    so on a plane whose default branch requires a pull request, `charter save` landed the
    change on `charter/<sha>` (#167) while a reactive memory commit was rejected, kept, and
    never mentioned again. Eleven commits were stranded on a local `main` in one session,
    each one destroyed by the next ordinary `git reset --hard origin/main`. Delegating is
    the fix: `planegit.push_head` is the only pusher, so the policy holds here by
    construction rather than by keeping two lists of forge signatures in step.

    ``announce=False`` because this runs DETACHED with stdout and stderr on ``/dev/null``
    (`planegit._spawn_bg_push`). Nothing printed here can reach anybody, which is exactly
    why `push_head` records the outcome as well as saying it — `charter doctor` is where
    this process gets to speak.

    Still rc 0 on every outcome: it is spawned from a Stop hook and must never break a
    turn. What changed is that rc 0 is no longer the only thing it leaves behind.
    """
    planegit.push_head(config.ROOT, announce=False)
    return 0


def _scope_note(scope: str) -> str:
    """How far the selection reaches, in the words the reader needs.

    Only a terminal pointer survives closing and reopening Claude. A session-scoped
    selection is gone the moment the session is, and saying so is the whole point: the
    reader who is not told goes looking for a bug the next time the status line says
    `default`.

    **Where a new session starts is `workspace.chosen`'s ladder, not a constant** (#936,
    review round 3). The note named the built-in `default` in two places the ladder does not
    reach it:

    * **Inside a chat.** What `use` writes there is the session pointer and the lock under
      the chat's id, and no terminal pointer (:func:`_terminal_for_selection`). A new chat
      resolves by its own launch record (`workspace.for_frame`), which outranks the terminal
      pointer and the declared default, and a closed chat's session files are reaped with it
      (`frame/state._forget_session`), so a reopened one starts clean. "A new session starts at
      'default'" and "kept across closing/reopening Claude" were both false there. So, until
      review round 4, was "this chat only": a harness that inherited the launching terminal's
      `$TERM_SESSION_ID` wrote that terminal's pointer, and the next launch from it read that.
    * **On a plane with a nominated default** (`charter workspace default`). A new session
      with no pointer and no pane id lands on it, and the note named `default` regardless.
      `commands_persona._scope_note` already reads its plane's default for the same sentence.
    """
    if scope not in ("terminal", "session"):
        return ""
    if workspace.launch_lock():
        return " (this chat only — a new chat starts at the workspace it is opened in)"
    if scope == "terminal":
        return " (this terminal only — kept across closing/reopening Claude)"
    starts = workspace.declared_default() or config.DEFAULT_WORKSPACE
    return (f" (this session only — this terminal reports no pane id, so a new "
            f"session starts at '{starts}')")


def _lock_words(name: str, locked: str | None, *, after_switch: bool = False) -> str:
    """How the lock stands relative to the workspace *name*.

    **Sites that decided this for themselves drifted** (#936, review rounds 2 and 3). `use`
    learned to name a chat's launch lock while `create --use` went on announcing "🔒 locked
    for this session" beside a workspace that was not the lock — measured, `create delta
    --use --force` in a chat launched in `north` said so while `is_locked()` was `north` —
    and `workspace current` carried a third copy. `rename` kept a fourth, "(still 🔒
    locked)", which asked nothing and was measured false in three states: after `use gamma
    --force` in a chat launched in `north`, after SessionStart's reconcile seeded the
    pointer, and after `use` then `unlock`. A lock is one of three things relative to the
    workspace a sentence names: absent, that workspace, or another one.

    **Who asks this, exactly.** Every sentence that reports how the lock stands once a
    workspace command has succeeded: `use` and `create --use` (through
    :func:`_announce_selection`), `current`, and `rename`'s session line. Those four cannot
    answer differently. Four other places name a lock in their own words and are not this
    function's to decide: a refusal names the lock that refused it (:func:`_locked_msg`, and
    `unlock` inside a chat, both read from `workspace.launch_lock` or `workspace.is_locked`);
    `unlock` outside a chat reports the file it just deleted or found absent;
    `commands_frame._pin_workspace` names the lock its own picked launch takes; and
    `harness/codex.py`'s `session-lock` deficit says a Codex shell outside a frame, which no
    per-session id reaches, has no lock at all (it once named a terminal-pane fallback that
    does not exist, #954). `cli.py`'s help and the SessionStart nudge say what confirming a
    workspace does, not what a command just did; the nudge withholds the lock only where
    `session.current()` finds no id AND the harness declares that `session-lock` deficit.

    *after_switch* is for the sentence after a selection that did NOT move the lock (a
    forced pointer inside a chat): there the elsewhere case says what the switch did and did
    not do, where `current`, which switched nothing, only names the lock.
    """
    if not locked:
        return "unlocked"
    if locked == name:
        return "🔒 locked for this session"
    if after_switch:
        return f"this session's commands only; 🔒 still locked to '{locked}'"
    return f"🔒 locked to '{locked}'"


def _terminal_for_selection() -> str | None:
    """The `terminal_id` that `use` and `create --use` hand `workspace.set_active`: ``""``
    inside a chat, and ``None`` (this process's own terminal) everywhere else (#936, review
    round 4).

    **A chat speaks for no terminal.** `set_active` keys its terminal pointer on
    `session.terminal()`, which ranks `$TERM_SESSION_ID` first, and `commands_frame._frame_env`
    strips `TMUX`, `TMUX_PANE` and the size variables and nothing else of that kind. So a
    harness started from Terminal.app or iTerm2 without tmux carries the LAUNCHING terminal's
    id, and a `use` in the chat wrote that terminal's pointer. Measured: after `use gamma
    --force` in a chat, the launching shell's `workspace.chosen()` answered `gamma`, which is
    what `commands_frame._choose_workspace` reads, so the next `charter claude` there opened in
    `gamma` with no picker. An unforced `use` of the chat's own workspace moved it as well.

    Writing none costs the chat nothing: whatever resolves by the chat's id meets its session
    pointer and its launch record before the terminal rung. It is also what makes
    :func:`_scope_note`'s "this chat only" true. `frame/switch.py` hands `persona.set_active`
    the same empty string, for #411's reason: a process inside a frame cannot trust the
    terminal id it inherited.

    **And `persona use` and `persona create --use` ask this too** (#953), through
    `commands_persona._terminal_for_selection`. The persona pointer is keyed on the same
    `session.terminal()`, so a chat wrote it for a recycled pane number or for its launcher,
    and a new chat met it with no launch-record rung to outrank it. Whether this process is a
    chat is one question, and two copies of its answer could drift apart.
    """
    return "" if workspace.launch_lock() else None


def _announce_selection(name: str, scope: str, locked: str | None, *,
                        before: str | None) -> None:
    """Say what a selection DID — the one announcement `use` and `create --use` share.

    Built from what `workspace.set_active` actually wrote (*scope*, as it reports it), the
    lock that stood before the call (*before*) and the lock that stands after it (*locked*),
    never from what the command was asked to do. ADR 0013's rule; each clause below is a
    place the sentence was measured lying:

    * **`none` wrote nothing.** No session id and no pane id means no pointer and no lock,
      and this said "Active workspace set to 'gamma'." while the next command resolved to
      `default`. It warns instead, and names the two routes that need no pointer.
    * **The lock is named by :func:`_lock_words`.** A chat's lock is its launch record, so
      a forced switch moves the chat's commands and not its lock; a shell with no session
      id gets a pointer and no lock at all. Both were told "🔒 locked for this session".
    * **"re-locked to" only where this call moved a lock that stood before it.** The verb
      used to read `--force`, which is what was ASKED. Inside a chat `--force` cannot move
      the lock (review round 1). `create --use --force` in a session that had never been
      locked answered "re-locked to 'beta'" beside a lock that did not exist a moment earlier
      (review round 3). And forcing the workspace the lock already names moves nothing.
    """
    if scope == "none":
        util.warn(f"Nothing was persisted: this process has no session id and no pane id, so "
                  f"there is nowhere to keep '{name}' selected. Pass `--workspace {name}` "
                  f"per command, or set `$CHARTER_WORKSPACE={name}`.")
        return
    verb = "re-locked to" if before and locked != before else "set to"
    util.ok(f"Active workspace {verb} '{name}'{_scope_note(scope)} — "
            f"{_lock_words(name, locked, after_switch=True)}.")


def cmd_workspace_reconcile(args) -> int:
    """Internal (SessionStart hook): seed this Claude session's workspace pointer
    from its terminal pane's selection, so a reopened session resumes its workspace.

    **Keyed on the session the rest of charter resolves by** (#936). This read
    `$CLAUDE_CODE_SESSION_ID`, then the payload's `session_id`, and inside a frame both name
    the HARNESS — while `workspace.chosen` resolves by `session.current()`, which is the
    CHAT's id there (ADR 0019), and `frame/state._forget_session` reaps `<chat id>.*`. So
    the pointer it wrote was read by nothing and reaped by nothing, in the one SessionStart
    workspace question that WRITES. `session.current()` is the question every reader asks;
    the payload stays underneath it for a harness that exports no id at all, which is the
    only case it ever answered.

    **And inside a chat it seeds nothing.** A chat's workspace is its launch record — what
    `workspace.for_frame` resolves and what :func:`workspace.launch_lock` locks it to. The
    pane this would seed FROM is one charter created for the harness, so on a recycled pane
    id the seed is another frame's selection; and a pointer under the chat id outranks the
    launch record in `chosen`, which would move the chat's own commands off the workspace it
    was launched in. Re-keying without this would have replaced an unread write with a
    silent one, which is the failure #936 exists to end.
    """
    if workspace.launch_lock():
        return 0
    sid = session.current()
    if not sid:
        try:
            sid = (json.load(sys.stdin) or {}).get("session_id")
        except Exception:
            sid = None
    workspace.reconcile(session_id=sid)
    return 0


def cmd_workspace_remember(args) -> int:
    """Record one workspace memory as its own timestamp-prefixed file (and index it) — the
    task journal, structured like persona memory (a small explorable DB, not one big log).
    With no text, show the workspace's memories instead. Committed + shared for LIVE."""
    name = getattr(args, "workspace", None) or workspace.resolve()
    text = getattr(args, "text", None) or getattr(args, "message", None)
    if not text:
        return cmd_workspace_recall(args)
    p = workspace.remember(name, text, title=getattr(args, "title", None))
    util.ok(f"Remembered in '{name}' → workspaces/{name}/memory/{p.name}")
    if not workspace.is_live(name):
        util.info(f"  '{name}' is LOCAL (private) — memory stays on disk, not committed. "
                  f"Make it shareable: charter workspace live {name}")
    elif getattr(args, "no_sync", False):
        util.info("  (--no-sync) recorded locally; share later with: charter workspace save.")
    else:  # LIVE + reactive: the memory reaches the shared repo immediately
        rels = [str(p.relative_to(config.ROOT)),
                str(workspace.memory_index(name).relative_to(config.ROOT))]
        commit_memory_reactive(rels, f"workspace({name}): {p.stem}")
    return 0


# `note` is the long-standing verb — keep it as an alias for `remember`.
def cmd_workspace_note(args) -> int:
    return cmd_workspace_remember(args)


#: The two ways a todo stops being open — `done` (finished) and `forget` (abandoned).
#: They are safe as leading words where a `list` subcommand was not (see the docstring
#: below) because each is followed by a SLUG: recording never has a second positional, so
#: "did the user mean to record this?" is answered by the shape of the call, not by
#: guessing at the word. Two states only, and neither is `in_progress` (docs/adr/0006).
_CLOSING_VERBS = ("done", "forget")


def cmd_workspace_todo(args) -> int:
    """Record one **todo** — something this task still means to do — list them, or close one.

    Shaped like `remember`: the verb with text records, the verb bare lists. A literal
    `todo list` subcommand would be indistinguishable from recording a todo whose text is
    "list", which is a real thing somebody will eventually try to write down.

    Intent is not memory (docs/adr/0004): a todo stops being true the moment it is done,
    so it lives in its own store and never surfaces from `charter recall`.
    """
    from . import todos
    name = getattr(args, "workspace", None) or workspace.resolve()
    text = (getattr(args, "text", None) or "").strip()
    slug = (getattr(args, "slug", None) or "").strip()
    query = getattr(args, "query", None)

    if text in _CLOSING_VERBS:
        if not slug:
            # Falling through to the recording path here would record a todo whose text is
            # "done" — a silent wrong action in answer to an obvious slip, and one nobody
            # could act on later. Ask for the missing half instead.
            util.err(f"`todo {text}` needs the slug of the todo to close.")
            util.info(f"  The slug is the first column: charter ws todo --workspace {name}")
            # Issue #59: the reserved words swallow a todo you genuinely wanted to record
            # under that name. The escape already existed — matching is exact and
            # lowercase, so any other capitalisation records — but nothing said so, which
            # made a recoverable slip look like a wall.
            util.info(f"  To record a todo actually called \"{text}\", capitalise it or "
                      f"add a word: charter ws todo \"{text.capitalize()} …\"")
            return 1
        return _close_todo(name, slug, journal=(text == "done"))

    if not text:
        return _list_todos(name, query)

    # Duplicate intent is worse than duplicate memory: closing one of a near-identical
    # pair leaves its twin looking outstanding, so the list starts lying about what is
    # left. Warn and skip rather than merge, so the writer learns it is already there.
    dup = todos.duplicate_of(name, text)
    if dup:
        # Contained for `_list_todos`' reason, one surface over: the title named here is a
        # stored one, and since `charter handoff` a stored title can be a model's prose.
        util.err(f"already on the list: {contain.one_line(dup)}")
        util.info(f"  See it: charter ws todo --workspace {name}")
        return 1

    p = todos.add(name, text)
    util.ok(f"Todo recorded in '{name}' → workspaces/{name}/todos/{p.name}")
    if not workspace.is_live(name):
        util.info(f"  '{name}' is LOCAL (private) — todos stay on disk, not committed.")
    return 0


def _close_todo(name: str, slug: str, *, journal: bool) -> int:
    """Close one todo: **delete** it, leaving a journal entry (`done`) or nothing (`forget`).

    Closing deletes rather than marking done because the journal is already the permanent
    record of what happened — keeping closed todos would build a second one that every read
    then has to filter past, and a store whose reads all begin with a filter is a store that
    will eventually be read without it.

    Which makes the journal entry the load-bearing half, not a courtesy. An agent may close
    todos it recorded itself, so without a trace outside the list it could create and tick
    off work unobserved and the list would always read as finished — worse than no list,
    because it would be confidently wrong. `forget` has no trace precisely because it claims
    nothing happened.

    Journalling happens BEFORE the delete: the entry is the only surviving evidence, so it
    is written while the todo is still there to name. Both halves resolve through the
    workspace's own todo directory, which is what keeps one workspace from closing another's
    work.

    **That last sentence used to claim more than the code did** (#339). `memstore.resolve`
    applies no containment, and every workspace's `todos/` lives under the same data root,
    so `../../<other>/todos/<slug>` resolved to a NEIGHBOUR's file and `unlink` took it —
    `contain.file_refusal` had nothing to object to, because the target really is plane
    data. The reachable input is argv rather than a committed file, so this was never a
    finding; the comment was load-bearing anyway, and one `segment_ok` is cheaper than
    softening it. A slug names one entry in this workspace's own directory or it names
    nothing.
    """
    from . import contain, memstore, todos
    if not contain.segment_ok(slug):
        util.err(contain.refusal(slug))
        util.info(f"  List the real ones: charter ws todo --workspace {name}")
        return 1
    d = todos.todos_dir(name)
    p = memstore.resolve(d, slug)
    if p is None:
        util.err(f"no todo '{slug}' in workspace '{name}'.")
        util.info(f"  List the real ones: charter ws todo --workspace {name}")
        return 1
    # Ask the store for the title rather than re-parsing the file here: `open_todos` already
    # decides what a todo is called, and two answers to that would eventually disagree.
    title = next((t["title"] for t in todos.open_todos(name) if t["slug"] == p.stem), p.stem)

    if journal:
        # Through the normal note path, so a LIVE workspace shares this entry exactly like
        # every other journal entry. A trace that stays on disk while the rest of the
        # journal is shared is a weaker trace than the argument above needs.
        cmd_workspace_remember(SimpleNamespace(
            workspace=name, text=f"Closed todo: {title}", title=None, no_sync=False))

    memstore.forget(d, p.name)  # drops the file AND its index line — no residue either side
    if journal:
        util.ok(f"Closed '{title}' in '{name}' — the journal has the trace.")
    else:
        util.ok(f"Dropped '{title}' from '{name}' — abandoned, so nothing was journalled.")
    return 0


def _list_todos(name: str, query: str | None) -> int:
    """Open todos, oldest first — the ranking the whole feature uses.

    **Every title goes through `contain.one_line` on the way to the terminal**, both here
    and on the `--query` path. These rows are ``  <slug>  <age>  <title>``, charter's own
    format with structure in it, and a title carrying `\\n` writes a second row that looks
    exactly as much like charter's output as the first (#453's mechanism).

    Pre-existing rows, and what changed is who writes the title: until `charter handoff` a
    todo's title was typed by the operator, and it is now the first line of a brief a MODEL
    wrote. Escaped at the render and never on the way into storage — the file a person
    opens must still hold the text they approved.
    """
    from . import todos
    if query:
        hits = todos.search(name, query)
        if not hits:
            util.info(f"No todos in '{name}' match {query!r}.")
            return 0
        for p, title, _score in hits:
            print(f"  {p.stem}  {contain.one_line(title)}")
        return 0

    open_ = todos.open_todos(name)
    if not open_:
        # Silence is indistinguishable from a broken command, so say it plainly.
        util.info(f"No open todos in '{name}'. Record one: charter ws todo \"<what>\"")
        return 0

    for t in open_:
        print(f"  {t['slug']}  {t['age_days']}d  {contain.one_line(t['title'])}")
    return 0


def cmd_workspace_recall(args) -> int:
    """Search this workspace's memories (--query) or list them all chronologically.

    A memory directory it could not read is named, and neither "no memories match" nor "no
    memories yet" is said over it (#1084)."""
    name = getattr(args, "workspace", None) or workspace.resolve()
    query = getattr(args, "query", None)
    unread: list = []
    results = workspace.recall(name, query, unread=unread)
    workspace.say_unread(unread)
    if unread:
        return 0          # its one directory: nothing was read, and the sentence said so
    if not results:
        if query:
            util.info(f"No memories in '{name}' match '{query}'.")
        else:
            util.info(f"workspace '{name}' has no memories yet. "
                      f'Add one: charter workspace remember "<text>"')
        return 0
    for p, title, score in results:
        tag = f"  ({score})" if score else ""
        print(f"  • {title}{tag}  [{p.name}]")
    util.info(f"{len(results)} memory(ies) in workspaces/{name}/memory/ — "
              f"read one: cat workspaces/{name}/memory/<file>")
    return 0


def cmd_workspace_forget(args) -> int:
    """Delete one workspace memory by slug or filename (and drop its index line)."""
    name = getattr(args, "workspace", None) or workspace.resolve()
    if workspace.forget_memory(name, args.slug):
        util.ok(f"Forgot '{args.slug}' from workspace '{name}'.")
        # Symmetric with `remember` — see `cmd_persona_forget` for why the directory,
        # not the deleted file, is what gets staged (#82).
        commit_memory_reactive([str(workspace.memory_dir(name).relative_to(config.ROOT))],
                               f"workspace({name}): forget {args.slug}")
        return 0
    util.err(f"no memory '{args.slug}' in workspace '{name}' (list them: charter workspace recall).")
    return 1


def cmd_workspace_vision(args) -> int:
    """Show or set the workspace's Vision — the north star in its living charter
    (workspaces/<name>/workspace.md). With text, replace the Vision; without, print
    it (and the charter path). The rest of the charter — Context & decisions, Glossary
    — is edited directly in workspace.md as the work evolves."""
    name = getattr(args, "workspace", None) or workspace.resolve()
    if not workspace.workspace_dir(name).exists():
        util.err(f"no workspace '{name}'")
        return 1
    text = getattr(args, "text", None)
    if text:
        workspace.set_vision(name, text)
        util.ok(f"Vision set for '{name}' → workspaces/{name}/workspace.md")
        return 0
    vision = workspace.read_vision(name)
    if vision:
        print(vision)
    else:
        util.info(f"workspace '{name}' has no vision yet. Set it: "
                  f'charter workspace vision "<the goal>"')
    util.info(f"Full charter: workspaces/{name}/workspace.md "
              "(Vision · Context & decisions · Glossary — edit it as the work evolves).")
    return 0


def cmd_workspace_fork(args) -> int:
    """Fork a workspace: create <new> pre-loaded with <src>'s context — the living
    charter (workspace.md: vision, context, glossary), the manifest (repos+branches),
    the task memo, and the open todos — so you can branch off and continue with full
    context. The repo clones are not copied (they're reconstructible): pass --restore to
    clone them from the manifest, or `charter clone` on demand. Starts LOCAL unless --live."""
    from . import todos
    src, new = args.src, args.new
    if not workspace.valid_name(new):
        util.err(f"invalid workspace name '{new}' (use lowercase letters, digits, . _ -)")
        return 1
    if src == new:
        util.err("source and fork names are the same — nothing to fork.")
        return 1
    if not workspace.workspace_dir(src).exists():
        util.err(f"no workspace '{src}'")
        return 1
    if workspace.workspace_dir(new).exists():
        util.err(f"workspace '{new}' already exists — pick another name or remove it first.")
        return 1

    workspace.ensure(new)
    workspace.scaffold(new)  # baseline; the charter is overwritten from src below
    src_charter = workspace.charter_file(src)
    if src_charter.exists():
        shutil.copyfile(src_charter, workspace.charter_file(new))
    src_mem = workspace.memory_dir(src)
    if src_mem.exists():
        shutil.copytree(src_mem, workspace.memory_dir(new), dirs_exist_ok=True)
    # Open todos travel with the memory, and for the same reason: a fork exists so someone
    # can pick the task up with full context, and what is still to be done is the most
    # actionable part of that. Inheriting everything the task LEARNED while dropping
    # everything it still INTENDED leaves the fork re-deriving the plan — the exact problem
    # todos were built to end.
    #
    # A COPY, so the two lists diverge from here: closing one in the fork must not rewrite
    # the source's plan. Copied wholesale (files + index) rather than re-added one by one,
    # which would restamp every todo with today's date and hide a three-week-old intent
    # behind a fresh one — age is the only ranking this feature has. Closed todos never
    # arise, since finishing one deletes it.
    src_todos = todos.todos_dir(src)
    if src_todos.exists():
        shutil.copytree(src_todos, todos.todos_dir(new), dirs_exist_ok=True)
    # Membership comes from BOTH sources — see `workspace.merge_repo_rows`. Reading the
    # manifest alone made a fork of an un-snapshotted workspace inherit nothing while
    # `status` cheerfully reported its clones (#81).
    m = workspace.read_manifest(src)
    disk = [{"name": d.name, "branch": _repo_branch(d)} for d in workspace.clones(src)]
    repos, disk_only = workspace.merge_repo_rows(m.get("repos") or [], disk)
    if repos or m:
        m["name"] = new
        m["forked_from"] = src
        m["repos"] = repos
        m.setdefault("description", "")
        m["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        m["updated_by"] = _git_user()
        workspace.write_manifest(new, m)
    workspace.note(new, f"Forked from '{src}' — inherited its vision, context, glossary, and memo.")

    if getattr(args, "live", False):
        workspace.set_live(new, True)
    util.ok(f"Forked '{src}' → '{new}' — charter + context + memo copied "
            f"({'LIVE' if getattr(args, 'live', False) else 'LOCAL'}).")
    inherited = todos.count_open(new)
    if inherited:
        # Said out loud because the two lists are independent from here: whoever forked
        # needs to know they now own a second copy of this intent, not a view of the first.
        util.info(f"Inherited {inherited} open todo(s) from '{src}' — the fork's own list "
                  f"now: charter ws todo --workspace {new}")
    # Say which source each repo came from. A snapshot promises its branch was pushed;
    # a clone found on disk promises only that it is checked out here right now, and
    # `restore` on another machine will fail on a branch that was never pushed. Reporting
    # it at the moment of use beats a drift warning that would fire on every workspace
    # nobody has snapshotted — which is most of them, by design.
    if disk_only:
        util.info(f"  {len(disk_only)} of them come from clones on disk, not from a "
                  f"snapshot ({', '.join(disk_only)}) — their branch is whatever is "
                  f"checked out now, which may not be pushed. `charter workspace "
                  f"snapshot {src}` records them properly.")
    if getattr(args, "restore", False) and repos:
        util.info(f"Cloning {len(repos)} inherited repo(s)…")
        return cmd_workspace_restore(SimpleNamespace(name=new, on_demand=False))
    if repos:
        util.info(f"Clone its {len(repos)} inherited repo(s): charter workspace restore {new}  "
                  f"(or re-run fork with --restore).")
    else:
        util.info(f"No repos on '{src}' — neither a snapshot nor clones on disk. "
                  f"Clone into the fork: charter clone <repo> -w {new}")
    if getattr(args, "live", False):
        util.info(f"Share the fork: charter workspace save {new}")
    return 0


#: Baseline components a LIVE workspace actually shares (see the managed block in
#: .gitignore that `workspace live` writes). A workspace's refs/ and its structure
#: marker stay local, so restoring only those gives `save` nothing to commit.
#:
#: `workspace.json` joined the baseline with #884, and it belongs here rather than only in
#: `_required_components`: it is the FIRST path in the managed LIVE block, so a backfill
#: that healed it and then said nothing would leave the manifest this whole change exists
#: to share sitting uncommitted on one machine.
_LIVE_SHARED_COMPONENTS = {"workspace.md", "workspace.json", "memory/MEMORY.md"}


def cmd_workspace_reinit(args) -> int:
    """Bring a workspace's on-disk structure up to the current layout — create any missing
    baseline files (workspace.md charter, memory/, refs/) and stamp the structure version.
    A workspace created by an older version of charter is flagged (status line,
    `workspace list`) until this runs. Idempotent + additive: existing content is never
    touched. `--all` fixes every workspace at once (handy after a charter upgrade)."""
    #: Workspaces `--all` could not look at, named here and counted in the closing line (#1028).
    #: `list_workspaces` leaves a directory that is a symlink loop out, so the walk below never
    #: met it and the line under it said "Up to date — nothing to do" about the whole plane.
    unseen: list[tuple[str, int | None]] = []
    if getattr(args, "all", False):
        # One listing for what it walks and what it names (#1043), said in the sentence every
        # command that lists workspaces now says it in.
        names, unread = workspace.read_workspaces_aloud()
        unseen = [(d.name, code) for d, code in unread]
    else:
        name = getattr(args, "name", None) or workspace.resolve()
        # Asked with `workspace._existence` (#942 review round 4, minor 2's class): `Path.exists`
        # called an EIO "no workspace", and raised instead on 3.11–3.13. The errno is kept (#1028):
        # `_exists` dropped it, and this sentence told a workspace that is a symlink loop to
        # restore read access, which clears no loop.
        there, code = workspace._existence(workspace.workspace_dir(name), follow=True)
        if there is None:
            util.err(workspace.cannot_check_workspace(name, code))
            return 1
        if there is False:
            util.err(f"no workspace '{name}'")
            return 1
        names = [name]
    if not names and not unseen:
        util.info("No workspaces to reinitialize.")
        return 0
    #: How many individual repairs were applied, and WHICH workspaces got at least one.
    #: Two counters because they are two units, and #876 is what one counter cost: a
    #: workspace can need several repairs — the harness layer is a row per file, the
    #: structure bump is another — so a single `healed` incremented per repair and then
    #: printed against `len(names)` said *"Healed 32 of 17 workspace(s); the rest were
    #: current."* on a 17-workspace plane. A numerator above its own denominator, and a
    #: "rest" that is negative, in the one line an operator reads to confirm a bulk
    #: mutation landed.
    #:
    #: `repaired` is a SET OF NAMES drawn from `names`, and that is the fix rather than a
    #: subtraction that happens to come out right: `len(repaired) <= len(names)` holds
    #: because a set of members of `names` cannot be bigger than `names`, so no arithmetic
    #: below is in a position to state a count greater than the total. The per-repair
    #: number is not thrown away — it is named as what it is.
    repairs = 0
    repaired: set[str] = set()
    #: Workspaces whose manifest `reinit` was asked for and could not write. Kept apart
    #: from `repaired` so the closing line does not say "nothing to do" — or, worse,
    #: "the rest were current" — over an error two lines above it. A repair command that
    #: contradicts itself is one nobody trusts the next time.
    blocked: set[str] = set()
    #: Workspaces left holding a state a row names and `reinit` cannot clear: a file charter did
    #: not write, one the harness keeps, one it cannot read or write, a record it cannot publish
    #: (#942 review round 5, R4). "Up to date — nothing to do" printed beside one of them told the
    #: operator the plane's rules were in force where they were not.
    unresolved: set[str] = set()
    for n in names:
        before = workspace.reinit(n)
        # The HARNESS LAYER, reported as its own line rather than folded into the
        # structure one (#850). It is a separate fact — a workspace whose layout is
        # current can still hold a `.claude/settings.json` generated before the plane's
        # own settings moved — and it is the one this command silently repaired while
        # printing "nothing to do" until it was said out loud.
        #
        # Subscripted, not `.get("layer") or ()`. The fallback was defending against a
        # shape charter itself builds one function away: `workspace.reinit` sets `layer`
        # unconditionally, before its own first return, so no call can hand this loop a
        # dict without it. The deletion sweep found the `or ()` as a survivor and there
        # was no test to write — a fixture would have had to stub `reinit` into returning
        # something `reinit` cannot return. `h.workspace_files() or {}` one module over
        # keeps its fallback for the opposite reason and that is the distinction: that
        # one guards a THIRD PARTY's answer, and a harness charter did not write can
        # return anything at all.
        for rel, did in before["layer"]:
            inside = workspace.checkout_row(n, rel)
            if did in ("foreign", "blocked", "harness-behind", "unreadable", "unrecorded",
                       "unhidden", "unlisted"):
                unresolved.add(n)
            if did == "foreign" and inside:
                # Never "remove it" in a checkout (review round 5, R2 and R5): the file is
                # somebody's own in their own repository and stays hidden while it is there, so
                # the one thing to say is how to commit it on purpose.
                util.warn(f"'{n}': {rel} holds content charter did not write — left completely "
                          f"untouched, and hidden in that checkout while it is there; if this is "
                          f"your own file and you mean to commit it: git add -f {inside[1]}")
            elif did == "foreign":
                # No removal advice here either (#942 final review, R5): `doctor` says a foreign
                # file stays exactly as it is, and one command may not advise what the other rules
                # out.
                util.warn(f"'{n}': {rel} was not written by charter — left completely "
                          f"untouched; charter never overwrites it.")
            elif did == "blocked":
                util.err(f"'{n}': {rel} could not be written — something is in the way at "
                         f"that path. charter never deletes or renames existing content.")
            elif did == "removed":
                # Its own sentence rather than the ternary below, which would call a
                # deletion "refreshed". A removal is the one repair here whose CAUSE the
                # operator cannot see in the workspace — the plane stopped declaring it —
                # so the row has to carry it (#942).
                repairs += 1
                repaired.add(n)
                util.ok(f"Reinitialized '{n}' → removed {rel} — the plane no longer "
                        f"declares it (charter's harness layer).")
            elif did == "withheld":
                # A sentence of its own: nothing is in the way at that path, so `blocked`'s
                # wording would send the operator looking for an obstruction that is not
                # there. What stopped the write is that the file could not be hidden.
                util.err(f"'{n}': {rel} was not written — charter could not hide it in that "
                         f"checkout's .git/info/exclude, and a machine-local file it cannot "
                         f"hide would be committable there.")
            elif did == "harness-behind":
                # Not "foreign" and never "remove it": the approvals in that file are the
                # harness's own, and deleting it to get charter's copy back destroys them.
                # True of a file charter never wrote, and of its own write whose record is gone.
                util.warn(f"'{n}': {rel} is a file charter cannot vouch for as its own write, and "
                          f"the harness saves its approvals into that file, so charter does not "
                          f"rewrite it: the plane's machine-local rules it lacks are not in force "
                          f"there.")
            elif did == "unreadable":
                # A generated path charter cannot read (#942, review rounds 2 and 3). Not
                # `foreign`'s "remove it", and not "until it can be read" either: once readable a
                # harness-edited file is `harness-behind` and never receives the rule.
                util.warn(f"'{n}': {rel} cannot be read — left exactly as it is; charter writes "
                          f"there again only if that file turns out to be exactly what charter "
                          f"last wrote.")
            elif did == "unlisted":
                # #1072: every worktree of that clone went unchecked, and "nothing to do" printed
                # over them. Not a repair either, and not one `reinit` can make.
                util.warn(f"'{n}': git could not list the worktrees of "
                          f"{workspace.checkout_label(n, inside[0])}, so none of them was checked "
                          f"or given charter's layer; {workspace.unlisted_fix(inside[0])}.")
            elif did == "unhidden":
                # #1072: a line left out of a shared exclude because it would hide a file of yours
                # in another checkout reading it. Not a repair — the fall-through below would call
                # it "wrote .git/info/exclude" — and not one `reinit` can make: the file is yours
                # to commit or move, and `workspace.unhidden` names it.
                util.warn(f"'{n}': {rel} does not hide all of charter's files in that checkout — "
                          + "; ".join(workspace.unhidden(inside[0])) + ".")
            elif did == "unrecorded":
                # Ruling H (#942 review round 4): a write charter could not record first is not
                # made, and the lines stay. Not `blocked`: nothing is in the way at that path. With
                # the errno the publish failed with (review round 5, R5).
                refused = workspace.unrecorded_fix(inside[0], "that checkout")
                util.warn(f"'{n}': {rel} — charter could not publish its record there first, so "
                          f"it wrote nothing and kept every exclude line it had"
                          f"{f'; {refused}' if refused else ''}.")
            else:
                repairs += 1
                repaired.add(n)
                util.ok(f"Reinitialized '{n}' → "
                        f"{'wrote' if did == 'created' else 'refreshed'} {rel} "
                        f"(charter's harness layer).")
        for rel, path, code in before["unreadable"]:
            # ADR 0009 (#942 final review): a baseline file charter cannot check is named with what
            # clears it, and `scaffold` writes nothing over it. It was a traceback out of this
            # command, on every interpreter, for a workspace `refs/` at mode 000.
            #
            # What clears it is the errno's, not one sentence for every cause: `doctor` and
            # `gitpolicy` took that split in the closing verification and this said "restore read
            # access" for a symlink loop, which no permission bit is in the way of. One function
            # words both, so the two commands cannot differ about one path.
            unresolved.add(n)
            util.warn(f"'{n}': {rel} cannot be checked — charter writes nothing there it cannot "
                      f"see; {workspace.uncheckable_fix(code, path, 'that path')}.")
        for rel, path, code in before["in_the_way"]:
            # #1028: the other shapes a directory of the layout takes when it is no directory. Each
            # was a `FileExistsError` out of this command, and "added" would be as wrong: `scaffold`
            # creates nothing beneath either, and removes neither, so the row says which one was
            # found and the repair that is the operator's to make.
            unresolved.add(n)
            if code == errno.ENOENT:
                fix = ("is a symlink whose target is not there, and charter writes nothing "
                       "through it; removing or repointing that link clears this")
            elif code == errno.ENOTDIR:
                fix = ("is not a directory, and charter never moves existing content; moving it "
                       "out of the way clears this")
            elif code == errno.ELOOP:
                # #1037: a link charter will not follow — where the file itself belongs, wherever
                # it points, or where a directory belongs and it does not land on one inside the
                # plane. Never "repoint it" for a file: no target makes a file link one charter
                # writes through. What it becomes is what the layout has at that path.
                real = "file" if path == workspace.workspace_dir(n) / rel else "directory"
                fix = (f"is a symlink, and charter writes nothing through one; replacing it with "
                       f"a real {real} clears this")
            else:
                # #1074: the structure stamp as a directory, a FIFO or any other file that is not a
                # regular one. The stamp's write refuses each and its read no longer opens one, so
                # it is #1028's sentence for a file-shaped path.
                fix = ("is not a regular file, and charter never moves existing content; moving it "
                       "out of the way clears this")
            # The stamp is written over, not created, when it is there: "could not be written" is
            # what happened to it, and it is the sentence the version line below gives way to.
            did = ("could not be written" if rel == workspace._STRUCTURE_MARKER
                   else "cannot be created")
            util.warn(f"'{n}': {rel} {did} — {path} {fix}.")
        # The BACKFILL half of #884, and the reason it is checked after rather than read
        # off `before`: `workspace.scaffold_manifest` swallows its own failure, because it
        # runs from `ensure` on a launch path where raising would cost the operator their
        # tab. That is the right trade there and it costs this command its honesty unless
        # the file is looked at again — "added workspace.json" printed over a manifest that
        # is not there is exactly the tick that stops somebody checking.
        #
        # The absence is the whole test, and the `"workspace.json" in before["missing"]`
        # half this started with is gone: `structure_status` derives `missing` from the
        # same `exists()`, so before `scaffold` runs the two always agree, and after it the
        # only way the file is still absent is that this call could not write it. The
        # sweep found the conjunct as a survivor and it was right — an equivalent mutant
        # and dead code are one finding.
        there = workspace._exists(workspace.manifest_path(n), follow=True)
        if "workspace.json" in {rel for rel, _path, _code in before["in_the_way"]}:
            # Named by its `in_the_way` row above, and not written by `scaffold`, which is not a
            # write that failed (#1037): "could not be written" beside that row said one link twice
            # in two sentences, and counted the workspace as a repair that went wrong.
            pass
        elif there is None:
            # Not "could not be written" (#942 review round 4, minor 2's class): an lstat that
            # fails proves nothing about the file, and that sentence sends somebody to fix a write.
            util.warn(f"'{n}': workspace.json cannot be checked — charter cannot say whether it "
                      f"is there; restoring read access to it clears this.")
        elif there is False:
            blocked.add(n)
            before["missing"] = [m for m in before["missing"] if m != "workspace.json"]
            before["ok"] = not before["missing"] and before["version"] >= before["target"]
            util.err(f"'{n}': workspace.json could not be written — something is in the "
                     f"way at that path. charter never deletes or renames existing content.")
        # The stamp, looked at again for the manifest's reason (#1074, ADR 0013): `scaffold`
        # swallows a refused stamp write, and "added structure v0 → v5" printed over one that was
        # not written — then again on the next run, since the workspace still read as stale. Only
        # a stamp that now reads current is reported as added; one a row above names is left to
        # that row, and one refused for a reason no row names gets this sentence.
        #
        # The read-back alone decides, with no `before["version"] < target` beside it: CI's sweep
        # left that conjunct, and `<=` for its `<`, as survivors, and they were right. A stamp that
        # read current before `scaffold` reads current after it — rewritten with the target, or
        # refused and left as it was — and a write that raises ends this command, so no input
        # tells the conjunct from its absence. The pins on both sides of the boundary are the
        # tests beside #1074's.
        after = workspace.structure_version(n)
        if after < before["target"]:
            unresolved.add(n)
            if workspace._STRUCTURE_MARKER not in {rel for rel, _path, _code in before["in_the_way"]}:
                util.warn(f"'{n}': {workspace._STRUCTURE_MARKER} could not be written, so this "
                          f"workspace still reads as structure v{after} and stays flagged for "
                          f"reinit.")
            before["ok"] = not before["missing"]   # files it did add are still reported
        if before["ok"]:
            continue
        repairs += 1
        repaired.add(n)
        what = (", ".join(before["missing"]) if before["missing"]
                else f"structure v{before['version']} → v{before['target']}")
        util.ok(f"Reinitialized '{n}' → added {what}.")
        # Only advise `save` when something LIVE actually shares was restored. A
        # workspace's refs/ and its structure marker are gitignored, so healing
        # only those leaves nothing to commit and the advice sends you to a
        # command that prints "Nothing to save".
        if workspace.is_live(n) and set(before["missing"]) & _LIVE_SHARED_COMPONENTS:
            util.info(f"  '{n}' is LIVE — commit the restored files: charter workspace save {n}")
    if not repaired and not blocked and not unresolved and not unseen:
        util.ok(f"Up to date (structure v{workspace.STRUCTURE_VERSION}) — nothing to do.")
    elif len(names) + len(unseen) > 1:
        # Two units, named as two. "Applied N repair(s)" is the number the per-workspace
        # rows above add up to; "across M of T workspace(s)" is the number an operator is
        # actually checking against the plane they know the size of. A workspace charter
        # could not repair is called out rather than swept into "the rest were current",
        # which would contradict the error it just printed — and so is one still holding a
        # state a row above names (review round 5, R4), and one it could not look at, which
        # is in T because the operator counts it there and is in none of "the rest" (#1028).
        stuck = f"{len(blocked)} could not be repaired; " if blocked else ""
        left = unresolved - repaired - blocked
        kept = f"{len(left)} still hold what the rows above name; " if left else ""
        unchecked = f"{len(unseen)} could not be checked; " if unseen else ""
        util.info(f"Applied {repairs} repair(s) across {len(repaired)} of "
                  f"{len(names) + len(unseen)} workspace(s); {stuck}{kept}{unchecked}the rest "
                  f"were current.")
    return 0


def _warn_env_override(name: str) -> None:
    # The name resolution ranks, not the raw variable: a blank one outranks nothing, and
    # warning that `' '` takes precedence sent the operator to a variable that was not
    # deciding (#1055). The name is bounded to one line because it comes out of a shell, and
    # a line separator in it would write a line of this output that charter did not.
    env = workspace.from_environment()
    if env and env != name:
        shown = contain.one_line(env)
        util.warn(
            f"$CHARTER_WORKSPACE='{shown}' is set and takes precedence — commands in this "
            f"session will still act on '{shown}', not '{name}'."
        )
