"""The frame-rung decision is written down with its consequence, not only its ruling.

charter-app's `charter` ports every rung of the workspace ladder except the tmux frame's
launch record, because `docs/plane-format.md` rules `.charter/frame/**` is the frame's and
that binary neither reads nor writes there (charter-app#74, settled 2026-09-20).

A ruling on its own is half a record. The half that gets lost is what an operator actually
sees while the divergence stands, so that is what this pins: the ADR has to name the one
state the two implementations can differ in, what a command does wrong in it, and the one
command that closes it. Each needle below is a fact somebody would have to delete on
purpose — not a turn of phrase, and never a line break, which is why every check runs
against the text with its whitespace collapsed.

The ADR is pinned **by slug**, not by number, so it can merge alongside another ADR that
claimed a number first (`tests/test_the_profile_words_are_written_down.py` does the same,
for the same reason). The cross-reference from `docs/plane-format.md` is pinned to the
number the file on disk actually carries, so a renumbering that leaves the pointer behind
is what goes red — an ADR nobody reading the format is pointed at is one nobody finds.

These read files off the tree, never through `config`: a test that resolved the plane would
be answering about whatever plane it ran in.
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr"
SPEC = ROOT / "docs" / "plane-format.md"
SLUG = "*-the-rust-charter-does-not-read-the-frames-launch-record.md"


def _flat(text: str) -> str:
    """The text with every run of whitespace collapsed to one space.

    A needle that spans a line break is a needle that breaks when somebody rewraps the
    paragraph, and a rewrap changes nothing about what the document says.
    """
    return " ".join(text.split())


def _the_adr() -> Path:
    found = sorted(ADR.glob(SLUG))
    assert len(found) == 1, found
    return found[0]


class TestTheDecisionIsRecorded(unittest.TestCase):
    def setUp(self) -> None:
        self.text = _the_adr().read_text()
        self.flat = _flat(self.text)

    def test_it_is_an_adr(self):
        self.assertTrue(self.text.startswith("# "))

    def test_it_states_the_ruling_it_follows_from(self):
        """The decision is downstream of the format's rule, and says so — otherwise it reads
        as a porting omission somebody could tidy up."""
        self.assertIn(".charter/frame", self.flat)
        self.assertIn("neither reads nor writes there", self.flat)

    def test_it_names_the_one_state_the_two_can_differ_in(self):
        """A bare "they may differ" is not a record. The window is one launch wide and
        bounded; a reader who cannot reconstruct it cannot judge the decision."""
        for fact in (
            "the session pointer is absent and a frame record is present",
            "`.charter/sessions/<sid>.workspace`",
            "one launch wide",
        ):
            self.assertIn(fact, self.flat, fact)

    def test_it_says_what_an_operator_sees_and_how_to_close_it(self):
        """The half a decision record is usually missing: the wrong answer an operator is
        given, where their writes land instead, and the command that ends it."""
        for cost in (
            "charter workspace current",
            "workspaces/default/",
            "charter recall",
            "charter workspace use",
        ):
            self.assertIn(cost, self.flat, cost)

    def test_it_keeps_the_alternative_it_did_not_take(self):
        """One flip of an existing scenario if practice disagrees with the ruling — worth
        nothing unless the option is still written down."""
        self.assertIn("The alternative not taken", self.flat)


class TestTheFormatPointsAtTheDecision(unittest.TestCase):
    def test_the_resolution_order_names_the_rung_the_rust_charter_lacks(self):
        flat = _flat(SPEC.read_text())
        after = flat[flat.index("Resolution order (`workspace.chosen`"):]
        self.assertIn("the frame's launch record", after)
        # The number the file on disk carries, so a renumbering cannot leave this behind.
        self.assertIn(f"ADR {_the_adr().name.split('-')[0]}", after)
