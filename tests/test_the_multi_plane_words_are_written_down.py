"""The multi-plane decisions are written down where a reader without the grill can find them.

The operator settled seven decisions on 2026-09-20 after opening charter-app from its icon and
finding an app that could not be given a plane. Two agents are implementing against them in
parallel, so the records are the interface, and this is the tripwire for the three places that
carry them: `CONTEXT.md` for the words, `docs/adr/` for the decisions, and
`docs/superpowers/specs/2026-09-17-charter-app.md` for what the milestones now include.

**The ADRs are pinned by slug, not by number**, the way
`test_the_profile_words_are_written_down.py` pins 0022 — three numbers were claimed in one
push while other branches were claiming their own, and whichever merges first decides. What is
pinned by number is the *agreement* between a file's own name and the way the spec cites it, so
a renumber that leaves a stale `ADR 00xx` in the spec goes red here instead of sending a reader
to the wrong record.

These read files off the tree, never through `config`: a test that resolved the plane would be
answering about whatever plane it ran in.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr"
SPEC = ROOT / "docs" / "superpowers" / "specs" / "2026-09-17-charter-app.md"

#: The three records, by the slug each was written under.
SLUGS = (
    "a-plane-is-a-project-and-a-window-may-hold-several",
    "charter-keeps-a-little-state-outside-every-plane",
    "a-plane-is-untrusted-until-the-operator-opens-it",
)


def _adr(slug: str) -> Path:
    found = sorted(ADR.glob(f"*-{slug}.md"))
    if len(found) != 1:
        raise AssertionError(f"expected one ADR for {slug!r}, found {[p.name for p in found]}")
    return found[0]


def _entry(text: str, term: str) -> str:
    """The body of one `**Term**:` entry in `CONTEXT.md`, up to the next bold term.

    Sliced rather than line-counted because an entry's definition runs to as many lines as it
    needs, and `_Avoid_` is the last of them.
    """
    start = text.index(f"**{term}**:")
    rest = text[start + len(term) + 5:]
    end = rest.find("\n**")
    return rest if end < 0 else rest[:end]


class TestTheWordsAreDefined(unittest.TestCase):
    def test_context_defines_the_three_terms(self):
        """A word that now means something it did not mean last week has to be in the glossary
        that says so, or the next writer reaches for the old sense."""
        text = (ROOT / "CONTEXT.md").read_text()
        for term in ("Project", "Opener", "Trusted plane"):
            self.assertIn(f"**{term}**:", text, f"CONTEXT.md defines no {term!r}")
            self.assertRegex(_entry(text, term), r"(?m)^_Avoid_:",
                             f"{term!r} names nothing it is not")

    def test_project_and_workspace_refuse_each_other(self):
        """`Workspace` has carried `_Avoid_: project` since the glossary was written. Now that
        a project IS a plane, the refusal has to run both ways or the two entries drift into
        meaning the same thing."""
        text = (ROOT / "CONTEXT.md").read_text()
        project = _entry(text, "Project").lower()
        self.assertIn("workspace", project[project.index("_avoid_:"):],
                      "'project' still permits 'workspace'")
        workspace = _entry(text, "Workspace").lower()
        self.assertIn("project", workspace[workspace.index("_avoid_:"):],
                      "'workspace' no longer refuses 'project'")

    def test_a_trusted_plane_is_not_described_as_safe(self):
        """The one framing that would actively mislead: an approved plane is in force in full,
        and the record says so at full volume. A glossary that called it 'safe' would undo
        that in one word."""
        body = _entry((ROOT / "CONTEXT.md").read_text(), "Trusted plane").lower()
        self.assertIn("not a boundary", body,
                      "'trusted plane' does not say what trust is not")
        self.assertIn("safe", body[body.index("_avoid_:"):],
                      "'trusted plane' still permits 'safe'")


class TestTheDecisionsAreRecorded(unittest.TestCase):
    def test_each_adr_exists_once_and_opens_with_its_claim(self):
        for slug in SLUGS:
            path = _adr(slug)
            self.assertTrue(path.read_text().startswith("# "),
                            f"{path.name} does not open with its claim as a title")

    def test_the_window_adr_states_what_one_plane_per_process_costs(self):
        """The half a decision record is usually missing. One plane per process is the state
        model — `app.manage` singletons and every command that takes one as `State` — not a UI
        assumption, and a reader who costs this as a tab bar has read the wrong record."""
        text = _adr(SLUGS[0]).read_text()
        for claim in ("app.manage", "single-instance", "--no-restore", "reopen.json"):
            self.assertIn(claim, text, f"the window ADR says nothing about {claim!r}")

    def test_the_machine_state_adr_names_the_precedent_and_the_limit(self):
        """It bends charter's founding rule, so it has to argue rather than announce: the
        rejected `~/.config/charter` of ADR 0022, the reporting consent that has been outside
        every plane since ADR 0003, and the `0600` that is not an ACL on Windows."""
        text = _adr(SLUGS[1]).read_text()
        for claim in ("reporting-consent", "$CHARTER_HOME", "0600", "M2.16",
                      "never plane content"):
            self.assertIn(claim, text, f"the machine-state ADR says nothing about {claim!r}")

    def test_the_trust_adr_quotes_what_it_measured(self):
        """Quoted from `layer.rs` rather than paraphrased, with both existing limits named:
        `allow` never travels, and a committed file cannot declare a harness profile."""
        text = _adr(SLUGS[2]).read_text()
        for claim in ('WORKSPACE_KEYS: [&str; 2] = ["enabledPlugins", "env"]',
                      'RESTRICTIVE: [&str; 2] = ["ask", "deny"]',
                      "charter.local.toml",
                      ".charter/app/reopen.json",
                      "--clone-this-repo"):
            self.assertIn(claim, text, f"the trust ADR no longer measures {claim!r}")

    def test_the_trust_adr_says_what_it_is_not(self):
        """`profiletrust` says it about its own record and this one inherits the sentence. A
        trust gate read as a sandbox is the one way this decision does harm."""
        text = _adr(SLUGS[2]).read_text()
        self.assertIn("Not a boundary", text)
        self.assertIn("no model and makes no judgements about the content of work", text,
                      "the trust ADR does not bound what its dialog can show")

    def test_every_adr_link_in_them_resolves(self):
        """They cite each other by filename, which is what a renumber breaks."""
        for slug in SLUGS:
            path = _adr(slug)
            for link in re.findall(r"\]\((\d{4}-[a-z0-9-]+\.md)\)", path.read_text()):
                self.assertTrue((ADR / link).is_file(),
                                f"{path.name} links {link}, which is not there")


class TestTheSpecCarriesThem(unittest.TestCase):
    def test_the_spec_admits_what_it_missed(self):
        """Recorded as missed rather than presented as always-intended. The next reader
        otherwise concludes the opener was descoped, or that ADR 0025 decided against it."""
        text = SPEC.read_text()
        self.assertIn("What this spec missed", text)
        self.assertIn("current_dir", text,
                      "the spec does not say how the app resolved its plane")

    def test_the_spec_numbers_them_after_21(self):
        """Continuing the sequence, not renumbering it: a decision's number is how it is
        cited."""
        text = SPEC.read_text()
        for n in range(22, 29):
            self.assertRegex(text, rf"(?m)^{n}\. \*\*",
                             f"the spec has no decision {n}")

    def test_the_spec_cites_each_adr_by_the_number_it_actually_has(self):
        """The tripwire for a renumber. Three numbers were claimed at once; a spec still
        pointing at the number a record had before it merged sends a reader to somebody
        else's decision."""
        text = SPEC.read_text()
        for slug in SLUGS:
            number = _adr(slug).name[:4]
            self.assertIn(f"ADR {number}", text,
                          f"the spec cites no ADR {number} for {slug!r}")

    def test_the_milestones_place_the_work(self):
        """A decision with no milestone is a decision nobody is building."""
        text = SPEC.read_text()
        self.assertIn("Where the multi-plane work goes", text)
        placement = text[text.index("Where the multi-plane work goes"):]
        for claim in ("M2", "M3", "M1 is not reopened"):
            self.assertIn(claim, placement, f"the placement says nothing about {claim!r}")

    def test_the_init_divergence_is_declared_rather_than_normalised(self):
        """Decision 27 changes a command that is already ported, against a frozen oracle.
        Written down in both places, because a differential scenario that is quietly relaxed
        is how a divergence stops being visible."""
        for text in (SPEC.read_text(), _adr(SLUGS[2]).read_text()):
            self.assertIn("differential", text)
            self.assertIn("frozen", text)


if __name__ == "__main__":
    unittest.main()
