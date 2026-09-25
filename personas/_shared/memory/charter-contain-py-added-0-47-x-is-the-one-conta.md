# charter-core's contain module (crates/charter-core/src/contain.rs, por

_2026-09-25 · persistent_

charter-core's contain module (crates/charter-core/src/contain.rs, ported from charter/contain.py) is the one containment helper for names read out of committed plane files: segment_ok checks shape and child does a lexical join. Containment is lexical on purpose: following symlinks would do only half of #336 and would refuse planes that symlink a persona directory. Route every name that comes from a committed file through it instead of writing a new check. See also charter-app#96: segment_ok must also refuse names Windows resolves elsewhere, because planes travel.
