# GitHub required status checks: a required check whose conclusion is 's

_2026-08-30 10:39 · persistent_

GitHub required status checks: a required check whose conclusion is 'skipped' counts as satisfied (the PR reports mergeStateStatus CLEAN). So requiring a job whose if: skips it on pull_request is decoration, not a gate. A required context that no job ever reports is the opposite: the PR is blocked forever. When adding a required check, confirm the job runs, not skips, on pull_request. Measured 2026-08-30.
