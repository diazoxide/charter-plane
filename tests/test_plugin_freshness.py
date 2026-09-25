"""The installed plugin versus the marketplace clone — by CONTENT, not by version string.

The gap this covers is live, and was measured on a real machine while it was written: the
marketplace clone at ``main``, the installed cache at whatever ``main`` was when the plugin
was last installed, **both saying 0.51.0**, 45 files apart — ``skills/secrets/SKILL.md``
and ``skills/browser/SKILL.md`` among them — and ``claude plugin update charter@charter``
correctly answering *already at the latest version*. Version-keyed updates cannot see this,
because charter's plugin version moves exactly once per release and the clone moves
whenever Claude Code re-fetches it.

Two consequences, both tested here:

* `doctor.check_plugin_freshness` compares files and says so.
* `charter update` on the dev channel force-refreshes, because uninstall + reinstall is the
  only mechanism that repopulates a version-keyed cache directory.

**What is NOT broken, so that nothing here "fixes" it:** ``hooks/hooks.json`` invokes
``charter hook … --plugin-version 0.51.0`` — the *command*, resolved from ``PATH``, i.e.
the ``uv tool`` install. Hook behaviour follows the CLI, not the plugin's bundled copy of
``charter/*.py``. The staleness that bites is the skills, which are text the model loads.

No test here runs `claude`. `plugincache._claude_json` is the one seam every call goes
through and it is stubbed; a test that reached the real CLI would mutate the developer's
own plugin installation.
"""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from charter import config, doctor, plugincache, util
from tests._isolation import PersonaIso

REPO = Path(__file__).resolve().parents[1]


def tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return root


def tracked_top_level_directories(repo: Path = REPO) -> set[str]:
    """Every top-level directory this repository TRACKS — read from the index, not the disk.

    The question the classification below asks is about the repository: what does charter
    ship, and does a plugin load it. A directory that is not in the index is not shipped, so
    it cannot be an answer to that question — it is an artefact of whoever is running the
    suite. `git ls-files` is the same seam `tests/test_workflows.tracked` uses, and for the
    same reason: a denylist of local artefacts (`.venv`, `dist`, `.pytest_cache`) is a guess
    at where untracked content lives, and the index is the answer.

    `check=True` on purpose. If the index cannot be read this test has nothing to say, and
    saying nothing quietly — an empty set, which classifies vacuously — is the shape of guard
    that reports green forever.

    **What this does not see**, stated because a guard that overclaims is the defect twice
    over: a top-level *submodule*. `git ls-files` prints a gitlink as a bare path with no
    slash, indistinguishable here from a tracked top-level file, so one would be classified
    as neither. charter has no submodules and `dependencies = []`; adding one at the top
    level would need `ls-files -s` and a mode-160000 check here.
    """
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z"],
        capture_output=True, check=True, text=True)
    return {p.split("/", 1)[0] for p in out.stdout.split("\0") if p and "/" in p}


#: Top-level directories this repo ships that a Claude Code plugin does NOT load.
#:
#: The other half of the classification `test_every_top_level_directory_is_classified`
#: enforces. `.claude/` is here rather than in the surface on purpose: a plugin's agents
#: live in `<plugin>/agents/`, and this repo's `.claude/agents/` is its OWN project
#: configuration, which travels into the cache because the marketplace entry is
#: `"source": "./"` and is not loaded as plugin content.
#:
#: **Every name here must be a tracked directory**, and a test holds it to that. `.git` and
#: `dist` used to be listed, back when the classification enumerated the filesystem; they
#: are not repo content, and keeping untracked names here is how the list would grow one
#: developer's machine at a time — `.charter`, `.superpowers`, `.venv`, `.idea` — until it
#: classified nothing.
#: `tools/` is developer tooling — `tools/sweep.py` runs the deletion sweep over a branch.
#: No plugin loads it, `pyproject.toml` names `charter` as the only package so no wheel
#: ships it, and an edit to it is not a stale plugin.
_NOT_PLUGIN_SURFACE = {
    ".github", ".claude", "charter", "docs", "tests", "personas", "workspaces", "tools",
}

PLUGIN = {
    ".claude-plugin/plugin.json": '{"name": "charter", "version": "0.51.0"}',
    "hooks/hooks.json": '{"hooks": {}}',
    "skills/secrets/SKILL.md": "# secrets\n",
    "skills/browser/SKILL.md": "# browser\n",
}


