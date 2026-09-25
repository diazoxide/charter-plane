# charter-app CI (2026-09-23): a PR whose branch has gone CONFLICTING with

_2026-09-23 01:22 · persistent_

charter-app CI (2026-09-23): a PR whose branch has gone CONFLICTING with main gets NO workflow run at all — GitHub cannot compute the merge commit, so 'gh pr checks' says 'no checks reported' and 'gh run list --branch' shows nothing new however many times you push. Check 'gh pr view N --json mergeable,mergeStateStatus' (CONFLICTING/DIRTY) before concluding the queue is just congested. Fix by merging origin/main in and pushing (force-push is blocked on this repo).
