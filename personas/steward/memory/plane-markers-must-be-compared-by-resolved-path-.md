# Compare paths by their RESOLVED form whenever the two sides come from 

_2026-09-25 · persistent_

Compare paths by their RESOLVED form whenever the two sides come from different processes or code paths, never by string. On macOS /var is a symlink to /private/var (and /tmp to /private/tmp), so one directory reached via a canonicalizing reader (realpath/fs::canonicalize) and a non-canonicalizing writer produces two spellings that never compare equal, and a best-effort check that declines on mismatch then fails silently every time. Measured 2026-09-16 in the retired Python frame, where it made every exit check decline without output. Canonicalize both sides at the comparison, and treat any identity check that crosses a process boundary as suspect until it does.
