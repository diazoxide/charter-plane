"""Every action CI runs is named by something nobody else can move (#443), and every
trigger that can publish is cross-examined before it does (#558).

`release.yml`'s `publish` job holds `id-token: write`, and PyPI's Trusted Publishing
verifies the token minted there as charter's genuine publisher — the claim is real, so
whatever code runs in that job can publish charter. A `uses:` on a floating ref is that
code, chosen by whoever can move the ref. `pypa/gh-action-pypi-publish@release/v1` is a
BRANCH head, so it is a force-push away from being different code; `@v4` is a tag its owner
can retarget. That is the whole of CVE-2025-30066.

**The property, and it is not "the string does not say v4".** A reference is acceptable
when naming it a second time cannot get you different bytes: a full commit SHA (a content
address), an image digest, or a path to a file **tracked in this repository**, which moves
only with a commit here. Everything else is a promise by a third party, whatever it is
spelled — and "in the working tree" is not the same claim as "tracked": `./node_modules/x`
is a path in this tree that an `npm install` rewrites. `uses:` is not the only key that
names somebody else's code, so `container:`/`services:`/`runs.image` are held to the same
rule: `image: node:18` runs third-party bytes inside the job exactly as a step does.

**And a container key has two shapes, which is the spelling problem again one level in.**
`container:` takes a mapping with an `image:` in it *or* a bare scalar — GitHub: "when you
only specify a container image, you can omit the `image` keyword" — and `services:` gives
every child the same pair. A key set of `("uses", "image")` knew the long form only, so
`container: evil/img:latest` on the `publish` job read as no reference at all and left this
whole file green. Both shapes are read now, and `Ref.kind` says what a reference *is*
(`ACTION` or `IMAGE`) so the rule tests select on that rather than on the key that spelled
it. The corpus below holds every shape, in both directions.

**Why this reads YAML instead of grepping for `uses:`.** The first version of this file
matched the key with `^\\s*(?:-\\s+)?uses\\s*:` and counted the literal bytes `uses:` as its
fail-closed cross-check. Both are one spelling of the key. YAML has many, and GitHub loads
them all: `- "uses": evil/action@main` contains neither the bare key nor the byte sequence
`uses:`, parses to a genuine step, and was invisible to every test below. So was
`- 'uses':`, so was the explicit key `- ? uses` / `: …`, and so was `"\\x75ses"`. Matching
one spelling of a thing is the failure this repository keeps re-learning; the answer is to
read the structure, not the bytes.

So `scan_text` is a small YAML reader for the **subset this repository writes** — block
mappings and sequences, plain and quoted scalars with real escape handling, block scalars
skipped as the opaque text they are. Anything outside that subset is not guessed at and not
ignored: it raises `Unparsed`, which fails the suite by name. A flow mapping, an anchor, an
alias, a merge key, a tag, an explicit key, a document marker, a `uses:` whose value is on
another line — every one of those can carry a step past a line-oriented reader, so every
one of them stops this test until a person either rewrites the file in the subset or
teaches the reader that construct on purpose. `TheKeyHasManySpellings` is the corpus that
holds it to that, and it asserts *which* outcome each spelling gets, so no case can pass
because some unrelated check happened to trip.

**Nothing is trusted for being on disk.** The set of files to read is everything under
`.github/` plus every `action.y*ml` in `git ls-files`, and every local `uses: ./x` must
resolve to a file in that index — a local composite action runs in the calling job with the
calling job's token, so its own `uses:` lines are checked exactly like the caller's, and a
path this repository does not track is not "a path that moves only with a commit here". The
first version walked the tree with a hardcoded list of directories to skip (`node_modules`,
`dist`, `.venv`), which is the same mistake in a second place: `uses: ./node_modules/probe`
was accepted as immutable while the skip list guaranteed its `action.yml` was never read.
There is deliberately no second walk from the refs: GitHub resolves a local `uses:` to a
directory's `action.y*ml` or to a file under `.github/workflows/`, both of which the seed
list already holds, and a test pins that invariant rather than leaving it as a comment.

**What this cannot check**, stated because a guard that overclaims is the defect twice
over. That a pinned SHA is a real commit of the repository beside it, or that its trailing
`# v1.2.3` is that commit's tag — both need the network, and no test in this suite makes a
network call; a wrong-but-well-formed SHA fails in CI on the next run, loudly, which is the
failure mode you want from an unresolvable ref. That a ref which *is* 40 hex characters is
an object name rather than a branch somebody named after one — GitHub resolves it as a
commit, and the case is theoretical, but it is not excluded here. That a tracked local
action stays benign — it is charter's own code, reviewed the way the rest of it is. And
nothing at all about a `run:` step that pipes a script off the internet: pinning is not a
defence against one, and there is none in these files today.

**What this checks is the refs written in this repository, one hop deep into local
actions and no hops at all into remote ones** (#473). `uses: owner/action@<sha>` pins that
action's tree; it does not pin what that tree then names. A Docker action builds from a
`Dockerfile` whose `FROM` is a tag its publisher rewrites, and a composite action has its
own `uses:` lines — neither is in this repository, neither can be read without the network,
and both run in the job holding `id-token: write`. So the property this file enforces is
"every reference charter *writes* is a content address", which is narrower than "every byte
that runs in the publishing job is pinned".

**The gap between those two sentences is now written down, and going stale in it is now
loud.** `.github/publish-closure.json` records, for every remote action that runs in a job
holding `id-token: write`, what that action's own tree names — read with the network, by a
person, at the SHA pinned here. `TheHopIntoAPinnedActionIsRecordedRatherThanChecked`
asserts that the record and the workflow name the same SHAs, so bumping a pin in `publish`
reddens the suite until somebody re-reads the tree it now points at. It is a **prompt, not
a proof**: nothing here can tell a re-reading from a retyped SHA, and that limit is stated
in the record, in that class, and in the news entry rather than left to be discovered. What
it removes is the failure that had already happened — the reading published on #473 on
2026-08-28 was wrong twenty-seven hours later, when `actions/download-artifact` moved from
v4.3.0 to v8.0.1 and `runs.using` moved from node20 to node24 with it, and nothing asked
anybody to look. Today one reference in that closure is movable and no test here can pin
it: PyPA's `Dockerfile` says `FROM python:3.13-slim`. Closing *that* means vendoring the
action or uploading from a `run:` step — a change to how charter releases itself, which is
the operator's decision and stays in #473.

**A second question, and a second reader for it (#558).** Pinning asks *what code runs*.
The other thing this file has to hold is *which trigger reaches the job that publishes,
and under what checks* — and the answer was: not the same checks on both. `release.yml`'s
version check was gated on `if: startsWith(github.ref, 'refs/tags/v')`, so a
`workflow_dispatch` run — which has a branch in `github.ref` — **skipped** it, and a
skipped step is a green step. The retry path published with strictly weaker checks than
the path it retries, and the check it dropped was the one guarding the irreversible act.
`load` reads a workflow as a tree for that question, and it exists because the shape of a
job graph is invisible to a reference scanner and a grep for `if:` is the spelling mistake
this whole file refuses to make. Two halves are asserted, since either alone can be
satisfied by a lie: the **shape** — no `if:` on the guard job, none on any step in it, and
`publish` transitively behind it — and the **behaviour**, by executing the check's own
`run:` script against a synthetic tree on both triggers and asserting what it refuses and
why. Not that it passed; that it ran.

**The next place to look**, since that is the question this file exists to keep asking. The
transitive hop above is recorded now, not closed: what a re-read of `python:3.13-slim`
costs is a decision about how charter releases itself, and it is open. Then the two
mismatches a reader like this always has with the real one: what counts as a line break —
see
`ALineBreakIsTheOtherHalfOfTheSpellingProblem`, which shows the mismatch runs the safe way
round — and a ref that is well formed here and means something else on the runner, such as a
branch somebody named after a 40-character hex string. And last, this reader judges a key by
its **name**, not by its position in GitHub's workflow schema, so an action input that
happens to be called `container:` reads here as a job container. That is a false alarm
somebody resolves in one look, which is the direction this file always takes when it has to
guess — all of it stated rather than quietly assumed.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import NamedTuple

REPO = Path(__file__).resolve().parents[1]
GITHUB = REPO / ".github"

#: A full git object name: the only ref that is a content address rather than a promise.
#: Lowercase, because that is what every tool that prints one emits — an uppercase variant
#: would be a second spelling of the same pin, and two spellings is how audits drift.
_SHA = re.compile(r"^[0-9a-f]{40}$")

#: An OCI digest, for a `docker://` step or a `container:`/`services:` image.
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")

#: The keys that name code somebody else wrote. `uses` is a step or a reusable workflow;
#: `image` is `jobs.<id>.container.image`, `services.<id>.image`, or a Docker action's
#: `runs.image` — all of which run third-party bytes inside the job just as a step does.
_CODE_KEYS = ("uses", "image")

#: The key that introduces a job container. It takes **two shapes**, and that is the whole
#: point of naming it separately: a mapping with an `image:` in it, which `_CODE_KEYS`
#: already reads, or a bare scalar — `container: node:18` — which GitHub documents as the
#: shorthand ("when you only specify a container image, you can omit the `image` keyword").
#: A key set that knew only the long form knew one spelling of the key again.
_CONTAINER = "container"

#: The key whose every child is a container, in the same two shapes. `services.<id>.image`
#: is the documented long form; `services:\n  redis: redis:7` is the string shorthand the
#: workflow schema and the runner both accept, resolved exactly like `container:`.
_SERVICES = "services"

#: What a reference *is*, as opposed to what key spelled it. `immutable` judges an action
#: ref; `immutable_image` judges an image. Tests select on this, not on the key name, so a
#: new spelling of either kind is judged the moment the reader emits it.
ACTION, IMAGE = "action", "image"

#: A block-scalar header: `|`, `>`, with any chomping/indent indicator and a comment.
_BLOCK_HEADER = re.compile(r"^[|>][-+0-9]*\s*(?:#.*)?$")

#: A local reference: a path, resolved by GitHub against the repository root.
_LOCAL = re.compile(r"^\.{1,2}/")


class Unparsed(Exception):
    """A construct the reader does not model.

    Never swallowed and never guessed at. It carries a line number and a name for the
    construct, and it fails the suite — because a YAML shape this file does not understand
    is exactly where the next step hides.
    """

    def __init__(self, line: int, what: str) -> None:
        super().__init__(f"line {line}: {what}")
        self.line = line
        self.what = what


# --------------------------------------------------------------------------- scalars

#: YAML 1.2's double-quoted escapes. Present so that `"\x75ses"` — which is the key `uses`
#: to every real parser — is the key `uses` here too.
_ESCAPES = {
    "0": "\0", "a": "\a", "b": "\b", "t": "\t", "\t": "\t", "n": "\n", "v": "\v",
    "f": "\f", "r": "\r", "e": "\x1b", " ": " ", '"': '"', "/": "/", "\\": "\\",
    "N": "\x85", "_": "\xa0", "L": "\u2028", "P": "\u2029",
}
_HEX = {"x": 2, "u": 4, "U": 8}

#: Characters that begin a YAML construct this reader does not model. Each one is a way to
#: introduce a mapping key out of line-oriented view, so each one stops the suite.
_INDICATORS = {
    "{": "a flow mapping",
    "[": "a flow collection in key position",
    "&": "an anchor",
    "*": "an alias",
    "!": "a tag",
    "?": "an explicit key",
    "%": "a directive",
    "@": "a reserved indicator",
    "`": "a reserved indicator",
}


def _double_quoted(s: str, i: int, line: int) -> tuple[str, int]:
    out: list[str] = []
    i += 1
    while i < len(s):
        c = s[i]
        if c == '"':
            return "".join(out), i + 1
        if c != "\\":
            out.append(c)
            i += 1
            continue
        i += 1
        if i >= len(s):
            raise Unparsed(line, "a double-quoted scalar folded onto the next line")
        e = s[i]
        if e in _HEX:
            width = _HEX[e]
            digits = s[i + 1:i + 1 + width]
            if len(digits) != width or any(d not in "0123456789abcdefABCDEF" for d in digits):
                raise Unparsed(line, f"a malformed \\{e} escape")
            out.append(chr(int(digits, 16)))
            i += 1 + width
        elif e in _ESCAPES:
            out.append(_ESCAPES[e])
            i += 1
        else:
            raise Unparsed(line, f"an escape this reader does not know: \\{e}")
    raise Unparsed(line, "an unterminated double-quoted scalar")


def _single_quoted(s: str, i: int, line: int) -> tuple[str, int]:
    out: list[str] = []
    i += 1
    while i < len(s):
        if s[i] == "'":
            if s[i + 1:i + 2] == "'":
                out.append("'")
                i += 2
                continue
            return "".join(out), i + 1
        out.append(s[i])
        i += 1
    raise Unparsed(line, "an unterminated single-quoted scalar")


def _plain(s: str, i: int) -> tuple[str, int]:
    """A plain scalar, stopping where YAML stops it: at `: `, at ` #`, or at end of line.

    A bare `:` that is not followed by a space does not end it — `https://example` is one
    scalar — and a `#` that is not preceded by a space does not start a comment, which is
    why `SECURITY.md#reporting` survives intact.
    """
    start = i
    while i < len(s):
        if s[i] == ":" and (i + 1 >= len(s) or s[i + 1] in " \t"):
            break
        if s[i] == "#" and i > start and s[i - 1] in " \t":
            break
        i += 1
    return s[start:i].rstrip(), i


def _scalar(s: str, i: int, line: int) -> tuple[str, int]:
    if s[i] == '"':
        return _double_quoted(s, i, line)
    if s[i] == "'":
        return _single_quoted(s, i, line)
    return _plain(s, i)


def _trailing(s: str, i: int, line: int) -> None:
    """Assert nothing but blanks and a comment follow — the line held one value, not two."""
    rest = s[i:].strip()
    if rest and not rest.startswith("#"):
        raise Unparsed(line, "two values on one line, or a scalar this reader misread")


# --------------------------------------------------------------------------- the reader

class Ref(NamedTuple):
    line: int
    key: str
    ref: str
    kind: str   # ACTION or IMAGE — what it names, not which key spelled it


def scan_text(text: str) -> list[Ref]:
    """Every reference to somebody else's code in a YAML document written in the subset.

    An action ref (`uses:`) or an image, in each of the shapes GitHub accepts an image in:
    `image:`, a scalar `container:`, and a scalar under `services:`.

    Raises `Unparsed` on the first construct outside the subset. There is no "skip what I
    do not understand" path, by design: that path is the bypass.
    """
    found: list[Ref] = []
    block_indent: int | None = None
    #: The column of a `container:`/`services:`/`services.<id>:` key whose value is a
    #: nested node, and the column of `services:`'s children. Both exist so a *scalar*
    #: written under such a key — the shorthand, wrapped onto the following line — is seen
    #: rather than dropped as an anonymous value.
    image_block: int | None = None
    services_col: int | None = None
    service_id_col: int | None = None

    for line, raw in enumerate(text.splitlines(), 1):
        if block_indent is not None:
            if not raw.strip() or len(raw) - len(raw.lstrip(" ")) > block_indent:
                continue                      # opaque block-scalar content
            block_indent = None

        if "\t" in raw:
            raise Unparsed(line, "a tab character")
        if raw.strip() in ("---", "..."):
            raise Unparsed(line, "a document marker — this reader loads one document")

        indent = i = len(raw) - len(raw.lstrip(" "))
        if i >= len(raw) or raw[i] == "#":
            continue                          # blank or whole-line comment

        # A sequence item's scalar is a value, not the shorthand: `ports:\n  - 6379:6379`
        # lives inside a service block and names no image.
        had_dash = raw[i] == "-" and (i + 1 >= len(raw) or raw[i + 1] == " ")

        # Close every container scope this line has stepped back out of, before anything
        # in it is judged. Scope is indentation, which is what it is in the real parser.
        if image_block is not None and indent <= image_block:
            image_block = None
        if services_col is not None and indent <= services_col:
            services_col = service_id_col = None

        while raw[i] == "-" and (i + 1 >= len(raw) or raw[i + 1] == " "):
            i += 1
            while i < len(raw) and raw[i] == " ":
                i += 1
            if i >= len(raw) or raw[i] == "#":
                break
        if i >= len(raw) or raw[i] == "#":
            continue                          # a lone `-`: the node is on the next line

        key_col = i
        if raw[i] in _INDICATORS:
            raise Unparsed(line, _INDICATORS[raw[i]])
        if raw[i] in "|>":
            raise Unparsed(line, "a block scalar in key position")

        name, i = _scalar(raw, i, line)
        j = i
        while j < len(raw) and raw[j] == " ":
            j += 1
        if j >= len(raw) or raw[j] != ":" or (j + 1 < len(raw) and raw[j + 1] not in " \t"):
            if image_block is not None and indent > image_block and not had_dash:
                # A bare scalar inside a `container:`/`services:` node *is* the image —
                # the shorthand, wrapped onto the next line. Dropping it as an anonymous
                # value is how `container:\n  evil/img:latest` would walk past.
                raise Unparsed(line, "a container image on a line of its own")
            _trailing(raw, i, line)           # a sequence item's own scalar value
            continue

        if name == "<<":
            raise Unparsed(line, "a merge key")

        # Which of the two container shapes is this key in? `container:` and every direct
        # child of `services:` take an image inline *or* a mapping holding `image:`, and
        # both shapes have to be judged — knowing only the mapping was the last bypass.
        is_service_id = (services_col is not None and key_col > services_col
                         and (service_id_col is None or key_col == service_id_col))
        if is_service_id:
            service_id_col = key_col
        names_image = name == _CONTAINER or is_service_id

        value = raw[j + 1:]
        k = len(value) - len(value.lstrip(" "))
        tail = value[k:]

        if not tail or tail.startswith("#"):
            if name in _CODE_KEYS:
                raise Unparsed(line, f"a `{name}:` whose value is not on its own line")
            if names_image or name == _SERVICES:
                image_block = key_col         # a nested node: watch it for a bare scalar
            if name == _SERVICES:
                services_col, service_id_col = key_col, None
            continue                          # a nested block follows
        if _BLOCK_HEADER.match(tail):
            if name in _CODE_KEYS or names_image or name == _SERVICES:
                raise Unparsed(line, f"a `{name}:` written as a block scalar")
            block_indent = key_col
            continue
        if tail[0] == "[":
            if name in _CODE_KEYS or names_image or name == _SERVICES:
                # A flow sequence is not a shape any of these keys takes, so it is the
                # third way to write a value this reader would otherwise walk past.
                raise Unparsed(line, f"a `{name}:` whose value is a flow sequence")
            close = tail.find("]")
            if close < 0:
                raise Unparsed(line, "a flow collection spanning lines")
            if "{" in tail[:close] or ":" in tail[:close]:
                raise Unparsed(line, "a mapping inside a flow sequence")
            _trailing(tail, close + 1, line)
            continue                          # a flow sequence of scalars: no keys in it
        if tail[0] in _INDICATORS:
            raise Unparsed(line, _INDICATORS[tail[0]])

        if name == _SERVICES:
            raise Unparsed(line, "a `services:` whose value is not a mapping")

        ref, end = _scalar(tail, 0, line)
        _trailing(tail, end, line)
        if ref and name in _CODE_KEYS:
            found.append(Ref(line, name, ref, IMAGE if name == "image" else ACTION))
        elif ref and names_image:
            found.append(Ref(line, name, ref, IMAGE))

    return found


# ------------------------------------------------------------------------ the structure

class _Loader:
    """The same subset, read as a tree rather than as a stream of references (#558).

    `scan_text` answers one question — *which third-party code can run* — and answers it
    without ever knowing which job a step is in. The second question this file has to
    answer is about shape, not content: **which trigger reaches `publish`, and under what
    checks**. A version check gated on `if: startsWith(github.ref, 'refs/tags/v')` is
    *skipped* on a `workflow_dispatch` run, and a skipped step is a green step — so the
    retry path published with the one check guarding an irreversible upload never having
    run. Nothing about that is visible to a reference scanner, and grepping for `if:` is
    the spelling mistake this file exists to refuse to make.

    So: block mappings, block sequences, plain and quoted scalars through the very same
    `_scalar` the scanner uses, and literal block scalars kept as text — because a `run:`
    body is the check, and the tests below *execute* it. Fail-closed on everything else,
    exactly as `scan_text` is: a construct outside the subset raises `Unparsed` and stops
    the suite rather than being guessed at, since a mis-read structure would answer "which
    trigger reaches publish" confidently and wrongly.

    Two limits, stated rather than assumed. Scalars stay **strings** — no `true`/`123`
    inference, so `required: true` reads as `"true"` and no test can quietly depend on this
    reader's idea of a type. And a key is a key: `on:` is the string `"on"` here, where
    YAML 1.1 would have made it the boolean `True` — which is GitHub's own behaviour, and
    the reason the workflow schema is written the way it is.
    """

    def __init__(self, text: str) -> None:
        # A private copy: `_sequence` blanks a `- ` it has consumed, so the item's first
        # line then reads as the ordinary line it means.
        self.lines = text.splitlines()
        self.i = 0

    # ---------------------------------------------------------------- lines

    def _skip(self) -> None:
        """Advance to the next line that carries a node — not blank, not a comment."""
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            if "\t" in raw:
                raise Unparsed(self.i + 1, "a tab character")
            stripped = raw.strip()
            if stripped in ("---", "..."):
                raise Unparsed(self.i + 1,
                               "a document marker — this reader loads one document")
            if not stripped or stripped.startswith("#"):
                self.i += 1
                continue
            return

    def _head(self) -> tuple[int, int | None, int]:
        """(column of the content, column of a `- ` opening an item or None, line number)."""
        raw = self.lines[self.i]
        no = self.i + 1
        col = len(raw) - len(raw.lstrip(" "))
        dash = None
        if raw[col] == "-" and (col + 1 >= len(raw) or raw[col + 1] == " "):
            dash = col
            col += 1
            while col < len(raw) and raw[col] == " ":
                col += 1
            if col < len(raw) and raw[col] == "-" and (
                    col + 1 >= len(raw) or raw[col + 1] == " "):
                raise Unparsed(no, "a nested sequence opened on one line")
        return col, dash, no

    # ---------------------------------------------------------------- nodes

    def load(self) -> object:
        self._skip()
        if self.i >= len(self.lines):
            return {}
        col, dash, _ = self._head()
        node = self._node(dash if dash is not None else col)
        self._skip()
        if self.i < len(self.lines):
            raise Unparsed(self.i + 1, "a line at a column no block above it opened")
        return node

    def _node(self, indent: int) -> object:
        _, dash, _ = self._head()
        return self._sequence(indent) if dash is not None else self._mapping(indent)

    def _sequence(self, indent: int) -> list:
        out: list = []
        while True:
            self._skip()
            if self.i >= len(self.lines):
                return out
            col, dash, no = self._head()
            if dash is None:
                if col >= indent:
                    raise Unparsed(no, "a mapping key where a sequence item was expected")
                return out
            if dash != indent:
                if dash > indent:
                    raise Unparsed(no, "a sequence item indented past its list")
                return out
            raw = self.lines[self.i]
            rest = raw[col:] if col < len(raw) else ""
            if not rest or rest.startswith("#"):
                self.i += 1                    # the item's node is on a following line
                self._skip()
                if self.i >= len(self.lines):
                    raise Unparsed(no, "a sequence item with nothing in it")
                ccol, cdash, _ = self._head()
                start = cdash if cdash is not None else ccol
                if start <= indent:
                    raise Unparsed(no, "a sequence item with nothing in it")
                out.append(self._node(start) if cdash is not None
                           else self._item(start))
                continue
            # Consume the dash by blanking it. `- uses: x` then reads as `uses: x` at the
            # content column, which is what it means — and the item's later keys line up
            # under it without this reader having to model "the first line was special".
            self.lines[self.i] = " " * col + rest
            out.append(self._item(col))

    def _item(self, indent: int) -> object:
        """A sequence item: a mapping (`- uses: x`) or a scalar (`- macOS`).

        Only a *sequence* item may be a bare scalar. `a:\\n  b` stays refused, because a
        scalar wrapped onto the line below its key is the one shape where guessing would
        read a continued value as a value of its own.
        """
        raw = self.lines[self.i]
        no = self.i + 1
        if self._opens_entry(raw, indent, no):
            return self._mapping(indent)
        value, end = _scalar(raw, indent, no)
        _trailing(raw, end, no)
        self.i += 1
        return value

    def _opens_entry(self, raw: str, col: int, no: int) -> bool:
        """Does this line begin `key:`? Indicators answer yes so `_mapping` names them."""
        if raw[col] in _INDICATORS or raw[col] in "|>":
            return True
        _, k = _scalar(raw, col, no)
        while k < len(raw) and raw[k] == " ":
            k += 1
        return k < len(raw) and raw[k] == ":" and (k + 1 >= len(raw) or raw[k + 1] == " ")

    def _mapping(self, indent: int) -> dict:
        out: dict = {}
        while True:
            self._skip()
            if self.i >= len(self.lines):
                return out
            col, dash, no = self._head()
            if (dash if dash is not None else col) < indent:
                return out                     # a dedent: this block is finished
            if dash is not None:
                raise Unparsed(no, "a sequence item where a mapping key was expected")
            if col > indent:
                raise Unparsed(no, "a value continued on the next line")

            raw = self.lines[self.i]
            if raw[col] in _INDICATORS:
                raise Unparsed(no, _INDICATORS[raw[col]])
            if raw[col] in "|>":
                raise Unparsed(no, "a block scalar in key position")
            name, k = _scalar(raw, col, no)
            while k < len(raw) and raw[k] == " ":
                k += 1
            if k >= len(raw) or raw[k] != ":" or (k + 1 < len(raw) and raw[k + 1] != " "):
                raise Unparsed(no, "a line that is not a mapping entry")
            if name == "<<":
                raise Unparsed(no, "a merge key")
            if name in out:
                raise Unparsed(no, f"a duplicate key: {name}")
            tail = raw[k + 1:]
            self.i += 1
            out[name] = self._value(tail, col, no)

    def _value(self, tail: str, key_col: int, no: int) -> object:
        tail = tail.lstrip(" ")
        if not tail or tail.startswith("#"):
            self._skip()
            if self.i >= len(self.lines):
                return None
            col, dash, cno = self._head()
            if dash is not None and dash == key_col:
                raise Unparsed(cno, "a sequence indented level with its key")
            start = dash if dash is not None else col
            if start <= key_col:
                return None                    # an empty value: `push:` with a key next
            return self._node(start)
        if _BLOCK_HEADER.match(tail):
            return self._block(tail, key_col, no)
        if tail[0] == "[":
            return self._flow(tail, no)
        if tail[0] in _INDICATORS:
            raise Unparsed(no, _INDICATORS[tail[0]])
        value, end = _scalar(tail, 0, no)
        _trailing(tail, end, no)
        return value

    def _block(self, header: str, key_col: int, no: int) -> str:
        """A literal block scalar, kept as text. This is where a `run:` script lives."""
        style, indicators = header[0], header[1:].partition("#")[0].strip()
        if style == ">":
            raise Unparsed(no, "a folded block scalar — this reader does not fold")
        if any(c.isdigit() for c in indicators):
            raise Unparsed(no, "a block scalar with an explicit indentation indicator")
        if "+" in indicators:
            raise Unparsed(no, "a block scalar that keeps its trailing blank lines")
        body: list[str] = []
        first: int | None = None
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            if not raw.strip():
                body.append("")
                self.i += 1
                continue
            here = len(raw) - len(raw.lstrip(" "))
            if here <= key_col:
                break
            if first is None:
                first = here
            elif here < first:
                raise Unparsed(self.i + 1,
                               "a block scalar line indented less than its first")
            body.append(raw[first:])
            self.i += 1
        while body and not body[-1]:
            body.pop()                         # trailing blanks belong to the document
        text = "\n".join(body)
        return text if "-" in indicators else text + "\n"

    def _flow(self, tail: str, no: int) -> list:
        """A flow sequence of scalars — `tags: ["v*"]`. A mapping in one is refused."""
        close = tail.find("]")
        if close < 0:
            raise Unparsed(no, "a flow collection spanning lines")
        if "{" in tail[:close] or ":" in tail[:close]:
            raise Unparsed(no, "a mapping inside a flow sequence")
        out: list[str] = []
        i = 1
        while True:
            while i < len(tail) and tail[i] in " ,":
                i += 1
            if i >= len(tail):
                raise Unparsed(no, "a flow collection spanning lines")
            if tail[i] == "]":
                _trailing(tail, i + 1, no)
                return out
            if tail[i] in "'\"":
                item, i = _scalar(tail, i, no)
            else:
                end = i
                while end < len(tail) and tail[end] not in ",]":
                    end += 1
                item, i = tail[i:end].rstrip(), end
            out.append(item)


def load(text: str) -> object:
    """A workflow as a tree: mappings, sequences, scalars, and `run:` bodies as text."""
    return _Loader(text).load()


def needs(job: dict) -> set[str]:
    """The jobs this one waits for, in both shapes `needs:` is written in."""
    declared = job.get("needs")
    if declared is None:
        return set()
    return {declared} if isinstance(declared, str) else set(declared)


def reached_before(jobs: dict, name: str) -> set[str]:
    """Every job that must have finished before `name` starts."""
    seen: set[str] = set()
    queue = list(needs(jobs[name]))
    while queue:
        job = queue.pop()
        if job in seen:
            continue
        seen.add(job)
        queue.extend(needs(jobs[job]))
    return seen


# --------------------------------------------------------------------------- the rule

def _unquote(ref: str) -> str:
    ref = ref.strip()
    if len(ref) >= 2 and ref[0] == ref[-1] and ref[0] in "'\"":
        return ref[1:-1]
    return ref


def is_local(ref: str) -> bool:
    """Does this reference name a path in this repository rather than somebody's repo?"""
    return bool(_LOCAL.match(_unquote(ref)))


def local_target(ref: str) -> str | None:
    """The repo-relative path a local reference names, or None if it leaves the tree.

    `uses: ./x` is resolved by GitHub against the repository root, not against the file
    holding it. A path that normalises to something outside the root is not "in this tree"
    however it is spelled, so it gets no immutability credit here.
    """
    rel = os.path.normpath(_unquote(ref))
    if os.path.isabs(rel) or rel == ".." or rel.startswith(".." + os.sep):
        return None
    return Path(rel).as_posix()


def immutable(ref: str) -> bool:
    """Can this third-party reference be made to mean different bytes by its owner?

    True when it cannot: an image digest, or `owner/repo` (optionally with a subdirectory)
    at a full commit SHA. Local references are not this function's question — they are
    `local_target`'s, because the answer depends on whether the file is tracked here.
    """
    ref = _unquote(ref)
    if ref.startswith("docker://"):
        _, _, tail = ref.partition("docker://")
        _, sep, digest = tail.rpartition("@")
        return bool(sep) and bool(_DIGEST.match(digest))
    owner, sep, rev = ref.rpartition("@")
    if not sep or owner.count("/") < 1:
        return False                      # no ref at all, or not `owner/repo`
    return bool(_SHA.match(rev))


def immutable_image(ref: str) -> bool:
    """A container image is a content address only when it names a digest.

    `node:18` is a tag its publisher rewrites, exactly like `@v4` — and `container.image`
    runs in the job beside whatever token the job holds.
    """
    ref = _unquote(ref)
    if ref.startswith("docker://"):
        ref = ref.partition("docker://")[2]
    _, sep, digest = ref.rpartition("@")
    return bool(sep) and bool(_DIGEST.match(digest))


# --------------------------------------------------------------------------- the files

def tracked() -> set[str]:
    """Every path in this repository's index: the set of files that move only with a commit.

    This replaces a hardcoded list of directories to skip. A denylist of `node_modules`,
    `dist`, `.venv` is a guess at where untracked code lives; the index is the answer.
    """
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"],
        capture_output=True, check=True, text=True)
    return {p for p in out.stdout.split("\0") if p}


