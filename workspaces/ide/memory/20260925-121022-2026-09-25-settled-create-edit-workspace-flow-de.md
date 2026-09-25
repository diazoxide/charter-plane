# 2026-09-25: settled create/edit-workspace flow design (see workspace.md 

_2026-09-25 12:10 · persistent_

2026-09-25: settled create/edit-workspace flow design (see workspace.md Context & decisions). /-cwd root cause: charter-core start.rs:228 returns raw start.cwd instead of resolved plane root. Plan: one charter-app PR.
