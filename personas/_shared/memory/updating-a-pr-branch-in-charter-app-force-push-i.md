# Updating a PR branch in charter-app: force-push is blocked by the Clau

_2026-09-25 · persistent_

Updating a PR branch in charter-app: force-push is blocked by the Claude Code auto-mode classifier (Git Destructive), so a rebase cannot be published. Merge origin/main INTO the branch instead and push a fast-forward: no force needed, CI re-runs, and the squash-merge hides the extra merge commit on main. Conflicts between parallel branches are almost always 'both sides added a line to the same list' (.gitignore, the module list in crates/charter-core/src/lib.rs, registration lists). Keep BOTH lines, in the existing order; never pick a side.
