"""A tiny per-file **memory store**: one markdown file per fact, plus a ``MEMORY.md``
index, in a directory. Keyword search, near-duplicate detection, and forget-by-slug — a
small, programmatically-explorable "DB" rather than one ever-growing file, so concurrent
writers don't conflict on a shared log.

Shared by **persona** memory (role knowledge) and **workspace** memory (task journal) so
both behave the same. A store can be ``timestamped`` — filenames get a
``YYYYMMDD-HHMMSS-`` prefix so a directory listing (and the index) orders chronologically;
that's the default for the workspace journal, where "when" matters. Persona memory keeps
its slug-only names (addressed by slug in ``forget``/``recall``).

Each memory file:  ``# <title>\\n\\n_<stamp> · <kind>_\\n\\n<body>\\n``
Never store secrets here — memory is committed + shared; secrets live only in the vault."""

from __future__ import annotations

import datetime
import re
from pathlib import Path

from . import config, contain

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug(title: str) -> str:
    s = _SLUG_RE.sub("-", (title or "").lower()).strip("-")
    return s[:48] or "note"


#: The longest a memory title may be. It becomes a `# ` heading, an index row and — through
#: :func:`slug` — part of a filename, so it is one line and it is short.
TITLE_MAX = 72


def title_of(text: str) -> str:
    """The title :func:`write` derives from a memory's body: its first line, capped.

    **Its own function because a READER has to be able to compute the same string.**
    `todos.duplicate_of` asks whether a todo it is about to write already exists, and one
    side of that comparison is a title `write` derived this way — so a second spelling of
    "the first line, stripped, capped" is how the writer and the reader come to disagree
    about which todos are the same one.

    ``""`` for a body with nothing in it; :func:`write` refuses such a body outright.

    **One `strip`, on the line, rather than one on the body and one on the line.** The
    outer one only ever skipped leading blank lines — its trailing half was redundant with
    the inner one, so `strip` and `lstrip` answered alike there for every input and the
    deletion sweep had a synonym nothing could settle. Written as the loop it is, "how
    much" is asked once and a title with padding at either end pins it.
    """
    for line in (text or "").splitlines():
        title = line.strip()
        if title:
            return title[:TITLE_MAX]
    return ""


def index_path(mem_dir: Path) -> Path:
    return mem_dir / "MEMORY.md"


def _now() -> datetime.datetime:
    return datetime.datetime.now()


#: **The one gate on the write side**, the mirror of :func:`files` on the read side and
#: for the same stated reason: containment asserted once rather than at four callers,
#: three of which stay correct. Every write this module performs goes through it, and it
#: checks both the file and the directory holding it — ``MEMORY.md`` is a fixed name, so
#: an attacker needs no guess and wins no race, and a linked ``memory/`` hides the file
#: check entirely (#349).
writable = contain.writable

#: **The one gate on the MODE side**, for the same reason and at the same three writes.
#: This module is handed its directory: ``personas/<n>/memory`` (committed, the operator's
#: to mode) on one call and ``PERSONA_STATE_DIR/ephemeral/<sid>/<n>`` (charter's own state,
#: which must be 0700 whatever the umask says) on the next. A bare
#: ``mkdir(parents=True, exist_ok=True)`` here is what created ``.charter/`` at 0755 on a
#: fresh clone, and no reader of this file could have told — only the caller knows which
#: quadrant it is. `config.mkdir_for` asks at runtime (#470).
mkdir_for = config.mkdir_for


def ensure_index(mem_dir: Path, header: str) -> Path:
    """Create the dir + MEMORY.md (with *header*) if missing; return the index path."""
    # Gated BEFORE the mkdir: `mkdir(exist_ok=True)` accepts a committed symlink to a
    # directory outside the plane, and would then create that directory's missing parents
    # for the attacker on the way past.
    idx = writable(index_path(mem_dir))
    mkdir_for(mem_dir)
    if not idx.exists():
        # `create_for`, not `write_for` (#1037): `exists()` is False for a dangling link too, and
        # `writable` above follows one that lands inside the plane, so a plain write created the
        # file the link named. Exclusive, so the kernel refuses the link however it got there.
        config.create_for(idx, header if header.endswith("\n") else header + "\n")
    return idx


