"""`$CHARTER_NO_BACKGROUND_CHECKS` stops both detached refreshes, and nothing else.

#945. charter starts two children nobody waits for: `update.maybe_spawn` forks `charter
_version-check`, a GET to PyPI, and `glstate.maybe_spawn` forks `charter gl-refresh`, the
forge client over every clone in the workspace. Both are throttled by state in
`config.STATE_DIR`, so a plane made a moment ago always forks. The suite makes such planes
all day and hands them to real child charters, where `tests._planeguard` cannot see the
fork; and an offline machine, a CI job or anyone who does not want charter phoning home had
no way to say "don't" short of planting a lock file by hand.

So there is a switch, and it is a production one: set the variable to any value that is not
blank and both spawners return before they read or write their lock or their cache. What a
person runs — `charter update`, `charter version bump`, `charter gl-refresh` — is not a
background refresh and still reaches the network.

**Every value but a blank one turns it on, ``0`` and ``false`` included.** A switch that
recognised a set of spellings would read the next spelling as "off" and phone home against
the operator's stated wish; reading an unintended value as "on" costs a stale indicator.
Blank is unset, as it is for `$CHARTER_WORKSPACE` (#1055).

The names are spelled here, not asked of `charter.util`: this module pins the documented
name, and a case that read it off the constant would pass whatever the constant said.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest import mock

from pathlib import Path

from charter import __version__, commands, config, glstate, root, update
from tests import _planeguard
from tests._isolation import PersonaIso, make_plane, pin_update_channel

NAME = "CHARTER_NO_BACKGROUND_CHECKS"

#: Values that turn the switch on, and the ones that leave it off. ``0`` and ``false`` are
#: on purpose on the first list; see the module docstring.
ON = ("1", "yes", "true", "0", "false", "off", " 1 ")
OFF = ("", " ", "\t\n")


@contextmanager
def _variable(value: str | None):
    """This process's environment with the variable set to *value*, or absent for None."""
    with mock.patch.dict(os.environ):
        os.environ.pop(NAME, None)
        if value is not None:
            os.environ[NAME] = value
        yield


class _Read(BaseException):
    """A read the switch should have prevented. A `BaseException`, because both spawners
    wrap their reads in ``except Exception`` and would turn an `AssertionError` into the
    early return this is trying to tell apart from the switch."""


def _fresh() -> None:
    """No lock and no cache, so each subtest starts from a plane made a moment ago."""
    shutil.rmtree(config.STATE_DIR / "cache", ignore_errors=True)


def _recorder():
    """A `Popen` stand-in that records the argv it was handed and forks nothing."""
    calls: list[list[str]] = []

    def popen(args, *rest, **kw):
        calls.append([str(a) for a in args])
        return mock.MagicMock(pid=os.getpid())

    return popen, calls



class TheForgeRefresh(PersonaIso):
    """`glstate.maybe_spawn` — the same switch on the second spawner, which forks only when
    it is handed a clone whose cache entry is stale."""

    def setUp(self) -> None:
        super().setUp()
        make_plane(self)
        self.repo = self.tmp / "somerepo"
        self.repo.mkdir()

    def _spawn(self) -> list[list[str]]:
        popen, calls = _recorder()
        with mock.patch.object(glstate.subprocess, "Popen", popen):
            glstate.maybe_spawn([self.repo], "default")
        return calls

    def test_off_a_stale_clone_forks_the_refresh_and_writes_the_lock(self):
        with _variable(None):
            calls = self._spawn()
        self.assertEqual(len(calls), 1)
        self.assertIn("gl-refresh", calls[0])
        self.assertTrue(glstate._lock_file().exists())

    def test_on_it_forks_nothing_and_writes_no_lock(self):
        for value in ON:
            with self.subTest(value=value), _variable(value):
                _fresh()
                self.assertEqual(self._spawn(), [])
                self.assertFalse(glstate._lock_file().exists())
                self.assertFalse(glstate._cache_file().parent.exists())

    def test_blank_is_unset(self):
        for value in OFF:
            with self.subTest(value=value), _variable(value):
                _fresh()
                self.assertEqual(len(self._spawn()), 1)

    def test_on_it_does_not_even_read_the_lock_or_the_cache(self):
        with _variable("1"), mock.patch.object(glstate, "_lock_file", side_effect=_Read), \
                mock.patch.object(glstate, "load", side_effect=_Read):
            self.assertEqual(self._spawn(), [])


