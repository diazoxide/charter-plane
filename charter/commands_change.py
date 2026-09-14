"""`charter change` — the cross-repo change: the record, and what charter does with it.

Nine verbs over :mod:`charter.change`, and they divide by what they touch rather than by
what they are called.

**Six reach nothing at all** — ``create``, ``add``, ``drop``, ``list``, ``forget`` and the
record half of ``show``: a file read, a file write, a directory listing.

**Two more reach git, in a clone the operator already has** — ``revert`` and the divergence
report. No socket, no forge CLI.

**Three act on a remote with the operator's own credential** — ``push``, ``land``, and
``show``'s derived columns. The line between those halves is drawn again, in a section
comment, at the point where it is crossed.

**Nothing derived is ever written back.** ``show``'s request numbers, check states and
landing dates are a reading taken at one moment and thrown away; the record on disk holds no
request number, no CI result, no branch position and no ``landed`` flag, so nothing on disk
can disagree with git — because nothing on disk claims to know.

**Membership is enumerated by hand, and that is the containment property.** There is no
glob, no pattern, no ``--all-repos``, no "every repo in the workspace", and nothing here
calls ``inventory.list_repos``. Every member in a record was typed by somebody, and a member
must resolve to a clone the operator already put in this workspace — so the reach of a
change is bounded by what is already on the disk in front of you, and by nothing that
travelled in a committed file. A record can name a repository you do not have; it is refused
for that, by name, and it can never name a *place*.

**What this module will not do, in a change action, including during a revert** (§3.7):
force-push to any branch; delete any branch, merged or not; ``reset --hard`` a default
branch; or close a request charter did not open. Those are not absent by oversight and
they are not guarded by a flag — the argv is never constructed, and
`tests/test_change_revert.py` records every git invocation a revert makes and asserts it.
An emergency is exactly when somebody reaches for one of them, and a force-push over three
default branches leaves a world where the change happened, was undone, and no repository's
history mentions either — the failure the whole design exists to prevent.

**A branch out of a record is argv, and ref grammar is not argv safety.** Every git call
below that carries one spells it ``refs/heads/<branch>``, which cannot begin with ``-``
whatever the record says — `git check-ref-format` **accepts** ``refs/heads/-b`` (measured
on git 2.50.1), so the grammar answers a different question. That is the positional half;
`change.branch_refusal` at the record boundary is the other, and neither substitutes for
the other. It is spelled this way rather than with a trailing ``--`` because the commands
that need it — `merge-base --is-ancestor`, `rev-parse --verify` — take no ``--`` at all,
and a separator that is not accepted is a guard that is not there.
"""

from __future__ import annotations

import datetime
import json
import os
import re
from pathlib import Path

from . import (change, config, contain, instance, pieces, trace, tui, util,
               workspace)
from .forge import base as forgebase, registry

#: Exit code for a **named refusal** — the request was understood and charter will not do
#: it — as distinct from the generic 1 that means something went wrong. `commands_worktree`
#: spends its 2 the same way (``CLAIM_TAKEN``) and for the same reason: a caller must not
#: have to parse English to tell "you asked for something I refuse" from "the disk is full".
#:
#: Four conditions share the code and **none shares a message**: a repo with no clone, a
#: change that does not exist, a member added twice, and an ordering that cannot be true.
#: Three gates in sequence mask each other, and an exit-code assertion cannot tell them
#: apart — so every refusal test here asserts *which* one fired.
REFUSED = 2

#: How long one read-only git question may take. `doctor.CHECK_TIMEOUT`'s reason, one
#: command out: a clone on a stalled network mount makes git hang, and a command the
#: operator is waiting on must fail rather than sit there.
GIT_TIMEOUT = 20

#: What a merge sha read out of the landing log must look like before it reaches git.
#:
#: **The log is a file, so it is untrusted for the same reason the record is.** It is
#: never committed, which makes it *local* rather than *trustworthy* — a hand edit, a
#: half-written line from a killed process, or an older charter all reach here — and the
#: value is handed to `git revert` and `git rev-list` as argv, where ``-X`` is a flag.
#: Anchored at both ends and hexadecimal, which is what a sha is; anything else is refused
#: by name rather than repaired, because a sha charter repaired is a commit nobody chose.
#:
#: **Asked with `fullmatch`, and the `^…$` is kept anyway.** Python's ``$`` matches at the
#: end of the string *or just before a trailing newline*, so `.match` would admit
#: ``"e0c9d13\n"`` — a value with a newline in it on its way to a git argv, which is the
#: class `tests/test_the_end_of_a_name_is_the_end_of_the_string.py` exists for. The anchors
#: are redundant under `fullmatch` and are load-bearing for something else: that test builds
#: its inventory by FINDING anchored constants, and unanchoring this would silently drop it
#: out of the table (#629).
_SHA_RE = re.compile(r"^[0-9a-f]{7,64}$")

#: The prefix of the branch a revert is seeded on. The revert is an ordinary change with an
#: ordinary name, so its branch is `change.default_branch` of its own slug — this exists
#: only to build that slug, and it is a constant so the record and the report cannot spell
#: it two ways.
REVERT_PREFIX = "revert-"


def _workspace(args) -> str:
    ws = workspace.resolve(getattr(args, "workspace", None))
    workspace.banner(ws, getattr(args, "workspace", None))
    return ws


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _author() -> str:
    """Who is recorded as having created this change.

    First line only, and contained: the value comes out of ``git config``, which is a file
    on this machine that charter did not write, and it lands in a record that a LIVE
    workspace commits and that every ``show`` prints back.
    """
    out = util.run(["git", "config", "user.name"], check=False).stdout or ""
    name = contain.one_line((out.splitlines() or [""])[0].strip())
    return name or os.environ.get("USER") or "unknown"


def _why(args, tail: str) -> str | None:
    """The ``--why`` this command was given, or ``None`` with the refusal printed.

    Two checks, and argparse can make neither. ``required=True`` cannot see ``--why ""``,
    and it cannot see a newline — which is the one that matters, because this value is
    repeated back on report rows and, later, written into pull request bodies where a
    newline forges a second row. A ``why`` that cannot be one line is prose, and prose
    belongs in ``workspace.md``.
    """
    why = (getattr(args, "why", None) or "").strip()
    if not why:
        util.err(f"--why is required: one line saying {tail}.")
        return None
    # `change.TEXT_LIMIT`, not `contain`'s row budget: the record's own bound and this one
    # have to be the same number, or a `why` charter accepts here is a record charter then
    # refuses to read back. Where it is drawn, `contain.one_line` clips it to a row.
    if contain.one_line(why, limit=change.TEXT_LIMIT) != why:
        util.err("--why must be one plain line — it is repeated back on a report row and "
                 "written into a pull request body. Longer reasoning belongs in "
                 "workspace.md, which is where this plane keeps prose.")
        return None
    return why


def _load(ws: str, slug: str) -> tuple[dict | None, int]:
    """``(record, 0)``, or ``(None, code)`` with the refusal already printed.

    Two different failures, two different codes. *No such change* is a refusal of what was
    asked (:data:`REFUSED`); a record that exists and does not parse is a defect in a file
    somebody has to go and fix, which is an error (1). Collapsing them would tell an agent
    to create a change that is already there.
    """
    if not change.exists(ws, slug):
        util.err(f"no change {contain.readable(slug)} in workspace '{ws}'.")
        util.info("List them: charter change list"
                  f"  ·  create it: charter change create {contain.readable(slug)} --why \"…\"")
        return None, REFUSED
    try:
        return change.read(ws, slug), 0
    except change.RecordError as exc:
        util.err(str(exc))
        return None, 1


def _save(ws: str, slug: str, rec: dict) -> int:
    """Write *rec* back, turning either refusal into an exit code.

    :class:`change.RecordError` here is an ordering that cannot be true — the cycle gate —
    and it is a refusal of the request. :class:`contain.Refused` is a path charter must not
    write, which is an error about the plane rather than about the request.
    """
    try:
        change.write(ws, slug, rec)
    except change.RecordError as exc:
        util.err(str(exc))
        return REFUSED
    except contain.Refused as exc:
        util.err(str(exc))
        return 1
    return 0


def _clone_for(ws: str, repo: str) -> Path | None:
    """The clone this member resolves to, or ``None``.

    :func:`contain.child` is the single gate, and it refuses rather than sanitises —
    *"silently rewriting a name invents a second identity"*. It is what makes ``..``, an
    absolute path, a drive-qualified name and a NUL unable to name a member at all. The
    rule underneath it is :func:`contain.segment_ok` and deliberately **not**
    ``workspace.valid_name``: ``.github`` is a real repository name, it comes from a forge
    rather than from charter, and ``valid_name`` rejects it for the leading dot.

    ``is_clone`` is the second half and answers a different question — git itself draws
    that line, since a clone's ``.git`` is a directory — so a symlink pointing out of the
    workspace, a plain file, or a directory that is not a checkout are all refused here
    rather than becoming a member charter would later try to push.
    """
    path = contain.child(workspace.workspace_dir(ws), repo)
    if path is None or not workspace.is_clone(path):
        return None
    return path