class TheHashCoversWhatThePluginLoads(PersonaIso):
    def _pair(self, extra_left=None, extra_right=None):
        left = tree(self.tmp / "installed", {**PLUGIN, **(extra_left or {})})
        right = tree(self.tmp / "clone", {**PLUGIN, **(extra_right or {})})
        return left, right

    def test_two_identical_trees_hash_the_same(self):
        left, right = self._pair()
        self.assertEqual(plugincache.content_hash(left), plugincache.content_hash(right))
        self.assertIsNotNone(plugincache.content_hash(left))

    def test_an_edited_skill_changes_the_hash(self):
        """The case that actually happened: same version on both sides, different text."""
        left, right = self._pair(extra_right={"skills/secrets/SKILL.md": "# secrets v2\n"})
        self.assertNotEqual(plugincache.content_hash(left), plugincache.content_hash(right))

    def test_an_added_file_changes_the_hash(self):
        left, right = self._pair(extra_right={"skills/newthing/SKILL.md": "# new\n"})
        self.assertNotEqual(plugincache.content_hash(left), plugincache.content_hash(right))

    def test_a_renamed_file_changes_the_hash_even_with_identical_bytes(self):
        """The path goes into the digest, not only the bytes. Without that, moving a skill
        from one directory to another — which changes which skill the model loads — would
        hash identically to not having moved it, and this check would report a tree that
        loads different instructions as being in step."""
        left = tree(self.tmp / "a", PLUGIN)
        moved = {k: v for k, v in PLUGIN.items() if k != "skills/secrets/SKILL.md"}
        moved["skills/vault/SKILL.md"] = PLUGIN["skills/secrets/SKILL.md"]
        right = tree(self.tmp / "b", moved)
        self.assertNotEqual(plugincache.content_hash(left), plugincache.content_hash(right))

    def test_a_deleted_file_changes_the_hash(self):
        left, right = self._pair()
        (right / "skills/browser/SKILL.md").unlink()
        self.assertNotEqual(plugincache.content_hash(left), plugincache.content_hash(right))

    def test_churn_outside_the_plugin_surface_is_not_staleness(self):
        """charter's marketplace entry is ``"source": "./"`` — the whole repository is
        copied into the cache, ``tests/`` and ``docs/`` and all. Hashing the copy wholesale
        would report a test-file edit as a stale plugin, which is not a stricter check but
        a noisier one: a row that warns about something benign trains people to scroll past
        the row, which costs the case that matters."""
        left, right = self._pair(extra_right={"tests/test_x.py": "assert True\n",
                                              "docs/news/unreleased-x.md": "hi\n",
                                              "README.md": "different\n",
                                              "charter/cli.py": "print(1)\n"})
        self.assertEqual(plugincache.content_hash(left), plugincache.content_hash(right))

    def test_a_missing_tree_is_none_rather_than_an_empty_hash(self):
        """"I could not look" must never render as "they match" — the same distinction
        `hooks.dispatched_handlers` documents at length, and the whole reason `doctor`
        reports WARN rather than a green tick when it cannot compare."""
        self.assertIsNone(plugincache.content_hash(self.tmp / "nothing-here"))
        self.assertIsNone(plugincache.content_hash(self.tmp / "installed" / "no" / "such"))

    def test_the_hash_of_an_empty_surface_is_not_the_hash_of_a_populated_one(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        left, _ = self._pair()
        self.assertNotEqual(plugincache.content_hash(empty), plugincache.content_hash(left))

    def test_every_top_level_directory_is_classified_one_way_or_the_other(self):
        """The constant is a whitelist, so a plugin directory missing from it is a whole
        category of drift this module reports as clean.

        **Enumerated from the index, and classified exhaustively.** The first version of
        this test built its `shipped` set from a hardcoded literal identical to
        `PLUGIN_SURFACE` and then asserted one was a subset of the other — true by
        construction. It caught a *removal* from the constant and could not catch the
        *addition* its own docstring claimed it caught.

        The second version enumerated `REPO.iterdir()`, which is the developer's filesystem
        rather than the repository. It passed in CI, in a `git archive` extraction and in a
        linked worktree, and failed on the one machine charter is actually used from: a real
        plane has a gitignored `.charter/` (its state) and a gitignored `.superpowers/` (SDD
        workspaces), and neither is an answer to "does a plugin load it" — they are not
        shipped at all.

        So this asks the *index* what directories the repository has, and requires every one
        of them to be in exactly one of two lists. Add `mcp/` or `commands/` to charter
        tomorrow and this fails on the PR that commits it, until somebody decides which it
        is — which is the decision the check needs made, and the only thing a test can
        usefully force. A directory that exists only on one machine is not that decision.
        """
        tops = tracked_top_level_directories()
        unclassified = tops - set(plugincache.PLUGIN_SURFACE) - _NOT_PLUGIN_SURFACE
        self.assertEqual(
            unclassified, set(),
            f"new top-level director{'y' if len(unclassified) == 1 else 'ies'} "
            f"{sorted(unclassified)}: does a Claude Code plugin LOAD it? Add it to "
            f"plugincache.PLUGIN_SURFACE, or to _NOT_PLUGIN_SURFACE in this file.")

    def test_the_classification_reads_the_index_and_not_the_working_directory(self):
        """The property #529 is about, held directly rather than left to CI's clean tree.

        An untracked directory — `.charter/`, `.superpowers/`, `.venv/`, a scratch dir — must
        not reach the classification, and a tracked one must. Both halves against a real
        throwaway git repository, because the seam being tested *is* git: asserting against a
        faked `subprocess.run` would only prove the parsing, and the parsing was never the
        defect.
        """
        repo = self.tmp / "planeish"
        (repo / "skills").mkdir(parents=True)
        (repo / "skills" / "SKILL.md").write_text("# x\n")
        for local in (".charter", ".superpowers", ".venv"):
            (repo / local).mkdir()
            (repo / local / "junk.json").write_text("{}\n")
        # A throwaway index, not the developer's: every GIT_* the ambient environment
        # carries is dropped, and both config files are pointed at nothing.
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                   HOME=str(self.tmp))

        def run(*args):
            subprocess.run(["git", "-C", str(repo), *args], check=True,
                           capture_output=True, text=True, env=env)

        run("init", "-q")
        run("add", "skills/SKILL.md")

        self.assertEqual(tracked_top_level_directories(repo), {"skills"},
                         "an untracked directory reached the classification")

        (repo / "commands").mkdir()
        (repo / "commands" / "go.md").write_text("# go\n")
        run("add", "commands/go.md")
        self.assertEqual(tracked_top_level_directories(repo), {"skills", "commands"},
                         "a committed directory did NOT reach the classification")

    def test_nothing_untracked_can_be_parked_in_the_not_plugin_surface_list(self):
        """The workaround #529 forbids, refused mechanically.

        The cheap fix for "`.charter/` fails the classification" is to write `.charter` into
        `_NOT_PLUGIN_SURFACE` — green on that machine, and the list then grows by one name
        per developer while the check quietly stops classifying anything. Every name in that
        constant is a directory this repository *ships*, so every name must be in the index.

        `PLUGIN_SURFACE` is deliberately not held to this: it names what a plugin loads *if
        present*, and `commands/` and `agents/` are two Claude Code surfaces charter does not
        use yet.
        """
        tracked = tracked_top_level_directories()
        stale = _NOT_PLUGIN_SURFACE - tracked
        self.assertEqual(
            stale, set(),
            f"_NOT_PLUGIN_SURFACE names {sorted(stale)}, which this repository does not "
            f"track. This list classifies directories charter SHIPS; a local artefact "
            f"belongs in .gitignore, not here (see #529).")

    def test_the_three_directories_the_plugin_loads_today_are_covered(self):
        """The removal half, named concretely so the pair covers both directions."""
        for name in (".claude-plugin", "hooks", "skills"):
            with self.subTest(name=name):
                self.assertTrue((REPO / name).is_dir(), f"{name}/ has moved")
                self.assertIn(name, plugincache.PLUGIN_SURFACE)

    def test_the_repos_own_plugin_surface_hashes(self):
        """End-to-end against the real tree: whatever else is true, this must produce a
        digest for the checkout the suite is running in."""
        self.assertIsNotNone(plugincache.content_hash(REPO))


