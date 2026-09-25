"""The suite-wide tripwire that refuses to SPAWN a charter against the developer's plane.

The sibling of `test_plane_write_guard.py`, and it follows the same rule: every case here
installs a THROWAWAY directory as "the real plane" and asserts against that. Pointing a
case at the operator's actual plane to prove a spawn is refused would, the first time the
guard regressed, run `gl-refresh` and `persona _gc` against a live machine — which is the
accident this guard exists to prevent.

**How "it was refused" is told apart from "it silently did nothing".** The fake charter
below writes a marker file when it runs. A refused case asserts both that
:class:`RealPlaneSpawn` was raised AND that the marker is absent; the allowed case asserts
the marker is PRESENT. Without that second half, an absent marker would prove nothing —
"the child never ran" and "the child ran and could not write" look identical, which is a
failure mode this repo has shipped before.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from charter import config, hooks, root
from tests import _envguard, _planeguard


class WhatIsGuarded(unittest.TestCase):
    def test_popen_is_wrapped_on_the_class_at_package_import(self):
        """The CLASS, not the ``subprocess.Popen`` module attribute.

        `subprocess.run`/`check_output`/`check_call` construct the class directly, and so
        does anything that did ``from subprocess import Popen``. A wrapper on the module
        attribute would watch none of them.
        """
        self.assertEqual(getattr(subprocess.Popen.__init__, "__module__", None),
                         "tests._planeguard",
                         "Popen.__init__ is unwrapped — charter children spawn unseen")

    def test_the_guarded_root_is_this_machines_own_plane(self):
        """Armed against the plane the test PROCESS resolved, not some later one.

        Recomputed from `root.find_root` rather than read off `config.ROOT`, which any
        `PersonaIso` case may have repointed by the time this runs.

        ``$CHARTER_ROOT`` is declared unset rather than left ambient, which is what
        `_envguard` asks of any test that depends on it (#519). Saying so is not a
        formality here: the name was scrubbed at install precisely so this walk starts from
        the cwd, and a machine that had exported it would otherwise make this assert about
        the operator's shell.
        """
        _envguard.unset(root.ENV_VAR)
        self.assertIn(os.path.abspath(str(root.find_root())), _planeguard._REAL_ROOT)


#: A program that exists, runs nothing and exits non-zero — the stand-in interpreter for
#: the ``-m charter`` cases, so that a guard which failed to refuse would leave a failed
#: exit rather than run something. Looked up rather than written out: there is no
#: ``/bin/false`` on macOS, so the literal turned a regression in those cases into a
#: `FileNotFoundError` naming a path instead of a failure naming the guard.
_FALSE = shutil.which("false") or "/bin/false"


class _FakePlane(unittest.TestCase):
    """A throwaway plane installed as "the real plane", plus a fake ``charter`` binary."""

    def setUp(self):
        self.real = Path(tempfile.mkdtemp(prefix="spawnguard-real-"))
        self.addCleanup(shutil.rmtree, self.real, True)
        (self.real / root.MARKER).write_text("schema = 1\n")

        self.elsewhere = Path(tempfile.mkdtemp(prefix="spawnguard-else-"))
        self.addCleanup(shutil.rmtree, self.elsewhere, True)
        (self.elsewhere / root.MARKER).write_text("schema = 1\n")

        # A `charter` that leaves evidence. Named `charter` because that is what the guard
        # is looking for at the end of every spelling below, and it makes the "allowed"
        # case a real spawn of a real process rather than an assertion about a decision
        # function.
        self.marker = self.elsewhere / "the-child-ran"
        self.fake = self.elsewhere / "charter"
        self.fake.write_text(f"#!/bin/sh\necho ran > {self.marker}\n")
        self.fake.chmod(0o755)

        self.enterContext(mock.patch.object(
            _planeguard, "_REAL_ROOT",
            (str(self.real), str(self.real.resolve()))))

    def run_fake(self, **kw):
        p = subprocess.Popen([str(self.fake)], **kw)
        p.wait()
        return p


class ARefusedSpawn(_FakePlane):
    def test_a_charter_child_that_would_walk_onto_the_real_plane_is_refused(self):
        """No ``$CHARTER_ROOT``, cwd inside the real plane: exactly the 131 detached
        children #527 measured, which resolved the operator's plane by walking up from
        wherever the test happened to be running."""
        with self.assertRaises(_planeguard.RealPlaneSpawn) as caught:
            self.run_fake(cwd=self.real, env={k: v for k, v in os.environ.items()
                                              if k != root.ENV_VAR})
        self.assertFalse(self.marker.exists(),
                         "refused after delegating — the child ran anyway")
        self.assertIn("REFUSED", str(caught.exception))

    def test_a_charter_root_pointing_at_the_real_plane_is_refused(self):
        """Handing the plane across the boundary only helps if it is a DIFFERENT plane."""
        with self.assertRaises(_planeguard.RealPlaneSpawn):
            self.run_fake(cwd=self.elsewhere,
                          env={**os.environ, root.ENV_VAR: str(self.real)})
        self.assertFalse(self.marker.exists())

    def test_a_dash_m_charter_argv_is_recognised_too(self):
        """`util.self_relaunch_argv`'s spelling — the one every self-relaunch site uses.

        The interpreter is :data:`_FALSE` so that a guard which failed to refuse would
        leave a non-zero exit rather than run anything.
        """
        with self.assertRaises(_planeguard.RealPlaneSpawn):
            subprocess.Popen([_FALSE, "-P", "-m", "charter", "gl-refresh"],
                             cwd=self.real,
                             env={k: v for k, v in os.environ.items()
                                  if k != root.ENV_VAR})

    def test_the_message_names_the_test_and_both_ways_out(self):
        """A tripwire nobody can act on is a tripwire that gets deleted."""
        with self.assertRaises(_planeguard.RealPlaneSpawn) as caught:
            self.run_fake(cwd=self.real, env={k: v for k, v in os.environ.items()
                                              if k != root.ENV_VAR})
        msg = str(caught.exception)
        self.assertIn("ARefusedSpawn.test_the_message_names_the_test_and_both_ways_out",
                      msg)
        self.assertIn("CHARTER_ROOT", msg)      # way out (2): hand it a throwaway plane
        self.assertIn("maybe_spawn", msg)       # way out (1): do not spawn at all
        self.assertIn(str(self.real), msg)      # which plane it would have landed on

    def test_the_message_says_where_that_plane_CAME_FROM(self):
        """#830 put one question to a CI log and the log could not answer it.

        The refusal named the argv it objected to and the plane it objected on behalf of —
        but not where that plane came from, and `_child_plane` has three answers with three
        different bugs behind them. A plane reached by walking up from a cwd nobody
        overrode is the guard's own steady answer, and if it is the operator's, so is every
        other spawn in the run. A plane that arrived as a handed ``$CHARTER_ROOT`` is a
        fixture pointing at the wrong place. A plane that is only `find_root_or_cwd`'s
        unwalked fallback is neither. One line separates them; without it the reader is
        reduced to reproducing a failure that fired once in two runs of one commit.
        """
        stranded = {k: v for k, v in os.environ.items() if k != root.ENV_VAR}

        # (1) the walk, from a cwd the spawn did not override.
        with self.assertRaises(_planeguard.RealPlaneSpawn) as caught:
            self.run_fake(cwd=self.real, env=stranded)
        self.assertIn(f"the walk up from the spawn's own cwd={self.real}",
                      str(caught.exception))

        # (2) a pointer handed across the boundary — a fixture aiming at the wrong plane,
        #     which reads nothing like (1) and used to print the same sentence.
        with self.assertRaises(_planeguard.RealPlaneSpawn) as caught:
            self.run_fake(cwd=self.elsewhere,
                          env={**stranded, root.ENV_VAR: str(self.real)})
        self.assertIn(f"${root.ENV_VAR}={self.real}, inherited from the spawn's own env=",
                      str(caught.exception))

        # (3) no plane above the child at all, so `find_root_or_cwd` makes its cwd one.
        with self.assertRaises(_planeguard.RealPlaneSpawn) as caught:
            self.run_fake(cwd=self.real,
                          env={**stranded, root.ENV_VAR: str(self.elsewhere / "gone")})
        self.assertIn("found no plane, so `find_root_or_cwd`'s fallback",
                      str(caught.exception))

    def test_it_is_a_base_exception_so_charters_own_fallbacks_cannot_eat_it(self):
        """`glstate.maybe_spawn` and `update.maybe_spawn` both wrap their `Popen` in
        `except Exception: return`. A tripwire those can catch reports nothing at all."""
        self.assertTrue(issubclass(_planeguard.RealPlaneSpawn, BaseException))
        self.assertFalse(issubclass(_planeguard.RealPlaneSpawn, Exception))


class AnAllowedSpawn(_FakePlane):
    def test_a_child_handed_a_throwaway_plane_really_runs(self):
        """The other half of the evidence: this is what proves an absent marker above
        means "never ran" rather than "could not write"."""
        p = self.run_fake(cwd=self.elsewhere,
                          env={**os.environ, root.ENV_VAR: str(self.elsewhere)})
        self.assertEqual(p.returncode, 0)
        self.assertTrue(self.marker.exists())

    def test_a_child_whose_cwd_is_a_throwaway_plane_really_runs(self):
        """`$CHARTER_ROOT` is not the only isolation that works — a cwd inside another
        plane resolves that one, and `charter init` in a fresh directory resolves none."""
        p = self.run_fake(cwd=self.elsewhere,
                          env={k: v for k, v in os.environ.items()
                               if k != root.ENV_VAR})
        self.assertEqual(p.returncode, 0)
        self.assertTrue(self.marker.exists())

    def test_a_child_that_is_not_charter_is_never_examined(self):
        """The guard is about charter's own plane resolution. Refusing `git`, `tmux` or
        `sh` because they happen to run inside the checkout would make the suite
        unusable — and none of them reads a `charter.toml`."""
        out = subprocess.run([sys.executable, "-c", "print('hi')"], cwd=self.real,
                             capture_output=True, text=True,
                             env={k: v for k, v in os.environ.items()
                                  if k != root.ENV_VAR})
        self.assertEqual(out.stdout.strip(), "hi")


class EverySpellingThatReachesCharter(_FakePlane):
    """The question is "will this child resolve the operator's plane as charter", not "is
    this argv one of the spellings charter's own code uses".

    Round one asked the second question, and the difference was measured against this same
    ``_REAL_ROOT``: ``[python, "-m", "charter", "--version"]`` was refused, while
    ``[python, "-c", "from charter import config; print(config.ROOT)"]``, ``["/bin/sh",
    "-c", "<python> -m charter --version"]`` and the same command as a ``shell=True``
    string all RAN, against the real plane. Two of those were not hypothetical: nine
    charter-importing ``python -c`` children per suite run were being waved through, and a
    third site (`test_news_cross_process`) spawned a chain of them.

    Every case here is a REAL spawn attempt, with a canary the child would leave behind.
    An `assertRaises` alone would not tell "refused" from "refused after the child had
    already gone" — the failure mode this file's header names.
    """

    def setUp(self):
        super().setUp()
        self.canary = self.elsewhere / "the-child-ran-anyway"
        self.stranded = {k: v for k, v in os.environ.items() if k != root.ENV_VAR}

    def refuse(self, args, **kw):
        """Assert *args* is refused — and stay finite if it is not.

        Two things this does NOT do with an `assertRaises` block, both of them lessons from
        the suite's own open hangs (#545, #546). It never `wait()`s on a child it did not
        expect to exist: a regression that lets `watch -n 1 charter` through would otherwise
        park the whole run forever on a command that by definition never exits. And it hands
        every child ``/dev/null`` for stdin, so a `su` that reaches a real terminal asks
        nobody for a password. A guard's own test may not be the thing that makes a red run
        impossible to get.

        Evidence is cleared FIRST, because several of these run as `subTest`s inside one
        case and share one setUp: a marker left by an earlier spelling would fail every
        later one on evidence that is not about it, turning one red case into seven and
        hiding which spelling actually got through.
        """
        for evidence in (self.canary, self.marker):
            if evidence.exists():
                evidence.unlink()
        kw.setdefault("stdin", subprocess.DEVNULL)
        try:
            child = subprocess.Popen(args, cwd=self.real, env=self.stranded, **kw)
        except _planeguard.RealPlaneSpawn as refused:
            self.assertFalse(self.canary.exists(),
                             "refused after delegating — the child ran anyway")
            self.assertFalse(self.marker.exists())
            return str(refused)
        child.kill()
        child.wait()
        self.fail(f"not refused: {args!r} spawned a charter that would resolve "
                  f"{self.real} — the guarded plane")

    def test_a_python_dash_c_that_imports_charter(self):
        """The shape that was live in the suite. The write comes FIRST, so a guard that
        let this through leaves the canary whatever the import then does."""
        self.refuse([sys.executable, "-c",
                     f"open({str(self.canary)!r}, 'w').close()\nimport charter"])

    def test_a_dash_c_that_names_the_module_as_a_string(self):
        """``__import__("charter")`` reaches the same import by a different token."""
        self.refuse([sys.executable, "-c",
                     f"open({str(self.canary)!r}, 'w').close()\n__import__('charter')"])

    def test_a_shell_command_string(self):
        self.refuse(["/bin/sh", "-c", f"{self.fake} --version"])

    def test_the_same_command_with_shell_true(self):
        self.refuse(f"{self.fake} --version", shell=True)

    def test_a_command_substitution_inside_an_assignment(self):
        """`hooks/hooks.json`'s own shape — ``out="$(charter doctor 2>&1)" || …``. Every
        lexer reads that as an assignment, so the invocation is in no command position at
        all; it is one for `_substitution_bodies`."""
        self.refuse(["/bin/sh", "-c", f'out="$({self.fake} doctor 2>&1)" || true'])

    def test_a_quoted_command_substitution_that_is_not_an_assignment(self):
        """The same clause as above with the assignment taken away, and QUOTED — which is
        what leaves the substitution scan as the only reader of it.

        Unquoted, ``$(…)``'s parentheses are punctuation to `shlex` and the segmenter walks
        straight into the inner command on its own. Quoted, the whole substitution is one
        argument to `echo`, in no command position and in no assignment. Two guards that
        cover each other look like one guard until one of them is taken away.
        """
        self.refuse(["/bin/sh", "-c", f'echo "$({self.fake} --version)"'])

    def test_an_assignment_that_names_charter(self):
        """``c=charter; eval $c``. `eval`'s argument is a variable, so the wrapper clause
        sees no charter in it and the command word is `eval` rather than something
        computed: the assignment is the only place the name appears."""
        self.refuse(["/bin/sh", "-c", f"c={self.fake}; eval $c --version"])

    def test_a_command_word_the_shell_computes(self):
        """The name reaches the command position through the environment, and the only
        charter in the string itself is a COMMENT — which `shlex` strips before any reader
        sees it. What is left is ``$CBIN --version``, and a command word this cannot
        resolve is refused rather than guessed at."""
        self.stranded["CBIN"] = str(self.fake)
        self.refuse(["/bin/sh", "-c", "# this line starts charter\n$CBIN --version"])

    def test_a_wrapper_that_takes_a_command_as_its_arguments(self):
        """`nice` rather than `sudo`: if this ever stops being refused the fallout is the
        fake charter running, not a password prompt on a real machine.

        The ARGV form is the one that matters and it is `test_a_wrapper_in_an_argv…`
        below, not this one. This case wrote only the shell-string spelling for a round,
        and the shell string is the form that already had a wrapper clause — so the plain
        ``["nice", "charter", "docs"]`` went unexercised and ran.
        """
        self.refuse(["/bin/sh", "-c", f"nice {self.fake} --version"])

    def test_a_wrapper_in_an_argv_is_followed_to_the_program(self):
        """The plainest spelling there is, and it RAN: ``["nice", "charter", "docs"]``.

        `_cmd_launches_charter` read `nice` as "a command called nice" and stopped. The
        wrapper follow existed only inside shell STRINGS, while `_COMMAND_WRAPPERS`' own
        docstring justified itself with ``sudo charter doctor`` — an argv — and the case
        above pinned only the string form. A reason that names a shape the code cannot see
        is the shape this whole round was sent back over.

        Each of these is now answered by `charter.hooks._split_env_chdir`, production's own
        reader, including each wrapper's own option arity: `nice -n 10`, `timeout`'s bare
        duration, `xargs -n1`, `stdbuf -o0` glued, and `env -i`, which is the flag a flat
        "wrappers take a value" table gets wrong.
        """
        for argv in (["nice", str(self.fake), "--version"],
                     ["nice", "-n", "10", str(self.fake), "--version"],
                     ["nohup", str(self.fake), "--version"],
                     ["env", "-i", str(self.fake), "--version"],
                     ["stdbuf", "-o0", str(self.fake), "--version"],
                     ["timeout", "5", str(self.fake), "--version"],
                     ["timeout", "--preserve-status", "5", str(self.fake)],
                     ["xargs", "-n1", str(self.fake)],
                     ["nice", "-n", "10", "nohup", str(self.fake), "--version"]):
            with self.subTest(argv=argv):
                self.refuse(argv)

    def test_a_wrapper_whose_grammar_cannot_be_followed_refuses_on_the_word(self):
        """`flock <file> <cmd>` and `watch -n1 <cmd>` put a positional of their own in
        front of the program, so no reader that names "the program" can name charter here.

        These are the reason the wrapper clause survives alongside the production split
        rather than being replaced by it: where the program cannot be named, the word
        appearing ANYWHERE after the wrapper is what refuses. `su -c` is here for the same
        reason `eval` is — its argument is a command STRING, which production's Bash guard
        states as a limit it does not follow.
        """
        for argv in (["flock", str(self.elsewhere / "lock"), str(self.fake), "--version"],
                     ["watch", "-n", "1", str(self.fake), "--version"],
                     ["su", "-c", f"{self.fake} --version"]):
            with self.subTest(argv=argv):
                self.refuse(argv)

    def test_a_bundled_short_option_reaches_a_shells_command_string(self):
        """``bash -lc 'charter docs'`` is what a login shell is SPELLED, and it ran.

        `_python_launches_charter` already walked a bundle — that is how ``-Pmcharter`` was
        caught — while the shell branch matched ``tok == "-c"`` and ``tok.startswith("-c")``
        and saw none of `-lc`, `-ec`, `-xc`, `-ic`. One walk, `_bundled_option`, now serves
        both. `-o pipefail` is in here because it is the shell short option that takes a
        VALUE: a walk that read its value as more bundled letters would be the mirror of
        the `env -i` mistake production's per-wrapper table exists to avoid.
        """
        for argv in (["/bin/bash", "-lc", f"{self.fake} --version"],
                     ["/bin/sh", "-ec", f"{self.fake} --version"],
                     ["/bin/sh", "-xc", f"{self.fake} --version"],
                     ["/bin/sh", "-ic", f"{self.fake} --version"],
                     ["/bin/sh", f"-c{self.fake} --version"],
                     ["/bin/bash", "-o", "pipefail", "-c", f"{self.fake} --version"],
                     ["/bin/bash", "--login", "-c", f"{self.fake} --version"]):
            with self.subTest(argv=argv):
                self.refuse(argv)

    def test_env_split_string_is_not_a_way_through(self):
        """`env -S '<cmd>'` packs a whole command into ONE token, and it printed the
        guarded plane.

        The old reader skipped `-S` as a value-taking option, which left an EMPTY argv —
        and an empty argv was answered "not charter". Its own docstring had warned against
        exactly that (*"a guard guessing at an unknown option's arity would start skipping
        the command word itself"*) and then committed it on the one flag whose value IS the
        command word. Production said the same thing and got it right
        (`hooks._SPLIT_STRING_FLAGS`, pinned by
        `test_guard_parsing.test_env_split_string_is_not_a_way_through`, whose name this
        borrows deliberately), and that is the code this now calls.
        """
        for argv in (["env", "-S", f"{self.fake} --version"],
                     ["env", f"-S{self.fake} --version"],
                     ["env", f"--split-string={self.fake} --version"],
                     ["env", "-S", f"nice {self.fake} --version"],
                     ["env", "-S",
                      f"{sys.executable} -c 'from charter import config; print(config)'"]):
            with self.subTest(argv=argv):
                self.refuse(argv)

    def test_a_packed_command_that_itself_contains_an_equals_sign(self):
        """``env -Sfoo=1 charter docs``, which reusing production's reader let through.

        `hooks._split_env_chdir` used to read the ``--split-string=`` spelling before the
        glued ``-S…`` one, so it split this at the FIRST ``=`` — the program came back ``1``
        and the charter after it was never looked at. Reuse means inheriting that, so the
        ordering was repaired here on the way in while #547 was open.

        The same input was a live bypass of charter's Bash tool-gate — measured:
        ``env -Sfoo=1 cat .charter/vaults/x.json`` and ``env -Sfoo=1 charter secret get v k
        --reveal --force`` were both ALLOWED while the unwrapped commands were denied. #547
        fixed the ordering in production (`hooks._flag_name_value`), the repair here is
        deleted, and this case now passes on production's parse alone — which is the second,
        free regression test that fix came with. `tests/test_guard_attached_option_values.py`
        holds the six-row table on the production side.
        """
        for argv in ([str(self.fake), "docs"],
                     ["env", f"-Sfoo=1 {self.fake} docs"],
                     ["env", "-Sfoo=1", str(self.fake), "docs"],
                     ["env", f"--split-string=foo=1 {self.fake} docs"],
                     ["/bin/sh", "-c", f"env -Sfoo=1 {self.fake} docs"]):
            with self.subTest(argv=argv):
                self.refuse(argv)

    def test_the_name_glued_to_an_option_letter_still_reaches_the_lexer(self):
        """``env -Scharter --version``, as a shell STRING, and it is the GATE that misses.

        `-S` puts a word character immediately in front of the name, so the word test —
        which exists to keep ``<checkout>/charter/sub`` from reading as a command — answers
        "charter is not named here" about a string whose entire content is a charter
        invocation, and the string is never lexed at all. A gate that can only cause misses
        must not be the thing deciding: :data:`~tests._planeguard._CHARTER_MENTION` asks
        for the name and nothing about its boundaries, and the word test still decides what
        is a command once the lexer has run.
        """
        bindir = self.elsewhere / "onpath"
        bindir.mkdir()
        shutil.copy(self.fake, bindir / "charter")
        (bindir / "charter").chmod(0o755)
        self.stranded["PATH"] = f"{bindir}:{self.stranded.get('PATH', '')}"
        self.refuse(["/bin/sh", "-c", "env -Scharter --version"])

    def test_the_program_name_is_case_folded_too(self):
        """``["CHARTER", "docs"]`` ran, against a guarded plane.

        Same class as production's `test_the_program_name_is_case_folded_too`, and the same
        one-line answer: on the filesystems this runs on `CHARTER` and `charter` are one
        binary, so a guard that matches one casing has a Shift key for a bypass. The
        harness guard was the last one in the tree still comparing
        ``os.path.basename(parts[0]) == "charter"``.
        """
        upper = self.elsewhere / "CHARTER"
        # On a case-INSENSITIVE filesystem this IS `self.fake`, written back unchanged —
        # which is the whole point of the case: one file, two spellings, one binary.
        upper.write_text(self.fake.read_text())
        upper.chmod(0o755)
        self.refuse([str(upper), "docs"])
        self.refuse(["/bin/sh", "-c", f"{upper} docs"])
        self.refuse([_FALSE, "-m", "CHARTER", "gl-refresh"])

    def test_the_pre_rename_binary_is_charter_too(self):
        """`edm` is charter's former name, and a machine that still has it on `PATH` has a
        binary that resolves a plane. Production keeps it in `_CHARTER_PROGS` for exactly
        that reason; this reads the same constant rather than deciding again."""
        edm = self.elsewhere / "edm"
        edm.write_text(self.fake.read_text())
        edm.chmod(0o755)
        self.refuse([str(edm), "docs"])
        self.refuse(["nice", str(edm), "docs"])

    def test_an_interpreter_is_what_it_resolves_to_not_what_it_is_called(self):
        """``Popen([<symlink to python3>, "-c", "import charter"])`` ran.

        The guard read the LINK's name, found neither `python` nor `sys.executable`'s
        basename in it, and answered "not an interpreter". What the child execs is decided
        by the kernel, not by the spelling: a path is followed to what is really there, a
        RELATIVE path against the child's own cwd — `Popen` chdirs before it execs — and a
        bare name along the child's own ``PATH``.
        """
        link = self.elsewhere / "notpython"
        os.symlink(sys.executable, link)
        self.refuse([str(link), "-c", "import charter"])

        # relative: it has to live in the plane the child is given, because that is the
        # directory the name is resolved against.
        os.symlink(sys.executable, self.real / "notpython")
        self.refuse(["./notpython", "-c", "import charter"])

    def test_a_bare_name_is_looked_up_on_the_childs_own_path(self):
        """``Popen(["charter", "--version"], env={"PATH": …})`` — the spelling charter's own
        hooks use, with nothing but ``PATH`` deciding which binary runs."""
        bindir = self.elsewhere / "bin"
        bindir.mkdir()
        shutil.copy(self.fake, bindir / "charter")
        (bindir / "charter").chmod(0o755)
        self.stranded["PATH"] = f"{bindir}:{self.stranded.get('PATH', '')}"
        self.refuse(["charter", "--version"])
        self.refuse(["/bin/sh", "-c", f"PATH={bindir}:$PATH charter --version"])

    def test_a_program_is_what_it_resolves_to_whatever_its_arguments_look_like(self):
        """``["tmux", "-L", <sock>, "attach", …]`` ran charter, when that ``tmux`` was a link
        to it (#967).

        The resolution above used to be asked only of an argv that reached an interpreter
        — a ``-c``, a ``-m`` or a ``.py`` — so every other shape was judged by the word
        written in ``argv[0]``. That is the shape charter's own frame code talks to tmux in,
        and a ``tmux``, ``git`` or ``ssh`` first on the child's ``PATH`` is what the kernel
        execs whatever follows it on the command line.
        """
        bindir = self.elsewhere / "shims"
        bindir.mkdir()
        os.symlink(self.fake, bindir / "tmux")
        self.stranded["PATH"] = f"{bindir}:{self.stranded.get('PATH', '')}"
        attach = ["-L", "spawnguard-967", "attach", "-t", "s0"]
        self.refuse(["tmux", *attach])
        self.refuse([str(bindir / "tmux"), *attach])

    def test_a_relative_path_entry_is_looked_up_from_the_childs_cwd(self):
        """``cwd=<plane>, PATH="bin:…"`` with ``<plane>/bin/tmux`` a link to charter: the
        child ran the link while the guard said "not charter" (#967, found fixing it).

        `Popen` joins each ``PATH`` entry to the name in the parent and tries them AFTER the
        chdir, so a relative entry — and an empty one, which means the current directory —
        is the CHILD's directory. `shutil.which` read both against this process's cwd, which
        is the checkout, and found nothing there. Asked of the plain argv and of the ``-c``
        shape, which resolved the same wrong way before the gate came out.
        """
        (self.real / "bin").mkdir()
        os.symlink(self.fake, self.real / "bin" / "tmux")
        os.symlink(self.fake, self.real / "tmux")
        path = self.stranded.get("PATH", "")
        # Both FIRST on the PATH: a relative entry after the real one would lose to a real
        # `tmux` for the child too, and then refusing it would be the guard that is wrong.
        for entries in (f"bin:{path}", f":{path}"):
            self.stranded["PATH"] = entries
            # A socket of its own in both, or `RealTmuxReach` answers first — correctly.
            for argv in (["tmux", "-L", "spawnguard-967", "attach"],
                         ["tmux", "-L", "spawnguard-967", "-c", "x"]):
                with self.subTest(PATH=entries.replace(path, "…"), argv=argv):
                    self.refuse(argv)

    def test_an_interpreter_under_another_name_is_asked_about_a_script_without_py(self):
        """The same gap one step in: a ``git`` that is really ``python3``, handed a script
        whose name carries no ``.py``. No ``-c``, no ``-m``, no suffix — so the old gate
        never looked, and the interpreter ran charter's import unread."""
        bindir = self.elsewhere / "shims"
        bindir.mkdir()
        os.symlink(sys.executable, bindir / "git")
        self.stranded["PATH"] = f"{bindir}:{self.stranded.get('PATH', '')}"
        probe = self.elsewhere / "probe"
        probe.write_text(f"open({str(self.canary)!r}, 'w').close()\nimport charter\n")
        self.refuse(["git", str(probe)])

    def test_an_env_wrapper_in_front_of_the_binary(self):
        """``env -u X <charter>``. The ``-m charter`` adjacency below would answer the
        other spelling on its own; nothing but reading past `env` answers this one."""
        self.refuse(["env", "-u", "NOTHING", str(self.fake), "--version"])

    def test_a_dash_c_body_that_will_not_tokenize(self):
        """Undecidable, and refusal is the direction that is safe to be wrong in.

        No canary here, and deliberately: source that does not compile runs nothing, so an
        absent canary would be true however this went. The refusal itself is the assertion.
        """
        with self.assertRaises(_planeguard.RealPlaneSpawn):
            subprocess.Popen([sys.executable, "-c", "import ((("],
                             cwd=self.real, env=self.stranded).wait()

    def test_a_script_that_cannot_be_read(self):
        """Same rule, the other unreadable input. `python <gone>.py` fails either way; what
        must not happen is the guard deciding "not charter" because it could not look."""
        with self.assertRaises(_planeguard.RealPlaneSpawn):
            subprocess.Popen([sys.executable, str(self.elsewhere / "gone.py")],
                             cwd=self.real, env=self.stranded).wait()

    def test_a_child_that_imports_the_test_package(self):
        """``import tests`` arms these guards, which imports `charter.config`, which
        resolves a plane — with the word never appearing. It was the last child in the
        suite still landing on the operator's plane.

        And it is the one child ``$CHARTER_ROOT`` cannot rescue: `_envguard` scrubs the
        charter namespace at import of this package, before `charter.config` loads, so the
        cwd is what decides. `test_no_test_reads_the_operators_shell` runs from a throwaway
        plane with ``$PYTHONPATH`` for exactly that reason.
        """
        msg = self.refuse([sys.executable, "-c",
                           f"open({str(self.canary)!r}, 'w').close()\nimport tests"])
        # And the message has to SAY so. A refusal whose stated remedy does not work for
        # the case it just refused is the shape this round was sent back over: a docstring
        # pointing at something the code cannot see.
        self.assertIn("cwd inside a throwaway plane", msg)
        self.assertIn("PYTHONPATH", msg)

    def test_a_shell_string_that_will_not_lex(self):
        """Undecidable, and refusal is the direction that is safe to be wrong in."""
        self.refuse(["/bin/sh", "-c", f'{self.fake} "--version'])

    def test_a_module_of_the_charter_package_run_by_path(self):
        """``python <plane>/charter/__main__.py``. Reading the file would not answer it —
        charter's real ``__main__.py`` reaches the CLI through ``from .cli import main``
        and never writes the word — so the package directory in the path is what does."""
        pkg = self.elsewhere / "tree" / "charter"
        pkg.mkdir(parents=True)
        (pkg / "__main__.py").write_text(f"open({str(self.canary)!r}, 'w').close()\n")
        self.refuse([sys.executable, str(pkg / "__main__.py")])

    def test_a_script_file_that_imports_charter(self):
        """A probe written to a temp file: nothing in its NAME says charter, and the guard
        reads it rather than guessing."""
        probe = self.elsewhere / "probe.py"
        probe.write_text(f"open({str(self.canary)!r}, 'w').close()\nimport charter\n")
        self.refuse([sys.executable, str(probe)])

    def test_an_env_wrapper_around_the_dash_m_spelling(self):
        """The suite's own gate is run as ``env -u CHARTER_SESSION_ID … python3 -m …``."""
        self.refuse(["env", "-u", "NOTHING", _FALSE, "-m", "charter", "gl-refresh"])

    def test_the_interpreter_is_named_by_executable_rather_than_argv(self):
        """``Popen(["x"], executable=".../charter")`` runs charter and says ``x``."""
        self.refuse(["not-charter", "--version"], executable=str(self.fake))

    def test_a_bare_path_object_as_the_whole_command(self):
        """`Popen` takes one path-like as the command. A `Path` is not iterable, so a
        reader that went straight to the sequence branch would get `TypeError` and answer
        "not charter" — the shape of every hole this recogniser has had."""
        self.refuse(self.fake)

    def test_cwd_and_env_are_read_when_they_are_passed_positionally(self):
        """`Popen`'s signature puts ``cwd`` ninth and ``env`` tenth. A guard that read only
        ``**kw`` would answer "no cwd, no env" here and ask `find_root` about this process
        instead — silently, and in the direction that allows."""
        with self.assertRaises(_planeguard.RealPlaneSpawn):
            subprocess.Popen([str(self.fake)], -1, None, None, None, None, None, True,
                             False, str(self.real), self.stranded).wait()
        self.assertFalse(self.marker.exists())


class SpellingsThatAreNotASpawn(_FakePlane):
    """The other half, and the reason the recogniser lexes instead of grepping.

    A guard that refused on the word alone would be conservative in the direction that is
    safe — and would also refuse `test_toolgate`'s comparison of shlex's parse against a
    real bash's, whose corpus contains the STRING ``charter "sec"'ret' list v``, and every
    tmux fixture whose argv quotes a path inside the checkout. Each of these really runs.
    """

    def setUp(self):
        super().setUp()
        self.ran = self.elsewhere / "it-ran"
        self.stranded = {k: v for k, v in os.environ.items() if k != root.ENV_VAR}

    def allow(self, args, **kw):
        p = subprocess.Popen(args, cwd=self.real, env=self.stranded, **kw)
        self.assertEqual(p.wait(), 0)
        self.assertTrue(self.ran.exists(), "the child did not run")
        return self.ran.read_text()

    def test_charter_as_an_argument_to_another_command(self):
        """`test_toolgate` runs exactly this: bash, asked to echo a corpus entry back."""
        self.assertEqual(
            self.allow(["/bin/sh", "-c", f"printf %s charter > {self.ran}"]), "charter")

    def test_a_path_that_merely_contains_the_word(self):
        """``cd ~/IdeaProjects/charter/tests`` is not a charter spawn, and the suite is
        full of children whose argv names a path inside the checkout."""
        inside = self.elsewhere / "tree" / "charter"
        inside.mkdir(parents=True)
        self.assertEqual(
            self.allow(["/bin/sh", "-c", f"ls -d {inside} > {self.ran}"]).strip(),
            str(inside))

    def test_a_python_child_whose_only_charter_is_inside_a_string_literal(self):
        """`tokenize` is what tells a NAME from a path: `test_frame_tmux_integration`
        spawns ``python -c "open('<checkout>/…', 'w').close()"`` as a hostile-argv fixture,
        and it has no charter import in it."""
        path = self.elsewhere / "tree" / "charter" / "canary"
        path.parent.mkdir(parents=True)
        self.allow([sys.executable, "-c",
                    f"open({str(path)!r}, 'w').close()\n"
                    f"open({str(self.ran)!r}, 'w').write('ok')"])
        self.assertTrue(path.exists())

    def test_a_wrapped_command_whose_argument_is_a_path_inside_the_checkout(self):
        """Where the word test's shape earns itself. ``charter`` followed by ``/`` is a
        directory on the way to something else, not a command — so ``nice ls -d
        <checkout>/charter/sub`` is a wrapper carrying a PATH, and a regex that stopped one
        character earlier would refuse it as a wrapper carrying charter."""
        inside = self.elsewhere / "tree" / "charter" / "sub"
        inside.mkdir(parents=True)
        self.assertEqual(
            self.allow(["/bin/sh", "-c", f"nice ls -d {inside} > {self.ran}"]).strip(),
            str(inside))

    def test_a_shell_string_with_no_mention_of_charter_is_never_lexed(self):
        # `.resolve()`, because macOS's ``/tmp`` is a symlink and ``pwd`` reports the
        # resolved spelling — the same two-spellings problem `_REAL_ROOT` carries.
        self.assertEqual(self.allow(["/bin/sh", "-c", f'pwd > "{self.ran}"']).strip(),
                         str(self.real.resolve()))

    def test_a_name_buried_in_a_longer_word_does_not_decide_an_unlexable_string(self):
        """#830: a `bash -c printf` refused against the operator's real plane, in one of
        two runs of the SAME commit — and the argv spawns no charter at all.

        Nothing raced. `tempfile` had drawn the directory name ``tmpq71ovzj50hedm9za``, and
        three of its eight random characters spell ``edm``, charter's pre-rename binary.
        That is enough for the mention GATE, which asks for the name and nothing about its
        boundaries; `shlex` cannot lex bash's ``$'…'`` ANSI-C quoting, so nothing was ever
        segmented; and "undecidable" answered charter. The gate was the whole decision —
        which is exactly what its own docstring says it must never be.

        The second name is the same defect with the coin taken out: every throwaway plane
        `tests._isolation` makes is ``edm-test-…``, so those three letters are in the argv
        of anything that hands such a path to a shell.
        """
        for name in ("tmpq71ovzj50hedm9za", "edm-test-9f2c"):
            with self.subTest(name=name):
                out = self.elsewhere / name / "it-ran"
                out.parent.mkdir()
                # Valid bash that `shlex` will not lex: the backslash inside `$'…'` is an
                # escape to bash and an ordinary character to shlex, which leaves shlex
                # holding an unbalanced quote.
                p = subprocess.Popen(["bash", "-c", f"printf %s $'a\\'b' > {out}"],
                                     cwd=self.real, env=self.stranded)
                self.assertEqual(p.wait(), 0)
                self.assertEqual(out.read_text(), "a'b", "the child did not run")


class AResolutionThatCannotFinishStillDecides(_FakePlane):
    """`_program_names` runs inside every `Popen` the suite makes, not only the ones whose
    argv reaches an interpreter (#967) — so each way a ``PATH`` lookup can fail to finish
    has to leave the spawn running rather than raise out of `Popen` into a test that never
    mentioned charter.

    Every case is a real ``touch`` with nothing but a file after it, the shape the old gate
    never resolved, and asserts the file is there: a guard that refused, or raised, or
    quietly skipped the spawn all fail it.
    """

    def setUp(self):
        super().setUp()
        self.ran = self.elsewhere / "it-ran"
        self.stranded = {k: v for k, v in os.environ.items() if k != root.ENV_VAR}

    def touch(self, **kw):
        kw.setdefault("cwd", self.real)
        p = subprocess.Popen(["touch", str(self.ran)], stdin=subprocess.DEVNULL, **kw)
        self.assertEqual(p.wait(), 0)
        self.assertTrue(self.ran.exists(), "the child did not run")

    def test_an_unreadable_path_entry(self):
        locked = self.elsewhere / "locked"
        locked.mkdir()
        locked.chmod(0)
        self.addCleanup(locked.chmod, 0o755)   # before the rmtree setUp registered
        self.touch(env={**self.stranded, "PATH": f"{locked}:{self.stranded['PATH']}"})

    def test_a_dangling_link_first_on_path(self):
        bindir = self.elsewhere / "shims"
        bindir.mkdir()
        os.symlink(self.elsewhere / "gone", bindir / "touch")
        self.touch(env={**self.stranded, "PATH": f"{bindir}:{self.stranded['PATH']}"})

    def test_relative_and_empty_path_entries(self):
        self.touch(env={**self.stranded,
                        "PATH": f"no/such/bin::.:{self.stranded['PATH']}"})

    def test_relative_entries_for_a_child_with_no_cwd_of_its_own(self):
        """Without ``cwd=`` the child starts where this process is, so that is what the
        entries are read against — the one case with no child directory to join them to."""
        self.touch(cwd=None, env={**self.stranded,
                                  "PATH": f"no/such/bin::.:{self.stranded['PATH']}"})

    def test_a_child_with_no_path_at_all(self):
        """No ``PATH`` in *env* means `os.defpath` for the child, not this process's."""
        env = {k: v for k, v in self.stranded.items() if k != "PATH"}
        self.touch(env=env)

    def test_a_child_that_inherits_this_processs_environment(self):
        self.touch()


class WhatAnArgvCannotSay(_FakePlane):
    """The guard's ceiling, stated where it costs something rather than left to be
    discovered — the same shape as
    `test_an_unlexable_string_that_names_charter_only_glued_to_a_word_is_the_price`.

    An argv guard follows what the KERNEL follows to find a program: a path, the child's
    ``PATH``, a symlink. It does not follow what the program does once it runs. A shim
    named ``tmux`` whose body is ``exec charter "$@"`` resolves to itself, and the only way
    to know it runs charter is to read the script and interpret it — a shell's job, and a
    guessing game for a guard. #967's own repro is exactly that shim, and it is not refused.
    `tests._planeguard._program_names` says so in its docstring; a change that reaches
    further turns this case red and owes that paragraph an edit.
    """

    def test_a_script_shim_that_execs_charter_under_another_name_is_the_ceiling(self):
        stranded = {k: v for k, v in os.environ.items() if k != root.ENV_VAR}
        attach = ["tmux", "-L", "spawnguard-967", "attach", "-t", "s0"]

        # Positive control: the same name as a LINK to the same charter is refused, so the
        # guard is armed and reading this child's PATH. Without it an allowed spawn below
        # would pass just as well against a guard that had been deleted.
        links = self.elsewhere / "links"
        links.mkdir()
        os.symlink(self.fake, links / "tmux")
        with self.assertRaises(_planeguard.RealPlaneSpawn):
            subprocess.Popen(attach, cwd=self.real, stdin=subprocess.DEVNULL,
                             env={**stranded, "PATH": f"{links}:{stranded['PATH']}"})
        self.assertFalse(self.marker.exists())

        shims = self.elsewhere / "shims"
        shims.mkdir()
        (shims / "tmux").write_text(f'#!/bin/sh\nexec {shlex.quote(str(self.fake))} "$@"\n')
        (shims / "tmux").chmod(0o755)
        p = subprocess.Popen(attach, cwd=self.real, stdin=subprocess.DEVNULL,
                             env={**stranded, "PATH": f"{shims}:{stranded['PATH']}"})
        self.assertEqual(p.wait(), 0)
        self.assertTrue(self.marker.exists(),
                        "the shim did not reach charter, so this pins nothing about it")


class WhatDecidesAnUndecidableShellString(unittest.TestCase):
    """#830, at the decision function rather than through a spawn.

    `_shell_launches_charter` has three exits that answer "charter" without having read a
    command position at all: nesting past the fourth level, a string that will not lex, and
    a command word the shell computes. Each is reached only because the mention gate let
    the string through, so on those three the gate is not a gate — it is the verdict. And
    the gate matches a bare SUBSTRING by design, on the promise (its own docstring) that
    "the word test still decides what is a COMMAND once the string is lexed". Where nothing
    is lexed, that promise has nothing behind it.

    The failure that cost a run was the compound: an incidental ``edm`` in a `tempfile`
    name AND a string `shlex` cannot lex. Pinning it as a spawn needs the guard to be
    armed against a real plane; pinning it here needs neither, so this is the half that
    still measures something the day the fixture above stops being reproducible.
    """

    #: Ordinary bash, and `shlex` raises on it — the premise the case below asserts rather
    #: than assumes.
    UNLEXABLE = "printf %s $'a\\'b'"

    def test_the_premise_that_shlex_refuses_what_bash_accepts(self):
        with self.assertRaises(ValueError):
            _planeguard._shell_segments(self.UNLEXABLE)
        self.assertEqual(
            subprocess.run(["bash", "-c", self.UNLEXABLE],
                           capture_output=True, text=True).stdout, "a'b")

    def test_the_name_inside_a_longer_word_is_not_what_decides_it(self):
        for path in ("/tmp/tmpq71ovzj50hedm9za/ran",   # the name CI actually drew
                     "/tmp/edm-test-9f2c/ran",         # `tests._isolation`'s own prefix
                     "/tmp/rechartering/ran"):         # and the current name, buried
            with self.subTest(path=path):
                command = f"{self.UNLEXABLE} > {path}"
                self.assertTrue(_planeguard._CHARTER_MENTION.search(command),
                                "fixture no longer reaches the gate it is about")
                self.assertFalse(_planeguard._shell_launches_charter(command))

    def test_the_name_as_a_word_still_decides_it(self):
        """The other half, and without it the case above is satisfied by a guard that
        answers "not charter" to everything it cannot lex."""
        for command in (f"{self.UNLEXABLE}; charter doctor",
                        f"{self.UNLEXABLE}; /usr/local/bin/charter doctor",
                        f"{self.UNLEXABLE}; edm doctor",
                        f'{self.UNLEXABLE}; CHARTER doctor'):
            with self.subTest(command=command):
                self.assertTrue(_planeguard._shell_launches_charter(command))

    def test_a_computed_command_word_is_decided_the_same_way(self):
        """The third exit. `ARefusedSpawn`'s spawn-level case pins the refusal; this pins
        that an incidental substring is not what earns it."""
        self.assertTrue(_planeguard._shell_launches_charter(
            "# this line starts charter\n$CBIN --version"))
        self.assertFalse(_planeguard._shell_launches_charter(
            "cd /tmp/edm-test-9f2c && $CBIN --version"))

    def test_an_unlexable_string_that_names_charter_only_glued_to_a_word_is_the_price(self):
        """What #830's fix gives up, stated where it costs something rather than left to
        be discovered.

        ``env -Scharter`` puts a word character against the name, which is the shape the
        mention gate exists for — so in a string that will not LEX, that spelling is no
        longer refused. It is the intersection of two rare things (a string bash runs and
        `shlex` cannot read, naming charter only glued to another word), and every one of
        those spellings is still refused the moment the string lexes, which is the case
        underneath. Narrowing this back out means finding a boundary rule that keeps
        ``-Scharter`` and drops ``edm-test-`` — and there is none: ``edm`` there is already
        bounded on both sides.
        """
        self.assertFalse(
            _planeguard._shell_launches_charter(f"env -Scharter {self.UNLEXABLE}"))
        self.assertTrue(_planeguard._shell_launches_charter("env -Scharter --version"))


class TheHarnessGuardIsNotASecondCopyOfProductions(unittest.TestCase):
    """The finding this round closed was not "a spelling was missing". It was that the
    harness guard held its OWN table of wrappers, its OWN `env` option arity and its OWN
    case rule, and each of them was weaker than the one `charter/hooks.py` already had —
    against inputs production denies and `tests/test_guard_parsing.py` already pins.

    Measured: ``["nice", "charter", "docs"]``, ``["CHARTER", "docs"]`` and ``["env", "-S",
    "<python> -c 'from charter import config; print(config.ROOT)'"]`` all ran against a
    guarded plane, and the last printed it. `nice cat <vault>`, `CHARTER secret get …
    --reveal` and `env -S 'cat <vault>'` are all denied by production.

    So the cases below are not about a list of commands. They are the join: what production
    can parse, this parses, because it is the same code. A second copy that starts drifting
    fails here rather than in someone's plane.
    """

    def test_the_launcher_split_is_productions_own_reader(self):
        """Not "behaves like" — IS. If someone reinstates a private walk, this catches it
        by watching production's function get called."""
        with mock.patch.object(hooks, "_split_env_chdir",
                               wraps=hooks._split_env_chdir) as split:
            _planeguard._launcher_argv(["nice", "charter", "docs"])
        split.assert_called_once()

    def test_every_wrapper_production_follows_is_followed_here(self):
        """The whole of `hooks._WRAPPERS`, as an ARGV — the form that was unexercised.

        A decision-function table rather than a spawn table on purpose: `sudo` and `su`
        would prompt a real machine for a password, and the point being pinned is the
        JOIN with production's constant, which no amount of spawning would show.
        """
        for wrapper in sorted(hooks._WRAPPERS):
            with self.subTest(wrapper=wrapper):
                self.assertTrue(
                    _planeguard._cmd_launches_charter([wrapper, "charter", "docs"]),
                    f"`{wrapper} charter docs` is a charter spawn to charter's own Bash "
                    f"guard and not to this one — the two tables have drifted")

    def test_the_wrappers_this_adds_are_the_ones_production_has_no_use_for(self):
        """An addition is fine; a re-statement is not. Whatever is here beyond production's
        set has to be a wrapper whose argument grammar cannot be followed to a program —
        which is why they are refused on the WORD instead."""
        self.assertLessEqual(hooks._WRAPPERS, _planeguard._COMMAND_WRAPPERS)
        self.assertEqual(_planeguard._COMMAND_WRAPPERS - hooks._WRAPPERS,
                         {"eval", "su", "watch", "script", "flock"})

    def test_the_charter_word_is_built_from_productions_names(self):
        """Including `edm`, charter's pre-rename binary, and folded — the two things
        `hooks._is_charter` and `_VAULT_PATH_RE` were already folded for."""
        for name in hooks._CHARTER_PROGS:
            with self.subTest(name=name):
                self.assertTrue(_planeguard._CHARTER_WORD.search(f"{name} --version"))
                self.assertTrue(
                    _planeguard._CHARTER_WORD.search(f"{name.upper()} --version"))
        # …and still not a path that merely contains the word, which is the shape the
        # frame's tmux fixtures spawn by the dozen.
        self.assertFalse(
            _planeguard._CHARTER_WORD.search("cd ~/IdeaProjects/charter/tests"))

    #: `test_guard_parsing`'s own wrapper corpus, with `charter` where the vault path was.
    #: Every one of these is a command charter's Bash guard already names as charter.
    SAME_CORPUS = ("sudo charter doctor",
                   "env charter doctor",
                   "/usr/bin/env charter doctor",
                   "nice -n 10 charter doctor",
                   "stdbuf -o0 charter doctor",
                   "timeout 5 charter doctor",
                   "timeout -s KILL 5 charter doctor",
                   "env -i charter doctor",
                   "env -u PATH charter doctor",
                   "sudo -u root charter doctor",
                   "sudo -- charter doctor",
                   "sudo env charter doctor",
                   "xargs charter doctor",
                   "env FOO=bar charter doctor",
                   "env -S 'charter doctor'",
                   "env -Scharter doctor",
                   "env --split-string='charter doctor'",
                   "CHARTER doctor")

    def test_the_same_corpus_is_charter_to_both_guards(self):
        """Asked as an ARGV, which is the form that had no wrapper follow at all — a
        `Popen(["nice", "charter", "docs"])` never becomes a shell string on the way."""
        for cmd in self.SAME_CORPUS:
            with self.subTest(cmd=cmd):
                argv = shlex.split(cmd)
                self.assertTrue(hooks._is_charter(*hooks._split_env(argv)[::2]),
                                f"{cmd} is not charter to PRODUCTION — wrong corpus")
                self.assertTrue(_planeguard._cmd_launches_charter(argv), cmd)

    def test_the_same_corpus_is_charter_inside_a_shell_string(self):
        """And again one layer of quoting in, where `charter workspace _reconcile` and
        `out="$(charter doctor 2>&1)"` — charter's own `hooks.json` — actually live."""
        for cmd in (*self.SAME_CORPUS,
                    "if true; then charter doctor; fi",
                    'out="$(charter doctor 2>&1)" || true'):
            with self.subTest(cmd=cmd):
                self.assertTrue(_planeguard._shell_launches_charter(cmd), cmd)


class NoCharterEscapesThroughTheExecFamily(unittest.TestCase):
    """The guard watches `subprocess.Popen.__init__`, and nothing else starts a process.

    `os.execv*`, `os.posix_spawn*`, `os.spawn*` and `os.system` all go around it. Wrapping
    them too would be the obvious move and the wrong one: `execvp` REPLACES this process,
    so a wrapper that refused would be refusing something that cannot be a child of the
    suite at all, and `os.system` is not used here.

    What makes "nothing reaches charter that way" a fact rather than an assumption is this
    case. Every module in `charter/` and `tests/` is parsed, every call to one of those
    functions is found, and each has to be one this file has already looked at and written
    down. A fourth appears the day somebody writes one, named by file and line.

    Parsed rather than grepped, so that ``mock.patch("os.execvp")`` — which
    `test_frame_launcher` writes fifteen times — is what it is: a string, not a call.
    """

    #: ``module:function`` → why this one cannot start a charter. Frozen deliberately: the
    #: point is that a NEW exec is noticed, and a set that grew by itself would notice
    #: nothing.
    KNOWN = {
        "charter/commands_frame.py:execvp":
            "`bypass` hands this process to the HARNESS (`claude`), and replaces it. The "
            "thing that runs afterwards is not charter and has no plane to resolve.",
        "charter/frame/launcher.py:execvpe":
            "The launcher hands its pane — or, on `--no-frame`, this process — to a harness "
            "profile's command and replaces itself. A profile whose command's first word is "
            "charter is refused by `profiles.current` before any launch (Ruling 14), so what "
            "runs afterwards is a harness and not charter. A wrapper script that execs "
            "charter is the limit, and it is the operator's own to write.",
        "charter/commands_secrets.py:execvpe":
            "`secret exec` replaces this process with the operator's own command. If they "
            "type `charter`, the process that becomes charter is the one that was already "
            "running — a test doing this by accident loses the runner, not a plane.",
        "tests/test_frame_tmux_integration.py:execvp":
            "`tmux attach` inside a `pty.fork` child, which `os._exit`s in its `finally`.",
        "tests/test_frame_overlay_escape_hatch.py:execvp":
            "The same `tmux attach` inside a `pty.fork` child, for the same reason: a "
            "`bind -n` can only be exercised by a real client with a real terminal, and "
            "`send-keys` never reaches the key table. `os._exit`s in its `finally`.",
        "tests/test_frame_palette_integration.py:execvp":
            "The same `tmux attach` inside a `pty.fork` child, and for the same reason "
            "again: the palette's whole entry point is a `bind -n`, which only a real "
            "client with a real terminal can press. `os._exit`s in its `finally`.",
        "tests/test_frame_input_reaches_a_component.py:execvp":
            "The same `tmux attach` inside a `pty.fork` child once more: tmux sends a "
            "pane focus report only while a client is attached, and a mouse report has "
            "to be put on a real client's terminal for tmux to route it — so neither "
            "`focus`/`blur` nor `click`/`scroll` can be exercised without a real one. "
            "`os._exit`s in its `finally`.",
        "tests/test_a_second_launch_focuses_instead_of_dragging.py:execvp":
            "The same `tmux attach` inside a `pty.fork` child, for the reason open-or-"
            "focus is ABOUT: the decision it takes is 'is a client attached to this "
            "workspace', and only a real client on a real terminal makes that true. "
            "`os._exit`s in its `finally`.",
        "tests/test_a_real_click_reaches_the_real_repo_table.py:execvp":
            "The same `tmux attach` inside a `pty.fork` child, for the sibling reason: "
            "that file exercises the pointer against charter's OWN `repos` panel rather "
            "than a fixture provider's, and a mouse report still has to be put on a real "
            "client's terminal for tmux to route it anywhere. `os._exit`s in its "
            "`finally`.",
        "tests/test_a_workspace_switch_moves_the_client.py:execvp":
            "The same `tmux attach` inside a `pty.fork` child, for the reason a workspace "
            "switch is ABOUT: `switch-client -c <client>` moves a CLIENT, and only a real "
            "one on a real terminal exists to be moved — a detached session has nothing "
            "for the switch to act on. `os._exit`s in its `finally`.",
        "tests/test_a_workspace_tab_opens_what_it_names.py:execvp":
            "The same `tmux attach` inside a `pty.fork` child, for the reason opening a "
            "workspace from a tab is ABOUT: the claim under test is that a process with "
            "no controlling terminal can still build a session and `switch-client` a "
            "real client onto it, and only a real client on a real terminal is a thing "
            "that can be moved. `os._exit`s in its `finally`.",
        "tests/test_a_real_click_on_a_real_tab_bar_switches.py:execvp":
            "The same `tmux attach` inside a `pty.fork` child, for the sibling reason "
            "again: that file exercises the pointer against the two BARS, whose click "
            "starts a real detached charter, and a mouse report still has to be put on a "
            "real client's terminal for tmux to route it anywhere. `os._exit`s in its "
            "`finally`.",
        "tests/test_a_real_click_opens_the_real_palette.py:execvp":
            "The same `tmux attach` inside a `pty.fork` child, for the sibling reason a "
            "third time: that file exercises the pointer against the two one-row STRIPS "
            "and the sidebar's persona column, whose clicks start a real detached "
            "`charter frame-palette` and `charter frame-switch --persona`, and a mouse "
            "report still has to be put on a real client's terminal for tmux to route it "
            "anywhere. `os._exit`s in its `finally`.",
        "tests/test_a_frame_sends_one_invocation_per_batch.py:execvp":
            "The same `tmux attach` inside a `pty.fork` child, for the reason #844's "
            "measurement is ABOUT: what a command list costs the operator is what tmux "
            "DRAWS for it, and there is no screen to draw on without a real client on a "
            "real terminal — a detached server repaints nothing at all. `os._exit`s in "
            "its `finally`.",
    }

    _WATCHED = ("execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp",
                "execvpe", "posix_spawn", "posix_spawnp", "spawnl", "spawnle", "spawnlp",
                "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe", "system")

    def test_every_exec_in_the_tree_is_one_that_cannot_become_charter(self):
        import ast

        tree = Path(__file__).resolve().parent.parent
        found = {}
        for path in sorted((*tree.glob("charter/**/*.py"), *tree.glob("tests/**/*.py"))):
            try:
                parsed = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError):       # not this case's business
                continue
            for node in ast.walk(parsed):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if (isinstance(func, ast.Attribute) and func.attr in self._WATCHED
                        and isinstance(func.value, ast.Name) and func.value.id == "os"):
                    key = f"{path.relative_to(tree)}:{func.attr}"
                    found.setdefault(key, node.lineno)

        unexpected = {k: v for k, v in found.items() if k not in self.KNOWN}
        self.assertEqual(
            unexpected, {},
            f"a process is started by a call `tests._planeguard` does not watch: "
            f"{unexpected}. `RealPlaneSpawn` wraps `subprocess.Popen.__init__` only, so a "
            f"charter started this way reaches the operator's plane unseen. Either it "
            f"cannot become charter — say why, and add it to "
            f"`NoCharterEscapesThroughTheExecFamily.KNOWN` — or it can, and it should go "
            f"through `subprocess` instead.")

        gone = set(self.KNOWN) - set(found)
        self.assertEqual(gone, set(),
                         f"{gone} is written down here and no longer exists — an "
                         f"allow-list nobody prunes stops being read")


class HowTheChildsPlaneIsResolved(_FakePlane):
    def test_it_asks_find_root_with_the_childs_environment_and_cwd(self):
        """Not with this process's. The whole defect is that the child's answer differs
        from the parent's, so a guard that asked the parent's question would agree with
        every spawn it was meant to catch.
        """
        seen = {}

        def spy(start=None, env=None):
            seen["start"], seen["env"] = start, env
            return self.elsewhere

        with mock.patch.object(root, "find_root", side_effect=spy):
            self.run_fake(cwd=self.elsewhere,
                          env={**os.environ, root.ENV_VAR: str(self.elsewhere)})
        self.assertEqual(Path(seen["start"]), self.elsewhere)
        self.assertEqual(seen["env"].get(root.ENV_VAR), str(self.elsewhere))

    def test_a_child_with_no_env_of_its_own_is_asked_about_ours(self):
        """``env=None`` means the child inherits this process's environment, so that is
        the environment its answer depends on.

        A COPY of it, not the mapping itself, and the difference is the other tripwire in
        this package: `_envguard` refuses an undeclared targeted read of ``$CHARTER_ROOT``
        and leaves bulk reads alone, so handing `find_root` the live `os.environ` would
        charge every test that spawns a `bash` with a read it never made. The values are
        the same either way — the ambient ones were scrubbed at install — and a copy is
        exactly what the child inherits.
        """
        seen = {}

        def spy(start=None, env=None):
            seen["env"] = env
            return self.elsewhere

        with mock.patch.object(root, "find_root", side_effect=spy):
            self.run_fake(cwd=self.elsewhere)
        self.assertIsNot(seen["env"], os.environ)
        self.assertEqual(seen["env"], dict(os.environ))

    def test_an_unresolvable_child_falls_back_to_its_own_cwd(self):
        """`charter.config` calls `find_root_or_cwd`, which falls back to the working
        directory when no plane is found — so a child with a bad `$CHARTER_ROOT` and a cwd
        of the real plane still lands on it. Answering "no plane, allow" there would be
        the guard waving through the one case the fallback makes dangerous.
        """
        with self.assertRaises(_planeguard.RealPlaneSpawn):
            self.run_fake(cwd=self.real,
                          env={**os.environ, root.ENV_VAR: str(self.elsewhere / "gone")})
        self.assertFalse(self.marker.exists())


class AChildThatRunsTheSuiteIsJudgedFromItsCwd(_FakePlane):
    """A child that imports `tests` has its ``$CHARTER_ROOT`` removed by `_envguard` before
    charter resolves a plane (#1064), so the pointer it is handed decides nothing: the walk
    up from its cwd does. The guard has to ask that question, or a throwaway pointer waves
    through a child that is standing in the real plane.

    The source names ``import tests`` under ``if False`` so the recogniser reads it while
    the child never runs the package: an allowed case really runs and leaves its canary,
    and a regression that let the refused case through runs nothing but that canary.
    """

    def setUp(self):
        super().setUp()
        self.canary = self.elsewhere / "the-suite-child-ran"
        self.handed = {**os.environ, root.ENV_VAR: str(self.elsewhere)}
        self.source = (f"open({str(self.canary)!r}, 'w').close()\n"
                       f"if False:\n    import tests\n")

    def _refused(self, args, cwd):
        try:
            child = subprocess.Popen(args, cwd=cwd, env=self.handed,
                                     stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except _planeguard.RealPlaneSpawn as refused:
            self.assertFalse(self.canary.exists(), "refused after the child ran")
            return str(refused)
        child.wait()
        self.fail(f"{args} ran from {cwd} with a throwaway $CHARTER_ROOT; that pointer is "
                  f"scrubbed as the child imports `tests`, so it resolved {cwd}")

    def test_a_throwaway_pointer_does_not_rescue_a_suite_child_in_the_real_plane(self):
        message = self._refused([sys.executable, "-c", self.source], cwd=self.real)
        self.assertIn(str(self.real), message)
        self.assertIn("_envguard", message)

    def test_running_a_suite_module_is_the_same_child(self):
        """``python -m tests.<module>`` imports the package without writing an import."""
        self._refused([sys.executable, "-m", "tests.no_such_module"], cwd=self.real)

    def test_the_same_child_standing_in_a_throwaway_plane_runs(self):
        child = subprocess.Popen([sys.executable, "-c", self.source], cwd=self.elsewhere,
                                 env=self.handed, stdin=subprocess.DEVNULL)
        self.assertEqual(child.wait(), 0)
        self.assertTrue(self.canary.exists(), "the child did not run")

    def test_a_charter_child_that_does_not_run_the_suite_still_follows_its_pointer(self):
        """Only the suite scrubs. `child_plane_env`'s whole contract is that a plain
        charter child handed a throwaway ``$CHARTER_ROOT`` resolves it from anywhere."""
        p = self.run_fake(cwd=self.real, env=self.handed)
        self.assertEqual(p.returncode, 0)
        self.assertTrue(self.marker.exists())


class WhatCharterHandsItsOwnChildren(unittest.TestCase):
    """`util.child_env` — the reason an isolated case satisfies the guard without knowing
    it exists."""

    def setUp(self):
        self.plane = Path(tempfile.mkdtemp(prefix="spawnguard-plane-"))
        self.addCleanup(shutil.rmtree, self.plane, True)

    def test_a_child_is_told_the_plane_this_process_resolved(self):
        from charter import util
        with mock.patch.object(config, "ROOT", self.plane), \
                mock.patch.object(config, "HAS_CONTROL_PLANE", True):
            self.assertEqual(util.child_env()[root.ENV_VAR], str(self.plane))

    def test_an_inherited_pointer_does_not_win_over_the_resolved_plane(self):
        """`config.ROOT` is the plane this process is actually reading and writing. When
        the two disagree, the child's job is to agree with its parent, not with a shell
        variable the parent already declined to follow."""
        from charter import util
        with mock.patch.object(config, "ROOT", self.plane), \
                mock.patch.object(config, "HAS_CONTROL_PLANE", True), \
                mock.patch.dict(os.environ, {root.ENV_VAR: "/somewhere/else"},
                                clear=False):
            self.assertEqual(util.child_env()[root.ENV_VAR], str(self.plane))

    def test_a_planeless_process_hands_nothing(self):
        """`$CHARTER_ROOT` wins outright in `find_root` and a value with no `charter.toml`
        at it RAISES rather than falling back — so a pointer to a non-plane is worse than
        no pointer. The spawners refuse to fork at all in that state; this pins that
        `child_env` would not have lied to the child either."""
        from charter import util
        with mock.patch.object(config, "ROOT", self.plane), \
                mock.patch.object(config, "HAS_CONTROL_PLANE", False), \
                mock.patch.dict(os.environ, {}, clear=True):
            self.assertNotIn(root.ENV_VAR, util.child_env())


class NoBackgroundRefreshWithoutAPlane(unittest.TestCase):
    """Both best-effort refreshers return before forking when there is no plane.

    Not a tidiness rule: outside a plane `config.STATE_DIR` is ``<cwd>/.charter``, so the
    child would scatter charter's caches into whatever directory the render ran in — and,
    having been handed no plane, would go looking for one of its own.
    """

    def test_glstate_does_not_fork(self):
        from charter import glstate
        with mock.patch.object(config, "HAS_CONTROL_PLANE", False), \
                mock.patch.object(glstate.subprocess, "Popen") as popen:
            glstate.maybe_spawn([Path("/tmp")])
        popen.assert_not_called()


class TheOperatorsCredentialStoreIsNeverReached(unittest.TestCase):
    """`RealVaultReach` — the fourth tripwire, and the only one not about the plane.

    Two tests in `test_vault_registration.py` ran the operator's real `op` against their
    real 1Password vault, because `cmd_vault_add` ends in `prov.health()` and a
    `1password` vault answers that by shelling out (#546). Measured with a logging
    stand-in first on `$PATH`: four invocations, two tests, none anywhere else in 6636.
    They passed because an unauthenticated `op` fails fast; they HANG when it prompts.

    A control, on the same terms as `ARefusedSpawn` above: the refusal is made to happen
    for real, and the evidence that nothing ran is a marker file that is absent while the
    same marker is PRESENT in the allowed case — "the child never started" and "the child
    started and could not write" look identical without it.
    """

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="vaultguard-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.marker = self.dir / "the-cli-ran"
        for name in ("op", "vault", "npx", "git"):
            p = self.dir / name
            p.write_text(f"#!/bin/sh\necho {name} >> {self.marker}\n")
            p.chmod(0o755)

    def _run(self, argv, **kw):
        subprocess.run(argv, **kw)

    def test_the_names_are_asked_of_productions_own_resolver_table(self):
        """Derived, not spelled — the rule `_envguard` states for its own loud set. A
        scheme added to `reference._RESOLVERS` is guarded on the commit that adds it,
        which is the difference between a guard and a list somebody has to remember."""
        from charter.secrets import reference
        self.assertEqual(sorted(_planeguard._VAULT_CLIS), ["npx", "op", "vault"])
        self.assertEqual(sorted(reference._RESOLVERS), ["browser", "op", "vault"])

    def test_op_is_named_even_if_the_table_stops_naming_it(self):
        """`OnePasswordProvider._argv` spells `op` inline and has no table to ask, so the
        derivation seeds it unconditionally. Today the `op://` resolver produces the same
        name and the seed looks redundant — this is what makes it not: with the table
        emptied, the provider charter writes 1Password items through is still guarded.
        """
        with mock.patch("charter.secrets.reference._RESOLVERS", {}):
            self.assertEqual(_planeguard._credential_clis(), frozenset({"op"}))

    def test_a_scheme_whose_uri_this_file_cannot_spell_costs_one_name_not_the_suite(self):
        """The probe URIs live here and the builders live in production, so a scheme
        arriving with a shape this file has not learned makes the lookup raise. The choice
        is between guarding one CLI fewer and refusing to import the `tests` package, and
        the skip is what picks the first — with the seeded `op` keeping the degraded answer
        from being empty. A sweep survivor until it had this case (#569)."""
        from charter.secrets import reference

        def _never_called(uri, config):     # pragma: no cover - the lookup raises first
            raise AssertionError("a scheme with no probe URI must not reach its builder")

        with mock.patch("charter.secrets.reference._RESOLVERS",
                        {"quantum": _never_called, "vault": reference._vault_argv}):
            self.assertEqual(_planeguard._credential_clis(),
                             frozenset({"op", "vault"}),
                             "the unspellable scheme took the rest of the table with it")

    def test_a_shell_string_that_runs_it_is_refused(self):
        """`shell=True` hands the whole string to `/bin/sh -c`, so the program name is
        inside it rather than in `argv[0]`. Nothing in charter spells a vault read that
        way; a test could, and the point of a tripwire is the spelling nobody planned."""
        with self.assertRaises(_planeguard.RealVaultReach):
            subprocess.run(f"{self.dir}/op item list", shell=True)
        self.assertFalse(self.marker.exists())

    def test_a_shell_string_that_will_not_lex_is_not_guessed_at(self):
        """The direction this guard chooses to be wrong in, said out loud: splitting a
        shell string is the shell's job and `shlex` only approximates it, so an unlexable
        command is answered "not a credential CLI" rather than refused. `RealPlaneSpawn`
        chooses the opposite for charter, because there the cost of a miss is a write to a
        live plane; here a miss is a `git`-shaped command that nobody could run."""
        subprocess.run(f"{self.dir}/git 'unclosed", shell=True, capture_output=True)
        self.assertFalse(self.marker.exists())      # sh refused it; nothing was reached

    def test_reading_a_real_1password_item_is_refused(self):
        """The exact argv the four measured invocations carried."""
        with self.assertRaises(_planeguard.RealVaultReach) as caught:
            self._run([str(self.dir / "op"), "item", "get", "charter-devops",
                       "--vault", "Eng", "--format", "json"])
        self.assertFalse(self.marker.exists(), "refused, and yet it ran")
        self.assertIn("REFUSED", str(caught.exception))

    def test_a_path_object_as_the_whole_command_is_refused(self):
        """`Popen` accepts one path-like as the entire command, and it is not iterable —
        so the branch that normalises it is the difference between recognising this and
        answering "not a credential CLI" for something that is about to run `op`."""
        with self.assertRaises(_planeguard.RealVaultReach):
            subprocess.Popen(Path(self.dir / "op"))
        self.assertFalse(self.marker.exists())

    def test_a_bare_string_is_a_program_name_and_is_not_lexed(self):
        """Without `shell=True` a string is one program NAME — spaces and all — while with
        it the string is a command line for `/bin/sh`. The two must not be conflated, and
        a path with no space in it cannot tell them apart: `shlex.split` returns the same
        one word either way. This one lexes into two, neither of which is `op`, so lexing
        it would read as "not a credential CLI" for a spawn that is about to run one.

        The directory is not called `vault something`, and that is not fussiness: the first
        spelling of this case used `vault dir`, whose first lexed word is `vault` — itself
        a guarded CLI — so the mutation it exists to catch stayed green by being refused
        for the wrong reason."""
        spaced = self.dir / "somebodys credentials"
        spaced.mkdir()
        shutil.copy(self.dir / "op", spaced / "op")
        (spaced / "op").chmod(0o755)
        with self.assertRaises(_planeguard.RealVaultReach):
            subprocess.Popen(str(spaced / "op"))
        self.assertFalse(self.marker.exists())

    def test_a_command_that_is_all_wrapper_leaves_no_program_to_name(self):
        """`Popen(["env"])` really runs `env`, and `_launcher_argv` strips the wrapper —
        so what reaches the name check is an EMPTY argv. Not a hypothetical branch: the
        guard runs on every spawn in the suite, and one that indexed `argv[0]` here would
        turn an ordinary command into an `IndexError` raised from inside a tripwire."""
        p = subprocess.run(["env"], capture_output=True)
        self.assertEqual(p.returncode, 0)

    def test_a_spawn_with_no_command_at_all_is_left_to_subprocess(self):
        """Asked of the decision function directly, because `Popen(None)` never gets far
        enough to prove anything: the guard must decline rather than raise a `TypeError`
        of its own from inside somebody else's spawn."""
        self.assertIsNone(_planeguard._reaches_a_credential_cli(None, {}))

    def test_a_bare_name_on_the_path_is_refused_too(self):
        """How charter actually spells it: `onepassword._argv` builds `["op", …]` and
        lets `$PATH` resolve it, so a guard that only recognised full paths would miss
        every real call."""
        with self.assertRaises(_planeguard.RealVaultReach):
            self._run(["op", "read", "--no-newline", "op://Eng/charter-devops/AWS_KEY"],
                      env={**os.environ, "PATH": f"{self.dir}:{os.environ['PATH']}"})
        self.assertFalse(self.marker.exists())

    def test_the_other_resolvers_are_refused_on_the_same_terms(self):
        """`vault kv get` and the browser lane's `npx` read credentials just as `op`
        does — one reaches a HashiCorp Vault, the other a logged-in browser session (and
        pulls a package off the network to do it)."""
        for argv in (["vault", "kv", "get", "-field=TOKEN", "secret/data/app"],
                     ["npx", "--yes", "@playwright/cli@0.1.18", "session", "read"]):
            with self.subTest(cli=argv[0]), \
                    self.assertRaises(_planeguard.RealVaultReach):
                self._run(argv, env={**os.environ,
                                     "PATH": f"{self.dir}:{os.environ['PATH']}"})
        self.assertFalse(self.marker.exists())

    def test_a_program_that_merely_resolves_to_it_is_refused(self):
        """`_program_names` follows the link and the `$PATH` lookup, so a basename compare
        cannot be walked past. charter's own spellings would never do this — which is the
        point: a guard is for the spelling nobody planned, and this one was a survivor of
        the hand-check until it had a case (#569)."""
        link = self.dir / "not-op-at-all"
        link.symlink_to(self.dir / "op")
        with self.assertRaises(_planeguard.RealVaultReach):
            self._run([str(link), "item", "list"])
        self.assertFalse(self.marker.exists())

    def test_a_wrapper_in_front_of_it_is_followed(self):
        """`_launcher_argv` is production's own command reader, and it is used here for
        the same reason `_charter_argv` uses it: a wrapper is not a disguise."""
        with self.assertRaises(_planeguard.RealVaultReach):
            self._run(["env", "OP_ACCOUNT=x", str(self.dir / "op"), "item", "list"])
        self.assertFalse(self.marker.exists())

    def test_the_message_names_the_test_the_cli_and_the_way_out(self):
        with self.assertRaises(_planeguard.RealVaultReach) as caught:
            self._run([str(self.dir / "op"), "item", "list"])
        msg = str(caught.exception)
        self.assertIn("TheOperatorsCredentialStoreIsNeverReached."
                      "test_the_message_names_the_test_the_cli_and_the_way_out", msg)
        self.assertIn("op", msg)
        self.assertIn("runner", msg)             # the way out five modules already take
        self.assertIn("shutil.which", msg)       # and its second half

    def test_it_is_a_base_exception_so_charters_own_fallbacks_cannot_eat_it(self):
        """`ReferenceProvider.health` answers a `VaultError` with a status string, and
        `doctor` catches broadly around every check: a tripwire either of those can
        swallow becomes a red line in a report instead of a failed test."""
        self.assertTrue(issubclass(_planeguard.RealVaultReach, BaseException))
        self.assertFalse(issubclass(_planeguard.RealVaultReach, Exception))

    def test_an_unrelated_binary_of_the_same_shape_really_runs(self):
        """The half that proves an absent marker above means "never started". `git` is
        spawned by this suite constantly and must stay spawnable."""
        self._run([str(self.dir / "git"), "status"])
        self.assertEqual(self.marker.read_text().strip(), "git")

    def test_the_guard_does_not_wait_on_a_plane(self):
        """Checked BEFORE the plane question and without `_REAL_ROOT`: reading somebody's
        1Password vault is wrong on a machine that has no control plane at all, and a
        guard armed only when one is resolvable would be off in exactly that case."""
        with mock.patch.object(_planeguard, "_REAL_ROOT", ()), \
                self.assertRaises(_planeguard.RealVaultReach):
            self._run([str(self.dir / "op"), "item", "list"])


class TheOperatorsForgeTokenIsNeverReached(unittest.TestCase):
    """`RealForgeReach` — the credential-store tripwire, one host out.

    `gh` and `glab` hold a real token for the operator's real account, so a test that
    reaches one enumerates and reads somebody's private repositories as whoever is signed in
    on this machine — and the cross-repo change surface will open and merge pull requests
    through the same binaries. It is also a flake, because CI has no forge credentials, and
    a hang, because both CLIs can park on a device-flow prompt.

    Same control as the class above: the refusal is made to happen for real, and a marker
    file that stays absent is the evidence that nothing ran — "the child never started" and
    "the child started and could not write" look identical without it.
    """

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="forgeguard-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.marker = self.dir / "the-cli-ran"
        for name in ("gh", "glab", "git"):
            p = self.dir / name
            p.write_text(f"#!/bin/sh\necho {name} >> {self.marker}\n")
            p.chmod(0o755)

    def test_the_names_come_from_the_registry_not_from_a_list_here(self):
        """`_credential_clis` asks `reference._RESOLVERS`; this asks `registry.KINDS`, so a
        forge added there is guarded on the commit that adds it."""
        from charter.forge import registry
        self.assertEqual(_planeguard._forge_clis(),
                         frozenset({cls.cli for cls in registry.KINDS.values()}))
        self.assertEqual(_planeguard._forge_clis(), frozenset({"gh", "glab"}))
        self.assertEqual(_planeguard._FORGE_CLIS, frozenset({"gh", "glab"}))

    def test_running_gh_is_refused(self):
        with self.assertRaises(_planeguard.RealForgeReach) as caught:
            subprocess.run([str(self.dir / "gh"), "api", "repos/acme/api/pulls"])
        self.assertFalse(self.marker.exists(), "refused, and yet it ran")
        self.assertIn("REFUSED", str(caught.exception))

    def test_running_glab_is_refused(self):
        with self.assertRaises(_planeguard.RealForgeReach):
            subprocess.run([str(self.dir / "glab"), "api", "projects/1/merge_requests"])
        self.assertFalse(self.marker.exists())

    def test_a_bare_name_on_the_path_is_refused_too(self):
        """How the backends actually spell it: `[self.cli, "api", …]`, letting `$PATH`
        resolve it — so a guard that only recognised full paths would miss every real
        call."""
        with self.assertRaises(_planeguard.RealForgeReach):
            subprocess.run(["gh", "api", "repos/acme/api/pulls"],
                           env={**os.environ, "PATH": f"{self.dir}:{os.environ['PATH']}"})
        self.assertFalse(self.marker.exists())

    def test_the_refusal_names_the_way_out(self):
        """A tripwire that only says no costs the next person an afternoon."""
        with self.assertRaises(_planeguard.RealForgeReach) as caught:
            subprocess.run([str(self.dir / "gh"), "pr", "merge", "601"])
        text = str(caught.exception)
        self.assertIn("util.run", text)
        self.assertIn("test_forge_github", text)
        self.assertIn("_forgeprobe", text)

    def test_a_flags_only_invocation_is_allowed_because_it_reaches_no_forge(self):
        """`doctor.check_forge_cli` runs `gh --version` to report which CLI is installed:
        a local probe that contacts no host, reads no token and cannot prompt. A flat
        refusal reddened twenty-six tests in this suite, every one of them that, and
        refusing it would have been the guard being wrong about its own subject."""
        subprocess.run([str(self.dir / "gh"), "--version"])
        self.assertTrue(self.marker.exists())

    def test_a_wrapper_in_front_of_a_flags_only_invocation_is_still_allowed(self):
        """The wrapper's own words are not the CLI's. `_launcher_argv` comes off first, so
        the rule reads `gh --version` here rather than `env gh --version` — which has a
        bare word in it and would otherwise be refused for a spawn that reaches nothing."""
        subprocess.run(["env", str(self.dir / "gh"), "--version"])
        self.assertTrue(self.marker.exists())

    def test_auth_status_is_refused_now_that_nothing_reaches_it(self):
        """The residual this tripwire shipped with, and closing it is the whole of #638.

        `doctor.check_forge_auth` runs `gh auth status --hostname github.com`, and the
        first version of this guard ALLOWED it: 28 such children per run, 20 `glab` and 8
        `gh`, from the eighteen modules that reach `doctor.run_all()`, and refusing it then
        would only have reddened them. `tests/_forgeprobe.py` now answers that probe with a
        recorded reply, so nothing reaches a real forge CLI — and an allowance nothing
        needs is an allowance that quietly comes back."""
        with self.assertRaises(_planeguard.RealForgeReach):
            subprocess.run([str(self.dir / "gh"), "auth", "status",
                            "--hostname", "github.com"])
        self.assertFalse(self.marker.exists())

    def test_auth_login_and_auth_token_are_refused_too(self):
        """They always were, and they are the reason the allowance was `auth status` rather
        than `auth`: `login` opens a browser and waits, `token` prints the credential onto
        stdout."""
        for sub in (["auth", "login"], ["auth", "token"], ["auth", "refresh"]):
            with self.subTest(sub=sub):
                with self.assertRaises(_planeguard.RealForgeReach):
                    subprocess.run([str(self.dir / "gh"), *sub])
        self.assertFalse(self.marker.exists())

    def test_the_calls_the_change_surface_makes_are_all_refused(self):
        """The half that matters most: every way charter's own change surface touches a
        forge goes through `api`, and merging goes through `pr`/`mr`."""
        for sub in (["api", "repos/acme/api/pulls"], ["pr", "merge", "601"],
                    ["mr", "merge", "14"], ["repo", "clone", "acme/api"],
                    ["release", "create", "v1"]):
            with self.subTest(sub=sub):
                with self.assertRaises(_planeguard.RealForgeReach):
                    subprocess.run([str(self.dir / "gh"), *sub])
        self.assertFalse(self.marker.exists())

    def test_a_subcommand_charter_has_never_heard_of_still_counts(self):
        """The rule is "does this argv name a subcommand", not a list of the ones charter
        happens to use — so a name nobody here recognises is refused rather than waved
        through, which is the direction a guard should be wrong in."""
        with self.assertRaises(_planeguard.RealForgeReach):
            subprocess.run([str(self.dir / "gh"), "codespace", "ssh"])
        self.assertFalse(self.marker.exists())

    def test_it_is_a_base_exception_so_charters_own_fallbacks_cannot_eat_it(self):
        """`GitHubForge.check_auth` and `report.gh` both wrap their `util.run` in
        `except Exception` and turn a failure into a degraded answer, so an `Exception`
        here would be reported as "not authenticated" and the test would pass."""
        self.assertTrue(issubclass(_planeguard.RealForgeReach, BaseException))
        self.assertFalse(issubclass(_planeguard.RealForgeReach, Exception))

    def test_the_guard_does_not_wait_on_a_plane(self):
        """`RealVaultReach`'s reason exactly: a real `gh` reaches somebody's repositories
        on a machine with no control plane at all."""
        with mock.patch.object(_planeguard, "_REAL_ROOT", ()), \
                self.assertRaises(_planeguard.RealForgeReach):
            subprocess.run([str(self.dir / "gh"), "api", "user"])

    def test_git_is_not_guarded(self):
        """The boundary. Charter's whole design is that git talks to a forge over HTTPS
        with the forge CLI's token, and tests here really do run git against local
        repositories — so guarding `git` would refuse the thing the suite is built on."""
        subprocess.run([str(self.dir / "git"), "status"])
        self.assertTrue(self.marker.exists())


if __name__ == "__main__":
    unittest.main()
