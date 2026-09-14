"""Centralized memory retrieval — the single gate for fetching across every memory base.

There are several memory *stores*, on two independent axes: the active **workspace**'s task
journal, the active **persona**'s own role memory, the cross-role **shared** namespace, and
(opt-in) the persona's **ephemeral** session scratch. Storage stays per-base — they're
genuinely different axes — but *reading* is unified here: a caller asks once and gets ranked,
**source-labeled** hits, without needing to know which base a fact lives in.

This is the one place memory is fetched. It sits on the shared :mod:`charter.memstore` engine
(whose ``search`` already ranks across a list of dirs); this module adds the context-aware
assembly of *which* dirs are in scope and tags each result with where it came from.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import NamedTuple

from . import config, contain, memstore

#: The selectable scopes, in the order they're assembled/displayed.
SCOPES = ("workspace", "persona", "shared", "ephemeral", "refs")
#: `refs` is DEFAULT-ON, unlike `ephemeral`. The distinction is standing, not size: refs are
#: committed, curated and shared — the same standing the other three defaults have — while
#: ephemeral is session scratch. Opt-in would also fix only the letter of #178: an agent that
#: must already know to ask for refs is in exactly the position the report describes, told
#: with a straight face that the runbook does not exist.
DEFAULT_SCOPES = ("workspace", "persona", "shared", "refs")


class Hit(NamedTuple):
    """One recalled memory. A NamedTuple rather than a bare tuple because this grew a field
    once (``date``) and every positional unpack in the codebase broke at the same time —
    the next field should not cost that again."""
    label: str
    path: Path
    title: str
    score: int
    date: datetime.date | None


class Recalled(NamedTuple):
    """Hits, plus what was *withheld*. ``undated`` counts memories a ``since`` filter could
    not place in time (no in-body stamp, no date-prefixed filename) and therefore dropped.
    Reported rather than silently discarded: a filter that hides what it excluded is a
    filter you cannot trust — and 0 undated is the common case, so it costs nothing."""
    hits: list[Hit]
    undated: int
    #: Refs excluded by `since`. Counted apart from `undated` because they are different
    #: facts: an undated MEMORY lost a stamp it was supposed to carry, while a refs document
    #: never had one — a date filter over undated documents can only lie or pass everything,
    #: so refs are excluded, and the message must not blame them for a missing stamp (#178).
    #: Defaulted so existing positional unpacking of (hits, undated) keeps working — this
    #: NamedTuple's own docstring records what happened the last time a field was added.
    undated_refs: int = 0
    #: Each base it could not read, as ``(directory, errno)`` (#1084). A search that did not
    #: look is not a search that found nothing, so the caller names these rather than letting
    #: "no memories match" stand for them. Defaulted for the same reason as the field above.
    unread: list | tuple = ()


#: `14d` / `2w` / `3m`. Months are 30 days — predictable beats calendar-correct for a
#: filter whose whole job is "roughly two weeks ago".
_REL_RE = re.compile(r"^(\d+)([dwm])$")
_REL_DAYS = {"d": 1, "w": 7, "m": 30}


def parse_since(value: str, today: datetime.date | None = None) -> datetime.date:
    """The earliest date a ``--since`` filter accepts. Takes a relative age (``14d``,
    ``2w``, ``3m``) or an ISO date (``2026-07-01``).

    Raises ``ValueError`` on anything else — deliberately, rather than falling back to no
    filter. A silently-ignored ``--since`` returns MORE than was asked for, and a reader
    then takes a full corpus as proof that nothing was recorded recently. A future date is
    accepted and simply matches nothing; that is a real answer, not an error."""
    s = (value or "").strip()
    m = _REL_RE.fullmatch(s)
    if m:
        return (today or datetime.date.today()) - datetime.timedelta(
            days=int(m.group(1)) * _REL_DAYS[m.group(2)])
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        raise ValueError(
            f"unrecognised --since {value!r} — use an age (14d, 2w, 3m) or a date (2026-07-01)"
        ) from None


def sources(session_id: str | None = None, persona_name: str | None = None,
            workspace_name: str | None = None, scopes=DEFAULT_SCOPES,
            all_workspaces: bool = False) -> list[tuple[str, Path]]:
    """``[(source_label, memory_dir)]`` for the requested scopes in the current context.
    Resolves the active workspace/persona unless overridden. Skips a scope with no owner
    (e.g. no active persona → no persona/ephemeral rows).

    ``all_workspaces`` widens the WORKSPACE axis only — one base per workspace, LOCAL and
    LIVE alike (that setting governs what is committed, not what you may search on your own
    machine). Persona and shared memory are not workspace-scoped, so they stay single rows;
    emitting them once per workspace would multiply every role fact by the workspace count.
    """
    from . import workspace as ws_mod, persona as p_mod
    out: list[tuple[str, Path]] = []
    if "workspace" in scopes:
        if all_workspaces:
            for ws in ws_mod.list_workspaces():
                out.append((f"workspace:{ws}", ws_mod.memory_dir(ws)))
        else:
            ws = workspace_name or ws_mod.resolve(session_id=session_id)
            out.append((f"workspace:{ws}", ws_mod.memory_dir(ws)))
    name = persona_name or p_mod.resolve_active()
    if "persona" in scopes and name:
        out.append((f"persona:{name}", p_mod.memory_dir(name)))
    if "ephemeral" in scopes and name:
        out.append((f"persona:{name}:ephemeral", p_mod.ephemeral_dir(name, session=session_id)))
    if "shared" in scopes:
        out.append(("shared", p_mod.memory_dir(config.SHARED_PERSONA, shared=True)))
    if "refs" in scopes:
        # A different KIND of knowledge, not a different owner: curated documents rather
        # than recorded facts. Its own scope so `--scope persona` can still mean only
        # memory — the one thing someone narrowing scope usually wants (#178).
        if name:
            for d in _ref_dirs(p_mod.refs_dir(name)):
                out.append((f"refs:{name}", d))
        for d in _ref_dirs(p_mod.refs_dir(config.SHARED_PERSONA, shared=True)):
            out.append(("refs:shared", d))
    return out


def _ref_dirs(base: Path) -> list[Path]:
    """*base* and every directory under it.

    Refs NEST — the reporting plane's own example is `refs/release/keycloak-prerequisites.md`
    — while `memstore.files` is a flat `*.md` glob, because memory is flat by construction.
    Rather than teach the memory engine to recurse (and change what every other base
    searches), each subdirectory is offered as its own source. `memstore.search` already
    takes a list of dirs, so recursion falls out of the assembly step where the shape
    difference actually lives.

    Every directory offered here is one `memstore.files` will list, so each is contained
    first. ``rglob`` does not descend *into* a symlinked directory, but it still yields the
    link itself and ``is_dir()`` follows it — so an escape needs no depth: one committed
    link at the top of `refs/` is enough, and the label this module derives for anything
    read out of it degrades to ``?``, which is the provenance the reader would most want to
    be right (#336).
    """
    if not base.exists() or contain.dir_refusal(base):
        return []
    try:
        return [base, *(d for d in sorted(base.rglob("*"))
                        if d.is_dir() and not contain.dir_refusal(d))]
    except OSError:
        return [base]


def _label_of(path: Path, srcs: list[tuple[str, Path]]) -> str:
    for lbl, d in srcs:
        try:
            Path(path).resolve().relative_to(Path(d).resolve())
            return lbl
        except (ValueError, OSError):
            continue
    return "?"


def recall(query: str | None = None, session_id: str | None = None, limit: int = 8,
           persona_name: str | None = None, workspace_name: str | None = None,
           scopes=DEFAULT_SCOPES, since: datetime.date | None = None,
           all_workspaces: bool = False) -> Recalled:
    """THE memory fetch gate. With a ``query`` → keyword-ranked hits across all in-scope
    bases (title hits weigh 3×, via the memstore engine). Without → every in-scope memory,
    newest-first by recorded date. ``limit`` caps the results (``0`` = no cap).

    ``since`` drops anything recorded earlier, on the same ``memstore.memory_date`` key the
    no-query listing already sorts by — so the filter and the order can never disagree. It
    **narrows, it never re-ranks**: with a query the survivors stay in score order, because
    someone who typed a keyword asked for relevance, and quietly re-sorting by date would
    change what "best match" means without saying so.

    A base it could not read is searched around, not through: the hits are what the others held,
    and :attr:`Recalled.unread` names each one it could not, for the caller to say (#1084).
    """
    srcs = sources(session_id=session_id, persona_name=persona_name,
                   workspace_name=workspace_name, scopes=scopes,
                   all_workspaces=all_workspaces)
    dirs = [d for _lbl, d in srcs]
    undated = undated_refs = 0
    unread: list[tuple[Path, int | None]] = []

    def _dated(p: Path) -> datetime.date | None:
        try:
            return memstore.memory_date(p.read_text(), p.name)
        except OSError:
            return None

    if query:
        rows = []
        for p, title, score in memstore.search(dirs, query, 0 or 10_000, unread=unread):
            d = _dated(p)
            lbl = _label_of(p, srcs)
            if since is not None and (d is None or d < since):
                if lbl.startswith("refs"):
                    undated_refs += 1
                else:
                    undated += d is None
                continue
            rows.append(Hit(lbl, p, title, score, d))
        return Recalled(rows[:limit] if limit else rows, undated, undated_refs, unread)

    items: list[tuple[datetime.date, Hit]] = []
    for lbl, d in srcs:
        found, missed = memstore.read_entries(d)
        unread.extend(missed)
        for p, title, text in found:
            dt = memstore.memory_date(text, p.name)
            if since is not None and (dt is None or dt < since):
                if lbl.startswith("refs"):
                    undated_refs += 1
                else:
                    undated += dt is None
                continue
            # `date.min` puts undated last without dropping them: "list everything" must not
            # silently omit the larger half of the corpus.
            items.append((dt or datetime.date.min, Hit(lbl, p, title, 0, dt)))
    items.sort(key=lambda x: x[0], reverse=True)
    rows = [h for _dt, h in items]
    return Recalled(rows[:limit] if limit else rows, undated, undated_refs, unread)
