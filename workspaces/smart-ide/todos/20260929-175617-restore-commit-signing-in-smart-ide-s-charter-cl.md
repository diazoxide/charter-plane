# Restore commit signing in smart-ide's charter clone (moved from ide M8.7

_2026-09-29 17:56 · persistent_

Restore commit signing in smart-ide's charter clone (moved from ide M8.7): workspaces/smart-ide/charter/.git/config has commit.gpgsign=false, written by agents running 'git config' inside worktrees (a worktree's git config writes the shared clone), so the operator's own commits there are unsigned. Fix once no agent worktree is active: 'git config --unset commit.gpgsign' in that clone; agents should pass '-c commit.gpgsign=false' per commit instead.