def write(mem_dir: Path, text: str, title: str | None = None, *, timestamped: bool = False,
          kind: str = "persistent", index: bool = True,
          stamp: datetime.datetime | None = None) -> Path:
    """Write one memory file into *mem_dir* and (unless ``index=False``) append it to the
    index. ``timestamped`` prefixes the filename with ``YYYYMMDD-HHMMSS-`` for chronological
    ordering. Returns the path. Raises ValueError on empty text — secrets must never pass here."""
    text = (text or "").strip()
    if not text:
        raise ValueError("empty memory")
    title = title.strip()[:TITLE_MAX] if title else title_of(text)
    # Before the mkdir, and before a byte is written: both targets are checked up front so
    # a refusal leaves the store exactly as it was, rather than a memory file on disk that
    # nothing indexes.
    refusal = contain.dir_refusal(mem_dir, "write")
    if refusal:
        raise contain.Refused(refusal)
    mkdir_for(mem_dir)
    now = stamp or _now()
    prefix = now.strftime("%Y%m%d-%H%M%S-") if timestamped else ""
    base = slug(title)
    p = mem_dir / f"{prefix}{base}.md"
    i = 2
    while p.exists():  # same title (and same second) → keep both
        p = mem_dir / f"{prefix}{base}-{i}.md"
        i += 1
    # `exists()` is false for a DANGLING link, so the loop above stops on exactly the
    # entry that would create a file wherever it points. `writable` resolves it.
    writable(p)
    if index:
        writable(index_path(mem_dir))
    config.write_for(
        p, f"# {title}\n\n_{now.strftime('%Y-%m-%d %H:%M')} · {kind}_\n\n{text}\n")
    if index:
        index_append(index_path(mem_dir), p.name, title)
    return p


def index_append(idx: Path, filename: str, title: str) -> None:
    idx = writable(idx)
    if not idx.exists():
        mkdir_for(idx.parent)
        config.write_for(idx, "# Memory Index\n\n")
    with config.open_for(idx, "a") as f:
        f.write(f"- [{title}]({filename})\n")


_STAMP_RE = re.compile(r"^_(\d{4}-\d{2}-\d{2})[ T]", re.M)


def memory_date(text: str, filename: str = ""):
    """The date a memory was recorded — from its in-body ``_YYYY-MM-DD …_`` stamp (universal,
    written by :func:`write`), falling back to a ``YYYYMMDD-`` filename prefix. ``date`` or None."""
    import datetime
    m = _STAMP_RE.search(text or "")
    if m:
        try:
            return datetime.date.fromisoformat(m.group(1))
        except ValueError:
            pass
    fm = re.match(r"(\d{4})(\d{2})(\d{2})-", filename or "")
    if fm:
        try:
            return datetime.date(int(fm.group(1)), int(fm.group(2)), int(fm.group(3)))
        except ValueError:
            pass
    return None


def files(mem_dir: Path) -> list[Path]:
    """Every memory file in *mem_dir* charter may read (sorted — chronological when
    timestamped).

    **The one gate.** Everything that reaches a memory, a todo or a ref goes through here
    — :func:`entries`, :func:`search`, :func:`resolve`, `index_drift`, `curate.report`,
    `todos.count_open` — so containment is asserted once rather than at six callers, five
    of which stay correct. A file this refuses is not "a memory that failed to load": it
    is not a memory, and the count, the index-drift report and the search all agree about
    that because they ask the same function (#336).

    Two questions, both from :mod:`charter.contain`: the *directory* must resolve inside
    the plane's data (paid once — it is what catches a linked ``memory/`` whose contents
    are all ordinary files), and each entry must be a plain contained file (one ``lstat``
    each).

    **A directory it could not look at is not an empty one** (#1084). `Path.glob` answered ``[]``
    for a `memory/` it may not list, so `charter recall` said "No memories match" of a search that
    never looked. This raises :class:`workspace.CannotCheck` instead, naming what it could not
    read; a caller with a partial answer to give asks :func:`read_files`.
    """
    found, unread = read_files(mem_dir)
    if unread:
        from . import workspace
        raise workspace.CannotCheck(unread)
    return found