class DifferingNamesThePaths(PersonaIso):
    """A doctor row that names `skills/secrets/SKILL.md` is the difference between a number
    a reader distrusts and a fact they can go and look at."""

    def test_it_names_an_edited_file(self):
        left = tree(self.tmp / "a", PLUGIN)
        right = tree(self.tmp / "b", {**PLUGIN, "skills/secrets/SKILL.md": "changed\n"})
        self.assertEqual(plugincache.differing(left, right), ["skills/secrets/SKILL.md"])

    def test_it_names_a_file_present_on_only_one_side(self):
        left = tree(self.tmp / "a", PLUGIN)
        right = tree(self.tmp / "b", {**PLUGIN, "skills/new/SKILL.md": "x\n"})
        self.assertIn("skills/new/SKILL.md", plugincache.differing(left, right))

    def test_identical_trees_name_nothing(self):
        left = tree(self.tmp / "a", PLUGIN)
        right = tree(self.tmp / "b", PLUGIN)
        self.assertEqual(plugincache.differing(left, right), [])

    def test_it_stops_at_the_limit_rather_than_listing_forty_five_files(self):
        left = tree(self.tmp / "a", PLUGIN)
        right = tree(self.tmp / "b", {**PLUGIN,
                                      **{f"skills/s{i}/SKILL.md": "x\n" for i in range(20)}})
        self.assertEqual(len(plugincache.differing(left, right)), 3)
        self.assertEqual(len(plugincache.differing(left, right, limit=5)), 5)


