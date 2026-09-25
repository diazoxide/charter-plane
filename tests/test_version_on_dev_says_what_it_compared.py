"""#937: on the dev channel, `charter version` called an older release newer.

Measured on the 0.60.0 wheel, on a plane declaring ``[update] channel = "dev"``, with a
cache holding ``latest: 0.58.0`` and a ``head`` from inside v0.59.0. One screen said:

    • A newer charter is published (0.58.0).
    •   update, commit and push the lock:  charter version bump --push
      installed  0.60.0
      latest     — (cached 0.58.0 is stale: it predates the 0.60.0 you are running)

The condition asked the dev channel (`update.newer_than` hands off to `newer_head`, which
nudges any build that records no commit), and the message answered with the PyPI cache,
a number that condition had never compared with anything. Three things were wrong, and
each class below pins one of them:

* **The headline printed a value its condition did not test.** On dev the verdict now
  names what was compared: the cached head against this build's commit, or, where there is
  no commit, the fact that this build did not come from `main`. It never prints a PyPI
  number, and its remedy is `charter update` — or `git`, where the charter running the
  command IS the tree, because `charter update` sends that reader back to `charter
  version`. `version bump --push` writes a pin that this plane's own session start calls
  contradictory.
* **`report send` claimed a direction nobody measured.** ``9d18d55 is out — this may
  already be fixed`` was said to a build that `9d18d55` predates. The nudge is kept,
  because `newer_head`'s docstring explains why it is deliberate, and both dev cases now
  print `update.dev_verdict`, the same sentence `charter version` prints.
* **`version bump` pinned a version it had not fetched.** It called `fetch_and_store` and
  then re-read the cache, which a failed GET leaves untouched. So the refusal fired only
  on an empty cache, and a stale one was installed over the running build and pushed.

ADR 0013: do not present as checked what was not checked. ADR 0009: an error may not
assert a cause it did not verify, which is why that refusal no longer says "offline?".

Nothing here reaches the network or installs anything: `NoNetwork` refuses every route
out, the two GETs are stubbed where a test needs an answer, and `sync_to`,
`set_locked_version` and `commit_push` are recorders.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest import mock

from charter import __version__, commands, commands_report, update, util
from tests._isolation import PersonaIso, pin_update_channel
from tests.test_dev_channel import NoNetwork

#: Older than any charter that can be running this suite. The field report's cache held
#: 0.58.0 under a 0.60.0 wheel, and the exact numbers are not the point.
_STALE = "0.0.1"
#: The report's cached head, `9d18d55`, which is contained in v0.59.0. It is older than
#: the wheel it was offered to, and nothing in charter can know that from a wheel.
_HEAD = "9d18d55" + "0" * 33
_MINE = "a" * 40


def _cache(**record) -> None:
    p = update._cache_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(record))


def _run(fn, args) -> tuple[int, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = fn(args)
    return rc, out.getvalue() + err.getvalue()


def _verdict(printed: str) -> str:
    """Everything `charter version` printed except its three table rows.

    The `latest` row legitimately carries the cached PyPI number, as "cached 0.0.1 is
    stale", and that row was right all along. Filtering it out is what lets "no PyPI number
    in the verdict" be asserted at all, rather than weakened to "no word 'published'".
    """
    rows = ("installed ", "locked ", "latest ")
    return "\n".join(l for l in printed.splitlines() if not l.lstrip().startswith(rows))



class VersionBumpPinsOnlyWhatItFetched(NoNetwork, PersonaIso):
    """`version bump` with no `--to` pins the version its own GET returned, or refuses."""

    def setUp(self):
        super().setUp()
        self.calls: list[tuple] = []

        def sync_to(v):
            self.calls.append(("sync_to", v))
            return True, v

        def set_locked_version(root, v):
            self.calls.append(("set_locked_version", v))
            return True

        def commit_push(root, add, message):
            self.calls.append(("commit_push", message))
            return 0

        self.enterContext(mock.patch("charter.commands.sync_to", side_effect=sync_to))
        self.enterContext(mock.patch("charter.instance.set_locked_version",
                                     side_effect=set_locked_version))
        self.enterContext(mock.patch("charter.commands.commit_push", side_effect=commit_push))

    def _bump(self):
        return _run(commands.cmd_version_bump, SimpleNamespace(to=None, push=True))

    def test_a_failed_pypi_fetch_over_a_stale_cache_refuses(self):
        """The downgrade. `fetch_and_store` leaves `latest` alone when its GET fails, and
        the re-read found 0.58.0 there, installed it over 0.60.0 and pushed the pin."""
        pin_update_channel(self, "stable")
        _cache(latest=_STALE, ts=1.0)
        with mock.patch.object(update, "_fetch_latest", return_value=None):
            rc, printed = self._bump()
        self.assertEqual(rc, 1)
        self.assertEqual(self.calls, [], "bump acted on a version it did not fetch")
        self.assertIn("charter version bump --to", printed)
        self.assertNotIn("offline", printed,
                         "the refusal names a cause it did not check (ADR 0009): "
                         "`fetch_and_store` also answers None when PyPI replied and the "
                         "cache write failed")

    def test_a_successful_fetch_pins_what_it_fetched(self):
        pin_update_channel(self, "stable")
        _cache(latest=_STALE, ts=1.0)
        with mock.patch.object(update, "_fetch_latest", return_value="99.0.0"):
            rc, _ = self._bump()
        self.assertEqual(rc, 0)
        self.assertEqual(self.calls, [("sync_to", "99.0.0"),
                                      ("set_locked_version", "99.0.0"),
                                      ("commit_push", "charter: pin to 99.0.0")])

    def test_a_padded_answer_is_trimmed_before_it_becomes_a_pin(self):
        """The fetched value is trimmed the way `--to` is, and the cache read it replaced
        was. It ends up on the right-hand side of `charter-cp==` and in a committed
        `charter.toml`, and a trailing newline there is a pin nothing can install."""
        pin_update_channel(self, "stable")
        with mock.patch.object(update, "_fetch_latest", return_value=" 99.0.0\n"):
            rc, _ = self._bump()
        self.assertEqual(rc, 0)
        self.assertEqual([v for _, v in self.calls[:2]], ["99.0.0", "99.0.0"])


if __name__ == "__main__":
    import unittest
    unittest.main()
