# 2026-09-19, charter-app: two machine-level hangs that look like code def

_2026-09-19 13:12 · persistent_

2026-09-19, charter-app: two machine-level hangs that look like code defects. (1) A COPIED node_modules on macOS hangs vitest/tsc/eslint/prettier forever — Gatekeeper re-assesses the copied native binaries and syspolicyd is saturated; symlink @esbuild/*/bin/esbuild and the *.node files to the originals. (2) cargo spawns rustc children that are created and never scheduled when the machine is full (150+ claude/node processes, ~400 MB free of 48 GB) — not an exec bug. rustfmt runs standalone without cargo, so fmt can still be checked. Check vm_stat and the process count before debugging either.
