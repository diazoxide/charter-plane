# Anything that installs or enables a harness plugin writes the operator

_2026-09-11 03:24 · persistent_

Anything that installs or enables a harness plugin writes the operator's real harness config (~/.claude/plugins/installed_plugins.json, $CODEX_HOME/config.toml), even for a throwaway plane built to reproduce a bug. When testing, point CLAUDE_CONFIG_DIR / CODEX_HOME / XDG_CONFIG_HOME at a scratch dir and keep the real harness binary off PATH. Verify no leak by hashing the operator's file before and after, and if it changed, read each new entry's projectPath before blaming your run: parallel agents write it too. Never 'clean up' by editing that file.
