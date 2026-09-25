# charter's PreToolUse guard refuses gh pr create/issue create with an inl

_2026-09-25 11:58 · persistent_

charter's PreToolUse guard refuses gh pr create/issue create with an inline $(cat <<EOF) body; pass --body-file - with a quoted heredoc (<<'BODY') or a file. To land a docs PR without touching the shared charter-app clone, git worktree add a branch from origin/main in the scratchpad and remove it after pushing.
