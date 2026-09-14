"""A memory directory or a `changes/` charter cannot list is named, in the one sentence #1081 gave
what could not be checked, and never read as empty (#1084, ADR 0009).

`memstore.files` globbed a memory directory, and `Path.glob` answers an empty list for one it may
not read, on every interpreter. So `charter recall` searched a `memory/` at mode 000 as if it held
nothing and said so: "No memories match". `change.all_for` read a `changes/` it could not list as
no changes, and `charter change list` said "No changes in workspace". A search that did not look
read the same as a search that found nothing.

The fixtures are real refusals — a directory at mode 000 or 333 beside a readable one, restored in
cleanup — plus the refusal injected at both calls `Path.iterdir` makes on 3.11–3.14, so each is
pinned on whichever interpreter runs, as root too. Every sentence is spelled out by hand, not
rebuilt from the function that prints it.
"""

from __future__ import annotations

import contextlib
import errno
import io
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from charter import (change, cli, commands, commands_change, commands_persona, commands_workspace,
                     config, curate, doctor, hooks, memstore, persona, recall, workspace)
from tests._isolation import PersonaIso, make_plane

AS_ROOT = os.geteuid() == 0


def sentence(rel: str) -> str:
    return f"{rel} cannot be checked — restoring read access to it clears this."


def locked(case, d: Path, mode: int = 0o000) -> Path:
    """*d* at *mode*, put back to 0755 in cleanup (before the tmp tree is removed)."""
    d.chmod(mode)
    case.addCleanup(d.chmod, 0o755)
    return d


def refusing_to_list(directory: Path):
    """*directory* refusing to be LISTED at both calls `Path.iterdir` makes on 3.11–3.14, while
    `stat` of it still answers — mode 333's shape, and a refusal root cannot walk past."""
    real_listdir, real_scandir = os.listdir, os.scandir

    def refusing(real):
        def call(p=".", *args, **kwargs):
            if isinstance(p, (str, os.PathLike)) and Path(p) == directory:
                raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), str(p))
            return real(p, *args, **kwargs)
        return call

    stack = contextlib.ExitStack()
    stack.enter_context(mock.patch.object(os, "listdir", refusing(real_listdir)))
    stack.enter_context(mock.patch.object(os, "scandir", refusing(real_scandir)))
    return stack


def run(fn, **kw) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = fn(SimpleNamespace(**kw))
    return rc, out.getvalue(), err.getvalue()


class TwoMemoryDirectories(PersonaIso):
    """`workspaces/alpha/memory` and `workspaces/beta/memory`, one keycloak memory each."""

    def setUp(self) -> None:
        super().setUp()
        make_plane(self)
        for ws in ("alpha", "beta"):
            workspace.ensure(ws)
            workspace.scaffold(ws)
            memstore.write(workspace.memory_dir(ws), f"the keycloak token in {ws} rotates yearly",
                           title="keycloak token policy", timestamped=True)
        self.alpha = workspace.memory_dir("alpha")
        self.beta = workspace.memory_dir("beta")
        self.alpha_file = memstore.files(self.alpha)[0]


