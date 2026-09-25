"""The right-aligned brand, and the update indicator beside it.

Two rules the status line cannot break, because it renders on every single turn:

* **never block** — the "is there a newer charter?" answer comes from a cache another
  process fills; nothing here touches the network;
* **never cost content** — the brand is dropped entirely when the last line is long
  enough that showing it would crowd a repo row.
"""

from __future__ import annotations

import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from charter import config, statusline, tui, update
from tests._isolation import PersonaIso, no_background_refresh, pin_update_channel


class BrandLayout(unittest.TestCase):
    def setUp(self) -> None:
        # Never fork a network child from a test. One call rather than three lines of
        # hand-rolled stubbing, and it covers the forge refresh beside the version
        # check — a file that stubbed only one of the two forked the other (#542).
        no_background_refresh(self)
        # `_brand` renders the `dev` chip from `config.UPDATE`, so every width assertion
        # below is a function of the channel unless it is pinned (#459). This class is
        # about LAYOUT and runs against the real plane on purpose; the chip belongs to
        # `UpdateIndicator` and `test_dev_channel`, which own it against a fixture.
        pin_update_channel(self)

    def test_brand_is_right_aligned_on_the_last_line(self):
        out = statusline._with_brand("short", 120)
        last = out.split("\n")[-1]
        self.assertTrue(last.startswith("short"))
        self.assertEqual(tui.width(last), 120, "must reach exactly the right edge")

    def test_only_the_last_line_is_touched(self):
        body = "one\ntwo\nthree"
        out = statusline._with_brand(body, 120)
        self.assertEqual(out.split("\n")[:-1], ["one", "two"])

    def test_dropped_when_it_would_crowd_the_content(self):
        """Branding must never push out a repo row."""
        body = "x" * 112
        self.assertEqual(statusline._with_brand(body, 120), body)

    def test_dropped_on_a_narrow_pane(self):
        for w in (24, 30, 40):
            with self.subTest(width=w):
                body = "x" * (w - 8)
                self.assertEqual(statusline._with_brand(body, w), body)

    def test_never_exceeds_the_width(self):
        for w in (24, 40, 80, 120, 200):
            for used in (0, 5, 20):
                with self.subTest(width=w, used=used):
                    out = statusline._with_brand("x" * used, w)
                    for line in out.split("\n"):
                        self.assertLessEqual(tui.width(line), w)

    def test_an_empty_body_does_not_crash(self):
        statusline._with_brand("", 80)

    def test_layout_failure_returns_the_body_unchanged(self):
        """The status line's whole contract is that it never crashes."""
        orig = statusline._brand
        statusline._brand = lambda: 1 / 0
        try:
            self.assertEqual(statusline._with_brand("body", 120), "body")
        finally:
            statusline._brand = orig


