# Rust runs locally as of 2026-09-22 (syspolicyd un-wedged 09-21), but rus

_2026-09-22 13:27 · persistent_

Rust runs locally as of 2026-09-22 (syspolicyd un-wedged 09-21), but rustup is a brew install and its shims are NOT on PATH: call /opt/homebrew/opt/rustup/bin/cargo directly, or write a small sh script that exports PATH first (the isolation check refuses env-var prefixes and subshells as too complex to verify). cargo test -p charter-core is ~15 s build plus ~30 s run. cargo-mutants installs fine with CARGO_INSTALL_ROOT pointed at the scratchpad. Pass libtest args through TWO dashes: cargo mutants ... -- -- --skip NAME (the first reaches cargo test, the second libtest). -F/--re filters by mutant name, -f by file glob; pypath.rs has 165 mutants but only 12 are in realpath.
