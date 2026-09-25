"""A probe never runs from inside a probe — including across a process boundary.

#311 bounded re-entry with a counter in :mod:`charter.news`. A counter is process-local,
and one re-entry path leaves the process: `commands_update._handoff` spawns a FRESH charter
running `charter news --since <baseline>`, which probes. Every hop is a new interpreter, so
`_depth` is 0 again at each level and the in-process guard never fires (#314).

Two failures live on that path and they are not the same size.

**The loop.** Each hop is a whole charter start-up rather than a stack frame, so it is
slower and less visible than #311's, and it terminates today only by arithmetic two modules
away — `cmd_update` stamps its baseline before it moves, so a later hop's
`between(installed, installed)` is empty. Nothing asserted that, which is what made it a
defect rather than a design: incidental safety nobody wrote down.

**The side effect.** `check: update …` reaches `_sync_to`, a real `uv tool install`, in the
process that IS the probe — at depth 1, which the counter permits and which no marker in a
child's environment can reach. A probe that installs software is worse than a probe that
hangs, so the mutation is refused on its own account, by asking whether a probe is in
flight rather than by naming commands.

Every test here bounds itself. The cross-process case caps its own hop count and gives
every subprocess an explicit timeout, so a real recursion ends in a failed assertion rather
than a wedged runner — and each hop records how many entries it could see, because a probe
that found nothing to probe passes every timing assertion while proving nothing.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import charter
from charter import (channel, commands, commands_persona, commands_update, harness,
                     instance, news, root)
from tests._isolation import child_plane_env, pin_update_channel

#: The `check:` every test here plants, and the handler it stands on. A `check:` may
#: only name a command `news._PROBEABLE` lists (#317), so the stand-in has to be one
#: an entry could really carry; each test replaces the handler with whatever it needs
#: the probe to do.
STAND_IN, STAND_IN_FN = "persona lint", "cmd_persona_lint"

#: What `charter update` would refuse for reasons that are not this test's. Left in place,
#: they stop the command before it reaches an installer — which is indistinguishable from
#: the guard working, and the suite runs inside exactly the charter checkout `cmd_update`
#: declines to install over.
_CLEAR_THE_WAY = (
    (channel, "running_inside", lambda root: False),
    (instance, "load", lambda root: {}),
    (instance, "locked_version", lambda cfg: None),
    (harness, "current", lambda: None),
    (harness, "get", lambda name: None),
)

#: Hops a test tolerates before it stops the chain itself. One is the guarded answer: the
#: probe's own command spawns one charter, and that charter refuses. The cap exists so an
#: unguarded tree ends red instead of running until something else kills it.
HOP_CAP = 3

#: Seconds any one hop may take. Charter's start-up is ~0.3s; this is a wedge detector,
#: not a performance budget.
HOP_TIMEOUT = 60

#: The repo this test is running from, so a spawned interpreter imports the tree under
#: test rather than whatever `charter` happens to be installed on the machine.
SRC = str(Path(charter.__file__).resolve().parents[1])

#: One hop. Points a fresh charter at the same throwaway news directory, probes the same
#: entry, appends what it saw, and — standing in for `cmd_update`'s handoff — spawns the
#: next hop from inside the probe. The entry's `check:` is dispatched to this, exactly as
#: `check: update` is dispatched to a command that spawns charter.
HOP = '''
import json, os, subprocess, sys
from pathlib import Path

sys.path.insert(0, os.environ["PROBE_SRC"])
from charter import commands_persona, config, news

news._PACKAGED = Path(os.environ["PROBE_NEWSDIR"])
hop = int(os.environ["PROBE_HOP"])
log = Path(os.environ["PROBE_LOG"])
cap = int(os.environ["PROBE_CAP"])


def spawn(args):
    """`check:` lands here — a command that starts another charter, like `_handoff`."""
    if hop >= cap:
        log.write_text(log.read_text() + json.dumps({"hop": hop + 1, "capped": True}) + "\\n")
        return 0
    env = {**os.environ, "PROBE_HOP": str(hop + 1)}
    done = subprocess.run([sys.executable, os.environ["PROBE_SCRIPT"]], env=env,
                          timeout=float(os.environ["PROBE_TIMEOUT"]),
                          capture_output=True, text=True)
    return done.returncode


commands_persona.cmd_persona_lint = spawn
entries = [e for e in news.released() if e.slug == "loop"]
record = {"hop": hop, "released": len(news.released())}
if entries:
    status, why = news.probe(entries[0])
    record.update(status=status, why=why)
log.write_text(log.read_text() + json.dumps(record) + "\\n")
'''


class CrossProcessReentry(unittest.TestCase):
    """The #314 reproduction, with the install replaced by a bare subprocess.

    The real chain runs `uv tool install` on the way, so it is not something a test may
    perform. What is reproduced is the part that matters: a `check:` whose command starts a
    fresh charter that probes the same entry, and therefore re-enters where a process-local
    counter cannot see it.
    """

    def setUp(self):
        self.plane, _ = child_plane_env(self)
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "0.44.0-loop.md").write_text(
            "---\nversion: 0.44.0\nheadline: h\ncheck: persona lint\nadopt: version\n---\nbody\n")
        patch = mock.patch.object(news, "_PACKAGED", self.dir)
        patch.start()
        self.addCleanup(patch.stop)

        self.script = self.dir / "hop.py"
        self.script.write_text(HOP)
        self.log = self.dir / "hops.jsonl"
        self.log.write_text("")

        self.entry, = [e for e in news.released() if e.slug == "loop"]
        # The counterfactual this suite has been burned by: a tree where `news.all()` comes
        # back empty makes every unguarded run finish instantly and look guarded. Nothing
        # below is trustworthy unless the planted entry is really there to be probed.
        self.assertEqual(self.entry.check, STAND_IN)
        self.assertEqual(len(news.released()), 1)

    def _env(self, hop: int) -> dict:
        # `HOP` opens with ``from charter import commands_persona, config, news``, and a
        # charter import resolves a plane from the importing process's own cwd. Every hop
        # runs from the checkout, so every hop — and each one it spawns in turn — used to
        # resolve the developer's LIVE plane. `child_plane_env` makes a throwaway one and
        # ``$CHARTER_ROOT`` points every hop at it instead.
        #
        # Read from `os.environ` at CALL time, not from a snapshot taken in `setUp`: the
        # re-entry marker this whole file is about (`news._ENV`) is set by `_dispatch`
        # while the probe is running, and it is inherited, not passed. A snapshot predates
        # it, and the chain would go on hopping with every guard intact.
        return {**os.environ, root.ENV_VAR: str(self.plane),
                "PROBE_SRC": SRC, "PROBE_NEWSDIR": str(self.dir),
                "PROBE_SCRIPT": str(self.script), "PROBE_LOG": str(self.log),
                "PROBE_HOP": str(hop), "PROBE_CAP": str(HOP_CAP),
                "PROBE_TIMEOUT": str(HOP_TIMEOUT)}

    def _spawn(self, args) -> int:
        done = subprocess.run([sys.executable, str(self.script)], env=self._env(1),
                              timeout=HOP_TIMEOUT, capture_output=True, text=True)
        self.stderr = done.stderr
        return done.returncode

    def _hops(self) -> list[dict]:
        return [json.loads(line) for line in self.log.read_text().splitlines() if line]

    def _probe(self) -> tuple[str, str]:
        with mock.patch.object(commands_persona, STAND_IN_FN, self._spawn):
            started = time.monotonic()
            status, why = news.probe(self.entry)
            self.elapsed = time.monotonic() - started
        return status, why

    def test_the_chain_stops_at_the_first_spawned_charter(self):
        self._probe()
        hops = self._hops()
        self.assertTrue(hops, f"no hop ran at all — the chain never started: {self.stderr}")
        self.assertEqual(
            [h["hop"] for h in hops], [1],
            f"a probe re-entered across {len(hops)} process boundaries — the guard has to "
            f"survive exec, not just recursion")

    def test_the_spawned_charter_could_see_the_entry_it_refused(self):
        """The vacuous pass this file exists to rule out. A hop that found no entries
        probes nothing, spawns nothing, and reports a bounded chain — which is what a
        broken guard and a missing news directory look like from the outside."""
        self._probe()
        hop, = self._hops()
        self.assertEqual(hop["released"], 1,
                         "the spawned charter saw no entries, so it proved nothing")
        self.assertIn("status", hop, "the spawned charter never reached the probe")

    def test_the_re_entered_probe_has_no_answer(self):
        """Bounded is not correct (ADR 0013). The spawned charter's `check:` would exit 0
        the moment the chain is cut, so a guard that only stopped the loop would hand the
        entry back as **adopted** — hidden forever by the bug that hid it."""
        self._probe()
        hop, = self._hops()
        self.assertEqual(hop["status"], news.UNKNOWN)
        self.assertIn("probe", hop["why"])

    def test_the_probe_that_spawned_it_has_no_answer_either(self):
        """The same half, in the direction that needs a channel.

        The entry the OUTER probe is asking about is the one whose `check:` spawned a
        charter that had to be refused — so its exit code is not an answer, whatever it
        says. Nothing in a child can reach its parent's memory, so a refused descendant
        leaves a mark at the path the marker names and this is where it is read. Without
        it the loop is bounded and the entry still comes back adopted, one process further
        away than #311.
        """
        status, why = self._probe()
        self.assertEqual(status, news.UNKNOWN)
        self.assertIn(STAND_IN, why)

    def test_it_finishes_in_bounded_time(self):
        """A wall clock is never the assertion — the hop count is — but a guard that let
        the chain run to the cap would still be slow here, and slow is what the field
        would report."""
        self._probe()
        self.assertLess(self.elapsed, HOP_TIMEOUT,
                        f"one probe took {self.elapsed:.1f}s")


class TheMarkerIsCleanedUp(unittest.TestCase):
    """An environment variable that outlived its probe would disable probing for good, and
    say nothing. That is a worse defect than the one being fixed."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "0.44.0-x.md").write_text(
            "---\nversion: 0.44.0\nheadline: h\ncheck: persona lint\nadopt: version\n---\nbody\n")
        patch = mock.patch.object(news, "_PACKAGED", self.dir)
        patch.start()
        self.addCleanup(patch.stop)
        self.entry, = news.released()

    def _probe_seeing(self, seen: list):
        def cmd(args):
            seen.append(os.environ.get(news._ENV))
            return 0

        with mock.patch.object(commands_persona, STAND_IN_FN, cmd):
            return news.probe(self.entry)

    def test_the_marker_names_this_process_while_the_probe_runs(self):
        seen = []
        self._probe_seeing(seen)
        self.assertEqual(len(seen), 1)
        pid, _, mark = seen[0].partition(":")
        self.assertEqual(pid, str(os.getpid()),
                         "the marker has to name the process running the probe — that is "
                         "what makes a stale one recognisable as debris")
        self.assertTrue(mark, "no way back up: a refused descendant could not report it")

    def test_nothing_is_left_in_the_environment_afterwards(self):
        self.assertNotIn(news._ENV, os.environ)
        self._probe_seeing([])
        self.assertNotIn(news._ENV, os.environ)

    def test_a_value_that_was_already_there_is_put_back(self):
        with mock.patch.dict(os.environ, {news._ENV: "already"}):
            self._probe_seeing([])
            self.assertEqual(os.environ[news._ENV], "already")

    @unittest.skipUnless(os.name == "posix",
                         "liveness is only asked on POSIX — `os.kill` off it would kill")
    def test_a_marker_from_a_dead_process_does_not_disable_probing(self):
        """The leak that would be silent. A marker names the process running the probe; a
        process that is gone is running nothing, so the marker is debris — believed, it
        would turn every probe on that machine into `unknown` until someone thought to look
        at their environment."""
        dead = _a_dead_pid()
        with mock.patch.dict(os.environ, {news._ENV: str(dead)}):
            self.assertEqual(self._probe_seeing([])[0], news.ADOPTED)

    def test_a_marker_from_a_live_ancestor_refuses_the_probe(self):
        ran = []
        with mock.patch.dict(os.environ, {news._ENV: str(os.getppid())}):
            status, why = self._probe_seeing(ran)
        self.assertEqual(status, news.UNKNOWN)
        self.assertEqual(ran, [], "the probe ran underneath another probe")
        self.assertIn("in flight", why)

    def test_the_mark_a_refused_descendant_leaves_is_read_and_removed(self):
        """The marker's other half, and the other thing that could rot in a temp
        directory. Left behind, the next probe in a process with the same PID would read
        somebody else's refusal as its own answer."""
        marks = []

        def cmd(args):
            _, _, mark = os.environ[news._ENV].partition(":")
            Path(mark).touch()      # what a spawned charter does when it declines to probe
            marks.append(mark)
            return 0

        with mock.patch.object(commands_persona, STAND_IN_FN, cmd):
            status, why = news.probe(self.entry)
        self.assertEqual(status, news.UNKNOWN, "an exit code from underneath a refusal is "
                                               "not this entry's answer")
        self.assertFalse(Path(marks[0]).exists(), "the mark outlived the probe that read it")

    def test_a_garbled_marker_is_ignored_rather_than_believed(self):
        with mock.patch.dict(os.environ, {news._ENV: "yes"}):
            self.assertEqual(self._probe_seeing([])[0], news.ADOPTED)



def _a_dead_pid() -> int:
    """A PID that has certainly exited: start one, reap it, reuse its number."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


if __name__ == "__main__":
    unittest.main()
