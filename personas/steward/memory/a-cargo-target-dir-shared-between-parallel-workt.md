# A CARGO_TARGET_DIR shared between parallel worktrees of charter (measure

_2026-09-26 20:43 · persistent_

A CARGO_TARGET_DIR shared between parallel worktrees of charter (measured 2026-09-26, SI-5) makes them clobber each other: workspace path crates get the same metadata hash in every worktree, so a sibling's build overwrites libcharter_core / test binaries between your compile and run. Symptoms: your own new items 'not found in charter_core', test counts that jump between runs, doctest E0463. Retry the command, and trust a run only when your own new test NAMES appear in its output.