def _action_files(rel: str, index: set[str]) -> list[str]:
    """The tracked file(s) a local reference resolves to, in the two shapes GitHub allows.

    A directory holding `action.yml`/`action.yaml`, or a reusable workflow under
    `.github/workflows/`. There is no third shape, and that is load-bearing: both of these
    are already in `seed_files`, so a local reference never names a file this scan would
    otherwise miss and there is no second walk to get wrong. `TheFileListComesFromTheIndex`
    holds that invariant, so widening this function without widening the seed list fails.
    """
    if rel.endswith((".yml", ".yaml")):
        return [rel] if rel in index and rel.startswith(".github/workflows/") else []
    return [c for c in (f"{rel}/action.yml", f"{rel}/action.yaml") if c in index]


def seed_files(root: Path = REPO, index: set[str] | None = None) -> list[Path]:
    """Where a `uses:` can enter CI, from two sources rather than one walk.

    Everything under `.github/` on disk — a workflow added but not yet committed is still a
    workflow somebody is about to run, and a list of the two files that exist today is a
    list somebody adds a third file beside. Plus every tracked `action.y*ml` anywhere in
    the tree, because a composite action runs inside the calling job.

    `root` and `index` are arguments rather than globals so the traversal can be exercised
    against a tree built for the purpose. This repository has no `action.yml` today, and a
    guard whose only input is a repository that never triggers it is a guard nobody has
    ever seen work.
    """
    index = tracked() if index is None else index
    github = root / ".github"
    found = {p for p in github.rglob("*") if p.is_file() and p.suffix in (".yml", ".yaml")}
    for rel in index:
        if os.path.basename(rel) in ("action.yml", "action.yaml"):
            found.add(root / rel)
    return sorted(found)