def cmd_change_create(args) -> int:
    """Create a change: a name, a reason, and no members yet."""
    ws = _workspace(args)
    slug = args.change
    if not instance.change_name_ok(slug):
        util.err(f"{contain.readable(slug)} is not a change name (letters, digits, '.', "
                 "'_', '-'; must not start with a dot or a dash).")
        util.info("The slug names a file in this plane, a branch in every member, and the "
                  "`Charter-Change:` trailer on each landing commit — so it is refused "
                  "rather than rewritten.")
        return 1
    # `required=True` on the parser as well. Both, because a change with no stated reason
    # is unreadable six months later — the one job the record has that git cannot do — and
    # argparse can see neither an empty value nor a newline in one.
    why = _why(args, "what this work is for")
    if why is None:
        return 1
    if change.exists(ws, slug):
        util.err(f"change '{slug}' already exists in workspace '{ws}'.")
        util.info(f"Show it: charter change show {slug}")
        return REFUSED
    rec = change.new_record(slug, why, _author(), _now())
    code = _save(ws, slug, rec)
    if code:
        return code
    util.ok(f"change '{slug}' created")
    util.info(f"Add its repos: charter change add {slug} <repo>")
    return 0


def cmd_change_add(args) -> int:
    """Add one member — one repository's part of the change — by literal name."""
    ws = _workspace(args)
    slug = args.change
    rec, code = _load(ws, slug)
    if rec is None:
        return code

    repo = args.repo
    if _clone_for(ws, repo) is None:
        util.err(f"{contain.readable(repo)}: no clone in workspace '{ws}'.")
        util.info(f"Clone it first: charter clone {contain.readable(repo)} -w {ws}")
        return REFUSED
    if change.member(rec, repo) is not None:
        shown = contain.readable(repo)
        util.err(f"'{shown}' is already a member of '{slug}'.")
        util.info(f"Change its branch or blockers by editing "
                  f"workspaces/{ws}/changes/{slug}.json, or drop it first: "
                  f"charter change drop {slug} {shown} --why \"…\"")
        return REFUSED

    branch = getattr(args, "branch", None) or change.default_branch(slug)
    complaint = change.branch_refusal(branch)
    if complaint:
        util.err(complaint)
        return 1
    needs = list(getattr(args, "needs", None) or ())

    rec = dict(rec)
    rec["members"] = rec["members"] + [{"repo": repo, "branch": branch, "needs": needs}]
    # A repo cannot be a member and excluded at once, so re-adding one lifts its exclusion —
    # loudly, because the exclusion carried a reason somebody wrote down and its removal is
    # a decision rather than bookkeeping.
    lifted = change.exclusion(rec, repo)
    if lifted is not None:
        rec["excluded"] = [e for e in rec["excluded"] if e["repo"] != repo]
    code = _save(ws, slug, rec)
    if code:
        return code
    if lifted is not None:
        util.warn(f"the exclusion recorded on {contain.one_line(lifted['at'])} is lifted: "
                  f"{contain.one_line(lifted['why'])}")
    print(_member_line(rec, {"repo": repo, "branch": branch, "needs": needs}))
    util.ok(f"'{contain.readable(repo)}' is a member of '{slug}'")
    return 0


def cmd_change_drop(args) -> int:
    """Drop a member (or record a repo that was never one) into ``excluded``, with a reason.

    ``--why`` is required and it is the cheapest line in this design: if members have
    already landed, the world stays partially changed permanently, and the only thing that
    makes that readable six months later is that somebody wrote down the reason at the
    moment they still knew it.
    """
    ws = _workspace(args)
    slug = args.change
    rec, code = _load(ws, slug)
    if rec is None:
        return code

    repo = args.repo
    why = _why(args, "why this repo is out")
    if why is None:
        return 1
    # No `segment_ok` gate here, deliberately, and it was measured rather than reasoned:
    # `..` reaches `change.write` below, `_repo_name` refuses the exclusion it would have
    # written, and the operator gets the same exit code and the same sentence — so a gate
    # here is a line no test can redden. `add` is the opposite case and keeps its own: there
    # the resolver has to answer *before* a name is joined onto a directory.
    if change.exclusion(rec, repo) is not None:
        util.err(f"'{contain.readable(repo)}' is already excluded from '{slug}'.")
        return REFUSED
    was_member = change.member(rec, repo) is not None
    blocked = change.dependents(rec, repo)
    if blocked:
        util.err(f"'{contain.readable(repo)}' cannot be dropped from '{slug}': "
                 + ", ".join(f"'{contain.readable(b)}'" for b in blocked) + " still need"
                 + ("" if len(blocked) > 1 else "s") + " it to land first.")
        util.info("Drop those members first, or edit their `needs` — a blocker nothing "
                  "will land is a member that never becomes ready.")
        return REFUSED

    rec = dict(rec)
    rec["members"] = [m for m in rec["members"] if m["repo"] != repo]
    rec["excluded"] = rec["excluded"] + [{"repo": repo, "why": why, "at": _now()}]
    code = _save(ws, slug, rec)
    if code:
        return code
    shown = contain.readable(repo)
    if was_member:
        util.ok(f"'{shown}' excluded — {len(rec['members'])} member(s) left")
    else:
        util.ok(f"'{shown}' excluded (never a member)")
    return 0


def cmd_change_forget(args) -> int:
    """Delete a change record by slug.

    A store with no way to end an entry grows without bound — ADR 0004's argument for
    ``charter workspace forget``, one noun out. It deletes the record and **nothing else**:
    no landing-log line, no branch, no request. The log is a past-tense declaration of
    something that happened, and deleting history to tidy a list is how a store starts
    lying; the branches are the repositories' business.
    """
    ws = _workspace(args)
    slug = args.change
    if not change.exists(ws, slug):
        util.err(f"no change {contain.readable(slug)} in workspace '{ws}'.")
        return REFUSED
    # No `RecordError` handler: `exists` above has already put this slug through
    # `path_for`, so the only way out of `forget` is a path charter must not write — a
    # committed link at the record's own name — which is the `None` below.
    removed = change.forget(ws, slug)
    if removed is None:
        util.err(f"could not delete the record for '{slug}'.")
        return 1
    util.ok(f"change '{slug}' forgotten — the record is gone; branches, requests and the "
            "landing log are untouched.")
    return 0


def cmd_change_list(args) -> int:
    """Every change in the workspace, one row each.

    A `changes/` it could not list is named, with what clears it, and is never "No changes"
    (#1084): the listing is not complete, so it exits 1 as it does for a record it could not
    read."""
    ws = _workspace(args)
    records, refused, unread = change.read_all(ws)
    if unread:
        workspace.say_unread(unread)
        return 1
    if not records and not refused:
        util.info(f"No changes in workspace '{ws}'. "
                  "Create one: charter change create <slug> --why \"…\"")
        return 0
    names = [contain.one_line(r["change"]) for r in records]
    # gap=0: the gutter is the two literal spaces in the row below, so the width
    # is the widest cell and nothing else. `tui.column` never `len()` — a name whose
    # glyphs are two cells wide is two cells wide (#472).
    w = tui.column("", names, gap=0)
    for rec, name in zip(records, names):
        counts = f"{len(rec['members'])} member(s)"
        if rec["excluded"]:
            counts += f", {len(rec['excluded'])} excluded"
        print(f"{tui.pad(name, w)}  {counts}  ·  {contain.one_line(rec['why'])}")
    for slug, complaint in refused:
        util.err(f"{contain.readable(slug)}: {complaint}")
    return 1 if refused else 0


