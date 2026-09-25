"""Is a newer charter published? — no longer asked, because 0.62.2 is the last release.

charter-cp is no longer maintained: charter is now a desktop app (:data:`END_OF_LIFE`).
Until 0.62.2 this module ran a cached, detached background check against PyPI and, on the
dev channel, against the head of ``main`` on the GitHub repository. That repository was
renamed and its ``main`` no longer holds this package, so the check is switched off:
:func:`maybe_spawn` starts nothing, and :func:`newer_than` and :func:`newer_head` never
report anything newer.

What stays is what other commands still read: :func:`version_key`, the cache
:func:`load` returns, and :func:`fetch_and_store`, the one PyPI GET that `charter version
bump` makes when it is run.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import NamedTuple

from . import config

#: PyPI distribution name. The *command* is `charter`; the *package* is `charter-cp`
#: (PyPI would not allow `charter`), so the metadata lives under the latter.
DIST = "charter-cp"
_URL = f"https://pypi.org/pypi/{DIST}/json"

#: Where charter-cp's source and history live now. **Not polled, and never installed
#: from.** Until 0.62.2 the dev channel read this repository's ``main`` head and
#: `charter update` installed ``git+https://github.com/diazoxide/charter@main``. The
#: repository was renamed ``diazoxide/charter-plane`` and its ``main`` is a control plane
#: with no Python package in it, and ``diazoxide/charter`` is now the desktop app. So
#: nothing here reaches the network for it: the one reader left is `news._entry_url`,
#: which links a release's notes to the tag that shipped them.
DEV_REPO = "diazoxide/charter-plane"
DEV_BRANCH = "main"

#: What every surface says about charter-cp's end of life, in one place. 0.62.2 is the last
#: release: `charter update` installs nothing and the update check reports nothing newer.
END_OF_LIFE = ("charter-cp is no longer maintained — charter is now a desktop app: "
               "https://github.com/diazoxide/charter/releases")

NET_TIMEOUT = 5           # `version bump` waits on this GET, so never hang around


#: Said wherever a pin and an install disagree, and nowhere else.
#:
#: The pin is per control plane; the binary is one machine-global install. Two planes
#: pinning different versions cannot both be satisfied, and `version sync` does not fix
#: that — it picks a winner and puts the other plane into drift, which is how a plane that
#: nobody touched went from "in sync" to "drift" because of work done somewhere else.
#: charter is a control plane, not a version manager, so it says this rather than growing a
#: shim to resolve the pinned version per plane.
SHARED_INSTALL_NOTE = (
    "the `charter` binary is ONE machine-global install shared by every control plane on "
    "this machine, so syncing here can put another plane into drift (see: uv tool list). "
    "The per-plane version is the PLUGIN's — see `charter version`"
)

#: The per-project fix, and the whole of what #127 asked for.
#:
#: A Claude Code plugin is installed **per project**: `installed_plugins.json` records an
#: `installPath` into `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`, and that
#: cache holds many versions side by side. Two projects on one machine were observed serving
#: two different charter versions at once — exactly what #127 reported as impossible.
#:
#: So this command is the one that honours a pin: it moves THIS project and no other, where
#: `version sync` conforms a binary every plane shares.
PLUGIN_SYNC_CMD = "claude plugin update charter@charter"


def plugin_version_here() -> str | None:
    """The version of the charter PLUGIN serving this project, or ``None``.

    ``$CLAUDE_PLUGIN_ROOT`` is a **documented** variable that Claude Code sets for the
    plugin's own processes, and it points at the versioned directory this project resolved
    to. That is the whole mechanism: no cache layout is parsed and `installed_plugins.json`
    is never read, because those are Claude Code internals — fine to look at by hand,
    never something to build on. Betting on an internal path is what `bin/edm` did, and it
    broke silently (#197).

    ``None`` outside a plugin process, which is the ordinary case for a `charter` typed in
    a terminal. Callers must say "not visible from here" rather than substituting the
    machine-global CLI's version and calling it this plane's — that conflation is #127.
    """
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not root:
        return None
    try:
        doc = json.loads((Path(root) / ".claude-plugin" / "plugin.json").read_text())
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    v = doc.get("version") if isinstance(doc, dict) else None
    return v.strip() if isinstance(v, str) and v.strip() else None


def _cache_file() -> Path:
    return config.STATE_DIR / "cache" / "update.json"


def load() -> dict:
    try:
        return json.loads(_cache_file().read_text())
    except (OSError, ValueError):
        return {}


#: A version as PEP 440 spells it, from the regular expression in the PEP's Appendix B, and
#: nothing wider. Stdlib, because charter has no runtime dependencies (CONTRIBUTING), so
#: `packaging` is not there to ask.
#:
#: **``re.ASCII``, and a strip of only the six characters PEP 440 names.** Without the flag,
#: ``re.IGNORECASE`` folds Unicode: the KELVIN SIGN is a ``k`` in a local label and a DOTLESS
#: I (U+0131) completes ``preview``. `str.strip()` would also take a trailing U+2028 LINE
#: SEPARATOR off. Each would make a version out of a string no installer accepts as one.
#:
#: The local label is matched and then never read. See :func:`version_key` for why.
_PEP_440 = re.compile(r"""
    v?
    (?:(?P<epoch>[0-9]+)!)?
    (?P<release>[0-9]+(?:\.[0-9]+)*)
    (?:[-_.]?(?P<pre_l>alpha|a|beta|b|preview|pre|c|rc)[-_.]?(?P<pre_n>[0-9]+)?)?
    (?:-(?P<post_n1>[0-9]+)|[-_.]?(?P<post_l>post|rev|r)[-_.]?(?P<post_n2>[0-9]+)?)?
    (?:[-_.]?(?P<dev_l>dev)[-_.]?(?P<dev_n>[0-9]+)?)?
    (?:\+[a-z0-9]+(?:[-_.][a-z0-9]+)*)?
""", re.VERBOSE | re.IGNORECASE | re.ASCII)

#: PEP 440's spellings of the three pre-release phases, in the order the phases come.
_PRE_PHASE = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "c": 2, "pre": 2, "preview": 2, "rc": 2}

#: What every string that is not a version keys as. Below every version, because an empty
#: tuple sorts before every tuple with something in it, and equal to every other
#: non-version, so no caller finds a direction between two strings that have none.
_NOT_A_VERSION = ()


def version_key(v: str | None) -> tuple:
    """The key that orders charter versions, as PEP 440 orders them. Every comparison of two
    charter versions goes through this one function, so they cannot disagree.

    It replaced `_parse`, which kept the digits of each dot-separated part and dropped the
    rest. ``0.60.0rc1`` became ``(0, 60, 1)``, so a release candidate compared newer than
    its release, and so did ``a``, ``b`` and ``.dev`` (#1050). Nothing had published a
    pre-release, so no comparison had yet met one. When one did, `charter update`, `version
    bump`, the status line's arrow and SessionStart's pin would all have got it backwards.

    Numbers compare as numbers (0.10.0 is newer than 0.2.0), and trailing zeros do not
    count (``0.60`` is ``0.60.0``). Around a release, PEP 440's order:
    ``X.devN < XaN.devN < XaN < XbN < XrcN < X < X.postN.devN < X.postN``.

    **A local label (``+dev``, ``+local``) does not move a version**, which is not PEP 440's
    order. `channel.build_label` appends one to the SAME wheel's number to say where the
    build came from, not that it is a later release, and `_parse` read ``0.61.0+dev`` as
    ``0.61.0``. No caller is handed a label today, because ``__version__`` carries none; the
    day one is, it gets the answer it always had.

    **Anything that is not a version sorts below every version and ties with every other
    one**, ``None`` included. `_parse` promised that too ("an unparseable version must never
    make the indicator claim an update") and kept it only for strings with no digits in
    them: ``build7`` read as ``(7,)``. Below, so that a cache or a pin holding junk never
    reads as newer, and every caller refuses in the direction it already did.
    """
    m = _PEP_440.fullmatch((v or "").strip(" \t\n\r\f\v"))
    if m is None:
        return _NOT_A_VERSION
    release = [int(n) for n in m["release"].split(".")]
    while release and release[-1] == 0:
        release.pop()
    if m["post_n1"] is not None:
        post = int(m["post_n1"])       # ``1.0-1``, PEP 440's implicit post-release
    elif m["post_l"]:
        post = int(m["post_n2"] or 0)
    else:
        post = None
    if m["pre_l"]:
        pre = (_PRE_PHASE[m["pre_l"].lower()], int(m["pre_n"] or 0))
    elif post is None and m["dev_l"]:
        pre = (-1,)    # ``X.devN`` comes before ``X``'s first alpha, not after its rc
    else:
        pre = (3,)     # a release, or its post-release, comes after every one of its phases
    # Absent sorts below any number for a post-release and above any number for a
    # development release: ``X < X.post0``, and ``X.dev0 < X``.
    return (int(m["epoch"] or 0), tuple(release), pre,
            -1 if post is None else post,
            (0, int(m["dev_n"] or 0)) if m["dev_l"] else (1,))


#: What the dev channel may say about a build that records no commit, and all it may say.
#:
#: `newer_head` nudges such a build on purpose, and its docstring says why. A nudge is not
#: a comparison, though. A cached head of `main` and a wheel's version number are not on
#: one axis, so charter cannot tell which is newer. `charter version` printed the cached
#: PyPI number as "published" and newer, and `report send` said "9d18d55 is out — this may
#: already be fixed", both to a 0.60.0 wheel that already contained `9d18d55` (#937). This
#: sentence claims only what the install record shows. Both surfaces print it, so they
#: cannot drift into describing one state two different ways.
NOT_INSTALLED_FROM_MAIN = (f"this plane follows `{DEV_BRANCH}`, but this build was not "
                           f"installed from a commit of it")


def dev_verdict(head: str) -> str:
    """What a dev plane may say about *head*, the short commit :func:`newer_head` returned.

    One comparison, and never a direction. `charter version` and `charter report send` both
    print this: one state described two different ways on two surfaces is how #937 started,
    and a constant shared by only ONE of the two cases below would leave the other free to
    drift back.

    **The build that has a commit is the case that looks safe and is not.** "``<head>`` is
    out" reads as *``main`` has moved past you*, which charter has not checked. The cache is
    per plane (:data:`config.STATE_DIR`) while the binary is one machine-global install
    (#127), so ``charter update`` run in plane A moves this build to a commit that plane B's
    cache has never heard of. B's cached head is then an ANCESTOR of what is running, and
    "is out" is exactly backwards — the same claim, in the same direction, that #937 is
    about. Unequal is all that was measured, so unequal is all this says.
    """
    from . import channel

    mine = channel.installed_commit()
    if not mine:
        return NOT_INSTALLED_FROM_MAIN
    return (f"this plane follows `{DEV_BRANCH}`, and the head cached for it ({head}) is "
            f"not the commit this build was installed from ({mine[:7]})")


def dev_remedy() -> str:
    """The command that moves THIS charter onto ``main`` — one answer for every surface.

    Beside :func:`dev_verdict`, and for the same reason. Two surfaces that describe one
    state with one sentence and then prescribe two different next steps have the same defect
    one line further down the message — which is exactly how it shipped: `charter version`
    learned about the checkout case and `report send` went on naming the installer.

    ``charter update`` refuses to install over the tree it is running from. It answers "the
    charter you are running IS this tree … it moves by git rather than by an installer:
    charter version", which is `commands.cmd_version` — so a reader working in a charter
    clone was handed a loop between two commands, each naming the other. The gate is the
    question `commands_update` already asks, :func:`channel.running_inside`, and that answer
    names the tree, because a bare ``git pull`` typed somewhere else moves something else.
    """
    from . import channel

    if channel.running_inside(config.ROOT):
        return f"git -C {channel.package_dir().parent} pull"
    return "charter update"


#: What a pin beside the dev channel amounts to, spelled once. The long form and the brief
#: one below both carry it, so a reader who meets the status line's row and then
#: `charter version`'s refusal reads the same words in both.
_TWO_CHARTERS = "two different charters"


class PinBesideDev(NamedTuple):
    """:func:`pin_beside_dev`'s answer, one field per kind of surface."""

    #: The conflict itself, for a surface with room for a sentence.
    conflict: str
    #: The two ways out: toward a pinned release, then toward ``main``.
    ways: tuple[str, str]
    #: The conflict and where both ways out are printed, for a surface with one short row.
    brief: str


def pin_beside_dev() -> PinBesideDev:
    """What every surface says about a pin beside ``[update] channel = "dev"``.

    Beside :func:`dev_remedy`, and for the same reason. The pair is ONE refused state, and it
    had six readers saying five things: session start refused it, `version bump` refused to
    write it, `version sync` installed the pin over a plane following ``main``, `charter
    version` and the status line recommended that sync, and `doctor` called it in sync or
    named a plugin update (#1018). Each caller says what IT did (nothing installed, nothing
    written); what the state is and how to leave it comes from here, so one surface cannot
    grow a third way out or quietly lose one.

    **The brief form is a field of this answer, not a sentence of the status line's.** A
    status line row has no room for both ways out, and a short wording written where it is
    drawn is exactly the second description of one state this function exists to prevent.
    So it is built here, from the same :data:`_TWO_CHARTERS`, and names the command whose
    output carries both ways out.

    **Neither way out is chosen for the operator.** Which charter the plane wants is theirs
    to say, and each is one edit. The second is worded to hold whether or not the plane
    already carries a pin, because `version bump` refuses on a pin-less dev plane too.
    """
    return PinBesideDev(
        conflict=(f"a `[charter] version` pin and `[update] channel = \"dev\"` ask for "
                  f"{_TWO_CHARTERS}"),
        ways=(f"to follow a pinned release, drop `[update] channel = \"dev\"` from the plane's "
              f"`charter.toml`",
              f"to stay on `{DEV_BRANCH}`, keep no `[charter] version` in the plane's "
              f"`charter.toml` and move this charter onto it:  {dev_remedy()}"),
        brief=f"pin + dev channel: {_TWO_CHARTERS} · charter version",
    )


def newer_head() -> str | None:
    """Always ``None``: the dev channel has nothing to follow.

    It compared ``main``'s head on :data:`DEV_REPO` against the commit this build was
    installed from. That ``main`` is now a control plane with no Python package in it, so
    a difference between the two would nudge toward an install that cannot work.
    """
    return None


def newer_than(current: str) -> str | None:
    """Always ``None``: charter-cp 0.62.2 is the last release, on either channel.

    The status line's arrow, `charter version` and `report send` all ask this, and none of
    them may point at an update that `charter update` will no longer install.
    """
    return None


def checked() -> bool:
    """Whether the cache holds the answer :func:`newer_than` compares on this channel.

    ``latest`` on the stable channel, ``head`` on dev, because a PyPI number is not what a
    dev plane is compared against. Without it `newer_than` answers None for "nothing
    newer" and for "nothing known" alike, and `charter version` read both as up to date.
    That was true for the hour before a first background check landed. With
    ``$CHARTER_NO_BACKGROUND_CHECKS`` set it is true for good, so the two are told apart
    here (#945).
    """
    from . import channel

    return bool((load().get("head" if channel.is_dev() else "latest") or "").strip())


def latest_display(installed: str) -> str:
    """The `latest` line, honest about what it is.

    `latest` is a cached reading of PyPI, not a live answer.
    Usually the distinction does not matter. It matters completely in one case: when the
    INSTALLED version is newer than the cached one, the cache is *provably* out of date —
    you cannot be running something PyPI has not published — and printing the lower number
    beside it produced `installed 0.27.2 / latest 0.26.0`, a contradiction on one screen
    that invites the reader to distrust every other line in the output.

    So that case reports the staleness instead of the number. ADR 0013: do not present as
    checked what was not checked.
    """
    latest = (load().get("latest") or "").strip()
    if not latest:
        return "— (not checked: charter-cp 0.62.2 is the last release)"
    try:
        stale = bool(installed) and version_key(latest) < version_key(installed)
    except Exception:
        stale = False
    if stale:
        return f"— (cached {latest} is stale: it predates the {installed} you are running)"
    return latest


def _fetch_latest() -> str | None:
    """One unauthenticated GET of PyPI's JSON metadata endpoint.

    Through `urlopen`'s DEFAULT opener, which honours ``$https_proxy`` — the setting a
    machine behind a proxy already has, and so the one this should keep reading.
    """
    import urllib.request
    try:
        with urllib.request.urlopen(_URL, timeout=NET_TIMEOUT) as r:
            return json.load(r)["info"]["version"]
    except Exception:
        return None


def fetch_and_store() -> str | None:
    """Query PyPI and cache the published version. Returns it, or ``None``.

    `charter version bump` calls this when it is run, and nothing calls it in the
    background any more (see :func:`maybe_spawn`). **The record is merged, not replaced**,
    so a ``head`` an older charter cached is left where it is rather than dropped.
    """
    latest = _fetch_latest()
    if latest is None:
        return None
    record = dict(load())
    record["latest"] = latest
    record["ts"] = time.time()
    try:
        p = _cache_file()
        config.private_mkdir(p.parent)
        config.write_for(p, json.dumps(record))
    except OSError:
        return None
    return latest


def maybe_spawn() -> None:
    """Start no background check. charter-cp 0.62.2 is the last release.

    This used to fork a detached ``charter _version-check`` whenever the cache went stale,
    from the status line's render, the frame's gather and the SessionStart hook. There is
    no newer charter-cp to find and no ``main`` to follow any more (see :data:`DEV_REPO`),
    so all three callers now start nothing and nothing touches the network on their behalf.
    """
    return None
