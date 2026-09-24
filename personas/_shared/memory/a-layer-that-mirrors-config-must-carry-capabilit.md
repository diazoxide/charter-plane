# A layer that mirrors harness config into workspaces or repos must carr

_2026-09-25 · persistent_

A layer that mirrors harness config into workspaces or repos must carry capability and never a grant. When deciding what a workspace or repo inherits from the plane, ask of each file or key whether it carries CAPABILITY (skills, agents, plugin enablement, status line, env) or AUTHORITY (permission grants, allow rules, credentials). Capability travels; authority never does. In the retired Python CLI, mirroring opencode.json into clones would have put a plane-level allow rule in force in a repo nobody granted it in, and Claude Code's mirror already refused to carry 'permissions'. One mechanism writing into one directory must not answer the grant question differently for different harnesses. Pin this mechanically: have each harness adapter write an allow rule into a throwaway root, and fail the test if the layer mirrors it.