class TheRefreshCommandsAreConstants(unittest.TestCase):
    """`claude plugin list --json` is a machine's own output rather than a committed file,
    so this is a narrower hazard than `charter.toml`'s — but it is still input, and it still
    reaches an argv."""

    def test_the_three_steps_are_in_the_order_that_was_verified_to_work(self):
        """Measured, not reasoned about. `install` alone against an already-installed plugin
        answers *"already installed"* and leaves the cache untouched; without `marketplace
        update` first, the reinstall faithfully re-copies the same stale content."""
        argvs = plugincache.refresh_argvs("charter@charter", "project")
        self.assertEqual([a[2] for a in argvs], ["marketplace", "uninstall", "install"])
        self.assertEqual(argvs[0], ["claude", "plugin", "marketplace", "update", "charter"])
        self.assertEqual(argvs[1], ["claude", "plugin", "uninstall", "charter@charter",
                                    "--scope", "project", "-y"])
        self.assertEqual(argvs[2], ["claude", "plugin", "install", "charter@charter",
                                    "--scope", "project", "-y"])

    def test_a_scope_charter_does_not_know_builds_nothing(self):
        for scope in ("global", "", None, "project;rm -rf /", "--force", 1, ["project"]):
            with self.subTest(scope=scope):
                self.assertIsNone(plugincache.refresh_argvs("charter@charter", scope))

    def test_a_plugin_id_charter_does_not_recognise_builds_nothing(self):
        """`util.run` takes a list and never a shell string, so the shell is not the
        exposure; the exposure is an element beginning with `-` that `claude` reads as a
        FLAG rather than as the plugin to uninstall."""
        for pid in ("--scope", "-y", "charter", "charter@", "@charter", "",
                    "charter@charter extra", "charter@charter\nrm -rf /",
                    "charter@charter;id", "a/b@c", None, 7, "charter@charter@charter"):
            with self.subTest(pid=pid):
                self.assertIsNone(plugincache.refresh_argvs(pid, "project"))

    def test_every_element_of_every_step_is_free_of_shell_metacharacters(self):
        argvs = plugincache.refresh_argvs("charter@charter", "user")
        for argv in argvs:
            for element in argv:
                for ch in (";", "|", "&", "`", "$", "\n", " "):
                    self.assertNotIn(ch, element)

    def test_all_three_scopes_are_accepted(self):
        for scope in ("user", "project", "local"):
            self.assertIsNotNone(plugincache.refresh_argvs("charter@charter", scope))


