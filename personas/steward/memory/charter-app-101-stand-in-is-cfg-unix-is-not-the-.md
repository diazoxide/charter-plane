# charter-app #101 (stand-in is cfg(unix)) is NOT the prerequisite for the

_2026-09-23 02:40 · persistent_

charter-app #101 (stand-in is cfg(unix)) is NOT the prerequisite for the Windows test suite: measured on origin/main, crates/*/tests/*.rs has 54 uses of std::os::unix::fs::symlink across 17 files (fixture_planes.rs alone 18) vs 30 stand_in:: uses across 12. Land #101 in full and 17 test files still do not compile. The wall behind stand-in is #97's question (what a link is on Windows), not a stand-in question.
