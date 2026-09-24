# charter-app#136 (PR #168, 2026-09-22): a chat's PATH is the inherited 

_2026-09-25 · persistent_

charter-app#136 (PR #168, 2026-09-22): a chat's PATH is the inherited PATH, then programs::USER_BIN/SYSTEM_BIN, then the app's own charter directory LAST (programs::chat_path, applied in Chats::open_it), so a bare 'charter' in a plane's .claude/settings.json hook resolves in a Finder-launched app. It has to be last: the Rust charter exits 2 (blocks) on every pretooluse hook it does not answer, so putting it first would shadow any other charter on the operator's PATH and block tool calls. The app's own state hooks never depend on this: harness::hook_command writes the bundled binary's absolute path. A profile env PATH wins whole.
