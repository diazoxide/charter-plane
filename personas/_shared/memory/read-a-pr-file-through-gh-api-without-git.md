# To read one file on a PR's branch without running git anywhere (e.g. w

_2026-09-10 17:53 · persistent_

To read one file on a PR's branch without running git anywhere (e.g. when every local worktree is in use by agents), use gh api repos/OWNER/REPO/contents/PATH?ref=BRANCH with header 'Accept: application/vnd.github.raw' and redirect to a scratch file; gh api repos/OWNER/REPO/pulls/N/commits lists the head commits, and gh pr diff N greps the whole change. Worked 2026-09-10 on diazoxide/charter PR 948.
