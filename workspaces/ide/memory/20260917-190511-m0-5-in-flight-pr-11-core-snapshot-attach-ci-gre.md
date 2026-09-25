# M0.5 in flight: PR #11 (core snapshot + attach; CI green; reviewed, nine

_2026-09-17 19:05 · persistent_

M0.5 in flight: PR #11 (core snapshot + attach; CI green; reviewed, nine findings fixed) and PR #13 (app tabs/splits/typed IPC, stacked on #11, under review). Scenario tests on branch m0.5-scenario drive the real app through @wdio/tauri-service's embedded provider; they already found two defects — typing needs the xterm screen focused, and the app dies around 50 tabs (registry-level 50 sessions are fine, so it is above the core).