def cmd_change_show(args) -> int:
    """One change, whole: what it is for, who is in it, and what must go first.

    §3.4 calls this the monorepo view, and being a *view* is what makes it correct — the
    clones are already siblings under one workspace directory, so ``rg`` already spans the
    change; what was missing is knowing which of those subdirectories are one piece of
    work. Every derived column (request numbers, check state, landing dates) belongs to the
    forge-reading phase; what prints here is the record and nothing else, so it is true
    without asking anybody.
    """
    ws = _workspace(args)
    slug = args.change
    rec, code = _load(ws, slug)
    if rec is None:
        return code

    print(f"{contain.one_line(rec['change'])} · {len(rec['members'])} member(s)"
          + (f" · {len(rec['excluded'])} excluded" if rec["excluded"] else ""))
    print(f"  why: {contain.one_line(rec['why'])}")
    print(f"  created {contain.one_line(rec['created'])} by {contain.one_line(rec['by'])}")

    if rec["members"]:
        print("")
        for m in rec["members"]:
            print(_member_line(rec, m))
    # The derived half, and it prints nothing at all when no member resolves to a forge —
    # a change whose clones charter cannot ask about shows exactly the record, rather than a
    # block of "unknown" rows that look like an answer. Nothing here is written back.
    observed = show_observed(ws, rec)
    if observed:
        print("")
        for line in observed:
            print(line)

    if rec["excluded"]:
        print("")
        print("  excluded:")
        w = tui.column("", [contain.one_line(e["repo"]) for e in rec["excluded"]], gap=0)
        for e in rec["excluded"]:
            print(f"  {tui.pad(contain.one_line(e['repo']), w)}  "
                  f"{contain.one_line(e['why'])}  ({contain.one_line(e['at'])})")
    return 0


# --------------------------------------------------------------------------- #
# git, in a clone the operator already has — never a forge, never a network     #
# --------------------------------------------------------------------------- #

def _git(clone: Path, *args: str):
    """One read-only git question about *clone*, never raising on a non-zero exit.

    `doctor._git_in`'s shape and its reason. Read-only is a property of the ARGUMENTS
    rather than of this function, and the two callers that are not read-only —
    :func:`_seed_revert`'s checkout and revert — go through here too, so that every git
    invocation a change action makes passes one place a test can record.
    """
    return util.run(["git", "-C", str(clone), *args], check=False, timeout=GIT_TIMEOUT)


def _default_branch(clone: Path) -> str | None:
    """*clone*'s default branch, or ``None`` when charter cannot honestly say.

    `doctor._plane_default_branch`, asked rather than re-spelled — `hooks` already reaches
    for it the same way. Two answers to "what is this repo's default branch" would drift,
    and the drift would be a divergence report about the wrong branch: a plane whose
    default is `trunk` easily still carries a stale local `main`, and the guess-first
    version of this warns about the correct branch.

    ``None`` matters here more than it does there: every question below is *relative to
    the default branch*, so a clone charter cannot resolve one for produces no divergence
    findings at all rather than findings against a branch nobody uses.
    """
    from .doctor import _plane_default_branch
    return _plane_default_branch(clone)


def _contains(clone: Path, commitish: str, default: str) -> bool:
    """Does *default* contain *commitish*? False for anything charter could not resolve.

    ``refs/heads/<default>`` for the argv reason in this module's docstring, and a bare
    *commitish* only where the caller has already held it to :data:`_SHA_RE` — the two
    callers are :func:`_declared_landed` (a sha out of the log) and :func:`divergences` (a
    member's branch, spelled as a ref).
    """
    return _git(clone, "merge-base", "--is-ancestor", commitish,
                f"refs/heads/{default}").returncode == 0


def _branch_exists(clone: Path, branch: str) -> bool:
    """Is there a local branch of this name? ``refs/heads/`` — see the module docstring."""
    return _git(clone, "rev-parse", "--verify", "--quiet",
                f"refs/heads/{branch}").returncode == 0


#: The one trailer charter promises, on the one commit charter authors. Held here rather
#: than spelled at each site: `revert` builds it, the divergence check looks for it, and
#: the docs quote it, so a second spelling would be a second trailer.
TRAILER = "Charter-Change"


def _local_branches(clone: Path) -> set[str]:
    """Every local branch in *clone*, as a set. Empty for anything charter could not ask.

    `for-each-ref` rather than a `rev-parse` per name: the caller is asking about N
    branches at once, and the difference is one child process against N of them on a path
    that runs at SessionStart. It also carries no untrusted argument at all — `refs/heads/`
    is a literal and the comparison happens in Python — which is a stronger answer to the
    argv question than spelling a committed value carefully.
    """
    got = _git(clone, "for-each-ref", "--format=%(refname:short)", "refs/heads/")
    if got.returncode != 0:
        return set()
    return {ln.strip() for ln in (got.stdout or "").splitlines() if ln.strip()}


def _trailer_names(clone: Path, sha: str, slug: str) -> bool:
    """Does the commit *sha* carry ``Charter-Change: <slug>``?

    Read out of the commit's own body rather than asked of `git log --grep`, because the
    question is about **this** commit and a grep over a range answers about the range.
    `%B` is the raw body, so a trailer somebody wrote by hand reads the same as one charter
    wrote — which is correct: the claim being checked is *what the commit says*, and
    charter has no way to tell its own trailer from an identical one, nor any business
    trying.
    """
    got = _git(clone, "show", "--no-patch", "--format=%B", sha)
    if got.returncode != 0:
        return False
    want = f"{TRAILER}: {slug}"
    return any(line.strip() == want for line in (got.stdout or "").splitlines())


def _declared_landed(ws: str, slug: str) -> dict[str, dict]:
    """``{repo: the landing line}`` for every member this plane DECLARED it landed.

    File reads only, deliberately: this is the same answer `frame/gather.py` carries into
    the frame's one snapshot, and a second, git-joined answer computed here would be the
    second clock §4f names as the thing this codebase has already paid for twice.

    The git join lives in :func:`divergences`, which is ADR 0013's shape rather than an
    omission: the cheap surface shows what charter declared, and a separate read names
    every place git disagrees with it. One clock, one divergence report.
    """
    return change.declared_landings(ws, slug)


def out_of_order(rec: dict, landed) -> dict[str, list[str]]:
    """``{member: the blockers it went in ahead of}`` — §3.2's honest half.

    Charter refuses to land a member whose blockers have not landed, and it cannot stop a
    human merging in a browser. What would be theatre is a guard that *reports*
    enforcement it does not have, so the same read that refuses also names the landings
    that happened anyway.

    A pure intersection of two things `change` already derives, so it cannot disagree with
    the gate: the members that landed, and the members some blocker of which has not.
    """
    have = set(landed or ())
    blocked = change.blocked_members(rec, have)
    return {repo: pending for repo, pending in blocked.items() if repo in have}


def divergences(ws: str, rec: dict) -> list[str]:
    """Everything git says about this change that the plane's own records do not — as
    sentences, each naming the member it is about.

    **ADR 0013 rule 2, five ways.** *"A divergence charter can see, charter names… WARN is
    not a surface. A divergence worth naming under rule 2 is worth FAIL."* Every finding
    here is a FAIL at its call site, and none of them is a state anything stores.

    1. **Landed outside charter.** The member's recorded branch is contained in its
       clone's default branch and there is no landing declaration — so there is no
       ``Charter-Change`` trailer and no merge sha, and `revert` has nothing to run
       against. Named, and handed to a human.
    2. **A declared landing git no longer contains.** Charter said it merged that sha and
       the default branch does not have it: reverted, or the branch was rewritten.
       *"A member with a log line git no longer contains is not landed any more, and
       nothing had to notice or update a flag for that to become true."*
    3. **A declared landing whose commit does not carry the trailer.** The log names a
       commit charter did not author for this change.
    4. **An out-of-order landing** — :func:`out_of_order`.
    5. **A member's branch name in a clone that is a member of nothing.** The one check
       that looks outside the change: a `change/<slug>` branch sitting in a repository
       nobody declared is either a member somebody forgot to add or a name collision, and
       both are worth a sentence.

    A clone charter cannot resolve a default branch for contributes nothing rather than
    contributing a guess — see :func:`_default_branch`.
    """
    slug = rec["change"]
    declared = _declared_landed(ws, slug)
    out: list[str] = []
    for m in rec["members"]:
        repo, branch = m["repo"], m["branch"]
        clone = _clone_for(ws, repo)
        if clone is None:
            continue          # `charter change add` refused this once; `doctor` says so
        default = _default_branch(clone)
        if default is None:
            continue
        line = declared.get(repo)
        if line is None:
            if _branch_exists(clone, branch) and \
                    _contains(clone, f"refs/heads/{branch}", default):
                out.append(
                    f"{contain.readable(repo)}: branch {contain.readable(branch)} is "
                    f"already in '{contain.one_line(default)}' and charter did not land "
                    f"it — so there is no {TRAILER} trailer and no merge sha. "
                    f"`charter change revert` cannot reach this member; a human has to.")
            continue
        sha = line["merge"]
        if not isinstance(sha, str) or not _SHA_RE.fullmatch(sha):
            out.append(f"{contain.readable(repo)}: the landing log records "
                       f"{contain.readable(sha)} as the merge, which is not a sha.")
            continue
        if not _contains(clone, sha, default):
            out.append(
                f"{contain.readable(repo)}: charter declared it landed as {sha}, and "
                f"'{contain.one_line(default)}' no longer contains that commit — it was "
                f"reverted, or the branch was rewritten. This member is not landed any "
                f"more.")
        elif not _trailer_names(clone, sha, slug):
            out.append(
                f"{contain.readable(repo)}: the landing log names {sha}, and that commit "
                f"carries no `{TRAILER}: {slug}` trailer — charter did not author it for "
                f"this change.")
    for repo, pending in sorted(out_of_order(rec, declared).items()):
        out.append(
            f"{contain.readable(repo)}: landed while "
            + ", ".join(f"'{contain.readable(p)}'" for p in pending)
            + " had not. Charter refuses that landing and cannot stop a browser; this is "
              "the half that makes the guard honest rather than decorative.")
    return out


