"""No test forks a charter child that nothing waits for.

#527 closed **which plane** a test-spawned charter lands on. This is the other half: **how
many charter children a test forks at all**, and the answer at b3dbd54 was 66 detached ones
per green run — 27 `charter _version-check`, each a GET to PyPI, 36 `charter gl-refresh`,
each running the forge client for every clone in the workspace, and 3 `charter
frame-gather`. Counted in-process, by wrapping `subprocess.Popen.__init__` before the
`tests` package is imported, because a ``ps | grep`` sample of a running suite matches its
own command line and reports a number that is not real.

**They fire in a test and almost never in real use for the same reason a temp plane is an
isolated one.** Both spawners are throttled by state in `config.STATE_DIR` — a cache TTL
and a cooldown lock — and `PersonaIso` hands every case a fresh one, so the cache is always
absent and the lock never exists. `test_statusline_brand` has said so in a comment for as
long as it has had one: *"a temp STATE_DIR always looks stale"*. Six modules stubbed the
spawner by hand because of it; the other twelve did not, and forked.

**The fix refuses the FORK, and that is what keeps it from being a stub.** The obvious move
— `PersonaIso` stubs `update.maybe_spawn` and `glstate.maybe_spawn` for every case — makes
a test that cannot fail: `test_glstate`, `test_glstate_respawn`, `test_dev_channel` and
`test_self_relaunch_argv` call those functions directly to assert on the argv and the
cooldown, and a base-class stub would swallow them, silently for the "must not raise"
cases. Refusing at `subprocess.Popen` leaves every one of those running its throttle logic
and asserting on it exactly as before; what it refuses is the `start_new_session=True`
child at the end, which is the only part nobody was asserting about.

Every case here is a control. `TheGuardIsNotBlind` makes the refusal happen for real and
`EitherWayOutWorks` exercises both documented escapes, because a tripwire with no usable
exit is a tripwire whoever hits it next deletes.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from charter import config, glstate, root, statusline, update, util
from tests import _envguard, _planeguard
# The MODULE, never the class: `from … import RenderNeverCrashesCase` would bind a TestCase
# subclass in this module's namespace, and `TestLoader` collects by namespace — the borrowed
# fixture would then run a second time in every suite run, under this file's name.
from tests import test_statusline_crash_guard
from tests._isolation import (PersonaIso, child_plane_env, isolate_state_dir, make_plane,
                              no_background_refresh)


class WhatIsRefused(unittest.TestCase):
    """The discriminator is a Popen KEYWORD, not a list of subcommand spellings.

    ``start_new_session=True`` is charter's own shape for "a child that outlives this
    process" — `util.detach_self`'s docstring calls it the load-bearing part — so a
    background refresher nobody has written yet is refused on the commit that writes it.
    """

    def test_a_detached_charter_child_is_refused(self):
        with self.assertRaises(_planeguard.BackgroundCharterChild):
            subprocess.Popen(["charter", "_version-check"], start_new_session=True,
                             cwd="/nonexistent-so-nothing-can-actually-start")

    def test_a_charter_child_the_test_will_wait_for_is_not(self):
        """`subprocess.run`, `check_output` and a plain `Popen` all construct the class
        without that keyword. Those children are the ones a test drives on purpose and
        waits for, and this guard is not about them — it is about the ones nobody waits
        for. Refused here only by the CWD, which proves the guard let it past."""
        with self.assertRaises(FileNotFoundError):
            subprocess.Popen(["charter", "_version-check"],
                             cwd="/nonexistent-so-nothing-can-actually-start")

    def test_a_detached_child_that_is_not_charter_is_not_refused(self):
        """The suite forks plenty of detached things that are nobody's control plane."""
        with self.assertRaises(FileNotFoundError):
            subprocess.Popen(["tmux", "-L", "nothing", "kill-server"],
                             start_new_session=True,
                             cwd="/nonexistent-so-nothing-can-actually-start")


