# Moving where a value is read can move it out from under a test guard. 

_2026-09-25 · persistent_

Moving where a value is read can move it out from under a test guard. Found 2026-09-11 on the Python charter: the test plane-guard refused the operator's real charter.local.toml only through the setting that carried the value, so once the code read the file lazily, several tests read the operator's real file. On a machine whose checkout IS the plane, that is the operator's own settings. Rule: a guard belongs on the file open (or the fence around the plane root), not on the setting that happened to carry the value, and moving where a value is read means re-checking what guarded it. In charter-app, verify after a test run that nothing new appeared under the real plane.
