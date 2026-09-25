# A diff-scoped check (mutation testing, coverage, lint-on-changed-lines

_2026-09-25 · persistent_

A diff-scoped check (mutation testing, coverage, lint-on-changed-lines) run on a STACKED branch against origin/main charges the branch for its base's lines: a PR branched off another reported 13 mutation survivors, 4 of them the base PR's, and 0 once the base merged and the branch rebased (#873, 2026-09-04). The same mis-charge happens when the diff is taken to a PR's MERGE commit: merge-base..merge-commit includes everything main gained since the merge-base, so the correct range is merge-base..HEAD. Rule: rebase onto the merged base before reading a diff-scoped verdict as a verdict on your change, and when a finding names a file your branch does not touch, suspect the range before your code.
