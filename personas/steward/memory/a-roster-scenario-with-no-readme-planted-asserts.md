# A green test is not evidence that it watches anything. A charter-app s

_2026-09-25 · persistent_

A green test is not evidence that it watches anything. A charter-app scenario about the persona roster block ran against a fixture plane with no README.md, so roster::splice found no markers, wrote nothing, and the test passed even under a mutation that reintroduced the bug it was written for. Any test of the roster block must plant a README carrying both markers. Only a mutation proof run found it. Also: the GitHub step-log view truncates long jobs; fetch the full log through the actions jobs logs API to read a summary printed at the end.
