"""Upstream reporting — turning a charter failure into an issue on charter's own tracker.

charter is installed by strangers (`uv tool install charter-cp`), so when it breaks in
someone's session the maintainer never hears about it: the Reporter is mid-task on their
own work, and opening a browser to write up a reproduction is enough friction that nobody
does. The reporting agent is already sitting there holding the traceback, the version and
what was being attempted — this module turns that into something publishable.

Vocabulary (see ``workspaces/user-reporting/workspace.md``):

* **Reporter** — the human who installed charter and in whose session this surfaced.
* **report** — the *private* draft. It is not public and may never become public.
* **upstream issue** — the public artifact. Qualified deliberately: charter also works
  with issues in the Reporter's *own* repos, so a bare "issue" is ambiguous here.
* **bug** — charter did something wrong. Structured, fingerprintable.
* **gap** — charter cannot do something it should. Free prose, no fingerprint.
* **condition** — a failure that is *not* a bug (a timeout, an interrupt). Never reported.

The governing decisions live in ``docs/adr/`` 0001-0003.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import time
import traceback
from pathlib import Path

from . import __version__, config, util

#: Ceiling on **distinct** pending reports. A broken config makes every invocation fail,
#: and a Reporter who walks away should not return to a full disk. Repeats of a report
#: already on disk are unaffected — they collapse onto it, which is the whole point.
MAX_PENDING = 25

#: How long an **unsent** draft survives. A report nobody approved in a month is one
#: nobody is going to; sent reports are never aged out, since they are what a later
#: identical crash points at.
MAX_DRAFT_AGE_DAYS = 30

#: The installed charter package. A frame is ours if it lives under here — resolved, so a
#: symlinked install (``uv tool install`` makes several) still matches its own frames.
_PKG = Path(__file__).resolve().parent

#: Every key a bug payload may carry. A **closed allowlist**: a public tracker is the
#: wrong place to discover that some field quietly carried a client's repo name, so
#: nothing travels unless it was decided to be safe. Note the deliberate absence of
#: ``argv`` — the subcommand *name* is safe, its *arguments* carry workspace and repo
#: names — and of anything derived from the session transcript.
BUG_FIELDS = (
    "charter_version",
    "python_version",
    "os",
    "subcommand",
    "exception_type",
    "frames",
    #: The one field that cannot be made safe mechanically: messages routinely embed the
    #: very names we are stripping (``no workspace 'acme-migration'``). Treated as free
    #: text the Reporter must read before sending, never as a field we vouch for.
    "message",
)


def safe_frames(frames) -> list[str]:
    """Charter's own stack frames, rendered package-relative. Everything else is dropped.

    Two different leaks are closed here, and only one of them is about paths. Relativizing
    ``/Users/someone/.local/.../charter/cli.py`` to ``charter/cli.py`` strips the
    Reporter's username. Dropping non-charter frames strips something we could not sanitize
    even if we wanted to: *their* filenames and *their* function names, which on a bug hit
    inside their own tooling would describe code they never agreed to publish.

    A frame that is not a real path (``<string>``, ``<stdin>``) simply fails the check and
    is dropped, which is the correct answer for it too.
    """
    out: list[str] = []
    for f in frames:
        p = Path(f.filename).resolve()
        if not p.is_relative_to(_PKG):
            continue
        # Prefixed with the package directory's own name rather than a literal "charter/",
        # so the rendering stays honest if the package is ever vendored under another name.
        out.append(f"{_PKG.name}/{p.relative_to(_PKG)}:{f.lineno} in {f.name}")
    return out


def fingerprint(payload: dict) -> str:
    """A stable identifier for *the same bug*, from the exception type and the deepest
    charter frame — the place it actually broke.

    Deliberately built **without the message**. The message is where the variable part
    lives: ``no workspace 'alpha'`` and ``no workspace 'beta'`` are one bug, and folding
    the message in would defeat the collapse this exists for — as well as baking a
    Reporter-specific name into a key that gets stored and compared.

    Line numbers are included, so the same bug fingerprints differently across a charter
    release that moved the code. That is the right trade: within a version (where collapse
    matters) it is exact, and across versions the upstream duplicate search is what catches
    the repeat.
    """
    frames = payload.get("frames") or []
    # Deepest charter frame — the innermost is where it broke; the outer ones are just
    # how we got there, and they are identical across unrelated failures in `main`.
    site = frames[-1] if frames else "<no charter frame>"
    return hashlib.sha256(
        f"{payload.get('exception_type')}\n{site}".encode()).hexdigest()[:16]


def bug_payload(exc: BaseException, subcommand: str) -> dict:
    """The publishable part of a **bug** report, built from a caught exception.

    Returns only :data:`BUG_FIELDS`. Callers must not add to the result — the closed set
    *is* the privacy guarantee.
    """
    return {
        "charter_version": __version__,
        "python_version": platform.python_version(),
        "os": platform.platform(),
        "subcommand": subcommand,
        "exception_type": type(exc).__name__,
        "frames": safe_frames(traceback.extract_tb(exc.__traceback__)),
        "message": str(exc),
    }


# --- gaps ---------------------------------------------------------------------------
# A gap is prose, so it cannot be allowlisted field-by-field the way a crash can. What it
# gets instead is a scrub of the things charter can positively identify, plus the human
# read that docs/adr/0003 makes mandatory. The scrub is the careless half; the Reporter is
# the rest, because nothing mechanical catches "our billing service can't do X".

#: Left in place of anything removed. Visible on purpose — a silent redaction reads as
#: charter having published the original.
REDACTED = "[redacted]"

#: Absolute paths rooted at a user's home. These carry the Reporter's username in the
#: second segment and their project names in the rest, so the whole token goes, not just
#: the prefix.
_HOME_PATH_RE = re.compile(r"(?:/Users|/home)/\S*")


#: Vault config keys whose VALUES are the Reporter's identifiers rather than charter's
#: wiring: which 1Password vault, which item, which token variable. `file` is deliberately
#: absent — it is a path, and paths are handled by `_HOME_PATH_RE` above.
_VAULT_ID_KEYS = ("op-vault", "op_vault", "op-item", "op_item", "token-env", "token_env")

#: Per-category placeholders rather than one `[redacted]` for everything. The complaint in
#: #137/#154 was not only that the scrub was incoherent but that it cost READABILITY: a
#: maintainer reading `charter vault add [redacted] --op-vault "[redacted]"` cannot follow
#: the command. Naming the category keeps the shape legible while removing the value.
_W, _P, _V, _T = "[workspace]", "[persona]", "[vault]", "[token-env]"


def _identifiers() -> list[tuple[str, str]]:
    """(value, placeholder) for every identifier charter knows about this machine.

    Lazy imports: importing `report` happens on every `cli` invocation, and this is the only
    place that needs the workspace, persona and vault machinery.
    """
    from . import persona, workspace
    from .secrets import registry

    out: list[tuple[str, str]] = []
    # A workspace charter cannot look inside still has a name, and the name is the identifier
    # (#1043). `list_workspaces` leaves it out, so it went into the draft unscrubbed.
    names, unread = workspace.read_workspaces()
    for w in names + [d.name for d, _code in unread]:
        out.append((w, _W))
    for p in persona.list_personas():
        out.append((p, _P))
    try:
        for name, vc in (registry.vaults() or {}).items():
            out.append((name, _V))
            cfg = (vc or {}).get("config") or {}
            for key in _VAULT_ID_KEYS:
                val = cfg.get(key)
                if isinstance(val, str) and val.strip():
                    out.append((val.strip(), _T if "token" in key else _V))
    except Exception:
        # A registry that cannot be read must not stop the rest of the scrub: the failure
        # direction that matters is "scrubbed less than it could", never "sent nothing".
        pass
    # `default` exists on every install, so it identifies nobody — and redacting it would
    # mangle ordinary English in most reports.
    return [(v, ph) for v, ph in out if v and v != config.DEFAULT_WORKSPACE]


def scrub(text: str) -> tuple[str, list[str]]:
    """Remove what charter can positively identify as the Reporter's, and say what it removed.

    Returns ``(text, categories)``.

    The advantage over a generic scrubber is that charter knows its own names — workspaces,
    personas, **vaults, vault items and token variables** — which are routinely named after
    the client, the project or the company.

    **The whole cluster or none of it.** Redacting the persona/vault *alias* while leaving
    the real 1Password vault name and `OP_..._SERVICE_ACCOUNT_TOKEN` on the adjacent lines
    cost readability and bought no privacy — the alias was recoverable in one step — and it
    created false confidence, because seeing `[redacted]` reads as "the identifiers were
    handled" and stops an author checking what else is going out on a PUBLIC tracker under
    their own identity (#137, #154).

    Between "redact everything charter knows" and "redact only the unambiguous", this takes
    the first: a vault name is frequently a **company** name, which is precisely the class
    of identifier this exists to keep off a public tracker.

    The known cost is unchanged and still deliberate — a workspace named after a common word
    redacts that word out of ordinary prose — and is paid down two ways rather than argued
    away: per-category placeholders keep a command's shape followable, and the returned
    categories give the Reporter's mandatory read (ADR 0003) something to check against
    instead of having to notice absences.
    """
    out = text
    used: set[str] = set()

    if _HOME_PATH_RE.search(out):
        used.add("home paths")
        out = _HOME_PATH_RE.sub(REDACTED, out)

    # Longest first, so `acme-migration` is removed whole rather than being half-eaten by
    # a shorter `acme` and leaving `[workspace]-migration` behind.
    for value, placeholder in sorted(_identifiers(), key=lambda p: len(p[0]), reverse=True):
        pattern = rf"\b{re.escape(value)}\b" if value[:1].isalnum() else re.escape(value)
        if re.search(pattern, out):
            used.add(placeholder)
            out = re.sub(pattern, placeholder, out)
    return out, sorted(used)


def scrubbed(text: str) -> str:
    """`scrub` for callers that only want the text."""
    return scrub(text)[0]


def gap_payload(text: str) -> dict:
    """The publishable part of a **gap** report. No exception type and no frames — a gap
    is not a crash — but the same version context, which is what tells the maintainer
    whether the capability landed since."""
    body, scrubbed_categories = scrub(text)
    return {
        "charter_version": __version__,
        "python_version": platform.python_version(),
        "os": platform.platform(),
        "text": body,
        # Carried in the payload so `render` can state it. ADR 0003 makes the Reporter read
        # the draft before it is sent; without this the read has to notice ABSENCES, which
        # is the hardest thing to check for and the reason a half-redaction went out
        # looking handled (#137).
        "scrubbed": scrubbed_categories,
    }


# --- local storage ------------------------------------------------------------------
# A report outlives the invocation that found it: detection is automatic, approval is not
# (docs/adr/0003), so the two can be hours apart. Reports are also kept AFTER sending,
# stamped with their issue URL, so the next identical crash can point at the existing
# upstream issue instead of re-drafting — local dedupe at zero API cost.

def _path(report_id: str) -> Path:
    return config.REPORTS_DIR / f"{report_id}.json"


def load(report_id: str) -> dict | None:
    """One report by id, or None if there is no such report."""
    p = _path(report_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except ValueError:
        # A truncated draft (killed mid-write) is not worth crashing a CLI over; the
        # Reporter loses a draft, which is recoverable, where a crash is not.
        return None


def _all() -> list[dict]:
    if not config.REPORTS_DIR.exists():
        return []
    out = []
    for p in sorted(config.REPORTS_DIR.glob("*.json")):
        r = load(p.stem)
        if r:
            out.append(r)
    return out


def pending() -> list[dict]:
    """Reports awaiting the Reporter's approval — drafted but never published."""
    return [r for r in _all() if not r.get("issue_url")]


def all_reports() -> list[dict]:
    """Every report on this machine, sent or not."""
    return _all()


def _write(rec: dict) -> str:
    config.private_mkdir(config.REPORTS_DIR)
    config.write_for(_path(rec["id"]), json.dumps(rec, indent=2))
    return rec["id"]


def delete(report_id: str) -> bool:
    """Remove one report from local storage. True if it was there.

    The undo for drafting. Drafting is deliberately cheap and local (ADR 0003 keeps
    recording separate from reporting), and that only works if discarding is cheap too —
    otherwise a redrafted report leaves its superseded twin in `report list` forever, and a
    list with permanent false positives stops being read (#155).

    No network, for the same reason drafting has none: this is the Reporter's own disk.
    """
    p = _path(report_id)
    if not p.exists():
        return False
    p.unlink(missing_ok=True)
    return True


def prune() -> int:
    """Drop unsent drafts older than :data:`MAX_DRAFT_AGE_DAYS`. Returns how many went.

    Only *unsent* ones: a sent report is kept forever, because it is what lets a later
    identical crash point at the existing upstream issue.

    Runs on write rather than from a hook, so it works on a CLI-only install with no
    plugin — the same reason crash detection lives in `cli.main` rather than in a hook.
    """
    cutoff = time.time() - (MAX_DRAFT_AGE_DAYS * 86400)
    gone = 0
    for r in pending():
        if r.get("first_seen", 0) < cutoff:
            _path(r["id"]).unlink(missing_ok=True)
            gone += 1
    return gone


def _record(rid: str, kind: str, payload: dict) -> str | None:
    """Store a report under *rid*, collapsing onto an existing one with the same id.

    Nothing here touches the network — recording is not reporting. That separation is what
    lets detection default to on: it only ever writes to the Reporter's own disk.
    """
    existing = load(rid)
    if existing:
        existing["occurrences"] = existing.get("occurrences", 1) + 1
        existing["last_seen"] = time.time()
        return _write(existing)

    prune()

    # Checked only for a genuinely new report, so a crash loop sitting at the cap keeps
    # counting the very bug that is looping.
    if len(pending()) >= MAX_PENDING:
        return None

    now = time.time()
    return _write({
        "id": rid,
        "kind": kind,
        "payload": payload,
        "occurrences": 1,
        "first_seen": now,
        "last_seen": now,
        "issue_url": None,
    })


def record_bug(exc: BaseException, subcommand: str) -> str | None:
    """Record a **bug** locally. Returns its id, or None if the cap refused it.

    The id *is* the fingerprint, so collapse falls out of the storage layout rather than
    needing a search: the same bug twice is the same filename twice.
    """
    payload = bug_payload(exc, subcommand)
    return _record(fingerprint(payload), "bug", payload)


def record_described(kind: str, text: str) -> str | None:
    """Record a report the Reporter **described in prose**, scrubbed. Returns its id, or
    None if the cap refused it.

    Covers both a gap and a bug the Reporter reports by hand — the latter has no exception
    object, so it gets the same prose treatment rather than a traceback payload.

    Scrubbed on the way *in*, not on the way out: a draft sitting on disk unredacted is a
    draft that can be published without the scrub having run. Identical text collapses the
    way a repeated crash does — prose has no stack frame to fingerprint, but an agent
    re-raising the same request every session should not accumulate.
    """
    payload = gap_payload(text)
    rid = hashlib.sha256(f"{kind}\n{payload['text']}".encode()).hexdigest()[:16]
    return _record(rid, kind, payload)


def record_gap(text: str) -> str | None:
    """Record a **gap** locally, scrubbed. See :func:`record_described`."""
    return record_described("gap", text)


def render(rec: dict) -> str:
    """The report as the Reporter will see it — and, later, as the upstream issue body.

    One renderer for both, deliberately: if what is shown and what is sent could drift,
    the Reporter's approval would stop meaning anything (docs/adr/0003).
    """
    p = rec["payload"]
    lines = []
    if p.get("text"):
        lines += [p["text"], ""]
    if p.get("exception_type"):
        lines.append(f"**{p['exception_type']}** in `charter {p.get('subcommand', '?')}`")
        if p.get("message"):
            # Flagged, not vouched for: this is the one field no allowlist could make safe.
            lines.append(f"> {p['message']}   ← free text, check before sending")
        if p.get("frames"):
            lines += ["", "```", *p["frames"], "```"]
        lines.append("")
    if rec.get("occurrences", 1) > 1:
        lines.append(f"Hit {rec['occurrences']} times on this machine.")
    if p.get("scrubbed"):
        # Named categories, because the Reporter's mandatory read (ADR 0003) is otherwise a
        # search for things that are NOT there. A visible `[vault]` also stops the failure
        # #154 describes — seeing a redaction and concluding the identifiers were handled.
        lines.append(f"_Scrubbed before drafting: {', '.join(p['scrubbed'])}. "
                     f"Restore anything over-redacted before sending._")
    lines.append(
        f"charter {p.get('charter_version')} · Python {p.get('python_version')} "
        f"· {p.get('os')}")
    return "\n".join(lines)


# --- consent ------------------------------------------------------------------------

class ReportingError(RuntimeError):
    """A reporting operation failed in a way the Reporter must be told about.

    Deliberately loud. The forge adapter's ``_api`` is documented as best-effort and
    returns None on any failure so the status line can never crash — correct there, and
    catastrophic here: applied to publishing, "swallow it and return None" means the
    Reporter's report vanishes while they are told it worked (docs/adr/0002).
    """


def consent_path() -> Path:
    """Where consent-to-publish is remembered — under the **human's** config home.

    Not STATE_DIR: that is per control plane, so a Reporter with several planes would be
    asked repeatedly until the safeguard became a reflex. Not charter.toml: that is
    committed, and would enrol a whole team on one person's say-so (docs/adr/0003).

    ``$CHARTER_CONFIG_HOME`` overrides it. That exists rather than relying on
    ``$XDG_CONFIG_HOME`` alone for a concrete reason: **`gh` keeps its own auth under
    XDG_CONFIG_HOME**, so anything redirecting that variable to isolate charter's consent
    also logs `gh` out — which silently turns a publish into the no-`gh` fallback path.
    """
    base = (os.environ.get("CHARTER_CONFIG_HOME")
            or os.environ.get("XDG_CONFIG_HOME")
            or (Path.home() / ".config"))
    return Path(base) / "charter" / "reporting-consent"


def has_consent() -> bool:
    return consent_path().exists()


def grant_consent() -> None:
    p = consent_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "The Reporter agreed that `charter report send` may open issues on the upstream "
        "tracker under their own GitHub identity. Delete this file to withdraw.\n")


