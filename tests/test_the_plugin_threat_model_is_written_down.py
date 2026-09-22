"""The plugin threat model is written down, gate included, before any runtime exists.

The operator decided on 2026-09-22 that charter-app becomes a pluggable platform running
third-party code, and agreed that the threat model gates the runtime. The record is therefore the
interface between that decision and whoever implements it, and this is the tripwire on the parts
a well-meaning edit would smooth away.

**Pinned by slug, not by number**, the way `test_the_ui_shell_words_are_written_down.py` and
`test_the_multi_plane_words_are_written_down.py` are: several agents allocate from this sequence
at once and nothing reserves a number. What IS pinned by number is that every `ADR 00NN` the
record cites names a file that exists, because a renumber that leaves a stale citation sends a
reader to somebody else's decision.

What else is pinned is the shape of the document that makes it a gate rather than a description:
a numbered list of conditions, a recommendation on each of the three decisions, the honesty
paragraph that says a subprocess does not confine anything, and the corrections it makes to the
records it rests on. A draft that drops any of those reads cleaner and is worth less — the whole
value of the record is the part that says what it does NOT buy.

These read files off the tree, never through `config`: a test that resolved the plane would be
answering about whatever plane it ran in.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr"

#: The record, by the slug it was written under.
PLUGINS = "a-plugin-is-a-subprocess-or-charter-has-no-plugins"


def _adr(slug: str) -> Path:
    found = sorted(ADR.glob(f"*-{slug}.md"))
    if len(found) != 1:
        raise AssertionError(f"expected one ADR for {slug!r}, found {[p.name for p in found]}")
    return found[0]


def _text() -> str:
    return _adr(PLUGINS).read_text()


def _said() -> str:
    """The record with its line wrapping and its emphasis taken out.

    A sentence this file pins is a sentence the record makes, not a sentence it happens to fit on
    one line. Reflowing a paragraph or bolding a clause must not redden a test, or the tripwire
    starts firing on edits that change nothing and gets deleted for being noise.
    """
    return re.sub(r"\s+", " ", _text().replace("*", ""))


class TestTheRecordExists(unittest.TestCase):
    def test_it_exists_once_and_opens_with_its_claim(self):
        self.assertTrue(_text().startswith("# "),
                        "the plugin ADR does not open with its claim as a title")

    def test_every_adr_number_it_cites_names_a_record_that_exists(self):
        """The tripwire for a renumber and for a citation written from memory. A record pointing
        at the number another decision now has is worse than one pointing nowhere, because it
        resolves."""
        numbers = {p.name[:4] for p in ADR.glob("[0-9][0-9][0-9][0-9]-*.md")}
        for cited in re.findall(r"ADR (\d{4})", _text()):
            self.assertIn(cited, numbers,
                          f"the plugin ADR cites ADR {cited}, which is not a record")

    def test_every_adr_link_in_it_resolves(self):
        for link in re.findall(r"\]\((\d{4}-[a-z0-9-]+\.md)\)", _text()):
            self.assertTrue((ADR / link).is_file(),
                            f"the plugin ADR links {link}, which is not there")


class TestItIsAGateAndNotADescription(unittest.TestCase):
    """A threat model written after the thing it gates is a description. What makes this one a
    gate is that its conditions are numbered, falsifiable and checkable by somebody who was not
    in the room."""

    def test_it_states_that_the_threat_model_gates_the_runtime(self):
        text = _said()
        self.assertIn("the threat model gates the runtime", text)
        self.assertIn("Nothing in this record is implemented", text,
                      "the record does not say it is written before the thing it gates")

    def test_the_gate_is_a_numbered_list_of_conditions(self):
        """Eight conditions were settled. A gate that loses its numbering becomes advice."""
        text = _text()
        self.assertIn("## The gate", text, "the record has no gate section")
        gate = text.split("## The gate", 1)[1].split("\n## ", 1)[0]
        numbered = re.findall(r"^\d+\. ", gate, flags=re.MULTILINE)
        self.assertGreaterEqual(len(numbered), 8,
                                f"the gate lists {len(numbered)} numbered conditions, not eight")

    def test_the_gate_holds_the_four_conditions_that_are_not_about_plugins(self):
        """Each of these is work that exists whether or not a plugin is ever built, which is what
        makes the gate checkable rather than a matter of opinion."""
        gate = _said().split("## The gate", 1)[1].split(" ## ", 1)[0]
        for condition in ("ADR 0031 is signed off", "#112", "#123", "is_a_tool_hook"):
            self.assertIn(condition, gate, f"the gate does not require {condition!r}")


class TestItRecommendsRatherThanOffersAMenu(unittest.TestCase):
    def test_it_names_one_isolation_model_in_its_own_title(self):
        title = _text().splitlines()[0]
        self.assertIn("subprocess", title,
                      "the record's title does not carry the isolation model it recommends")

    def test_it_rules_out_each_of_the_four_other_options_by_name(self):
        """A menu with a preference is still a menu. Each option gets a verdict."""
        text = _said()
        for option in ("main webview", "Web Worker", "second Tauri webview", "WASM"):
            self.assertIn(option, text, f"the record does not consider {option!r}")
        self.assertIn("ruled out", text.lower())

    def test_it_names_a_minimum_capability_set_of_two(self):
        text = _said()
        self.assertIn("minimum viable capability set is two things", text,
                      "the record does not commit to a minimum capability set")

    def test_it_says_what_to_build_first_that_needs_no_runtime(self):
        text = _said()
        self.assertIn("none of it needs the runtime", text)
        self.assertIn("extension registry with no executor", text,
                      "the record does not name the registry as buildable without a runtime")


class TestTheCorrectionsSurvive(unittest.TestCase):
    """The record contradicts things believed when the decision was taken. A tidier draft drops
    the contradictions and the next reader re-derives the wrong thing."""

    def test_it_says_adr_0031_is_still_a_draft(self):
        """0031 says of itself that it needs the operator's sign-off before anything is built on
        it. A record that leant on it as settled would be citing a proposal as a precedent."""
        text = _said()
        self.assertIn("DRAFT", text,
                      "the record treats ADR 0031 as settled when 0031 says it is not")
        self.assertIn("sign-off", text)

    def test_it_says_the_approval_path_it_copies_has_two_open_defects(self):
        """ADR 0035's first-open prompt is the precedent, and #112 and #123 are live against the
        code that implements it. Copying the pattern without them copies the holes."""
        text = _said()
        self.assertIn("#112", text)
        self.assertIn("#123", text)
        self.assertIn("inherits both", text,
                      "the record does not say a plugin trust record would inherit those defects")

    def test_it_says_charters_own_word_plugin_is_already_taken(self):
        """`layer::WORKSPACE_KEYS` is `["enabledPlugins", "env"]` — Claude Code's plugins, shown in
        the same dialog a charter extension would appear in."""
        text = _said()
        self.assertIn("enabledPlugins", text)
        self.assertIn("already spoken for", text,
                      "the record does not name the collision between the two uses of 'plugin'")

    def test_it_records_adr_0022s_amendment_rather_than_the_simple_reading(self):
        """0022's 2026-09-15 amendment made a launch install a plugin into a config folder. A
        record that read 0022 as 'charter never installs anything' would rest on a sentence that
        was reversed."""
        text = _said()
        self.assertIn("2026-09-15 amendment", text)
        self.assertIn("charter@charter", text,
                      "the record does not name what a launch already installs")


class TestItStatesWhatTheBoundaryDoesNotBuy(unittest.TestCase):
    """The failure this whole sequence is written against is a partial guard presented as a
    complete one. These are the sentences a confident draft deletes."""

    def test_it_says_a_subprocess_does_not_confine_a_plugin_below_the_operator(self):
        text = _said()
        self.assertIn("does not confine a plugin below the operator", text)
        self.assertIn("trusted code that charter is polite to", text,
                      "the record does not state what the install-time decision is carrying")

    def test_it_names_the_sandboxes_it_is_not_building(self):
        text = _said()
        for sandbox in ("Seatbelt", "Landlock", "AppContainer"):
            self.assertIn(sandbox, text, f"the record does not name {sandbox}")

    def test_it_says_a_plugin_is_a_second_door_beside_the_tool_guard(self):
        """The irony is the reason for the gate: charter's own PreToolUse guard exists to stop
        charter's agents, and a plugin never calls a tool, so no stage of that guard can see it."""
        text = _said()
        self.assertIn("second door", text)
        self.assertIn("stage 3 of", text,
                      "the record does not say how much of the tool guard is actually in the tree")

    def test_it_reopens_adr_0028_rather_than_assuming_the_race_stays_out_of_scope(self):
        """0028 says the accepted race is out of scope only because nothing confines an agent
        below charter, and that the day something does, it is the first decision to re-open."""
        text = _said()
        self.assertIn("re-opened", text)
        self.assertIn("confined principal", text,
                      "the record does not connect a plugin to ADR 0028's re-opening clause")

    def test_the_network_is_declared_and_not_granted(self):
        """charter cannot enforce a network rule on a subprocess, and a table that listed it as
        grantable would be selling an enforcement that does not exist."""
        text = _said()
        self.assertIn("Declared, not granted", text)

    def test_the_round_trip_cost_is_open_rather_than_estimated(self):
        """ADR 0026 measures before it locks. An unmeasured number presented as an estimate is how
        a limit gets set from a guess."""
        text = _said()
        self.assertIn("unmeasured", text)
        self.assertIn("1.8 ms", text,
                      "the record does not name the nearest measured number or say it differs")


