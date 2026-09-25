# When debugging a 'charter moved my workspace' style report, first chec

_2026-09-25 · persistent_

When debugging a 'charter moved my workspace' style report, first check that the instrumentation used THIS session's id. Issue #254 was filed after a diagnostic hardcoded another session's uuid, so every reading described a parallel session — correctly — and two rounds of conclusions were wrong before the harness transcript settled it. The transcript at ~/.claude/projects/<slug>/<sid>.jsonl is the authoritative record of what a session actually ran; grep it for the workspace name before theorising. And any state write nobody types (a seeded pointer, an auto-selected workspace) must leave a trace entry, or the confusion recurs.