def read_files(mem_dir: Path) -> tuple[list[Path], list[tuple[Path, int | None]]]:
    """:func:`files`, and beside them what could not be read, with its errno — ``(files,
    unread)``, in `workspace.read_directory`'s shape and through it (#1084).

    *unread* is *mem_dir* itself when it cannot be listed (mode 000 or 333, a link loop, a parent
    charter may not search), or each entry whose own ``lstat`` is refused (a directory at mode
    666). A directory that is not there, or that containment refuses, is ``([], [])``, as before:
    the first holds nothing, and the second is `contain`'s refusal, which `doctor` names on its
    own terms.
    """
    from . import workspace
    if contain.dir_refusal(mem_dir):
        return [], []

    def keep(p: Path) -> tuple[bool | None, int | None]:
        if p.name == "MEMORY.md" or not p.name.endswith(".md"):
            return False, None
        if not contain.file_refusal(p):
            return True, None
        # Refused: asked why only here, so a readable store pays no second `lstat`. An entry
        # whose `lstat` is refused is one charter could not look at, not "not a memory".
        seen, errno_ = workspace._existence(p)
        return (None, errno_) if seen is None else (False, None)

    try:
        return workspace.read_directory(mem_dir, keep)
    except OSError as e:
        return [], [(mem_dir, e.errno)]


#: A memory FILENAME is a bare slug — no slash, space or colon. Matching only that
#: shape keeps a title containing a URL-ish `](…md` fragment (API paths do) from being
#: mistaken for a listed file.
_INDEX_LINK_RE = re.compile(r"\(([A-Za-z0-9][\w.-]*\.md)\)")


def index_drift(mem_dir: Path) -> dict[str, list[str]]:
    """Compare MEMORY.md's links against the files actually present.

    Returns ``{"dangling": [...], "unindexed": [...]}`` — links pointing at a file
    that isn't there, and files no link points at. Both are reachable without any
    concurrency bug: MEMORY.md is append-heavy and edited by many agents and
    humans at once, so a merge resolved by taking one side drops the other's
    line while its file survives.

    Cheap by design (one read + one glob, no file contents): `doctor` calls this
    for every memory base, and runs from the SessionStart hook.
    """
    actual = {p.name for p in files(mem_dir)}
    listed = _listed(mem_dir)
    return {"dangling": sorted(listed - actual), "unindexed": sorted(actual - listed)}


def index_refusal(mem_dir: Path) -> str | None:
    """Why charter will not touch this base's ``MEMORY.md``, or ``None``.

    Public because a refusal here is the one that hides. A refused *memory* still leaves
    the other memories to list, so the store visibly shrinks; a refused *index* answers
    with an empty set, which a base that simply has no memories yet answers with too. On
    a store whose files were also refused, `doctor` reported "consistent" over an index
    pointing at a credential file.

    So the reason is exported rather than swallowed, and `doctor` prints it. ADR 0009:
    name what was actually checked. "1 unindexed" is true and sends the operator to
    `charter persona optimize`, which cannot repair an index charter declines to write.

    **The write-side rule, deliberately, even though `_listed` reads.** An index that is
    simply *absent* is not a defect — `charter init` scaffolds a front door whose
    `memory/` holds a `.gitkeep` and no `MEMORY.md` — so the read-side gate's "not there
    is a refusal" reported every fresh plane as broken. `write_refusal` still catches the
    case `exists()` cannot see: a **dangling** link that escapes, which is absent and
    hostile at the same time. `_listed` is unaffected either way, because a missing file
    and a refused one both leave it with nothing listed.
    """
    return (contain.dir_refusal(mem_dir, "write")
            or contain.write_refusal(index_path(mem_dir)))