class ReadingTheInstalledPlugin(unittest.TestCase):
    """Everything talks to `claude plugin … --json`, never to Claude Code's own files —
    `~/.claude/plugins/*` is an internal charter does not own, and `bin/edm` bet on an
    internal path and broke silently (#197)."""

    def _rows(self, rows):
        return mock.patch.object(plugincache, "_claude_json", return_value=rows)

    def test_the_charter_entry_is_found_among_others(self):
        rows = [{"id": "figma@official", "scope": "user", "installPath": "/x"},
                {"id": "charter@charter", "scope": "project", "installPath": "/y",
                 "projectPath": "/p"}]
        with self._rows(rows), mock.patch.object(plugincache, "available",
                                                 return_value=True):
            got = plugincache.installed_charter_plugin()
        self.assertEqual(got["id"], "charter@charter")

    def test_an_entry_charter_would_not_act_on_is_not_returned_at_all(self):
        """Validated where it is read, so no caller has to remember to check — the same
        placement argument `instance._HOTKEY_RE` makes for the config boundary."""
        for row in ({"id": "charter@charter", "scope": "root", "installPath": "/y"},
                    {"id": "-charter@charter", "scope": "user", "installPath": "/y"},
                    {"id": "charter@charter x", "scope": "user", "installPath": "/y"},
                    {"id": 7, "scope": "user"},
                    "not-a-dict"):
            with self.subTest(row=row):
                with self._rows([row]), mock.patch.object(plugincache, "available",
                                                          return_value=True):
                    self.assertIsNone(plugincache.installed_charter_plugin())

    def test_a_plugin_that_is_not_charter_is_not_charters_to_reinstall(self):
        rows = [{"id": "charterly@charter", "scope": "user", "installPath": "/y"}]
        with self._rows(rows), mock.patch.object(plugincache, "available",
                                                 return_value=True):
            self.assertIsNone(plugincache.installed_charter_plugin())

    def test_the_entry_for_the_plane_you_are_standing_in_wins(self):
        """Every project-scoped install points at the SAME versioned cache directory, so
        which one is chosen does not change the outcome — it changes which project's
        `claude plugin` invocation performs it, and the plane you are standing in is the
        least surprising choice."""
        rows = [{"id": "charter@charter", "scope": "project", "installPath": "/y",
                 "projectPath": "/elsewhere"},
                {"id": "charter@charter", "scope": "project", "installPath": "/y",
                 "projectPath": "/here"}]
        with self._rows(rows), mock.patch.object(plugincache, "available",
                                                 return_value=True):
            got = plugincache.installed_charter_plugin("/here")
        self.assertEqual(got["projectPath"], "/here")

    def test_a_list_that_could_not_be_read_is_unknown_and_not_nothing_installed(self):
        """The distinction `_claude_json`'s docstring states as a rule and the caller used
        to throw away one line later.

        Both collapsed to `None`, and `doctor` renders `None` as a GREEN *"the charter
        plugin is not installed here"* — so any `claude` too old to understand `--json`
        got a tick over a plugin nobody had looked at, which is the population most likely
        to be running a stale one. The previous version of this test asserted the collapse
        rather than catching it.
        """
        for rows in (None, {}, "[]", 7):
            with self.subTest(rows=rows):
                with self._rows(rows), mock.patch.object(plugincache, "available",
                                                         return_value=True):
                    got = plugincache.installed_charter_plugin()
                self.assertIs(got, plugincache.UNKNOWN)

    def test_a_list_that_WAS_read_and_holds_no_charter_is_plainly_none(self):
        """The other side of the same distinction: looked, and it is not installed. A
        supported state (`docs/install.md` documents a CLI-only install), so it must NOT
        report as unknown or the row warns forever on a plane with no plugin."""
        with self._rows([]), mock.patch.object(plugincache, "available",
                                               return_value=True):
            self.assertIsNone(plugincache.installed_charter_plugin())

    def test_the_reads_are_bounded_by_the_same_budget_every_other_check_uses(self):
        """`doctor` runs as a SessionStart preflight with a 20s hook budget, and this check
        makes two `claude plugin` reads. At 15s each that was 30s against 20s — and the
        constant's own comment cited the 20s budget while exceeding it. Pinned to
        `CHECK_TIMEOUT` rather than to a number, so the two cannot drift."""
        self.assertEqual(plugincache.LIST_TIMEOUT, doctor.CHECK_TIMEOUT)

    def test_a_claude_that_never_returns_does_not_take_the_preflight_down(self):
        """`util.run` raises `ProcTimeout` regardless of `check=False`, and nothing caught
        it: not `_claude_json`, not the check, and not `doctor._checks()` — an eager list
        literal with no per-check guard. `hooks/hooks.json` renders a non-zero `charter
        doctor` as "charter preflight failed - fix before working:" at EVERY SessionStart,
        so a hanging `claude` printed zero rows and that line.

        Demonstrated end to end before the fix: 27 rows on origin/main, zero rows and
        EXIT=1 here.
        """
        with mock.patch.object(plugincache, "available", return_value=True), \
                mock.patch.object(plugincache.util, "run",
                                  side_effect=util.ProcTimeout(["claude"], 5)):
            self.assertIsNone(plugincache._claude_json(["list"]))

    def test_a_claude_removed_between_the_which_and_the_exec_is_not_a_crash(self):
        """`shutil.which` in `available()` and the exec in `util.run` are two moments. A
        `FileNotFoundError` from the gap reached the crash reporter the same way a timeout
        did."""
        with mock.patch.object(plugincache, "available", return_value=True), \
                mock.patch.object(plugincache.util, "run",
                                  side_effect=FileNotFoundError("claude")):
            self.assertIsNone(plugincache._claude_json(["list"]))

    def test_only_charters_own_marketplace_id_is_recognised(self):
        """`charter@charter` exactly, not `charter@<anything>`.

        `force_refresh` UNINSTALLS what this returns. A plugin called `charter` published
        by somebody else's marketplace is not charter's to uninstall, and the id anyone who
        followed `docs/install.md` has is this one — a marketplace registers under the name
        its own `marketplace.json` declares.
        """
        rows = [{"id": "charter@someone-else", "scope": "user", "installPath": "/y"}]
        with self._rows(rows), mock.patch.object(plugincache, "available",
                                                 return_value=True):
            self.assertIsNone(plugincache.installed_charter_plugin())
        self.assertEqual(plugincache.PLUGIN_ID, "charter@charter")

    def test_a_marketplace_name_charter_would_not_build_a_path_from_is_refused(self):
        for name in ("../../etc", "char ter", "-x", "", None, 7, "a/b"):
            with self.subTest(name=name):
                with mock.patch.object(plugincache, "_claude_json") as looked:
                    self.assertIsNone(plugincache.marketplace_clone(name))
                looked.assert_not_called()

    def test_force_refresh_declines_cleanly_with_no_claude_on_path(self):
        """charter supports opencode and Codex; a plane on either has no plugin cache. This
        must be a plain "nothing to do", not an error and not a claim of success."""
        with mock.patch.object(plugincache, "available", return_value=False):
            ok, detail = plugincache.force_refresh()
        self.assertFalse(ok)
        self.assertIn("claude", detail)

    def test_force_refresh_declines_when_no_charter_plugin_is_installed(self):
        with mock.patch.object(plugincache, "available", return_value=True), \
                self._rows([]):
            ok, detail = plugincache.force_refresh()
        self.assertFalse(ok)
        self.assertIn("no charter plugin is installed", detail)

    def test_force_refresh_stops_at_the_first_failing_step_and_names_it(self):
        rows = [{"id": "charter@charter", "scope": "user", "installPath": "/y"}]
        calls = []

        def run(cmd, cwd=None, check=True, **kw):
            calls.append(list(cmd))
            code = 1 if "uninstall" in cmd else 0
            return mock.Mock(returncode=code, stdout="", stderr="boom")

        with mock.patch.object(plugincache, "available", return_value=True), \
                self._rows(rows), mock.patch.object(plugincache.util, "run", run):
            ok, detail = plugincache.force_refresh()
        self.assertFalse(ok)
        self.assertIn("uninstall", detail)
        self.assertEqual(len(calls), 2, "it must not go on to install after a failure")

    def test_force_refresh_runs_all_three_steps_on_success(self):
        rows = [{"id": "charter@charter", "scope": "user", "installPath": "/y"}]
        calls = []

        def run(cmd, cwd=None, check=True, **kw):
            calls.append(list(cmd))
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(plugincache, "available", return_value=True), \
                self._rows(rows), mock.patch.object(plugincache.util, "run", run):
            ok, _ = plugincache.force_refresh()
        self.assertTrue(ok)
        self.assertEqual([c[2] for c in calls], ["marketplace", "uninstall", "install"])

    def test_a_failure_AFTER_the_uninstall_leads_with_what_the_operator_now_has(self):
        """The one outcome that must not read as a generic command failure.

        This is not rollback-capable: the uninstall is what makes the install do any work,
        so a failure between them leaves the plugin GONE for that scope. By the time this
        runs the CLI has already been replaced and the harness artifact already moved — the
        operator is several steps into a successful update, and a line naming only the argv
        that broke leaves them to work out on their own that a plugin went missing.
        """
        rows = [{"id": "charter@charter", "scope": "user", "installPath": "/y"}]

        def run(cmd, cwd=None, check=True, **kw):
            code = 1 if "install" in cmd and "uninstall" not in cmd else 0
            return mock.Mock(returncode=code, stdout="", stderr="boom")

        with mock.patch.object(plugincache, "available", return_value=True), \
                self._rows(rows), mock.patch.object(plugincache.util, "run", run):
            ok, detail = plugincache.force_refresh()
        self.assertFalse(ok)
        self.assertIn("UNINSTALLED", detail)
        self.assertIn("claude plugin install charter@charter", detail)

    def test_a_failure_BEFORE_the_uninstall_does_not_claim_anything_was_removed(self):
        """The counterpart. Saying "the plugin is now uninstalled" when it is not would be
        the same defect pointing the other way."""
        rows = [{"id": "charter@charter", "scope": "user", "installPath": "/y"}]

        def run(cmd, cwd=None, check=True, **kw):
            code = 1 if "marketplace" in cmd else 0
            return mock.Mock(returncode=code, stdout="", stderr="offline")

        with mock.patch.object(plugincache, "available", return_value=True), \
                self._rows(rows), mock.patch.object(plugincache.util, "run", run):
            ok, detail = plugincache.force_refresh()
        self.assertFalse(ok)
        self.assertNotIn("UNINSTALLED", detail)
        self.assertIn("marketplace", detail)

    def test_force_refresh_will_not_uninstall_what_it_could_not_read(self):
        """`UNKNOWN` must not fall through to the "nothing installed" branch, and above all
        must not reach the uninstall: charter does not know what is there."""
        calls = []

        def run(cmd, **kw):
            calls.append(list(cmd))
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(plugincache, "available", return_value=True), \
                self._rows(None), mock.patch.object(plugincache.util, "run", run):
            ok, detail = plugincache.force_refresh()
        self.assertFalse(ok)
        self.assertEqual(calls, [])
        self.assertIn("could not read", detail)


