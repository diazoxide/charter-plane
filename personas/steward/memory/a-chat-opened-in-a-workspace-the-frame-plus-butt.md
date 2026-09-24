# A chat whose cwd is a workspace directory (workspaces/WS) gets Claude 

_2026-09-25 · persistent_

A chat whose cwd is a workspace directory (workspaces/WS) gets Claude Code project settings only from that cwd's .claude/settings.json; Claude Code does not walk up to the plane root for them. So no permission rule written at the plane root (ask or deny) is in force in such a chat unless charter mirrors it into the workspace's settings. Any design that relies on an ask or deny rule reaching the chat that runs a command must mirror the restrictive buckets (ask, deny) into the workspace layer, never allow. Found 2026-09-10 on the Python charter, whose mirror carried only enabledPlugins and env; check what charter-app's settings layer carries before relying on it.