class TheGuardIsNotBlind(unittest.TestCase):
    """The refusal, made to happen, and read."""

    def _refusal(self) -> str:
        with self.assertRaises(_planeguard.BackgroundCharterChild) as raised:
            subprocess.Popen(["charter", "gl-refresh"], start_new_session=True,
                             cwd="/nonexistent-so-nothing-can-actually-start")
        return str(raised.exception)

    def test_the_message_names_the_test_the_argv_and_both_ways_out(self):
        said = self._refusal()
        self.assertIn("test_the_message_names_the_test_the_argv_and_both_ways_out", said)
        self.assertIn("charter gl-refresh", said)
        self.assertIn("no_background_refresh", said)
        self.assertIn("allow_background_children", said)
        self.assertIn("#542", said)

    def test_the_message_says_why_a_test_sees_this_and_a_real_machine_does_not(self):
        """The single most useful sentence in it: the reader's next thought is "this never
        happens to me", and the answer is that their plane has a cache and a cooldown lock
        and a test's plane is one line old."""
        said = self._refusal()
        self.assertIn("STATE_DIR", said)
        self.assertIn("cooldown", said)

    def test_the_refusal_is_not_an_exception(self):
        """Both spawners wrap their `Popen` in ``try/except Exception`` and return — so an
        `Exception` here would be swallowed into "the spawn did not happen", which is
        exactly what the guard is trying to report. `_planeguard.RealPlaneWrite` and
        `_envguard.AmbientEnvRead` are `BaseException` for the same reason."""
        self.assertTrue(issubclass(_planeguard.BackgroundCharterChild, BaseException))
        self.assertFalse(issubclass(_planeguard.BackgroundCharterChild, Exception))


class EitherWayOutWorks(unittest.TestCase):
    """Both documented escapes, exercised rather than described."""

    def test_declaring_the_case_wants_one_lets_it_through(self):
        """The A half of an A/B: the same call `WhatIsRefused` above is refused for, made
        after the declaration. `FileNotFoundError` is the REAL `Popen` reporting a cwd that
        does not exist, which is proof the guard is no longer what stopped it."""
        _planeguard.allow_background_children(self)
        with self.assertRaises(FileNotFoundError):
            subprocess.Popen(["charter", "_version-check"], start_new_session=True,
                             cwd="/nonexistent-so-nothing-can-actually-start")

    def test_the_declaration_does_not_outlive_its_case(self):
        """Scoped by `addCleanup`, so the case after this one is guarded again. Run as an
        inner case rather than asserted on the flag, because what matters is the state the
        NEXT test runs in."""
        class Declares(unittest.TestCase):
            def runTest(inner):        # noqa: N805
                _planeguard.allow_background_children(inner)

        Declares().run(unittest.TestResult())
        with self.assertRaises(_planeguard.BackgroundCharterChild):
            subprocess.Popen(["charter", "_version-check"], start_new_session=True,
                             cwd="/nonexistent-so-nothing-can-actually-start")


class StoppingTheSpawnerIsTheOtherWayOut(PersonaIso):
    """`no_background_refresh` — the one spelling of what six modules wrote by hand.

    About the spawners, so the suite's ``$CHARTER_NO_BACKGROUND_CHECKS`` is taken away:
    with it on, both return before the fork this class is measuring (#945)."""

    def setUp(self) -> None:
        super().setUp()
        _planeguard.allow_background_checks(self)

    def test_without_it_a_render_path_call_forks(self):
        """The control. `make_plane` gives this case a REAL plane, which is what the
        spawner requires, and a plane one line old has no lock — so this is the state
        twelve modules were in. The forge refresh, because since 0.62.2 the version check
        starts nothing at all."""
        make_plane(self)
        with self.assertRaises(_planeguard.BackgroundCharterChild):
            glstate.maybe_spawn([self.tmp], "default")

    def test_with_it_the_same_call_forks_nothing(self):
        make_plane(self)
        no_background_refresh(self)
        update.maybe_spawn()                  # must not raise
        glstate.maybe_spawn([self.tmp], "default")

    def test_it_covers_the_forge_refresh_as_well_as_the_version_check(self):
        """The half the hand-rolled stubs missed. `test_statusline_plane_root_warning`
        stubbed `update.maybe_spawn` and named the reason — "a suite that quietly reaches
        the network is not hermetic" — and then forked a real `charter gl-refresh` past it
        on every dirty-root render (#542)."""
        make_plane(self)
        with self.assertRaises(_planeguard.BackgroundCharterChild):
            glstate.maybe_spawn([self.tmp], "default")


#: Spelled, not asked of `charter.util`: these cases pin the documented name.
_SWITCH = "CHARTER_NO_BACKGROUND_CHECKS"