class TheStoreNamesWhatItCouldNotList(TwoMemoryDirectories):
    @unittest.skipIf(AS_ROOT, "root lists a directory whatever its mode")
    def test_a_real_directory_at_mode_000_or_333_is_unread_not_empty(self):
        for mode in (0o000, 0o333):
            with self.subTest(mode=oct(mode)):
                locked(self, self.alpha, mode)
                got = memstore.read_files(self.alpha)
                self.alpha.chmod(0o755)
                self.assertEqual(got, ([], [(self.alpha, errno.EACCES)]))

    def test_an_injected_refusal_to_list_is_unread_on_either_interpreter(self):
        with refusing_to_list(self.alpha):
            self.assertEqual(memstore.read_files(self.alpha), ([], [(self.alpha, errno.EACCES)]))

    def test_files_refuses_in_the_shared_sentence_rather_than_answering_none(self):
        with refusing_to_list(self.alpha):
            with self.assertRaises(workspace.CannotCheck) as cm:
                memstore.files(self.alpha)
        self.assertIsInstance(cm.exception, OSError)
        self.assertEqual(str(cm.exception), sentence("workspaces/alpha/memory"))
        self.assertEqual(cm.exception.unread, [(self.alpha, errno.EACCES)])

    def test_search_names_it_and_still_searches_the_rest(self):
        unread: list = []
        with refusing_to_list(self.alpha):
            hits = memstore.search([self.alpha, self.beta], "keycloak", unread=unread)
        self.assertEqual([p.parent for p, _t, _s in hits], [self.beta])
        self.assertEqual(unread, [(self.alpha, errno.EACCES)])

    def test_search_with_nowhere_to_name_it_refuses(self):
        with refusing_to_list(self.alpha):
            with self.assertRaises(workspace.CannotCheck):
                memstore.search([self.alpha, self.beta], "keycloak")
            with self.assertRaises(workspace.CannotCheck):
                memstore.duplicates([self.beta, self.alpha])

    def test_duplicates_names_it_and_still_compares_the_rest(self):
        memstore.write(self.beta, "the keycloak token in beta rotates yearly", title="again",
                       timestamped=True)
        unread: list = []
        with refusing_to_list(self.alpha):
            pairs = memstore.duplicates([self.alpha, self.beta], unread=unread)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(unread, [(self.alpha, errno.EACCES)])

    @unittest.skipIf(AS_ROOT, "root searches a directory whatever its mode")
    def test_an_entry_it_cannot_stat_is_unread_not_refused_as_no_memory(self):
        """Mode 666: the names can be listed and none of them `stat`-ed. Each is named."""
        second = memstore.write(self.alpha, "a second fact", title="second", timestamped=True)
        locked(self, self.alpha, 0o666)
        expected = sorted([(self.alpha_file, errno.EACCES), (second, errno.EACCES)])
        self.assertEqual(memstore.read_files(self.alpha), ([], expected))
        with self.assertRaises(workspace.CannotCheck) as cm:
            memstore.files(self.alpha)
        self.assertEqual(str(cm.exception), " ".join(
            sentence(f"workspaces/alpha/memory/{p.name}") for p, _code in expected))

    def test_a_path_outside_the_plane_is_named_whole(self):
        outside = Path("/elsewhere/memory")
        self.assertEqual(str(workspace.CannotCheck([(outside, errno.EACCES)])),
                         sentence("/elsewhere/memory"))

    def test_a_memory_directory_that_is_a_symlink_loop_names_the_loop(self):
        for p in self.alpha.iterdir():
            p.unlink()
        self.alpha.rmdir()
        self.alpha.symlink_to(self.alpha)
        self.assertEqual(memstore.read_files(self.alpha), ([], [(self.alpha, errno.ELOOP)]))
        with self.assertRaises(workspace.CannotCheck) as cm:
            memstore.entries(self.alpha)
        self.assertEqual(str(cm.exception), f"workspaces/alpha/memory cannot be checked — fix "
                                             f"the symlink loop at {self.alpha}.")

    def test_a_readable_or_absent_directory_names_nothing(self):
        """And lists only memories: not the index, not a file that is no `.md`, not a directory."""
        (self.beta / ".gitkeep").write_text("")
        (self.beta / "notes.txt").write_text("x")
        (self.beta / "archive").mkdir()
        self.assertEqual(memstore.read_files(self.beta), (memstore.files(self.beta), []))
        self.assertEqual([p.parent for p in memstore.files(self.beta)], [self.beta])
        self.assertTrue(memstore.files(self.beta)[0].name.endswith("-keycloak-token-policy.md"))
        self.assertEqual(memstore.read_files(self.tmp / "nowhere"), ([], []))

    def test_a_memory_directory_linked_out_of_the_plane_is_refused_not_unread(self):
        """The other side of the line: containment's refusal (#336) stays a refusal, asked before
        the listing. Restoring read access clears nothing there, so it is not named as unread."""
        import shutil
        import tempfile
        outside = Path(tempfile.mkdtemp(prefix="edm-outside-"))
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        (outside / "stolen.md").write_text("# stolen\n\nkeycloak secret\n")
        link = config.PERSONAS_DIR / "dev" / "memory"
        link.parent.mkdir(parents=True)
        link.symlink_to(outside, target_is_directory=True)
        self.assertEqual(memstore.read_files(link), ([], []))
        self.assertEqual(memstore.files(link), [])

    @unittest.skipIf(AS_ROOT, "root searches a directory whatever its mode")
    def test_a_memory_directory_under_a_parent_it_cannot_search_is_named(self):
        locked(self, workspace.workspace_dir("alpha"))
        self.assertEqual(memstore.read_files(self.alpha), ([], [(self.alpha, errno.EACCES)]))

    @unittest.skipIf(AS_ROOT, "root searches a directory whatever its mode")
    def test_resolve_refuses_rather_than_answering_no_such_memory(self):
        """`forget` and `archive` reach a memory through here. On 3.14 a directory at mode 000
        answered "nothing matched"; on 3.11–3.13 `Path.exists` raised past every handler."""
        locked(self, self.alpha)
        with self.assertRaises(workspace.CannotCheck):
            memstore.resolve(self.alpha, self.alpha_file.name)


