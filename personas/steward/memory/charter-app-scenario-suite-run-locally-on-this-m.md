# charter-app scenario suite, run locally on this machine 2026-09-22: it i

_2026-09-22 23:30 · persistent_

charter-app scenario suite, run locally on this machine 2026-09-22: it is green, but only when nothing else is building. Two ways a local run lies. (1) Under load from other agents' cargo builds the app process dies mid-spec (ECONNREFUSED on every later command) and EVERY test in the file fails — read the FIRST failure, not the count. (2) 'shows the CI state the forge cache holds' is racy on its own: focusing a workspace kicks a real gl-refresh, and within about five seconds it overwrites the fixture's seeded 'failed #41' with 'no pipeline recorded', so that repo test fails locally while passing in CI. And a mutation probe that only greps for a cross reads a run where the spec never ran as STILL GREEN — always assert the spec RAN and that the baseline is green before believing any verdict.
