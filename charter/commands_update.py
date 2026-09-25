"""`charter update` — says that charter-cp is finished, and installs nothing.

charter-cp 0.62.2 is the last release. Up to 0.62.1 this command moved the CLI (from PyPI,
or on the dev channel from ``git+https://github.com/diazoxide/charter@main``), then the
harness artifact, then the plane's pin. Both sources are gone as upgrade paths: there is no
newer charter-cp on PyPI, and ``diazoxide/charter`` is now the desktop app's repository,
while this package's history moved to ``diazoxide/charter-plane``, whose ``main`` holds no
Python package. An install from either would at best do nothing and at worst replace
charter-cp with something that is not it.

So the command prints :data:`charter.update.END_OF_LIFE` and exits 0. Exit 0 because
nothing failed: an agent that runs `charter update` to stay current is current, as current
as charter-cp gets. ``--to`` and ``--bump`` are still accepted so that a script passing them
gets the same answer rather than a usage error, and neither installs or writes anything.
"""

from __future__ import annotations

from . import update, util


def cmd_update(args) -> int:
    util.warn(update.END_OF_LIFE)
    util.info("  nothing was installed: charter-cp 0.62.2 is the last release, "
              "and `charter update` no longer installs anything.")
    return 0
