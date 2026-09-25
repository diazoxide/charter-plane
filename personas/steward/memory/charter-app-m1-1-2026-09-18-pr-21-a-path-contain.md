# charter-app M1.1 (2026-09-18, PR #21): a path-containment gate that reso

_2026-09-18 13:57 · persistent_

charter-app M1.1 (2026-09-18, PR #21): a path-containment gate that resolves with a LEXICAL '..' fold is broken wherever the path can contain an unresolved symlink. Two committed symlinks (jump -> outside, MEMORY.md -> jump/../target) made the gate judge a path inside the plane while the kernel wrote outside it; confirmed writing an attacker's authorized_keys. Only the DANGLING case escapes — canonicalize() catches it when the target exists. Fix: resolve component by component, follow each symlink as reached, pop '..' only from the already-resolved prefix. Four reviews on one branch each found a hole in the previous fix, same direction each time: the gate sat one level shallower than the write.