# --- the forge ----------------------------------------------------------------------
# The ONLY network boundary in reporting, and the only place charter writes to a forge.
# Concentrated into one function on purpose: it is the single seam tests stub, which is
# what lets the whole feature be developed and verified without touching a real tracker.

#: Where reports go. Configuration rather than a constant so a fork can point its users at
#: its own tracker, and an internal deployment can keep reports off a public one.
#:
#: The desktop app's repository since 0.62.2: charter-cp is no longer maintained, its old
#: repository was renamed ``diazoxide/charter-plane``, a plane that takes no reports, and
#: the app took over the name ``diazoxide/charter``.
DEFAULT_UPSTREAM = "diazoxide/charter"


def upstream_repo() -> str:
    return os.environ.get("CHARTER_UPSTREAM_REPO") or DEFAULT_UPSTREAM


def gh(args: list[str]) -> str:
    """Run one `gh` command and return its stdout. Raises :class:`ReportingError`.

    A flat call rather than a `Forge` method (docs/adr/0002): reporting always targets one
    specific repo on github.com, so it is not polymorphic over the Reporter's forges, and
    putting ``create_issue`` on that protocol would imply a GitLab implementation nobody
    will ever need.
    """
    p = util.run(["gh", *args], check=False)
    if p.returncode != 0:
        raise ReportingError((p.stderr or p.stdout or "gh failed").strip())
    return (p.stdout or "").strip()


