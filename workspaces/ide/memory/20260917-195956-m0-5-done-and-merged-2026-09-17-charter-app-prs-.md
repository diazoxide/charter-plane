# M0.5 done and merged (2026-09-17): charter-app PRs #11 (core snapshot + 

_2026-09-17 19:59 · persistent_

M0.5 done and merged (2026-09-17): charter-app PRs #11 (core snapshot + Session::attach), #14 (tabs, splits, typed IPC, visible-only panes) and #15 (scenario tests on macOS + Linux CI). Scenario suite drives the real app through @wdio/tauri-service's embedded provider with fake-harness in every pane; 6 tests, green in CI on both OSes, incl. a tab returning to the front redrawing from the core's snapshot and 50 sessions counted with ps. Two reviews found 17 real defects, all fixed. Open follow-ups: issue #16 (app died once at ~50 tabs, not reproduced) and, if M0.6 misses the =100ms pane switch, hold each session's terminal outside the React tree (a split changes tree depth and rebuilds panes below it).
