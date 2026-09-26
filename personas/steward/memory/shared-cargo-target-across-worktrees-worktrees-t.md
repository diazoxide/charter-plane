# Shared cargo target across worktrees (.worktrees/_target) can leave a bu

_2026-09-26 22:54 · persistent_

Shared cargo target across worktrees (.worktrees/_target) can leave a build-script binary compiled with ANOTHER worktree's CARGO_MANIFEST_DIR: charter-core build.rs then panics 'cannot read .../si-2a-.../docs'. Fix: touch crates/charter-core/build.rs and rebuild. Under concurrent load, extension_commands' 30s timeout and a charter-app doctest (E0463 can't find charter_core) also flake; rerun alone.
