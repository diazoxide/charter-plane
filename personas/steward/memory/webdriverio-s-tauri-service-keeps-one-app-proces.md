# WebdriverIO's Tauri service keeps ONE app process for every spec file in

_2026-09-17 23:24 · persistent_

WebdriverIO's Tauri service keeps ONE app process for every spec file in a run (verified charter-app 2026-09-17: the same pid served four bench spec files, 32 min old, still holding the first spec's sessions). To measure or test from a clean app, run wdio once per spec file ('npx wdio run <conf> --spec <file>') — that is what tools/bench.mjs does. Also: a value returned from browser.execute that has an 'error' key is read by @wdio/tauri-service as a FAILED call and retried, so a poll result must name its failure something else ('trouble').
