# MERGE GATE: do not trust 'gh pr checks' or mergeStateStatus=CLEAN alon

_2026-09-25 · persistent_

MERGE GATE: do not trust 'gh pr checks' or mergeStateStatus=CLEAN alone to mean CI passed. GitHub intermittently swallows Actions triggers, so a pushed sha can have total_count:0 check-runs while the PR still reports CLEAN when nothing requires those checks (hit twice on 2026-08-26 on the old charter repo, which then had no branch protection). Always verify per head SHA, not per PR: gh api repos/<owner>/<repo>/commits/<HEAD_SHA>/check-runs. If total_count is 0, trigger the workflow (gh workflow run <file> --ref <branch>). On a repo with required checks, confirm the required list actually covers the jobs you care about.