def _no_symlink(path: Path) -> None:
    """A tracked symlink moves with a commit; the bytes it points at need not.

    Git stores a symlink as its target string, so `./tools/act` can be a committed link
    into `node_modules` — immutable as a name, and not as code.
    """
    if os.path.realpath(path) != str(path):
        raise Unparsed(0, f"{path} is reached through a symlink")


class Closure(NamedTuple):
    refs: list[tuple[str, Ref]]        # (repo-relative file, ref)
    local: list[tuple[str, Ref, str]]  # (file, ref, resolved repo-relative target)


def closure(root: Path = REPO, index: set[str] | None = None) -> Closure:
    """Every reference CI can reach, and every local reference's resolved target.

    A local composite action runs inside the calling job with the calling job's token, so
    its own `uses:` lines are checked exactly like the caller's — they are here because
    every file a local reference can name is already in `seed_files`, not because this
    function walks a second time. `_action_files` is what makes that true.
    """
    index = tracked() if index is None else index
    refs: list[tuple[str, Ref]] = []
    local: list[tuple[str, Ref, str]] = []

    for path in seed_files(root, index):
        _no_symlink(path)
        name = path.relative_to(root).as_posix()
        for ref in scan_text(path.read_text()):
            refs.append((name, ref))
            if ref.key == "uses" and is_local(ref.ref):
                local.append((name, ref, local_target(ref.ref) or ref.ref))
    return Closure(refs, local)


# --------------------------------------------------------------------------- tests

class TheScannerSeesEverything(unittest.TestCase):
    """A checker that found nothing would pass every test below it."""

    def test_the_workflows_are_where_this_thinks_they_are(self):
        names = {p.relative_to(REPO).as_posix() for p in seed_files()}
        self.assertIn(".github/workflows/release.yml", names)
        self.assertIn(".github/workflows/test.yml", names)

    def test_it_finds_actions_to_check_at_all(self):
        self.assertGreater(len(closure().refs), 0,
                           "no `uses:` found anywhere — the scanner is broken, and a "
                           "broken scanner passes every other test here")

    def test_every_file_is_written_in_the_subset_this_reader_understands(self):
        """Fail-closed, and this is the whole of it. There is no path where a construct is
        skipped: anything the reader does not model raises, so a shape that could carry a
        step past it stops the suite instead of being waved through by it."""
        for path in seed_files():
            with self.subTest(file=path.relative_to(REPO).as_posix()):
                try:
                    scan_text(path.read_text())
                except Unparsed as exc:
                    self.fail(f"{path.relative_to(REPO)}: {exc}. Rewrite it in the subset "
                              f"tests/test_workflows.py reads, or teach the reader this "
                              f"construct deliberately — do not delete the check.")

    def test_it_reads_the_pins_that_are_actually_in_release_yml(self):
        """Anchored to the file, so a reader that silently stops finding things is caught.
        `publish` is the job holding `id-token: write`."""
        text = (GITHUB / "workflows" / "release.yml").read_text()
        refs = scan_text(text)
        actions = {r.ref.rpartition("@")[0] for r in refs}
        self.assertIn("pypa/gh-action-pypi-publish", actions)
        self.assertIn("actions/download-artifact", actions)
        self.assertEqual(
            [r for r in refs if r.kind == ACTION and not r.ref.rpartition("@")[1]], [],
            "a step in release.yml came out with no ref at all")


class EveryActionIsPinnedToSomethingImmutable(unittest.TestCase):
    def test_no_workflow_runs_a_ref_its_owner_can_move(self):
        found = closure()
        for name, ref in found.refs:
            if ref.kind == IMAGE:
                continue
            if is_local(ref.ref):
                continue
            with self.subTest(file=name, line=ref.line):
                self.assertTrue(
                    immutable(ref.ref),
                    f"{ref.ref} is a ref somebody else can move. Pin it to a full commit "
                    f"SHA with the tag in a trailing comment — see release.yml's "
                    f"header for why (#443).")

    def test_no_job_runs_a_container_image_its_publisher_can_move(self):
        """Selected on what the ref *is*, not on the key that spelled it, so both shapes
        of `container:`/`services:` — the `image:` mapping and the bare-scalar shorthand —
        arrive here without this test naming either one."""
        for name, ref in closure().refs:
            if ref.kind != IMAGE:
                continue
            with self.subTest(file=name, line=ref.line):
                self.assertTrue(
                    immutable_image(ref.ref),
                    f"{ref.ref} is an image tag. `container:`/`services:` run third-party "
                    f"bytes in the job exactly as a step does; name a @sha256: digest.")

    def test_every_local_action_is_a_file_committed_to_this_repository(self):
        """`uses: ./x` earns its immutability from being *tracked*, not from being on disk.
        `./node_modules/probe` is a path in this tree that an `npm install` rewrites."""
        index = tracked()
        for name, ref, target in closure().local:
            with self.subTest(file=name, line=ref.line):
                self.assertTrue(
                    _action_files(target, index),
                    f"{ref.ref} names no file tracked in this repository. A local action "
                    f"runs in the calling job with the calling job's token; if it is not "
                    f"committed here, 'it moves only with a commit here' is false.")

    def test_every_pin_says_which_version_it_is(self):
        """The SHA is the security property; the trailing tag is what makes it
        maintainable. Without it nobody can tell whether the pin is a year stale, and a pin
        nobody dares move is how an unpatched action outlives the reason it was pinned."""
        for path in seed_files():
            lines = path.read_text().splitlines()
            for ref in scan_text(path.read_text()):
                if not _SHA.match(_unquote(ref.ref).rpartition("@")[2]):
                    continue
                with self.subTest(file=path.relative_to(REPO).as_posix(), line=ref.line):
                    _, sep, comment = lines[ref.line - 1].partition("#")
                    self.assertTrue(sep and comment.strip(),
                                    "a SHA pin with no `# <tag>` beside it")

    def test_something_is_watching_the_pins_for_updates(self):
        """A pin freezes a security fix out as effectively as it freezes an attacker out.
        Dependabot opens the pull request that moves one; a human still merges it."""
        cfg = GITHUB / "dependabot.yml"
        self.assertTrue(cfg.is_file(), "SHA-pinned actions with nothing watching them")
        self.assertIn("github-actions", cfg.read_text())


class TheRuleIsAboutMovability(unittest.TestCase):
    """The predicate itself, on the spellings a "does it say v4" check would wave through.

    Not a denylist of bad strings — that is the guard this repository has now watched fail
    five times. Each case below asks the same one question: *given only this ref, can the
    bytes it resolves to change without a commit landing here?*
    """

    def test_a_full_sha_is_the_only_accepted_third_party_ref(self):
        self.assertTrue(immutable("actions/checkout@" + "a" * 40))
        self.assertTrue(immutable("owner/repo/sub/dir@" + "0" * 40))

    def test_near_misses_are_not_pins(self):
        for ref in (
            "actions/checkout@v4",                     # a tag its owner can retarget
            "actions/checkout@v4.4.0",                 # an exact tag is still a tag
            "pypa/gh-action-pypi-publish@release/v1",  # a branch head
            "actions/checkout@main",
            "actions/checkout@" + "a" * 39,            # short
            "actions/checkout@" + "a" * 41,            # long
            "actions/checkout@" + "A" * 40,            # not the spelling any tool emits
            "actions/checkout@" + "g" * 40,            # 40 chars, not hex
            "actions/checkout",                        # no ref at all
            "actions/checkout@${{ env.PIN }}",         # resolved at run time, elsewhere
            "docker://alpine:3.20",                    # a tag on an image is a tag
            "docker://alpine@sha256:" + "a" * 63,      # short digest
        ):
            with self.subTest(ref=ref):
                self.assertFalse(immutable(ref), ref)

    def test_an_image_digest_is_a_content_address_too(self):
        self.assertTrue(immutable("docker://alpine@sha256:" + "b" * 64))
        self.assertTrue(immutable_image("alpine@sha256:" + "b" * 64))
        self.assertFalse(immutable_image("node:18"))
        self.assertFalse(immutable_image("node:18@sha256:" + "b" * 63))

    def test_quoting_does_not_change_the_answer(self):
        """YAML lets the same value be written three ways, and a scanner that only knows
        one of them is a scanner with two holes in it."""
        self.assertTrue(immutable('"actions/checkout@' + "a" * 40 + '"'))
        self.assertFalse(immutable("'actions/checkout@v4'"))

    def test_a_local_reference_is_recognised_however_it_is_spelled(self):
        for ref in ("./.github/actions/setup", '"./tools/act"', "'../x'", "./x/action.yml"):
            with self.subTest(ref=ref):
                self.assertTrue(is_local(ref))
        self.assertFalse(is_local("actions/checkout@" + "a" * 40))

    def test_a_path_that_leaves_the_repository_is_not_in_this_tree(self):
        """`immutable` used to return True for anything starting `../`, on the grounds that
        it was "in this tree". `../../evil` is not in this tree."""
        self.assertIsNone(local_target("../../evil"))
        self.assertIsNone(local_target("./a/../../evil"))
        self.assertEqual(local_target("./.github/actions/setup"), ".github/actions/setup")
        self.assertEqual(local_target('"./tools/act"'), "tools/act")

    def test_a_local_reference_earns_nothing_from_merely_existing_on_disk(self):
        """The bypass this replaces, as a unit: `./node_modules/probe` resolves to a path,
        and that path is not in the index, so it is not a pin."""
        self.assertEqual(local_target("./node_modules/probe"), "node_modules/probe")
        self.assertEqual(_action_files("node_modules/probe", {"README.md"}), [])
        self.assertEqual(_action_files("tools/act", {"tools/act/action.yml"}),
                         ["tools/act/action.yml"])


def _steps(*lines: str) -> str:
    """A step list in the shape release.yml writes one, so indentation is realistic."""
    return "jobs:\n  publish:\n    steps:\n" + "".join(lines)


class TheKeyHasManySpellings(unittest.TestCase):
    """The corpus. Every entry is a way to write `uses` that a real YAML parser resolves to
    the key `uses`, and that the first version of this file could not see.

    Each case asserts **which** outcome it gets — parsed-and-refused, or refused as
    unparsed — because "the suite went red" is not evidence that this check did it. A case
    that flipped from parsed to unparsed would still be safe but would mean the reader had
    quietly stopped reading, and that is worth knowing.
    """

    SEEN = [
        # (name, yaml, the value the reader must extract)
        ("a bare key",
         _steps('      - uses: evil/action@main\n'), "evil/action@main"),
        ("a double-quoted key",
         _steps('      - "uses": evil/action@main\n'), "evil/action@main"),
        ("a single-quoted key",
         _steps("      - 'uses': evil/action@main\n"), "evil/action@main"),
        ("a hex-escaped key",
         _steps('      - "\\x75ses": evil/action@main\n'), "evil/action@main"),
        ("a unicode-escaped key",
         _steps('      - "\\u0075ses": evil/action@main\n'), "evil/action@main"),
        ("space before the colon",
         _steps('      - uses : evil/action@main\n'), "evil/action@main"),
        ("space before the colon, quoted",
         _steps('      - "uses"  : evil/action@main\n'), "evil/action@main"),
        ("the dash on its own line",
         _steps('      -\n        uses: evil/action@main\n'), "evil/action@main"),
        ("a double-quoted value",
         _steps('      - uses: "evil/action@main"\n'), "evil/action@main"),
        ("a single-quoted value",
         _steps("      - uses: 'evil/action@main'\n"), "evil/action@main"),
        ("a value that looks like a comment anchor",
         _steps('      - uses: evil/action@main # v1\n'), "evil/action@main"),
        ("a container image",
         "jobs:\n  publish:\n    container:\n      image: node:18\n", "node:18"),
        # The second shape of the same key, and the bypass this corpus grew for. GitHub:
        # "when you only specify a container image, you can omit the `image` keyword".
        ("a container image in the shorthand",
         "jobs:\n  publish:\n    container: evil/img:latest\n", "evil/img:latest"),
        ("a container image in the shorthand, quoted",
         "jobs:\n  publish:\n    container: 'evil/img:latest'\n", "evil/img:latest"),
        ("a container image in the shorthand, hex-escaped key",
         'jobs:\n  publish:\n    "\\x63ontainer": evil/img:latest\n', "evil/img:latest"),
        ("a container image in the shorthand, docker://",
         "jobs:\n  publish:\n    container: docker://evil/img:latest\n",
         "docker://evil/img:latest"),
        ("a service image in the shorthand",
         "jobs:\n  publish:\n    services:\n      redis: evil/redis:latest\n",
         "evil/redis:latest"),
        ("a service image in the long form",
         "jobs:\n  publish:\n    services:\n      redis:\n        image: evil/redis:latest\n",
         "evil/redis:latest"),
    ]

    REFUSED = [
        ("an explicit key", _steps('      - ? uses\n        : evil/action@main\n'),
         "an explicit key"),
        ("a flow mapping step", _steps('      - {uses: evil/action@main}\n'),
         "a flow mapping"),
        ("a flow mapping value", "jobs:\n  publish:\n    steps: [{uses: e/a@main}]\n",
         "a mapping inside a flow sequence"),
        ("an implicit pair in a flow sequence",
         "jobs:\n  publish:\n    steps: [uses: evil/action@main]\n",
         "a mapping inside a flow sequence"),
        ("an anchored step", _steps('      - &s\n        uses: evil/action@main\n'),
         "an anchor"),
        ("an aliased step", _steps('      - *s\n'), "an alias"),
        ("a merge key", _steps('      - <<: *s\n        name: x\n'), "a merge key"),
        ("a tagged step", _steps('      - !!map\n        uses: evil/action@main\n'),
         "a tag"),
        ("an aliased value", _steps('      - uses: *pin\n'), "an alias"),
        ("a value on the next line", _steps('      - uses:\n          evil/action@main\n'),
         "a `uses:` whose value is not on its own line"),
        ("a folded value", _steps('      - uses: >-\n          evil/action@main\n'),
         "a `uses:` written as a block scalar"),
        ("a literal value", _steps('      - uses: |-\n          evil/action@main\n'),
         "a `uses:` written as a block scalar"),
        ("a second document", "jobs: {}\n---\njobs:\n  p:\n    steps:\n"
                              "      - uses: evil/action@main\n", "a flow mapping"),
        ("a tab where a space belongs", _steps('      -\tuses: evil/action@main\n'),
         "a tab character"),
        ("a folded double-quoted key", _steps('      - "us\\\n        es": e/a@main\n'),
         "a double-quoted scalar folded onto the next line"),
        ("a flow sequence left open", "jobs:\n  p:\n    steps: [\n      uses: e/a@main]\n",
         "a flow collection spanning lines"),
        ("a second colon the reader would have to guess about",
         _steps('      - uses: evil/action@main: extra\n'),
         "two values on one line, or a scalar this reader misread"),
        # The shorthand's own escape hatches: an image is still an image when YAML puts it
        # on the following line or folds it, and neither shape is guessed at.
        ("a shorthand image on the next line",
         "jobs:\n  publish:\n    container:\n      evil/img:latest\n",
         "a container image on a line of its own"),
        ("a shorthand service image on the next line",
         "jobs:\n  publish:\n    services:\n      redis:\n        evil/redis:latest\n",
         "a container image on a line of its own"),
        ("a shorthand image folded",
         "jobs:\n  publish:\n    container: >-\n      evil/img:latest\n",
         "a `container:` written as a block scalar"),
        ("a shorthand image as a literal block",
         "jobs:\n  publish:\n    services:\n      redis: |-\n        evil/redis:latest\n",
         "a `redis:` written as a block scalar"),
        ("a services node that is not a mapping of containers",
         "jobs:\n  publish:\n    services: evil/redis:latest\n",
         "a `services:` whose value is not a mapping"),
        ("a services node folded",
         "jobs:\n  publish:\n    services: >-\n      redis: evil/redis:latest\n",
         "a `services:` written as a block scalar"),
        ("a step ref in a flow sequence", _steps('      - uses: [evil/action@main]\n'),
         "a `uses:` whose value is a flow sequence"),
        ("a shorthand image in a flow sequence",
         "jobs:\n  publish:\n    container: [evil/img:latest]\n",
         "a `container:` whose value is a flow sequence"),
    ]

    def test_every_spelling_of_the_key_is_read_and_refused(self):
        for name, text, expected in self.SEEN:
            with self.subTest(spelling=name):
                refs = scan_text(text)
                self.assertEqual([r.ref for r in refs], [expected],
                                 f"{name}: the reader did not extract the value")
                rule = immutable_image if refs[0].kind == IMAGE else immutable
                self.assertFalse(rule(refs[0].ref),
                                 f"{name}: extracted but judged pinned")

    def test_every_construct_outside_the_subset_stops_the_suite_by_name(self):
        for name, text, expected in self.REFUSED:
            with self.subTest(spelling=name):
                with self.assertRaises(Unparsed) as caught:
                    scan_text(text)
                self.assertEqual(caught.exception.what, expected,
                                 f"{name}: refused, but for a different reason than the "
                                 f"one this case exists to exercise")

    def test_a_digest_pinned_container_survives_both_of_its_shapes(self):
        """The other half for the image keys. `test_a_pinned_step_survives_every_spelling`
        skips them because their rule is `immutable_image`, so without this a reader that
        refused every `container:` outright would pass the corpus above and be useless.
        Both shapes, plus the keys that sit beside an image and are not one."""
        digest = "@sha256:" + "b" * 64
        for name, text in (
            ("the shorthand", f"jobs:\n  p:\n    container: node{digest}\n"),
            ("the mapping", f"jobs:\n  p:\n    container:\n      image: node{digest}\n"),
            ("a service, shorthand",
             f"jobs:\n  p:\n    services:\n      redis: redis{digest}\n"),
            ("a service, mapping and its neighbours",
             f"jobs:\n  p:\n    services:\n      redis:\n        image: redis{digest}\n"
             f"        ports:\n          - 6379:6379\n        env:\n          X: y\n"),
            ("a container beside its options",
             f"jobs:\n  p:\n    container:\n      image: node{digest}\n"
             f"      options: --cpus 2\n      credentials:\n        username: u\n"),
        ):
            with self.subTest(shape=name):
                refs = scan_text(text)
                self.assertEqual([r.ref for r in refs], [
                    ("node" if "service" not in name else "redis") + digest], name)
                self.assertEqual(refs[0].kind, IMAGE, name)
                self.assertTrue(immutable_image(refs[0].ref), name)

    def test_the_scope_of_a_container_block_ends_where_its_indentation_does(self):
        """Both container scopes close on dedent, and that is load-bearing in each
        direction. A bare scalar *inside* a container node is the shorthand and stops the
        suite; the same shape outside one is an ordinary wrapped value this reader has
        always let through, and it must stay let through. A key at the column the service
        ids used is a key, not a fourth service — scope is indentation here because it is
        indentation in the real parser."""
        sha, digest = "a" * 40, "@sha256:" + "b" * 64
        text = (f"jobs:\n  p:\n    container:\n      image: node{digest}\n"
                f"    steps:\n      - uses: actions/checkout@{sha}\n"
                f"      - run: echo hi\n")
        self.assertEqual([(r.kind, r.ref) for r in scan_text(text)],
                         [(IMAGE, f"node{digest}"), (ACTION, f"actions/checkout@{sha}")])

        wrapped = (f"jobs:\n  p:\n    container:\n      image: node{digest}\n"
                   f"    name: a job name that\n      wraps onto a second line\n"
                   f"    steps:\n      - uses: actions/checkout@{sha}\n")
        self.assertEqual([r.ref for r in scan_text(wrapped)],
                         [f"node{digest}", f"actions/checkout@{sha}"],
                         "a wrapped value outside the container node was refused as if it "
                         "were the image shorthand")

        beside = (f"jobs:\n  p:\n    services:\n      redis:\n        image: r{digest}\n"
                  f"    env:\n      TOKEN: not-an-image\n")
        self.assertEqual([(r.key, r.ref) for r in scan_text(beside)],
                         [("image", f"r{digest}")],
                         "a key beside the services block was read as another service")

    def test_a_pinned_step_survives_every_spelling_too(self):
        """The corpus above would pass against a reader that refused everything. This is
        the other half: the same spellings, pinned, must come out clean."""
        sha = "a" * 40
        for name, text, _ in self.SEEN:
            if "image" in name:
                continue
            with self.subTest(spelling=name):
                refs = scan_text(text.replace("evil/action@main", f"actions/checkout@{sha}"))
                self.assertEqual(len(refs), 1)
                self.assertTrue(immutable(refs[0].ref), name)


