# A git worktree of the plane isolates files, not plane state. In the re

_2026-09-25 · persistent_

A git worktree of the plane isolates files, not plane state. In the retired Python CLI, plane identity followed the main working tree, so any charter command run from a release or feature worktree wrote the operator's real plane, while some other paths did follow the worktree. Do not assume either behaviour for charter-app's CLI: before running any charter command that mutates state from a worktree, check where it resolves the plane and its state directory (read the resolution code or run a read-only command that prints the path). Prefer calling the library function in-process over shelling out to the CLI when you only need its effect.