#: A cwd that cannot exist, so a child the guard lets past fails in the real `Popen` with
#: `FileNotFoundError` — the proof it was not the guard that stopped it — and runs nothing.
_NOWHERE = "/nonexistent-so-nothing-can-actually-start"


class TheSuiteSwitchesTheChecksOffForEveryChild(unittest.TestCase):
    """#945, the generation below. `BackgroundCharterChild` refuses a fork in THIS process;
    a child charter handed a fresh plane forks its own `_version-check` and `gl-refresh`,
    where no patch reaches. `$CHARTER_NO_BACKGROUND_CHECKS` is set once, for the suite, the
    way `tests/_gitguard.py` redirects `~/.gitconfig`: every child inherits it, and so does
    every child of a child and every pane of a tmux server a test starts."""

    def test_this_process_has_it_on(self):
        self.assertTrue(os.environ.get(_SWITCH, "").strip())
        self.assertTrue(util.background_checks_off())

    def test_a_child_inherits_it(self):
        """A real `unsetenv`/`putenv`, not a Python-side value a child never sees."""
        out = subprocess.run([sys.executable, "-c",
                              f"import os; print(os.environ.get({_SWITCH!r}, ''))"],
                             capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(out, os.environ[_SWITCH])

    def test_a_developers_shell_neither_hides_it_nor_stands_in_for_it(self):
        """The ordering, asked of a fresh import of the `tests` package rather than read off
        its source. `_envguard` removes every ``CHARTER_*`` name the shell exported; the
        suite's own value has to arrive after that removal or it is removed with them. A
        blank export would then HIDE the switch from every child, and a developer who
        exports it themselves would FAKE it: green on their machine and a real GET to PyPI
        on a runner that never set it. The same child also has to find the shell's value in
        `_envguard.scrubbed()`, which is what proves it was removed rather than never there.

        Run from a throwaway plane with ``$PYTHONPATH`` carrying the tree, for
        `test_no_test_reads_the_operators_shell`'s reason: a child importing this package
        resolves a plane at import, and the scrub removes any ``$CHARTER_ROOT`` first."""
        _planeguard.allow_background_checks(self)       # the blank one is refused otherwise
        probe = ("import json, os, tests; from tests import _envguard;"
                 f"print(json.dumps([os.environ.get({_SWITCH!r}), "
                 f"_envguard.scrubbed().get({_SWITCH!r})]))")
        plane, _ = child_plane_env(self)
        tree = Path(__file__).resolve().parent.parent
        for shell in ("", "   ", "a value the developer exported"):
            with self.subTest(shell=shell):
                out = subprocess.run(
                    [sys.executable, "-c", probe],
                    env={**os.environ, _SWITCH: shell, "PYTHONPATH": str(tree)},
                    cwd=str(plane), capture_output=True, text=True, check=True)
                suite, scrubbed = json.loads(out.stdout.splitlines()[-1])
                self.assertEqual(suite, "1")
                self.assertEqual(scrubbed, shell)


class AChildThatDropsTheSwitchIsRefused(unittest.TestCase):
    """The redirect alone is a default, and a hand-built ``env=`` walks past a default. So
    the spawn is refused, the way `AmbientGitConfig` refuses a git child that drops
    ``$GIT_CONFIG_GLOBAL``: for a charter child, and for a tmux child, whose server hands
    its own environment to every `charter panel` it starts."""

    def test_a_charter_child_with_a_hand_built_environment_is_refused(self):
        with self.assertRaises(_planeguard.BackgroundGrandchild):
            subprocess.Popen(["charter", "hook", "sessionstart"], env={"PATH": "/usr/bin"},
                             cwd=_NOWHERE)

    def test_a_blank_value_is_dropped_too(self):
        """Blank is unset to `util.background_checks_off`, so it is unset to the guard."""
        with self.assertRaises(_planeguard.BackgroundGrandchild):
            subprocess.Popen(["charter", "panel", "right"], env={**os.environ, _SWITCH: " "},
                             cwd=_NOWHERE)

    def test_a_charter_child_in_an_emptied_environment_is_refused(self):
        """`mock.patch.dict(os.environ, clear=True)` and ``env=None`` is the other way to
        hand a child nothing; the guard asks the environment the child will GET."""
        with mock.patch.dict(os.environ, {"PATH": "/usr/bin"}, clear=True), \
                self.assertRaises(_planeguard.BackgroundGrandchild):
            subprocess.Popen(["charter", "frame-gather"], cwd=_NOWHERE)

    def test_a_tmux_child_that_drops_it_is_refused(self):
        with self.assertRaises(_planeguard.BackgroundGrandchild):
            subprocess.Popen(["tmux", "-L", "charter-945-nothing", "new-session", "-d"],
                             env={"PATH": "/usr/bin"}, cwd=_NOWHERE)

    def test_the_refusal_names_the_test_the_command_the_switch_and_the_ways_out(self):
        with self.assertRaises(_planeguard.BackgroundGrandchild) as caught:
            subprocess.Popen(["charter", "hook", "sessionstart"], env={}, cwd=_NOWHERE)
        said = str(caught.exception)
        self.assertIn("test_the_refusal_names_the_test_the_command_the_switch_and_the_ways_out",
                      said)
        self.assertIn("charter hook sessionstart", said)
        self.assertIn(_SWITCH, said)
        self.assertIn("#945", said)
        self.assertIn("PyPI", said)                        # what it costs
        self.assertIn("env=None", said)                    # way out 1
        self.assertIn("os.environ", said)                  # way out 2
        self.assertIn("_envguard.stated()", said)          # way out 3
        self.assertIn("allow_background_checks", said)     # way out 4

    def test_it_is_a_base_exception_so_a_fallback_cannot_eat_it(self):
        self.assertTrue(issubclass(_planeguard.BackgroundGrandchild, BaseException))
        self.assertFalse(issubclass(_planeguard.BackgroundGrandchild, Exception))

    def test_a_child_that_carries_it_is_not_refused(self):
        for env in (None, {**os.environ, "EXTRA": "1"}, {_SWITCH: "1", "PATH": "/usr/bin"}):
            for argv in (["charter", "hook", "sessionstart"],
                         ["tmux", "-L", "charter-945-nothing", "new-session", "-d"]):
                with self.subTest(argv=argv[0], env=None if env is None else sorted(env)):
                    with self.assertRaises(FileNotFoundError):
                        subprocess.Popen(argv, env=env, cwd=_NOWHERE)

    def test_the_helpers_own_answer_is_enough_in_a_bare_environment(self):
        with self.assertRaises(FileNotFoundError):
            subprocess.Popen(["charter", "hook", "sessionstart"],
                             env={"PATH": "/usr/bin", **_envguard.stated()}, cwd=_NOWHERE)

    def test_a_program_that_is_neither_may_state_its_own_environment(self):
        """The boundary: a rule about the two programs that start charter, not a ban on
        building an environment."""
        with self.assertRaises(FileNotFoundError):
            subprocess.Popen(["tar", "--version"], env={}, cwd=_NOWHERE)

    def test_asking_tmux_its_version_starts_no_server(self):
        """``tmux -V`` prints and exits; nothing it starts can run a panel."""
        with self.assertRaises(FileNotFoundError):
            subprocess.Popen(["tmux", "-V"], env={}, cwd=_NOWHERE)

    def test_every_way_tmux_is_told_to_start_a_server_is_refused(self):
        """A server takes its environment from the client that starts it, and hands it to
        every pane. tmux starts one for `new-session`, its alias `new`, `start-server` and
        its alias `start`, any prefix of either name that no other command shares, and a
        bare `tmux` with no command at all — also when the command follows a `;`."""
        for words in (["new-session", "-d"], ["new", "-d"], ["new-s"], ["start-server"],
                      ["start"], ["st"], [], ["-f", "/dev/null"], ["ls", ";", "new-session"],
                      ["ls;", "new"], ["-2", "-u", "new-session"]):
            with self.subTest(words=words), \
                    self.assertRaises(_planeguard.BackgroundGrandchild):
                subprocess.Popen(["tmux", "-L", "charter-945-nothing", *words],
                                 env={"PATH": "/usr/bin"}, cwd=_NOWHERE)

    def test_a_command_to_a_server_that_must_already_run_is_not_refused(self):
        """`cmd_chrome` sets a style on a running frame with a cleared environment: tmux
        answers "no server running" rather than start one, so no pane can inherit what
        this child lacks. `new-window` and `new-w` are the names one letter away, and
        `new-` and `s` are prefixes tmux refuses as ambiguous rather than run."""
        for words in (["set", "-g", "status", "off"], ["list-sessions"], ["new-window"],
                      ["new-w"], ["new-"], ["s"], ["kill-server"],
                      ["send-keys", "new-session"], ["rename-window", "new"]):
            with self.subTest(words=words), self.assertRaises(FileNotFoundError):
                subprocess.Popen(["tmux", "-L", "charter-945-nothing", *words],
                                 env={"PATH": "/usr/bin"}, cwd=_NOWHERE)


class ACaseAboutASpawnerTurnsTheSwitchOff(unittest.TestCase):
    """`allow_background_checks` — the way out for a case whose subject IS a spawner, which
    with the switch on would return before running anything worth asserting on."""

    def test_it_takes_the_switch_out_of_this_process(self):
        _planeguard.allow_background_checks(self)
        self.assertNotIn(_SWITCH, os.environ)
        self.assertFalse(util.background_checks_off())

    def test_and_lets_a_child_without_it_through(self):
        _planeguard.allow_background_checks(self)
        with self.assertRaises(FileNotFoundError):
            subprocess.Popen(["charter", "hook", "sessionstart"], env={}, cwd=_NOWHERE)

    def test_the_declaration_and_the_switch_come_back_when_the_case_ends(self):
        before = os.environ[_SWITCH]

        class Declares(unittest.TestCase):
            def runTest(inner):        # noqa: N805
                _planeguard.allow_background_checks(inner)

        Declares().run(unittest.TestResult())
        self.assertEqual(os.environ.get(_SWITCH), before)
        with self.assertRaises(_planeguard.BackgroundGrandchild):
            subprocess.Popen(["charter", "hook", "sessionstart"], env={}, cwd=_NOWHERE)

class _ARenderThatOnlyRedirectsTheStateDir(unittest.TestCase):
    """The positive control: the fixture `RenderNeverCrashesCase` had at #944, kept so the
    probe below is known to SEE a fork rather than merely to report none.

    Its probe method is deliberately not named ``test_*``. Discovery collects this class (a
    leading underscore does not hide it from `TestLoader`) and would otherwise fork for
    real, out of whatever plane the suite resolved, every single run.
    """

    def setUp(self) -> None:
        _envguard.unset_all()
        isolate_state_dir(self)

    def runProbe(self) -> None:
        statusline.render({"session_id": "t"})


class ARenderAgainstTheRealPlaneForksNothing(unittest.TestCase):
    """#944 half two: `no_background_refresh` exists, and a case still has to CALL it.

    `test_statusline_crash_guard.RenderNeverCrashesCase` renders against the real plane on
    purpose — its own comment says so — and redirected only `config.STATE_DIR`. **That
    redirect is what arms the fork.** `glstate.maybe_spawn` reads its cooldown lock and its
    cache out of `STATE_DIR`, so in a fresh tempdir there is never a lock, never a cache
    entry, and every directory it is handed looks stale. All that was left deciding the
    outcome was ``dirs`` — the active workspace's clones. Recorded on unmodified code:
    ``n_dirs=0`` at the plane root and on a CI checkout, which has no ``workspaces/<ws>/``
    holding clones, so ``any([])`` is False and nothing forks; ``n_dirs=7`` in a workspace
    clone and in a worktree of one, so it forked and the guard refused it.

    So the case was green where CONTRIBUTING says not to work and red where it says to, and
    what decided which was **whether the person running it had ever cloned a repo**. It is
    asked here of a plane that HAS one, so the answer is the same on every machine.
    """

    def _run_against_a_plane_holding_a_clone(self, case_class, method) -> unittest.TestResult:
        """Run one real test method with the ambient plane pointed at a sentinel that has a
        workspace with a clone in it, and hand back what the run recorded.

        A sentinel plane, never the real one: a RED run of this module must not commit the
        very fork it exists to forbid. `charter.toml` is present so `HAS_CONTROL_PLANE` is
        what it is on a developer's machine — both spawners refuse outright without a plane
        — and the clone is a bare ``.git`` DIRECTORY, which is the whole of
        `workspace.is_clone`'s test.
        """
        # Without the suite's switch, which would otherwise answer this for every case run
        # here: a crash guard that stopped calling `no_background_refresh` would fork
        # nothing because the spawners return on their first line, and pass (#945).
        _planeguard.allow_background_checks(self)
        sentinel = Path(tempfile.mkdtemp(prefix="charter-944-sentinel-")).resolve()
        self.addCleanup(shutil.rmtree, sentinel, True)
        (sentinel / root.MARKER).write_text("schema = 1\n")
        (sentinel / "workspaces" / "default" / "charter" / ".git").mkdir(parents=True)
        outer = config.use(sentinel)
        try:
            result = unittest.TestResult()
            case_class(method).run(result)
            return result
        finally:
            config.restore(outer)

    @staticmethod
    def _what_it_said(result: unittest.TestResult) -> str:
        return "\n".join(text for _, text in (*result.errors, *result.failures))

    def test_the_probe_can_see_a_render_fork(self):
        """Without this, the case below would pass just as well if the probe were blind —
        and blind is the failure mode that already happened once here, since the whole
        defect was a spawn nobody's machine attempted."""
        said = self._what_it_said(
            self._run_against_a_plane_holding_a_clone(
                _ARenderThatOnlyRedirectsTheStateDir, "runProbe"))
        self.assertIn("BackgroundCharterChild", said)

    def test_the_render_crash_guard_forks_nothing(self):
        """The case itself, run against a plane with a clone in it. It is about `render()`
        not propagating an exception, so nothing in it ever wanted a child."""
        for method in ("test_a_broken_repo_row_does_not_crash_render",
                       "test_a_broken_persona_chips_call_does_not_crash_render"):
            with self.subTest(method=method):
                result = self._run_against_a_plane_holding_a_clone(
                    test_statusline_crash_guard.RenderNeverCrashesCase, method)
                self.assertTrue(result.wasSuccessful(), self._what_it_said(result))


class EveryCharterCharterStartsForItselfIsDetached(PersonaIso):
    """Why one keyword is enough, asked of production rather than assumed of it.

    The guard recognises a background child by ``start_new_session=True``. That is only a
    complete answer while every charter that charter starts for itself passes it — so this
    is where that stops being an assumption. Two cases, behaviour first and source second:
    the behavioural one fails if a spawner drops the flag, the AST one fails if a NEW
    spawner is written without it.
    """

    def _kwargs_of_the_spawn(self, call) -> dict:
        seen = {}

        def spy(args=None, *rest, **kw):
            seen["args"], seen["kw"] = args, kw
            raise RuntimeError("no child, thank you")

        make_plane(self)
        _planeguard.allow_background_checks(self)     # or neither spawner gets that far
        with mock.patch("subprocess.Popen", spy):
            call()
        return seen


    def test_the_forge_refresh_is_started_detached(self):
        seen = self._kwargs_of_the_spawn(
            lambda: glstate.maybe_spawn([self.tmp], "default"))
        self.assertIn("gl-refresh", seen["args"])
        self.assertTrue(seen["kw"].get("start_new_session"))

    #: ``<module>:<function>`` → why this `subprocess.Popen` starts a child nothing
    #: waits for. **Frozen deliberately**, the way
    #: `NoCharterEscapesThroughTheExecFamily.KNOWN` in `test_plane_spawn_guard.py` is: the
    #: point is that a NEW spawner is noticed, and a set that grew by itself would notice
    #: nothing.
    #:
    #: It is also the CONTROL, and that is what earns it over a bare "nothing is
    #: undetached" assertion. Four separate mutations to this case's own reader survived
    #: the version that only checked for undetached spawns — including one that made the
    #: reader answer ``None`` for every `subprocess.Popen`, so it found nothing at all and
    #: reported success for it. A census that does not say what it expected to find cannot
    #: tell "nothing is wrong" from "I looked at nothing".
    DETACHED = {
        "charter/glstate.py:maybe_spawn":
            "`charter gl-refresh` — the forge client over every clone in the workspace, "
            "the status line's own render path, so a render never blocks on the network. "
            "(`update.maybe_spawn` started `charter _version-check` the same way until "
            "0.62.2, charter-cp's last release, switched the update check off.)",
        "charter/util.py:detach_self":
            "The helper the other three go through: `charter <args>` in a process that "
            "outlives this one, which is what a hook's `\"async\": true` used to buy.",
        "charter/planegit.py:_spawn_bg_push":
            "A push of the plane's own repo, after the turn that dirtied it.",
        "charter/commands_workspace.py:_spawn_pushbg":
            "The workspace half of the same push, from the Stop hook.",
        "charter/frame/builtin_actions.py:_spawn":
            "A palette action re-entering charter, with the overlay pane's tty already "
            "closed under it — which is why its streams go to DEVNULL as well.",
    }

    @staticmethod
    def _popens_in(source: str, where: str = "<source>") -> dict[str, bool]:
        """``{where:function -> passes start_new_session}`` for every `Popen` in *source*.

        Parsed, not grepped, so a `mock.patch("subprocess.Popen")` written in a docstring
        or a string is what it is. A function of its own, taking TEXT, so
        :meth:`test_it_sees_a_popen_written_either_way` can hand it both spellings and
        watch it answer — the reader's ``ast.Name`` branch is unexercised by charter, which
        writes ``subprocess.Popen`` everywhere, and a mutation deleting it survived the
        version of this case that only ever ran the reader over the real tree. It is not
        dead code: ``from subprocess import Popen`` is a shape `_guard_spawns`'s own
        docstring names as one it has to cover, so the branch stays and gets a control.
        """
        parsed = ast.parse(source)
        for enclosing in ast.walk(parsed):
            for node in ast.iter_child_nodes(enclosing):
                node.parent = enclosing
        found = {}
        for node in ast.walk(parsed):
            if not (isinstance(node, ast.Call) and _called_name(node.func) == "Popen"):
                continue
            found[f"{where}:{_enclosing_name(node)}"] = any(
                kw.arg == "start_new_session" for kw in node.keywords)
        return found

    def _popens_in_charter(self) -> dict[str, bool]:
        """The same reader over every module in `charter/`.

        Deliberately NOT wrapped in a try/except: a file under `charter/` that will not
        parse is a defect in charter, and skipping it would leave whatever it contains
        unguarded while this case carried on looking healthy.
        """
        tree = Path(__file__).resolve().parent.parent
        found = {}
        for path in sorted((tree / "charter").glob("**/*.py")):
            found.update(self._popens_in(path.read_text(encoding="utf-8"),
                                         path.relative_to(tree).as_posix()))
        return found

    def test_it_sees_a_popen_written_either_way(self):
        """The control. Both spellings, both answers, and the enclosing function named —
        a reader that quietly stopped recognising one of them would report "nothing
        undetached" for the best of reasons."""
        seen = self._popens_in(
            "import subprocess\n"
            "from subprocess import Popen\n"
            "def attribute_form():\n"
            "    subprocess.Popen(['x'], start_new_session=True)\n"
            "def bare_name_form():\n"
            "    Popen(['x'])\n")
        self.assertEqual(seen, {"<source>:attribute_form": True,
                                "<source>:bare_name_form": False})

    def test_it_names_a_spawn_that_sits_at_module_scope(self):
        """`_enclosing_name`'s other answer. Nothing in charter does this today; a reader
        that raised on it would fail the day something did, which is the day this census
        matters most."""
        self.assertEqual(self._popens_in("import subprocess\nsubprocess.Popen(['x'])\n"),
                         {"<source>:<module>": False})

    def test_every_charter_child_charter_starts_is_started_detached(self):
        """One keyword is a complete answer only while every self-relaunch passes it."""
        found = self._popens_in_charter()
        undetached = sorted(k for k, detached in found.items() if not detached)
        self.assertEqual(
            undetached, [],
            f"{undetached} starts a child from `subprocess.Popen` without "
            f"`start_new_session=True`. `tests._planeguard.BackgroundCharterChild` "
            f"recognises a background charter child by exactly that keyword, so a spawner "
            f"without it is one no test can be refused for forking (#542). Either detach "
            f"it — every other one in charter does — or, if this child is one its caller "
            f"really waits for, say so in `DETACHED` and give the guard another way to "
            f"see it.")

    def test_the_census_still_finds_every_spawner_it_was_written_against(self):
        """The control. Without it, a reader that quietly stopped recognising
        `subprocess.Popen` would report "nothing undetached" for the best of reasons —
        which is what four mutations to the previous version of this case did."""
        self.assertEqual(sorted(self._popens_in_charter()), sorted(self.DETACHED))


def _enclosing_name(node) -> str:
    """The name of the function *node* sits in, or ``<module>``.

    `ast` carries no parent links, so `_popens_in_charter` adds them on the way past. A
    `Popen` at module scope has no enclosing function and is named for what it is.
    """
    while getattr(node, "parent", None) is not None:
        node = node.parent
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node.name
    return "<module>"


def _called_name(func) -> str | None:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


if __name__ == "__main__":       # pragma: no cover
    unittest.main()
