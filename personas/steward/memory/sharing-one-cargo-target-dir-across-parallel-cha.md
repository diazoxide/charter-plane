# Sharing one CARGO_TARGET_DIR across parallel charter worktrees makes sib

_2026-09-26 20:36 · persistent_

Sharing one CARGO_TARGET_DIR across parallel charter worktrees makes sibling builds clobber each other's charter-core artifacts (cargo's metadata hash for a workspace path member does not depend on the worktree path). Symptom: E0599 'no method named X' whose 'help:' cites a line number from ANOTHER worktree's source. Fix: touch the changed file in crates/charter-core and retry; it is not a code defect (SI-6, 2026-09-26).