def stray_branches(ws: str) -> list[str]:
    """Members' branch names found in clones that are a member of no change at all.

    §3.2's second check, and the only one that looks outside the change: a branch named
    like a change's member, in a repository nobody declared, is either a member somebody
    forgot to `charter change add` or a collision with a name that means something else.
    Both are worth a sentence and neither is a state.

    A record charter cannot read contributes no names — `change.all_for` reports those
    separately and `doctor` says so — because guessing at branch names from a record that
    did not parse is the unearned diagnosis ADR 0009 forbids.
    """
    # `read_all`, not `all_for`: a `changes/` it could not list contributes no names either, and
    # `doctor`, this function's caller, has already named it from its own read (#1084) rather
    # than losing the whole row to it here.
    records, _refused, _unread = change.read_all(ws)
    wanted: dict[str, str] = {}          # branch name → the change that declares it
    members: set[str] = set()
    for rec in records:
        for m in rec["members"]:
            wanted.setdefault(m["branch"], rec["change"])
            members.add(m["repo"])
    if not wanted:
        return []
    out: list[str] = []
    for clone in sorted(workspace.clones(ws)):
        if clone.name in members:
            continue
        # ONE git call per clone, not one per (clone, branch). This runs from doctor,
        # which runs from SessionStart under a budget — a plane with ten clones and five
        # changes would otherwise pay fifty `rev-parse`s to answer a question one listing
        # answers. It also takes the untrusted value out of the argv entirely: the only
        # argument here is the literal `refs/heads/`, and the branch names are compared in
        # Python.
        here = _local_branches(clone)
        for branch, slug in sorted(wanted.items()):
            if branch in here:
                out.append(
                    f"{contain.readable(clone.name)}: has branch "
                    f"{contain.readable(branch)}, which change "
                    f"'{contain.readable(slug)}' declares — and this repo is a member of "
                    f"no change. Add it (charter change add), or the branch is a name "
                    f"collision worth knowing about.")
    return out


# --------------------------------------------------------------------------- #
# revert — a new change, because that is the only rollback a stranger can read  #
# --------------------------------------------------------------------------- #

def _parents(clone: Path, sha: str) -> int | None:
    """How many parents *sha* has, asked of git — or ``None`` when git would not say.

    **Asked, never remembered**, which is what decides whether the revert carries ``-m
    1``. A squash landing is an ordinary one-parent commit and ``-m`` on one fails; a
    merge landing has two and ``git revert`` refuses without it. Storing "this was a
    squash" in the log would be a derivable fact cached for convenience, which is the
    sentence ADR 0011 is.
    """
    got = _git(clone, "rev-list", "--parents", "-n", "1", sha)
    if got.returncode != 0:
        return None
    parts = (got.stdout or "").split()
    return len(parts) - 1 if parts else None


def _seed_revert(clone: Path, *, sha: str, branch: str, default: str) -> str | None:
    """Create *branch* off *default* carrying a revert of *sha*. ``None``, or the reason.

    Four things this does not do, and none of them is behind a flag: it does not force
    anything, delete anything, reset anything, or touch a request. What it does is create
    a branch and add a commit, which is the whole of what a revert-as-a-new-change is.

    **The working tree is checked first and the refusal is named.** `git revert` commits
    into the checkout, so running it over uncommitted work would fold somebody's work in
    progress into a revert commit — and the recovery for that is worse than the wait.

    A conflicted revert is **aborted and named**, not left half-applied: `--abort` restores
    the checkout the revert started from, so the branch stays and the operator resolves it
    themselves. Charter has no business guessing which side of a conflict a rollback
    wanted.

    **`commit.gpgsign` is deliberately not passed on this call**, and the reason is that it
    is already settled one layer down. A revert is the operator's commit in the operator's
    repository, so charter silently unsigning it would be charter deciding somebody's
    signing policy — ADR 0014's rule, which puts that with the host. What actually keeps an
    autonomous run from hanging on a signer prompt is `gitpolicy`: `charter git-policy
    --apply` writes `commit.gpgsign = false` into each clone's *local* config, and `charter
    clone` applies it to everything it clones, precisely because *"a GPG signer prompt hangs
    an autonomous agent mid-run"*. In a clone charter did not set up, the prompt is the
    operator's own configuration doing what they asked it to — measured here as a suite that
    hung with `op-ssh-sign` waiting, which is why `tests/_changerepo.py` sets the policy on
    its fixture repos rather than this function setting it on everybody's.
    """
    dirty = _git(clone, "status", "--porcelain")
    if dirty.returncode != 0:
        return "git could not read the working tree"
    if (dirty.stdout or "").strip():
        return ("the working tree has uncommitted changes, and `git revert` commits into "
                "the checkout — commit or stash them first")
    if _branch_exists(clone, branch):
        return f"branch {contain.readable(branch)} already exists here"
    # `switch -c` rather than `checkout -b`: one verb that only ever moves the branch,
    # against a verb that also restores files and whose argv a path can slip into.
    made = _git(clone, "switch", "-c", branch, f"refs/heads/{default}")
    if made.returncode != 0:
        return contain.one_line((made.stderr or "could not create the branch").strip())
    n = _parents(clone, sha)
    if n is None:
        return f"git does not know the commit {sha}"
    # `-m 1` exactly when git says there is more than one parent — see `_parents`. Spread
    # into the call rather than built as a whole argv, so that the VERB stays a literal at
    # the call site: `tests/test_commands_change.py` reads every `_git` invocation in this
    # module statically and lists the git subcommands it can reach, which is what makes
    # "no network" a claim about the argv rather than about the imports.
    mflag = ["-m", "1"] if n > 1 else []
    done = _git(clone, "revert", "--no-edit", *mflag, sha)
    if done.returncode != 0:
        _git(clone, "revert", "--abort")
        return contain.one_line(
            (done.stderr or "the revert did not apply").strip()) + \
            " — the branch is here and the revert was aborted; finish it by hand"
    return None


