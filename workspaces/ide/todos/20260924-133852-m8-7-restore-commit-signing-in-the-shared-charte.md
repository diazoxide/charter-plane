# M8.7 Restore commit signing in the shared charter-app clone once no agen

_2026-09-24 13:38 · persistent_

M8.7 Restore commit signing in the shared charter-app clone once no agent worktree is active: agents ran `git config commit.gpgsign false` in worktrees, which writes the SHARED clone config (/Users/aharon/IdeaProjects/charter/workspaces/ide/charter/.git/config), so the operators own commits there are unsigned. Fix: `git config --unset commit.gpgsign` in that clone; for future agents use `git config extensions.worktreeConfig true` + `git config --worktree commit.gpgsign false`.