class DoctorsMemoryRow(TwoMemoryDirectories):
    """`check_memory_indexes` lists each base before reading it (#1043), and a base it can list
    whose memories it cannot `stat` (mode 666) is one it could not read either: its drift is
    asked of `memstore.files`, which refuses there, and the row must not end in a traceback."""

    DETAIL = "; workspaces/alpha/memory/{} cannot be checked"

    def test_on_either_interpreter_each_memory_it_cannot_stat_is_named(self):
        from tests.test_a_workspace_listing_names_what_it_cannot_look_at import (
            BOTH_INTERPRETERS, unsearchable)
        for answers in BOTH_INTERPRETERS:
            with self.subTest(answers=answers):
                with unsearchable(self.alpha, answers):
                    r = doctor.check_memory_indexes()
                self.assertEqual(r.status, doctor.WARN, r)
                self.assertTrue(r.detail.endswith(self.DETAIL.format(self.alpha_file.name)),
                                r.detail)

    @unittest.skipIf(AS_ROOT, "root searches a directory whatever its mode")
    def test_a_real_base_at_mode_666(self):
        locked(self, self.alpha, 0o666)
        r = doctor.check_memory_indexes()
        self.assertEqual(r.status, doctor.WARN, r)
        self.assertTrue(r.detail.endswith(self.DETAIL.format(self.alpha_file.name)), r.detail)


class RecallNamesTheBaseItCouldNotSearch(TwoMemoryDirectories):
    def setUp(self) -> None:
        super().setUp()
        self.make_persona("dev", role="Dev")
        persona.remember("dev", "shared keycloak convention", shared=True)

    def test_the_gate_reports_it_beside_the_hits_it_found(self):
        with refusing_to_list(self.alpha):
            got = recall.recall("keycloak", workspace_name="alpha", persona_name="dev")
            listed = recall.recall(None, workspace_name="alpha", persona_name="dev")
        self.assertEqual(sorted({h.label for h in got.hits}), ["shared"])
        self.assertEqual(got.unread, [(self.alpha, errno.EACCES)])
        self.assertEqual(listed.unread, [(self.alpha, errno.EACCES)])
        labels = {h.label for h in listed.hits}
        self.assertIn("shared", labels)
        self.assertNotIn("workspace:alpha", labels)

    def test_a_readable_plane_reports_nothing_unread(self):
        self.assertEqual(recall.recall("keycloak", workspace_name="alpha",
                                       persona_name="dev").unread, [])
        for query in ("keycloak", "absent"):
            with self.subTest(query=query):
                _, _, err = self.recall_cmd(query)
                self.assertNotIn("not searched", err)
                self.assertNotIn("cannot be checked", err)

    def recall_cmd(self, query: str) -> tuple[int, str, str]:
        return run(commands.cmd_recall, query=query, scope=None, ephemeral=False, persona="dev",
                   workspace="alpha", all_workspaces=False, since=None, limit=8, full=False)

    @unittest.skipIf(AS_ROOT, "root lists a directory whatever its mode")
    def test_charter_recall_names_it_beside_what_it_found(self):
        locked(self, self.alpha)
        rc, out, err = self.recall_cmd("keycloak")
        self.assertEqual(rc, 0)
        self.assertIn("shared keycloak convention", out)
        self.assertIn(sentence("workspaces/alpha/memory"), err)
        self.assertIn("1 memory(ies) across workspace, persona, shared, refs; 1 base(s) not "
                      "searched — charter could not read them.", err)

    def test_with_no_hit_it_does_not_say_nothing_matches(self):
        with refusing_to_list(self.alpha):
            _, _, err = self.recall_cmd("rotates")
        self.assertIn(sentence("workspaces/alpha/memory"), err)
        self.assertNotIn("No memories match 'rotates' across workspace, persona, shared, refs.",
                         err)
        self.assertIn("No memories match 'rotates' across workspace, persona, shared, refs; "
                      "1 base(s) not searched — charter could not read them.", err)


