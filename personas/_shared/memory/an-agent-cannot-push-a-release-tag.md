# In an agent-run release the agent can merge the bump PR after CI is gr

_2026-09-15 16:11 · persistent_

In an agent-run release the agent can merge the bump PR after CI is green, but pushing the release tag (git tag -a vX.Y.Z && git push origin vX.Y.Z) is denied by the Claude Code auto-mode classifier as [Production Deploy], even with the operator's go-ahead relayed by a coordinator (seen twice, 2026-09-13 and 2026-09-15). The agent's reach ends at a merged main; the operator pushes the tag. Do not route around it with workflow_dispatch or another agent: that is laundering a refusal.