def cmd_change_revert(args) -> int:
    """`charter change revert <slug>` — derive a NEW change that reverts what landed.

    **A revert is a new change**, and that is the whole design rather than a limitation.
    Force-pushing three default branches back past the merges leaves a world where the
    change happened, was undone, and no repository's history mentions either — the exact
    failure this whole surface exists to prevent. `component-api-2` and
    `revert-component-api-2`, both named, both cross-referenced, in every repository they
    touched, reads as a decision six months later; a force-push reads as corruption.

    So from here it is ordinary: pushed, reviewed, gated and landed one member at a time,
    by the same commands with the same refusals. There is no ``--all`` on this either.

    **A member landed outside charter is named, not guessed.** No line in the landing log
    means no merge sha, and charter will not pick the merge commit that looks about right.
    ADR 0009: it degrades to silence, never to a confident wrong answer.

    **Two things it cannot do, said here rather than discovered.** It cannot revert a
    deploy — a merge to a default branch on a repo with continuous deployment has already
    had an effect in the world, and charter has no model of deployment. And it cannot
    revert what it did not record.
    """
    ws = _workspace(args)
    slug = args.change
    rec, code = _load(ws, slug)
    if rec is None:
        return code

    # **There is deliberately no `change_name_ok(new_slug)` guard here, and it was
    # measured rather than assumed.** `_load` above succeeded, which means `change.exists`
    # put *slug* through `change.path_for` and therefore through `instance.change_name_ok`
    # — and `CHANGE_NAME_RE` has no length bound and no leading-character rule a
    # `revert-` prefix could break, so `change_name_ok("revert-" + <a valid slug>)` is
    # true for every valid slug there is. A guard nothing can reach is a comment with a
    # runtime cost (`commands_frame.cmd_toggle` records the same deletion for the same
    # reason). The property is pinned directly instead, on the derivation.
    new_slug = REVERT_PREFIX + slug
    if change.exists(ws, new_slug):
        util.err(f"change '{new_slug}' already exists in workspace '{ws}'.")
        util.info(f"Show it: charter change show {new_slug}  ·  or forget it first: "
                  f"charter change forget {new_slug}")
        return REFUSED

    declared = _declared_landed(ws, slug)
    if not declared:
        util.err(f"'{slug}': charter has landed no member of this change, so there is "
                 "nothing to revert.")
        util.info("A member merged outside charter has no landing record and no merge "
                  "sha — charter names it rather than guessing which commit was the one.")
        return REFUSED

    # Named before anything is written, so the operator reads the whole picture rather
    # than discovering the un-revertible half after the record exists.
    handed_over = [m["repo"] for m in rec["members"] if m["repo"] not in declared]
    for repo in handed_over:
        util.warn(f"{contain.readable(repo)}: no landing record, so no merge sha — "
                  "charter cannot revert this member. If it was merged in a browser, the "
                  "commit is a human's to find.")

    members, seeded, refused = [], [], []
    for m in rec["members"]:
        repo = m["repo"]
        line = declared.get(repo)
        if line is None:
            continue
        clone = _clone_for(ws, repo)
        if clone is None:
            refused.append((repo, f"no clone in workspace '{ws}'"))
            continue
        sha = line["merge"]
        if not isinstance(sha, str) or not _SHA_RE.fullmatch(sha):
            refused.append((repo, f"the landing log records {contain.readable(sha)} as "
                                  "the merge, which is not a sha"))
            continue
        default = _default_branch(clone)
        if default is None:
            refused.append((repo, "charter cannot tell which branch is the default here, "
                                  "so it will not guess what to branch from"))
            continue
        branch = change.default_branch(new_slug)
        # The member joins the record whether or not the seeding worked. The record is the
        # statement of intent — these repositories are the ones to revert — and a branch
        # that did not get created is a thing to fix, not a member to drop silently.
        #
        # **The ordering is the original's, REVERSED**, and that is a decision rather than
        # bookkeeping. If `charter-metrics` needed `charter` to land first — because its
        # code depends on charter's new API — then undoing it has to go the other way:
        # reverting `charter` while `charter-metrics` still depends on the API it removes
        # leaves the dependent broken, which is the world the revert was supposed to
        # restore. So a member's blockers here are the members that declared IT as a
        # blocker there (`change.dependents`), filtered to the ones being reverted — a
        # member whose dependent charter did not land is not waiting for anybody.
        members.append({"repo": repo, "branch": branch,
                        "needs": [d for d in change.dependents(rec, repo)
                                  if d in declared]})
        why = _seed_revert(clone, sha=sha, branch=branch, default=default)
        if why is None:
            seeded.append(repo)
        else:
            refused.append((repo, why))

    new_rec = change.new_record(
        new_slug,
        f"reverts change '{slug}': {rec['why']}"[:change.TEXT_LIMIT],
        _author(), _now())
    new_rec["members"] = members
    code = _save(ws, new_slug, new_rec)
    if code:
        return code

    util.ok(f"change '{new_slug}' created — {len(members)} member(s) to revert")
    for repo in seeded:
        print(f"  {contain.one_line(repo)}  branch "
              f"{contain.one_line(change.default_branch(new_slug))}  reverted")
    for repo, why in refused:
        util.err(f"{contain.readable(repo)}: {why}")
    util.info(f"It is an ordinary change from here: charter change show {new_slug}")
    # Non-zero when a member charter put in the record has no branch behind it: the record
    # says these repositories are to be reverted, and one of them is not started.
    return 1 if refused else 0


def _member_line(rec: dict, m: dict) -> str:
    """One member's row. Every field is contained **before** the width arithmetic.

    That order is #472: `tui.pad` measures the string it is handed, so escaping a value
    after padding it pads it to the wrong width, and the column stops lining up at exactly
    the row whose content came out of a committed file. `contain.one_line` is the bound
    here, and it holds only what that function holds — line structure, not trustworthiness.
    """
    w = tui.column("", [contain.one_line(x["repo"]) for x in rec["members"]], gap=0)
    row = (f"  {tui.pad(contain.one_line(m['repo']), w)}  "
           f"branch {contain.one_line(m['branch'])}")
    if m["needs"]:
        row += "   needs: " + ", ".join(contain.one_line(n) for n in m["needs"])
    return row


# =================================================================================== #
# The forge half: push, land                                                          #
# =================================================================================== #
# Everything above this line is a file read and a file write. Everything below it acts on
# a remote with the operator's own credential, and the containment property is one
# sentence:
#
#     **Membership is committed. Destination is local.**
#
# §4b's *"Arrangement is committed. Execution is local."* applied to a different committed
# file. A record may say WHICH repositories are members and never WHERE they are, for the
# same reason `charter.toml` may say which components to place and never what code runs: a
# remote URL in a committed file is a destination that arrived from someone else's machine.
#
# So the record carries no URL, no host, no remote name, no forge kind and no base branch.
# Every one of those is read from the clone the member resolves to, which the operator put
# there by hand. A hostile record can name a repository you do not have — and be refused
# for that, by name — but it can never name a place.

#: The delimiters charter owns inside a request body. Everything outside them is somebody's
#: prose, and charter does not write there.
#:
#: The shape is `workspace._LIVE_BEGIN`/`_LIVE_END` and `render.PERSONAS_BEGIN`/`END`, and
#: so is the posture: `render.splice_personas` answers ``None`` when the markers are absent
#: *"so a hand-written README is never appended to by surprise"*. A request body is the same
#: thing with a wider audience.
BLOCK_BEGIN = ("<!-- BEGIN charter change — GENERATED by `charter change push`; "
               "do not edit by hand. -->")
BLOCK_END = "<!-- END charter change -->"

#: A markdown fence, either spelling. A marker inside one is prose ABOUT the block rather
#: than the block, and splicing there would rewrite an example somebody wrote out.
_FENCE = ("```", "~~~")


def _cell(value) -> str:
    """One table cell. Contained first, then the pipe escaped.

    Two treatments because they answer different questions. `contain.one_line` is what stops
    a `why` carrying a newline or a U+2028 from becoming a second table row — the record is
    committed and arrived from someone else's machine. The pipe is markdown's own column
    separator and `one_line` has no opinion about it, so a `why` reading ``a | b`` would
    silently add a column to every reader's table.
    """
    return contain.one_line(value).replace("|", "\\|")


def cross_link_block(rec: dict, seen: dict) -> str:
    """The block charter writes into every member's request body.

    This is the artifact the whole design leans on: it is the cross-repo link that lives
    **inside the repositories**, so it survives charter being uninstalled, and it is the one
    thing that has to be MAINTAINED rather than written once — membership changes, and five
    hand-written request bodies go stale the first time it does.

    *seen* is ``{repo: (number, path, sigil)}`` for the members charter actually reached —
    **one dict, not three**, and that is a fix rather than a tidy-up. Three parallel dicts
    meant two lookups that could miss, so both grew a fallback (``paths.get(repo) or repo``,
    ``sigils.get(repo, "#")``), and the deletion sweep found both: they are unreachable,
    because a repo only ever gets a number once its path and sigil are known. One lookup
    has one outcome to handle, and the ``—`` that handles it is a row a test asserts.

    A member charter could not open a request for renders as ``—`` rather than being
    dropped, because a table that omits a member says the change has fewer members than it
    has. The sigil is per member, not per plane: a workspace can hold clones from several
    forges side by side, so ``!14`` and ``#601`` can be two rows of one table.
    """
    rows = ["| repo | request | needs |", "|---|---|---|"]
    for m in rec["members"]:
        repo = m["repo"]
        entry = seen.get(repo)
        if entry is None:
            where = "—"
        else:
            number, path, sigil = entry
            where = f"{_cell(path)}{_cell(sigil)}{int(number)}"
        needs = ", ".join(_cell(n) for n in m["needs"]) or "—"
        rows.append(f"| {_cell(repo)} | {where} | {needs} |")
    return "\n".join([
        BLOCK_BEGIN,
        f"**Cross-repo change: `{_cell(rec['change'])}`** — {_cell(rec['why'])}",
        "",
        *rows,
        BLOCK_END,
    ])