class PersonaRecall(PersonaIso):
    def setUp(self) -> None:
        super().setUp()
        make_plane(self)
        self.make_persona("dev", role="Dev")
        self.own = persona.memory_dir("dev")
        # Written to the store, not through `persona.remember`: that records a trace event, and
        # the listing's activity section would then speak for a store it could not read.
        memstore.write(self.own, "own keycloak deploy fact", title="own keycloak deploy fact")

    def test_a_query_names_the_directory_it_could_not_search(self):
        persona.remember("dev", "shared keycloak convention", shared=True)
        with refusing_to_list(self.own):
            _, out, err = run(commands_persona.cmd_persona_recall, name="dev", query="keycloak",
                              log=8)
        self.assertIn("shared keycloak convention", out)
        self.assertIn(sentence("personas/dev/memory"), err)

    def test_a_query_with_no_hit_does_not_say_there_is_no_memory_of_it(self):
        with refusing_to_list(self.own):
            _, _, err = run(commands_persona.cmd_persona_recall, name="dev", query="keycloak",
                            log=8)
        self.assertIn(sentence("personas/dev/memory"), err)
        self.assertNotIn("no memory of 'keycloak'", err)

    @unittest.skipIf(AS_ROOT, "root lists a directory whatever its mode")
    def test_the_listing_does_not_say_it_has_no_memories_yet(self):
        locked(self, self.own)
        _, _, err = run(commands_persona.cmd_persona_recall, name="dev", query=None, log=8)
        self.assertIn(sentence("personas/dev/memory"), err)
        self.assertNotIn("has no memories yet", err)

    def test_the_listing_names_an_ephemeral_scratch_it_could_not_read(self):
        scratch = persona.ephemeral_dir("dev", False, None)
        scratch.mkdir(parents=True, exist_ok=True)
        with refusing_to_list(scratch):
            _, _, err = run(commands_persona.cmd_persona_recall, name="dev", query=None, log=8)
        self.assertIn(sentence(scratch.relative_to(config.ROOT).as_posix()), err)

    def test_a_readable_persona_names_nothing(self):
        _, out, err = run(commands_persona.cmd_persona_recall, name="dev", query="absent", log=8)
        self.assertIn("no memory of 'absent' for 'dev'.", err)
        self.assertNotIn("cannot be checked", err)


class WorkspaceRecall(TwoMemoryDirectories):
    @unittest.skipIf(AS_ROOT, "root lists a directory whatever its mode")
    def test_the_listing_names_it_and_does_not_say_there_are_none_yet(self):
        locked(self, self.alpha)
        _, _, err = run(commands_workspace.cmd_workspace_recall, workspace="alpha", query=None)
        self.assertIn(sentence("workspaces/alpha/memory"), err)
        self.assertNotIn("has no memories yet", err)

    def test_a_query_names_it_and_does_not_say_nothing_matches(self):
        with refusing_to_list(self.alpha):
            _, _, err = run(commands_workspace.cmd_workspace_recall, workspace="alpha",
                            query="keycloak")
        self.assertIn(sentence("workspaces/alpha/memory"), err)
        self.assertNotIn("No memories in 'alpha' match", err)


