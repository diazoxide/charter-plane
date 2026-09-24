# CLAUDE_PID and CLAUDE_CODE_SESSION_ID are inherited by ANY process start

_2026-09-18 15:19 · persistent_

CLAUDE_PID and CLAUDE_CODE_SESSION_ID are inherited by ANY process started under a Claude Code session, not just its hooks (measured 2026-09-18). So an app launched from inside a chat passes the launcher's harness identity to every child it spawns, and a hook in one of those children reports the LAUNCHER's pid/conversation as its own. charter-app had to strip them (Spec::env_without / hookwire::NOT_INHERITED) before a chat could report honestly. A scenario test caught it; no unit test could have.
