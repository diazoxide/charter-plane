"""Documentation is a shipping requirement, so a few claims are pinned by tests.

Not prose review — just the facts that would actively mislead a new consumer if they
drifted: the install command, the config keys, and the two framings that protect people
(the vault is not a password manager; memory defaults to local)."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text()
INSTALL = (ROOT / "docs" / "install.md").read_text()

#: Badge and image lines carry no prose. Counting them against the "first paragraph"
#: budget would fail the check for adding a CI badge, which is not what it is for.
# Badges, images, and a blockquote callout (the "charter is now a desktop app" notice at the top,
# a GitHub `> [!IMPORTANT]` alert) are decoration: what the README says charter IS starts after them.
_DECORATION = re.compile(r"^\s*(\[!\[.*|!\[.*|>.*)$", re.M)


class TestReadme(unittest.TestCase):
    def test_says_what_it_is_in_the_first_paragraph(self):
        head = _DECORATION.sub("", README)[:600].lower()
        self.assertIn("claude code", head)
        for word in ("persona", "workspace", "repo"):
            self.assertIn(word, head, word)

    def test_shows_a_real_install_command(self):
        self.assertRegex(README, r"(uv tool install|pipx install|pip install)\s+charter")

    def test_documents_both_artifacts(self):
        """Install is the CLI *and* the plugin — omitting the plugin leaves hooks dead."""
        self.assertIn("plugin", README.lower())

    def test_the_install_section_asks_for_one_command(self):
        """#881. The README used to print three commands and hope the reader ran all of
        them; a CLI-only install leaves every hook inert while looking complete.

        Asserted against the CODE BLOCK rather than the prose, because the prose still
        names `claude plugin update charter@charter` — correctly, since updating the
        plugin remains its own step — and a whole-document search would pass on a README
        that had gone back to typing the install by hand.
        """
        block = next(b for b in re.findall(r"```bash\n(.*?)```", README, re.S)
                     if "charter init" in b)
        self.assertIn("uv tool install charter-cp", block)
        for gone in ("claude plugin marketplace add", "claude plugin install"):
            self.assertNotIn(gone, block,
                             f"the 60-seconds block still types {gone!r} — `charter init` "
                             f"installs the plugin (#881)")

    def test_frames_the_vault_honestly(self):
        """It stores plaintext at 0600. Saying anything that implies encryption at rest
        would be the single most harmful inaccuracy in these docs."""
        low = README.lower() + (ROOT / "docs" / "secrets.md").read_text().lower()
        self.assertTrue("not a password manager" in low
                        or "not a secrets manager" in low)
        self.assertIn("transcript", low)

    def test_states_the_memory_default(self):
        low = README.lower() + (ROOT / "docs" / "control-plane.md").read_text().lower()
        self.assertIn("local", low)
        self.assertIn("share", low)

    def test_explains_the_one_credential_rule(self):
        """A user who does not know it reads a guard denial as a bug."""
        low = README.lower()
        self.assertIn("https", low)
        self.assertTrue("ssh" in low)

    def test_is_not_a_stub(self):
        self.assertGreater(len(README.splitlines()), 60)


class TestConfigDocs(unittest.TestCase):
    def test_every_charter_toml_key_is_documented(self):
        body = (ROOT / "docs" / "control-plane.md").read_text()
        for key in ("schema", "forge", "kind", "host", "group", "owner",
                    "exclude", "memory", "share", "workspace"):
            self.assertIn(key, body, key)

    def test_shows_a_multi_forge_example(self):
        body = (ROOT / "docs" / "control-plane.md").read_text()
        self.assertGreaterEqual(len(re.findall(r"\[\[forge\]\]", body)), 2,
                                "a mixed-forge example is the non-obvious case")


class TestPasteInInstall(unittest.TestCase):
    """The docs carry a prompt users paste into Claude Code to install charter.

    Prose that drifts merely reads oddly; a prompt that drifts *fails*, in someone else's
    session, on their first contact with the project. Every command in it is therefore
    checked against the thing it names — the distribution on PyPI — rather than trusted to
    stay true. The plugin id and the order its two `claude plugin` steps run in used to be
    checked here too; #881 moved both into code (`plugincache.install_argvs`) and
    `tests/test_plugin_install.py` holds them there, against the same two manifests.

    The prompt is looked for in the README *and* in `docs/install.md`, because which page
    hosts it is a layout decision and these checks are not: they must keep holding when it
    moves, or moving it silently retires them.
    """

    #: Fences are paired by ANCHORING both ends at the start of a line and letting the
    #: opener carry an optional language, which is what keeps the pairing in phase.
    #:
    #: The previous spelling matched only a bare "```\n" as an opener, so a ```bash block
    #: anywhere ABOVE the prompt put the whole document out of phase: its closing fence
    #: reads as an opening one, and every pair from there on is shifted by one. #881 put a
    #: `uv tool install charter-cp` block at the top of `docs/install.md` and the prompt
    #: stopped being found at all — four cases failing for a document that still said the
    #: right thing. The old comment named that hazard and defended against only half of it.
    _FENCE = re.compile(r"^```[A-Za-z0-9_+-]*\n(.*?)^```", re.S | re.M)

    def _paste_block(self) -> str:
        # Each document is still scanned on its own: concatenating them would let a fence
        # in one pair with a fence in the other.
        for doc in (README, INSTALL):
            for block in self._FENCE.findall(doc):
                if "Install charter" in block:
                    return block
        self.fail("the paste-in install prompt is gone from the docs")

    def test_it_installs_the_distribution_that_actually_exists(self):
        """`charter` is not installable — PyPI would not allow the name, so the
        distribution carries a suffix. A prompt saying otherwise installs nothing."""
        import tomllib
        pkg = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["name"]
        self.assertIn(pkg, self._paste_block())

    def test_it_no_longer_types_the_plugin_install_by_hand(self):
        """The two assertions this replaces — that the prompt names
        `claude plugin install <plugin>@<marketplace>`, and that it adds the marketplace
        first — were pinning a real mechanism to prose. #881 moved the mechanism into
        `plugincache.install_argvs`, which `tests/test_plugin_install.py` now holds to both
        facts against the same two manifests. What is left to say here is that the prompt
        does not go back to typing them: it installs the CLI, and `charter init` installs
        the plugin for the plane the reader picks."""
        block = self._paste_block()
        self.assertNotIn("claude plugin install", block)
        self.assertNotIn("marketplace add", block)
        self.assertIn("charter init", block,
                      "the prompt must still say which command installs the plugin")

    def test_it_does_not_tell_an_agent_to_run_init(self):
        """`charter init` inside an existing git repo makes THAT repo a control plane.
        An install prompt pasted from an unrelated project would quietly convert it, so
        the prompt must stop before anything that writes to the working directory."""
        block = self._paste_block()
        self.assertIn("Do NOT run `charter init`", block)

    def test_it_tells_the_user_to_restart(self):
        """Hooks load on the next session, so an install that looks complete and does
        nothing is the default experience without this line."""
        self.assertIn("restart", self._paste_block().lower())


if __name__ == "__main__":
    unittest.main()
