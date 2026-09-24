# When a session's state looks wrong (wrong workspace, wrong persona), c

_2026-09-25 · persistent_

When a session's state looks wrong (wrong workspace, wrong persona), check the instrumentation first: in 2026-08 two investigations reached confident wrong conclusions from pointer files because the diagnostic script had another session's id hardcoded, so every reading described a parallel session correctly (issue #254, closed not-a-defect). Method: (a) confirm the probe uses THIS session's id; (b) read the harness transcript (~/.claude/projects/<slug>/<sid>.jsonl for Claude Code), which is the authoritative record of what a session ran; (c) only then suspect the code.
