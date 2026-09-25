# charter-app app/src/bindings.ts hand-mirroring, third confirmation (PR 1

_2026-09-21 01:05 · persistent_

charter-app app/src/bindings.ts hand-mirroring, third confirmation (PR 111, 2026-09-20): signatures, argument order, camelCase keys, Option->|null, alphabetical type ordering, transparent newtype (struct PlaneId(String) -> 'export type PlaneId = string;') all matched tauri-specta byte for byte on the first try. The ONLY thing that went wrong was the blank line inside a doc block, which must be tab + ' * ' WITH a trailing space — a Write/heredoc pipeline can strip it and prettier --check will not complain either way. Fastest recovery: let CI's the_typescript_the_ui_imports_is_the_one_these_commands_generate fail, pull the job log, ast.literal_eval the Rust Debug string after 'right: ' and write it straight to bindings.ts. That is the generator's own output, no guessing.