class AnIndexWriterDoesNotWorkFromAnUnlistedDirectory(TwoMemoryDirectories):
    @unittest.skipIf(AS_ROOT, "root lists a directory whatever its mode")
    def test_apply_safe_refuses_and_leaves_the_store_as_it_was(self):
        """Mode 333: the index is writable, the directory is not listable. Every "safe" op here —
        archive a duplicate, link an unindexed file — is decided from the listing, so one it
        could not make is no basis for touching MEMORY.md."""
        dup = memstore.write(self.alpha, "the keycloak token in alpha rotates yearly",
                             title="unindexed copy", timestamped=True, index=False)
        idx = memstore.index_path(self.alpha)
        before = idx.read_bytes()
        locked(self, self.alpha, 0o333)
        with self.assertRaises(workspace.CannotCheck) as cm:
            curate.apply_safe(self.alpha)
        self.alpha.chmod(0o755)
        self.assertEqual(str(cm.exception), sentence("workspaces/alpha/memory"))
        self.assertEqual(idx.read_bytes(), before)
        self.assertTrue(dup.exists())

    def test_workspace_optimize_names_it_and_goes_on_to_the_next(self):
        memstore.write(self.beta, "the keycloak token in beta rotates yearly", title="again",
                       timestamped=True)
        with refusing_to_list(self.alpha):
            _, out, err = run(commands_workspace.cmd_workspace_optimize, name=None, all=True,
                              apply=False, stale_days=90)
        self.assertIn(sentence("workspaces/alpha/memory"), err)
        self.assertIn("◆ beta", out)

    def test_persona_optimize_names_it_and_goes_on_to_the_next(self):
        self.make_persona("dev", role="Dev")
        persona.remember("dev", "own keycloak deploy fact")
        persona.remember("dev", "shared keycloak convention", shared=True)
        with refusing_to_list(persona.memory_dir("dev")):
            _, out, err = run(commands_persona.cmd_persona_optimize, name=None, all=True,
                              apply=False, stale_days=90)
        self.assertIn(sentence("personas/dev/memory"), err)
        self.assertIn("◆ _shared", out)


class TheBriefingDigest(PersonaIso):
    def setUp(self) -> None:
        super().setUp()
        make_plane(self)
        self.make_persona("dev", role="Dev")
        persona.ensure_shared()

    def test_it_names_the_store_it_could_not_count_rather_than_counting_none(self):
        persona.remember("dev", "own keycloak deploy fact")
        persona.remember("dev", "shared keycloak convention", shared=True)
        with refusing_to_list(persona.memory_dir("dev")):
            digest = hooks._memory_digest("dev")
        self.assertIn("**own (?)** — not read:\n   ⚠ " + sentence("personas/dev/memory"), digest)
        self.assertIn("## Memory — ? own · 1 shared", digest)
        self.assertIn("shared keycloak convention", digest)

    def test_either_store_alone_unread_is_named_not_an_empty_digest(self):
        """With nothing readable beside it, the digest said nothing at all — the briefing of a
        persona that has recorded nothing."""
        for shared, rel, head in ((False, "personas/dev/memory", "## Memory — ? own · 0 shared"),
                                  (True, "personas/_shared/memory",
                                   "## Memory — 0 own · ? shared")):
            with self.subTest(shared=shared):
                with refusing_to_list(persona.memory_dir("dev", shared=shared)):
                    digest = hooks._memory_digest("dev")
                self.assertIn(sentence(rel), digest)
                self.assertIn(head, digest)
                self.assertNotIn("(0)**", digest)


