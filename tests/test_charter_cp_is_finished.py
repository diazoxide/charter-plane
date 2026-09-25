"""charter-cp 0.62.2 is the last release, and it stops pointing at places that change hands.

The repository this package came from was renamed ``diazoxide/charter-plane``, and the
desktop app's repository took over the name ``diazoxide/charter``. Every place an installed
charter-cp named ``diazoxide/charter`` as *this package* now reaches the app. These cases pin
the five changes that deal with that:

* `charter update` prints the end-of-life notice, installs nothing and exits 0;
* the update check never reports anything newer, on either channel, and starts no child;
* the marketplace charter adds is ``diazoxide/charter-plane``;
* `report send` files on ``diazoxide/charter``, which is the app;
* the notice reaches a person at a terminal and changes no stdout anything parses.
"""

from __future__ import annotations

import contextlib
import io
import tomllib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from charter import channel, cli, commands_update, config, plugincache, report, update, wiring
from tests._isolation import PersonaIso, make_plane
from tests._planeguard import allow_background_checks

REPO = Path(__file__).resolve().parent.parent
NOTICE = ("charter-cp is no longer maintained — charter is now a desktop app: "
          "https://github.com/diazoxide/charter/releases")


class _Quiet:
    """Refuse every route to the network and every child process for the case."""

    def setUp(self):
        super().setUp()
        self.reached: list[str] = []
        for route in ("socket.socket", "socket.create_connection",
                      "urllib.request.urlopen", "subprocess.Popen", "subprocess.run"):
            self.enterContext(mock.patch(route, self._refuse(route)))
        self.addCleanup(lambda: self.assertEqual(self.reached, []))

    def _refuse(self, route):
        def boom(*a, **kw):
            self.reached.append(route)
            raise AssertionError(f"{route} was reached")
        return boom


class TheNoticeIsOneSentence(unittest.TestCase):
    def test_it_is_the_sentence_the_release_promises(self):
        self.assertEqual(update.END_OF_LIFE, NOTICE)


class UpdateInstallsNothing(_Quiet, PersonaIso):
    def _run(self, **kw) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        args = SimpleNamespace(to=kw.get("to"), bump=kw.get("bump", False))
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = commands_update.cmd_update(args)
        return code, out.getvalue(), err.getvalue()

    def test_it_prints_the_notice_and_exits_zero(self):
        code, out, err = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertIn(NOTICE, err)
        self.assertIn("nothing was installed", err)

    def test_a_named_version_and_bump_install_and_write_nothing_either(self):
        make_plane(self)
        before = (config.ROOT / "charter.toml").read_text()
        code, _out, err = self._run(to="9.9.9", bump=True)
        self.assertEqual(code, 0)
        self.assertIn(NOTICE, err)
        self.assertEqual((config.ROOT / "charter.toml").read_text(), before)

    def test_on_the_dev_channel_too(self):
        with mock.patch("charter.channel.update_is_dev", return_value=True), \
                mock.patch("charter.channel.is_dev", return_value=True):
            code, _out, err = self._run()
        self.assertEqual(code, 0)
        self.assertIn(NOTICE, err)

    def test_the_main_install_path_is_gone(self):
        source = (REPO / "charter" / "commands_update.py").read_text()
        for gone in ("DEV_SPEC", "_DEV_INSTALLERS", "uv\", \"tool\", \"install"):
            self.assertNotIn(gone, source)
        self.assertFalse(hasattr(commands_update, "DEV_SPEC"))

    def test_the_parser_still_accepts_what_scripts_pass(self):
        args = cli.build_parser().parse_args(["update", "--to", "1.2.3", "--bump"])
        self.assertIs(args.func, commands_update.cmd_update)


