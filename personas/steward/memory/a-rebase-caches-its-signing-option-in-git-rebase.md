# A rebase caches its signing option in .git/rebase-merge/gpg_sign_opt, so

_2026-09-20 10:06 · persistent_

A rebase caches its signing option in .git/rebase-merge/gpg_sign_opt, so setting commit.gpgsign=false after a conflict does not take and --continue keeps failing on the 1Password agent. Delete that file, then continue.
