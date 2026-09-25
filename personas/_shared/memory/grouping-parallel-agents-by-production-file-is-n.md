# Grouping parallel agents by production file is not enough: tests are t

_2026-09-25 · persistent_

Grouping parallel agents by production file is not enough: tests are the shared surface where they collide. Measured 2026-09-03 with five concurrent agents grouped by source-file ownership: two touched no production file in common and still conflicted in one shared test fixture, where each had a needed but different change (one supplied the plane the test needed, the other the directory). Taking either side alone yields a green fixture that asserts nothing. Rules: (1) when briefing parallel agents, fence shared test fixtures and helpers (charter-app's tests/ support modules, fixtures/, e2e helpers) as explicitly as production files; (2) a rebase onto a moved base invalidates a mutation verdict charged against the diff; (3) when a fixture conflict has two edits that look redundant, ask what question each isolates before dropping one.