class TestTheLineBetweenDataAndCode(unittest.TestCase):
    """Themes are the first extension point and the cheap safe start. What makes them safe has to
    be stated as properties, or the next declarative format is judged by resemblance."""

    def test_it_states_what_makes_a_declarative_extension_safe(self):
        text = _said()
        self.assertIn("parses and re-emits, never interpolates", text)
        self.assertIn("closed and charter decides it", text,
                      "the record does not say who owns the vocabulary")

    def test_it_names_the_crossings_that_turn_data_into_code(self):
        text = _said()
        for crossing in ("url(", "media query", "@import"):
            self.assertIn(crossing, text, f"the record names no crossing for {crossing!r}")

    def test_it_separates_code_execution_from_deception(self):
        """A theme cannot run code and can still repaint a consent prompt. Two properties, and a
        record that ran them together would call the vocabulary safe on the wrong grounds."""
        text = _said()
        self.assertIn("consent surfaces and the state colours are charter's", text)
        self.assertIn("different properties", text,
                      "the record collapses code execution and deception into one claim")

    def test_a_theme_is_not_called_a_plugin(self):
        text = _said()
        self.assertIn("Calling a theme a plugin", text,
                      "the record does not reject bundling themes behind the runtime's gate")


class TestTheCapabilitySurfaceIsEnumerated(unittest.TestCase):
    def test_the_execution_inputs_are_ungrantable_at_any_level(self):
        """The machine store and the reopen record are execution inputs — #129 was a test suite
        writing 49 chats into the operator's live plane, and #132 fenced both paths for it."""
        text = _said()
        self.assertIn("No, at any level", text)
        for path in ("machine.rs", "reopen.json", "#129", "#132"):
            self.assertIn(path, text, f"the capability table says nothing about {path!r}")

    def test_vaults_are_absent_rather_than_denied(self):
        """A denial is a name, and a name is something a later grant attaches to."""
        text = _said()
        self.assertIn("Absent", text)
        self.assertIn("no capability name for it", text)

    def test_the_command_surface_is_counted_rather_than_gestured_at(self):
        text = _said()
        self.assertIn("collect_commands", text)
        self.assertIn("forty", text,
                      "the record does not say how large the command surface actually is")


if __name__ == "__main__":
    unittest.main()