def gh_available() -> bool:
    """Whether this Reporter can publish directly. False for a GitLab-only Reporter, and
    whenever `gh` is missing, logged out, or rate-limited — all of which fall back to the
    prefilled URL rather than losing the report."""
    p = util.run(["gh", "auth", "status"], check=False)
    return p.returncode == 0


#: A Markdown ATX heading opening the first line of a described report. Stripped before
#: that line becomes an issue title, because a heading marker is a **block** marker — it
#: was never part of the reporter's sentence — where backticks and bold are inline markup
#: the reporter chose. Charter un-marks the line; it does not rewrite the words.
#:
#: The body of a report *is* Markdown, so opening with a heading is the natural thing to
#: write, and #322 on this tracker is titled ``# `charter secret list` reports …`` because
#: nothing removed it. The trailing group is CommonMark's *closed* form (``## Title ##``).
#: The whitespace CommonMark requires after the marker is load-bearing here: without it,
#: "#331 is still open" — an issue reference in the reporter's own sentence — would be
#: read as a heading and silently lose the number.
_ATX_HEADING = re.compile(r"^#{1,6}[ \t]+(.*?)[ \t]*#*[ \t]*$")

#: The longest an issue title may be, ellipsis included. A forge allows far more; this is
#: about the maintainer's issue list, where a title that wraps stops being scannable.
_TITLE_MAX = 72

