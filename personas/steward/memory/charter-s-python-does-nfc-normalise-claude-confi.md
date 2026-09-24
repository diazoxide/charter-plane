# Claude Code NFC-normalises its config home: (CLAUDE_CONFIG_DIR ?? join

_2026-09-25 · persistent_

Claude Code NFC-normalises its config home: (CLAUDE_CONFIG_DIR ?? join(homedir(), '.claude')).normalize('NFC'), read off the Claude Code 2.1.268 binary. Any charter code that computes Claude's config path must normalise the same way, or a path with decomposed Unicode names a different directory than Claude uses. The Rust port first missed this and a differential scenario against the Python oracle caught it (charter-app PR #85).