class TheReadmeRoster(PersonaIso):
    def test_it_is_not_rewritten_with_a_count_it_could_not_take_and_says_why(self):
        """`charter docs` refreshes README's persona roster, whose memory column is a count of
        each persona's memory directory. One it could not list read as 0 and was committed so."""
        from charter import render
        make_plane(self)
        self.make_persona("dev", role="Dev")
        memstore.write(persona.memory_dir("dev"), "own keycloak deploy fact", title="own fact")
        readme = config.ROOT / "README.md"
        readme.write_text(f"# plane\n\n{render.PERSONAS_BEGIN}\nold roster\n{render.PERSONAS_END}\n")
        before = readme.read_text()
        err = io.StringIO()
        with refusing_to_list(persona.memory_dir("dev")), redirect_stderr(err):
            changed = commands.refresh_readme_personas()
        self.assertFalse(changed)
        self.assertEqual(readme.read_text(), before)
        self.assertIn(sentence("personas/dev/memory"), err.getvalue())


class ACommandWithNoPartialAnswerRefusesCleanly(PersonaIso):
    @unittest.skipIf(AS_ROOT, "root lists a directory whatever its mode")
    def test_it_prints_the_sentence_and_exits_1_rather_than_crashing_or_answering_none(self):
        make_plane(self)
        self.make_persona("dev", role="Dev")
        persona.remember("dev", "own keycloak deploy fact")
        locked(self, persona.memory_dir("dev"))
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            rc = cli.main(["persona", "dedupe", "dev"])
        self.assertEqual(rc, 1)
        self.assertIn(sentence("personas/dev/memory"), err.getvalue())
        self.assertNotIn("no near-duplicate", err.getvalue())
        self.assertNotIn("charter bug", err.getvalue())


class TwoChangeStores(PersonaIso):
    def setUp(self) -> None:
        super().setUp()
        make_plane(self)
        for ws in ("alpha", "beta"):
            workspace.ensure(ws)
            change.write(ws, f"{ws}-api", change.new_record(f"{ws}-api", "API 1 -> 2", "me",
                                                             "2026-09-14T00:00:00+00:00"))
        self.alpha = change.changes_dir("alpha")


class TheChangeStoreNamesWhatItCouldNotList(TwoChangeStores):
    @unittest.skipIf(AS_ROOT, "root lists a directory whatever its mode")
    def test_a_real_changes_directory_at_mode_000_is_unread_not_empty(self):
        locked(self, self.alpha)
        self.assertEqual(change.read_all("alpha"), ([], [], [(self.alpha, errno.EACCES)]))

    def test_an_injected_refusal_is_unread_on_either_interpreter(self):
        with refusing_to_list(self.alpha):
            self.assertEqual(change.read_all("alpha"), ([], [], [(self.alpha, errno.EACCES)]))
            with self.assertRaises(workspace.CannotCheck) as cm:
                change.all_for("alpha")
        self.assertEqual(str(cm.exception), sentence("workspaces/alpha/changes"))

    def test_a_readable_or_absent_store_names_nothing(self):
        records, refused, unread = change.read_all("beta")
        self.assertEqual(([r["change"] for r in records], refused, unread), (["beta-api"], [], []))
        workspace.ensure("gamma")
        self.assertEqual(change.read_all("gamma"), ([], [], []))

    @unittest.skipIf(AS_ROOT, "root lists a directory whatever its mode")
    def test_change_list_names_it_and_does_not_say_there_are_no_changes(self):
        locked(self, self.alpha)
        rc, _, err = run(commands_change.cmd_change_list, workspace="alpha")
        self.assertEqual(rc, 1)
        self.assertIn(sentence("workspaces/alpha/changes"), err)
        self.assertNotIn("No changes in workspace", err)

    def test_doctor_names_it_beside_the_changes_it_read(self):
        with refusing_to_list(self.alpha):
            r = doctor.check_changes()
        self.assertEqual(r.status, doctor.WARN, r)
        self.assertTrue(r.detail.startswith("1 change(s), none divergent"), r.detail)
        self.assertTrue(r.detail.endswith("; workspaces/alpha/changes cannot be checked"),
                        r.detail)
        self.assertEqual(r.hint, sentence("workspaces/alpha/changes"))


if __name__ == "__main__":
    unittest.main()
