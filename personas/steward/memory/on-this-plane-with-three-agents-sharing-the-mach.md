# With several agents sharing this machine, a local FULL test run is not

_2026-09-25 · persistent_

With several agents sharing this machine, a local FULL test run is not evidence: on 2026-09-12 four full runs were killed at 90-97% while sibling agents ran their own suites. Coordinator ruling: run TARGETED tests locally (everything the change touches) and read CI's jobs, one by one, as the full-suite evidence. A CI red where the targeted local runs were green is a finding to report, not a reason to start a local full run.