def _listed(mem_dir: Path) -> set[str]:
    """The filenames MEMORY.md links to — ``set()`` when charter may not read it.

    **The one read `files()` never covered**, because ``MEMORY.md`` is the single name it
    filters out (`p.name != "MEMORY.md"`). So the file with the most predictable name in
    the store was the only one with no gate on either side (#336, #349). `doctor` reads
    this for every memory base on every SessionStart, where a FIFO costs the briefing and
    a link reads whatever it points at.

    An unreadable index answers ``set()`` rather than raising, matching `files()`: the
    drift report then shows every file as unindexed, which is true — nothing charter is
    willing to read indexes them — and is what surfaces the defect to the operator.
    """
    if index_refusal(mem_dir):
        return set()
    try:
        return set(_INDEX_LINK_RE.findall(index_path(mem_dir).read_text()))
    except OSError:
        return set()


def index_size(mem_dir: Path) -> int:
    """How many memories a base holds — the growth signal `doctor` reports.

    Counts files, not index lines: the files are the truth, and a base mid-drift
    would otherwise report a number that disagrees with `index_drift`.
    """
    return len(files(mem_dir))


def entries(mem_dir: Path) -> list[tuple[Path, str, str]]:
    """(path, title, text) per memory; title = first '# ' line, else the file stem.

    Raises :class:`workspace.CannotCheck` for what it could not list, as :func:`files` does."""
    return _entries_of(files(mem_dir))


def read_entries(mem_dir: Path) -> tuple[list[tuple[Path, str, str]],
                                         list[tuple[Path, int | None]]]:
    """:func:`entries`, and beside them what could not be read — :func:`read_files`' shape."""
    found, unread = read_files(mem_dir)
    return _entries_of(found), unread


def gather(dirs, unread: list | None = None) -> list[tuple[Path, str, str]]:
    """The entries of every one of *dirs*. With an *unread* list, each directory it could not
    read is added to it and the rest are still read; without one, the first raises (#1084)."""
    ents = []
    for d in dirs:
        if unread is None:
            ents += entries(d)
            continue
        found, missed = read_entries(d)
        ents += found
        unread.extend(missed)
    return ents


def _entries_of(paths: list[Path]) -> list[tuple[Path, str, str]]:
    out = []
    for p in paths:
        try:
            text = p.read_text()
        except OSError:
            continue
        title = p.stem
        for ln in text.splitlines():
            if ln.startswith("# "):
                title = ln[2:].strip()
                break
        out.append((p, title, text))
    return out


#: Words carrying no signal, dropped so they cannot outvote the term that mattered.
#: Scoring is raw `count()` with no IDF, so before this "for" in a long memory could beat
#: a single exact hit on the one word the user actually searched for.
_STOPWORDS = frozenset("""
a an the and or but if then than that this these those of in on at to for from by with
without as is are was were be been being it its it's do does did done have has had
you your we our i my me they them their he she his her not no yes so such can could
should would will shall may might must about into over under again more most some any
""".split())


def _terms(s: str) -> list[str]:
    """Query tokens worth scoring.

    The length floor is **2**, not 3. At 3 it silently discarded every two-character
    token, so `recall "S3"`, `"CI"`, `"db"`, `"PR"`, `"TZ"` and `"v2"` each returned a
    confident "No memories match" against a corpus that contained them — and search is
    the only route to memories beyond the ten titles the session briefing lists, so a
    false negative here is indistinguishable from the fact not existing.

    Single characters stay out: they match nearly everything and rank nothing.
    """
    return [t for t in re.split(r"\W+", (s or "").lower())
            if len(t) >= 2 and t not in _STOPWORDS]


