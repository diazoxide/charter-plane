# Parallel agents share the git WORKING TREE, not just the scratchpad. On

_2026-09-18 17:19 · persistent_

Parallel agents share the git WORKING TREE, not just the scratchpad. On 2026-09-18 (charter-app M1.2) a review sub-agent ran 'git checkout main' + 'git pull' in the implementer's own clone while the implementer was mid-task: HEAD moved off the feature branch and main advanced two merged PRs under it. Nothing was lost because the work was already committed and pushed, but uncommitted work would have been at risk and the tree state silently stopped matching what the implementer believed. Before dispatching a reviewer or any Bash-capable sub-agent at a repo: commit and push first, then give yourself a dedicated 'git worktree add' (or tell the agent to make its own). A good reviewer DOES create its own worktree - this one did, at scratchpad/wt-review - but only after it had already moved the shared clone. Symptom to recognise: 'file changed on disk' notices naming files you never touched, carrying another milestone's features.

**2026-09-22, the other half of the same trap.** Once every agent gets its own
`.claude/worktrees/agent-*`, nobody builds in the shared clone any more — so nobody
fast-forwards it either. It was found sitting **64 commits behind `origin/main`** (at an M2.2
commit) while `main` had 64 newer ones, and listing `crates/charter-core/src/` in it produced a
module list old enough to be reported to the operator as fact. **Read `git ls-tree origin/main`,
not the working tree, whenever the answer is "what does the code look like now".** `git rev-list
--count HEAD..origin/main` is the one-line check; it costs nothing and the tree gives no hint.
