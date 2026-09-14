"""Personas: shared, committable role identities an agent can adopt.

A **persona** (e.g. ``devops``, ``qa``, ``developer``) is a role the agent
imitates. It lives in a **committed** directory ``personas/<name>/``:

- ``persona.md`` — frontmatter metadata plus a prose *charter* (the definition).
- ``memory/``    — **persistent** knowledge the persona has learned (committed,
  shared with the team): a ``MEMORY.md`` index plus one file per durable fact.
- ``refs/``      — curated docs / links / snippets for the role (committed).

Two more stores live **per-developer** under ``.charter/persona-state/`` (gitignored):

- **ephemeral** memory — session-scoped scratch the persona can jot down and that
  is deleted after the session (``ephemeral/<session>/<name>/``), and
- an activity **log** (``log/<name>.jsonl``).

So a persona has a 2×2 memory: *own vs shared* × *persistent vs ephemeral*. The
persona decides which quadrant a note belongs in (see :func:`remember`).

The active persona is resolved by precedence, mirroring workspaces (:func:`_resolved`):
``--persona`` flag → ``$CHARTER_PERSONA`` env → session pointer
(``.charter/sessions/<id>.persona``) → terminal pointer (``.charter/terminals/<id>.persona``)
→ plane-wide ``.charter/active-persona`` → ``charter.toml`` ``[persona] default`` →
``personas/.default`` → none. The first rung naming anything wins. The two committed rungs
name only a persona that exists; a rung above them naming one that does not — a pointer
``persona remove`` left behind — still wins, and the session has no persona rather than the
default. :func:`selection` says which case it is (#1045). A ``$CHARTER_PERSONA`` holding only
whitespace names nothing and is unset, not a rung (:func:`from_environment`, #1048).

The legacy flat layout ``personas/<name>.md`` still resolves for read, so old
checkouts keep working until migrated (``charter persona migrate``).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from itertools import groupby as _groupby
from pathlib import Path
from typing import NamedTuple

from . import config, contain, mcpseen

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

#: The characters :data:`_NAME_RE` admits anywhere after the first. Kept beside it so the
#: rule and the sentence that reports the rule cannot drift apart.
_NAME_CHARS = re.compile(r"[a-z0-9._-]")

#: Why a reference is not a persona name when its **alphabet** is what it violated, rather
#: than its shape. Said here, next to :func:`valid_name`, because that is the rule broken.
#:
#: `contain.NOT_A_SEGMENT` describes a *different* violation and enumerates separators,
#: dots and absolute paths — none of which is true of ``"parent"`` (quoted). Rendering it
#: for either half of :func:`reference_ok` sent the operator looking for a slash that is
#: not there, which is #328's own defect, a distinction collapsed, reappearing three lines
#: below the docstring that names it (#361).
NOT_A_NAME = ("'{name}' is not a persona name{detail}. Charter mints these itself — "
              "`persona create` enforces exactly this — so a reference can only name one: "
              "a lowercase letter or digit first, then lowercase letters, digits, '.', "
              "'_' or '-'")

#: The one refused reference that is neither a path nor a bad character: nothing at all.
#: ``extends:`` with an empty value parses to ``""``, and "'' is not a name — it is a path"
#: would be wrong twice over.
EMPTY_REFERENCE = "is empty — remove the key, or name a persona"


def valid_name(name: str) -> bool:
    # A leading '_' is reserved (the shared namespace) and rejected by the regex.
    # `fullmatch`, never `match`: `$` matches at the end of the string OR just before a
    # trailing newline, so `_NAME_RE.match("evil\n")` admitted a name the alphabet
    # excludes, and `personas/evil<LF>/` resolved, loaded and wrote a blank line into a
    # generated agent's frontmatter (#577). `fullmatch` is the property `$` spells.
    return bool(name) and _NAME_RE.fullmatch(name) is not None


def _alphabet_detail(ref: str) -> str:
    """The clause naming *which* part of the alphabet *ref* broke.

    Three cases, because they are three different fixes. A disallowed character is deleted
    or replaced; a bad *first* character means the name is otherwise fine and only starts
    wrong; and quotes mean the frontmatter was written as YAML by someone who reasonably
    expected YAML.
    """
    bad = sorted({c for c in ref if not _NAME_CHARS.fullmatch(c)})
    if bad and set(bad) <= {'"', "'"}:
        # The live case from #361, and worth its own sentence because the generic one
        # ("'\"' cannot appear in one") is true and still leaves the reader guessing.
        # charter's frontmatter parser does not strip quotes, so the value really does
        # carry them — the fix is in the file, and it is two characters.
        return (" — the quotes are part of the value. charter's frontmatter parser does "
                "not strip them, so `extends: \"parent\"` asks for a persona whose name "
                "includes the quote marks; remove them")
    if bad:
        return f" — {', '.join(repr(c) for c in bad)} cannot appear in one"
    # Every character is in the alphabet, so the FIRST one is what is wrong. Listing '_'
    # as a disallowed character here would be its own small lie: it is allowed, just not
    # in front.
    if ref[0] == "_":
        return " — a leading '_' is reserved for the shared namespace"
    return f" — it starts with {ref[0]!r}"


def reference_refusal(ref: str) -> str | None:
    """Why *ref*, read out of a committed file, cannot name a persona — or ``None``.

    **The one place that answers this**, verdict *and* sentence together, which is the
    property :func:`reference_ok` already claimed for itself and did not have: it decided
    the verdict here while the caller picked the message somewhere else, and the message
    it picked described the other failure (#361).

    The two halves are asked in this order deliberately. Where a reference is both a path
    and outside the alphabet, "it is a path" is the more serious and the more useful thing
    to say — the alphabet is a naming rule, containment is what stops a committed file
    naming a target outside the directory charter meant to look in.
    """
    if not ref:
        return EMPTY_REFERENCE
    if contain.child(config.PERSONAS_DIR, ref) is None:
        return contain.refusal(ref)
    if not valid_name(ref):
        # `contain.readable`, for the reason the branch above goes through
        # `contain.path_sentence`: this sentence NAMES the offender, so the offender must not
        # be able to write a second line of it. Newly load-bearing as of #577 — while `$`
        # admitted a trailing newline this branch was unreachable for the one character
        # that could, and the raw `.format` was safe by accident (#453, #498).
        return NOT_A_NAME.format(name=contain.readable(ref), detail=_alphabet_detail(ref))
    return None


def reference_ok(ref: str) -> bool:
    """Can *ref*, read out of a committed file, name a persona at all?

    **The one place that answers this**, so the resolver and the operator's own check
    cannot disagree — which they did, and that divergence is #328's tell rather than a
    detail of it. `structural_errors` tested membership in a *name* set while `lineage`
    resolved a *path*, so `charter persona lint` printed

        ✗ frontdoor: uses: '<relative path>' — no such persona (dangling)

    about a reference `resolve()` loaded without complaint and whose `tools:` the
    PreToolUse gate then honoured. The signal an operator would actively check said the
    grant was inert while it was live (#329, #337).

    `valid_name` is the right rule here and a *forge* name would not be: charter mints
    persona names itself — `persona create` already enforces exactly this — so a reference
    outside that alphabet cannot name a persona this plane contains. That makes lint and
    the resolver agree by construction instead of by two checks kept in step by hand.

    The containment join is belt and braces on top, per :mod:`charter.contain`: it is the
    half that still holds if `_NAME_RE` is ever widened.

    Delegates to :func:`reference_refusal` rather than re-testing the two halves, so the
    verdict and the sentence an operator reads cannot describe different failures — which
    they did, and which is what #361 is (see that function).
    """
    return reference_refusal(ref) is None


# --------------------------------------------------------------------------- #
# paths: directory layout, with legacy flat-file fallback                      #
# --------------------------------------------------------------------------- #
def dir_of(name: str) -> Path:
    """The persona's directory ``personas/<name>/`` (may not exist yet)."""
    return config.PERSONAS_DIR / name


def def_path(name: str) -> Path:
    """The definition file. Prefers the directory layout
    (``personas/<name>/persona.md``), falls back to the legacy flat
    ``personas/<name>.md``; if neither exists, returns the *canonical new*
    location so writers create the directory layout."""
    d = dir_of(name) / "persona.md"
    if d.exists():
        return d
    flat = config.PERSONAS_DIR / f"{name}.md"
    if flat.exists():
        return flat
    return d


#: Back-compat alias — existing callers use ``persona.path(name)``.
path = def_path


def is_dir_layout(name: str) -> bool:
    return (dir_of(name) / "persona.md").exists()


def memory_dir(name: str, shared: bool = False) -> Path:
    """Persistent (committed) memory dir — own or the shared namespace."""
    base = config.PERSONAS_DIR / (config.SHARED_PERSONA if shared else name)
    return base / "memory"


def refs_dir(name: str, shared: bool = False) -> Path:
    base = config.PERSONAS_DIR / (config.SHARED_PERSONA if shared else name)
    return base / "refs"


def _session_id(session: str | None = None) -> str:
    """This session's bucket name — see :mod:`charter.session`, which owns the question."""
    from . import session as _session
    return _session.bucket(session)


def ephemeral_dir(name: str, shared: bool = False, session: str | None = None) -> Path:
    """Ephemeral (gitignored, session-scoped) scratch dir — own or shared. The
    whole session directory is pruned by :func:`gc_ephemeral`."""
    ns = config.SHARED_PERSONA if shared else name
    return config.PERSONA_STATE_DIR / "ephemeral" / _session_id(session) / ns


def index_of(mem_dir: Path) -> Path:
    return mem_dir / "MEMORY.md"


# --------------------------------------------------------------------------- #
# listing / loading                                                            #
# --------------------------------------------------------------------------- #
def list_personas() -> list[str]:
    d = config.PERSONAS_DIR
    if not d.exists():
        return []
    names: set[str] = set()
    for p in d.glob("*.md"):  # legacy flat files
        if p.stem.lower() != "readme":
            names.add(p.stem)
    for sub in d.iterdir():  # directory layout
        if sub.is_dir() and not sub.name.startswith("_") and (sub / "persona.md").exists():
            names.add(sub.name)
    return sorted(names)


def _frontmatter(text: str) -> tuple[list[tuple[str, str]], str]:
    """The frontmatter as ``[(key, value)]`` **in file order**, plus the body.

    The one line-walk. :func:`parse` collapses these pairs into a dict and :func:`load`
    also asks them what the dict cannot answer — which keys were written more than once
    (#509). Two questions, one reading of the file, so the answers cannot disagree about
    what the file said.

    Splitting this out is what let #509 be fixed without the change it feared. That issue
    read the choice as "either change what `parse` returns or give it a second output",
    both of which land on `persona.load`, `structural_errors`, `resolve`, `tools_of`,
    `vault_of`, `docsrc`, `news._read` and the skill lint at once. Neither happened:
    `parse` still returns ``(dict, body)`` and every caller of it is untouched. The second
    answer is carried by the *loader*, which is where the persona-shaped questions are
    already asked.
    """
    pairs: list[tuple[str, str]] = []
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            frontmatter, body = parts[1], parts[2]
            for line in frontmatter.strip().splitlines():
                if ":" not in line:
                    continue
                key, _, value = line.partition(":")
                key, value = key.strip(), value.strip()
                if key:
                    pairs.append((key, value))
    return pairs, body.strip()


def parse(text: str) -> tuple[dict, str]:
    """Split frontmatter markdown into (metadata, charter body).

    Minimal, dependency-free: flat ``key: value`` lines. Good enough for our
    small, controlled frontmatter (``role``, ``vault``, …).

    **Lossy, and now provably so.** Two lines carrying one key collapse to the last of
    them, which is a fact about a `dict` and not a decision anyone made: the file said two
    things and this says one. A caller holding only text asks :func:`duplicate_keys` for
    what the dict dropped; :func:`load` reads both off one walk of the same file, so every
    persona-shaped consumer gets the answer without a second parse.
    """
    pairs, body = _frontmatter(text)
    return dict(pairs), body


def duplicate_keys(text: str) -> list[str]:
    """Frontmatter keys *text* declares more than once, first-declaration order.

    A key written twice is a contradiction in the file, not a value to be picked (#509).
    :func:`parse` keeps the last line because that is what building a dict does, so the
    first value is gone before any consumer sees the dict — ``vault:`` twice hands out
    whichever vault is lower in the file, ``tools:`` twice auto-approves whichever list
    is lower, and nothing anywhere said a word.

    Exposed on the TEXT rather than folded into `parse`'s return type, so the news reader
    and the skill lint can ask the same question of the same parser when their owners want
    it, without this changing under them first.
    """
    return [k for k, n in _key_counts(_frontmatter(text)[0]).items() if n > 1]


#: Frontmatter keys `commands_persona._render_agent` copies straight into the generated
#: sub-agent.
AGENT_PASSTHROUGH_KEYS = ("model", "color", "memory")

#: Keys charter reads itself rather than emitting. Together with the passthrough set this
#: is the full vocabulary of a persona charter's frontmatter.
CHARTER_OWN_KEYS = (
    "name", "role", "vault", "extends", "uses", "delegate-when", "description",
    "agent-description", "agent-tools", "tools", "activity", "dispatch-isolation",
    "draft", "skills", "disallowed-tools", "routing", "routes-to", "borrows",
)

#: The whole vocabulary, and the only spelling of each word charter answers to.
#:
#: Declared HERE rather than in `commands_persona`, where it lived, because
#: :func:`structural_errors` needs it and its docstring says in as many words that it
#: cannot afford the import — it runs on every turn for the status line. The vocabulary of
#: a persona definition is a fact about the parser, not about the command that renders one,
#: so the lower layer is where it belongs; `commands_persona` still exports the old names.
KNOWN_KEYS = frozenset(AGENT_PASSTHROUGH_KEYS) | frozenset(CHARTER_OWN_KEYS)

#: `KNOWN_KEYS` folded, for :func:`misspelled_key` — built once rather than per key per
#: persona per turn.
_FOLDED_KEYS = {k.casefold(): k for k in KNOWN_KEYS}


def misspelled_key(key: str) -> str | None:
    """The key charter reads that *key* differs from **only by case**, or None.

    This is not the case-folding #573 refused, and the difference is which question gets
    folded. There, folding was proposed for the *lookup* — `meta.get(key.casefold())` —
    which would have made ``Vault:`` work and left ``vualt:``, ``borrow:`` and
    ``delegate_when:`` exactly as silent, a guard against one spelling rather than the
    property. Nothing here is looked up: a value is never read out of a miscased key, and
    charter never guesses which field the author meant.

    What is folded is the **sentence and the severity**. A key outside the vocabulary is
    caught by :data:`KNOWN_KEYS` being closed — that is #573's mechanism, unchanged, and it
    is what catches ``vualt:``. This only asks, of a key already caught, whether charter can
    name the word the author was reaching for. When it can, the report says so and the
    grant stops trusting the key's absence (:func:`borrows_of`), because ``Borrows: none``
    is not a key charter has no opinion about — it is a key charter reads, one shift away,
    and the author who wrote it was opting OUT of a permission grant.

    ``casefold``, matching `news._flag`'s reading of ``TRUE``/``True``, so the whole tree
    folds text one way.
    """
    if key in KNOWN_KEYS:
        return None
    return _FOLDED_KEYS.get(key.casefold())


def key_issues(name: str) -> list[tuple[str, str]]:
    """Frontmatter keys in *name*'s own definition that charter can neither honour nor
    let pass — ``[(level, message)]``, all of them errors.

    **The property: a frontmatter key is honoured or reported, never silently resolved.**
    Two ways a key goes unhonoured while charter can still prove which word the author
    meant, and both used to end in a value chosen by accident with nothing said:

    * **Declared twice** (#509). ``vault: safe`` above ``vault: prod`` hands out ``prod``
      because that is what building a dict does — the file states a contradiction and
      charter resolves it by LINE ORDER. Charter does not pick; it names the key.
    * **Spelled in another case** (#575). ``Vault:`` is read by nothing, so the persona
      declares a vault and has none; ``Extends:`` declares a parent and inherits nothing.

    A key charter simply does not read — ``modell:``, ``delegate_when:`` — is *not* here.
    It stays the warning :func:`lint` has always given it, because charter has no claim
    about it: a harness's own field is a legitimate thing to carry in a committed file, and
    an error would break planes that are correct. These two are different in kind. Charter
    can say which key charter reads the author was writing, which is what makes the finding
    an error and what lets :func:`borrows_of` act on it.

    Own definition only, matching :func:`structural_errors`' framing — a parent's bad key
    is a finding about the parent, reported when the parent is linted, and the parent's own
    sub-agent is the one withheld for it.
    """
    d = load(name)
    if not d:
        return []
    issues: list[tuple[str, str]] = []
    # Bounded, because a key is a string from a committed file on its way into a report a
    # human reads and acts on. `splitlines` already makes a second ROW impossible — it
    # splits on \r, \x85, U+2028 and U+2029 alike, so none of those survives into a key —
    # but a key of U+3164 HANGUL FILLER strips to nothing visible and printed as
    # `frontmatter key '' …`: #498's finding, a row telling somebody to go and edit a key
    # it does not name. `readable` decides on the complement, so the key named here is one
    # they can find in the file.
    for key in sorted(d.get("dupes") or ()):
        issues.append(("error", f"frontmatter key '{contain.readable(key)}' is declared "
                                f"more than once — charter keeps the LAST line and the "
                                f"first is lost before anything reads it. Two lines are a "
                                f"contradiction in the file, not a value to pick: delete "
                                f"one"))
    for key in sorted(set(d["meta"])):
        meant = misspelled_key(key)
        if meant:
            issues.append(("error", f"frontmatter key '{contain.readable(key)}' is read by "
                                    f"nothing — charter matches keys exactly, so this is "
                                    f"not `{meant}:` and its value never reaches charter. "
                                    f"Spell it `{meant}:`"))
    return issues


def definition_refusal(name: str) -> str | None:
    """Why this persona's definition file must not be read, or ``None``.

    The path half of what :func:`reference_ok` does for the name half, and split out for
    the same reason: :func:`load` and :func:`structural_errors` must not be able to
    disagree about it. When they did — lint calling a live grant dangling — the signal an
    operator would actively check was the one that lied (#329, #337).

    Both questions are asked, because they catch different links. The *directory* resolving
    out of the plane's data is the case where `persona.md` is an ordinary file and there is
    nothing about it to object to; the *file* resolving out is #336's demonstration,
    ``persona.md`` → ``../../.charter/vaults/…``, which `sync-agents` then writes into a
    sub-agent's system prompt while `pretooluse-read` denies the agent that same read.
    """
    p = def_path(name)
    if not p.exists():
        return None
    return contain.dir_refusal(p.parent) or contain.file_refusal(p)


#: Why a definition file charter may read did not come back as text (#1061). What the read
#: said, and nothing about why the file is that way.
UNREADABLE = "'{name}' cannot be read ({why})"
NOT_TEXT = "'{name}' is not {encoding} text ({why} at offset {at})"


def read_refusal(name: str) -> str | None:
    """Why this persona's definition file, there and not refused by
    :func:`definition_refusal`, cannot be read as text, or ``None``.

    :func:`load` answers ``None`` for these without saying why. This reads the file again to
    name the reason, so ask it only once `load` has failed: it is `persona lint`'s answer to
    the persona every other command calls :data:`DOES_NOT_LOAD`, and the status line never
    pays for it.
    """
    p = def_path(name)
    if not p.exists() or definition_refusal(name):
        return None
    try:
        p.read_text()
    except UnicodeDecodeError as ex:
        return contain.path_sentence(NOT_TEXT, name=str(p), encoding=ex.encoding,
                                     why=ex.reason, at=str(ex.start))
    except OSError as ex:
        return contain.path_sentence(UNREADABLE, name=str(p),
                                     why=ex.strerror or type(ex).__name__)
    return None


def load(name: str) -> dict | None:
    """The persona's OWN (unmerged) definition. For the effective persona with
    inheritance applied, use :func:`resolve`.

    **The choke point for every reference read out of a file.** `lineage`, `resolve`,
    `tools_of`, `vault_of` and `effective_tools` all reach a definition through here, so
    refusing a non-name here is what stops `extends:`/`uses:`/`borrows:` naming a file
    outside `personas/` — rather than four guards at four call sites, three of which stay
    correct. Returns None for a refused reference exactly as it does for one that names
    nothing: the caller has no reason to tell a typo from an escape, and
    `structural_errors` is where the difference is spelled out for the human.
    """
    if not reference_ok(name):
        return None
    p = def_path(name)
    if not p.exists() or definition_refusal(name):
        return None
    try:
        text = p.read_text()
    except (OSError, UnicodeError):
        # A file that is there and does not read as text does not load either, and says so
        # the way a refused one does (#1061). It raised, through `resolve`, into every
        # command that reached it, so one unreadable parent crashed `lint` for its children
        # and one unreadable persona crashed `persona list` for the roster.
        # :func:`read_refusal` says why, for `lint`.
        return None
    pairs, charter = _frontmatter(text)
    meta = dict(pairs)
    meta.setdefault("name", name)
    # The second answer the dict cannot carry, from the same read (#509). A third key
    # rather than a changed return type: every consumer indexes `["meta"]`/`["charter"]`,
    # so nothing downstream has to learn about this to keep working — only the two
    # functions that report it do.
    dupes = [k for k, n in _key_counts(pairs).items() if n > 1]
    return {"meta": meta, "charter": charter, "dupes": dupes}


def _key_counts(pairs) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, _v in pairs:
        counts[key] = counts.get(key, 0) + 1
    return counts


# --------------------------------------------------------------------------- #
# inheritance — a persona may ``extends:`` a parent, deriving its charter + tools #
# and layering its own on top. Charters concatenate (parent base → child adds);  #
# tools/agent-tools/uses union; scalar fields (role, model, vault, …) child wins, #
# else inherited. Chains resolve root→child; cycles are broken.                   #
# --------------------------------------------------------------------------- #
def _csv_set(v) -> set[str]:
    return {x.strip() for x in (v or "").strip("[]").split(",") if x.strip()}


def _csv_list(v) -> list[str]:
    return [x.strip() for x in (v or "").strip("[]").split(",") if x.strip()]


#: The sidecar naming a persona's MCP servers, same schema as `.mcp.json` plus a
#: charter-only `secrets` map per server. A separate FILE rather than frontmatter because
#: `parse` above is line-based and charter carries no runtime dependencies: nested YAML can
#: be emitted (JSON is valid YAML) but not read. A sidecar also takes a server's own README
#: snippet unchanged, which is the form these arrive in.
MCP_FILE = "mcp.json"

#: The shape an MCP server NAME may have, and the reason a committed `mcp.json` can no
#: longer choose what the generated sub-agent runs (#453).
#:
#: A server name is not inert. `commands_persona._render_agent` emitted it as a **bare key**
#: in the agent's YAML frontmatter (``  - {name}: {json}``) — `json.dumps` quoted the entry
#: and nothing quoted the key — so a newline in it ended that line and declared a SECOND
#: server, entry and all. The injected entry could be `charter secret exec <any vault>
#: --exec -- <anything>`, and nothing on the consent path fired: the carrier server need
#: declare no `secrets`, so there was no fingerprint, no prompt, and no withheld line. The
#: run printed `✓ Synced 1 persona sub-agent(s)`. The same name is also interpolated into
#: the tool grant ``mcp__{name}__*``, where a comma buys a second grant.
#:
#: Bounded HERE, at the boundary that reads the committed file, rather than escaped at each
#: place it is emitted — the rule `contain`'s own docstring states, and the one `[frame]
#: hotkey` follows after the identical defect reached tmux config text. The emission is
#: serialised as well (see `_render_agent`), so neither layer is the only thing standing
#: between a commit and a vault; this one is what makes the name an identifier rather than
#: leaving that a hope.
#:
#: Deliberately narrower than "anything JSON can hold": ASCII letters, digits, ``_``, ``.``
#: and ``-``, first character alphanumeric or ``_``, and 64 of them. That is the alphabet a
#: real server name already uses — it has to survive `mcp__<server>__<tool>` on the host
#: side — and the asymmetry is the same one `_HOTKEY_RE` names: a name this refuses that
#: the host would have accepted costs a rename in one committed file, while a name this
#: accepted and the YAML parsed as a declaration costs the machine's vaults.
#:
#: A refusal is NOT silent, which is where `[frame] hotkey` stopped: `mcp_refused` carries
#: the names, `persona lint` reports each as an error and `sync-agents` warns as it writes.
_MCP_NAME_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,63}")


def mcp_name_ok(name) -> bool:
    """True when *name* may be used as an MCP server name — see :data:`_MCP_NAME_RE`.

    ``fullmatch``, and the pattern carries no ``^``/``$`` of its own, because ``$`` matches
    **before a trailing newline**: an anchored `re.match` would accept ``"ok\\n"``, which is
    the one shape this exists to refuse. A test holds that case by name.
    """
    return isinstance(name, str) and _MCP_NAME_RE.fullmatch(name) is not None


#: A persona's own executables. The fifth capability, alongside memory, refs, ephemeral
#: scratch and `mcp.json` — and the one whose absence kept a whole Claude Code plugin alive
#: as a file carrier (#283).
#:
#: Deliberately NOT put on PATH, because it cannot be: a `PreToolUse` hook decides whether a
#: Bash call runs, not what environment it runs in, and wrapping every Bash call to inject
#: one is the takeover of a host mechanism ADR 0014 exists to refuse. Scripts are invoked by
#: path — which already worked; what was missing is charter knowing they are there, so it can
#: surface them to the agent and vouch for them at the guard.
BIN_DIR = "bin"


def bin_dir(name: str) -> Path:
    """Where *name*'s own executables live. Not created eagerly — an empty `bin/` in every
    persona is noise in a directory a human reads."""
    return dir_of(name) / BIN_DIR


def bin_scripts(name: str) -> dict:
    """``{script_name: path}`` this persona can run, inheritance applied.

    Unioned along ``lineage()`` — the same chain ``mcp_servers`` uses, and for the same
    reason: a child that silently lost what its parent declared would be a surprise. Child
    wins on a name collision, so a persona can override an inherited script.

    ``uses:``/``borrows:`` deliberately do NOT carry scripts. Borrowing is a grant to run
    another persona's *declared tools*; shipping its code is a different thing, and conflating
    them is how #257 got the tool grant wrong in the first place.

    Executable files only. Git preserves the mode bit, so a file committed without ``+x``
    reaches every clone unable to run — failing at the moment somebody needs it, with a
    shell error that points nowhere near here. `lint` names those separately.
    """
    out = {}
    # REVERSED: `lineage()` is child-first, so iterating it directly would let the most
    # distant ancestor overwrite the child — the opposite of the rule. `mcp_servers` below
    # had exactly that bug (#296); this is the shape both now share, and the reason to reach
    # for `reversed()` in any future union along the chain.
    for anc in reversed(lineage(name)):
        d = bin_dir(anc)
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if f.is_file() and os.access(f, os.X_OK):
                out[f.name] = f
    return out


def bin_issues(name: str) -> list[tuple[str, str]]:
    """A file in `bin/` that cannot run. Its own check because the failure is invisible
    until dispatch and reads as a broken script rather than a missing mode bit."""
    d = bin_dir(name)
    if not d.is_dir():
        return []
    return [("warn", f"`{BIN_DIR}/{f.name}` is not executable — it will fail at the moment "
                     f"it is needed; `chmod +x {f.relative_to(config.ROOT)}`")
            for f in sorted(d.iterdir())
            if f.is_file() and not os.access(f, os.X_OK)]


def mcp_servers(name: str) -> dict:
    """``{server_name: config}`` a persona declares, inheritance applied.

    Unioned along the lineage the way ``tools``/``uses`` are — parent first, child wins on
    a name collision. A child that silently lost the server its parent declared would be a
    surprise, and this is the rule the rest of the frontmatter already follows.

    **Every name here has passed :func:`mcp_name_ok`.** This is the one function every
    consumer goes through — the render, the tool grant, `lint`, `mcp_credentialed`, the
    line `persona use` prints — so bounding it here bounds all of them, and a consumer
    added tomorrow inherits the bound instead of having to remember it. What was refused is
    :func:`mcp_refused`, never discarded silently.

    Never raises. The file is hand-edited, and a stray comma in it must not take down
    `sync-agents` for every persona in the plane.
    """
    return _mcp_declared(name)[0]


def mcp_refused(name: str) -> list[str]:
    """The server names in this persona's lineage that :func:`mcp_name_ok` refused.

    Reported, not swallowed. A dropped server is a working persona losing a capability,
    and the value that caused it is in a committed file somebody has to edit — so `lint`
    raises it as an error and `sync-agents` says so on the run that wrote the agent. The
    names come back RAW; every caller renders them through `contain.one_line`, because the
    refused ones are exactly the names that can hold a newline.
    """
    return _mcp_declared(name)[1]


def _mcp_declared(name: str) -> tuple[dict, list[str]]:
    """``(kept, refused)`` — the lineage's declared servers, split by :func:`mcp_name_ok`.

    One read, two answers, so `mcp_servers` and `mcp_refused` cannot disagree about what
    was in the file. A name is refused for the WHOLE lineage's answer at the point it is
    read, so an ancestor cannot smuggle one in on behalf of a child.
    """
    out: dict = {}
    refused: list[str] = []
    # REVERSED, and that is the whole fix for #296. `lineage()` is child-first, so feeding it
    # straight into `dict.update` — last write wins — let the most distant ancestor overwrite
    # the child: the exact inversion of the rule stated above. Nothing surfaced it, because
    # the child's entry was parsed and applied and then thrown away, so `sync-agents`
    # succeeded and the generated agent simply carried somebody else's server.
    for anc in reversed(lineage(name)):
        declaration = dir_of(anc) / MCP_FILE
        if contain.file_refusal(declaration):
            continue          # same promise as the `except` below, kept before the open
        try:
            doc = json.loads(declaration.read_text())
            servers = doc.get("mcpServers") or {}
        except (OSError, ValueError, AttributeError):
            continue
        if not isinstance(servers, dict):
            continue
        for server, entry in servers.items():
            # The bound, at the boundary (#453). NOT `out.update(servers)` any more: that
            # handed every consumer a key straight out of a committed file, and one of them
            # wrote it into YAML as a key.
            if mcp_name_ok(server):
                out[server] = entry
            elif server not in refused:
                refused.append(server)
    return out, refused


def mcp_vault(vault) -> str | None:
    """The vault an MCP entry would actually be wrapped with — ``None`` for :data:`NO_VAULT`.

    ``vault: none`` is charter's reserved way of saying *this persona deliberately holds no
    credentials* (:func:`declares_no_vault`), and :func:`vault_of` has always returned
    ``None`` for it so that no caller goes looking for a vault literally named ``none``.
    The MCP path read ``meta["vault"]`` raw and therefore did not. Measured against 0.53.0,
    on a persona whose charter says ``vault: none``:

        consent line   run uvx analytics-mcp  secrets "T"="k"  vault "none"
        rendered       charter secret exec none --env T=k --exec -- uvx analytics-mcp

    So charter asked the operator to approve spending the value of a vault named ``none``,
    recorded the consent, and wrote a launcher into the generated agent that can never
    work — while `lint` was separately, correctly, calling the same persona one that names
    no vault. One sentinel, two readings.

    Applied in :func:`mcp_render_entry` and :func:`mcp_credentialed` — the render and the
    consent list — because those two must agree about which servers carry a credential or
    the operator is asked about a server the file does not wrap, and vice versa.
    """
    v = vault.strip() if isinstance(vault, str) else ""
    return None if not v or v == NO_VAULT else v


def vault_for_mcp(name: str) -> str | None:
    """The vault *name*'s MCP entries would actually be wrapped with, or ``None``.

    :func:`mcp_vault` applied to the resolved ``vault:``, in ONE place. Both readers that
    have to agree — :func:`mcp_credentialed`, which decides what the operator is asked
    about, and :func:`lint`, which decides what they are told — spelled this chain out
    themselves, and a chain written twice is the thing `file_path` and `loose_dirs` are
    both about in this same commit.

    The ``or {}`` is load-bearing here and not in the callers' old copies: `resolve` returns
    ``None`` for a persona whose ``persona.md`` does not load, and `_approve_mcp` reaches
    `mcp_credentialed` for every name `list_personas` globbed, without asking first.
    """
    return mcp_vault((resolve(name) or {}).get("meta", {}).get("vault"))


def mcp_render_entry(name: str, vault: str | None, entry: dict) -> dict:
    """One declared server, as the generated agent should carry it.

    A ``secrets`` map — ``{ENV_VAR: vault-key}`` — turns the entry into a
    ``charter secret exec … --exec -- <original command>`` invocation, so the value reaches
    the server's environment without ever reaching a context window. The env var names
    belong to the third-party server, which is why they are declared rather than inferred:
    charter cannot know them, and injecting every key in the vault would hand a server
    every credential the persona holds instead of the two it needs.

    ``--exec`` is not optional. It replaces the process rather than capturing it, and an
    MCP stdio server never returns — the capturing form would hang holding output nobody
    reads.

    A server with no ``secrets`` is passed through untouched: dragging a credential-free
    server through charter would buy nothing and add a process.
    """
    out = {k: v for k, v in entry.items() if k not in ("secrets", "secret_files")}
    # `vault: none` is the declared ABSENCE of a vault, not the name of one — see
    # :func:`mcp_vault` for what this line was emitting before it was normalised here.
    vault = mcp_vault(vault)
    secrets = entry.get("secrets") or {}
    # A separate key, not a marker inside `secrets`, because these are different MECHANISMS
    # rather than two spellings of one: `secrets` puts a VALUE in the environment,
    # `secret_files` materialises a 0600 file and puts its PATH there. Google ADC needs the
    # second — `GOOGLE_APPLICATION_CREDENTIALS` takes a path, not a value — and before this a
    # persona whose servers authenticate that way could not declare them at all (#190).
    # A reader should see which mechanism is in play without decoding a value.
    files = entry.get("secret_files") or {}
    if not (secrets or files) or not vault:
        return out
    # The committed sidecar chooses `command`, and this function is where that choice
    # becomes "…and it receives the vault's value" (#330). The gate belongs HERE rather
    # than in `sync-agents`, even though `sync-agents` is the only caller today: the
    # decision being guarded is this one, and a guard sitting one frame above the decision
    # is a guard the next caller forgets to ask for.
    #
    # NOT an allowlist of commands, which is how #317 was closed on a news `check:`. That
    # worked because a `check:` names a charter subcommand — a closed grammar with an
    # enumerable answer. An MCP `command` is an arbitrary binary followed by arbitrary
    # `args`, so a list holding the launchers real servers use (`npx`, `uvx`, `docker`) is
    # walked straight past by `args` alone, and a list excluding them refuses every server
    # anyone actually runs. See `mcpseen` for the full argument.
    #
    # The digest covers the WHOLE entry, not the fields charter happens to know about.
    # `out` above keeps every key it does not consume — `env` among them — and hands them
    # to the harness, which sets them on this process before `secret exec` reaches
    # `execvpe`; so a fingerprint over an allowlist of five fields let a committed edit
    # re-point an approved server's PATH or NODE_OPTIONS with the approval intact (#426).
    if mcpseen.fingerprint(vault, entry) not in mcpseen.approved(name):
        return out
    args = ["secret", "exec", vault]
    for env_name, key in secrets.items():
        args += ["--env", f"{env_name}={key}"]
    for env_name, key in files.items():
        args += ["--file", f"{env_name}={key}"]
    # `--stream` whenever a file is involved: `--exec` replaces charter, so nothing would
    # survive to delete the tempfile. Streaming is unaffected — a forked child inherits this
    # process's descriptors — so the only thing given up is process replacement, which is
    # precisely what made cleanup impossible.
    args += ["--stream" if files else "--exec", "--"]
    if out.get("command"):
        args.append(out["command"])
    args += list(out.get("args") or [])
    out["command"] = "charter"
    out["args"] = args
    return out


def mcp_credentialed(name: str) -> list[tuple[str, dict, str, str]]:
    """``(server, entry, fingerprint, consent line)`` for every server of *name* that would
    carry a credential — i.e. declares ``secrets``/``secret_files`` against a real vault.

    The list `sync-agents --approve-mcp` records and the list it reports on are both
    derived from this one, so "what you were shown" and "what got approved" cannot drift
    apart — which is the failure mode of a consent prompt that computes its own list.

    **The LINE is returned, not just the entry**, and that is deliberate. `mcpseen`
    fingerprints the consent line itself, so the line a caller prints and the digest it
    records have to be the same string; handing back the entry and letting each caller
    render its own is how they come to differ — the caller that forgot the vault would
    print a line the digest does not match. There is one rendering per server here, and
    both callers print that one.

    ``fingerprint`` may be ``None``, and then the line is ``""``: an entry
    `mcpseen.describe` cannot render is in scope (it declares secrets against a vault) but
    can never be approved (#427). Membership is decided by `mcpseen.needs_consent` rather
    than by the digest, so such an entry is still REPORTED as withheld instead of
    vanishing from both lists at once.
    """
    # `vault_for_mcp`, which is `mcp_render_entry`'s own normalisation: a persona declaring
    # `vault: none` holds no credential to withhold, and a consent prompt about one is a
    # prompt about nothing that records an approval for a command that cannot run.
    vault = vault_for_mcp(name)
    out = []
    for server, entry in sorted(mcp_servers(name).items()):
        if mcpseen.needs_consent(vault, entry):
            out.append((server, entry, mcpseen.fingerprint(vault, entry),
                        mcpseen.describe(vault, entry)))
    return out


def mcp_withheld(name: str) -> list[tuple[str, str]]:
    """``(server, consent line)`` for the credentialed servers this operator has NOT
    approved — what `mcp_render_entry` is about to render without its vault wrapper."""
    ok = mcpseen.approved(name)
    return [(s, line) for s, _e, fp, line in mcp_credentialed(name) if fp not in ok]


def lineage(name: str) -> list[str]:
    """The inheritance chain, child-first: ``[name, parent, grandparent, …]``.
    Cycle-safe (stops if it revisits a persona)."""
    out, seen, cur = [], set(), name
    while cur and cur not in seen:
        d = load(cur)
        if not d:
            break
        out.append(cur)
        seen.add(cur)
        cur = (d["meta"].get("extends") or "").strip() or None
    return out


def ancestor_that_does_not_load(name: str) -> str | None:
    """The persona up *name*'s ``extends:`` chain whose definition file is there and does
    not load, or ``None`` (#1061).

    :func:`lineage` stops at the first persona that does not load, so :func:`resolve` builds
    the child without it and says nothing. A parent that is absent, is not a name, or
    closes a cycle is not this: `lint` already has a sentence for each of those.
    """
    chain = lineage(name)
    if not chain:
        return None
    # Not stripped: `_frontmatter` strips every value it reads, so there is nothing to strip
    # and a second strip here could not be told from none.
    parent = load(chain[-1])["meta"].get("extends", "")
    if parent in chain or not reference_ok(parent):
        return None
    return parent if def_path(parent).exists() else None


def resolve(name: str) -> dict | None:
    """The EFFECTIVE persona with inheritance applied: merged meta + concatenated
    charter. Returns ``{meta, charter, lineage}`` (lineage child-first), or None."""
    chain = lineage(name)
    if not chain:
        return None
    meta: dict = {}
    tools, agent_tools, uses = [], [], []  # ordered + deduped (parent first, child appends)
    charter_parts, prev = [], None

    def _extend(dst, vals):
        for v in vals:
            if v and v not in dst:
                dst.append(v)

    for a in reversed(chain):  # root → child, so the child's values win
        d = load(a)
        m = d["meta"]
        for k, v in m.items():
            if k in ("tools", "agent-tools", "uses", "extends") or not v:
                continue
            meta[k] = v  # later (more-derived) wins
        _extend(tools, _csv_list(m.get("tools")))
        _extend(agent_tools, _csv_list(m.get("agent-tools")))
        _extend(uses, [u for u in _csv_list(m.get("uses")) if u != name])
        c = (d["charter"] or "").strip()
        if c:
            charter_parts.append(c if prev is None
                                 else f"\n\n---\n\n### ⤷ `{a}` extends `{prev}` — its own charter\n\n{c}")
        prev = a
    meta["name"] = name
    if tools:
        meta["tools"] = ", ".join(tools)
    if agent_tools:
        meta["agent-tools"] = ", ".join(agent_tools)
    if uses:
        meta["uses"] = ", ".join(uses)
    return {"meta": meta, "charter": "".join(charter_parts), "lineage": chain}


# --------------------------------------------------------------------------- #
# active persona resolution                                                    #
# --------------------------------------------------------------------------- #
def default_persona() -> str | None:
    """The committed, team-wide default persona (``personas/.default``) — adopted when
    nothing else is selected. Shared/versioned (unlike the local ``.charter/active-persona``);
    ignored if it names a persona that no longer exists."""
    p = config.PERSONAS_DIR / ".default"
    # Gated like every other committed file charter reads: this one answers "who am I" on
    # every turn, so a FIFO here hangs the status line rather than costing a briefing.
    if contain.file_refusal(p):
        return None
    try:
        val = p.read_text().strip()
    except OSError:
        return None
    # `reference_ok` before `.exists()`: this dotfile is committed, so the value is a
    # teammate's, and "a path that exists" was never the question being asked (#337).
    return val if val and reference_ok(val) and def_path(val).exists() else None


#: The outbound postures a persona may declare, least → most insistent. `off` is what an
#: absent or unrecognised `routing:` means: a typo must not silently switch a gate on, and
#: an upgrade must change nothing for a plane that has declared nothing.
ROUTING_LEVELS = ("off", "advise", "require")


def routing_level(name: str) -> str:
    """How insistently *name* hands work away — its ``routing:``, inheritance-merged.

    ``delegate-when`` says what a persona accepts; this says when it should stop doing the
    work itself. Two directions, two words, deliberately unalike: a field called
    ``delegation`` beside ``delegate-when`` would be one letter and one glance apart from
    its own opposite.

    Read from the ACTING persona only — the one whose session this is. That is the whole
    reason there is no plane-level setting to merge with here: a floor would apply to
    personas that never declared anything, which is the action-at-a-distance this design
    was reshaped to avoid.
    """
    try:
        r = resolve(name)
    except Exception:
        return "off"
    if not r:
        return "off"
    val = str(r["meta"].get("routing") or "").strip().lower()
    return val if val in ROUTING_LEVELS else "off"


def routes_to(name: str) -> list[str]:
    """Personas *name* considers first — its ``routes-to:``, inheritance-merged.

    Priority, never restriction: it reorders the roster and removes nobody. A restricting
    form would silently hide every persona created after the line was written, and nothing
    would report the omission — the same failure shape `lint` had to grow a dangling-`uses:`
    check for.
    """
    r = resolve(name)
    return _csv_list(r["meta"].get("routes-to")) if r else []


def roster_for(active: str | None) -> list[dict]:
    """Every persona this session could hand work to, as ``{name, role, delegate_when,
    last_dispatched}`` — the facts charter owns, and nothing more.

    charter does not decide which of these owns the prompt (ADR 0016). It states who
    exists, what each one claims, and when each was last dispatched; the reader routes.

    Excludes the acting persona (routing to yourself is noise in a block that cannot
    afford any) and drafts (charter generates no sub-agent for a draft, so offering one
    would advertise a route that does not exist).
    """
    from . import dispatch
    rows = []
    for n in list_personas():
        if n == active or is_draft(n):
            continue
        try:
            r = resolve(n) or {}
            meta = r.get("meta", {})
        except Exception:
            continue
        rows.append({
            "name": n,
            "role": meta.get("role") or n,
            "delegate_when": (meta.get("delegate-when") or "").strip(),
            "last_dispatched": dispatch.last_seen(n),
        })
    first = routes_to(active) if active else []
    order = {n: i for i, n in enumerate(first)}
    # Declared order first, then everyone else alphabetically — a stable order matters on a
    # block that reappears: a roster that reshuffles between prompts reads as new content.
    rows.sort(key=lambda r: (order.get(r["name"], len(order)), r["name"]))
    return rows


def declared_default() -> str | None:
    """The front door this control plane DECLARES — ``charter.toml``'s ``[persona] default``.

    Outranks the legacy ``personas/.default`` dotfile, which keeps resolving so no plane
    that adopted it breaks. The move is about findability, not capability: the dotfile is
    invisible to ``ls``, appears in no documentation page, and was used by nobody —
    including this repo, whose own front door resolved through a gitignored local file
    instead (#255). ``charter.toml`` is the file a consumer already opens to understand
    their plane, and ``[workspace] default`` is already in it.

    Validated against what exists, exactly like :func:`default_persona`: a declaration
    naming a persona that was renamed or deleted resolves to *nothing* rather than to a
    broken identity. Saying so out loud is `doctor`'s job — silence here is the fail-toward-
    no-change half, not the whole answer.

    Never raises. A malformed or too-new ``charter.toml`` is a real error, and every actual
    command surfaces it through :func:`instance.load`; but this rung is read by hooks on
    every session start and every status-line paint, where the rule is that a hook may cost
    a session its briefing and never its turn.
    """
    from . import instance as _instance
    try:
        val = _instance.default_persona_of(_instance.load(config.ROOT))
    except Exception:
        return None
    # Same as `default_persona`: `charter.toml` is committed, so this rung picks the
    # session's acting identity out of a teammate-authorable file. Existence of a path was
    # the wrong question — a reference climbing out of `personas/` named a file the plane
    # does not contain, and `resolve()` merged its `vault:`, `role:` and `tools:` (#337).
    return val if val and reference_ok(val) and def_path(val).exists() else None


def plane_default() -> str | None:
    """The default persona this PLANE declares, or ``None`` — the two committed rungs of
    :func:`_resolved` and neither of the four session ones.

    That exclusion is the whole point of the function existing. :func:`resolve_active`
    answers *who am I being right now*, which moves with a `$CHARTER_PERSONA`, a session
    pointer or a `charter persona use`; this answers *who does this plane put first*,
    which is a committed fact and the same for every frame, every session and every
    teammate on the plane. :func:`by_use` pins the answer to the top of every switcher,
    and a pin that moved with the session would be the defect #882 is about wearing a
    different name.

    ``charter.toml`` before ``personas/.default`` for :func:`declared_default`'s own
    reason, and both are already validated against what exists, so a declaration naming a
    persona that was renamed resolves to nothing rather than pinning a name no switcher
    can offer.
    """
    return declared_default() or default_persona()


def _dispatches() -> dict:
    """agent → how many times it has been dispatched, ever. ``{}`` on any failure.

    One read of `personas/_dispatch/` per call and never one per persona — the store is a
    handful of month-and-host jsonl files, so the whole tally is a directory glob and a
    line walk (measured on this plane at 0.4 ms for 449 rows), while asking it per name
    would re-walk the same files once for each. Swallowed like every other number a
    switcher draws: an unreadable log is a roster in alphabetical order, never a frame
    that will not paint.

    That "handful" is the count TODAY, and it is one file per month per host forever
    after: the store only grows, this sits on a per-turn repaint path, and the walk was
    therefore monotonic in the age of the plane rather than in anything an operator does
    (#887). `dispatch._rows_of` memoises each file's rows on ``(path, mtime, size)``, so a
    closed month is parsed once per process and the reading is bounded by the current
    month. Nothing about the number this returns changed.
    """
    from . import dispatch
    try:
        return dict(dispatch.tally())
    except Exception:
        return {}


def by_use(names: list[str] | None = None) -> list[str]:
    """*names* (default: every persona) in the order a switcher offers them.

        **The declared default first, then most-dispatched first, ties broken by the
        larger memory count, then by name.**

    **Nothing here depends on which persona you are currently on**, and that is the whole
    of #882. The sidebar column used to lift the ACTIVE persona to the top
    (`statusline._persona_chip_cells`), so choosing a persona re-laid the list that had
    just been chosen from: every other row moved, and where a name sat depended on where
    the operator already was. A list whose rows reorder with state is a list nobody
    learns — `frame/slots._change_rows` settled the identical question for changes, and
    this is that rule arriving on the noun it was first broken for. The active persona is
    still MARKED, on every surface that draws it; being marked costs no other row its
    position.

    **Dispatch count and not memory count, and the two genuinely disagree.** Measured on
    this plane the day #882 was written: by memory it is `release 51`, `steward 47`,
    `statusline 14`, `forge 13`, `reddit 7`; by dispatch it is `release 26`, `forge 18`,
    `steward 11`, `statusline 8`, `reddit 4` — `forge` is second on one and fourth on the
    other. **A memory count only ever grows**, so it ossifies: a persona worked heavily
    one month outranks one used daily the next, permanently, because nothing ever takes a
    memory back. A dispatch count measures *use*, which is what makes a persona worth
    reaching for, and it is the same number `charter persona stats` retires personas on.

    **"Last dispatched" was considered and rejected**, and it is the sharper signal of the
    two — `dispatch.last_seen` already computes it. It is refused because it makes the
    list reorder far more often than a count does: every dispatch would be able to move a
    row, where a count only moves one past a neighbour it has overtaken. That is the same
    defect as lifting the selected item, one cause over, and a fix that reintroduces the
    thing it removes is not a fix.

    **The memory count is read only where dispatch counts TIE**, which is why the tie-break
    is a second pass rather than a second term in one sort key. `memory_count` is a
    directory glob per persona (`memstore.files`), a switcher opens on a keypress, and a
    key function is called once per element — so a single key would pay one glob per
    persona on every open, to decide an order the first term almost always decides alone.
    On this plane's five personas the dispatch counts are all distinct and this reads no
    memory directory at all. `groupby` over the already-sorted list is what makes "almost
    always" free rather than merely cheap.

    The name is the last term on both passes so the answer is TOTAL: two personas with the
    same dispatch count and the same memory count still have one order, the same one every
    time, on every machine. `sorted` over a set would have been an ordering that is right
    about half the time by luck — and that totality is also why *names* is not pre-sorted
    here: both passes below already end in the name, so a `sorted()` in front of them
    would be a line no test could go red without.

    **No early return for an empty roster either**, for the same rule one step further.
    Every line below is a no-op on `[]` — the two store reads answer for a plane, not for
    a name, and neither of them is reached per persona — so a guard would only save a
    directory glob on the one plane whose switcher has nothing to offer anyway.
    """
    names = list(list_personas() if names is None else names)
    default = plane_default()
    rest = [n for n in names if n != default]
    disp = _dispatches()
    rest.sort(key=lambda n: (-disp.get(n, 0), n))
    out = []
    for _, grp in _groupby(rest, key=lambda n: disp.get(n, 0)):
        run = list(grp)
        # One name in the run is one order already, and asking for its memory count would
        # be a directory glob spent on a comparison with nobody.
        out.extend(run if len(run) == 1
                   else sorted(run, key=lambda n: (-memory_count(n), n)))
    return ([default] if default in names else []) + out


def memory_count(name: str) -> int:
    """How many persistent memories *name* holds — :func:`by_use`'s tie-break, and 0 for a
    persona whose directory cannot be read.

    Its own function rather than a `len(memories(...))` inside the sort, because the tie-
    break is exactly what a mutation sweep attacks and a named thing can be measured
    directly. The 0 is the same fail-toward-no-change every other number on a switcher
    takes: an unreadable memory directory demotes a persona within its tie group, and does
    not raise out of a repaint.
    """
    try:
        return len(memories(name))
    except Exception:
        return 0


def _pointer_files(session_id: str | None = None,
                   terminal_id: str | None = None) -> tuple[Path | None, Path | None]:
    """``(session pointer, terminal pointer)`` for right now — either may be ``None``.

    Mirrors workspaces exactly (``.charter/sessions/<id>.workspace`` and
    ``.charter/terminals/<id>.workspace``), because the failure it prevents is the same
    one, one noun over: a single plane-wide file meant `charter persona use forge` in one
    pane changed the persona in every other pane and every future session, which is the
    opposite of what a fleet of parallel personas is for (#255).

    ``session_id`` names *whose* session pointer, for the same reason
    `workspace.set_active` takes one: the process writing is not always the session being
    written for. A frame's persona switcher (`frame/switch.py`) is the case — it runs as a
    `run-shell` child of the tmux server and must write under the FRAME's id, which it was
    handed, rather than under whatever `$CHARTER_SESSION_ID` that child happens to have
    inherited from a server shared with every other frame on the machine (#411).

    ``terminal_id=""`` says the same thing about the TERMINAL pointer, and is the half
    that matters more: `session.terminal()` reads `$TERM_SESSION_ID`/`$TMUX_PANE`/`$STY`/
    `$SSH_TTY`, and in that same `run-shell` child those belong to whichever launcher
    started the shared server. Writing a persona pointer for THAT terminal would change
    the persona in a terminal nobody touched. See `workspace.set_active`'s own note.
    """
    from . import session as _session
    sid = _session.current(session_id)
    tid = _session.terminal() if terminal_id is None else terminal_id
    return (config.SESSIONS_DIR / f"{sid}.persona" if sid else None,
            config.TERMINALS_DIR / f"{tid}.persona" if tid else None)


def _read_pointer(f: Path | None) -> str | None:
    if f is None:
        return None
    try:
        return f.read_text().strip() or None
    except OSError:
        return None


def pointers_naming(name: str) -> dict[str, int]:
    """How many selections on this machine name *name*, by rung: ``session``, ``terminal``
    and ``active-file`` (0 or 1), counted through the reader :func:`_resolved` uses.

    Every session's and every terminal's, not this process's: `persona create` asks it
    because a new persona becomes the selection of every pointer a removed one of that name
    left behind, in sessions nobody is looking at (#1045). A pointer outlives its session, so
    some of these may belong to sessions that will never run again, and the count does not
    pretend to know which.
    """
    def count(d: Path) -> int:
        return sum(1 for f in d.glob("*.persona") if _read_pointer(f) == name)
    return {"session": count(config.SESSIONS_DIR),
            "terminal": count(config.TERMINALS_DIR),
            "active-file": int(_read_pointer(config.ACTIVE_PERSONA_FILE) == name)}


def for_session(sid: str) -> str | None:
    """The persona explicitly chosen FOR *sid*, or ``None`` if nobody chose one.

    The per-session rung of :func:`_resolved`, asked about a session that is not
    necessarily this process's — the exact counterpart of `workspace.for_session`, and
    public for the same reason. A frame's palette (`frame/switch.py`) has to mark the persona
    the PANELS are showing, and it runs as a `run-shell` child of a tmux server shared
    between every frame on the machine, so reading the rung out of its own environment
    would answer for whichever frame started that server (#411).

    Name-checked on the way out, like `workspace.for_session`: the value ends up in
    :func:`dir_of`'s join and on a panel's screen.
    """
    val = _read_pointer(config.SESSIONS_DIR / f"{sid}.persona") if sid else None
    return val if val and valid_name(val) else None


def from_environment() -> str | None:
    """The persona ``$CHARTER_PERSONA`` names, or ``None`` when it names none (#1048).

    **Stripped, and what is left empty is unset.** The variable used to be taken as the top
    rung whenever it was set and stripped only after that, so a value of whitespace resolved
    to ``""`` and hid every rung below it: the session pointer, the terminal pointer, the
    plane-wide file and the plane's declared default. `export CHARTER_PERSONA=$(…)` over a
    command that printed only a space or a tab leaves exactly that — the shell strips the
    trailing newlines of a substitution and nothing else — and nobody chose it. Empty was
    already unset — `commands_frame._frame_identity_env` launches every chat with
    ``CHARTER_PERSONA=`` — and this is that rule one character further, the one
    `session.current` applies to ``$CHARTER_SESSION_ID`` and `frame.switch._pin` to a launch
    pin. A name inside the whitespace is that name, as a pointer file's content is.

    The one reading of the variable: :func:`_resolved` ranks it, `commands_persona._warn_env`
    says it outranks a `use`, and a second copy is how those two came to disagree about
    ``" "``.
    """
    return os.environ.get("CHARTER_PERSONA", "").strip() or None


def blank_in_environment() -> bool:
    """``$CHARTER_PERSONA`` is set to whitespace and nothing else, so :func:`from_environment`
    ignored it (#1048).

    Worth saying because the operator's export is broken, and resolution going on through the
    rungs below hides that from them. Empty is not reported: it is what a frame launches every
    chat with when the launch pinned nothing, so it would be said in every chat about an
    export nobody wrote.
    """
    return bool(os.environ.get("CHARTER_PERSONA")) and from_environment() is None


def blank_flag(value: str | None) -> str | None:
    """The refusal for a ``--persona`` holding only whitespace, or ``None`` for any other
    value (#1055).

    **Refused, where the variable is ignored.** A flag is typed for one command, on purpose,
    so there is no rung below it that the operator meant instead: falling through would run
    `persona secret` against the active persona's vault or search the active persona's
    memory, neither of which they named. Taken as a name, it did worse and said nothing
    true: `persona secret --persona " "` blamed a vault file no whitespace name can have,
    and `recall --persona " "` searched a persona called `' '` and answered "No memories
    yet". The wording is `persona use`'s for a name that defines nothing.

    Empty is not refused. Every reader of the flag tests it for truth, so `--persona ""` has
    always meant no flag, and ``""`` is how charter's own records spell "no persona".
    """
    if value and not value.strip():
        return (f"no persona '{contain.one_line(value)}' (a persona name is never only "
                "whitespace)")
    return None


#: What every command says to a valid name that defines nothing here. One spelling, so no
#: command can come to describe the same absence in different words (#1057, #1059).
NO_SUCH_PERSONA = "no persona '{name}' (create it: charter persona create {name})"

#: What every command says to a name outside the alphabet. No create hint, because this is
#: the refusal `persona create` gives and that hint would lead to.
INVALID_NAME = "invalid persona name '{name}' (lowercase letters, digits, '.', '_', '-')"

#: What every command says to a valid name whose definition file is there and does not load
#: (#1061). No create hint, because `persona create` refuses a name whose file is there, and
#: no reason, because `persona lint` is the command that says why and this does not guess.
DOES_NOT_LOAD = "persona '{name}' does not load from {file} (see why: charter persona lint {name})"

#: :data:`DOES_NOT_LOAD` for the persona *name* inherits from, which is the one that does not
#: load, so the line names both and points `lint` at the parent (#1061).
INHERITS_ONE_THAT_DOES_NOT_LOAD = (
    "persona '{name}' inherits from '{parent}', which does not load from {file} "
    "(see why: charter persona lint {parent})")


def name_refusal(name: str, *, defined: bool = True) -> str | None:
    """The refusal for a persona name a command was given, or ``None`` when it names a
    persona this plane defines (#1059). With ``defined=False``, when it is a name a persona
    could have.

    **Every command that takes a persona name asks this, first, before it looks anything
    up.** Each used to check in its own way, and the ways disagreed. `persona use ../x`
    offered `charter persona create ../x`, which `persona create` refuses. `persona secret
    --persona devosp` never checked at all, so `vault_of`'s fallback read the vault tagged
    `devosp` for a persona nobody defines. `persona stats devosp` exited 0 over a row for
    it. `vault add --persona` stored whatever it was given as the vault's owner (#1057).

    Four sentences for four fixes. Whitespace is :func:`blank_flag`'s. A name outside the
    alphabet is :data:`INVALID_NAME`, with no create hint, because `persona create` would
    refuse it. A valid name nothing defines is :data:`NO_SUCH_PERSONA`, hint included.
    Existence is :func:`load`'s answer, so every command refuses the persona `persona use`
    refuses. ``defined=False`` is for the callers that answer existence themselves: `persona
    create`, which makes the persona, and the ones that say more about a missing persona
    than "no persona" can.

    A valid name whose definition file is there and does not load is :data:`DOES_NOT_LOAD`
    (#1061). It was called absent, and the create hint it got is one `persona create`
    refuses, because the file is there. "Is there" is the test `persona create` refuses on,
    so the hint is given exactly when `create` would take it. A file `load` cannot read or
    decode raised out of every command that asked; it does not load either. A persona that
    loads and inherits from one that does not is :data:`INHERITS_ONE_THAT_DOES_NOT_LOAD`,
    because what `resolve` builds for it is missing that parent.

    An empty name is refused as outside the alphabet. A *flag* reads empty as not given,
    and :func:`undefined_flag` is that reading.
    """
    refused = blank_flag(name)
    if refused:
        return refused
    # Before `load`, which answers None for this too and would reach the create hint.
    if not valid_name(name):
        return INVALID_NAME.format(name=contain.one_line(name))
    if not defined:
        return None
    if load(name) is None:
        file = def_path(name)
        if file.exists():
            return DOES_NOT_LOAD.format(name=name, file=file.relative_to(config.ROOT))
        return NO_SUCH_PERSONA.format(name=name)
    parent = ancestor_that_does_not_load(name)
    if parent:
        return INHERITS_ONE_THAT_DOES_NOT_LOAD.format(
            name=name, parent=parent, file=def_path(parent).relative_to(config.ROOT))
    return None


def undefined_flag(value: str | None) -> str | None:
    """:func:`name_refusal` for a ``--persona``-shaped flag, or ``None`` when the flag was
    not given (#1057).

    Empty is no flag, as it is for :func:`blank_flag`. Every reader of such a flag tests it
    for truth, and ``""`` is how charter's own records spell "no persona".
    """
    if not value:
        return None
    return name_refusal(value)


def _resolved(explicit: str | None = None) -> tuple[str | None, str]:
    """``(persona, where it came from)`` — the whole precedence, decided ONCE.

    :func:`resolve_active` and :func:`source` are two questions about a single decision,
    and they used to walk the rungs separately. Two ladders answering one question is the
    shape this repo's own convention warns about: adding a rung to one and forgetting the
    other yields a session that adopts a persona while reporting it came from nowhere.
    """
    if explicit:
        return explicit, "--persona"
    env = from_environment()
    if env:
        return env, "$CHARTER_PERSONA"
    sf, tf = _pointer_files()
    val = _read_pointer(sf)
    if val:
        return val, "session"
    val = _read_pointer(tf)
    if val:
        return val, "terminal"
    f = config.ACTIVE_PERSONA_FILE
    if f.exists():
        val = f.read_text().strip()
        if val:
            return val, "active-file"
    declared = declared_default()
    if declared:
        return declared, "charter.toml"
    committed = default_persona()
    if committed:
        return committed, "committed-default"
    return None, "none"


def resolve_active(explicit: str | None = None) -> str | None:
    """Active persona by precedence: ``--persona`` → ``$CHARTER_PERSONA`` → local
    ``.charter/active-persona`` (``charter persona use``) → declared ``charter.toml``
    ``[persona] default`` → committed ``personas/.default`` → none."""
    return _resolved(explicit)[0]


def source(explicit: str | None = None) -> str:
    return _resolved(explicit)[1]


class Selection(NamedTuple):
    """What :func:`_resolved` decided, and whether the persona it names is defined here."""

    name: str | None
    source: str
    exists: bool

    @property
    def missing(self) -> bool:
        """A rung named a persona and there is none — which is not the same as no rung
        naming anything, where there is nothing to report."""
        return bool(self.name) and not self.exists


def selection(explicit: str | None = None) -> Selection:
    """``(persona, where it came from, whether that persona exists)``, decided once (#1045).

    **A rung that names a persona that does not exist still wins, and this does not change
    that.** `persona remove` leaves every session and terminal pointer that named the
    persona, so those sessions resolve to a name that defines nothing, and every rung below
    it — the plane's declared default included — stays hidden. Falling through instead would
    hand the session a persona, with its tool grants and its vault, that nobody chose for
    it; staying on the name fails toward no role and no grants. What was wrong is that
    nothing said so, so the answer is carried to every surface that reports a selection
    rather than each of them checking the name again, and disagreeing about how.

    ``exists`` asks what the two committed rungs already ask before they answer
    (:func:`declared_default`, :func:`default_persona`), so those two are always ``True``
    here, and only the rungs a person or a shell wrote can come back ``False``. The name
    check is not optional: a pointer is a file, and ``../personas/forge`` spells a path
    where a definition sits without naming a persona. It also answers ``False`` for no name
    at all, which is why nothing in front of it asks.
    """
    name, src = _resolved(explicit)
    return Selection(name, src, reference_ok(name) and def_path(name).exists())


def ways_out(source: str) -> str:
    """The commands that move a selection held at *source*, as a clause (#1045).

    One answer for every surface that names a missing persona, because the true answer
    depends on the rung and a second copy would be the one that offered a command that does
    nothing. Only the rungs :func:`selection` can report missing reach here: the committed
    two are checked before they answer, and ``--persona`` is not a selection anybody reports.

    ``$CHARTER_PERSONA`` outranks both pointers, so `use` and `clear` leave it deciding. In a
    chat, `clear` drops the chat's session pointer and nothing else (#1022): the terminal
    pointer it resolves is keyed on an id the chat inherited, and the plane-wide file on a
    shell with no ids, so offering `clear` there for either would send the reader to a
    command that leaves the stale name exactly where it was. Who owns that pointer is not
    said, because an inherited terminal id can be a launcher's or a recycled pane's, and
    naming one would be a guess (ADR 0009).
    """
    if source == "$CHARTER_PERSONA":
        return ("unset `$CHARTER_PERSONA`, or set it to a persona that exists; it outranks "
                "`charter persona use` and `charter persona clear`, so neither moves it")
    from . import workspace
    if source != "session" and workspace.launch_lock():
        return ("`charter persona use <persona>` selects one for this chat; `charter persona "
                "clear` here drops only this chat's own selection, and this is not it")
    return ("`charter persona use <persona>` selects one that exists, or `charter persona "
            "clear` drops the selection")


def set_active(name: str, session_id: str | None = None,
               terminal_id: str | None = None) -> str:
    """Select *name* for this session and this pane. Returns the reach of what was written
    (``session`` | ``terminal`` | ``plane``) so a caller can say how long it will last.

    The plane-wide file is written only when there is neither a session id nor a pane id —
    a bare shell with nothing to key on. That is the one case where it is still the right
    answer, and it is why the file is kept rather than removed.

    ``session_id`` and ``terminal_id`` state which session and which terminal are being
    selected for, rather than letting :func:`charter.session` read them out of the
    environment — see :func:`_pointer_files` for the case that needs it. Ordinary callers
    (`charter persona use`) leave both unset and get exactly today's behaviour.

    **``name`` is a name, and the ``(name or "")`` that used to stand in front of both
    writes is gone.** The deletion sweep reported it twice as a survivor and it was right:
    all three callers hand this a non-empty string — `cmd_persona_use` and
    `cmd_persona_create` pass a required argparse positional, and `frame.switch.to_persona`
    has already run `valid_name` and checked the roster before it gets here — so nothing
    in the package could reach the fallback and no test could tell the two spellings apart.
    Deleting it is the same finding as an equivalent mutant, and it makes a call that
    should not happen fail loudly (a `TypeError` naming the argument) rather than quietly
    writing a pointer that means "nobody", which is what `clear_active` is for.

    **All three pointers go through `config.write_for`, which settles the mode on the
    descriptor before any content lands.** These were the three writers #505 routed the
    rest of the package's state through and left out — not because they are different, but
    because two other branches were live in this file at the time. `Path.write_text`
    creates at ``0o777 & ~umask``, so on a plane whose ``.charter/`` predates charter (0755,
    and charter will not chmod a directory it did not create — #331) these came out 0644,
    and under ``umask 000`` **0666**. The read side leaks little — a persona name is also
    the name of a committed directory under ``personas/`` — but the write side is the sharp
    half: ``.charter/sessions/`` and ``.charter/terminals/`` decide which charter a session
    runs as, and a world-writable pointer is one another account gets to set (#581).
    """
    config.private_mkdir(config.STATE_DIR)
    sf, tf = _pointer_files(session_id, terminal_id)
    for f in (sf, tf):
        if f is not None:
            config.private_mkdir(f.parent)
            config.write_for(f, name + "\n")
    if sf is None and tf is None:
        config.write_for(config.ACTIVE_PERSONA_FILE, name + "\n")
    try:
        from . import trace
        trace.record("persona-use", persona=name)
    except Exception:
        pass
    # The terminal pointer outlives the session one, so it names the longest-lived thing
    # that actually landed — the same reasoning `workspace.use` records for its own return.
    return "terminal" if tf is not None else "session" if sf is not None else "plane"


def clear_active(terminal_id: str | None = None) -> bool:
    """Drop this session's and this pane's selection, and the plane-wide file with them.
    Returns whether any pointer it dropped held a selection — in a chat, only the session's,
    which is all a chat has to clear; anywhere else, any of the three, because each of them
    is a selection `clear` removed (#1045: "cleared" was printed over a shell that held none).

    All three, because they are rungs of one ladder: clearing only the top rung would hand
    the session straight back to a lower one, and "cleared" would be a lie the very next
    command exposes.

    ``terminal_id=""`` is `set_active`'s: this process speaks for no terminal (#1022). Inside
    a chat `session.terminal` answers the `$TERM_SESSION_ID` of the terminal that launched
    the frame, so the pointer this used to unlink was THAT terminal's choice. Measured: the
    launcher ran `use forge`, a chat ran `clear`, and the launcher resolved `None`.

    **And then it speaks for no plane-wide file either.** `set_active` writes that file only
    for a shell with neither a session id nor a pane id, so a caller with no terminal to
    speak for, and a session of its own, never wrote it. So the ladder argument above stops
    at this session's rung here, on purpose: the rungs below it are someone else's choice,
    and the caller says what it now resolves to rather than calling them cleared.
    """
    sf, tf = _pointer_files(terminal_id=terminal_id)
    plane = () if terminal_id == "" else (config.ACTIVE_PERSONA_FILE,)
    # Read before the unlink, through the reader `_resolved` uses, so "held a selection" means
    # what those rungs would have answered rather than "a file was there". In a chat `tf` is
    # None and `plane` is empty, so this is the session pointer alone there.
    held = any(_read_pointer(f) is not None for f in (sf, tf, *plane))
    for f in (sf, tf, *plane):
        try:
            if f is not None and f.exists():
                f.unlink()
        except OSError:
            pass
    return held


# --------------------------------------------------------------------------- #
# tools + reuse                                                                #
# --------------------------------------------------------------------------- #
def tools_of(name: str) -> set[str]:
    """Commands the persona is allowed to run without a prompt (its ``tools:``),
    **including inherited** ones (union across the ``extends`` chain)."""
    r = resolve(name)
    return _csv_set(r["meta"].get("tools")) if r else set()


def uses_of(name: str) -> list[str]:
    """Other personas this one may reuse — its ``uses:`` field (inherited-inclusive).
    Reusing a persona means it may read that persona's vault, run its tools, and
    delegate to its sub-agent (see the charter it's generated into)."""
    r = resolve(name)
    return _csv_list(r["meta"].get("uses")) if r else []


#: A `borrows:` value meaning "deliberately nothing" — the same spelling `vault: none`
#: already uses for the same idea, so the vocabulary stays one vocabulary.
BORROWS_NONE = "none"


#: The keys whose unreadability makes :func:`borrows_of`'s ``None`` a lie, and therefore
#: the ones a grant may not be widened over.
#:
#: ``borrows`` is #575's own defect: the answer is read off the key's ABSENCE, so a
#: spelling charter cannot read is indistinguishable from an author who never opted in.
#:
#: ``extends`` is the same fail-open one key over, and it was found by asking this list the
#: question rather than by trusting the issue's. A child declaring ``Extends: parent`` does
#: not inherit its parent's ``borrows:``, so a chain that opted OUT of the legacy grant
#: hands the child the wide one:
#:
#:     parent:  borrows: none
#:     kid:     Extends: parent   uses: forge   → forge's tools, auto-approved
#:
#: Charter cannot follow a chain it could not read, which is precisely why it must not
#: conclude "this persona declared no ``borrows:``" from the end of one.
_GRANT_DECIDING_KEYS = ("borrows", "extends")


def _borrows_unreadable(resolved: dict) -> bool:
    """Did the author write a grant-deciding declaration charter could not read?

    The whole of #575's teeth live in the difference between that and "the author never
    mentioned borrowing", because :func:`effective_tools` widens on the second one.
    Two spellings of unreadable, both of which used to answer *absent*:

    * a key that differs from one of :data:`_GRANT_DECIDING_KEYS` only by case —
      ``Borrows: none`` was read by nothing, so the persona kept the legacy grant it had
      just written the word to give up, and
    * one of them on two lines, where the dict keeps whichever is lower in the file, so
      ``borrows: none`` above ``borrows: forge`` grants `forge`'s tools by line order.

    Both are asked of the whole inheritance chain, unlike :func:`key_issues`, and that
    asymmetry is deliberate: a REPORT belongs to the file that has to be edited, while a
    GRANT belongs to the persona the tool gate is deciding about. A parent whose
    ``Borrows:`` charter could not read must not hand its children the wide grant either.

    Deliberately NOT "any key charter could not read". A persona with an unrelated typo
    would silently lose its legacy `uses:` grant, which is a fail-closed nobody asked for
    and nothing would explain — the same over-reach that made the general unknown-key
    finding a warning rather than an error.

    The case half is read off the *resolved* meta, which costs nothing — `resolve` copies
    a key it does not recognise straight through, so an ancestor's ``Borrows`` is already
    sitting in the merged dict under that spelling. Only the duplicate half needs the
    per-file answer, and only that half walks.
    """
    if any(misspelled_key(k) in _GRANT_DECIDING_KEYS for k in resolved["meta"]):
        return True
    for a in resolved.get("lineage") or ():
        d = load(a)
        if d and any(k in (d.get("dupes") or ()) for k in _GRANT_DECIDING_KEYS):
            return True
    return False


def borrows_of(name: str) -> list[str] | None:
    """Personas whose tools and vault this one may use — its ``borrows:``, or ``None`` when
    the key is absent.

    ``None`` and ``[]`` are different answers and the difference is the whole feature:
    absent means "I have not opted in, keep the legacy `uses:` grant", while
    ``borrows: none`` means "I borrow nothing". Collapsing them would either break every
    existing plane or make opting out unsayable.

    **`None` means the author never mentioned borrowing, and nothing else (#575).** It used
    to also mean "the author mentioned it and charter did not read the key", which made
    this the one field in the file that fails OPEN: every other miscased key costs the
    persona something — a miscased ``Vault:`` means no credentials, a miscased ``Tools:``
    means no auto-approvals — while a miscased ``Borrows:`` fell through to the legacy
    ``uses:`` grant, which is the WIDER one. An author writing ``Borrows: none`` to opt out
    of #257's grant got #257's grant, both borrowed personas' tools auto-approved at
    `toolgate.decide`, and `structural_errors` empty.

    So an unreadable declaration answers ``[]`` — borrow nothing — and never ``None``. That
    is narrower than the author asked for whenever they meant ``Borrows: forge``, and
    narrower is the direction this may be wrong in: the persona pays a permission prompt it
    did not expect and `persona lint` names the line to fix, which is a cost measured in one
    edit. The other direction is measured in a vault.
    """
    r = resolve(name)
    if not r:
        return None
    if _borrows_unreadable(r):
        return []
    if "borrows" not in r["meta"]:
        return None
    vals = _csv_list(r["meta"].get("borrows"))
    return [v for v in vals if v != BORROWS_NONE]


def effective_tools(name: str) -> set[str]:
    """The persona's own auto-approved tools, plus those it may borrow (one level).

    Which personas those are depends on whether this persona has opted into the split:

    * ``borrows:`` declared → its tools come from that list, and ``uses:`` is a routing
      edge only. This is the point of the field. ``uses:`` granted vault access, tool
      auto-approval and delegation in one word, and the middle grant is why delegating
      always lost: a front door declaring ``uses: forge, release`` could do both personas'
      work with both personas' tools and never pay a prompt, while handing the work over
      cost a dispatch and the context with it (#257).
    * ``borrows:`` absent → the legacy grant, unchanged. Fails toward no change, per
      persona: opting one persona in must never alter another's permissions, which is
      exactly what a plane-wide switch would have done.
    """
    tools = tools_of(name)
    borrows = borrows_of(name)
    for other in (uses_of(name) if borrows is None else borrows):
        tools |= tools_of(other)
    return tools


def _enabled_plugin_names() -> set[str]:
    """Plugin names enabled in the committed .claude/settings.json (the part before '@')."""
    try:
        import json
        data = json.loads((config.ROOT / ".claude" / "settings.json").read_text())
        return {str(k).split("@", 1)[0] for k in (data.get("enabledPlugins") or {})}
    except Exception:
        return set()


#: Process-global memo for the plugin-cache walk below. A sentinel rather than None,
#: because "no plugin cache on this machine" is itself a cacheable answer.
_SKILLS_UNSET = object()
_SKILLS_CACHE: object = _SKILLS_UNSET


def _reset_skill_cache() -> None:
    """Forget the memoised plugin-cache walk. For tests, and for any caller that
    would install a plugin mid-process."""
    global _SKILLS_CACHE
    _SKILLS_CACHE = _SKILLS_UNSET


def _installed_skills() -> dict[str, bool] | None:
    """:func:`_walk_installed_skills`, memoised for the life of the process.

    The walk reads every ``SKILL.md`` under ``~/.claude/plugins`` — 96 skills and
    ~27ms on a real machine — and :func:`lint` calls it once per persona, so a
    13-persona roster paid it 13 times: 358ms of a 364ms sweep. That cost is why
    ``doctor`` could not afford to lint the roster at all. The plugin cache cannot
    change during a single command, so one walk is enough.
    """
    global _SKILLS_CACHE
    if _SKILLS_CACHE is _SKILLS_UNSET:
        _SKILLS_CACHE = _walk_installed_skills()
    return _SKILLS_CACHE  # type: ignore[return-value]


def _skill_roots() -> list:
    """Every directory the harness resolves a skill from, in the order it reads them.

    Three, not one. Walking only the plugin cache made two charter commands disagree about
    what a skill is (#286): `charter browser install` writes
    `.claude/skills/playwright-cli/` — that path chosen because the harness reads project
    skills from there — and `persona lint` then called it "not installed here … Remove it or
    install the plugin". There is no plugin to install; charter deliberately does not vendor
    those pages, which is the whole reason `browser install` exists.

    The lint's own justification is that a declared skill costs context on every dispatch, so
    a dead entry is paid forever for nothing. That argues for accuracy about what EXISTS, not
    about what happens to be packaged.

    **These are the DEFAULT config folder's, and not a harness profile's** (ruling 16). A
    profile can point Claude Code at another folder with its own `plugins/` and `skills/`;
    a persona belongs to the plane and is declared once for every chat on it, so an answer
    that followed one chat's profile would lint the same persona differently depending on
    which account asked.
    """
    from pathlib import Path as _P
    home = _P.home() / ".claude"
    return [home / "plugins", home / "skills", _P(config.ROOT) / ".claude" / "skills"]


def _walk_installed_skills() -> dict[str, bool] | None:
    """Map each available skill's leaf-name → is it **model-invokable** (i.e. not
    ``disable-model-invocation: true``), scanned from :func:`_skill_roots`.

    Returns None when the plugin cache is absent, so lint can skip gracefully on a fresh
    clone / CI without plugins. Keyed on the PLUGIN cache specifically, even though project
    skills are now walked too: without it charter cannot see plugin-provided skills at all,
    so checking anyway would report every one of them as missing — confidently wrong, which
    is worse than silent."""
    from pathlib import Path as _P
    roots = _skill_roots()
    if not roots[0].exists():
        return None
    out: dict[str, bool] = {}
    for sk in [f for r in roots if r.exists() for f in r.rglob("SKILL.md")]:
        try:
            lines = sk.read_text().splitlines()
        except OSError:
            continue
        if not lines or lines[0].strip() != "---":
            continue
        skname, dmi = None, False
        for ln in lines[1:]:
            if ln.strip() == "---":
                break
            if ln.startswith("name:"):
                skname = ln.split(":", 1)[1].strip().strip("\"'")
            elif ln.startswith("disable-model-invocation:"):
                dmi = ln.split(":", 1)[1].strip().lower() == "true"
        skname = skname or sk.parent.name
        out[skname] = out.get(skname, False) or (not dmi)  # invokable if ANY copy is
    return out or None


# `plugin:skill` inside backticks = a skill an AGENT invokes (must be model-invokable);
# the `/skill` slash form is a human step (allowed to be human-only). Charters follow this.
_SKILL_REF_RE = re.compile(r"`([a-z0-9][a-z0-9-]*):([a-z0-9][a-z0-9-]*)`")


def _skill_ref_issues(charter: str) -> list[tuple[str, str]]:
    """Every ```plugin:skill``` an enabled plugin's charter names for agent use must
    resolve to an installed, model-invokable skill — else it's a dead/human-only name that
    a sub-agent can't invoke (the exact rot that shipped un-caught before)."""
    skills = _installed_skills()
    if skills is None:  # no plugin cache here → can't verify; skip
        return []
    plugins = _enabled_plugin_names()
    if not plugins:
        return []
    out = []
    for m in _SKILL_REF_RE.finditer(charter or ""):
        plug, skill = m.group(1), m.group(2)
        if plug not in plugins:
            continue  # not a reference to an enabled plugin's skill
        if skill not in skills:
            out.append(("error", f"charter names `{plug}:{skill}` — not an installed skill "
                                 "(renamed/removed upstream?); fix it or pin the marketplace"))
        elif not skills[skill]:
            out.append(("error", f"charter names `{plug}:{skill}` for agent use, but it's "
                                 "human-only (disable-model-invocation) — a sub-agent can't "
                                 "invoke it; use the /slash form for a human step"))
    return out


#: Frontmatter values are plain strings — :func:`parse` does no type coercion — so
#: ``draft: false`` arrives as the string ``"false"``, which is *truthy*. Every read of
#: the flag goes through :func:`is_draft` for exactly this reason.
_DRAFT_TRUE = {"true", "yes", "1", "on"}


def is_draft(name: str) -> bool:
    """Is this persona's charter still unfinished, and therefore undispatchable?

    ``charter persona create`` stamps ``draft: true``; the author removes the line when
    the charter says something real. While it is set, no sub-agent is generated — a
    generated agent file *is* a sub-agent's system prompt, and shipping an unwritten
    charter there tells an agent its responsibilities are whatever the scaffold said.

    Adoption is deliberately still allowed: ``persona use`` injects only the identity
    line and a pointer to ``charter persona show``, never the charter body, and a human
    is reading. That asymmetry is the whole rule.

    Resolved, not own — a child ``extends:``-ing a draft parent concatenates the
    parent's unfinished charter into its own dispatched prompt, so it inherits the
    label like any other scalar (and may override it with an explicit ``draft: false``).
    """
    d = resolve(name)
    if not d:
        return False
    return str(d["meta"].get("draft", "")).strip().lower() in _DRAFT_TRUE


def _reference_problem(field: str, ref: str, known: set[str]) -> tuple[str, str] | None:
    """Why *ref* cannot be used as a persona reference, or None when it can.

    Three failures, said three ways, because they send the reader to three different
    places. A name that is simply absent is a typo or a rename — "dangling" is right, and
    hunting for the persona is the fix. A reference that is a *path* is not a name at all:
    no amount of looking for that persona will help, and the fix is in the file. And a
    reference that is neither — ``"parent"``, quoted — is refused by the *alphabet*, where
    the fix is two characters. #328's whole shape is a distinction like these being
    collapsed, so each gets its own sentence.

    It said two, and that is #361: this line rendered `contain.refusal` for either half of
    :func:`reference_ok`, so a quoted reference — no separator, no dot, not absolute — was
    answered with a sentence enumerating separators, dots and absolute paths. The
    distinction this docstring exists to draw was collapsed on the line below it.
    :func:`reference_refusal` now decides the verdict and the sentence together.

    Shares :func:`reference_ok` with :func:`load`, which is what makes lint and the
    resolver structurally unable to disagree again — the property whose absence let the
    gate honour a grant `lint` was calling dangling in the same run.
    """
    refused = reference_refusal(ref)
    if refused:
        return ("error", f"{field}: {refused}")
    if ref not in known:
        return ("error", f"{field}: '{ref}' — no such persona (dangling)")
    return None


def structural_errors(name: str, known: set[str] | None = None) -> list[tuple[str, str]]:
    """The ``error``-level half of :func:`lint`: references that do not resolve.

    A dangling ``extends:``/``uses:`` or an inheritance cycle makes a persona broken
    rather than untidy — the resolver cannot build it. Split out from :func:`lint`
    (which calls this, so there is still one implementation) because the status line
    needs exactly this subset on **every turn** and none of the rest: no ``vault_of``,
    no role/delegate-when, no walk of the plugin cache, and no import of any command
    module.

    ``known`` lets a caller sweeping the whole roster pass ``list_personas()`` once
    instead of paying for it per persona — 1.6ms of a 5.2ms 13-persona sweep.

    :func:`key_issues` is here, and it is the one thing this gained. A key charter could
    not honour is the same kind of broken as a dangling reference — the resolver builds a
    persona out of a file that says something else — and it is where the fail-open shows:
    ``Borrows: none`` narrows the grant now (#575), so the operator has to be told which
    line did it by the signal that is on screen, not by a command they may never run.

    It cost nothing to move here. This function used to be unable to ask about keys at
    all, because the vocabulary lived in `commands_persona` and the import was the whole
    expense; the vocabulary is :data:`KNOWN_KEYS` in this module now, and `lint`'s own
    unknown-key scan stopped paying for that import too. The general unknown-key WARNING
    stays in `lint` — it is not an error and this half is the error half.
    """
    allnames = known if known is not None else set(list_personas())
    issues: list[tuple[str, str]] = list(key_issues(name))
    refused = definition_refusal(name)
    if refused:
        # First, and on its own terms: every check below reads through `load`, which
        # returns None for this persona, so without this line a definition charter
        # DECLINED to read is indistinguishable from one that says nothing — and the
        # operator is looking straight at the signal that would have told them (#336).
        issues.append(("error", f"persona.md: {refused}"))
    for u in uses_of(name):
        problem = _reference_problem("uses", u, allnames)
        if problem:
            issues.append(problem)
    for b in borrows_of(name) or ():
        problem = _reference_problem("borrows", b, allnames)
        if problem:
            issues.append(problem)
    d = load(name)
    ext = ((d["meta"] if d else {}).get("extends") or "").strip()
    if ext:
        problem = _reference_problem("extends", ext, allnames)
        if problem:
            issues.append(problem)
        else:
            # Listed, so not dangling, and still missing from what `resolve` builds (#1061).
            parent = ancestor_that_does_not_load(name)
            if parent:
                issues.append(("error", "extends: " + DOES_NOT_LOAD.format(
                    name=parent, file=def_path(parent).relative_to(config.ROOT))))
    cycle = _inherits_cycle(name)
    if cycle:
        issues.append(("error", f"extends: inheritance cycle ({cycle})"))
    return issues


def declared_skills(name: str) -> list[str]:
    """The skills this persona is accountable for, from its ``skills:`` frontmatter.

    Not an allowlist — the host has no such thing. `skills:` **preloads** the full text of
    each skill into the sub-agent's context at startup, so a declared skill is standing
    equipment the persona begins holding rather than something it might discover. Access is
    all-or-nothing and lives elsewhere: ``Skill`` in or out of ``agent-tools``.

    The prose and this list answer different questions, which is what keeps them from being
    the duplicate index ADR 0010 warns about. Prose says *when and how* to use a skill; this
    says *what the persona starts holding*. Only this one can be acted on — charter emits it
    into the generated agent, and prose can only mention.

    Comma-separated, matching ``uses:`` — one frontmatter idiom for one shape of list.
    """
    d = load(name)
    if not d:
        return []
    raw = (d["meta"].get("skills") or "").strip()
    return [t.strip() for t in raw.split(",") if t.strip()]


def declared_skill_issues(name: str) -> list[tuple[str, str]]:
    """Lint a persona's DECLARED skills, on the same terms as the ones its prose names.

    A declared skill that does not resolve is worse than a prose mention that does not: the
    prose is advice a reader can route around, while this is emitted into the agent, so the
    failure is silent at the moment it matters.

    Costs context on every dispatch, which is the part worth being strict about — `skills:`
    injects full content at startup, so a dead entry is paid forever for nothing.
    """
    return _declared_skill_issues(declared_skills(name))


def _declared_skill_issues(names: list[str]) -> list[tuple[str, str]]:
    """The check itself, over already-resolved names — so it can be tested against a
    controlled skill tree rather than a persona that has to exist on disk."""
    if not names:
        return []
    skills = _installed_skills()
    if skills is None:  # no plugin cache here → cannot verify; skip, as `_skill_ref_issues` does
        return []
    out: list[tuple[str, str]] = []
    for ref in names:
        leaf = ref.split(":", 1)[-1]
        if leaf not in skills:
            # ADR 0009 — name what was actually checked. The old remedy ("install the
            # plugin") was impossible for a skill charter generates INTO the plane, and sent
            # the reader hunting for a package that does not exist (#286).
            out.append(("error", f"declares skill `{ref}` — not found in ~/.claude/plugins, "
                                 f"~/.claude/skills or this plane's .claude/skills. It is "
                                 f"preloaded into the agent, so this fails silently at "
                                 f"dispatch. Install it, generate it, or drop the entry"))
        elif not skills[leaf]:
            out.append(("warn", f"declares skill `{ref}`, which is human-only "
                                f"(disable-model-invocation) — preloading its text is "
                                f"harmless but the agent can never invoke it"))
    return out


def lint(name: str, deep: bool = True) -> list[tuple[str, str]]:
    """Config-correctness checks for one persona → ``[(level, message)]`` where
    level is ``'error'`` (dangling ``uses:``, or a charter naming a human-only/unknown
    plugin skill for agent use) or ``'warn'`` (missing role/vault/delegate-when, or an
    unfinished ``draft:``). The agent-in-sync check lives in the CLI (it needs the
    renderer). A deterministic eval of the persona config — the routing/guard behaviours
    are covered by the test suite.

    ``deep=False`` drops the skill-reference check, the one part that walks the plugin
    cache. Everything else is frontmatter arithmetic (~0.1ms per persona), which is what
    lets the status line — rendered on *every turn* — show roster health at all. One
    implementation with a flag, rather than a second "cheap health" function that would
    drift from this one the first time a check was added to only one of them.
    """
    d = load(name)
    if not d:
        # WHY, when there is a why. "does not load" about a `persona.md` sitting right
        # there sends the reader looking for a missing file; the refusal names the path
        # charter actually resolved to, which is the whole defect (#336). A file that is
        # there and does not read as text raised here instead, and every other command
        # now sends the reader here to find out why (#1061).
        refused = definition_refusal(name) or read_refusal(name)
        # `contain.readable`, because *name* here is a DIRECTORY name and a directory name
        # is not a name charter minted: `personas/` is committed, and a filesystem forbids
        # only `/` and NUL. A U+2028 in one made this single lint row two rows, the second
        # of them indistinguishable from charter's own — the #453 mechanism on the surface
        # that exists to REPORT #453. Reproduced before it was bounded.
        #
        # It was `contain.one_line`, which stops that and nothing else: it escapes five
        # general categories, and U+3164 HANGUL FILLER is `Lo`, not whitespace, and survives
        # `strip`, so this read `persona '' does not load` — the one sentence whose entire
        # job is to tell somebody WHICH persona to go and fix, with the name left out
        # (#498). `readable` decides on the complement instead: printable ASCII is what may
        # reach the sentence and everything else prints as its escape, so the name is one
        # the reader can find on disk. Charter mints persona names out of
        # `[a-z0-9][a-z0-9._-]` (`valid_name`), so a name that resolves is ASCII already and
        # comes back unchanged; the escapes only ever appear for a directory that is broken.
        #
        # This bounds the MESSAGE and only the message. `cmd_persona_lint` builds the row
        # around it out of the same directory name and bounds its own prefix; `persona
        # list` and `persona stats` still do not, which is #472. A bound here is not a
        # bound on every report that prints this name.
        return [("error", f"persona.md: {refused}" if refused
                 else f"persona '{contain.readable(name)}' does not load")]
    meta = d["meta"]
    issues: list[tuple[str, str]] = []
    if deep:
        # Declared skills are checked on the same walk as the prose references — one plugin
        # cache read serves both, which is what `_installed_skills`' memo exists for.
        issues += declared_skill_issues(name)
    if not meta.get("role"):
        issues.append(("warn", "no role"))
    if not vault_of(name) and not declares_no_vault(name):
        issues.append(("warn", f"no vault named — add `vault:` or `vault: {NO_VAULT}` "
                               f"if this persona holds no credentials"))
    if not (meta.get("delegate-when") or "").strip():
        issues.append(("warn", "no delegate-when → weak auto-routing"))
    if is_draft(name):
        issues.append(("warn", "draft: true → charter unfinished; no sub-agent is "
                               "generated and it cannot be dispatched. Finish the "
                               "charter, drop the line, then `charter persona sync-agents`"))
    # A frontmatter key charter neither reads nor emits reaches nothing: it is not copied
    # into .claude/agents/<name>.md and no charter code consults it, so a typo (`modell:`,
    # `delegate_when:`) is silently inert.
    #
    # A WARNING, and it stays one. Charter has no claim about `modell:` — a harness's own
    # field is a legitimate thing to carry in a committed file, and this line firing as an
    # error would break planes that are correct. The two kinds of key charter CAN make a
    # claim about — one it reads spelled in another case, and one it reads written twice —
    # are errors, and they come from `structural_errors` below.
    #
    # Skipping the keys `key_issues` already named is not tidiness. "It does nothing
    # (typo?)" is the wrong sentence for `Borrows:`: the key does nothing and its ABSENCE
    # does a great deal, and a reader who acts on the milder of two sentences about one
    # line acts on the wrong one.
    #
    # `contain.readable` because a key is a string from a committed file printed into a row
    # whose whole job is to say which key to go and edit. `splitlines` already rules out a
    # second row — it splits on \r, \x85, U+2028 and U+2029 — but a key of U+3164 HANGUL
    # FILLER strips to nothing and printed as `frontmatter key '' …`, #498's finding on a
    # row that had not been given the escape.
    named = {k for k in meta if misspelled_key(k)}
    for key in sorted((set(meta) - KNOWN_KEYS) - named):
        issues.append(("warn", f"frontmatter key '{contain.readable(key)}' is neither read "
                               f"by charter nor emitted into the sub-agent — it does "
                               f"nothing (typo?)"))
    issues += structural_errors(name)
    issues += bin_issues(name)
    if deep:
        issues += _skill_ref_issues(d["charter"])
    # A declared MCP server whose `secrets` cannot be resolved. Reported rather than
    # refused: the persona charter is committed and SHARED, while a vault is machine-local
    # by design, so a teammate cloning this repo legitimately has neither the vault nor the
    # keys. The wrapper charter emits is correct either way — only the run would fail — and
    # refusing to render would break `sync-agents` on a fresh clone (ADR 0013: name the
    # divergence, do not resolve it).
    servers, refused_names = _mcp_declared(name)
    # A name `mcp_name_ok` refused. An ERROR, and named on its own line rather than folded
    # into the count above: the server is not declared at all — the persona lost a
    # capability — and the value that caused it is a string in a committed file that
    # somebody has to edit. Rendered through `mcpseen.label`, because a refused name is
    # precisely the one that may hold a newline and forge a second issue line (#453) — and
    # also the one that may render as NOTHING. `contain.one_line` answers the first and not
    # the second: it escapes the categories with no glyph (Cc, Cf, Cs, Zl, Zp), which is a
    # list of spellings that U+3164 HANGUL FILLER (Lo) and U+2800 BRAILLE PATTERN BLANK
    # (So) are not on, so `server name '' is refused` named nothing at all. `label` decides
    # on the complement instead — printable ASCII is what may reach the line and everything
    # else prints as its escape — so the name this sentence tells somebody to go edit is a
    # name they can find.
    for bad in refused_names:
        issues.append(("error",
                       f"mcp: server name '{mcpseen.label(bad)}' is refused and the "
                       f"server is not declared — a name is emitted into the generated "
                       f"agent's YAML and into `mcp__<server>__*`, so it may hold only "
                       f"letters, digits, '_', '.' and '-' (64 max). Rename it in "
                       f"`{MCP_FILE}`"))
    if servers:
        # `vault_for_mcp`, so this row and the render agree about what "has a vault" means.
        # It was `not vault or vault == "none"` — a second spelling of the sentinel, written
        # out beside a `NO_VAULT` constant that exists to stop exactly that, and one that
        # reads a whitespace-only `vault:  ` as a vault name.
        vault = vault_for_mcp(name)
        # `mcpseen.declares_credential`, not `entry.get("secrets")`. `secrets` and
        # `secret_files` are two mechanisms for one thing and every other reader treats
        # them as one — `needs_consent`, `mcp_render_entry`, `secret exec --env/--file`.
        # This line was the odd one out, so a server declaring only `secret_files` against
        # a persona naming no vault rendered without its credential and was reported by
        # NOTHING: not here, because the key was not read, and not by `mcp_withheld`,
        # because with no vault there is no consent to withhold. `secret_files` is what
        # Google ADC needs (#190) — the exact declaration #489's reproduction carries.
        # `e`, not `e or {}`. A committed `{"mcpServers": {"x": null}}` puts `None` here,
        # and `declares_credential` answers that with False by construction — its
        # `isinstance(entry, dict)` is the guard, and it is pinned. A second guard in front
        # of a pinned one is a line no test can go red without, which the sweep reported and
        # which this file's own rule says to delete rather than to leave looking careful.
        wants = sorted(s for s, e in servers.items() if mcpseen.declares_credential(e))
        if wants and not vault:
            issues.append(("error",
                           f"mcp: server(s) {', '.join(wants)} declare `secrets` or "
                           f"`secret_files` but this persona names no vault — add `vault:` "
                           f"or drop the declaration"))
    # The credential this persona declares and is NOT running with (#489). Standing state,
    # said by the command you run BECAUSE a persona is misbehaving — which is the whole
    # finding: `mcp_withheld` had exactly one caller, `sync-agents`, on the run that wrote
    # the file. That warning is correct and it is said once. After it scrolls, a persona
    # running without the credential it declares is byte-identical in
    # `.claude/agents/<name>.md` to one that never declared a vault at all, and the failure
    # it produces arrives three layers away as an MCP server failing to authenticate.
    #
    # A WARNING, not an error, and that is a decision rather than a default. Withholding is
    # the #330 gate working: the operator may have read the command and declined it, and
    # charter must not overrule that with an exit code — `charter persona lint` returning 1
    # forever would make the finding something planes turn off. What charter owes is that
    # the state stays VISIBLE, which is what this row is. `doctor` reports it without a
    # second sentence of its own: `check_personas` already counts these issues and names
    # the persona, and one fact with two wordings is the drift this file keeps recording.
    #
    # Nothing is re-derived here. `mcp_withheld` computes the list `sync-agents` prints, so
    # the two surfaces cannot disagree about which servers are withheld — the failure mode
    # of a report that recomputes its own answer.
    for server, line in mcp_withheld(name):
        if line:
            issues.append((
                "warn",
                f"mcp: '{mcpseen.label(server)}' declares a credential this machine has "
                f"not approved, so the generated sub-agent runs it WITHOUT the vault and "
                f"it will fail to authenticate. Read the command and approve it with "
                f"`charter persona sync-agents --approve-mcp`, or drop `secrets`/"
                f"`secret_files` from `{MCP_FILE}` if it should hold no credential"))
        else:
            # `describe` cannot render this entry, so it can never be approved (#427) and
            # `--approve-mcp` refuses it by name. Telling the operator to run that command
            # would be a nudge that cannot work, which is the one thing a nudge may not be
            # (#371) — so this is a different sentence AND a different level: the entry has
            # to change before any answer to the consent question exists.
            issues.append((
                "error",
                f"mcp: '{mcpseen.label(server)}' declares a credential and "
                f"{mcpseen.UNRENDERABLE} — it can never be approved, so the vault is "
                f"withheld permanently. Fix the entry in `{MCP_FILE}`"))

    return issues


def _inherits_cycle(name: str) -> str | None:
    """The cycle path (e.g. ``a → b → a``) if ``extends`` loops, else None."""
    seen, cur = [], name
    while cur:
        if cur in seen:
            return " → ".join(seen[seen.index(cur):] + [cur])
        seen.append(cur)
        d = load(cur)
        if not d:
            return None  # dangling parent, not a cycle
        cur = (d["meta"].get("extends") or "").strip() or None
    return None


#: Reserved ``vault:`` value meaning "this persona deliberately holds no credentials".
#: A vault may therefore not be named ``none``.
NO_VAULT = "none"


def declares_no_vault(name: str) -> bool:
    """True when the persona's ``vault:`` is the reserved :data:`NO_VAULT` value.

    Charter's model assumes a persona has a scoped vault, and `lint` warned whenever one
    had none. But plenty legitimately hold no credentials — a status-line or release
    persona touches nothing secret, or leans on a tool's own auth (`gh`) — so the warning
    fired forever on personas that were entirely correct. A lint with a permanent false
    positive is a lint people learn to scroll past, which costs more than the warning
    ever bought.

    Declared rather than inferred, the same rule `[plane] shape` follows: "no secrets" is
    an intent, not something readable off disk. That keeps the warning meaningful for the
    case it was written for — a persona whose author simply never thought about it — while
    letting one say so and be believed.
    """
    r = resolve(name)
    return bool(r) and (r["meta"].get("vault") or "").strip() == NO_VAULT


def vault_of(name: str) -> str | None:
    """The vault a persona uses: its ``vault:`` field (inherited if unset), else a
    vault tagged with it.

    ``None`` for a persona that declares :data:`NO_VAULT` — there is no vault to open, and
    returning the sentinel would send callers looking for one literally named ``none``.
    Use :func:`declares_no_vault` to tell "none, deliberately" from "none, unexamined";
    every caller that merely opens a vault wants this function and cannot tell the
    difference, which is the point.
    """
    r = resolve(name)
    if r and r["meta"].get("vault"):
        v = r["meta"]["vault"].strip()
        return None if v == NO_VAULT else (v or None)
    try:
        from .secrets import registry
        tagged = registry.vaults_for_persona(name)
        return tagged[0] if tagged else None
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# memory: 2×2 (own/shared × persistent/ephemeral) + activity log              #
# --------------------------------------------------------------------------- #
def scaffold_memory(name: str, shared: bool = False) -> None:
    """Create the committed memory/ and refs/ dirs with keep-files so git tracks
    them and the persona always has an index to read."""
    # Two fixed names under a directory a commit controls, written HERE rather than
    # through `memstore.ensure_index` — so gating the store alone would have left the
    # scaffolder holding the same hole one function over (#349). Both checked before the
    # `mkdir`, which happily accepts a committed link to a directory outside the plane.
    mem = memory_dir(name, shared)
    idx = contain.writable(index_of(mem))
    mem.mkdir(parents=True, exist_ok=True)
    if not idx.exists():
        who = "shared (all personas)" if shared else name
        idx.write_text(
            f"# Memory Index — {who}\n\n"
            "One line per memory; each links a file holding a single durable fact.\n"
            "Written by the persona as it learns; committed and shared.\n"
        )
    refs = refs_dir(name, shared)
    readme = contain.writable(refs / "README.md")
    refs.mkdir(parents=True, exist_ok=True)
    if not readme.exists():
        who = "shared (all personas)" if shared else name
        readme.write_text(
            f"# References — {who}\n\n"
            "Curated docs, links, and snippets this role collects. Committed and "
            "shared. Never store secrets here — those live only in the vault.\n"
        )


def ensure_shared() -> None:
    scaffold_memory(config.SHARED_PERSONA, shared=True)


def remember(name: str, text: str, title: str | None = None, *,
             shared: bool = False, ephemeral: bool = False,
             session: str | None = None) -> Path:
    """Write one memory. The caller (the persona) picks the quadrant:

    - ``ephemeral=False`` → **persistent**, committed under ``personas/…/memory``
      (appears in ``git status`` for a human to commit & push).
    - ``ephemeral=True``  → session-scoped scratch under gitignored persona-state,
      deleted after the session.
    - ``shared`` → the cross-persona ``_shared`` namespace instead of this persona.

    Returns the written file path. Secrets must never be passed here.
    """
    from . import memstore
    text = (text or "").strip()
    if not text:
        raise ValueError("empty memory")
    title = (title or text.splitlines()[0]).strip()[:72]
    d = ephemeral_dir(name, shared, session) if ephemeral else memory_dir(name, shared)
    kind = "ephemeral" if ephemeral else "persistent"
    # Persona memory keeps slug-only filenames (addressed by slug in forget/recall); the
    # ephemeral quadrant needs no committed index.
    p = memstore.write(d, text, title, kind=kind, index=not ephemeral)
    try:
        from . import trace
        trace.record("memory", persona=name, scope="shared" if shared else "own",
                     kind=kind, title=title)
    except Exception:
        pass
    return p


def memories(name: str, shared: bool = False, ephemeral: bool = False,
             session: str | None = None) -> list[Path]:
    """One quadrant's memory files. A directory charter cannot list raises
    `workspace.CannotCheck` (`memstore.files`), rather than counting as none (#1084)."""
    from . import memstore
    return memstore.files(_quadrant(name, shared, ephemeral, session))


def read_memories(name: str, shared: bool = False, ephemeral: bool = False,
                  session: str | None = None) -> tuple[list[Path], list[tuple[Path, int | None]]]:
    """:func:`memories`, and beside them what could not be read — `memstore.read_files`."""
    from . import memstore
    return memstore.read_files(_quadrant(name, shared, ephemeral, session))


def _quadrant(name: str, shared: bool, ephemeral: bool, session: str | None) -> Path:
    return ephemeral_dir(name, shared, session) if ephemeral else memory_dir(name, shared)


def _mem_dirs(name: str, include_shared: bool) -> list[Path]:
    dirs = [memory_dir(name)]
    if include_shared:
        dirs.append(memory_dir(name, shared=True))
    return dirs


def search_memories(name: str, query: str, limit: int = 8, include_shared: bool = True,
                    unread: list | None = None) -> list[tuple[Path, str, int]]:
    """Keyword-rank a persona's persistent memories (own + shared) against *query*.
    Returns [(path, title, score)] best-first — pull just the relevant few.

    A directory it could not list goes to *unread* (`memstore.search`, #1084)."""
    from . import memstore
    return memstore.search(_mem_dirs(name, include_shared), query, limit, unread=unread)


def find_duplicates(name: str, threshold: float = 0.5,
                    include_shared: bool = True) -> list[tuple[float, Path, str, Path, str]]:
    """Near-duplicate memory pairs (Jaccard word overlap ≥ *threshold*) for a human to
    `forget` one — never auto-deletes."""
    from . import memstore
    return memstore.duplicates(_mem_dirs(name, include_shared), threshold)


def forget(name: str, slug: str, *, shared: bool = False, ephemeral: bool = False,
           session: str | None = None):
    """Delete one memory file (by slug/filename) and drop its index line.

    Returns the removed path (falsy when nothing matched) so the caller can stage the
    deletion — see `memstore.forget`."""
    from . import memstore
    d = ephemeral_dir(name, shared, session) if ephemeral else memory_dir(name, shared)
    return memstore.forget(d, slug)


# --------------------------------------------------------------------------- #
# roster health — a persona's committed memory IS its activity trace, so mine it #
# into a usage + (in-corpus) quality signal for the steward's observe loop. Read- #
# only: count/recency = usage; verification-marker & near-dup ratios = a quality  #
# *proxy* (a signal, not a verdict — volume ≠ value). Feeds `charter persona stats`.  #
# --------------------------------------------------------------------------- #
# The verification-discipline vocabulary personas actually use (freq-ranked in the
# committed corpus): a memory asserting it was checked, not merely guessed.
_VERIFY_RE = re.compile(r"\b(?:confirmed|validated|verified|proven|reproduced)\b", re.I)


def _memory_date(text: str, filename: str):
    """Date a memory was recorded — delegates to the memstore file-format owner."""
    from . import memstore
    return memstore.memory_date(text, filename)


# A persona may declare an `activity:` profile when memory volume is NOT a fair usage
# signal for it — so `stats` reports that profile instead of crying "dormant":
#   orchestrator — routes/delegates, writes no domain memory (e.g. steward)
#   standby      — invoked on-demand / rarely but valuable (e.g. performance-investigator)
#   advisory     — output is design/requirements/review, not durable facts (e.g. nx-code-reviewer)
# Absent → a normal investigative persona whose memory volume IS a real usage signal.
_MEMORY_BLIND = ("orchestrator", "standby", "advisory")


def stats(name: str, recent_days: int = 14, shared: bool = False, today=None) -> dict:
    """Read-only roster-health for one persona (or the ``_shared`` namespace), mined from
    its committed memory — the persona's own activity trace. Returns:

      count       total persistent memories (usage)
      recent      memories recorded within ``recent_days`` (recency/cadence)
      last        ISO date of the most recent memory, or None
      verify_pct  % of memories carrying a verification marker (quality proxy), or None
      dup_pct     % of memories in a near-duplicate pair (noise proxy), or None
      activity    the declared `activity:` profile (orchestrator/standby/advisory), or None
      status      declared profile if set (memory-blind role); else 'active' (recent memory)
                  | 'idle' (has memories, none recent) | 'dormant' (none) — a *real* prune signal
    """
    import datetime
    from . import memstore
    day = today or datetime.date.today()
    ents = memstore.entries(memory_dir(name, shared))
    total = len(ents)
    recent = verified = 0
    dates = []
    for p, _title, text in ents:
        if _VERIFY_RE.search(text):
            verified += 1
        d = _memory_date(text, p.name)
        if d:
            dates.append(d)
            if (day - d).days <= recent_days:
                recent += 1
    dup_files = set()
    for _jac, pa, _ta, pb, _tb in memstore.duplicates([memory_dir(name, shared)]):
        dup_files.add(pa)
        dup_files.add(pb)
    meta = (load(name) or {}).get("meta", {}) if not shared else {}
    activity = (meta.get("activity") or "").strip().lower() or None
    if activity in _MEMORY_BLIND:
        status = activity  # memory-blind by declared role nature — never "dormant"
    else:
        status = "dormant" if total == 0 else ("active" if recent else "idle")
    return {
        "persona": name, "count": total, "recent": recent,
        "last": max(dates).isoformat() if dates else None,
        "verify_pct": round(100 * verified / total) if total else None,
        "dup_pct": round(100 * len(dup_files) / total) if total else None,
        "activity": activity, "status": status,
    }


# (Persona activity now lives in the single session **trace** — see charter/trace.py.
# `charter persona log` writes `note` events there; there is no separate per-persona log.)


def gc_ephemeral(current: str | None = None, max_age_hours: float = 6.0) -> int:
    """Prune ephemeral scratch from sessions that have ended. A session dir is
    removed when it isn't the current session *and* hasn't been touched within
    ``max_age_hours`` (so concurrent live sessions are never clobbered). Called
    from the SessionStart hook. Returns the number of session dirs removed."""
    root = config.PERSONA_STATE_DIR / "ephemeral"
    if not root.exists():
        return 0
    # `current()`, not `_session_id()`. The latter falls back to the shared NO_SESSION
    # bucket, so when the GC itself ran without a session id — which is most of the time,
    # since it runs from a hook — that bucket compared equal to "the live session" and was
    # skipped every single time. Ephemeral scratch from every id-less session accumulated
    # there forever, which is the opposite of ephemeral. There is nothing to preserve when
    # there is no current session, so nothing is exempt.
    from . import session as _session
    cur = _session.current(current)
    now = time.time()
    removed = 0
    for sd in root.iterdir():
        if not sd.is_dir() or (cur is not None and sd.name == cur):
            continue
        try:
            newest = max([sd.stat().st_mtime] + [p.stat().st_mtime for p in sd.rglob("*")])
        except (OSError, ValueError):
            newest = 0
        if now - newest > max_age_hours * 3600:
            shutil.rmtree(sd, ignore_errors=True)
            removed += 1
    return removed


def migrate(name: str) -> str:
    """Convert the legacy flat ``personas/<name>.md`` to the directory layout
    ``personas/<name>/persona.md`` and scaffold memory/ + refs/. Returns
    'migrated' | 'already' | 'missing'."""
    target = dir_of(name) / "persona.md"
    if target.exists():
        return "already"
    flat = config.PERSONAS_DIR / f"{name}.md"
    if not flat.exists():
        return "missing"
    target.parent.mkdir(parents=True, exist_ok=True)
    flat.rename(target)  # content-identical move → git records a rename
    scaffold_memory(name)
    return "migrated"
