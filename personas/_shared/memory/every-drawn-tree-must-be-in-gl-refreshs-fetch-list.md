# A tree that any charter surface draws with a CI column must also be in

_2026-08-09 22:54 · persistent_

A tree that any charter surface draws with a CI column must also be in gl-refresh's fetch list (charter-core glrefresh::trees), or its CI column stays blank forever. That is how an embedded plane's own repo and its worktrees once shipped empty. Draw and fetch are decided by one list on purpose; never split it.
