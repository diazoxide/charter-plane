# charter-app chats carry where they started (SI-1, PR #498): start::ready

_2026-09-26 22:54 · persistent_

charter-app chats carry where they started (SI-1, PR #498): start::ready sets CHARTER_WORKSPACE=<ws> for a chat in a workspace and CHARTER_PLANE_ROOT_SESSION=1 for one at the plane root (neither elsewhere); both are in hookwire::NOT_INHERITED. active::at_plane_root is asked BEFORE the ladder; -w or a non-blank CHARTER_WORKSPACE outranks it. CLI Here::active_workspace returns Result and refuses at the root; workspace_if_any is for commands that run without one (recall, extcmd, glstate). The cwd rung now counts bare workspaces/<ws>, and Plane::workspace_of calls active::workspace_of_tree.
