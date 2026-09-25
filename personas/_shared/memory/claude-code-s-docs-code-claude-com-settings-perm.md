# Claude Code's docs (code.claude.com settings, permissions and worktree

_2026-09-25 · persistent_

Claude Code's docs (code.claude.com settings, permissions and worktrees pages, fetched 2026-09-10): .claude/settings.local.json is not cwd-only. It loads from the git repository root, and in a linked git worktree from the MAIN checkout's root (v2.1.211+). Only .claude/settings.json keys (enabledPlugins, env, hooks, permissions) are read from the cwd, with no fallback to a parent. Workspace trust in a linked worktree also uses the main checkout's root, so a worktree does not need its own trust acceptance. This comes from the docs and was not re-measured; check it against the installed version before charter-app code relies on it.
