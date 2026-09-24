# Memory written from inside a worktree can land in the wrong tree: a wo

_2026-09-25 · persistent_

Memory written from inside a worktree can land in the wrong tree: a worktree of a workspace repo has no plane marker of its own, so plane resolution walks back to that repo's main checkout and the memory lands under workspaces/<ws>/<repo>/personas/..., dirtying the clone instead of reaching the plane. Record persona memory from the plane root (or through the app), and check where a memory file actually landed before trusting it was saved.
