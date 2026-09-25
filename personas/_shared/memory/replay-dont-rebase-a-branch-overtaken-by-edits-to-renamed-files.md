# When a branch that renamed files (e.g. stamped changelog entries) is o

_2026-09-04 12:29 · persistent_

When a branch that renamed files (e.g. stamped changelog entries) is overtaken by a PR that edits those same files, do not rebase: the rename+edit conflict resolves into the renamed copy of the stale text, silently. Reset to origin/main and replay the branch's steps (re-run the bump/stamp), then force-push with --force-with-lease. Replaying also picks up files added after the branch was cut.
