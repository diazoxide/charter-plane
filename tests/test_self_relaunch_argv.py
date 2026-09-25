"""Every self-relaunch site builds its child argv through `util.self_relaunch_argv`,
never a hand-built `[sys.executable, "-m", "charter", ...]` list of its own — #390.

`python -m charter` prepends the current working directory to `sys.path` before it even
looks for the `charter` package to import (`-m`'s own documented behaviour). Every site
below sets its child's `cwd` to something outside charter's own control — a project
directory, a workspace root, wherever an operator's pane happened to start — and when
THAT directory contains its own `charter/` package (a charter checkout dogfooding
itself, the common case for anyone developing charter), the child imports that tree
instead of the installed one. `-P` (3.11+, `pyproject.toml` already requires it) is
`-m`'s own switch for "don't do that".

`tests/test_self_relaunch_shadowing.py` proves the mechanism end to end against a real
decoy package that genuinely shadows. This module is the fast half: one test per site,
asserting the argv it hands to `Popen`/`split-window` carries `-P` — a passing
end-to-end test on ONE site does not prove the other sites were changed, so each is
pinned separately here.

**And one test that is not per-site at all.** `NoHandBuiltSelfRelaunchArgvAnywhere`
below reads the package's own source and fails on ANY hand-built `-m charter` argv,
wherever it appears. The per-site tests cannot do that job, and the gap is not
hypothetical: `commands_frame.cmd_respawn` — written on a branch cut before this module
existed — landed a brand-new `[sys.executable, "-m", "charter"]` site with a clean merge,
and every test here stayed green because a NEW site is invisible to a list of OLD ones.
A respawn is spawned into the dead pane's OWN cwd, which for anyone dogfooding charter is
a charter checkout, so that site was #390 exactly, on the one path where the panel has
already failed once and there is nothing left to say why.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import charter
from charter import glstate, planegit, update, util
from charter import commands_workspace as cw

from tests._isolation import PersonaIso, make_plane
from tests._planeguard import allow_background_checks

#: The package directory this test process actually imported, not a path guessed from
#: `__file__`'s neighbours — whatever `charter` means to the rest of the suite is what
#: gets read here.
_PKG = Path(charter.__file__).resolve().parent

#: The one function allowed to contain the argv every other site must call it for.
_HELPER = "self_relaunch_argv"


def _hand_built_relaunch_argvs() -> list[tuple[str, int, str]]:
    """Every list/tuple literal in the package that spells out `-m charter` itself.

    An AST walk rather than a text grep, and that is not fastidiousness: a grep is
    defeated by a line break between `"-m",` and `"charter"`, by a different quote
    style, and by any of it appearing in a docstring — this module's own docstring
    would match its own grep. The AST sees the literal `-m` followed by `charter`
    among a sequence's string constants however it is spelled or wrapped, and sees
    nothing at all in prose.

    Returns `(file, line, source)` triples so a failure names the site rather than
    merely asserting one exists.
    """
    found = []
    for path in sorted(_PKG.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.List, ast.Tuple)):
                continue
            words = [e.value for e in node.elts
                     if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            if any(a == "-m" and b == "charter" for a, b in zip(words, words[1:])):
                found.append((str(path.relative_to(_PKG.parent)), node.lineno,
                              ast.unparse(node)))
    return found


class SelfRelaunchArgvShape(unittest.TestCase):
    """The helper itself: charter/util.py."""

    def test_bare_call_is_the_interpreter_plus_dash_p_plus_the_module(self):
        self.assertEqual(util.self_relaunch_argv(),
                         [sys.executable, "-P", "-m", "charter"])

    def test_extra_args_are_appended_after_the_module(self):
        self.assertEqual(
            util.self_relaunch_argv("workspace", "_pushbg"),
            [sys.executable, "-P", "-m", "charter", "workspace", "_pushbg"],
        )


class DetachSelfUsesIt(unittest.TestCase):
    """charter/util.py:288 — `detach_self`, a session-start hook's own background
    refresh (`gl-refresh`, `persona _gc`)."""

    def test_argv_carries_dash_p(self):
        with mock.patch.object(util.subprocess, "Popen") as popen:
            self.assertTrue(util.detach_self(["gl-refresh"]))
        argv = popen.call_args.args[0]
        self.assertEqual(argv, util.self_relaunch_argv("gl-refresh"))


class GlstateMaybeSpawnUsesIt(PersonaIso):
    """charter/glstate.py:226 — `gl-refresh`, spawned from the status line's own render
    path. The quiet one: on any charter checkout this ran the wrong charter on every
    render, indefinitely, until fixed."""

    def setUp(self):
        super().setUp()
        make_plane(self)      # `maybe_spawn` refuses to fork without one (#527)
        allow_background_checks(self)     # and returns first thing with the switch on (#945)

    def test_argv_carries_dash_p(self):
        d = self.tmp / "somerepo"
        d.mkdir(parents=True, exist_ok=True)
        captured = {}

        def fake_popen(cmd, **kw):
            captured["cmd"] = cmd
            return mock.MagicMock()

        with mock.patch.object(glstate.subprocess, "Popen", side_effect=fake_popen):
            glstate.maybe_spawn([d])

        self.assertIn("cmd", captured, "Popen was never called — nothing was stale?")
        self.assertEqual(captured["cmd"], util.self_relaunch_argv("gl-refresh"))



class WorkspaceAutosavePushUsesIt(unittest.TestCase):
    """charter/commands_workspace.py:686 — `workspace _pushbg`, the Stop-hook autosave's
    background push under the `push` sharing posture."""

    def test_argv_carries_dash_p(self):
        with mock.patch.object(cw.subprocess, "Popen") as popen:
            cw._spawn_pushbg(Path("/some/control/plane"))
        argv = popen.call_args.args[0]
        self.assertEqual(argv, util.self_relaunch_argv("workspace", "_pushbg"))
        self.assertEqual(popen.call_args.kwargs.get("cwd"), "/some/control/plane")


class DiscoverPushUsesIt(unittest.TestCase):
    """charter/planegit.py:87 — `workspace _pushbg`, `discover`'s own background push of
    HEAD, the sibling of the autosave push above."""

    def test_argv_carries_dash_p(self):
        with mock.patch.object(planegit.subprocess, "Popen") as popen:
            planegit._spawn_bg_push(Path("/some/control/plane"))
        argv = popen.call_args.args[0]
        self.assertEqual(argv, util.self_relaunch_argv("workspace", "_pushbg"))
        self.assertEqual(popen.call_args.kwargs.get("cwd"), "/some/control/plane")


class NoHandBuiltSelfRelaunchArgvAnywhere(unittest.TestCase):
    """The whole-tree rule, so a site nobody has thought of yet is still covered.

    Every class above names a call site that exists today. That is the one thing such a
    test cannot do for a site added tomorrow, and tomorrow arrived: `cmd_respawn` shipped
    a fresh `[sys.executable, "-m", "charter"]` on a branch cut before `-P` landed, merged
    cleanly (different lines), and left this module fully green while re-opening #390 on
    the respawn path. This test reads the source instead of the call sites, so the NEXT
    one fails on the way in.
    """

    def test_the_detector_finds_the_helpers_own_literal(self):
        """First, that the detector is not vacuous.

        A scanner that parsed nothing — a wrong package path, a `rglob` that matched no
        files, an AST shape that never fires — would make the test below pass forever
        while checking nothing, which is this project's most-caught flavour of broken
        test. `util.self_relaunch_argv` contains the one literal of exactly the shape
        being hunted, so finding it proves the hunt works on the real thing rather than
        on a fixture built to be found.
        """
        sites = _hand_built_relaunch_argvs()
        helper = [s for s in sites if s[0] == "charter/util.py"]
        self.assertEqual(len(helper), 1,
                         f"the detector did not find `util.{_HELPER}`'s own argv "
                         f"literal — it is not detecting anything: {sites}")
        self.assertIn("-P", helper[0][2],
                      f"the helper itself lost `-P`: {helper[0][2]}")

    def test_no_other_module_builds_one_itself(self):
        """Then, the rule: `charter/util.py` is the only file allowed to spell it out.

        Not "every file except this one call site" — any file. A new self-relaunch is
        one `util.self_relaunch_argv(...)` call, and there is no case where writing the
        list out by hand is the right answer: the `-P` it must carry is the same `-P`
        everywhere, and a shell TEMPLATE that cannot take a flag carries
        `PYTHONSAFEPATH=1` instead (see `commands_frame._charter_pythonsafepath_env_argv`)
        rather than a hand-built argv.
        """
        offenders = [s for s in _hand_built_relaunch_argvs() if s[0] != "charter/util.py"]
        self.assertEqual(
            offenders, [],
            "hand-built `-m charter` argv outside `util.self_relaunch_argv` — call the "
            "helper instead, so this site cannot import whatever `charter/` package "
            "happens to sit in its child's cwd (#390):\n" +
            "\n".join(f"  {f}:{line}  {src}" for f, line, src in offenders))


if __name__ == "__main__":
    unittest.main()
