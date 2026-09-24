# Test-oracle lesson from charter-app M0.5 (2026-09-17), cost two wrong te

_2026-09-17 18:59 · persistent_

Test-oracle lesson from charter-app M0.5 (2026-09-17), cost two wrong tests: a test that compares two terminals' final SCREENS cannot see output lost in the middle of a stream — the missing lines scroll away, so a deliberate 2ms gap injected into the snapshot/stream handover still passed. Assert on what the consumer was SENT (every line number of a 100k-line flood, in order, once each), not on where it ended up. Same run: a 'mid-flood' test that waited for line 100 before attaching was vacuous because the flood finished first — assert the program is STILL RUNNING (wait(Duration::ZERO) == None) at the moment the test claims to interleave.
