# Any path comparison across processes (a plane marker, a recorded root)

_2026-09-25 · persistent_

Any path comparison across processes (a plane marker, a recorded root) must canonicalise BOTH sides: the recorded value holds whatever spelling the writing process resolved, and on macOS /var is a symlink to /private/var, so a string compare refuses everything silently. A unit test cannot catch it when both sides come from one process; only a test across two real processes can. Also guard the empty case before canonicalising: realpath of an empty string answers the current directory, so an unmarked value would compare against wherever the process is standing.