#: The earliest index at which a word break is worth taking. Below it, breaking throws away
#: more of the sentence than a tidy ending is worth, so charter cuts mid-word instead.
#:
#: Hand-rolled rather than :func:`textwrap.shorten` for exactly that case: `shorten`
#: returns **only** the placeholder when the first word exceeds the width, so a first line
#: that is one long unbroken token — a URL, a path, a stack frame — would arrive on the
#: tracker as an issue titled "…". The obvious helper is wrong in the one case a floor is
#: for, and it would have looked right in review.
_BREAK_FLOOR = 40


def title(rec: dict) -> str:
    """The upstream issue title. Crashes lead with exception type and subcommand so
    duplicates collide visually in the issue list.

    A *described* report has no exception to lead with, so its title is its first line —
    un-marked and bounded at a word. That line is also what :func:`search_duplicates`
    searches on, so a marker left in place degrades duplicate detection as well as the
    title (#360).

    The heading is deliberately **not** removed from the body. :func:`render` serves both
    the Reporter's review and the issue body so that what is shown and what is sent cannot
    drift (docs/adr/0003); dropping a line here would make the sent thing differ from the
    approved thing, and would need `render` and this function to agree about which line
    became the title. One repeated heading is the cheaper failure.
    """
    p = rec["payload"]
    if p.get("exception_type"):
        return f"{p['exception_type']} in `charter {p.get('subcommand', '?')}`"
    lines = (p.get("text") or "").strip().splitlines()
    if not lines:
        # `splitlines()` on empty or whitespace-only text is the EMPTY list, and the
        # verbatim `[0]` raised `IndexError`. `commands_report._draft` refuses an empty
        # body one layer up, so no CLI path reaches this — but `title` is called on stored
        # records, and the one function whose job is to describe a report must never be the
        # thing that raises.
        return ""
    first = lines[0].strip()
    heading = _ATX_HEADING.match(first)
    if heading:
        first = heading.group(1).strip()
    # Measured AFTER the marker is stripped: a line whose words fit once the "# " is gone
    # must not be truncated for two characters charter itself removed.
    if len(first) <= _TITLE_MAX:
        return first
    cut = first[:_TITLE_MAX - 1]                       # leave room for the ellipsis
    space = cut.rfind(" ")
    if space >= _BREAK_FLOOR:
        cut = cut[:space]
    return cut.rstrip() + "…"


