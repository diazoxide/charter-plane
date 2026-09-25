# A read guard only sees reads that happen. A probe of a guard that refu

_2026-09-25 · persistent_

A read guard only sees reads that happen. A probe of a guard that refused reads of the operator's charter.local.toml found a surface still answering unrefused: for a file git would commit, it answered from git alone and returned before ever reading the file, so the guard never fired. The fix was ordering (read through the guarded path first). When probing a new read guard, drive every surface down each early-return path, not just the happy path. (Found 2026-09-11, PR #978, on the Python charter.)
