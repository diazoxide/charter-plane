"""The UI shell decisions are written down where a reader without the grill can find them.

The operator settled three decisions about charter-app's window on 2026-09-21 after opening the
app and hitting a start-chat dialog he could not read: what the app takes from a component
library, what each of the four regions holds, and how the chat strip behaves over time. Two
agents are implementing against them in parallel, so the records are the interface and this is
the tripwire.

**Pinned by slug, not by number**, the way `test_the_multi_plane_words_are_written_down.py` and
`test_the_profile_words_are_written_down.py` are: three numbers were claimed in one push while
other branches were claiming their own, and whichever merges first decides. What IS pinned by
number is that every `ADR 00NN` these records cite names a file that exists — a renumber that
leaves a stale citation behind sends a reader to somebody else's decision, and that is the one
failure a slug cannot catch.

The rest of what is pinned here is the part of each record that a well-meaning edit would
smooth away: the corrections. Each of these three ADRs contradicts something that was believed
when the decision was taken, and a summary that drops the contradiction reads as a cleaner
record and is a worse one.

These read files off the tree, never through `config`: a test that resolved the plane would be
answering about whatever plane it ran in.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr"

#: The three records, by the slug each was written under.
BEHAVIOUR = "charter-takes-the-behaviour-and-keeps-the-look"
REGIONS = "the-window-is-four-regions-and-what-has-no-region-is-named"
TABS = "tabs-keep-their-order-and-the-overflow-sorts-by-activity"
SLUGS = (BEHAVIOUR, REGIONS, TABS)


def _adr(slug: str) -> Path:
    found = sorted(ADR.glob(f"*-{slug}.md"))
    if len(found) != 1:
        raise AssertionError(f"expected one ADR for {slug!r}, found {[p.name for p in found]}")
    return found[0]


class TestTheDecisionsAreRecorded(unittest.TestCase):
    def test_each_adr_exists_once_and_opens_with_its_claim(self):
        for slug in SLUGS:
            path = _adr(slug)
            self.assertTrue(path.read_text().startswith("# "),
                            f"{path.name} does not open with its claim as a title")

    def test_every_adr_number_they_cite_names_a_record_that_exists(self):
        """The tripwire for a renumber, and for a citation written from memory. Three numbers
        were claimed at once; a record pointing at the number another decision now has is worse
        than one pointing nowhere, because it resolves."""
        numbers = {p.name[:4] for p in ADR.glob("[0-9][0-9][0-9][0-9]-*.md")}
        for slug in SLUGS:
            path = _adr(slug)
            for cited in re.findall(r"ADR (\d{4})", path.read_text()):
                self.assertIn(cited, numbers,
                              f"{path.name} cites ADR {cited}, which is not a record")

    def test_every_adr_link_in_them_resolves(self):
        """They cite each other by filename too, which is what a renumber breaks."""
        for slug in SLUGS:
            path = _adr(slug)
            for link in re.findall(r"\]\((\d{4}-[a-z0-9-]+\.md)\)", path.read_text()):
                self.assertTrue((ADR / link).is_file(),
                                f"{path.name} links {link}, which is not there")


class TestTheCorrectionsSurvive(unittest.TestCase):
    """Each record contradicts a belief held when its decision was taken. A tidier draft drops
    the contradiction, and the next reader re-derives the wrong thing."""

    def test_the_behaviour_adr_refuses_credit_for_the_bug_that_prompted_it(self):
        """The reported defect was unstyled spans inside a native `<label>`, not a missing
        label/control association. A component library would not have prevented it, and an ADR
        that claimed otherwise would be sold on a fix it does not deliver."""
        text = _adr(BEHAVIOUR).read_text()
        self.assertIn("claudeclaudeclaudebuilt-indefault", text,
                      "the record does not quote what the operator actually saw")
        self.assertIn("would not have prevented this bug", text,
                      "the record still takes credit for the start-chat picker")
        self.assertIn("App.css", text,
                      "the record does not name the missing stylesheet as the cause")

    def test_the_behaviour_adr_rests_on_what_was_read_off_the_tree(self):
        """The evidence is the window, not the dialog: four modals that do not trap focus and
        three tablists with none of the tabs pattern. Named so the claim can be re-checked."""
        text = _adr(BEHAVIOUR).read_text()
        for claim in ('aria-modal="true"', "roving", "Palette", "headless"):
            self.assertIn(claim, text, f"the behaviour ADR says nothing about {claim!r}")

    def test_the_behaviour_adr_does_not_argue_the_choice_on_speed(self):
        """ADR 0026's own sentence, because it applies identically. Cold start is missed on
        Linux for a D-Bus timeout no bundle moves, and saying so is what keeps the argument
        standing when a reviewer checks it."""
        text = _adr(BEHAVIOUR).read_text()
        self.assertIn("priority 3 does not decide it", text)
        self.assertIn("D-Bus", text,
                      "the cold-start argument does not say what the 25 s actually is")

    def test_the_behaviour_adrs_amendment_keeps_both_sides_of_the_boundary(self):
        """The operator amended this record on 2026-09-22 to allow shadcn/ui components copied
        into charter-app. An amendment that records only the permission is the dangerous half:
        the rule it loosens — no component library as a dependency, no house abstraction over
        Radix — is still in force, and the words that forbade a *wrapper* were charter-app's
        `docs/ui-primitives.md` rather than this file, which the amendment has to say or the next
        reader goes looking here for a quote that is not here."""
        text = _adr(BEHAVIOUR).read_text()
        self.assertIn("## Amendment, 2026-09-22", text,
                      "the behaviour ADR carries no amendment for the copied-in-components ruling")
        # Reflowing a paragraph or bolding a clause must not redden this, the way
        # `test_the_plugin_threat_model_is_written_down.py` handles the same problem.
        amendment = re.sub(r"\s+", " ",
                           text.split("## Amendment, 2026-09-22", 1)[1].replace("*", ""))
        self.assertIn("The words are charter-app's, in `docs/ui-primitives.md`", amendment,
                      "the amendment does not say where the rule it changes is actually written")
        self.assertIn('This record never says "wrapper"', amendment,
                      "the amendment lets a reader hunt this file for a quote that is not in it")
        self.assertIn("shadcn", amendment)
        self.assertIn("A component library as a dependency.", amendment,
                      "the amendment does not say a component library is still refused")
        self.assertIn("A house abstraction layer, whether written or copied.", amendment,
                      "the amendment does not say a house layer over Radix is still refused")
        self.assertIn("this record is authoritative", amendment,
                      "the amendment does not say which file wins when the two disagree")

    def test_the_behaviour_adrs_amendment_says_no_build_catches_a_missed_rename(self):
        """The amendment's own cost, and the one a confident draft deletes because it makes the
        permission sound worse. A pasted `bg-background` is not a class in this app — the palette
        is deleted — so it emits nothing and the element renders undressed, which is the
        `claudeclaudeclaudebuilt-indefault` defect at the top of this very record. Saying "and the
        build catches it" would be false and would be believed."""
        text = _adr(BEHAVIOUR).read_text()
        amendment = re.sub(r"\s+", " ",
                           text.split("## Amendment, 2026-09-22", 1)[1].replace("*", ""))
        self.assertIn("the build does not catch it", amendment,
                      "the amendment claims or implies a mechanical guard on a pasted class")
        self.assertIn("claudeclaudeclaudebuilt-indefault", amendment,
                      "the amendment does not say a missed rename is this record's own defect")

    def test_the_regions_adr_marks_its_own_reading_as_a_reading(self):
        """'Left is navigation, bottom is state' is the record's inference and not the
        operator's words. An inference that hardens into a decision nobody made is how ADR 0029
        and ADR 0036 came to be written after the fact."""
        text = _adr(REGIONS).read_text()
        self.assertIn("interpretation", text,
                      "the regions ADR presents its reading as the operator's")
        self.assertIn("the table stands and the", text,
                      "the regions ADR does not say what survives if the reading is wrong")

    def test_the_regions_adr_does_not_claim_the_regions_are_all_new(self):
        """There is a right-hand `<aside className="panels">` already, holding Repos, CI, Todos
        and Personas. The decision splits it — Repos and CI go down, the queue and alerts come
        in — and a record that read as 'four new regions' would send an implementer to build
        what is there."""
        text = _adr(REGIONS).read_text()
        self.assertIn("Repos, CI, Todos, Personas", text,
                      "the regions ADR does not say what the right-hand side holds today")
        self.assertIn("re-tenanted", text,
                      "the regions ADR presents a split of an existing region as a new one")

    def test_the_regions_adr_says_the_needs_you_queue_already_exists(self):
        """It is not the words in the bar. `NeedsYou.tsx` lists the chats by name and hedges
        for the harnesses that cannot report; what changes is where it is drawn."""
        text = _adr(REGIONS).read_text()
        self.assertIn("NeedsYou.tsx", text)
        self.assertIn("Nothing has said it needs you", text,
                      "the regions ADR flattens the queue's two different empty states")

    def test_the_regions_adr_gets_the_context_gauge_history_right(self):
        """ADR 0019's 'no gauge on any surface' bullet is marked closed by #413 for the tmux
        frame. The app has no such closure, and the two must not be run together."""
        text = _adr(REGIONS).read_text()
        self.assertIn("#413", text,
                      "the regions ADR repeats ADR 0019's bullet without its closure")
        self.assertIn("rows_at", text,
                      "the regions ADR does not say what was and was not ported")

    def test_the_regions_adr_names_the_gaps_as_gaps(self):
        text = _adr(REGIONS).read_text()
        for gap in ("ctx", "cache", "alerts", "doctor", "news"):
            self.assertIn(gap, text, f"the regions ADR names no gap for {gap!r}")
        self.assertIn("None of them is decided by this record", text,
                      "the gap list reads as a plan rather than as open questions")

    def test_the_tabs_adr_admits_it_reverses_the_workspace_axis_record(self):
        """ADR 0036 chose a scrollbar over an overflow menu in as many words. Reversing it
        quietly is how a decision gets taken twice with no record of the second."""
        text = _adr(TABS).read_text()
        self.assertIn("A scrollbar and not an overflow menu", text,
                      "the tabs ADR does not quote the decision it reverses")
        self.assertIn("reverses", text)

    def test_the_tabs_adr_says_last_activity_is_not_recorded_yet(self):
        """Sorting by a fact nothing writes down. `chatState.ts` carries state and a queue and
        no timestamp of any kind, so the field is new work in the core."""
        text = _adr(TABS).read_text()
        self.assertIn("does not exist as data today", text)
        self.assertIn("chatState.ts", text)

    def test_the_tabs_adr_keeps_the_add_button_out_of_the_overflow(self):
        """The measured constraint: `panes.e2e` could not press New tab partway through fifty.
        A show-more menu can eat the `+` exactly as the scroller did."""
        text = _adr(TABS).read_text()
        self.assertIn("panes.e2e", text)
        self.assertIn("charter-app#130", text,
                      "the tabs ADR does not cite where the constraint was measured")

    def test_the_tabs_adr_stores_each_pin_somewhere_it_argues_for(self):
        """Three levels is three storage decisions. A project pin is machine state whose own
        record says 'three things, and nothing else'; a workspace pin would travel in a clone;
        a chat is recorded nowhere on the plane."""
        text = _adr(TABS).read_text()
        for claim in ("machine.rs", "charter.toml", "reopen.json", "Three things, and nothing else"):
            self.assertIn(claim, text, f"the tabs ADR says nothing about {claim!r}")


if __name__ == "__main__":
    unittest.main()
