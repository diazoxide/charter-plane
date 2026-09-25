# charter-app worktrees have no node_modules, and symlinking the shared ap

_2026-09-22 22:58 · persistent_

charter-app worktrees have no node_modules, and symlinking the shared app/node_modules does not work: it is stale (missing @tailwindcss/vite) and vite resolves its temp config from the symlink's real path, so the import fails. Run 'npm ci' inside the worktree's app/ instead — it takes about 7 seconds.
