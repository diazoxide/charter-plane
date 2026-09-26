# On this machine cargo is not on PATH in agent shells: export PATH=/opt/h

_2026-09-26 20:07 · persistent_

On this machine cargo is not on PATH in agent shells: export PATH=/opt/homebrew/opt/rustup/bin:$PATH. A CARGO_TARGET_DIR shared between parallel agent worktrees can produce a spurious compile error (another worktree's crate build lands mid-build); rerun before debugging it.