class TheSubsetIsWideEnoughToWriteAWorkflowIn(unittest.TestCase):
    """The other direction. A reader that raised on everything would satisfy every check
    above and be useless — these are constructs this repository's files actually contain,
    and each one must read clean.
    """

    def test_the_shapes_the_real_files_use(self):
        for name, text in (
            ("a flow sequence of scalars", 'on:\n  push:\n    tags: ["v*"]\n'),
            ("a matrix", 'matrix:\n  python-version: ["3.11", "3.12"]\n'),
            ("an expression value", "with:\n  python-version: ${{ matrix.python }}\n"),
            ("a url with a colon in it", "url: https://pypi.org/p/charter-cp\n"),
            ("a url with a fragment", "url: https://x/SECURITY.md#reporting\n"),
            ("a comment after a value", "id-token: write        # REQUIRED: mints it\n"),
            ("a block scalar", "run: |\n  echo hi\n  # uses: evil/action@main\n"),
            ("a folded block scalar", "description: >\n  a b\n  c\n"),
            ("a keyless block", "on:\n  push:\n  pull_request:\n"),
            ("an if expression",
             "if: github.event_name == 'push' && github.ref == 'refs/heads/main'\n"),
            ("a dropdown of plain items",
             "options:\n  - macOS\n  - Windows (WSL)\n  - Other\n"),
            ("a whole-line comment at depth", "jobs:\n  p:\n    # a note\n    x: 1\n"),
        ):
            with self.subTest(shape=name):
                self.assertEqual(scan_text(text), [], name)

    def test_a_block_scalar_hides_nothing_and_invents_nothing(self):
        """`run:` content is opaque text, so a `uses:` inside a shell heredoc is neither a
        step nor a false alarm — and the block ends where the indentation does."""
        text = ("steps:\n"
                "  - run: |\n"
                "      echo 'uses: evil/action@main'\n"
                "  - uses: actions/checkout@" + "a" * 40 + "\n")
        self.assertEqual([r.ref for r in scan_text(text)],
                         ["actions/checkout@" + "a" * 40])


class ALineBreakIsTheOtherHalfOfTheSpellingProblem(unittest.TestCase):
    """Where does a line begin? A reader that works line by line has already answered that,
    usually without noticing — and this repository has been bitten by exactly that answer
    before, by an escape that handled `\n` and let U+2028, U+2029 and U+0085 through.

    Here the relationship runs the safe way round, and it is worth stating as a property
    rather than trusting: `str.splitlines` breaks on a **superset** of what a YAML parser
    calls a line break. So every separator GitHub honours is one this reader has already
    honoured, and it cannot be handed a key on a line it never looked at. The cost of the
    superset is the opposite mistake — see the second test — and the opposite mistake is a
    false alarm somebody reads, not a step somebody misses.
    """

    def test_every_separator_a_parser_honours_this_reader_honours_first(self):
        for sep in ("\n", "\r\n", "\r", "\u2028", "\u2029", "\x85", "\x0b", "\x0c"):
            with self.subTest(separator=repr(sep)):
                text = "steps:" + sep + "  - uses: evil/action@main" + sep
                self.assertEqual([r.ref for r in scan_text(text)], ["evil/action@main"],
                                 "a step on the far side of this separator was not read")

    def test_splitting_too_eagerly_shows_up_as_a_finding_not_a_blind_spot(self):
        """U+2028 is a break to `str.splitlines` and not one in YAML 1.2, so a scalar
        containing it comes apart here and not on the runner. That surfaces a ref which is
        not really a step — noise a person resolves in one look — rather than swallowing
        one that is. Stated because the inverse would be the bug."""
        text = "steps:\n  - run: echo\u2028uses: evil/action@main\n"
        self.assertEqual([r.ref for r in scan_text(text)], ["evil/action@main"])


class TheFileListComesFromTheIndex(unittest.TestCase):
    def test_the_workflows_are_tracked(self):
        index = tracked()
        self.assertIn(".github/workflows/release.yml", index)
        self.assertIn(".github/workflows/test.yml", index)

    def test_untracked_directories_need_no_denylist(self):
        """The hole this replaces: `_PRUNE = {"node_modules", "dist", ".venv", …}` was a
        guess at where untracked code lives, and `uses: ./node_modules/probe` walked past
        it. Nothing in those directories is in the index, so nothing needs naming."""
        index = tracked()
        self.assertFalse([p for p in index
                          if p.split("/")[0] in ("node_modules", "dist", ".venv")])

    def test_a_local_reference_resolves_only_to_files_the_seed_list_already_holds(self):
        """Why there is no second walk. Every shape `_action_files` can return is either
        under `.github/` or is a directory's `action.y*ml` — both already seeds. Widen it
        to a third shape without widening `seed_files` and this fails, which is the only
        thing standing between "no walk needed" and "a file nobody reads"."""
        index = {"tools/act/action.yml", "tools/act/action.yaml", "docs/x.yaml",
                 ".github/workflows/reusable.yml", "tools/rogue.yml"}
        resolved = [hop for rel in ("tools/act", "tools/missing", "docs/x.yaml",
                                    "tools/rogue.yml", ".github/workflows/reusable.yml")
                    for hop in _action_files(rel, index)]
        self.assertEqual(sorted(resolved), [".github/workflows/reusable.yml",
                                            "tools/act/action.yaml", "tools/act/action.yml"])
        for hop in resolved:
            self.assertTrue(
                hop.startswith(".github/") or hop.rsplit("/", 1)[-1].startswith("action."),
                f"{hop} is a shape seed_files does not collect")
        self.assertEqual(_action_files("tools/rogue.yml", index), [],
                         "a reusable workflow outside .github/workflows is not one")

    def test_a_tracked_action_file_anywhere_is_a_seed(self):
        """A composite action does not have to live under `.github/`, and the seed list has
        to find one wherever it is. Driven off a synthetic index because this repository has
        none today — a check that only fires on a file nobody has written is not a check."""
        seeds = seed_files(REPO, {"tools/act/action.yml", "docs/notes.yaml", "README.md"})
        self.assertIn(REPO / "tools/act/action.yml", seeds)
        self.assertNotIn(REPO / "docs/notes.yaml", seeds)
        self.assertIn(GITHUB / "workflows" / "release.yml", seeds)


