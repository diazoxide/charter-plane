# gh pr edit --body-file from the SHARED scratchpad pushed another agent's

_2026-09-23 03:25 · persistent_

gh pr edit --body-file from the SHARED scratchpad pushed another agent's PR body onto my PR. The scratchpad is shared across parallel agents and a plain name like pr.md WILL be clobbered mid-task. Namespace every scratch file with the agent/worktree id, and re-read a file immediately before handing it to gh.