def splice_block(body: str, block: str) -> str | None:
    """*body* with the region between the markers replaced by *block*, or ``None``.

    ``None`` — a refusal, not a fallback — when the markers are absent, when either appears
    more than once, when they are in the wrong order, or when either sits inside a fenced
    code block. Charter owns what is between its own delimiters and nothing else; every
    other reading of a body it did not author is charter editing a human's words.

    A body charter itself wrote at `create_change` time already carries the pair, so the
    absent case is a request somebody else opened — which is exactly the one where refusing
    is right.

    *body* is a ``str``, not ``str | None``: the protocol's `change_body` already turns
    GitHub's ``"body": null`` into ``""``, and a second ``or ""`` here was a fallback the
    deletion sweep could remove without reddening anything — the same value defended twice,
    which reads as a guard and is not one.
    """
    lines = body.splitlines()
    begins, ends, fenced = [], [], False
    fence = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(_FENCE):
            fence = not fence
        if BLOCK_BEGIN in line:
            begins.append(i)
            fenced = fenced or fence
        if BLOCK_END in line:
            ends.append(i)
            fenced = fenced or fence
    if fenced or len(begins) != 1 or len(ends) != 1 or begins[0] > ends[0]:
        return None
    return "\n".join(lines[:begins[0]] + block.splitlines() + lines[ends[0] + 1:])


def _origin_url(clone) -> str:
    return (_git(clone, "remote", "get-url", "origin").stdout or "").strip()


def _forge_for(clone) -> tuple[object | None, str, str]:
    """``(forge, path_with_namespace, complaint)`` for one member's clone.

    Resolved from **this clone's own origin**, never from the plane's first ``[[forge]]``
    block: a workspace can hold clones from several forges side by side, which is why the
    sigil in the block above is per member. A host that is neither a registered default nor
    declared in this plane's ``charter.toml`` is genuinely unrecognised, and it is refused
    rather than handed another forge's policy — a wrong-but-plausible answer is worse than
    an honest "can't tell", and this one would push with the wrong credential.
    """
    url = _origin_url(clone)
    if not url:
        return None, "", "has no 'origin' remote — nothing to push to."
    forge = registry.resolve_host(url, config.ROOT)
    if forge is None:
        return None, "", (f"origin is on a host charter does not know "
                          f"({contain.readable(url)}). Declare it as a [[forge]] block.")
    path = registry.namespace_of(url)
    if not path:
        return None, "", f"origin names no repository ({contain.readable(url)})."
    return forge, path, ""


def _member_forge(ws: str, m: dict) -> tuple[object | None, str, str]:
    """``(forge, path, complaint)`` for one member, containment included.

    The member resolves through `contain.child` and `workspace.is_clone` exactly as `add`
    does — refused, never sanitised — so a record naming ``..``, an absolute path, a NUL or
    a symlink out of the workspace cannot name a clone here either. The reach of a change is
    bounded by what the operator already put on this disk.
    """
    repo = m["repo"]
    clone = _clone_for(ws, repo)
    if clone is None:
        return None, "", (f"no clone in workspace '{ws}'. "
                          f"Clone it first: charter clone {contain.readable(repo)} -w {ws}")
    return _forge_for(clone)


# --------------------------------------------------------------------------------- #
# The landing log — a past-tense declaration, never committed                         #
# --------------------------------------------------------------------------------- #
# "Has this member landed" cannot be answered from the record and must not be stored in it.
# It also cannot be answered from the forge alone: a merged request's source branch is
# routinely deleted, and a branch-keyed lookup then finds nothing at all — indistinguishable
# from a member that was never pushed.
#
# So charter writes the shape `planegit` already ships for exactly this problem. What the
# log holds is the declaration git cannot make — *charter merged this commit, for this
# change* — and the present tense is reconstructed at read time by asking git whether the
# default branch still contains that sha. That join is what keeps this from being the
# "current status" marker ADR 0011 forbids.

def _log_path(ws: str):
    """``changes/log/<host>.jsonl``.

    The host tag is `pieces._host` itself rather than a second implementation of it: the
    spec asks for the same per-host filename as ``pieces/<host>.jsonl``, and two functions
    that both answer "what is this machine called" are two functions that can disagree.
    """
    return change.log_dir(ws) / f"{pieces._host()}.jsonl"


def _append_landing(ws: str, slug: str, repo: str, number: int,
                    head: str, merge: str) -> None:
    """Append one past-tense line. Best-effort, `O_APPEND`, no lock — `pieces.record`'s
    exact shape, and never committed for the same reason ``pieces/`` is not.

    Written **after** the read-back and only for a merge charter confirmed: a declaration of
    something that did not happen is worse than none.
    """
    line = {"ts": _now(), "change": slug, "repo": repo,
            "number": int(number), "merge": merge, "head": head}
    p = _log_path(ws)
    if contain.write_refusal(p):
        return
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        blob = (contain.json_line(line, sort_keys=True) + "\n").encode()
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, blob)
        finally:
            os.close(fd)
    except OSError:
        pass


def landings(ws: str, slug: str) -> dict:
    """``{repo: line}`` — the last landing charter declared for each of *slug*'s members.

    Every host's file, because a change is worked from more than one machine and a landing
    declared on one of them is still a landing. Unreadable or malformed lines are skipped
    rather than raising: this is bookkeeping beside git, and git is the thing being asked.
    """
    out: dict = {}
    d = change.log_dir(ws)
    if contain.dir_refusal(d):
        return out
    for f in sorted(d.glob("*.jsonl")) if d.is_dir() else []:
        # Both halves of #336, and they catch different things: `dir_refusal` above sees a
        # link at `log/` itself — under which every file is an ordinary regular file with
        # nothing to object to — and this one sees a link, a FIFO or an oversized file at
        # one entry inside an ordinary directory.
        if contain.file_refusal(f):
            continue
        try:
            text = f.read_text()
        except OSError:
            continue
        for raw in text.splitlines():
            try:
                line = json.loads(raw)
            except ValueError:
                continue
            if isinstance(line, dict) and line.get("change") == slug and line.get("repo"):
                out[line["repo"]] = line
    return out


#: What a commit id may look like before charter hands it to git as a revision.
def member_landed(ws: str, m: dict, forge, path: str, log: dict):
    """``(landed, why_not)`` for one member. Both halves, because neither alone is enough.

    The forge alone cannot see a revert; the log alone cannot see a browser merge. So:
    the forge must say **merged**, and where charter's own log has a line for this member,
    git must still show the default branch containing the sha that line recorded. A member
    the forge calls merged with no log line is landed *and* divergent — it landed outside
    charter — which is a thing to NAME rather than a reason to call it unlanded.

    Raises :class:`forgebase.ForgeError` when the lookup itself failed; there is no value
    here meaning "could not ask", and answering ``False`` for a rate-limited call is how a
    blocker that landed reads as one that did not.
    """
    req = forge.request_for(path, m["branch"])
    if req is None:
        return False, "has no request"
    if req.state != forgebase.REQUEST_MERGED:
        return False, f"request {req.state}"
    line = log.get(m["repo"])
    if not line or not line.get("merge"):
        return True, "landed outside charter (no charter landing record)"
    sha = str(line["merge"])
    clone = _clone_for(ws, m["repo"])
    if clone is None:
        return False, "merged, but its clone is no longer in this workspace"
    # `_SHA_RE` before `_contains`, because that helper's contract says a bare commitish
    # reaches git only where the caller has already held it to this shape. The log is never
    # committed, which makes it LOCAL rather than trustworthy: a hand edit, or a
    # half-written line from a killed process, reaches here and then reaches a git argv.
    if not _SHA_RE.fullmatch(sha):
        return False, (f"merged, but the landing log's sha {contain.readable(sha)} is not a "
                       f"sha — charter will not hand it to git")
    # `None` is asked separately rather than folded into the answer: `_contains` is False
    # for a default branch charter could not resolve AND for one that genuinely does not
    # contain the sha, and those two send the reader to different places.
    default = _default_branch(clone)
    if default is None:
        return False, "merged, but charter cannot resolve this clone's default branch"
    if not _contains(clone, sha, default):
        return False, (f"merged as {contain.one_line(sha)[:12]}, which this clone's "
                       f"'{contain.one_line(default)}' does not contain "
                       f"(reverted, or not fetched since)")
    return True, ""


# --------------------------------------------------------------------------------- #
# `charter change push`                                                               #
# --------------------------------------------------------------------------------- #

def _title_for(rec: dict, m: dict) -> str:
    return f"{contain.one_line(rec['change'])}: {contain.one_line(m['repo'])}"


def _new_body(rec: dict) -> str:
    """The body charter writes when it OPENS a request — markers included, empty table.

    The markers go in at creation so the second pass has something to splice into. A body
    charter did not author never gains them, and `splice_block` refuses it: charter owns
    what is between its delimiters and nothing else.
    """
    return "\n".join([
        f"{_cell(rec['why'])}",
        "",
        cross_link_block(rec, {}),
    ])


