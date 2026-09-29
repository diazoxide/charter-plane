# The plane repo diazoxide/charter-plane is plane-only since 2026-09-25 (c

_2026-09-29 17:56 · persistent_

The plane repo diazoxide/charter-plane is plane-only since 2026-09-25 (charter-plane#1186, tag cli-final): the Python charter left it; nothing that ships lives there. No new ADRs in the plane repo — ADR numbering belongs to the app (diazoxide/charter); the plane's docs/adr/ is history only. The old charter@charter plugin is gone from Claude Code's and Codex's caches and ~/.codex/config.toml, so a terminal claude/codex started outside the app has no charter guard (app #374).