class ALocalActionIsFollowedIntoTheFileItNames(unittest.TestCase):
    """`uses: ./x` is code running in the calling job with the calling job's token. The
    traversal is exercised against a tree built here, because charter has no local action
    to exercise it with and an untested traversal is how `./node_modules/probe` got in.
    """

    def _tree(self, tmp: Path, action: str) -> None:
        (tmp / ".github/workflows").mkdir(parents=True)
        (tmp / ".github/workflows/w.yml").write_text(
            "jobs:\n  j:\n    steps:\n      - uses: ./tools/act\n")
        (tmp / "tools/act").mkdir(parents=True)
        (tmp / "tools/act/action.yml").write_text(
            "runs:\n  using: composite\n  steps:\n" + action)

    def test_a_local_actions_own_uses_is_checked_like_the_callers(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(os.path.realpath(raw))
            self._tree(tmp, "    - uses: evil/action@main\n")
            found = closure(tmp, {".github/workflows/w.yml", "tools/act/action.yml"})
            refs = {(name, r.ref) for name, r in found.refs}
            self.assertIn(("tools/act/action.yml", "evil/action@main"), refs,
                          "the local action's own `uses:` was never read")
            self.assertFalse(immutable("evil/action@main"))

    def test_the_hop_is_only_taken_to_a_tracked_file(self):
        """The bypass, end to end: the action file exists on disk and is not in the index,
        so it is reported as an unresolved local reference rather than followed and
        trusted."""
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(os.path.realpath(raw))
            self._tree(tmp, "    - uses: evil/action@main\n")
            found = closure(tmp, {".github/workflows/w.yml"})
            self.assertEqual([t for _, _, t in found.local], ["tools/act"])
            self.assertEqual(_action_files("tools/act", {".github/workflows/w.yml"}), [])
            self.assertNotIn("evil/action@main", {r.ref for _, r in found.refs})

    def test_a_file_reached_through_a_symlink_is_refused(self):
        """Git tracks a symlink as its target string. The link moves only with a commit;
        what it points at does not, so the file it resolves to is not this repository's."""
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(os.path.realpath(raw))
            (tmp / "real").mkdir()
            (tmp / "real/action.yml").write_text("runs:\n")
            (tmp / "link").symlink_to(tmp / "real")
            _no_symlink(tmp / "real/action.yml")          # the plain path is fine
            with self.assertRaises(Unparsed) as caught:
                _no_symlink(tmp / "link/action.yml")
            self.assertIn("symlink", caught.exception.what)


# ------------------------------------------------------------------ the second reader

class TheStructureIsReadTheSameWayTheRefsAre(unittest.TestCase):
    """`load` gets the corpus treatment `scan_text` gets, in both directions.

    A tree reader that quietly dropped half a file would make every assertion about the
    job graph below vacuously true — the failure mode this repository keeps re-learning —
    so the shapes it must read assert the value it produces, the shapes outside the subset
    assert *which* refusal they get, and the real workflows are read twice and compared.
    """

    READS = [
        ("a nested mapping", 'on:\n  push:\n    tags: ["v*"]\n',
         {"on": {"push": {"tags": ["v*"]}}}),
        ("a key whose value is nothing at all", "on:\n  push:\n  pull_request:\n",
         {"on": {"push": None, "pull_request": None}}),
        ("a sequence of mappings",
         'steps:\n  - uses: a\n    with:\n      x: "1"\n  - run: echo\n',
         {"steps": [{"uses": "a", "with": {"x": "1"}}, {"run": "echo"}]}),
        ("the dash on its own line", "steps:\n  -\n    uses: a\n",
         {"steps": [{"uses": "a"}]}),
        ("a sequence of scalars", "options:\n  - macOS\n  - Windows (WSL)\n",
         {"options": ["macOS", "Windows (WSL)"]}),
        ("a literal block scalar", "run: |\n  echo hi\n  echo there\n",
         {"run": "echo hi\necho there\n"}),
        ("a stripped block scalar", "run: |-\n  echo hi\n", {"run": "echo hi"}),
        ("a block scalar keeps its blank lines and its hashes",
         "run: |\n  a\n\n  # not a comment in here\n  b\n",
         {"run": "a\n\n# not a comment in here\nb\n"}),
        ("a block scalar keeps its own indentation",
         "run: |\n  if x; then\n    y\n  fi\n", {"run": "if x; then\n  y\nfi\n"}),
        ("a comment after a value", "id-token: write        # REQUIRED: mints it\n",
         {"id-token": "write"}),
        ("a whole-line comment at depth", "jobs:\n  # a note\n  p: 1\n",
         {"jobs": {"p": "1"}}),
        ("an expression value", "with:\n  python-version: ${{ matrix.python-version }}\n",
         {"with": {"python-version": "${{ matrix.python-version }}"}}),
        ("a url with a colon in it", "url: https://pypi.org/p/charter-cp\n",
         {"url": "https://pypi.org/p/charter-cp"}),
        ("an if expression", "if: github.event_name == 'push'\n",
         {"if": "github.event_name == 'push'"}),
        ("a quoted key", '"uses": a\n', {"uses": "a"}),
        ("a flow sequence of plain scalars", "on: [push, pull_request]\n",
         {"on": ["push", "pull_request"]}),
        ("an empty flow sequence", "x: []\n", {"x": []}),
        ("a document that is a sequence", "- a\n- b\n", ["a", "b"]),
    ]

    REFUSES = [
        ("a flow mapping", "jobs: {a: b}\n", "a flow mapping"),
        ("an anchor", "a: &x 1\n", "an anchor"),
        ("an alias", "a: *x\n", "an alias"),
        ("a tag", "a: !!str 1\n", "a tag"),
        ("an explicit key", "? a\n: b\n", "an explicit key"),
        ("a directive", "%YAML 1.2\n", "a directive"),
        ("a merge key", "a:\n  <<: *x\n", "a merge key"),
        ("a second document", "a: 1\n---\nb: 2\n",
         "a document marker — this reader loads one document"),
        ("a tab where a space belongs", "a:\tb\n", "a tab character"),
        ("a duplicate key", "a: 1\na: 2\n", "a duplicate key: a"),
        ("a folded block scalar", "a: >\n  x\n",
         "a folded block scalar — this reader does not fold"),
        ("a block scalar that keeps its trailing blanks", "a: |+\n  x\n\n",
         "a block scalar that keeps its trailing blank lines"),
        ("a block scalar with an indentation indicator", "a: |2\n   x\n",
         "a block scalar with an explicit indentation indicator"),
        ("a block scalar line indented less than its first", "a: |\n    x\n  y\n",
         "a block scalar line indented less than its first"),
        ("a sequence indented level with its key", "steps:\n- uses: a\n",
         "a sequence indented level with its key"),
        ("a value continued on the next line", "name: a job name that\n  wraps\n",
         "a value continued on the next line"),
        ("a mapping key where a sequence item belongs", "steps:\n  - a\n  b: 1\n",
         "a mapping key where a sequence item was expected"),
        ("a sequence item where a mapping key belongs", "a:\n  b: 1\n  - c\n",
         "a sequence item where a mapping key was expected"),
        ("a nested sequence on one line", "a:\n  - - b\n",
         "a nested sequence opened on one line"),
        ("a scalar where a key belongs", "a:\n  b\n",
         "a line that is not a mapping entry"),
        ("two values on one line", "a: b: c\n",
         "two values on one line, or a scalar this reader misread"),
        ("a flow collection spanning lines", "a: [\n  b]\n",
         "a flow collection spanning lines"),
        ("a mapping inside a flow sequence", "a: [{b: c}]\n",
         "a mapping inside a flow sequence"),
        ("an unterminated quote", 'a: "b\n', "an unterminated double-quoted scalar"),
        ("a sequence item with nothing in it", "a:\n  -\n", "a sequence item with nothing in it"),
    ]

    def test_every_shape_the_real_files_use_is_read_into_the_value_it_means(self):
        for name, text, expected in self.READS:
            with self.subTest(shape=name):
                self.assertEqual(load(text), expected, name)

    def test_every_construct_outside_the_subset_stops_the_suite_by_name(self):
        for name, text, expected in self.REFUSES:
            with self.subTest(shape=name):
                with self.assertRaises(Unparsed) as caught:
                    load(text)
                self.assertEqual(caught.exception.what, expected,
                                 f"{name}: refused, but for a different reason than the "
                                 f"one this case exists to exercise")

    def test_every_workflow_in_this_repository_reads_as_a_tree(self):
        """Fail-closed on the real files, exactly as the reference scan is. A workflow
        written outside the subset stops the suite rather than being read as a shorter
        workflow that happens to have no `if:` in it."""
        for path in sorted((GITHUB / "workflows").glob("*.y*ml")):
            with self.subTest(file=path.name):
                try:
                    load(path.read_text())
                except Unparsed as exc:
                    self.fail(f"{path.relative_to(REPO)}: {exc}. Rewrite it in the subset "
                              f"tests/test_workflows.py reads, or teach the reader this "
                              f"construct deliberately — do not delete the check.")

    def test_the_two_readers_agree_about_what_is_in_the_file(self):
        """The cross-check that keeps one reader from going quietly blind. Both read the
        same files for the same key by two different routes — a line-oriented scan and a
        tree — and a step either of them cannot see is a step neither can judge."""
        for path in sorted((GITHUB / "workflows").glob("*.y*ml")):
            with self.subTest(file=path.name):
                text = path.read_text()
                scanned = sorted(r.ref for r in scan_text(text) if r.key == "uses")
                walked = sorted(_every(load(text), "uses"))
                self.assertEqual(scanned, walked)
                self.assertTrue(scanned, "neither reader found a step: both are broken")


def _every(node: object, key: str) -> list:
    """Every value under `key`, anywhere in a loaded tree."""
    if isinstance(node, dict):
        return ([node[key]] if key in node else []) + [
            v for child in node.values() for v in _every(child, key)]
    if isinstance(node, list):
        return [v for child in node for v in _every(child, key)]
    return []


# ------------------------------------------------------- which trigger reaches publish

def _release() -> dict:
    return load((GITHUB / "workflows" / "release.yml").read_text())


def _step(job: dict, step_id: str) -> dict:
    """The step this job runs under a given `id:`, refused if it is not there.

    Every step reached this way stands between a release and something irreversible —
    `version-check` is the cross-check #558 exists for, `artefact-set` is the bound #835
    put on what a retry may upload — so "not found" is refused rather than answered with a
    default. A reader that shrugged would report a green measurement of a step that is no
    longer in the file.
    """
    found = [s for s in job["steps"] if isinstance(s, dict) and s.get("id") == step_id]
    if len(found) != 1:
        raise AssertionError(
            f"expected exactly one step with `id: {step_id}`, found {len(found)}. If it "
            f"moved, move the tests that read it with it rather than deleting them.")
    return found[0]


class _Run(NamedTuple):
    """One run of the release workflow, as the version check would see it."""
    name: str
    event: str
    ref: str | None = None        # GITHUB_REF_NAME, unset when None
    claimed: str | None = None    # the `version` input, unset when None
    says: str = ""                # what its refusal must name, when it refuses
    #: GITHUB_REF_TYPE, unset when None. `branch` and `tag` are the only values GitHub
    #: writes here, and the difference decides whether this run's commit is the one its
    #: version's tag names or whatever that ref held when the run started.
    ref_type: str | None = None
    #: What PyPI answers when asked whether it already holds this version — the HTTP
    #: status a stubbed `curl` reports. `"200"` already there, `"404"` not there, `"000"`
    #: or a 5xx unreachable. **None means the run must never ask**, and every case that
    #: says None has that asserted, because a release that needs the network to publish a
    #: tagged tree is a release the network can stop.
    pypi: str | None = None


class _Result(NamedTuple):
    code: int
    said: str
    asked: list[str]      # the argv of every `curl` the script ran, in order


def _execute(script: str, run: _Run, packaged: str = "0.53.0") -> _Result:
    """Actually run the check's script, in a tree whose pyproject says `packaged`.

    Reading the YAML proves the step has no `if:`; only running it proves the step
    refuses. `python` is a shim onto this interpreter because the step's own comment says
    why the workflow pins one: it needs `tomllib`, which is 3.11+, and the runner's
    default `python` is a version nobody chose. `curl` is a shim for a different reason:
    the check asks PyPI a question, this suite reaches no network, and stubbing the answer
    is also the only way to exercise the answers that are hard to arrange for real — a
    version PyPI has never seen, and PyPI not answering at all.
    """
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(os.path.realpath(raw))
        (tmp / "pyproject.toml").write_text(
            f'[project]\nname = "charter-cp"\nversion = "{packaged}"\n')
        (tmp / "bin").mkdir()
        shim = tmp / "bin" / "python"
        shim.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n')
        shim.chmod(0o755)
        log = tmp / "curl-calls"
        answers = run.pypi and run.pypi != "000"
        # A stub that models the two flags the script depends on rather than ignoring its
        # argv, because a stub that answers whatever it is asked cannot fail when the
        # question changes. Real `curl` writes the response body to stdout unless `-o`
        # redirects it, and writes `-w`'s format after that — so a script that dropped
        # either flag would read a status it never received, and here it reads one too.
        curl = tmp / "bin" / "curl"
        curl.write_text(
            "#!/bin/sh\n"
            f'printf "%s\\n" "$*" >> {shlex.quote(str(log))}\n'
            'case "$*" in *" -o "*) ;; *) printf \'{"info": {}}\' ;; esac\n'
            + (f'case "$*" in *"%{{http_code}}"*) printf "%s" {shlex.quote(run.pypi)} ;; esac\n'
               "exit 0\n" if answers else "exit 7\n"))
        curl.chmod(0o755)
        env = {"PATH": f"{tmp / 'bin'}:/usr/bin:/bin", "GITHUB_EVENT_NAME": run.event}
        if run.ref is not None:
            env["GITHUB_REF_NAME"] = run.ref
        if run.ref_type is not None:
            env["GITHUB_REF_TYPE"] = run.ref_type
        if run.claimed is not None:
            env["CLAIMED_VERSION"] = run.claimed
        done = subprocess.run(["bash", "-e", "-c", script], cwd=tmp, env=env,
                              capture_output=True, text=True)
        asked = log.read_text().splitlines() if log.exists() else []
        return _Result(done.returncode, done.stdout + done.stderr, asked)


class TheVersionCheckRunsOnEveryTriggerThatCanPublish(unittest.TestCase):
    """The assertion #558 says is missing: which trigger reaches `publish`, under what.

    `publish` mints an OIDC token PyPI accepts, and an upload it makes cannot be undone —
    so the question is not whether the version check *passed* but whether it *ran*. Those
    are the same colour in GitHub Actions: a step whose `if:` is false reports success.
    The check was gated on `startsWith(github.ref, 'refs/tags/v')`, which is true only of
    a tag push, so `workflow_dispatch` — the retry path, the one a human reaches for when
    a release has already half-happened — published with the guard green and unrun.

    Two halves, and both are here because either alone is satisfiable by a lie. The shape
    says the check cannot be skipped: no `if:` on the job, none on any step in it, and
    `publish` transitively behind it. The behaviour says the check is worth running: its
    script is executed, on both triggers, and refused when the run cannot name what it is
    publishing — no input, the wrong input, a trigger the check was never taught.

    And then the rest of #558, which those halves do not reach. Naming a version is a claim
    about a string; publishing is an act on a commit. On the tag path they are one question
    because `github.ref` *is* the tag. On the dispatch path they came apart, and #673 leaned
    on the gap: `skip-existing` is passed on that trigger because "the dispatch retry is not
    there to publish, it is there to finish a publish that may already have happened". True
    of every run it was written for — and nothing made it true. If PyPI does not already
    hold the version, that run is not finishing anything, it IS the publish, and from
    `--ref main` it publishes whatever the default branch holds, under a version no tag
    names. So a run that is not standing on `v<version>` has to show it cannot be that
    version's first upload, and the tables below are sorted by which of those two things a
    run gets wrong.
    """

    #: Runs that must be refused for not naming what they publish, and what each refusal
    #: must say. The message is asserted because it is what makes the sweep honest: delete
    #: any one refusal in the script and the surviving ones still exit non-zero, so an
    #: exit-code-only test would stay green while the run stopped being told what it did
    #: wrong. Every case is refused before the ref is looked at, so every one carries
    #: `pypi=None` — asserted, not assumed: a run refused for its version asks nobody.
    REFUSED = [
        _Run("a dispatch that names no version", "workflow_dispatch", "main", "",
             says="did not say which version it publishes", ref_type="branch"),
        _Run("a dispatch with no input at all", "workflow_dispatch", "main", None,
             says="did not say which version it publishes", ref_type="branch"),
        _Run("a dispatch naming the wrong version", "workflow_dispatch", "main", "0.52.0",
             says="but pyproject.toml says 0.53.0", ref_type="branch"),
        _Run("a dispatch from a tag-shaped branch, still naming nothing",
             "workflow_dispatch", "v0.53.0", None,
             says="did not say which version it publishes", ref_type="branch"),
        _Run("a dispatch standing on the right tag but naming the wrong version",
             "workflow_dispatch", "v0.53.0", "0.52.0",
             says="but pyproject.toml says 0.53.0", ref_type="tag"),
        _Run("a tag that disagrees with the packaged version", "push", "v0.52.0", None,
             says="but pyproject.toml says 0.53.0", ref_type="tag"),
        _Run("a tag push with no ref name", "push", "", None,
             says="did not say which version it publishes", ref_type="tag"),
        _Run("a trigger nobody taught this check", "schedule", "main", "0.53.0",
             says="does not know what that run claims to publish", ref_type="branch"),
        _Run("a repository_dispatch", "repository_dispatch", "main", "0.53.0",
             says="does not know what that run claims to publish", ref_type="branch"),
        _Run("no event at all", "", "main", "0.53.0",
             says="does not know what that run claims to publish", ref_type="branch"),
    ]

    #: Runs that name the packaged version correctly — every refusal above is satisfied —
    #: and would still be the FIRST upload of it while standing somewhere that is not its
    #: tag. This is the half #560 left open and #673 built on. The first case is the
    #: window #558 opened with: a bump merged to main, no tag pushed yet, and a dispatch
    #: that agrees with the `pyproject.toml` sitting beside it.
    WOULD_BE_THE_FIRST_UPLOAD = [
        _Run("a dispatch from main in the window before the tag is pushed",
             "workflow_dispatch", "main", "0.53.0", says="FIRST upload of charter-cp 0.53.0",
             ref_type="branch", pypi="404"),
        _Run("a dispatch from a branch someone named after the tag",
             "workflow_dispatch", "v0.53.0", "0.53.0",
             says="FIRST upload of charter-cp 0.53.0", ref_type="branch", pypi="404"),
        _Run("a dispatch whose ref type is not set at all", "workflow_dispatch",
             "v0.53.0", "0.53.0", says="FIRST upload of charter-cp 0.53.0", ref_type=None,
             pypi="404"),
        _Run("a dispatch standing on some other version's tag", "workflow_dispatch",
             "v0.52.0", "0.53.0", says="FIRST upload of charter-cp 0.53.0",
             ref_type="tag", pypi="404"),
        _Run("a push that reaches here from a branch rather than a tag", "push",
             "v0.53.0", None, says="FIRST upload of charter-cp 0.53.0", ref_type="branch",
             pypi="404"),
    ]

    #: Same runs, except PyPI does not answer. Whether the run would be a first upload is
    #: then unknown, and the last step before an irreversible act does not guess.
    PYPI_DID_NOT_ANSWER = [
        _Run("PyPI is unreachable", "workflow_dispatch", "main", "0.53.0",
             says="could not ask PyPI", ref_type="branch", pypi="000"),
        _Run("PyPI answers 503", "workflow_dispatch", "main", "0.53.0",
             says="could not ask PyPI", ref_type="branch", pypi="503"),
        _Run("PyPI answers something nobody expected", "push", "v0.53.0", None,
             says="could not ask PyPI", ref_type="branch", pypi="418"),
    ]

    #: Off the tag and allowed, because PyPI already holds the version — so this run cannot
    #: be its first upload and `skip-existing` has something to skip. This is #673's
    #: `--ref main` recovery, and it must keep working: a check that closed #558 by making
    #: a half-finished release unfinishable would have moved the defect, not fixed it.
    FINISHING = [
        _Run("the #665 recovery: the upload landed, announce did not", "workflow_dispatch",
             "main", "0.53.0", ref_type="branch", pypi="200"),
        _Run("the same recovery from a branch named after the tag", "workflow_dispatch",
             "v0.53.0", "0.53.0", ref_type="branch", pypi="200"),
    ]

    #: Runs that must be allowed with nobody asked at all: they stand on the tag for the
    #: version they publish, so what they upload is the tree that tag names. `pypi=None`
    #: is asserted here, and it is a property rather than bookkeeping — the ordinary
    #: release must not be stoppable by PyPI's API being down.
    ACCEPTED = [
        _Run("a tag naming the packaged version", "push", "v0.53.0", None,
             ref_type="tag"),
        _Run("a dispatch standing on the tag it is retrying", "workflow_dispatch",
             "v0.53.0", "0.53.0", ref_type="tag"),
        _Run("a dispatch naming it with the tag's leading v", "workflow_dispatch",
             "v0.53.0", "v0.53.0", ref_type="tag"),
        _Run("a tag run carrying a stale input from an earlier dispatch", "push",
             "v0.53.0", "9.9.9", ref_type="tag"),
    ]

    def setUp(self):
        self.release = _release()
        self.jobs = self.release["jobs"]
        self.check = _step(self.jobs["guard"], "version-check")

    # ----------------------------------------------------------------- the shape

    def test_the_job_graph_from_the_trigger_to_the_release_is_intact(self):
        """Every job before `publish`, and `announce` behind it. If this is rearranged the
        tests below are asserting about a job that no longer gates anything."""
        self.assertEqual(needs(self.jobs["guard"]), set(), "guard waits for nothing")
        self.assertEqual(needs(self.jobs["test"]), {"guard"})
        self.assertEqual(needs(self.jobs["build"]), {"test"})
        self.assertEqual(needs(self.jobs["publish"]), {"build"})
        self.assertEqual(needs(self.jobs["announce"]), {"publish"})
        self.assertEqual(reached_before(self.jobs, "publish"),
                         {"guard", "test", "build"},
                         "publish no longer waits on the job that refuses a bad version")

    def test_no_job_between_the_trigger_and_the_upload_can_be_skipped(self):
        """A job-level `if:` is the same trick one level up: a skipped job is a green
        job, and `needs:` on a green job is satisfied."""
        for name in sorted(reached_before(self.jobs, "publish") | {"publish"}):
            with self.subTest(job=name):
                self.assertNotIn(
                    "if", self.jobs[name],
                    f"the `{name}` job is between a trigger and an irreversible upload, "
                    f"and a condition on it is a way for it to report success unrun")

    def test_no_step_in_the_guard_job_can_be_skipped(self):
        """The regression, exactly. Restore `if: startsWith(github.ref, 'refs/tags/v')`
        on the version check — or put a condition on any other step in the job whose only
        purpose is to refuse — and this goes red."""
        for i, step in enumerate(self.jobs["guard"]["steps"]):
            with self.subTest(step=step.get("name") or step.get("uses") or i):
                self.assertNotIn(
                    "if", step,
                    "a conditional step in `guard`. A skipped step reports success, so "
                    "this is how the release published with its version check unrun "
                    "(#558). Whatever the new trigger needs, it is not a condition here.")

    def test_the_dispatch_path_has_to_say_what_it_is_retrying(self):
        """The input exists, is required, and is wired into the script that reads it. A
        script reading an environment variable the workflow never sets would pass every
        behavioural test below against a value only the test provides."""
        dispatch = self.release["on"]["workflow_dispatch"]
        self.assertIsInstance(dispatch, dict,
                              "`workflow_dispatch:` takes no input, so a retry states "
                              "nothing and there is nothing to cross-examine")
        self.assertEqual(dispatch["inputs"]["version"].get("required"), "true")
        self.assertIn("inputs.version", self.check["env"]["CLAIMED_VERSION"],
                      "the version the check reads does not come from the dispatch input "
                      "— in either spelling, `inputs.version` or the one defined on every "
                      "trigger, `github.event.inputs.version`")

    def test_the_publish_job_still_names_the_environment_pypi(self):
        """Trusted Publishing's OIDC claim carries this name, so it is load-bearing for
        the upload — and it is also where the last piece of #558 hangs: a required
        reviewer on this environment, and a deployment-branch policy narrowing which refs
        may deploy to it, are repository settings rather than lines in this file, so no
        test here can assert them. What this can hold is that the name is still there for
        the rules to attach to."""
        self.assertEqual(self.jobs["publish"]["environment"]["name"], "pypi")

    def test_the_tag_the_check_reconstructs_is_the_tag_this_workflow_triggers_on(self):
        """The check builds `v$pkg` and asks whether the run is standing on it, which is
        the right question only while `v<version>` is what this project tags. Change the
        convention under `on: push:` without changing the check and the tag path starts
        sending itself down the off-tag branch — so the two are asserted together rather
        than left to agree by habit."""
        self.assertEqual(self.release["on"]["push"]["tags"], ["v*"])
        self.assertIn('= "v$pkg"', self.check["run"])

    # ----------------------------------------------------------------- the behaviour

    def test_every_trigger_this_workflow_declares_is_one_the_check_understands(self):
        """The link between the two halves. The tables below name the triggers they
        exercise; adding a third entry under `on:` without teaching the check what such a
        run claims to publish fails here, and fails in the workflow, rather than reaching
        `build` on the strength of nobody having thought about it."""
        declared = set(self.release["on"])
        self.assertEqual(declared, {"push", "workflow_dispatch"})
        for table in (self.ACCEPTED, self.REFUSED, self.WOULD_BE_THE_FIRST_UPLOAD,
                      self.PYPI_DID_NOT_ANSWER):
            for trigger in declared:
                self.assertIn(trigger, {run.event for run in table},
                              f"{trigger} has no case in one of the tables")

    def _refuses(self, table):
        script = self.check["run"]
        for run in table:
            with self.subTest(run=run.name):
                r = _execute(script, run)
                self.assertNotEqual(r.code, 0,
                                    f"{run.name} was allowed to publish:\n{r.said}")
                self.assertIn("::error::", r.said, "refused without annotating the log")
                self.assertIn(run.says, r.said,
                              f"{run.name} was refused, but for a different reason than "
                              f"the one this case exists to exercise")

    def test_the_check_refuses_a_run_that_cannot_name_what_it_publishes(self):
        self._refuses(self.REFUSED)

    def test_a_run_refused_for_its_version_never_asks_anybody_anything(self):
        """The refusals above come first, and they are the cheap ones. A run with no
        version to check has nothing to look up, and a check that went to the network
        before finishing the arithmetic it can do offline would fail differently when PyPI
        is slow than when it is not."""
        script = self.check["run"]
        for run in self.REFUSED:
            with self.subTest(run=run.name):
                self.assertIsNone(run.pypi, "this table is the offline one")
                self.assertEqual(_execute(script, run).asked, [])

    def test_a_run_that_would_be_a_versions_first_upload_from_off_its_tag_is_refused(self):
        """The rest of #558. Every run here names the packaged version correctly, so every
        refusal above is satisfied — and PyPI has never seen this version, so the run is
        not finishing a release, it is beginning one, from a ref no tag names."""
        self._refuses(self.WOULD_BE_THE_FIRST_UPLOAD)

    def test_a_run_that_cannot_find_out_whether_it_would_be_the_first_is_refused(self):
        """Fail closed on the unknown. A network answer that did not arrive is not a
        `404` and not a `200`, and the step that reads it is the last one before an act
        with no way back — where re-running `guard` costs a minute and being wrong costs
        a version number forever."""
        self._refuses(self.PYPI_DID_NOT_ANSWER)

    def test_a_run_finishing_a_release_pypi_already_holds_is_allowed_off_the_tag(self):
        """#673's `--ref main` recovery, kept working. It is the reason this check asks
        PyPI instead of simply demanding the tag: when `announce` fails for a reason still
        true of the tagged tree, the fix is on main and the tag cannot carry it. What the
        check refuses is that same command run when it would publish rather than finish."""
        script = self.check["run"]
        for run in self.FINISHING:
            with self.subTest(run=run.name):
                r = _execute(script, run)
                self.assertEqual(r.code, 0, f"{run.name} was refused:\n{r.said}")
                self.assertEqual(len(r.asked), 1, "asked PyPI more than once")

    def test_the_check_allows_a_run_that_names_the_packaged_version(self):
        """The other direction, and it is not decoration: a check that refused everything
        would pass every case above and take the release path with it.

        `asked == []` is the second half and it is a property, not bookkeeping: a run
        standing on `v0.53.0` publishes the tree that tag names whatever PyPI says, so an
        ordinary release must not be stoppable by pypi.org being unreachable. The network
        is reached on exactly the path that cannot answer the question without it."""
        script = self.check["run"]
        for run in self.ACCEPTED:
            with self.subTest(run=run.name):
                r = _execute(script, run)
                self.assertEqual(r.code, 0, f"{run.name} was refused:\n{r.said}")
                self.assertIn("pyproject=0.53.0", r.said)
                self.assertEqual(r.asked, [],
                                 "a run standing on the tag asked PyPI's permission to "
                                 "publish the tree that tag names")

    def test_the_question_put_to_pypi_names_what_this_run_would_publish(self):
        """Both halves of it read from `pyproject.toml`. A URL with the project or the
        version written into it would answer about some other release and be impossible to
        tell apart from this one on a green run."""
        script = self.check["run"]
        r = _execute(script, self.FINISHING[0])
        self.assertEqual(len(r.asked), 1, r.asked)
        self.assertIn("https://pypi.org/pypi/charter-cp/0.53.0/json", r.asked[0])
        r = _execute(script, self.FINISHING[0]._replace(claimed="9.9.9"), packaged="9.9.9")
        self.assertIn("https://pypi.org/pypi/charter-cp/9.9.9/json", r.asked[0])

    def test_the_refusal_names_the_dispatch_that_would_have_been_accepted(self):
        """A refusal that leaves an operator mid-release without the next command is a
        refusal they will route around, and the route around this one is irreversible."""
        script = self.check["run"]
        for run in self.WOULD_BE_THE_FIRST_UPLOAD + self.PYPI_DID_NOT_ANSWER:
            with self.subTest(run=run.name):
                self.assertIn(
                    "gh workflow run release.yml --ref v0.53.0 -f version=0.53.0",
                    _execute(script, run).said,
                    "the refusal does not name the dispatch that would be accepted")

    def test_no_accepted_run_reaches_the_upload_without_the_tag_or_pypi_saying_so(self):
        """The tables themselves, before they are executed. Every other test is a claim
        about the script; this is a claim about the tables — that the cheap way back to
        green after this change is not to add a permissive row. An allowed run either
        stands on the tag for the version it publishes, or has been told by PyPI that the
        version is already there."""
        for run in self.ACCEPTED:
            with self.subTest(run=run.name):
                self.assertEqual((run.ref_type, run.ref), ("tag", "v0.53.0"),
                                 "an accepted run that is not standing on the tag for the "
                                 "version it publishes uploads a tree no tag names (#558)")
                self.assertIsNone(run.pypi, "and it must not need PyPI's answer to do it")
        for run in self.FINISHING:
            with self.subTest(run=run.name):
                self.assertEqual(run.pypi, "200",
                                 "an off-tag run is allowed only where PyPI has already "
                                 "made this run's upload a no-op (#558, #673)")

    def test_the_check_reads_the_packaged_version_from_pyproject_and_not_from_a_guess(self):
        """The comparison is against the file being published, whatever it says. Pinning
        `0.53.0` in the tables above would otherwise be indistinguishable from a script
        that had the answer written into it — and that goes for the tag it reconstructs as
        much as for the version it compares."""
        script = self.check["run"]
        on_tag = _Run("a tag", "push", "v9.9.9", ref_type="tag")
        self.assertEqual(_execute(script, on_tag, packaged="9.9.9").code, 0)
        self.assertNotEqual(_execute(script, on_tag, packaged="0.53.0").code, 0)
        # And the tag it demands is built from the version, not written down: standing on
        # v0.53.0 while publishing 9.9.9 is off-tag, and off-tag runs are asked about PyPI.
        r = _execute(script, _Run("a dispatch on the wrong tag", "workflow_dispatch",
                                  "v0.53.0", "9.9.9", ref_type="tag", pypi="404"),
                     packaged="9.9.9")
        self.assertNotEqual(r.code, 0, r.said)
        self.assertIn("FIRST upload of charter-cp 9.9.9", r.said)


# ------------------------------------------------- what a pinned action then names (#473)

#: The record of the hop this suite cannot take, read at the SHAs this repository pins.
#:
#: `.json` and not `.y*ml`, on purpose and load-bearing: the record NAMES a movable
#: reference, because naming one is the whole point of it, and every `.y*ml` under
#: `.github/` is a seed file whose every reference the rule above refuses. Written as YAML
#: there, a record of somebody else's tree would be read as a claim about charter's — and
#: correctly refused, with no config key anywhere that could lift the denial (#370).
PUBLISH_CLOSURE = GITHUB / "publish-closure.json"

#: The permission that makes a job the one this record is about. PyPI's Trusted Publishing
#: accepts the token minted under it as charter's genuine publisher, so code in such a job
#: can act as charter off this platform, and what it uploads cannot be taken back.
_IDENTITY = "id-token"


def the_grant_that_can_publish(workflow: dict, job: dict) -> str | None:
    """What makes this job one that can publish charter — in words — or None if nothing.

    A sentence rather than a boolean, and that is not decoration. The three ways a job
    arrives here are not the same claim: two of them are grants somebody wrote down, and
    the third is this reader admitting it cannot see the answer. Telling a reader "this
    job holds `id-token: write`" when what actually happened is "nobody declared any
    permissions" would be a guard overstating what it verified — which is the defect #473
    is about, committed by #473's own fix. It said exactly that in its first draft.

    A job-level `permissions:` **replaces** the workflow's rather than adding to it, which
    `release.yml` says at length about `publish` itself. So the job's own block is the
    whole answer when it has one, and the workflow's is the answer when it does not.

    Fail-closed on everything else, exactly as the two readers above are. A workflow that
    declares no permissions at all runs on the repository's DEFAULT token permissions — a
    setting in GitHub's web UI, not a byte in this tree — so answering "no identity" there
    would be this file confidently reporting a value it cannot see. It answers with the
    admission instead, and the fix is to declare the permissions, which every workflow
    here already does. A spelling neither this function nor GitHub's schema knows raises
    `Unparsed` rather than being read as an absence, for the same reason `container:` had
    to grow its second shape: an unrecognised spelling that reads as "nothing here" is a
    blind spot with a green tick on it.
    """
    where = job if "permissions" in job else workflow
    declared = where.get("permissions")
    if "permissions" in where and declared is None:
        # The key with nothing under it is neither a grant nor a silence, and reading it
        # as either would put a wrong sentence in a failure message. `permissions: {}` —
        # GitHub's own spelling of "no scopes at all" — is a flow mapping and already
        # stops the reader above by name, so this is the one shape left where "declared
        # and empty" and "never declared" would be told apart by nothing.
        raise Unparsed(0, "a `permissions:` key with no scopes under it")
    if declared is None:
        return ("no `permissions:` is declared on the job or on the workflow, so it runs "
                "on the repository's default token permissions — a setting in GitHub's "
                "web UI and not a byte in this tree. Which is to say this reader cannot "
                "see the identity WITHHELD, not that it saw it granted; declare the "
                "permissions and this job stops being one of these")
    if isinstance(declared, str):
        if declared == "write-all":
            return "`permissions: write-all`, which is every scope including this one"
        if declared == "read-all":
            return None
        raise Unparsed(0, f"a `permissions:` scalar this reader does not know: {declared!r}")
    if not isinstance(declared, dict):
        raise Unparsed(0, "a `permissions:` value that is neither a mapping nor a scalar")
    granted = declared.get(_IDENTITY)
    if granted is None or granted in ("none", "read"):
        return None
    if granted == "write":
        return f"`{_IDENTITY}: write`"
    raise Unparsed(0, f"an `{_IDENTITY}:` value this reader does not know: {granted!r}")


class Beside(NamedTuple):
    """A remote action that runs in a job which can publish charter."""
    workflow: str      # the file it is written in
    job: str           # the job it runs in
    action: str        # `owner/repo`, or `owner/repo/path`, with no ref on it
    sha: str           # what it is pinned to — a full commit SHA, by the rule above
    grant: str         # why the job counts, in `the_grant_that_can_publish`'s own words


def beside_the_publishing_identity(root: Path = REPO,
                                   index: set[str] | None = None) -> list[Beside]:
    """Every remote `uses:` that runs in a job which can publish charter.

    Read from the tree and not from `scan_text`, because this question is about a JOB and a
    reference scanner does not know which job a step is in — the same reason `load` exists
    for #558. Images are skipped: a `container:` beside the identity is already held to a
    digest by the rule above, and a digest addresses the whole image, so there is no hop
    left to record.

    A local `uses:` is **followed**, not skipped, and getting that wrong was this
    collector's first draft. `uses: ./x` names charter's own file, so the rule above does
    reach it — but a local composite action runs INSIDE the calling job with the calling
    job's token, so a remote action written in one stands beside `id-token: write` exactly
    as a remote action written in the job does. Stopping at the job would have been this
    collector bounding the refs the *workflow file* names rather than the refs that
    actually run beside the identity: #473's own defect, one level in, inside #473's fix.
    """
    index = tracked() if index is None else index
    found: list[Beside] = []
    # `sorted` for the failure messages, not for the answer: every caller compares sets, so
    # the deletion sweep is right that dropping it changes nothing a test can see. It stays
    # because a `subTest` list that reorders between runs makes two red runs of the same
    # branch look like two different findings.
    for path in sorted((root / ".github" / "workflows").glob("*.y*ml")):
        workflow = load(path.read_text())
        # `or {}` because a file under `.github/workflows/` need not be a workflow yet — a
        # half-written one has no `jobs:` — and this reader crashing the suite on it would
        # be an unrelated failure standing where a pin check should be.
        for name, job in (workflow.get("jobs") or {}).items():
            grant = the_grant_that_can_publish(workflow, job)
            if grant is None:
                continue
            found.extend(
                _reached_from(root, index, path.name, name, grant, _every(job, "uses")))
    return found


def _reached_from(root: Path, index: set[str], workflow: str, job: str, grant: str,
                  refs: list) -> list[Beside]:
    """The remote actions these references reach, through this repository's own files.

    One hop per local reference and as many hops as there are local references, which is
    the same walk `closure` describes and the same one GitHub takes: a local `uses:`
    resolves to a tracked `action.y*ml`, or to a reusable workflow under
    `.github/workflows/`, and both may name further references of their own.

    A local reference to a file this repository does not track contributes nothing here —
    deliberately, and not silently: `test_every_local_action_is_a_file_committed_to_this_
    repository` already refuses that ref by name, so swallowing it a second time here
    would only produce a second complaint about the same line.

    A local reference to a **reusable workflow** is read whole rather than job by job, and
    that over-collects on purpose. `workflow_call` hands the called workflow the caller
    job's permissions, which it can reduce but not exceed, so every job in it may be
    holding the identity — and this reader would be guessing which. Asking for a record of
    one action too many is a question somebody answers; missing one is the whole of #473.
    """
    out: list[Beside] = []
    queue = [_unquote(r) for r in refs]
    walked: set[str] = set()
    while queue:
        ref = queue.pop()
        if not is_local(ref):
            action, _, sha = ref.rpartition("@")
            out.append(Beside(workflow, job, action, sha, grant))
            continue
        target = local_target(ref)
        # Two refusals, deliberately on two lines: they are two different facts, and the
        # deletion sweep can only charge them separately when they are written separately.
        if target is None:
            continue                       # a path out of the tree names nothing in it
        if target in walked:
            continue                       # a cycle ends here rather than spinning
        walked.add(target)
        for rel in _action_files(target, index):
            queue.extend(_unquote(r.ref)
                         for r in scan_text((root / rel).read_text()) if r.key == "uses")
    return out


def publish_closure(path: Path = PUBLISH_CLOSURE) -> dict:
    """The record, as data. Read with `json` and never with this file's YAML reader: the
    record is not a workflow, and the one thing that must not happen to it is being read
    as one."""
    return json.loads(path.read_text())


class TheHopIntoAPinnedActionIsRecordedRatherThanChecked(unittest.TestCase):
    """The boundary the docstring states, given the one tooth it can honestly have (#473).

    `uses: owner/action@<sha>` pins that action's tree. It does not pin what that tree then
    names: a composite action has its own `uses:` lines, a Docker action builds from a
    `Dockerfile` whose `FROM` is a tag its publisher rewrites. Both run in the job holding
    `id-token: write`, both are files in somebody else's repository, and no test in this
    suite makes a network call. **So this cannot be checked here, and nothing in this class
    pretends to check it.**

    What it checks is that the RECORD of that reading names the same code the workflow
    runs. `.github/publish-closure.json` says which action was read, at which SHA, what its
    `runs:` block said and what it named; these tests say the SHA in the record is the SHA
    in the workflow, that nothing runs beside the identity without an entry, that no entry
    outlives the pin it was written for, and that the record's own `pinned` verdicts agree
    with the very predicate this file applies to charter's own refs. When a pin moves the
    record is stale, and this goes red **at the moment somebody is already reading that
    pin**, with the command to re-read the tree in the failure message.

    **That is a prompt, not a proof.** Nothing offline can tell whether the person who
    bumped the SHA re-read the tree or merely retyped the record, and the record says so
    about itself. What it removes is the failure that actually happened here rather than a
    hypothetical one: the reading published on #473 on 2026-08-28 named
    `actions/download-artifact@d3f86a1 # v4.3.0`; commit 032a061 moved that pin the next
    day; `runs.using` moved with it, node20 to node24; and nothing anywhere asked anybody
    to look. Six days of documented boundary, wrong within twenty-seven hours of being
    re-verified on purpose.

    **Why `id-token: write` and not every write grant** is argued in the record's own
    `scope` block, and it is the same crying-wolf argument that kept option (2) of #473 —
    a scheduled network job — unbuilt: a prompt that fires on every `actions/checkout`
    bump is a prompt that gets waved through, and it takes whatever else it would have
    caught with it (#171, #55).
    """

    def test_there_is_a_job_holding_the_publishing_identity_for_this_to_be_about(self):
        """A reader that found no privileged job would pass every test below it, and a
        record with nothing in it would pass most of them."""
        self.assertIn(
            ("release.yml", "publish"),
            {(b.workflow, b.job) for b in beside_the_publishing_identity()},
            "no remote action was found in a job that can publish charter — either the "
            "grant moved, or the permissions reader has gone blind, and every assertion "
            "below is vacuous either way")
        self.assertTrue(
            publish_closure()["reviewed"],
            f"{PUBLISH_CLOSURE.name} records no reading at all, which is not the same "
            f"claim as `there was no hop to read`")

    def test_every_action_beside_the_identity_is_recorded_at_the_sha_it_is_pinned_to(self):
        """The whole point. Bump a pin in `publish` without re-reading the tree it now
        names, and the record is a description of code nothing runs."""
        entries = {e["uses"]: e for e in publish_closure()["reviewed"]}
        for b in beside_the_publishing_identity():
            with self.subTest(workflow=b.workflow, job=b.job, action=b.action):
                entry = entries.get(b.action)
                self.assertIsNotNone(
                    entry,
                    f"`{b.action}` runs in `{b.workflow}`'s `{b.job}` job, which can "
                    f"publish charter — {b.grant} — and nothing in "
                    f"{PUBLISH_CLOSURE.name} says what its own tree names. Read it at the "
                    f"SHA it is pinned to and add an entry: a composite action's `uses:` "
                    f"lines, a Docker action's `image:` or its `Dockerfile` `FROM`, "
                    f"nothing at all for a JavaScript one. That reading needs the "
                    f"network, which is why no test here can do it for you.")
                self.assertEqual(
                    entry["sha"], b.sha,
                    f"`{b.action}` is recorded at {entry['sha']} ({entry['tag']}), and "
                    f"`{b.workflow}` now pins {b.sha}. The record describes a tree nothing "
                    f"runs any more. Re-read the new one:\n\n    "
                    f"{entry['reread'].replace(entry['sha'], b.sha)}\n\n"
                    f"then set `sha`, `tag`, `runs`, `reread` and `transitive` from what "
                    f"comes back. Retyping the SHA without reading the tree passes this "
                    f"test, and is the one thing it cannot catch.")

    def test_the_record_keeps_no_entry_for_a_hop_nothing_takes_any_more(self):
        """The other direction, and it is not decoration: a record free to accumulate
        entries reads as more thorough the longer it goes untended, and an entry for an
        action this repository has dropped is a reading nobody has any reason to refresh —
        so it is exactly the entry that will still be there, and still believed, when
        somebody adds the action back at a different SHA."""
        live = {(b.action, b.sha) for b in beside_the_publishing_identity()}
        for entry in publish_closure()["reviewed"]:
            with self.subTest(action=entry["uses"]):
                self.assertIn(
                    (entry["uses"], entry["sha"]), live,
                    f"{PUBLISH_CLOSURE.name} records `{entry['uses']}@{entry['sha']}` and "
                    f"no job that can publish charter runs it. Delete the entry, or put "
                    f"back the pin it was written for.")

    def test_each_entry_says_what_was_read_and_how_to_read_it_again(self):
        """Two SHAs and a verdict would be a record nobody can check or refresh. The
        `reread` command has to name the entry's own SHA, which is what catches the
        half-update: a bumped `sha` beside a command that still fetches the old tree is
        a record claiming to have read something it did not.

        `.strip()` here — and in the two assertions after it — survives the deletion sweep
        as `.lstrip()`, and that is a genuine equivalent rather than a gap. A string is
        all-whitespace exactly when its `lstrip` is empty and exactly when its `strip` is,
        so inside `assertTrue` the two cannot be told apart by any input at all. The call
        still earns its place: without it a record whose `tag` is `"  "` would pass.
        """
        for entry in publish_closure()["reviewed"]:
            with self.subTest(action=entry["uses"]):
                self.assertTrue(
                    _SHA.match(entry["sha"]),
                    f"`{entry['uses']}` is recorded at {entry['sha']!r}, which is not a "
                    f"full commit SHA — the record has to name a content address for the "
                    f"same reason the workflow does")
                self.assertTrue(entry["tag"].strip(),
                                f"`{entry['uses']}` is recorded at a SHA with no version "
                                f"beside it, so nobody can tell how stale the reading is")
                self.assertTrue(entry["runs"].strip(),
                                f"`{entry['uses']}` has no `runs:` recorded, and `runs:` "
                                f"is what decides whether there is a hop at all")
                self.assertIn(
                    entry["sha"], entry["reread"],
                    f"`{entry['uses']}`'s `reread` command does not name the SHA the "
                    f"entry claims to have read, so running it would read a different "
                    f"tree than the one recorded")

    def test_the_records_own_verdicts_are_judged_by_the_rule_this_file_already_applies(self):
        """The reference is somebody else's; the claim about it is this repository's, and
        that claim is checkable offline. `immutable` is the same predicate that judges
        charter's own refs, so a record calling `docker://python:3.13-slim` a pin
        disagrees with the rule the file is built on — and so does one calling a full
        commit SHA movable, which inflates the exposure instead of hiding it. Both
        directions, because a record that overstates is as unreadable as one that lies."""
        for entry in publish_closure()["reviewed"]:
            for hop in entry["transitive"]:
                with self.subTest(action=entry["uses"], ref=hop["ref"]):
                    self.assertTrue(
                        hop["note"].strip(),
                        f"`{hop['ref']}` is recorded under `{entry['uses']}` with no note "
                        f"— a bare list of refs is a count, and this file reports "
                        f"findings rather than counts")
                    fixed = immutable(hop["ref"]) or is_local(hop["ref"])
                    if hop["pinned"]:
                        self.assertTrue(
                            fixed,
                            f"the record calls `{hop['ref']}` pinned, and `immutable` — "
                            f"the predicate this file uses on charter's own refs — says "
                            f"it is a promise its owner can move")
                    else:
                        self.assertFalse(
                            fixed,
                            f"the record calls `{hop['ref']}` movable, and it is a "
                            f"content address by this file's own rule. Overstating the "
                            f"residual exposure is how a real one stops being read.")

    def test_the_record_is_a_tracked_file_this_suite_does_not_read_as_a_workflow(self):
        """Tracked, because an untracked record is one a working tree rewrites between the
        reading and the release. And NOT a seed file, because it names a movable reference
        on purpose: rename it to `.yml` under `.github/` and the rule above would read
        `docker://python:3.13-slim` as a ref charter had written and refuse it — correctly,
        unanswerably, and about the wrong repository's file."""
        self.assertIn(
            PUBLISH_CLOSURE.relative_to(REPO).as_posix(), tracked(),
            "the closure record is not committed, so 'it moves only with a commit here' "
            "is false of it")
        self.assertNotIn(
            PUBLISH_CLOSURE, seed_files(),
            "the closure record is being read as a workflow. It names refs charter does "
            "not write and cannot pin; judging them by the rule above is a refusal aimed "
            "at somebody else's repository, and there is no key that lifts one (#370).")

    def test_the_record_states_its_own_reach(self):
        """Shape, not content, and said plainly rather than dressed up: this holds that
        the `about` and `scope` blocks exist and are not empty. They are where the record
        says it is a reading and not a verification, and which jobs it covers — and a
        guard whose reach is not written down beside it gets read as a wider guard than it
        is, which is #473 itself one level up."""
        record = publish_closure()
        self.assertTrue("".join(record["about"]).strip(),
                        "the record does not say what it is, or that it is not a check")
        self.assertTrue("".join(record["scope"]).strip(),
                        "the record does not say which jobs it covers")


class TheJobThisIsAboutIsTheOneThatCanPublish(unittest.TestCase):
    """`the_grant_that_can_publish` on the spellings a `grep id-token` gets wrong.

    Both directions, and the withheld cases are the load-bearing half: a reader that said
    "privileged" about everything would satisfy every assertion in the class above by
    demanding a record entry for `actions/checkout`, and a reader that said it about
    nothing would satisfy them by demanding none at all.

    The granted cases assert **which** grant was found and not merely that one was, since
    the three are three different sentences and one of them is an admission rather than a
    finding. A boolean here is how the first draft of this told a reader that a job with
    no declared permissions "holds `id-token: write`" — the guard-overstates-its-reach
    defect, inside the fix for the guard-overstates-its-reach defect.
    """

    SHA = "a" * 40

    def _grants(self, text: str) -> dict[str, str | None]:
        workflow = load(text)
        return {name: the_grant_that_can_publish(workflow, job)
                for name, job in workflow["jobs"].items()}

    GRANTED = [
        ("a job that asks for it",
         "permissions:\n  contents: read\njobs:\n  publish:\n    permissions:\n"
         "      id-token: write\n    steps:\n      - uses: owner/act@" + SHA + "\n",
         "`id-token: write`"),
        ("a workflow grant, inherited by a job that declares nothing",
         "permissions:\n  id-token: write\njobs:\n  publish:\n    steps:\n"
         "      - uses: owner/act@" + SHA + "\n",
         "`id-token: write`"),
        ("write-all, which is every scope including this one",
         "permissions: write-all\njobs:\n  publish:\n    steps:\n"
         "      - uses: owner/act@" + SHA + "\n",
         "write-all"),
        ("no permissions declared anywhere — the repository default, which is a setting "
         "in a web UI and not a byte in this tree",
         "jobs:\n  publish:\n    steps:\n      - uses: owner/act@" + SHA + "\n",
         "cannot see the identity WITHHELD"),
    ]

    WITHHELD = [
        ("a job block, which REPLACES the workflow's rather than adding to it",
         "permissions:\n  id-token: write\njobs:\n  publish:\n    permissions:\n"
         "      contents: read\n    steps:\n      - uses: owner/act@" + SHA + "\n"),
        ("read-all",
         "permissions: read-all\njobs:\n  publish:\n    steps:\n"
         "      - uses: owner/act@" + SHA + "\n"),
        ("id-token: read",
         "jobs:\n  publish:\n    permissions:\n      id-token: read\n    steps:\n"
         "      - uses: owner/act@" + SHA + "\n"),
        ("id-token: none",
         "jobs:\n  publish:\n    permissions:\n      id-token: none\n    steps:\n"
         "      - uses: owner/act@" + SHA + "\n"),
        ("a write grant that is not this one",
         "jobs:\n  publish:\n    permissions:\n      contents: write\n    steps:\n"
         "      - uses: owner/act@" + SHA + "\n"),
    ]

    REFUSED = [
        ("a `permissions:` scalar nobody taught this reader",
         "permissions: bananas\njobs:\n  publish:\n    steps:\n"
         "      - uses: owner/act@" + SHA + "\n",
         "a `permissions:` scalar this reader does not know"),
        ("an `id-token:` value nobody taught this reader",
         "jobs:\n  publish:\n    permissions:\n      id-token: maybe\n    steps:\n"
         "      - uses: owner/act@" + SHA + "\n",
         "an `id-token:` value this reader does not know"),
        ("a `permissions:` sequence, which is not a permission set at all",
         "permissions:\n  - id-token\njobs:\n  publish:\n    steps:\n"
         "      - uses: owner/act@" + SHA + "\n",
         "neither a mapping nor a scalar"),
        ("a `permissions:` key with nothing under it, which is neither a grant nor a "
         "silence and must not be read as the second",
         "jobs:\n  publish:\n    permissions:\n    steps:\n"
         "      - uses: owner/act@" + SHA + "\n",
         "a `permissions:` key with no scopes under it"),
        ("the same empty key at the workflow level",
         "permissions:\njobs:\n  publish:\n    steps:\n"
         "      - uses: owner/act@" + SHA + "\n",
         "a `permissions:` key with no scopes under it"),
    ]

    def test_a_job_that_can_publish_is_recognised_and_says_which_grant_made_it_one(self):
        for name, text, says in self.GRANTED:
            with self.subTest(case=name):
                grant = self._grants(text)["publish"]
                self.assertIsNotNone(grant, "a job that can publish charter read as one "
                                            "that cannot")
                self.assertIn(says, grant,
                              "the job was recognised, and for a different reason than "
                              "the one this case exists to exercise — which is the whole "
                              "of what the failure message will tell somebody")

    def test_a_job_that_cannot_publish_is_not_dragged_in(self):
        for name, text in self.WITHHELD:
            with self.subTest(case=name):
                self.assertIsNone(self._grants(text)["publish"])

    def test_a_permission_set_this_reader_cannot_read_stops_the_suite_by_name(self):
        """Fail-closed, and the message is asserted rather than the exception: three
        different unreadable shapes all raise `Unparsed`, so a test that only checked the
        type would pass while the reader stopped being able to say which one it met."""
        for name, text, says in self.REFUSED:
            with self.subTest(case=name):
                with self.assertRaises(Unparsed) as caught:
                    self._grants(text)
                self.assertIn(says, str(caught.exception))

    def test_only_the_remote_actions_of_a_privileged_job_are_collected(self):
        """The collector, on a tree built to trip every branch of it: an action in an
        unprivileged job beside one in a privileged job, a local reference, and an image
        that is not a `uses:` at all."""
        text = (
            "permissions:\n"
            "  contents: read\n"
            "jobs:\n"
            "  build:\n"
            "    steps:\n"
            "      - uses: owner/unprivileged@" + "b" * 40 + "\n"
            "  publish:\n"
            "    permissions:\n"
            "      id-token: write\n"
            "    container: ghcr.io/x@sha256:" + "c" * 64 + "\n"
            "    steps:\n"
            "      - uses: owner/act@" + self.SHA + "\n"
            "      - uses: owner/act/sub@" + self.SHA + "\n"
            "      - uses: ./tools/local\n")
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(os.path.realpath(raw))
            (tmp / ".github" / "workflows").mkdir(parents=True)
            (tmp / ".github" / "workflows" / "release.yml").write_text(text)
            found = beside_the_publishing_identity(tmp)
        self.assertEqual(
            {(b.job, b.action, b.sha) for b in found},
            {("publish", "owner/act", self.SHA), ("publish", "owner/act/sub", self.SHA)})
        self.assertEqual({b.workflow for b in found}, {"release.yml"})
        self.assertEqual({b.grant for b in found}, {f"`{_IDENTITY}: write`"},
                         "the reason the job counted did not reach the finding, so the "
                         "failure message cannot say why this action needs a record")

    def _tree(self, tmp: Path, files: dict[str, str]) -> set[str]:
        for rel, text in files.items():
            path = tmp / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        return set(files)

    def test_a_remote_action_reached_through_a_local_one_is_collected_too(self):
        """A composite action runs INSIDE the calling job with the calling job's token, so
        every remote action it names stands beside `id-token: write` exactly as the job's
        own steps do. A collector that stopped at the workflow file would report the
        closure of a FILE and call it the closure of a JOB — #473's own defect, one level
        in. The cycle back to the first action is here because a walk that can be sent
        round one is a walk that hangs the suite rather than failing it.

        The **image** in the deeper action is here for the other half: this walk follows
        `uses:` and nothing else, and a `runs.image` reached through a local action is a
        reference the rule above already holds to a digest — collecting it would ask for a
        reading of an action that is not one. The **doubly-`@`'d** ref is here for the
        third: the split has to take the LAST `@`, because that is the end `immutable`
        judges, and a collector splitting at a different one would key the record on a
        name the rule above never saw."""
        far = "d" * 40
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(os.path.realpath(raw))
            index = self._tree(tmp, {
                ".github/workflows/release.yml":
                    "jobs:\n  publish:\n    permissions:\n      id-token: write\n"
                    "    steps:\n      - uses: ./.github/actions/inner\n",
                ".github/actions/inner/action.yml":
                    "runs:\n  using: composite\n  steps:\n"
                    "    - uses: owner/reached@" + self.SHA + "\n"
                    "    - uses: owner/odd@branch@" + far + "\n"
                    "    - uses: ./.github/actions/deeper\n",
                ".github/actions/deeper/action.yml":
                    "runs:\n  using: docker\n"
                    "  image: docker://ghcr.io/x@sha256:" + "e" * 64 + "\n"
                    "  steps:\n"
                    "    - uses: owner/deeper@" + far + "\n"
                    "    - uses: ./.github/actions/inner\n",
            })
            found = beside_the_publishing_identity(tmp, index)
        self.assertEqual(
            {(b.job, b.action, b.sha) for b in found},
            {("publish", "owner/reached", self.SHA),
             ("publish", "owner/odd@branch", far),
             ("publish", "owner/deeper", far)},
            "this is not the closure of that job. A remote action reached through a local "
            "composite action has to be in it — nothing would ask for a reading of its "
            "tree otherwise; an image must not be, because a digest is already a content "
            "address with no hop behind it; and a ref splits at its LAST `@`, the end "
            "`immutable` reads.")

    def test_a_local_reference_this_repository_does_not_track_adds_nothing_here(self):
        """It is not swallowed, it is somebody else's complaint: `uses: ./nope` is already
        refused by name for not being a file committed here, and a second finding about
        the same line would be this collector inventing a reason of its own.

        The tracked step beside them is what keeps this from passing for the wrong reason.
        Its first version asserted an empty result, which a collector that read nothing at
        all — a mistyped path, a glob that stopped matching — satisfies just as well. The
        deletion sweep found exactly that: the workflow's filename could be replaced with
        gibberish and the test stayed green. So the job also holds one ref that MUST come
        back, and the assertion is the whole set rather than its emptiness."""
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(os.path.realpath(raw))
            index = self._tree(tmp, {
                ".github/workflows/release.yml":
                    "jobs:\n  publish:\n    permissions:\n      id-token: write\n"
                    "    steps:\n      - uses: ./node_modules/probe\n"
                    "      - uses: ../outside/the/tree\n"
                    "      - uses: owner/tracked@" + self.SHA + "\n",
            })
            (tmp / "node_modules" / "probe").mkdir(parents=True)
            (tmp / "node_modules" / "probe" / "action.yml").write_text(
                "runs:\n  using: composite\n  steps:\n"
                "    - uses: owner/untracked@" + self.SHA + "\n")
            found = beside_the_publishing_identity(tmp, index)
        self.assertEqual(
            {(b.action, b.sha) for b in found}, {("owner/tracked", self.SHA)},
            "either an untracked local action leaked a remote ref into this closure, or "
            "the collector read nothing at all — and an empty result cannot tell those "
            "two apart, which is what the tracked step is here to stop")

    def test_a_file_under_workflows_that_is_not_a_workflow_yet_is_not_a_crash(self):
        """A half-written file under `.github/workflows/` has no `jobs:`, and this reader
        raising on it would put an unrelated `AttributeError` exactly where a pin check
        should be — a red suite that says nothing about pinning, on a branch that has not
        finished writing its workflow. The job beside it still has to come back, so this
        is not "reads nothing and survives"."""
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(os.path.realpath(raw))
            index = self._tree(tmp, {
                ".github/workflows/half-written.yml": "name: not finished\non:\n  push:\n",
                ".github/workflows/release.yml":
                    "jobs:\n  publish:\n    permissions:\n      id-token: write\n"
                    "    steps:\n      - uses: owner/act@" + self.SHA + "\n",
            })
            found = beside_the_publishing_identity(tmp, index)
        self.assertEqual({(b.workflow, b.action) for b in found},
                         {("release.yml", "owner/act")})


# ------------------------------------------ what can speak for a run that never happened

def requirable(workflow: object) -> dict[str, str]:
    """Job key -> the check-run name it publishes, for the jobs that can be *required*.

    Branch protection matches a required status check by NAME and by nothing else, so a job
    has to answer two questions to be one: what name does it publish, and does that name
    hold still. A job with no `name:` publishes its key; one with a `name:` publishes that.

    A name carrying `${{ }}` publishes a different string on every branch. Requiring it
    would protect a branch against a string that never appears again — and a required
    context nothing ever reports does not pass, it blocks forever. Two jobs in `sweep.yml`
    are deliberately in that class: `verdict`, whose name IS the answer (#630), and the
    sharded `sweep` job, whose name counts shards. Neither is a mistake and neither is a
    candidate.

    A job with no body at all is a workflow somebody is still writing, and it names no
    check yet — the same half-written case `beside_the_publishing_identity` handles rather
    than crashing on.
    """
    out: dict[str, str] = {}
    for key, job in workflow["jobs"].items():
        if not isinstance(job, dict):
            continue
        name = job.get("name", key)
        if "${{" not in name:
            out[key] = name
    return out


class TheMatrixRunsOncePerPullRequestAndOnceOnMain(unittest.TestCase):
    """`test.yml`'s triggers, and the sentence in `sweep.yml`'s header that used to excuse
    them.

    That header argues at length that `push:` does not belong on the SWEEP, and every word
    of that still stands — the two events sweep different trees, and a required check
    satisfied by a push-scoped run stops proving the pull-request-scoped sweep happened.
    One bullet of the argument was a concession rather than part of it: *"That workflow
    carries both triggers, and every pull request there runs its matrix twice — once on the
    head sha, once on the merge commit. Four cheap jobs, twice, is affordable."*

    Affordable in what. The repository is public, so the runner minutes were never the
    price — the wall clock is, and a duplicated matrix is not cheap in the only currency
    being spent. Both runs test the same four interpreters, and the merge-commit run is the
    one branch protection reads. So `push:` here is scoped to `main`, which is the branch
    where a push is not also a pull request, and a branch with an open PR runs the matrix
    once.

    Three things have to hold together for that to be safe, and they are asserted rather
    than argued:

    * The four required contexts — `test (3.11)` … `test (3.14)` — are reported by a job
      no trigger-shaped condition gates, so `pull_request` still produces every one of
      them. A required context nothing reports blocks forever.
    * `dev-install` asks for `refs/heads/main` by hand, and a `push:` narrowed to some
      OTHER branch would leave that condition permanently false: a job that silently stops
      running is the failure this whole file is about. So the branch the filter names and
      the ref the condition demands are checked against each other.
    * `pull_request` and `workflow_dispatch` stay. Narrowing the push trigger must not
      become "the matrix runs on main only".
    """

    def workflow(self) -> dict:
        return load((GITHUB / "workflows" / "test.yml").read_text())

    def test_a_branch_with_an_open_pull_request_runs_the_matrix_once(self):
        on = self.workflow()["on"]
        self.assertEqual(set(on), {"push", "pull_request", "workflow_dispatch"})
        self.assertEqual(on["push"], {"branches": ["main"]},
                         "an unfiltered `push:` runs this matrix a second time on every "
                         "pull request, on the head sha, and nothing reads that run")
        self.assertIsNone(on["pull_request"],
                          "the merge-commit run is the one branch protection reads")

    def test_the_contexts_branch_protection_requires_are_reported_on_pull_requests(self):
        """`test (3.11)`…`test (3.14)` come from the matrix job, and it carries no `if:`.

        A condition here mentioning `github.event_name` would be the same defect from the
        other side: the check would stop appearing on the trigger that still needs it, and
        a required context that never reports does not pass — it blocks.
        """
        test = self.workflow()["jobs"]["test"]
        self.assertNotIn("if", test)
        self.assertEqual(test["strategy"]["matrix"]["python-version"],
                         ["3.11", "3.12", "3.13", "3.14"])


class TheSweepsAbsenceIsSomethingOnlyARequiredCheckCanSay(unittest.TestCase):
    """#646 and #561 are one defect seen from two heights, and this holds the code half.

    #561: *a check that never ran reports CLEAN*. #646: *a branch with no gate run looks
    identical to one whose gate found nothing*. Neither can be answered from inside the
    workflow, because every line of a workflow is code that runs only on the runs that
    already happen — so the answer is a required status check, which is a repository
    setting and not a commit.

    What IS in this repository's gift is keeping that setting meaningful, and there are
    exactly two ways a commit can quietly hollow it out. Add `push:` to `sweep.yml` and the
    required check can be satisfied by a run that swept the branch tip instead of the merge
    result — the hole reopened one level below the fix. Or rename the job that check names,
    or take away the `always()` that makes it report at all.

    So the trigger set and the two properties of `collect` are pinned here, and `requirable`
    is exercised in both directions: a reader that called everything requirable would make
    the `verdict` assertion vacuous, and one that called nothing requirable would satisfy
    the `collect` assertion by finding no jobs at all.
    """

    def sweep(self) -> dict:
        return load((GITHUB / "workflows" / "sweep.yml").read_text())

    NAMES = [
        ("a job with no name of its own publishes its key",
         "jobs:\n  collect:\n    runs-on: ubuntu-latest\n", {"collect": "collect"}),
        ("a job with a fixed name publishes that name",
         'jobs:\n  c:\n    name: Add up what the shards found\n', {"c": "Add up what"
                                                                   " the shards found"}),
        ("a name that interpolates an output is not a context anything can require",
         'jobs:\n  verdict:\n    name: "${{ needs.collect.outputs.headline }}"\n', {}),
        ("a name that interpolates a matrix value is not one either",
         "jobs:\n  sweep:\n    name: Sweep shard ${{ matrix.shard }} of 8\n", {}),
        ("the fixed names survive beside the moving ones",
         "jobs:\n  plan:\n    name: Size the sweep\n  v:\n    name: ${{ x }}\n",
         {"plan": "Size the sweep"}),
        ("a job nobody has finished writing names no check yet",
         "jobs:\n  half:\n", {}),
    ]

    def test_a_job_names_a_required_context_only_when_that_name_holds_still(self):
        for label, text, expected in self.NAMES:
            with self.subTest(label):
                self.assertEqual(requirable(load(text)), expected, label)

    def test_the_sweep_runs_on_the_two_triggers_it_can_answer_for(self):
        """The assertion the header of `sweep.yml` argues at length, and #646 asks to
        overturn. `pull_request` is the only trigger that hands this gate a merge commit
        and a base sha — the tree that will land, which is what "scoped to added lines"
        means. `workflow_dispatch` is a human asking, once.

        A `push:` here would let the required `collect` check be reported by a run that
        swept the branch TIP against the merge-base instead, under the same name — so the
        check's presence would stop proving that the pull-request-scoped sweep ever ran.
        Overturning this is a decision; it is not a line somebody adds in passing.
        """
        self.assertEqual(set(self.sweep()["on"]), {"pull_request", "workflow_dispatch"})

    def test_the_context_to_require_is_the_job_that_reports_whatever_the_shards_did(self):
        """`collect` is the one job in this workflow fit to be a required check, and both
        halves of that were measured on real runs rather than reasoned from the file.

        Its name is fixed, so branch protection can name it. And it runs under `always()`,
        which is why it reports at all when the shards die (#626) and when a newer push
        cancels the run (#654): across twelve consecutive runs it concluded `success` every
        time, including the two whose `plan` job concluded `cancelled`. That is what makes
        it absent EXACTLY when the workflow did not fire, which is the whole property #646
        needs — a `cancelled` required context blocks, so requiring `Size the sweep`
        instead would block every pull request that got a second push.
        """
        jobs = self.sweep()["jobs"]
        self.assertEqual(requirable(self.sweep())["collect"],
                         "Add up what the shards found")
        self.assertEqual(jobs["collect"]["if"], "always()")

    def test_the_job_whose_name_is_the_answer_can_never_be_a_required_check(self):
        """The `verdict` job says this about itself already; this is that comment with
        teeth. Its name is `no survivors` on one branch and `114 survivors, 1 not measured`
        on the next, so requiring it would demand a context that never reports twice — and
        a required context nothing reports blocks forever rather than passing.
        """
        names = requirable(self.sweep())
        self.assertNotIn("verdict", names)
        self.assertNotIn("sweep", names)


class TheSweepCheckSaysItIsAWaitAndNotAFailureRisk(unittest.TestCase):
    """#988: the `verdict` step's own body said "This check reports and blocks nothing".

    True about the verdict: no `tools/sweep.py` step in `sweep.yml` passes `--enforce`, so
    survivors never fail the run. False about merging, which is what the sentence is read
    for: the base branch policy requires every check to COMPLETE. Measured on PR #982 — with
    `Sweep shard 1 of 1` still running and every other check green, the merge was refused,
    and it went through once the shard finished, verdict unchanged.

    So the two facts are stated apart, and the first is pinned to the file that makes it
    true: the day a step gains `--enforce`, "never fails on survivors" goes red here rather
    than going on being printed.
    """

    @staticmethod
    def _code(step: dict) -> str:
        """What a step's shell RUNS: comment lines dropped, continuations joined. Both
        steps this reads carry a comment that quotes what is not so — `collect`'s names
        `--enforce` to say it is absent, `verdict`'s quotes the sentence #988 retired."""
        code = [ln for ln in str(step.get("run", "")).splitlines()
                if not ln.strip().startswith("#")]
        return "\n".join(code).replace("\\\n", " ")

    def _jobs(self) -> dict:
        return load((GITHUB / "workflows" / "sweep.yml").read_text())["jobs"]

    def test_the_check_says_it_never_fails_on_survivors_only_while_nothing_enforces(self):
        jobs = self._jobs()
        invocations = [ln for job in jobs.values() for step in job.get("steps") or []
                       for ln in self._code(step).splitlines() if "tools/sweep.py" in ln]
        self.assertTrue(any("--verdict" in ln for ln in invocations),
                        "found no `sweep.py --verdict` step, so nothing here is measured")
        enforced = any("--enforce" in ln for ln in invocations)
        said = self._code(jobs["verdict"]["steps"][0])
        self.assertEqual("never fails on survivors" in said, not enforced, said)

    def test_the_check_says_it_must_complete_before_a_pull_request_merges(self):
        said = self._code(self._jobs()["verdict"]["steps"][0])
        self.assertIn("must COMPLETE before the branch policy will let a pull request merge",
                      said)
        self.assertNotIn("blocks nothing", said)


if __name__ == "__main__":
    unittest.main()
