# Rebasing here fails at the commit step with '1Password: failed to fill w

_2026-09-20 10:08 · persistent_

Rebasing here fails at the commit step with '1Password: failed to fill whole buffer' even when commit.gpgsign is false: the sequencer records the signing flag at rebase start in .git/rebase-merge/gpg_sign_opt as -S and uses that, not the config; emptying that file did not help. The way through is to quit the rebase (it ends the operation but leaves HEAD, index and worktree exactly as the conflict resolution left them), commit plainly, then move the branch ref to HEAD.
