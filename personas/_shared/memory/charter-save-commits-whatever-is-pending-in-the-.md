# A plane save commits whatever is pending in the plane's tree, not only

_2026-09-25 · persistent_

A plane save commits whatever is pending in the plane's tree, not only memories, so check the commit's directory breakdown, never its file count. Measured 2026-09-12: a save reported 169 files, which read as an ordinary batch of persona memories. Listed by directory, it included uv.lock, a repo file that had never existed in the repository. Some agent's local tool run created it on the machine, and nothing ignored it. A project file reached main through the plane's save with no PR and nobody choosing it. In charter-app, auto-save and the save modes (commit, push, pr, pr-merge) take the plane's pending changes the same way. After a save, one `git show --stat` (or `--dirstat`) over the commit is the whole check. A save that rebases onto a moved remote can print a SHA that no longer exists by the time it finishes, so read the SHA off the remote.
