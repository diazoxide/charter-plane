# The plane's remote is diazoxide/charter-plane, not diazoxide/charter. di

_2026-10-02 15:58 · persistent_

The plane's remote is diazoxide/charter-plane, not diazoxide/charter. diazoxide/charter is now the desktop app repo (the old charter-app, renamed). A plane clone whose origin still points at diazoxide/charter shows main as unrelated (ahead ~860, behind ~400, no merge base), and charter save fails its rebase. Fix (2026-10-02): git remote set-url origin https://github.com/diazoxide/charter-plane.git, git fetch --prune, git merge --ff-only origin/main. Local main was a strict ancestor of charter-plane/main.
