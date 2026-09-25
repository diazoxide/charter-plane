# charter-app's app/src/bindings.ts CAN be produced without cargo when not

_2026-09-22 22:20 · persistent_

charter-app's app/src/bindings.ts CAN be produced without cargo when nothing Rust runs locally (syspolicyd): splice it with a script that reads the Rust doc comments out of the source rather than retyping them, and mirror tauri-specta's shape — tab indent, /**  one line */ inline, multi-line blocks with ' * ' (trailing space) for a blank doc line, snake_case params camelCased in the invoke object, types sorted alphabetically. CI's the_typescript_the_ui_imports_is_the_one_these_commands_generate is the check, and it passed first time on PR #172 (2026-09-22). Cargo.lock can be hand-edited the same way for a crate already in the tree (chrono under charter-app) — CI runs --locked.