class TheUpdateCheckReportsNothing(_Quiet, PersonaIso):
    def setUp(self):
        super().setUp()
        make_plane(self)
        allow_background_checks(self)      # the switch must not be what keeps it quiet

    def _cache(self, doc: dict) -> None:
        import json
        p = config.STATE_DIR / "cache" / "update.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc))

    def test_a_newer_cached_release_is_not_reported_on_stable(self):
        self._cache({"latest": "99.0.0", "ts": 0})
        with mock.patch("charter.channel.is_dev", return_value=False):
            self.assertIsNone(update.newer_than("0.62.2"))

    def test_a_different_cached_head_is_not_reported_on_dev(self):
        self._cache({"latest": "99.0.0", "head": "a" * 40, "ts": 0})
        with mock.patch("charter.channel.is_dev", return_value=True):
            self.assertIsNone(update.newer_than("0.62.2"))
            self.assertIsNone(update.newer_head())

    def test_a_stale_cache_on_a_real_plane_starts_no_child(self):
        self._cache({"latest": "0.1.0", "ts": 0})
        update.maybe_spawn()                    # `_Quiet` fails the case on any Popen
        self.assertFalse((config.STATE_DIR / "cache" / "update.checking").exists())

    def test_nothing_asks_github_for_a_branch_head(self):
        source = (REPO / "charter" / "update.py").read_text()
        self.assertNotIn("api.github.com", source)
        self.assertNotIn("diazoxide/charter/branches", source)


class TheRepositoriesAreTheOnesThatKeepTheirNames(unittest.TestCase):
    def test_the_marketplace_is_charter_plane(self):
        self.assertEqual(plugincache.MARKETPLACE_SOURCE, "diazoxide/charter-plane")
        add, _install = plugincache.install_argvs()
        self.assertEqual(add[-1], "diazoxide/charter-plane")

    def test_codex_is_told_the_same_marketplace(self):
        add = wiring.CODEX_COMMANDS[0]
        self.assertEqual(add[-1], "https://github.com/diazoxide/charter-plane")

    def test_reports_go_to_the_app(self):
        self.assertEqual(report.DEFAULT_UPSTREAM, "diazoxide/charter")
        with mock.patch.dict("os.environ", {"CHARTER_UPSTREAM_REPO": ""}):
            self.assertEqual(report.upstream_repo(), "diazoxide/charter")

    def test_the_package_metadata_sends_the_app_to_the_app_and_the_source_to_the_plane(self):
        urls = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["urls"]
        self.assertEqual(urls["Homepage"], "https://github.com/diazoxide/charter/releases")
        self.assertEqual(urls["Issues"], "https://github.com/diazoxide/charter/issues")
        for name in ("Repository", "Source", "Changelog"):
            with self.subTest(name=name):
                self.assertTrue(urls[name].startswith(
                    "https://github.com/diazoxide/charter-plane"), urls[name])


class TheNoticeReachesAPersonAndNoParser(unittest.TestCase):
    def test_version_keeps_its_one_line_of_stdout(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                self.assertRaises(SystemExit) as done:
            cli.main(["--version"])
        self.assertEqual(done.exception.code, 0)
        self.assertEqual(out.getvalue(), f"charter {channel.build_label()}\n")
        self.assertIn(NOTICE, err.getvalue())

    def _notice_for(self, typed: str, *, tty: bool) -> str:
        err = io.StringIO()
        err.isatty = lambda: tty
        with contextlib.redirect_stderr(err):
            cli._end_of_life_notice(typed)
        return err.getvalue()

    def test_a_person_at_a_terminal_is_told_once(self):
        self.assertEqual(self._notice_for("doctor", tty=True).count(NOTICE), 1)

    def test_a_pipe_is_told_nothing(self):
        self.assertEqual(self._notice_for("doctor", tty=False), "")

    def test_hooks_the_status_line_the_frame_and_internal_children_are_told_nothing(self):
        for typed in ("hook", "statusline", "gl-refresh", "tool-gate", "frame",
                      "frame-gather", "_version-check", "_autosave"):
            with self.subTest(typed=typed):
                self.assertEqual(self._notice_for(typed, tty=True), "")

    def test_update_and_version_are_not_told_twice(self):
        for typed in ("update", "version"):
            with self.subTest(typed=typed):
                self.assertEqual(self._notice_for(typed, tty=True), "")


if __name__ == "__main__":       # pragma: no cover
    unittest.main()
