# Building a THROWAWAY plane (a demo, a screenshot capture, a probe) mus

_2026-09-25 · persistent_

Building a THROWAWAY plane (a demo, a screenshot capture, a probe) must not touch the operator's real harness setup. Anything that wires a harness for a plane (installing a harness plugin, writing harness settings) runs against the caller's HOME and whatever harness binary is on PATH, so a scratch-plane script must give it an isolated HOME and strip the real harness from PATH. A review caught a demo script that did not (PR 958, 2026-09-11). Related: a Unix socket path under the Claude Code session scratchpad can exceed the 104-byte sun_path limit on macOS, so put sockets in a short directory under /tmp.
