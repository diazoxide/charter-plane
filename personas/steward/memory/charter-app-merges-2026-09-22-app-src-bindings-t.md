# charter-app merges (2026-09-22): app/src/bindings.ts and App.css are the

_2026-09-22 21:33 · persistent_

charter-app merges (2026-09-22): app/src/bindings.ts and App.css are the two files a stacked-branch merge gets wrong. bindings.ts is GENERATED — always regenerate after any merge (cargo test -p charter-app -- --ignored), never hand-resolve, and note that RUNNING a debug charter-app (including a stale e2e build from another branch) REWRITES app/src/bindings.ts from that binary's commands, which silently broke a later build. App.css conflicts must NOT be resolved by a line-level union: git's chunks split inside rule blocks and produce unclosed CSS; take main's file whole and re-append your own blocks (scratchpad css_merge.py). Also: a scenario spec that fires a 'stop' hook leaves the chat in the needs-you queue and turns palette.e2e.ts red.
