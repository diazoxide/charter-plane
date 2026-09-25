# Permission-rule matching (charter-app crates/charter-core/src/scaffold

_2026-09-25 · persistent_

Permission-rule matching (charter-app crates/charter-core/src/scaffold/settings.rs, ported from the Python guard's _as_rule): never classify a rule by a raw prefix of tool names — 'Globalprotect --connect' starts with 'Glob' and 'Taskwarrior add x' with 'Task'. Test the rule's SHAPE (Tool(pattern) | bare tool name | bare mcp__ name), or the fix mirrors the bug it fixes (charter#365).