def search_duplicates(rec: dict) -> list[dict]:
    """Candidate upstream issues that may already cover *rec*.

    Returns candidates for a human or the reporting agent to **judge** — deliberately not
    a verdict. A keyword score cannot separate "clone fails on a private repo" from "clone
    fails on a submodule", which is a distinction that needs the issue read.
    """
    out = gh(["issue", "list", "--repo", upstream_repo(), "--search", title(rec),
              "--state", "all", "--limit", "5", "--json", "number,title,url"])
    try:
        return json.loads(out) if out else []
    except ValueError:
        return []


def issue_body(rec: dict) -> str:
    return render(rec)


def create_issue(rec: dict) -> str:
    """Open the upstream issue and return its URL."""
    return gh(["issue", "create", "--repo", upstream_repo(),
               "--title", title(rec), "--body", issue_body(rec),
               "--label", "via-charter-report", "--label", rec.get("kind", "bug")])


def comment_on(issue: str, rec: dict) -> str:
    """Add this Reporter's reproduction to an existing upstream issue.

    The default on a confirmed duplicate: silently dropping a repeat throws away the most
    valuable thing it carries — a second environment where the bug reproduces.
    """
    return gh(["issue", "comment", issue, "--repo", upstream_repo(), "--body", issue_body(rec)])


def fallback_url(rec: dict) -> str:
    """A prefilled `issues/new` link, for a Reporter with no usable `gh`.

    charter supports GitLab forges, so "no GitHub identity" is a real population rather
    than an edge case — and this doubles as the escape hatch when `gh` is broken.
    """
    return (f"https://github.com/{upstream_repo()}/issues/new"
            f"?title={util.urlenc(title(rec))}&body={util.urlenc(issue_body(rec))}")


def mark_sent(report_id: str, issue_url: str) -> None:
    """Stamp a report with the upstream issue it became. Kept rather than deleted: a later
    identical crash points the Reporter at their own issue instead of drafting again."""
    rec = load(report_id)
    if rec:
        rec["issue_url"] = issue_url
        _write(rec)