class DoctorReportsFreshnessOnBothChannels(PersonaIso):
    """The severity differs by channel, and that is not hedging.

    The marketplace clone tracks ``main``, which Claude Code re-fetches on its own, so SOME
    drift is the steady state for every stable plane from the day after a release onward.
    A warning there would be a permanent yellow row whose only honest fix is "wait for the
    next release" — the cry-wolf failure `doctor`'s own comments keep returning to. On dev
    the plane asked to track ``main`` and its plugin is not, which is a real gap with a real
    command that closes it.
    """

    def _check(self, installed, clone, channel="stable", version="0.51.0"):
        entry = {"id": "charter@charter", "scope": "project", "version": version,
                 "installPath": str(installed), "projectPath": str(self.tmp)}
        with mock.patch.object(config, "UPDATE", {"channel": channel}), \
                mock.patch.object(plugincache, "available", return_value=True), \
                mock.patch.object(plugincache, "installed_charter_plugin",
                                  return_value=entry), \
                mock.patch.object(plugincache, "marketplace_clone",
                                  return_value=Path(clone) if clone else None):
            return doctor.check_plugin_freshness()

    def test_matching_trees_are_green_on_both_channels(self):
        left = tree(self.tmp / "a", PLUGIN)
        right = tree(self.tmp / "b", PLUGIN)
        for ch in ("stable", "dev"):
            with self.subTest(channel=ch):
                res = self._check(left, right, channel=ch)
                self.assertEqual(res.status, doctor.OK)
                self.assertIn("matches", res.detail)

    def test_drift_on_the_dev_channel_is_a_warning_that_names_the_command(self):
        left = tree(self.tmp / "a", PLUGIN)
        right = tree(self.tmp / "b", {**PLUGIN, "skills/secrets/SKILL.md": "moved on\n"})
        res = self._check(left, right, channel="dev")
        self.assertEqual(res.status, doctor.WARN)
        self.assertIn("skills/secrets/SKILL.md", res.detail)
        self.assertIn("charter update", res.hint)


    def test_drift_on_the_stable_channel_is_reported_in_detail_not_in_a_hint(self):
        """`Result.render` drops the hint entirely at OK, so guidance written there would
        be invisible while looking shipped — which is the failure ADR 0013 is about, and an
        unusually poor place to commit it."""
        left = tree(self.tmp / "a", PLUGIN)
        right = tree(self.tmp / "b", {**PLUGIN, "skills/secrets/SKILL.md": "moved on\n"})
        res = self._check(left, right, channel="stable")
        self.assertEqual(res.status, doctor.OK)
        self.assertIn("skills/secrets/SKILL.md", res.detail)
        self.assertIn("claude plugin update", res.detail)
        self.assertIn(res.detail, res.render())

    def test_the_row_never_fails_and_so_never_blocks_a_session(self):
        """`cmd_doctor` exits non-zero only on FAIL, and that exit code is what makes the
        SessionStart preflight print. A plugin whose skills are a week old is not a reason
        to shout at every session start on every plane."""
        left = tree(self.tmp / "a", PLUGIN)
        right = tree(self.tmp / "b", {**PLUGIN, "skills/secrets/SKILL.md": "x\n"})
        for ch in ("stable", "dev"):
            self.assertNotEqual(self._check(left, right, channel=ch).status, doctor.FAIL)

    def test_a_marketplace_it_cannot_locate_is_not_checked_rather_than_green(self):
        left = tree(self.tmp / "a", PLUGIN)
        res = self._check(left, None, channel="dev")
        self.assertEqual(res.status, doctor.WARN)
        self.assertIn("not checked", res.detail)

    def test_an_unreadable_install_path_is_not_checked_rather_than_green(self):
        right = tree(self.tmp / "b", PLUGIN)
        res = self._check(self.tmp / "gone", right, channel="stable")
        self.assertEqual(res.status, doctor.WARN)
        self.assertIn("not checked", res.detail)

    def test_no_claude_on_path_is_a_plain_green_nothing_to_compare(self):
        with mock.patch.object(plugincache, "available", return_value=False):
            res = doctor.check_plugin_freshness()
        self.assertEqual(res.status, doctor.OK)
        self.assertIn("no `claude`", res.detail)

    def test_a_list_that_could_not_be_read_is_a_warning_not_a_tick(self):
        """The row an older `claude` gets — one that does not understand `--json`, i.e. the
        population most likely to be running a stale plugin. It used to render:

            ✓  plugin files     the charter plugin is not installed here

        which is the #171 defect exactly: "a check that silently does nothing is worse than
        no check". The sibling branch three lines below it (marketplace not located) always
        got this right, which is what made the inconsistency visible.
        """
        with mock.patch.object(plugincache, "available", return_value=True), \
                mock.patch.object(plugincache, "installed_charter_plugin",
                                  return_value=plugincache.UNKNOWN):
            res = doctor.check_plugin_freshness()
        self.assertEqual(res.status, doctor.WARN)
        self.assertIn("not checked", res.detail)
        self.assertEqual(res.hint, doctor._NOT_CHECKED_HINT)
        # The REASON, not merely the status. Deleting the `is UNKNOWN` branch still yields
        # a WARN — the sentinel falls through, `entry.get` raises on a bare object, and the
        # row-level crash guard catches it — so a test that stopped at the status would
        # accept "not checked ('object' object has no attribute 'get')" as though it were
        # this branch working. That is a guard passing because a different guard caught it.
        self.assertIn("claude plugin list", res.detail)

    def test_a_raising_check_costs_one_row_and_not_the_whole_preflight(self):
        """`doctor._checks()` is an eager list literal with no per-check guard, so one
        raising check returns NO rows — and `hooks/hooks.json` renders a non-zero `charter
        doctor` as "charter preflight failed - fix before working:" at every SessionStart.
        `plugincache` returns rather than raises on every path it owns; this is the belt for
        the paths it does not."""
        with mock.patch.object(plugincache, "available",
                               side_effect=RuntimeError("something unforeseen")):
            res = doctor.check_plugin_freshness()
        self.assertEqual(res.status, doctor.WARN)
        self.assertIn("not checked", res.detail)
        with mock.patch.object(plugincache, "available",
                               side_effect=RuntimeError("something unforeseen")):
            rows = doctor.run_all()
        self.assertGreater(len(rows), 20, "one bad check must not empty the preflight")
        self.assertIn("plugin files", [r.name for r in rows])

    def test_no_charter_plugin_installed_is_a_plain_green(self):
        """CLI-only is a supported install (`docs/install.md`), and a plane that never
        installed the plugin must not be warned about the plugin's freshness forever."""
        with mock.patch.object(plugincache, "available", return_value=True), \
                mock.patch.object(plugincache, "installed_charter_plugin",
                                  return_value=None):
            res = doctor.check_plugin_freshness()
        self.assertEqual(res.status, doctor.OK)
        self.assertIn("not installed", res.detail)

    def test_the_check_is_registered_so_doctor_actually_runs_it(self):
        """A check nobody calls is a check that does not exist. `_checks` is private, so
        this asks the public surface the SessionStart preflight uses."""
        with mock.patch.object(plugincache, "available", return_value=False):
            names = [r.name for r in doctor.run_all()]
        self.assertIn("plugin files", names)

    def test_it_does_not_replace_the_version_skew_row(self):
        """Two different questions — 'is the plugin newer than the CLI' and 'is the plugin
        the same files as the clone' — and losing either one loses a real guard."""
        with mock.patch.object(plugincache, "available", return_value=False):
            names = [r.name for r in doctor.run_all()]
        self.assertIn("plugin", names)
        self.assertIn("plugin files", names)


if __name__ == "__main__":
    unittest.main()
