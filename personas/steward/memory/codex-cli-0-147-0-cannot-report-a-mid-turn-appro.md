# codex-cli 0.147.0 cannot report a mid-turn approval without arming Permi

_2026-09-20 21:30 · persistent_

codex-cli 0.147.0 cannot report a mid-turn approval without arming PermissionRequest, and there is no second channel (charter-app#52, 2026-09-20). Read out of the binary: exactly eleven hook events — PreToolUse, PermissionRequest, PostToolUse, PreCompact, PostCompact, SessionStart, SessionEnd, UserPromptSubmit, SubagentStart, SubagentStop, Stop — matching its own hook-review descriptions; no Notification. The 'notify' config key is NOT a way round it: in 0.147.0 it is hooks/src/legacy_notify.rs, a shim whose single payload type is agent-turn-complete (thread-id, turn-id, cwd, client, input-messages, last-assistant-message) raised off Stop, which charter already has. PreToolUse-without-PostToolUse is timing inference, which ADR 0018 forbids. So the honest fix is wording, not a hook.