def dropped_terms(s: str) -> list[str]:
    """Tokens in *s* that :func:`_terms` discarded. Lets a caller tell "nothing matched"
    from "nothing was searched for" — printing the first when it is really the second is
    how a query like `recall "in CI"` reported an empty corpus."""
    raw = [t for t in re.split(r"\W+", (s or "").lower()) if t]
    return [t for t in raw if len(t) < 2 or t in _STOPWORDS]


def search(dirs, query: str, limit: int = 8,
           unread: list | None = None) -> list[tuple[Path, str, int]]:
    """Keyword-rank memories across one or more *dirs* against *query* (stdlib, no
    vectors). Title hits weigh 3×. Returns [(path, title, score)] best-first.

    Terms match on a word BOUNDARY (``\\bterm``) rather than as bare substrings, so
    "version" no longer scores inside "conversion" and a short token like "db" no longer
    hits every "dbname" in the corpus. Prefixes still count — "version" matches
    "versioned" — which is the cheap half of stemming without the maintenance of the
    other half.

    A directory it could not list is added to *unread* and the rest are still searched; with
    no *unread* list to name it in, the search refuses (:class:`workspace.CannotCheck`) rather
    than rank what it did not read as nothing (#1084).
    """
    terms = _terms(query)
    if not terms:
        return []
    pats = [(t, re.compile(rf"\b{re.escape(t)}\w*")) for t in terms]
    ents = gather(dirs, unread)
    scored = []
    for p, title, text in ents:
        low, tl = text.lower(), title.lower()
        score = sum(3 * len(pat.findall(tl)) + len(pat.findall(low)) for _t, pat in pats)
        if score:
            scored.append((score, str(p), p, title))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [(p, title, score) for score, _s, p, title in scored[:limit]]


def wordset(text: str) -> set[str]:
    """The comparable words in *text* — the tokenizer :func:`duplicates` scores with.

    Public because near-duplicate detection has a second caller (the todo store, which asks
    "would this new text duplicate an existing one?" rather than "which stored pairs
    duplicate each other?"). Both must tokenize identically or the shared threshold means
    two different things.
    """
    return {w for w in re.split(r"\W+", text.lower()) if len(w) > 3}


def duplicates(dirs, threshold: float = 0.5,
               unread: list | None = None) -> list[tuple[float, Path, str, Path, str]]:
    """Near-duplicate memory pairs by Jaccard word overlap ≥ *threshold* across *dirs*.

    What it could not list goes to *unread*, or refuses without one — :func:`search`'s rule."""
    ents = gather(dirs, unread)
    sets = [(p, title, wordset(text)) for p, title, text in ents]
    dupes = []
    for i in range(len(sets)):
        pa, ta, sa = sets[i]
        for j in range(i + 1, len(sets)):
            pb, tb, sb = sets[j]
            if not sa or not sb:
                continue
            jac = len(sa & sb) / len(sa | sb)
            if jac >= threshold:
                dupes.append((jac, pa, ta, pb, tb))
    dupes.sort(key=lambda x: -x[0])
    return dupes


def resolve(mem_dir: Path, ident: str) -> Path | None:
    """Find a memory file by full filename or slug — matching ``<slug>.md`` or, for a
    timestamped store, ``<prefix>-<slug>.md``. First match wins."""
    name = ident if ident.endswith(".md") else f"{ident}.md"
    p = mem_dir / name
    # The direct hit asks the filesystem rather than the listing, so it needs the listing's
    # gate spelled out: without it `forget`/`show` would reach a file `files()` refuses,
    # which is the same read arriving by a shorter route (#336).
    # Asked through `_existence`, not `Path.exists`, which raised past every handler for a
    # store at mode 000 on 3.11–3.13 and answered "not there" on 3.14 (#1084). Either way the
    # listing below is what then names the directory it could not read.
    from . import workspace
    if (workspace._existence(p, follow=True)[0] is True
            and not (contain.dir_refusal(mem_dir) or contain.file_refusal(p))):
        return p
    hits = [q for q in files(mem_dir) if q.name == name or q.name.endswith(f"-{name}")]
    return hits[0] if hits else None