def _push_one(ws: str, rec: dict, m: dict) -> tuple[dict, str]:
    """Push one member's branch and make sure it has a request. ``(facts, complaint)``."""
    repo = m["repo"]
    clone = _clone_for(ws, repo)
    if clone is None:
        return {}, (f"no clone in workspace '{ws}'. "
                    f"Clone it first: charter clone {contain.readable(repo)} -w {ws}")
    forge, path, complaint = _forge_for(clone)
    if forge is None:
        return {}, complaint
    branch = m["branch"]
    # **Spelled here, in full, rather than built by a helper.** `_git`'s verb is a literal
    # at every call site in this module so `tests/test_commands_change.py` can read the git
    # subcommand off the syntax tree — a dynamic argv is a subcommand nobody is checking.
    #
    # `--` before the branch, because `git check-ref-format` **accepts** `refs/heads/-b`:
    # ref grammar is not argv safety, so `change.branch_refusal` at the record boundary and
    # this position are two mechanisms, and either alone has already shipped a bug here.
    # No force of any spelling — a push that can only fast-forward cannot overwrite a
    # remote, which is what §3.7 refuses.
    pushed = _git(clone, "push", "--set-upstream", "origin", "--", branch)
    if pushed.returncode != 0:
        # git's own words. `planegit` already declines to predict a protected branch because
        # *"guessing it from the branch name is precisely the unearned diagnosis ADR 0009
        # forbids"*, and the same applies to every other reason a push can be refused.
        detail = (pushed.stderr or pushed.stdout or "").strip().splitlines()
        return {}, "push failed: " + contain.one_line(detail[-1] if detail else "no output")
    facts = {"forge": forge, "path": path, "clone": clone, "sigil": forge.change_sigil}
    try:
        req = forge.request_for(path, branch)
    except forgebase.ForgeError as exc:
        return facts, contain.one_line(str(exc))
    if req is not None:
        facts["number"] = req.number
        facts["state"] = req.state
        return facts, ""
    base = _default_branch(clone)
    if not base:
        return facts, ("has no origin/HEAD, so charter cannot tell what to open the request "
                       "against. Run: git -C <clone> remote set-head origin -a")
    try:
        facts["number"] = forge.create_change(
            path, base, branch, _title_for(rec, m), _new_body(rec))
    except forgebase.ForgeWriteError as exc:
        return facts, contain.one_line(str(exc))
    facts["state"] = forgebase.REQUEST_OPEN
    facts["opened"] = True
    return facts, ""


def cmd_change_push(args) -> int:
    """Push every member's branch, open the requests, and write the cross-link block.

    Fire-and-report: one member's failure is reported and the rest still run, because a
    change whose third repository has no clone is not a reason to leave the first two
    unpushed. The exit code is non-zero if anything was refused, and the block is written
    with what charter actually knows — a member it could not open renders as ``—`` rather
    than being dropped from the table.
    """
    ws = _workspace(args)
    slug = args.change
    rec, code = _load(ws, slug)
    if rec is None:
        return code
    if not rec["members"]:
        util.err(f"change {contain.readable(slug)} has no members.")
        util.info(f"Add one: charter change add {contain.readable(slug)} <repo>")
        return REFUSED

    # `seen` is filled ONLY where all three of number, path and sigil are known, which is
    # what lets `cross_link_block` have one lookup and one fallback instead of three.
    seen: dict = {}
    forges: dict = {}
    failed = 0
    names = [contain.one_line(m["repo"]) for m in rec["members"]]
    w = tui.column("", names, gap=0)
    for m in rec["members"]:
        repo = m["repo"]
        facts, complaint = _push_one(ws, rec, m)
        if complaint:
            failed += 1
            util.err(f"{contain.one_line(repo)}: {complaint}")
            continue
        seen[repo] = (facts["number"], facts["path"], facts["sigil"])
        forges[repo] = facts["forge"]
        verb = "opened" if facts.get("opened") else "pushed"
        print(f"✓ {tui.pad(contain.one_line(repo), w)}  {verb}  -> "
              f"{facts['sigil']}{facts['number']}")

    block = cross_link_block(rec, seen)
    written, refused_bodies = 0, 0
    for repo, (number, path, sigil) in seen.items():
        forge = forges[repo]
        try:
            body = forge.change_body(path, number)
            spliced = splice_block(body, block)
            if spliced is None:
                refused_bodies += 1
                util.err(f"{contain.one_line(repo)}: {sigil}{number}'s body has no "
                         f"balanced charter block, so charter did not edit it. Charter owns "
                         f"only what is between {BLOCK_BEGIN!r} and {BLOCK_END!r}.")
                continue
            if spliced != body:
                forge.update_change_body(path, number, spliced)
            written += 1
        except forgebase.ForgeError as exc:
            refused_bodies += 1
            util.err(f"{contain.one_line(repo)}: {contain.one_line(str(exc))}")
    if written:
        print(f"✓ cross-link block written into {written} request "
              f"{'body' if written == 1 else 'bodies'}")
    return 1 if (failed or refused_bodies) else 0


# --------------------------------------------------------------------------------- #
# `charter change land` — one member, three gates, and the flag that does not exist   #
# --------------------------------------------------------------------------------- #
# **There is no `--all`.** It is not a flag that defaults off; the flag does not exist, and
# a test asserts it does not parse. ADR 0020.
#
# Two reasons, and the second is the stronger. ADR 0003 rejected a `--yes` on `charter
# report send` with one sentence — *"a flag the agent can pass is a flag the agent will pass
# unprompted, which is exactly the failure being prevented"* — and this is that flag for an
# operation whose blast radius is five repositories rather than one issue. And `--all` would
# have to answer a question with no answer: when member 3 of 5 is rejected mid-loop it must
# stop and leave two landed, continue and land the independents, or roll back what it did,
# and each is wrong in a case the others handle.
#
# The shell loop is not what is refused. A five-iteration loop over `charter change land` is
# five GATED landings, because the gates are in the command it calls; `--all` is one ungated
# one. **The refusal is not of repetition, it is of a code path that batches the gates.**

#: What the check gate says, per state, and each is its own sentence.
#:
#: Three gates in sequence mask each other and an exit-code assertion cannot tell them
#: apart, so each refusal names the thing it read and nothing else. In particular the
#: `not_run` message does not tell the reader what `gh pr checks` or `mergeStateStatus`
#: would have said here — that is true, it is in the spec, and it is an assertion about
#: tools charter did not run (ADR 0009's grain).
_CHECK_REFUSALS = {
    forgebase.CHECKS_NOT_RUN:
        "checks NOT RUN at {sha} — this head sha has no check run and no commit status. "
        "Nothing ran, or nothing has run yet.",
    forgebase.CHECKS_UNKNOWN:
        "checks UNKNOWN at {sha} — charter could not read them, or could not read all of "
        "them. It will not treat 'I did not look' as 'nothing to see'.",
    forgebase.CHECKS_FAILED:
        "checks FAILED at {sha} ({total}).",
    forgebase.CHECKS_RUNNING:
        "checks RUNNING at {sha} ({total}) — not a verdict yet.",
}


def _refuse(message: str) -> tuple[int, str]:
    util.err(message)
    return REFUSED, message


