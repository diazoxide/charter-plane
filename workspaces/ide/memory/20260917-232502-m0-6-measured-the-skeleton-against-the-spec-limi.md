# M0.6: measured the skeleton against the spec limits on the operator's M4

_2026-09-17 23:25 · persistent_

M0.6: measured the skeleton against the spec limits on the operator's M4 Pro (2026-09-17). Stack locked in charter PR 1133 (ADR 0026), benchmark in charter-app PR 18 (node tools/bench.mjs). Met: 50 sessions, bursts (37.4 MB/s at 13 MB vs tmux 27.0), keystroke worst 33 ms under 49 streamers, switches under 53 ms, cold start 341 ms, idle hidden session 20.7 MB at the 5000-line cap. Missed: hook call 101.5 ms through Python charter (Rust binary 1.8 ms, M3's to fix) and a ?2026 animation at 1 fps when a harness pauses inside an open update (M1: the core should never end a chunk inside one). Renderer locked to xterm.js's DOM renderer; WebGL won nothing and 20 panes kept contexts anyway.
