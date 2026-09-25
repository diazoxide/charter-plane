"""charter: an engine for control-plane repo tooling.

A tiny, stdlib-only CLI that keeps an inventory of every repo in a configured
GitLab group and clones them on demand into ``workspaces/``.

Run it as ``python3 -m charter`` (from the control plane root) or via the
installed ``charter`` console script.
"""

__version__ = "0.62.2"