class WhatAPersonRunsStillAsks(PersonaIso):
    """The switch is about DETACHED refreshes. A command somebody typed is an answer they
    asked for, and it reaches the network with the switch on exactly as without it."""

    def setUp(self) -> None:
        super().setUp()
        make_plane(self)

    def test_fetch_and_store_still_fetches(self):
        """What `charter update`, `charter version bump` and `_version-check` itself call."""
        with _variable("1"), mock.patch.object(update, "_fetch_latest",
                                               return_value="9.9.9") as fetch:
            self.assertEqual(update.fetch_and_store(), "9.9.9")
        fetch.assert_called_once()
        self.assertEqual(update.load().get("latest"), "9.9.9")

    def test_a_forge_refresh_still_refreshes(self):
        """What `charter gl-refresh` calls."""
        repo = self.tmp / "somerepo"
        repo.mkdir()
        state = {"change": 7, "ci": "success", "sigil": "#"}
        with _variable("1"), mock.patch.object(glstate, "_branch", return_value="main"), \
                mock.patch.object(glstate, "state_for_repo", return_value=state) as asked:
            glstate.refresh([repo])
        asked.assert_called_once()
        self.assertEqual(glstate.load()[str(repo)]["change"], 7)



#: A charter that records every detached child it would start, and starts none of them.
#: `start_new_session=True` is charter's own shape for a background refresh (see
#: `test_no_test_forks_a_background_charter`), and both spawners catch the `OSError`
#: and return — so the tripwire costs the child nothing but the fork, and nothing reaches
#: the network whether the switch holds or not.
_TRIPWIRE = """
import os, runpy, subprocess, sys
real = subprocess.Popen.__init__
def tripwire(self, args, *rest, **kw):
    if kw.get("start_new_session"):
        with open(os.environ["TRIPWIRE_RECORD"], "a") as fh:
            fh.write(" ".join(str(a) for a in args) + "\\n")
        raise OSError("no grandchild, thank you")
    return real(self, args, *rest, **kw)
subprocess.Popen.__init__ = tripwire
sys.argv = ["charter", *sys.argv[1:]]
runpy.run_module("charter", run_name="__main__", alter_sys=True)
"""

_TREE = Path(__file__).resolve().parent.parent


class ARealChildGivenTheSuitesEnvironmentForksNoGrandchild(unittest.TestCase):
    """The measurement #945 was filed on, as a case: a real `charter` process, a plane made a
    moment ago, and the question of what that process forks.

    That fork happens in another process, so `tests._planeguard` never sees it; the tripwire
    above is the only witness. A plane with a clone in its workspace, so the status line has
    something stale for the forge refresh as well as for the version check. Each case runs
    the same child twice — the environment this process hands every child, and that
    environment without the switch — so a tripwire that recorded nothing because it never
    ran cannot pass for a switch that held.
    """

    def _plane(self) -> Path:
        """A plane made a moment ago — one per run, because the first run's lock would
        otherwise hold the second one back and the control would measure the cooldown."""
        plane = Path(tempfile.mkdtemp(prefix="charter-945-child-")).resolve()
        self.addCleanup(shutil.rmtree, plane, True)
        (plane / root.MARKER).write_text("schema = 1\n")
        (plane / "workspaces" / "default" / "somerepo" / ".git").mkdir(parents=True)
        return plane

    def _forks(self, argv: list[str], payload: dict, *, switch: bool) -> list[str]:
        plane = self._plane()
        record = plane / "forks"
        env = {**os.environ, "CHARTER_ROOT": str(plane), "PYTHONPATH": str(_TREE),
               "TRIPWIRE_RECORD": str(record)}
        if not switch:
            env.pop(NAME, None)
        subprocess.run([sys.executable, "-c", _TRIPWIRE, *argv],
                       input=json.dumps({**payload, "cwd": str(plane)}), env=env,
                       cwd=str(plane), capture_output=True, text=True, timeout=120)
        return record.read_text().splitlines() if record.exists() else []

    def _both(self, argv: list[str], payload: dict) -> tuple[list[str], list[str]]:
        held = self._forks(argv, payload, switch=True)
        # The control is a child that drops the switch on purpose, so it is declared — and
        # only after the first run, because the declaration also takes the switch out of
        # this process, which is where the first run's environment came from.
        _planeguard.allow_background_checks(self)
        return held, self._forks(argv, payload, switch=False)

    def test_session_start(self):
        """Since 0.62.2 session start forks no version check even without the switch:
        charter-cp's last release has nothing newer to look for (`update.maybe_spawn`)."""
        held, control = self._both(["hook", "sessionstart"], {"session_id": "t"})
        self.assertFalse(any("_version-check" in f for f in control), control)
        self.assertEqual(held, [])

    def test_the_status_line(self):
        held, control = self._both(["statusline"], {"session_id": "t"})
        # The forge refresh is what the switch still holds back; the version check is off
        # at the source since 0.62.2, switch or not.
        self.assertFalse(any("_version-check" in f for f in control), control)
        self.assertTrue(any("gl-refresh" in f for f in control), control)
        self.assertEqual(held, [])


if __name__ == "__main__":       # pragma: no cover
    unittest.main()
