# 2026-09-22, later the same day: syspolicyd un-wedged (measured at 2.6% C

_2026-09-22 23:10 · persistent_

2026-09-22, later the same day: syspolicyd un-wedged (measured at 2.6% CPU), so Rust DOES run on this machine again — 'cargo test -p charter-app -- --ignored' regenerates app/src/bindings.ts properly and 'cargo fmt --all --check', 'cargo clippy --workspace --all-targets --locked -- -D warnings' and 'cargo test -p charter-app --locked' all run locally in a few minutes. cargo is at ~/.rustup/toolchains/stable-aarch64-apple-darwin/bin/cargo; it is NOT on PATH and 'which cargo' says not found, which is what made it look dead. Prefer the generator over the hand-splice recorded in the note beside this one.
