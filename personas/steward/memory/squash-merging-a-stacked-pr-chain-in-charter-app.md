# Squash-merging a stacked PR chain in charter-app: GitHub auto-retargets

_2026-09-25 15:08 · persistent_

Squash-merging a stacked PR chain in charter-app: GitHub auto-retargets the next PR to main when the base branch is deleted, but it then conflicts (it still carries the parent's original commits). Merge origin/main into it (no force-push); verify main == parent tip + unrelated files with git diff --stat before taking the branch side of a conflict.