def _land(ws: str, args, fields: dict) -> tuple[int, str]:
    """The gates and the merge. ``(exit_code, refusal_or_empty)``.

    Split from :func:`cmd_change_land` so the trace call around it is unconditional and
    there is exactly one of it — the refusal path is traced identically to the success path,
    which is what makes *"which command landed what"* answerable after the fact.
    """
    slug = args.change
    fields["change"] = slug
    rec, code = _load(ws, slug)
    if rec is None:
        return code, "no such change"

    # `--rebase` before anything else: it is a refusal of the REQUEST, and running the gates
    # first would report a check failure for a landing charter was never going to perform.
    if getattr(args, "rebase", False):
        return _refuse(
            "charter does not land by rebase. A rebase merge replays the author's own "
            "commits and charter authors none of them, so there is no commit to carry "
            "`Charter-Change: " + contain.one_line(slug) + "` and no single sha for "
            "`charter change revert` to run against. Use --merge (the default) or --squash; "
            "a repository that permits only rebase is one a human lands by hand.")
    method = "squash" if getattr(args, "squash", False) else "merge"
    fields["method"] = method

    repo = args.repo
    fields["repo"] = repo
    m = change.member(rec, repo)
    if m is None:
        excluded = change.exclusion(rec, repo)
        if excluded is not None:
            return _refuse(f"{contain.readable(repo)} was excluded from "
                           f"{contain.readable(slug)}: {contain.one_line(excluded['why'])}")
        return _refuse(f"{contain.readable(repo)} is not a member of "
                       f"{contain.readable(slug)}.")

    forge, path, complaint = _member_forge(ws, m)
    if forge is None:
        return _refuse(f"{contain.one_line(repo)}: {complaint}")

    # --- gate (a): the member has a request, and it is open ---------------------------
    try:
        req = forge.request_for(path, m["branch"])
    except forgebase.ForgeError as exc:
        util.err(f"{contain.one_line(repo)}: {contain.one_line(str(exc))}")
        return 1, "request lookup failed"
    if req is None:
        return _refuse(f"{contain.one_line(repo)}: no request for branch "
                       f"{contain.readable(m['branch'])}. Push it first: "
                       f"charter change push {contain.readable(slug)}")
    fields["number"] = req.number
    fields["head"] = req.head
    if req.state == forgebase.REQUEST_MERGED:
        return _refuse(f"{contain.one_line(repo)}: {forge.change_sigil}{req.number} is "
                       f"already merged. Nothing to land.")
    if req.state != forgebase.REQUEST_OPEN:
        return _refuse(f"{contain.one_line(repo)}: {forge.change_sigil}{req.number} is "
                       f"REJECTED — closed unmerged. Narrow the change instead: "
                       f"charter change drop {contain.readable(slug)} "
                       f"{contain.readable(repo)} --why \"…\"")

    # --- gate (b): every repo in `needs` has landed -----------------------------------
    log = landings(ws, slug)
    for need in m["needs"]:
        blocker = change.member(rec, need)
        if blocker is None:
            return _refuse(f"{contain.one_line(repo)}: blocker "
                           f"{contain.readable(need)} is not a member of this change.")
        bforge, bpath, bcomplaint = _member_forge(ws, blocker)
        if bforge is None:
            return _refuse(f"{contain.one_line(repo)}: blocker "
                           f"{contain.one_line(need)} {bcomplaint}")
        try:
            landed, why = member_landed(ws, blocker, bforge, bpath, log)
        except forgebase.ForgeError as exc:
            util.err(f"{contain.one_line(repo)}: reading blocker "
                     f"{contain.one_line(need)}: {contain.one_line(str(exc))}")
            return 1, "blocker lookup failed"
        if not landed:
            return _refuse(f"{contain.one_line(repo)}: blocker "
                           f"{contain.readable(need)} has not landed ({why}).")

    # --- gate (c): the checks, at THIS head sha ---------------------------------------
    checks = forge.checks_at(path, req.head, req.number)
    fields["checks"] = checks.state
    if checks.state != forgebase.CHECKS_PASSED:
        template = _CHECK_REFUSALS.get(
            checks.state, "checks {state} at {sha} — charter will not land on that.")
        return _refuse(f"{contain.one_line(repo)}: " + template.format(
            sha=contain.one_line(req.head)[:12], state=checks.state,
            total="no runs" if not checks.total else f"{checks.total} runs"))
    print(f"• {contain.one_line(repo)}: checks PASSED at "
          f"{contain.one_line(req.head)[:12]} ({checks.total} runs)")

    # --- the merge ---------------------------------------------------------------------
    # There is deliberately no mergeability gate. Charter attempts the merge and the forge's
    # refusal IS the evidence — `planegit` already declines to ask whether a branch is
    # protected for exactly this reason, and the only field that would answer it is
    # `mergeStateStatus`, which reports CLEAN for a head nothing ever checked.
    trailer = f"Charter-Change: {contain.one_line(slug)}"
    title = f"{contain.one_line(slug)}: {contain.one_line(repo)} " \
            f"({forge.change_sigil}{req.number})"
    message = f"{contain.one_line(rec['why'])}\n\n{trailer}"
    try:
        forge.merge_change(path, req.number, method, title, message)
    except forgebase.ForgeError as exc:
        util.err(f"{contain.one_line(repo)}: {contain.one_line(str(exc))}")
        return 1, "merge failed"

    # --- the read-back (ADR 0013) ------------------------------------------------------
    # A success line reports what charter CONFIRMED, not what it asked for. The sha printed,
    # traced and written to the log is the one the forge answers with on a fresh read.
    try:
        after = forge.request_for(path, m["branch"])
    except forgebase.ForgeError as exc:
        util.err(f"{contain.one_line(repo)}: merged, but the read-back failed "
                 f"({contain.one_line(str(exc))}) — nothing was recorded.")
        return 1, "read-back failed"
    if after is None or after.state != forgebase.REQUEST_MERGED or not after.merge:
        util.err(f"{contain.one_line(repo)}: the forge did not confirm the merge on a "
                 f"read-back — nothing was recorded.")
        return 1, "read-back did not confirm"

    _append_landing(ws, slug, repo, after.number, req.head, after.merge)
    fields["merge"] = after.merge
    print(f"✓ merged {forge.change_sigil}{after.number} as "
          f"{contain.one_line(after.merge)[:12]}, trailer {trailer}")
    return 0, ""


def cmd_change_land(args) -> int:
    """Land **one** member. See the section comment above for why there is no `--all`.

    Traced unconditionally, refusals included (§6.3). The security assessment found
    `commands_secrets.py` had no trace calls at all, so after the fact charter could not
    answer *"which command received the prod token"*, and called fixing that the
    highest-value observability change in the repo. A surface that merges code into several
    repositories does not get to ship without it.
    """
    ws = _workspace(args)
    fields: dict = {"workspace": ws}
    # Seeded, and written in a `finally`, so an exception on the way through is traced too:
    # "charter was asked to land this and something went wrong" is exactly the row whose
    # absence made the last surface unanswerable after the fact.
    refused = "unhandled error"
    try:
        code, refused = _land(ws, args, fields)
    finally:
        trace.record("change-land", refused=refused or None, **fields)
    return code


# --------------------------------------------------------------------------------- #
# `charter change show`'s derived columns                                             #
# --------------------------------------------------------------------------------- #
# §3.4 calls `show` the monorepo view, and being a VIEW is what makes it correct: the clones
# are already siblings under one workspace directory, so `rg` already spans the change. What
# was missing is the knowing, and the knowing includes what each member's request and checks
# are doing right now.
#
# **Derived, never stored.** Nothing here is written back. The record still holds no request
# number, no check result and no landed flag — the value of this block is that it is a
# reading taken at one moment and thrown away, so nothing on disk can disagree with git.

def _observed_row(ws: str, m: dict, log: dict) -> tuple[str, str] | None:
    """``(state_cell, detail)`` for one member, or ``None`` when there is no forge to ask.

    A clone with no ``origin``, or one on a host this plane does not declare, produces
    ``None`` and the whole block is skipped for it — an honest silence rather than a row of
    dashes implying charter looked. A forge that *is* there and would not answer produces
    ``UNKNOWN``, which is a different sentence and is never green.
    """
    forge, path, _complaint = _member_forge(ws, m)
    if forge is None:
        return None
    try:
        req = forge.request_for(path, m["branch"])
        if req is None:
            return "no request", ""
        if req.state == forgebase.REQUEST_MERGED:
            landed, why = member_landed(ws, m, forge, path, log)
            return ("landed" if landed else "merged"),  \
                   (f"{forge.change_sigil}{req.number}  "
                    f"{contain.one_line(req.merge or '')[:12]}"
                    + (f"  ({why})" if why else ""))
        if req.state == forgebase.REQUEST_CLOSED:
            return "REJECTED", f"{forge.change_sigil}{req.number} closed unmerged"
        checks = forge.checks_at(path, req.head, req.number)
        return ("open",
                f"{forge.change_sigil}{req.number}  "
                f"{checks.state.replace('_', ' ').upper()} "
                f"at {contain.one_line(req.head)[:12]}")
    except forgebase.ForgeError as exc:
        return "UNKNOWN", contain.one_line(str(exc))


def show_observed(ws: str, rec: dict) -> list[str]:
    """The derived block's lines, or ``[]`` when no member resolves to a forge.

    Public because that emptiness is the thing worth pinning: a change whose clones charter
    cannot resolve prints exactly what it printed before this existed, rather than a block
    of "unknown" rows that look like an answer.
    """
    log = landings(ws, rec["change"])
    rows = []
    for m in rec["members"]:
        observed = _observed_row(ws, m, log)
        if observed is not None:
            rows.append((contain.one_line(m["repo"]), observed[0], observed[1]))
    if not rows:
        return []
    landed = sum(1 for _, state, _ in rows if state == "landed")
    # Never greener than the worst member, and no single word the change as a whole can
    # hide behind: the count is printed, and every member is listed under it.
    head = (f"  {landed} of {len(rec['members'])} landed"
            if landed else f"  0 of {len(rec['members'])} landed")
    w = tui.column("", [r[0] for r in rows], gap=0)
    sw = tui.column("", [r[1] for r in rows], gap=0)
    return [head] + [f"  {tui.pad(name, w)}  {tui.pad(state, sw)}  {detail}".rstrip()
                     for name, state, detail in rows]