class UpdateIndicator(PersonaIso):
    """`PersonaIso`, not a hand-rolled ``config.STATE_DIR`` redirect.

    Every assertion here is about the STABLE channel's comparison — `update.newer_than`
    hands off to `newer_head` on dev, where a cached ``"9.9.9"`` means nothing — and
    redirecting one attribute left `config.UPDATE` reading the channel of whatever plane
    the suite resolved. On a developer whose own `charter.toml` declares
    ``channel = "dev"`` these went red, and only there (#459). `PersonaIso` re-derives
    every setting from a tmp plane in one `config.use()` call, so the channel is the
    default `stable` because the fixture says so, not because the machine does.
    """

    def setUp(self) -> None:
        super().setUp()
        # _brand() calls maybe_spawn(), and a temp STATE_DIR always looks stale — so
        # without this every test here forks a real network child. A suite that
        # quietly reaches the internet is not hermetic.
        no_background_refresh(self)

    def _cache(self, latest: str, age: float = 0) -> None:
        p = config.STATE_DIR / "cache" / "update.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"latest": latest, "ts": time.time() - age}))


    def test_same_version_is_not(self):
        self._cache("0.6.0")
        self.assertIsNone(update.newer_than("0.6.0"))

    def test_older_cached_version_is_not(self):
        self._cache("0.5.0")
        self.assertIsNone(update.newer_than("0.6.0"))


    def test_no_cache_means_no_claim(self):
        self.assertIsNone(update.newer_than("0.6.0"))

    def test_an_unparseable_version_never_claims_an_update(self):
        """Better to show nothing than to nag about a release that isn't there."""
        for bad in ("", "not-a-version", "junk.junk"):
            with self.subTest(latest=bad):
                self._cache(bad)
                self.assertIsNone(update.newer_than("0.6.0"))

    def test_a_string_with_digits_in_it_is_still_not_a_version(self):
        """#1050. The rule above held only for strings with no digits: ``build7`` read as
        ``(7,)`` and ``99.0.0-CANARY`` as ``(99, 0, 0)``, both newer than 0.6.0, so the arrow
        offered an update to something that is not a version at all."""
        for bad in ("build7", "99.0.0-CANARY"):
            with self.subTest(latest=bad):
                self._cache(bad)
                self.assertIsNone(update.newer_than("0.6.0"))

    def test_a_release_candidate_is_not_newer_than_its_release(self):
        """#1050: ``0.7.0rc1`` read as ``(0, 7, 1)``, so a machine already on 0.7.0 was told
        its own release's candidate was the newer charter."""
        self._cache("0.7.0rc1")
        self.assertIsNone(update.newer_than("0.7.0"))


    def test_brand_always_names_the_running_version(self):
        import charter
        self.assertIn(charter.__version__, statusline._brand())


class NeverBlocks(unittest.TestCase):
    """The status line renders every turn — a network call here would be felt."""

    def setUp(self) -> None:
        self._td = TemporaryDirectory()
        self._orig = config.STATE_DIR
        config.STATE_DIR = Path(self._td.name)
        self.addCleanup(self._td.cleanup)
        self.addCleanup(lambda: setattr(config, "STATE_DIR", self._orig))
        # `test_render_never_raises_even_if_the_check_explodes` reaches `_brand`, and so
        # the `dev` chip. Nothing here is about the channel, so it is pinned (#459).
        pin_update_channel(self)

    def test_a_fresh_cache_spawns_nothing(self):
        p = config.STATE_DIR / "cache" / "update.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"latest": "0.6.0", "ts": time.time()}))
        calls = []
        import subprocess
        orig = subprocess.Popen
        subprocess.Popen = lambda *a, **k: calls.append(a)
        try:
            update.maybe_spawn()
        finally:
            subprocess.Popen = orig
        self.assertEqual(calls, [])


    def test_render_never_raises_even_if_the_check_explodes(self):
        orig = update.maybe_spawn
        update.maybe_spawn = lambda: 1 / 0
        try:
            statusline._brand()          # must not raise
        finally:
            update.maybe_spawn = orig


class UpgradeAdviceIsRunnable(unittest.TestCase):
    """Every upgrade command charter prints must actually work.

    Two ways to get this wrong, both of which shipped: the distribution is
    `charter-cp` (PyPI would not allow `charter`, so `pip install charter` fetches
    nothing of ours), and `uv tool upgrade` reports "Nothing to upgrade" for a
    git-installed charter and leaves the user pinned on an old version.
    """

    def _sources(self):
        root = Path(__file__).resolve().parent.parent
        for rel in ("charter/hooks.py", "charter/instance.py"):
            yield rel, (root / rel).read_text()

    def test_no_upgrade_hint_names_the_wrong_distribution(self):
        import re
        bad = re.compile(r"(?:pip|pipx|uv tool)[^`\"']{0,40}?(?:install|upgrade)\s+charter(?!-cp)\b")
        for rel, text in self._sources():
            for line in text.splitlines():
                if line.lstrip().startswith("#"):
                    continue          # explanatory comments may name the wrong form
                with self.subTest(file=rel, line=line.strip()[:70]):
                    self.assertIsNone(bad.search(line))

    def test_no_upgrade_hint_offers_uv_tool_upgrade(self):
        for rel, text in self._sources():
            for line in text.splitlines():
                if line.lstrip().startswith("#"):
                    continue
                with self.subTest(file=rel):
                    self.assertNotIn("uv tool upgrade", line)


if __name__ == "__main__":
    unittest.main()
