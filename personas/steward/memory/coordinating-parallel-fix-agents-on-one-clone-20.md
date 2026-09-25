# Coordinating parallel fix agents on one clone (2026-09-13, user-reportin

_2026-09-13 10:24 · persistent_

Coordinating parallel fix agents on one clone (2026-09-13, user-reporting): (1) charter wt add branches from the clone CURRENT HEAD by design, not origin/main, so with a feature branch checked out every piece silently carries it; cut parallel pieces with git worktree add -b <branch> <path> origin/main. (2) Worktrees of one clone share one git stash; an agent used bare git stash/pop to prove red-without-fix while siblings were live. Every brief must forbid git stash (use a WIP commit or git show origin/main:file). (3) Agents told to watch CI stop repeatedly with idle notifications and never write their report; the coordinator should own one Monitor over all session PRs and briefs should say open the PR, report, finish.
