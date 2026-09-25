# claude plugin list --json carries an enabled flag per install record, 

_2026-09-10 17:53 · persistent_

claude plugin list --json carries an enabled flag per install record, but it is computed from the current directory's resolved enabledPlugins, not from the record's projectPath (measured on Claude Code 2.1.267). It is a cheap read-only way to ask whether Claude Code enables a plugin for a directory without starting a session; unset CLAUDECODE and the CLAUDE_CODE_* session vars when running it from inside a session. It is the host's flag, not proof a session's hooks fired.