def forget(mem_dir: Path, ident: str) -> Path | None:
    """Delete one memory (by filename or slug) and drop its index line.

    Returns the path that was removed, so the caller can stage the deletion — `remember`
    is reactive and `forget` was not, which meant a purge stayed on the machine that ran
    it while the memory it removed lived on in the remote and came back with the next
    pull. Removal is the operation that most needs to propagate: it is how a poisoned or
    secret-bearing memory is taken out of circulation (#82).

    Falsy when nothing matched, as before — a `Path` is truthy, so callers testing the
    result still read correctly.
    """
    p = resolve(mem_dir, ident)
    if not p or not p.exists():
        return None
    p.unlink()
    _drop_index_line(mem_dir, p.name)
    return p


def _drop_index_line(mem_dir: Path, filename: str) -> None:
    """Remove *filename*'s line from the index — the store's only **truncating** write.

    Where `index_append` adds two lines to whatever a link points at, this replaces the
    target with what survived a filter, so pointed at a credential store it destroys it
    outright rather than corrupting it. `file_refusal` is the right gate here rather than
    `write_refusal`: the file must already exist for there to be a line to drop, so ENOENT
    is genuinely "nothing to do" on both sides of the question.

    Refuses by doing nothing, deliberately — unlike `write`, this runs *after* `forget`
    and `archive` have already moved the memory file, so raising would report a failure
    for work that succeeded. The index left holding a stale line is a file charter has
    declined to read, which `index_drift` reports as drift on the next `doctor`.
    """
    idx = index_path(mem_dir)
    if not idx.exists() or contain.dir_refusal(mem_dir, "write") or contain.file_refusal(idx):
        return
    keep = [ln for ln in idx.read_text().splitlines() if f"({filename})" not in ln]
    config.write_for(idx, "\n".join(keep) + ("\n" if keep else ""))


def body(text: str) -> str:
    """A memory's content with the ``# title`` and ``_stamp_`` header lines stripped and
    whitespace normalized — the basis for EXACT-duplicate comparison (same fact, maybe
    recorded twice with different timestamps/titles)."""
    lines = (text or "").splitlines()
    kept = [ln for ln in lines
            if not ln.startswith("# ") and not re.match(r"^_.*·.*_\s*$", ln.strip())]
    return re.sub(r"\s+", " ", " ".join(kept)).strip().lower()


def archive(mem_dir: Path, ident: str) -> Path | None:
    """Move one memory into ``<mem_dir>/archive/`` (out of the active glob, so it drops
    from search/recall/stats) and remove its index line — a **reversible** retire that
    keeps the file on disk + in git history. Returns the new path, or None if not found."""
    p = resolve(mem_dir, ident)
    if not p or not p.exists():
        return None
    dest_dir = mem_dir / "archive"
    # The fifth fixed name in the store, and the one #349 did not list. `rename` follows a
    # link on the destination directory exactly as `open` follows one on a file, so a
    # committed `archive` → elsewhere turns a retire into a move out of the plane. Answers
    # None like every other "nothing was archived", rather than raising into `curate`'s
    # batch.
    if contain.dir_refusal(dest_dir, "write"):
        return None
    mkdir_for(dest_dir)
    dest = dest_dir / p.name
    i = 2
    while dest.exists():
        dest = dest_dir / f"{dest.stem}-{i}{dest.suffix}"
        i += 1
    p.rename(dest)
    _drop_index_line(mem_dir, p.name)
    return dest
