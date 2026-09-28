# git --no-optional-locks does NOT stop porcelain 'git diff' refreshing .g

_2026-09-28 23:19 · persistent_

git --no-optional-locks does NOT stop porcelain 'git diff' refreshing .git/index under index.lock when a tracked file is stat-dirty (git 2.50, measured); it only stops status's refresh. A read-only poll must use plumbing 'git diff-files' (SI-9f, charter PR #527).
